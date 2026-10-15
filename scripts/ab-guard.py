#!/usr/bin/env python3
"""Interleaved A/B of builds / per-arm environments on a unified-memory gfx1151 (one request per target and server).

Each arm runs in a fresh Strata server per round; arms are interleaved round by round. Requires exclusive GPU use.
Guarded copy of ab-armenv-runs.py: the client is longprompt-guard.py (waits for /proc/vmstat to settle before each prompt,
flags a prompt that met page migration or direct reclaim, --prime reads a discarded prompt first).  Round 0 is discarded; then
rounds continue until every target has --pairs pairs with neither side flagged (later rounds read only the targets still short),
or --max-rounds measured rounds were run.  Two arms only.
"""
import argparse
import json
import os
import pathlib
import signal
import subprocess
import sys
import time
import urllib.request

def terminate(signum, frame):
    raise SystemExit(f'terminated by signal {signum}')

signal.signal(signal.SIGTERM, terminate)

ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument('--root', type=pathlib.Path, required=True)    # Strata checkout (serve/, tools/, data/)
ap.add_argument('--build', type=pathlib.Path, required=True)   # build dir with ./strata
ap.add_argument('--alt-build', action='append', default=[])   # NAME=DIR: an arm 'F-borrow@NAME' runs DIR/strata
ap.add_argument('--model', type=pathlib.Path, required=True)
ap.add_argument('--sdk', type=pathlib.Path, required=True)
ap.add_argument('--out', type=pathlib.Path, required=True)
ap.add_argument('--arms', default='D-borrow,D-own,F-borrow,F-own')
ap.add_argument('--rounds', type=int, default=3)
ap.add_argument('--first-round', type=int, default=1)
ap.add_argument('--targets', default='4096,32768,128000')
ap.add_argument('--runs', type=int, default=1)   # per target; run 1 of a fresh engine can meet the kernel's compaction (var4k/)
ap.add_argument('--port', type=int, default=18751)
ap.add_argument('--extra-args', default='')   # appended to every arm's engine args
ap.add_argument('--native', default='UD-IQ4_XS/Qwen3.8-Flash-Next-UD-IQ4_XS-00001-of-00003.gguf')   # first shard, under --model
ap.add_argument('--budget-gib', default='55')   # --resident-budget-gib
ap.add_argument('--arm-env', action='append', default=[], help='ARM:KEY=VALUE; recorded per arm')
ap.add_argument('--env', action='append', default=[])   # extra KEY=VALUE for every arm's engine
ap.add_argument('--prime', type=int, default=4096)   # a discarded prompt of this size right after the warm-up (0 = none)
ap.add_argument('--pairs', type=int, default=11)   # clean pairs wanted per target
ap.add_argument('--max-rounds', type=int, default=16)   # measured rounds at most
a = ap.parse_args()
a.out = a.out.resolve()   # the server runs with --root as its working directory
a.out.mkdir(parents=True, exist_ok=True)
builds = {'': a.build, **{k: pathlib.Path(v) for k, v in (x.split('=', 1) for x in a.alt_build)}}
url = f'http://127.0.0.1:{a.port}'
PY = sys.executable
base_env = {**os.environ, 'PYTHONUNBUFFERED': '1', 'ROCM_PATH': str(a.sdk), 'HIP_PATH': str(a.sdk), 'HIP_PLATFORM': 'amd',
            'LD_LIBRARY_PATH': ':'.join(str(a.sdk / x) for x in ['lib', 'lib/rocm_sysdeps/lib', 'lib/llvm/lib']),
            'STRATA_HIPBLASLT_TUNING': str(a.root / 'tools/hip/gfx1151-hipblaslt-100401.txt')}
base_env = {k: v for k, v in base_env.items() if not k.startswith('STRATA_') or k == 'STRATA_HIPBLASLT_TUNING'}
FAST = dict(STRATA_PF_FUSED='1', STRATA_PF_GEMM='1', STRATA_HC_UPMIX='1', STRATA_PA_FAST='1', STRATA_HIP_WMMA='1',
            STRATA_SELECT_WMMA='1', STRATA_HC_Q8='1', STRATA_PF_SWITCH_MIN_T='2048', STRATA_PREFILL_STREAM_MIN='128')
base_env.update(kv.split('=', 1) for kv in a.env)


def gtt_bytes():
    return sum(int(p.read_text()) for p in pathlib.Path('/sys/class/drm').glob('card*/device/mem_info_gtt_used'))


initial_gtt = gtt_bytes()


def event(kind, **fields):
    row = dict(timestamp=time.time(), event=kind, **fields)
    with (a.out / 'events.jsonl').open('a') as f:
        f.write(json.dumps(row) + '\n')
    print(json.dumps(row), flush=True)


