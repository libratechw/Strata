#!/usr/bin/env python3
"""Task check of one Strata engine configuration (gfx1151): HumanEval every second problem (82, EvalPlus 0.3.1 base and plus)
and 30 generated reasoning tasks with exact answers.  Greedy, reasoning off, one run per arm; the server is started with the
arm's environment like klrun.py.  Usage: taskcheck.py --out DIR --arm NAME --model {q4kxl,iq4xs} [--env K=V ...] [--harness]"""
import argparse
import hashlib
import json
import multiprocessing
import os
import pathlib
import random
import re
import signal
import subprocess
import sys
import time
import urllib.request

ap = argparse.ArgumentParser()
ap.add_argument('--out', type=pathlib.Path, required=True)
ap.add_argument('--arm', required=True)
ap.add_argument('--model', choices=['q4kxl', 'iq4xs'], required=True)
ap.add_argument('--exe', required=True)
ap.add_argument('--root', type=pathlib.Path, required=True)
ap.add_argument('--env', action='append', default=[])
ap.add_argument('--harness', action='store_true', help='the section-5 switches of docs/STRIX_HALO.md')
ap.add_argument('--port', type=int, default=18772)
ap.add_argument('--max-tokens', type=int, default=1024)
ap.add_argument('--grade-only', action='store_true')
a = ap.parse_args()
multiprocessing.set_start_method('fork')   # Python 3.14 defaults to forkserver, which EvalPlus's module-level pool cannot use
out = (a.out / a.arm).resolve()
out.mkdir(parents=True, exist_ok=True)
url = f'http://127.0.0.1:{a.port}'


def reasoning_tasks(n=30, seed=20261017):
    """Generated tasks with one exact answer each: arithmetic word problems, weekdays, orderings, base conversion, counting."""
    rng = random.Random(seed)
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    names = ['Ana', 'Ben', 'Chika', 'Dev', 'Emi', 'Farid', 'Gita', 'Hugo']
    tasks = []
    for i in range(n):
        kind = i % 5
        if kind == 0:
            a1, b1, c1, d1 = rng.randint(12, 40), rng.randint(3, 9), rng.randint(2, 6), rng.randint(5, 30)
            q = (f'A shop packs {a1} boxes with {b1} pens each. It sells {c1} full boxes, then receives {d1} loose pens and '
                 f'packs nothing more. How many pens does the shop have now?')
            ans = str((a1 - c1) * b1 + d1)
        elif kind == 1:
            k, off = rng.randint(0, 6), rng.randint(20, 400)
            q = f'Today is {days[k]}. What day of the week is it {off} days from today?'
            ans = days[(k + off) % 7]
        elif kind == 2:
            ppl = rng.sample(names, 4)
            order = ppl[:]
            rng.shuffle(order)   # order[0] is the tallest
            facts = [f'{order[j]} is taller than {order[j + 1]}.' for j in range(3)]
            rng.shuffle(facts)
            q = ' '.join(facts) + ' Who is the shortest? Answer with the name only.'
            ans = order[-1]
        elif kind == 3:
            v = rng.randint(100, 900)
            q = f'Write the decimal number {v} in binary. Answer with the binary digits only.'
            ans = bin(v)[2:]
        else:
            lo, step, hi = rng.randint(3, 20), rng.randint(2, 7), rng.randint(150, 400)
            q = (f'How many integers between {lo} and {hi} inclusive leave a remainder of {lo % step} when divided by {step}?')
            ans = str(sum(1 for x in range(lo, hi + 1) if x % step == lo % step))
        tasks.append({'id': i, 'prompt': q + '\nThink step by step, then end with a final line "Answer: <answer>".', 'answer': ans})
    return tasks


def chat(content, max_tokens):
    r = {'model': 'strata', 'messages': [{'role': 'user', 'content': content}], 'temperature': 0,
         'reasoning_effort': 'none', 'max_tokens': max_tokens, 'stream': False}
    req = urllib.request.Request(url + '/v1/chat/completions', data=json.dumps(r).encode(), headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=3600) as resp:
        return json.load(resp)['choices'][0]['message'].get('content') or ''


def code_of(text, prompt, entry):
    blocks = re.findall(r'```(?:python|py)?\n(.*?)```', text, re.S)
    code = max(blocks, key=len) if blocks else text
    return code if f'def {entry}' in code else prompt + code


from evalplus.data import get_human_eval_plus, get_human_eval_plus_hash
from evalplus.eval import PASS, untrusted_check
from evalplus.evaluate import get_groundtruth

problems_all = get_human_eval_plus()
ids = sorted(problems_all, key=lambda x: int(x.split('/')[-1]))[::2]   # every second problem: 0, 2, ..., 162
problems = {k: problems_all[k] for k in ids}
digest = get_human_eval_plus_hash()

