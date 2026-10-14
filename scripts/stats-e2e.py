#!/usr/bin/env python3
"""Paired statistics of the whole-prompt A/B: per mode (F, D) and size, the per-round ratio off/on of the engine's prompt_ms
(round 0 discarded), over one or more run directories (the same binary).  Prints n, median and mean ratio, a 95% bootstrap
interval of the mean log ratio (10,000 resamples), the exact two-sided sign test and a paired t on the log ratios.
A row that longprompt-guard.py flagged (page migration or direct reclaim during the prompt) drops its pair; the count is printed.
Usage: stats-e2e.py DIR [DIR ...]"""
import glob, json, math, os, random, statistics, sys

dirs = sys.argv[1:]
random.seed(1)
def sign_p(k, n):   # two-sided exact binomial(0.5) for k successes out of n
    from math import comb
    tail = sum(comb(n, i) for i in range(0, min(k, n - k) + 1)) / 2 ** n
    return min(1.0, 2 * tail)
def _betacf(a, b, x):
    tiny = 1e-300; qab, qap, qam = a + b, a + 1, a - 1
    c, d = 1.0, 1 - qab * x / qap
    d = 1 / (d if abs(d) > tiny else tiny); h = d
    for m in range(1, 300):
        m2 = 2 * m; aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1 + aa * d; d = 1 / (d if abs(d) > tiny else tiny)
        c = 1 + aa / c; c = c if abs(c) > tiny else tiny; h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1 + aa * d; d = 1 / (d if abs(d) > tiny else tiny)
        c = 1 + aa / c; c = c if abs(c) > tiny else tiny
        de = d * c; h *= de
        if abs(de - 1) < 1e-14: break
    return h
def _ibeta(a, b, x):   # regularized incomplete beta
    if x <= 0: return 0.0
    if x >= 1: return 1.0
    bt = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1 - x))
    return bt * _betacf(a, b, x) / a if x < (a + 1) / (a + b + 2) else 1 - bt * _betacf(b, a, 1 - x) / b
def tdist_p(t, df):   # two-sided p of Student's t
    return _ibeta(df / 2, 0.5, df / (df + t * t))
for mode in ('F', 'D'):
    res, flagged = {}, {}
    for d in dirs:
        for run in sorted(glob.glob(f'{d}/{mode}/{mode}-borrow_*-r*')):
            if not os.path.isdir(run) or not os.path.exists(run + '/results.json'): continue
            base = os.path.basename(run); arm = base.split('_')[1].split('-')[0]; rnd = int(base.rsplit('-r', 1)[1])
            if rnd == 0: continue
            for r in json.load(open(run + '/results.json')):
                if not r['label'].startswith('tokens-'): continue   # warmup, prime-N
                if os.environ.get('RUN') and not r['label'].endswith('-run-' + os.environ['RUN']): continue   # RUN=2: e4k/
                size = int(r['label'].split('-')[1])
                if r.get('reclaim', {}).get('flag'):
                    flagged.setdefault(size, set()).add((d, rnd)); continue
                res.setdefault(size, {}).setdefault((d, rnd), {})[arm] = r['engine']['prompt_ms']
    for size in sorted(res):
        ratios = [v['off'] / v['on'] for key, v in res[size].items() if 'off' in v and 'on' in v and key not in flagged.get(size, ())]
        n = len(ratios)
        if n < 2: continue
        lr = [math.log(x) for x in ratios]
        boots = sorted(statistics.fmean(random.choices(lr, k=n)) for _ in range(10000))
        lo, hi = math.exp(boots[250]), math.exp(boots[9749])
        sd = statistics.stdev(lr); t = statistics.fmean(lr) / (sd / math.sqrt(n))
        k = sum(x > 1 for x in ratios)
        print(f'{mode} {size:>6}: n={n:2d} median {statistics.median(ratios):.4f} geomean {math.exp(statistics.fmean(lr)):.4f} '
              f'95% CI [{lo:.4f}, {hi:.4f}] faster {k}/{n} sign p={sign_p(k, n):.4f} t-test p={tdist_p(t, n - 1):.4f} '
              f'min {min(ratios):.3f} max {max(ratios):.3f} pairs dropped (reclaim) {len(flagged.get(size, ()))}')