def group_stop(p):
    if p is None:
        return
    try:
        os.killpg(p.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        p.wait(timeout=60)
    except subprocess.TimeoutExpired:
        os.killpg(p.pid, signal.SIGKILL)
        p.wait(timeout=15)


def wait_released():
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        alive = []
        for p in pathlib.Path('/sys/class/kfd/kfd/proc').glob('*'):
            try:
                if any(str(b).encode() in (pathlib.Path('/proc') / p.name / 'cmdline').read_bytes() for b in builds.values()):
                    alive.append(p.name)
            except FileNotFoundError:
                continue
        if not alive and gtt_bytes() <= initial_gtt + 512 * 1024 ** 2:
            return
        time.sleep(1)
    raise RuntimeError('Strata GPU mappings/GTT were not released')


def get(path):
    with urllib.request.urlopen(url + path, timeout=10) as r:
        return json.load(r)


def config(name, fast, borrow, build):
    args = ['--pack', str(a.model / 'pack'),
            '--native', str(a.model / a.native),
            '--expert-profile', str(a.root / 'data/expert-profile.bin'), '--expert-cache', 'auto',
            '--resident-budget-gib', a.budget_gib, '--prefill', '16384' if fast else 'auto', '--spec', '4',
            '--spec-min-p', '0.5', '--mtp', str(a.model / 'mtp/rt'), '--max-context', '131072', '--kv', 'int8',
            '--kv-resident', '32768']
    if fast:
        args += ['--lookup-chain', '3', '--mtp-q4', 'all']
    if not borrow:
        args += ['--no-prefill-borrow']
    args += a.extra_args.split()
    cfg = dict(exe=str(build / 'strata'), args=args, cwd=str(a.root), tokenizer=str(a.model / 'pack/tokenizer'),
               model_name='strata', log=str(a.out / (name + '-engine.log')), host='127.0.0.1', port=a.port,
               parallel=1, open_browser=False)
    path = a.out / (name + '-config.json')
    path.write_text(json.dumps(cfg, indent=2))
    return path


def run_arm(arm, rnd, targets):
    spec, _, bname = arm.partition('@')
    mode, loan = spec.split('-')
    fast, borrow = mode == 'F', loan == 'borrow'
    name = f'{arm.replace("@", "_")}-r{rnd}'
    wait_released()
    cfg = config(name, fast, borrow, builds[bname])
    env = {**base_env, **(FAST if fast else {})}
    for spec in a.arm_env:
        env_arm, kv = spec.split(':', 1)
        if env_arm == arm:
            k, v = kv.split('=', 1)
            env[k] = v
    (a.out / (name + '-env.json')).write_text(json.dumps({k: v for k, v in env.items() if k.startswith('STRATA_')}, indent=2))
    log = (a.out / (name + '-server.log')).open('w')
    server = subprocess.Popen([PY, str(a.root / 'serve/server.py'), '--engine', 'strata', '--config', str(cfg),
                               '--host', '127.0.0.1', '--port', str(a.port)],
                              cwd=a.root, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    event('server-start', arm=arm, round=rnd, pid=server.pid)
    try:
        deadline = time.monotonic() + 900
        while True:
            if server.poll() is not None:
                raise RuntimeError(f'{name}: server exited {server.returncode}')
            try:
                if get('/health').get('status') in ['ok', 'healthy', 'ready']:
                    break
            except (OSError, ValueError):
                pass
            if time.monotonic() > deadline:
                raise TimeoutError(name)
            time.sleep(2)
        event('server-ready', arm=arm, round=rnd)
        res = a.out / name
        cmd = [PY, str(pathlib.Path(__file__).resolve().parent / 'longprompt-guard.py'), '--root', str(a.root), '--pack',
               str(a.model / 'pack'), '--url', url, '--out', str(res), '--targets', targets, '--runs', str(a.runs), '--prime', str(a.prime),
               f'--tag=-r{rnd}']
        with (a.out / (name + '-client.log')).open('w') as f:
            rc = subprocess.run(cmd, cwd=a.root, env=base_env, stdout=f, stderr=subprocess.STDOUT, timeout=7200).returncode
        event('client-done', arm=arm, round=rnd, returncode=rc)
        if rc:
            raise RuntimeError(f'{name}: client exited {rc}')
    finally:
        group_stop(server)
        log.close()


def clean_pairs():
    """target -> measured rounds (>= 1) in which every arm has an unflagged row."""
    arms = a.arms.split(',')
    got = {}
    for res in a.out.glob('*-r*/results.json'):
        name = res.parent.name
        arm, rnd = name.rsplit('-r', 1)[0].replace('_', '@'), int(name.rsplit('-r', 1)[1])
        if rnd < 1:
            continue
        for row in json.loads(res.read_text()):
            if row['label'].startswith('tokens-') and not row['reclaim']['flag']:
                got.setdefault(int(row['label'].split('-')[1]), {}).setdefault(rnd, set()).add(arm)
    return {t: sum(1 for v in got.get(t, {}).values() if v >= set(arms)) for t in map(int, a.targets.split(','))}


arms0 = a.arms.split(',')
if len(arms0) < 2:
    raise SystemExit('ab-guard: two arms or more')
rnd = a.first_round
while True:
    have = clean_pairs()
    short = [t for t in map(int, a.targets.split(',')) if have[t] < a.pairs]
    if rnd > 0:
        event('clean-pairs-before', round=rnd, have=have)
    if not short or rnd > a.max_rounds:
        break
    targets = a.targets if rnd == 0 else ','.join(map(str, short))
    k = (rnd - 1) % len(arms0)   # the order rotates by one arm per round
    arms = arms0[k:] + arms0[:k] if rnd > 0 else arms0
    for arm in arms:
        run_arm(arm, rnd, targets)
    rnd += 1
event('done', have=clean_pairs())
wait_released()