if not a.grade_only:
    S = pathlib.Path('<ROCm 7.14.1>')
    env = {k: v for k, v in os.environ.items() if not k.startswith('STRATA_')}
    env.update(PYTHONUNBUFFERED='1', ROCM_PATH=str(S), HIP_PATH=str(S), HIP_PLATFORM='amd',
               LD_LIBRARY_PATH=':'.join(str(S / x) for x in ['lib', 'lib/rocm_sysdeps/lib', 'lib/llvm/lib']))
    if a.model == 'q4kxl':
        model = pathlib.Path('<model dir q4kxl>')
        native, budget = 'UD-Q4_K_XL/Qwen3.8-Flash-Next-UD-Q4_K_XL-00001-of-00004.gguf', '72'
    else:
        model = pathlib.Path('<model dir iq4xs>')
        native, budget = 'UD-IQ4_XS/Qwen3.8-Flash-Next-UD-IQ4_XS-00001-of-00003.gguf', '55'
    if a.harness:
        env.update(STRATA_HIPBLASLT_TUNING=str(a.root / 'tools/hip/gfx1151-hipblaslt-100401.txt'), STRATA_PF_GEMM='1',
                   STRATA_HC_UPMIX='1', STRATA_PA_FAST='1', STRATA_HIP_WMMA='1', STRATA_SELECT_WMMA='1', STRATA_HC_Q8='1',
                   STRATA_PREFILL_STREAM_MIN='128')
    env.update(kv.split('=', 1) for kv in a.env)
    args = ['--pack', str(model / 'pack'), '--native', str(model / native), '--expert-profile',
            str(a.root / 'data/expert-profile.bin'), '--expert-cache', 'auto', '--resident-budget-gib', budget,
            '--prefill', '16384', '--spec', '4', '--max-context', '131072', '--kv', 'int8', '--kv-resident', '32768']
    cfg = dict(exe=a.exe, args=args, cwd=str(a.root), tokenizer=str(model / 'pack/tokenizer'), model_name='strata',
               log=str(out / 'engine.log'), host='127.0.0.1', port=a.port, parallel=1, open_browser=False)
    (out / 'config.json').write_text(json.dumps(cfg, indent=2))
    (out / 'env.json').write_text(json.dumps({k: v for k, v in env.items() if k.startswith('STRATA_') and 'HIPBLASLT' not in k}, indent=2))
    log = (out / 'server.log').open('w')
    server = subprocess.Popen([sys.executable, str(a.root / 'serve/server.py'), '--engine', 'strata', '--config', str(out / 'config.json'),
                               '--host', '127.0.0.1', '--port', str(a.port)], cwd=a.root, env=env, stdout=log,
                              stderr=subprocess.STDOUT, start_new_session=True)
    try:
        deadline = time.monotonic() + 1500
        while True:
            if server.poll() is not None:
                raise RuntimeError(f'server exited {server.returncode}')
            try:
                urllib.request.urlopen(url + '/health', timeout=10).read()
                break
            except OSError:
                pass
            if time.monotonic() > deadline:
                raise TimeoutError('startup')
            time.sleep(2)
        chat('Write one sentence about the sea.', 32)   # warm-up
        samples = []
        for tid in ids:
            p = problems[tid]
            text = chat('Complete the following Python function. Reply with the complete function in one ```python block.\n\n' + p['prompt'],
                        a.max_tokens)
            samples.append({'task_id': tid, 'response': text, 'solution': code_of(text, p['prompt'], p['entry_point'])})
            print('he', tid, len(text), flush=True)
        (out / 'humaneval-samples.json').write_text(json.dumps(samples, indent=2))
        rs = []
        for t in reasoning_tasks():
            text = chat(t['prompt'], 1536)
            rs.append({**t, 'response': text})
            print('rs', t['id'], flush=True)
        (out / 'reasoning-samples.json').write_text(json.dumps(rs, indent=2))
    finally:
        try:
            os.killpg(server.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            server.wait(timeout=600)
        except subprocess.TimeoutExpired:
            os.killpg(server.pid, signal.SIGKILL)
        log.close()

# grading (after the server is gone)
samples = json.loads((out / 'humaneval-samples.json').read_text())
oracle = get_groundtruth(problems, digest + '-everysecond-strata477', [])
rows = []
for s in samples:
    p, o = problems[s['task_id']], oracle[s['task_id']]
    res = {}
    for part in ('base', 'plus'):
        status, _ = untrusted_check('humaneval', s['solution'], p[part + '_input'], p['entry_point'], o[part], p['atol'],
                                    o[part + '_time'], fast_check=True)
        res[part] = status == PASS
    rows.append({'task_id': s['task_id'], **res, 'solution_sha256': hashlib.sha256(s['solution'].encode()).hexdigest()})
rs = json.loads((out / 'reasoning-samples.json').read_text())
rrows = []
for t in rs:
    m = re.findall(r'Answer:\s*(.+)', t['response'])
    got = m[-1].strip().strip('.*` ').lower() if m else ''
    rrows.append({'id': t['id'], 'ok': got == t['answer'].lower(), 'got': got, 'want': t['answer']})
summary = {'arm': a.arm, 'humaneval_n': len(rows), 'base': sum(r['base'] for r in rows), 'plus': sum(r['plus'] for r in rows),
           'reasoning_n': len(rrows), 'reasoning': sum(r['ok'] for r in rrows)}
(out / 'graded.json').write_text(json.dumps({'summary': summary, 'humaneval': rows, 'reasoning': rrows}, indent=2))
print(json.dumps(summary), flush=True)
