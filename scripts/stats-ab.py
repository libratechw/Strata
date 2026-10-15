#!/usr/bin/env python3
"""Whole-prompt A/B at TOKENS: per arm, the prompt tok/s of the measured rounds in which every arm's prompt was unflagged; and per pair of
arms the ratio of prompt_ms with a 95% bootstrap interval.  Usage: stats-ab.py RUNS_DIR TOKENS"""
import itertools, json, pathlib, random, statistics, sys

runs = pathlib.Path(sys.argv[1]); T = int(sys.argv[2])
rows = {}   # round -> arm -> (prompt_ms, tokens, flag)
for res in runs.glob('*-r*/results.json'):
    arm, rnd = res.parent.name.rsplit('-r', 1)
    for r in json.loads(res.read_text()):
        if r['label'].startswith(f"tokens-{T}-"):
            rows.setdefault(int(rnd), {})[arm] = (r['engine']['prompt_ms'], r['engine']['prompt_tokens'], r['reclaim']['flag'])
arms = sorted({a for v in rows.values() for a in v})
clean = {k: v for k, v in rows.items() if k >= 1 and len(v) == len(arms) and not any(x[2] for x in v.values())}
flagged = sorted((k, a) for k, v in rows.items() if k >= 1 for a, x in v.items() if x[2])
print(f'rounds measured {sum(k >= 1 for k in rows)}, clean {len(clean)}; flagged (round, arm): {flagged}')
for a in arms:
    t = [v[a][1] / v[a][0] * 1000 for v in clean.values()]
    print(f'{a:16s} tok/s median {statistics.median(t):7.1f}  min {min(t):7.1f}  max {max(t):7.1f}  (n={len(t)})')
random.seed(1)
for a, b in itertools.combinations(arms, 2):
    r = [v[a][0] / v[b][0] for v in clean.values()]
    boot = sorted(statistics.median(random.choices(r, k=len(r))) for _ in range(10000))
    print(f'prompt_ms {a} / {b}: median {statistics.median(r):.3f}  95% [{boot[250]:.3f}, {boot[9749]:.3f}]')
