#!/usr/bin/env python3
"""First-token KL of prompt paths on Strata (gfx1151): one engine start per arm, the same natural-text prompts
(Strata's own docs and sources, 1.5K-24K tokens), STRATA_DUMP_FIRST_LOGITS=<out>/logits writes the logits of the token after
each prompt; klcompare.py compares the arms.  Usage: klrun.py --out DIR --arm NAME --model {q4kxl,iq4xs} [--env K=V ...]"""
import argparse
import json
import hashlib
import os
import pathlib
import signal
import subprocess
import sys
import time
import urllib.request

ap = argparse.ArgumentParser()
ap.add_argument('--out', type=pathlib.Path, required=True)
ap.add_argument('--arm', required=True)
ap.add_argument('--model', choices=['q4kxl', 'iq4xs'], required=True)
ap.add_argument('--exe', default='/data/ssd/llm-build/strata-halo-142/strata')
ap.add_argument('--root', type=pathlib.Path, default=pathlib.Path('/data/ssd/llm-src/strata-142'))
ap.add_argument('--env', action='append', default=[])
ap.add_argument('--harness', action='store_true', help='the section-5 switches of docs/STRIX_HALO.md (rounding-level ones too)')
ap.add_argument('--port', type=int, default=18771)
ap.add_argument('--lengths', default='1500,3000,4500,6000,8000,10000,12000,14000,16000,18000,20000,24000')
a = ap.parse_args()
out = (a.out / a.arm).resolve()
out.mkdir(parents=True, exist_ok=False)
S = pathlib.Path('/data/ssd/llm-build/strata-sdk-7.14.1/install')
url = f'http://127.0.0.1:{a.port}'
env = {k: v for k, v in os.environ.items() if not k.startswith('STRATA_')}
env.update(PYTHONUNBUFFERED='1', ROCM_PATH=str(S), HIP_PATH=str(S), HIP_PLATFORM='amd',
           LD_LIBRARY_PATH=':'.join(str(S / x) for x in ['lib', 'lib/rocm_sysdeps/lib', 'lib/llvm/lib']))
if a.model == 'q4kxl':
    model = pathlib.Path('/data/ssd/llm/strata-qwen38-ud-q4kxl')
    native, budget = 'UD-Q4_K_XL/Qwen3.8-Flash-Next-UD-Q4_K_XL-00001-of-00004.gguf', '72'
else:
    model = pathlib.Path('/data/ssd/llm/strata-qwen38-ud-iq4xs')
    native, budget = 'UD-IQ4_XS/Qwen3.8-Flash-Next-UD-IQ4_XS-00001-of-00003.gguf', '55'
if a.harness:
    env.update(STRATA_HIPBLASLT_TUNING=str(a.root / 'tools/hip/gfx1151-hipblaslt-100401.txt'), STRATA_PF_GEMM='1',
               STRATA_HC_UPMIX='1', STRATA_PA_FAST='1', STRATA_HIP_WMMA='1', STRATA_SELECT_WMMA='1', STRATA_HC_Q8='1',
               STRATA_PREFILL_STREAM_MIN='128')
env.update(kv.split('=', 1) for kv in a.env)
env['STRATA_DUMP_FIRST_LOGITS'] = str(out / 'logits')

sys.path[:0] = [str(a.root), str(a.root / 'tools')]
from strata_tokenizer import Tokenizer
from serve.frontend import ChatTemplate, openai_to_messages
d = model / 'pack/tokenizer'
vocab = json.loads((d / 'vocab.json').read_text())
toks = [None] * len(vocab)
for t, n in vocab.items():
    toks[n] = t
tok = Tokenizer(toks, (d / 'merges.txt').read_text().splitlines(), json.loads((d / 'token_type.json').read_text()))
tpl = ChatTemplate(d / 'chat_template.jinja')


def req(content):
    return {'model': 'strata', 'messages': [{'role': 'user', 'content': content}], 'temperature': 0,
            'reasoning_effort': 'none', 'max_tokens': 1, 'stream': False}


def count(r):
    m, tools, kw = openai_to_messages(r)
    return len(tok.encode(tpl.render(m, tools, **kw), parse_special=True))


# natural text: Strata's own docs and sources, rotated so the prompts differ in kind as well as in length
files = sorted(a.root.glob('docs/*.md')) + sorted(a.root.glob('src/**/*.cu')) + sorted(a.root.glob('src/**/*.cpp')) + sorted(a.root.glob('serve/*.py'))
corpus = []
for p in files:
    try:
        corpus.append(f'=== {p.relative_to(a.root)} ===\n' + p.read_text(errors='replace'))
    except OSError:
        pass
prompts = []
for i, n in enumerate(int(x) for x in a.lengths.split(',')):
    start = (i * 7) % len(corpus)
    text = ''.join(corpus[start:] + corpus[:start])[:n * 8]
    pre, end = 'Read the following material and answer in one word: is it mostly code or prose?\n\n', '\n\nAnswer:'
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if count(req(pre + text[:mid] + end)) <= n:
            lo = mid
        else:
            hi = mid - 1
    prompts.append(req(pre + text[:lo] + end))


def post(r):
    body = json.dumps(r).encode()
    (out / f"request.{post.counter}.json").write_bytes(body + b"\n")
    post.counter += 1
    with urllib.request.urlopen(urllib.request.Request(url + '/v1/chat/completions', data=body,
                                headers={'Content-Type': 'application/json'}), timeout=3600) as resp:
        return json.load(resp)


post.counter = 0

def terminate(signum, frame):
    raise SystemExit(f'terminated by signal {signum}')
signal.signal(signal.SIGTERM, terminate)

(out / 'provenance.json').write_text(json.dumps({'exe': a.exe, 'binary_sha256': hashlib.sha256(pathlib.Path(a.exe).read_bytes()).hexdigest(), 'runtime_root_head': subprocess.check_output(['git', '-C', str(a.root), 'rev-parse', 'HEAD'], text=True).strip(), 'binary_source_head': subprocess.check_output(['git', '-C', '/data/ssd/llm-src/strata-pr296', 'rev-parse', 'HEAD'], text=True).strip()}, indent=2))

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
    post(req('Write one sentence about the sea.'))   # warm-up = logits.0
    rows = []
    for i, r in enumerate(prompts):
        t0 = time.monotonic()
        resp = post(r)
        rows.append({'index': i + 1, 'prompt_tokens': resp['usage']['prompt_tokens'], 'seconds': time.monotonic() - t0,
                     'token': resp['choices'][0]['message'].get('content'), 'request_sha256': hashlib.sha256(json.dumps(r).encode()).hexdigest(), 'finish_reason': resp['choices'][0]['finish_reason']})
        print(rows[-1], flush=True)
    (out / 'rows.json').write_text(json.dumps(rows, indent=2))
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
print('done', flush=True)
