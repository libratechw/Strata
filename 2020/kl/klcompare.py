#!/usr/bin/env python3
"""KL(reference || arm) of the first token after each prompt (nats, full vocabulary) and top-1 agreement.
Usage: klcompare.py OUT_DIR REF_ARM ARM [ARM ...]"""
import json
import pathlib
import sys

import numpy as np

root = pathlib.Path(sys.argv[1])


def load(arm):
    rows = json.loads((root / arm / 'rows.json').read_text())
    return [np.fromfile(root / arm / f'logits.{r["index"]}', dtype=np.float32).astype(np.float64) for r in rows], rows


def logp(x):
    m = x.max()
    return x - m - np.log(np.exp(x - m).sum())


ref, rows = load(sys.argv[2])
for arm in sys.argv[3:]:
    cur, _ = load(arm)
    kls, agree = [], 0
    for r, c in zip(ref, cur):
        lr, lc = logp(r), logp(c)
        kls.append(float((np.exp(lr) * (lr - lc)).sum()))
        agree += int(r.argmax() == c.argmax())
    print(f'{arm:28} vs {sys.argv[2]}: KL mean {np.mean(kls):.5f} median {np.median(kls):.5f} max {np.max(kls):.5f}, '
          f'top-1 {agree} of {len(kls)}  ' + ' '.join(f'{k:.4f}' for k in kls))
