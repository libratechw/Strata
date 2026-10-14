#!/usr/bin/env python3
"""Per prompt of delay4k3.sh runs: KFD queue evictions (by trigger) and the time the engine's queues stood evicted inside the
prompt window, from kfd-events.py's log; plus pgmigrate_success.  Usage: kfd-window.py KFDLOG RUN_DIR ..."""
import re, sys
log, runs = sys.argv[1], sys.argv[2:]
ev = []   # (wall_s_of_event, kind, pid, trigger)
for l in open(log):
    if l.startswith('#'): continue
    f = l.split()
    wall, boot, kind = float(f[0]), int(f[1]), f[2]
    if kind in ('QUEUE_EVICTION', 'QUEUE_RESTORE'):
        ns, pid = int(f[3]), int(f[4].lstrip('-'))
        t = wall - (boot - ns) / 1e9
        ev.append((t, kind, pid, f[6] if kind == 'QUEUE_EVICTION' else ''))
ev.sort()
def window(t0, t1):
    n = {}; susp = 0.0; state = {}; longest = 0.0
    for t, kind, pid, trig in ev:
        if kind == 'QUEUE_EVICTION':
            if t0 <= t <= t1: n[trig] = n.get(trig, 0) + 1
            state.setdefault(pid, t)
        else:
            s = state.pop(pid, None)
            if s is not None:
                a, b = max(s, t0), min(t, t1)
                if b > a: susp += b - a; longest = max(longest, b - a)
    return n, susp, longest
for d in runs:
    cl = open(d + '/client.log').read().splitlines()
    ms = [float(x) for x in re.findall(r'"prompt_ms": ([\d.]+)', '\n'.join(cl))]
    S, cur = [], None
    for l in open(d + '/procvm.log'):
        f = l.split()
        if f and f[0] == 'T': cur = {'t': float(f[1])}; S.append(cur)
        elif cur is not None and len(f) == 2: cur[f[0]] = int(f[1])
    out = []
    for k, run in ((1, '1'), (2, '2')):
        t0 = float(next(l.split()[0] for l in cl if f'start tokens-4096-run-{run}' in l)); t1 = t0 + ms[k] / 1000
        a = max((s for s in S if s['t'] <= t0), key=lambda s: s['t']); b = min((s for s in S if s['t'] >= t1), key=lambda s: s['t'], default=S[-1])
        n, susp, lo = window(t0, t1)
        out.append(f"run{run} {ms[k]:6.0f} migr {b.get('pgmigrate_success',0)-a.get('pgmigrate_success',0):7d} evict {n} evicted {susp*1000:6.0f} ms (longest {lo*1000:5.0f})")
    print(f"{d.split('/')[-1]:9s} d={ms[1]-ms[2]:6.0f}  " + ' | '.join(out))
