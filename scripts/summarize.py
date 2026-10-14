#!/usr/bin/env python3
"""Recompute the numbers of the docs/AMD_HIP.md section from runs/start-up.

Usage: summarize.py [RUNS_DIR]   (default: runs/start-up next to this script's parent)

Per run: prompt_ms of the first and second 4K prompt (from client.log) and the pgmigrate_success increment over each prompt
(from procvm.log: the last sample at or before the prompt's start to the first sample at or after start + prompt_ms).
With kfd-root.log present, the kfd-* runs also get the engine's QUEUE_EVICTION count per prompt.
"""
import csv, pathlib, re, statistics, sys

root = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parent.parent / 'runs/start-up'
SETTINGS = [('none', ('vm', 'kfd')), ('GPU_PINNED_MIN_XFER_SIZE=1048576', ('pinxfer',)),
            ('HSA_USERPTR_FOR_PAGED_MEM=0', ('nouserptr',)), ('compaction sysctls', ('nocomp',))]
LINE = 50_000

def samples(path):
    out, cur = [], None
    for l in open(path):
        f = l.split()
        if f and f[0] == 'T':
            cur = {'t': float(f[1])}; out.append(cur)
        elif cur is not None and len(f) == 2:
            cur[f[0]] = int(f[1])
    return out

def evictions(log):
    ev = []
    if not log.exists():
        return ev
    for l in open(log):
        if l.startswith('#'):
            continue
        f = l.split()
        if f[2] == 'QUEUE_EVICTION':
            wall, boot, ns = float(f[0]), int(f[1]), int(f[3])
            ev.append(wall - (boot - ns) / 1e9)
    return ev

EV = evictions(root / 'kfd-root.log')

def run(d):
    cl = (d / 'client.log').read_text()
    ms = [float(x) for x in re.findall(r'"prompt_ms": ([\d.]+)', cl)]   # warm-up, first, second
    S = samples(d / 'procvm.log')
    out = []
    for k in (1, 2):
        t0 = float(next(l.split()[0] for l in cl.splitlines() if f'start tokens-4096-run-{k}' in l))
        t1 = t0 + ms[k] / 1000
        a = max((s for s in S if s['t'] <= t0), key=lambda s: s['t'])
        b = min((s for s in S if s['t'] >= t1), key=lambda s: s['t'], default=S[-1])
        ev = sum(t0 <= t <= t1 for t in EV) if d.name.startswith('kfd') else None
        out.append((ms[k], b.get('pgmigrate_success', 0) - a.get('pgmigrate_success', 0), ev))
    return out

R = {d.name: run(d) for d in sorted(root.iterdir()) if d.is_dir()}
for name, ((m1, g1, e1), (m2, g2, e2)) in R.items():
    print(f'{name:13s} first {m1:7.1f} ms migr {g1:7d}' + (f' evictions {e1}' if e1 is not None else '') +
          f' | second {m2:7.1f} ms migr {g2:7d}' + (f' evictions {e2}' if e2 is not None else '') + f' | d {m1 - m2:6.0f}')

base = [v for n, v in R.items() if not n.startswith('nocomp')]
hit = [(p1[0] - p2[0]) for p1, p2 in base if p1[1] > LINE]
print(f'\nfirst 4K prompt: {len(hit)} of {len(base)} over {LINE} pages; {sum(d >= 100 for d in hit)} of those 100 ms or more '
      f'slower than the second, by {min(d for d in hit if d >= 100) / 1000:.2f}-{max(hit) / 1000:.2f} s')
print(f'second 4K prompt: {sum(p2[1] > LINE for p1, p2 in base)} of {len(base)} over {LINE} pages')

kfd = [p for n, v in R.items() if n.startswith('kfd') for p in v]
if EV:
    m = [p for p in kfd if p[1] > 0]; z = [p for p in kfd if p[1] == 0]
    print(f'kfd runs: evicted in {sum(p[2] > 0 for p in m)} of {len(m)} prompts with any page migration, '
          f'{sum(p[2] > 0 for p in z)} of {len(z)} without')

print()
for label, prefixes in SETTINGS:
    d = [p1[0] - p2[0] for n, (p1, p2) in R.items() if n.split('-')[0] in prefixes]
    print(f'{label:34s} first 200 ms or more slower than the second: {sum(x >= 200 for x in d)} of {len(d)}, '
          f'most {max(d) / 1000:.2f} s')

# "Later prompts": the whole-prompt A/B on a0116b27 (round 0, the warm-up and the discarded prime-4096 left out).
rows = [r for r in csv.DictReader(open(root.parent.parent / 'summary/later-prompts-requests.csv'))
        if r['round'] != '0' and r['label'].startswith('tokens-')]
def kind(r): return r['mode'], r['arm'], r['prompt_tokens']
med = {}
for r in rows:
    if r['flag'] == 'False':
        med.setdefault(kind(r), []).append(float(r['prompt_ms']))
hit = [float(r['prompt_ms']) - statistics.median(med[kind(r)]) for r in rows if int(r['pgmigrate_success']) > LINE]
print(f'\nlater prompts: {len(hit)} of {len(rows)} over {LINE} pages; 100 ms or more slower than the median of the same kind '
      f'without a flag: ' + ', '.join(f'{d / 1000:.2f} s' for d in sorted(hit) if d >= 100))
