#!/bin/bash
# The candidate's model evidence on the rebased build: whole-prompt A/B with ab-guard.py (F then D), then first-token KL.
set -uo pipefail
H=/data/ssd/llm-experiments/gdn-chunk-20261012
b=/data/ssd/llm-build/strata-halo-gdnc-r4
cd $H
for mode in F D; do
  /data/ssd/llm-build/strata-venv/bin/python scripts/ab-guard.py --root /data/ssd/llm-src/strata-gdnc --build $b --alt-build off=$b --alt-build on=$b \
   --model /data/ssd/llm/strata-qwen38-ud-iq4xs --sdk /data/ssd/llm-build/strata-sdk-7.14.1/install --out $H/e2e6/$mode \
   --arms $mode-borrow@off,$mode-borrow@on --first-round 0 --targets 4096,32768,128000 --pairs 11 --max-rounds 16 --port 18752 \
   --arm-env $mode-borrow@off:STRATA_GDN_CHUNKED=0 --arm-env $mode-borrow@on:STRATA_GDN_CHUNKED=1 > $H/e2e6/$mode.log 2>&1
done
touch $H/e2e6.done
scripts/kl5.sh > kl5.log 2>&1
touch $H/remeasure-r5.done
