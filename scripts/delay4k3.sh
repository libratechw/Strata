#!/bin/bash
# Fresh engines (defaults arm, chunked off), the 4K prompt twice after a DELAY after /health; alternating DELAY 0 and 20.
# vmstat 1 runs alongside.  Usage: delay4k.sh <pairs>
set -uo pipefail
H=/data/ssd/llm-experiments/gdn-chunk-20261012
PY=/data/ssd/llm-build/strata-venv/bin/python
root=/data/ssd/llm-src/strata-gdnc
src=$H/e2e4/D/D-borrow_off-r0
for i in $(seq 1 ${1:-4}); do for d in ${DELAYS:-0 20}; do
  out=$H/var4k/${PREFIX:-delay}-$d-$i; mkdir -p $out
  python3 -c "import json,sys;c=json.load(open('$src-config.json'));c['log']='$out/engine.log';json.dump(c,open('$out/config.json','w'),indent=2)"
  cd $root
  env STRATA_HIPBLASLT_TUNING=$root/tools/hip/gfx1151-hipblaslt-100401.txt STRATA_GDN_CHUNKED=0 ${EXTRA_ENV:-} setsid $PY serve/server.py --engine strata --config $out/config.json --host 127.0.0.1 --port 18752 > $out/server.log 2>&1 &
  spid=$!
  (while true; do echo "T $(date +%s.%N)"; grep -E "^(compact_|pgmigrate|pgscan|pgsteal|thp_migration|thp_split|numa_|allocstall|kswapd|pgfault|pgmajfault|pswp|nr_free_pages|workingset_refault)" /proc/vmstat; sleep 0.5; done) > $out/procvm.log & vpid=$!
  setsid sh -c "sleep 900 | amd-smi event --json" > $out/smi-event.log 2>&1 & epid=$!
  for k in $(seq 1 450); do curl -sf http://127.0.0.1:18752/health >/dev/null && break; sleep 2; done
  date +%s.%N > $out/ready.txt
  sleep $d
  PYTHONUNBUFFERED=1 $PY /data/ssd/llm-experiments/strata-uma-borrow-20261010/scripts/longprompt.py --root $root --pack /data/ssd/llm/strata-qwen38-ud-iq4xs/pack --url http://127.0.0.1:18752 --out $out/res --targets 4096 --runs 2 --tag=-d$d-$i 2>&1 | while IFS= read -r l; do echo "$(date +%s.%N) $l"; done > $out/client.log
  kill $vpid 2>/dev/null; kill -- -$epid 2>/dev/null
  kill -INT -- -$spid; for k in $(seq 1 60); do kill -0 $spid 2>/dev/null || break; sleep 1; done; kill -9 -- -$spid 2>/dev/null
  while pgrep -x strata >/dev/null; do sleep 1; done; sleep 3
  echo "delay $d #$i: $(grep -oE '"prompt_ms": [0-9.]+' $out/client.log | tail -2 | grep -oE '[0-9.]+$' | tr '\n' ' ')"
done; done
echo ALLDONE
