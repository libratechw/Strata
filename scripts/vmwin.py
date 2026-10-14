#!/usr/bin/env python3
"""/proc/vmstat counter increments during the first 4K request of a delay4k3.sh run.  Usage: vmwin.py RUN_DIR ..."""
import re, sys
keys = ['compact_stall', 'compact_migrate_scanned', 'compact_isolated', 'pgmigrate_success', 'thp_migration_success',
        'pgscan_kswapd', 'pgscan_direct', 'pgsteal_kswapd', 'pgsteal_direct', 'allocstall_normal', 'allocstall_movable',
        'pswpin', 'pswpout', 'pgmajfault', 'workingset_refault_file', 'numa_hint_faults', 'pgfault']
for d in sys.argv[1:]:
    cl = open(d + '/client.log').read().splitlines()
    t0 = float(next(l.split()[0] for l in cl if 'start tokens-4096-run-1' in l))
    t1 = float(next(l.split()[0] for l in cl if 'done tokens-4096-run-1' in l))
    ms = re.findall(r'"prompt_ms": ([\d.]+)', open(d + '/client.log').read())
    samples, cur = [], None
    for l in open(d + '/procvm.log'):
        f = l.split()
        if f[0] == 'T':
            cur = {'t': float(f[1])}; samples.append(cur)
        elif cur is not None and len(f) == 2:
            cur[f[0]] = int(f[1])
    a = max((s for s in samples if s['t'] <= t0), key=lambda s: s['t'])
    b = min((s for s in samples if s['t'] >= t0 + float(ms[1]) / 1000), key=lambda s: s['t'])
    print(f"{d.split('/')[-1]:8s} {ms[1]:>7s} ms  " + ' '.join(f"{k}={b.get(k, 0) - a.get(k, 0)}" for k in keys if b.get(k, 0) - a.get(k, 0)))
