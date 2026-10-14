#!/usr/bin/env python3
"""KFD SMI events (queue eviction / restore, page migration, unmap, process start / end) straight from /dev/kfd, one line per
event with the wall time and CLOCK_BOOTTIME of the read: "<wall> <boottime_ns> <event> <kernel payload>".  The kernel payload of
QUEUE_EVICTION is "<boottime_ns> -<pid> <node> <trigger>" (trigger 0 SVM, 1 USERPTR, 2 TTM, 3 SUSPEND, ...).
Events of every process need root (KFD_SMI_EVENT_ALL_PROCESS); without root only this process's own and the broadcast ones.
Usage: [sudo] kfd-events.py OUT [--own]   (stop with Ctrl+C or SIGTERM)"""
import fcntl, os, select, signal, struct, sys, time

NAMES = {1: 'VMFAULT', 2: 'THERMAL_THROTTLE', 3: 'GPU_PRE_RESET', 4: 'GPU_POST_RESET', 5: 'MIGRATE_START', 6: 'MIGRATE_END',
         7: 'PAGE_FAULT_START', 8: 'PAGE_FAULT_END', 9: 'QUEUE_EVICTION', 10: 'QUEUE_RESTORE', 11: 'UNMAP_FROM_GPU',
         12: 'PROCESS_START', 13: 'PROCESS_END'}
ALL_PROCESS = 64
# _IOWR('K', 0x1F, struct { __u32 gpuid; __u32 anon_fd; })
IOC_SMI_EVENTS = (3 << 30) | (8 << 16) | (ord('K') << 8) | 0x1F


def gpu_ids():
    base = '/sys/class/kfd/kfd/topology/nodes'
    ids = []
    for n in sorted(os.listdir(base)):
        g = int(open(f'{base}/{n}/gpu_id').read())
        if g:
            ids.append(g)
    return ids


def main():
    out = open(sys.argv[1], 'a', buffering=1)
    own = '--own' in sys.argv
    kfd = os.open('/dev/kfd', os.O_RDWR)
    mask = 0
    for i in NAMES:
        mask |= 1 << (i - 1)
    if not own:
        mask |= 1 << (ALL_PROCESS - 1)
    fds = {}
    for g in gpu_ids():
        buf = bytearray(struct.pack('II', g, 0))
        fcntl.ioctl(kfd, IOC_SMI_EVENTS, buf)
        fd = struct.unpack('II', buf)[1]
        os.write(fd, struct.pack('Q', mask))
        fds[fd] = g
    out.write(f'# started {time.time():.6f} boottime_ns {time.clock_gettime_ns(time.CLOCK_BOOTTIME)} gpus {list(fds.values())} '
              f'all_process {not own}\n')
    stop = []
    signal.signal(signal.SIGTERM, lambda *a: stop.append(1))
    try:
        while not stop:
            ready, _, _ = select.select(list(fds), [], [], 1.0)
            for fd in ready:
                data = os.read(fd, 65536).decode(errors='replace')
                wall, boot = time.time(), time.clock_gettime_ns(time.CLOCK_BOOTTIME)
                for line in data.splitlines():
                    if not line.strip():
                        continue
                    ev, _, rest = line.partition(' ')
                    out.write(f'{wall:.6f} {boot} {NAMES.get(int(ev, 16), ev)} {rest}\n')
    except KeyboardInterrupt:
        pass
    out.write(f'# stopped {time.time():.6f}\n')


if __name__ == '__main__':
    main()
