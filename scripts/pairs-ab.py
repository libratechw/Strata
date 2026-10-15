#!/usr/bin/env python3
"""Per round: each arm's prompt tok/s and the flag, and the ratio of prompt_ms (first arm / second) for clean rounds after
round 0.  Usage: pairs-ab.py RUNS_DIR TOKENS ARM_A ARM_B"""
import json, pathlib, sys
runs, T, A, B = pathlib.Path(sys.argv[1]), int(sys.argv[2]), sys.argv[3], sys.argv[4]
rows = {}
for res in runs.glob('*-r*/results.json'):
    arm, rnd = res.parent.name.rsplit('-r', 1)
    for r in json.loads(res.read_text()):
        if r['label'].startswith(f'tokens-{T}-'):
            rows.setdefault(int(rnd), {})[arm] = (r['engine']['prompt_ms'], r['engine']['prompt_tokens'], r['reclaim']['flag'])
for k in sorted(rows):
    v = rows[k]
    cells = '  '.join(f"{a} {v[a][1] / v[a][0] * 1000:8.1f} tok/s{' FLAGGED' if v[a][2] else ''}" for a in (A, B) if a in v)
    ok = k > 0 and A in v and B in v and not v[A][2] and not v[B][2]
    print(f"round {k:2d}  {cells}" + (f"  ratio {v[A][0] / v[B][0]:.4f}" if ok else "  (not counted)"))
