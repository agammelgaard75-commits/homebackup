#!/usr/bin/python3
"""Read-only Linux telemetry; no external dependencies or process command lines."""
import json
import os
import pathlib
import socket
import subprocess
import time

PROC = pathlib.Path('/proc')

def read(path):
    return pathlib.Path(path).read_text()

def snapshot():
    cpu = [int(x) for x in read(PROC / 'stat').splitlines()[0].split()[1:9]]
    network = {}
    for line in read(PROC / 'net/dev').splitlines()[2:]:
        name, fields = line.split(':', 1)
        values = [int(x) for x in fields.split()]
        if name.strip() != 'lo':
            network[name.strip()] = (values[0], values[8], values[2], values[10], values[3], values[11])
    disk = {}
    for line in read(PROC / 'diskstats').splitlines():
        fields = line.split()
        name = fields[2]
        if pathlib.Path('/sys/block', name).exists() and not name.startswith(('loop', 'ram', 'dm-')):
            disk[name] = (int(fields[5]), int(fields[9]), int(fields[12]))
    return time.monotonic(), cpu, network, disk

def emit(kind, **values):
    print(json.dumps(dict(time=round(time.time(), 3), host=socket.gethostname(), kind=kind, **values)), flush=True)

def main():
    first = snapshot()
    time.sleep(1)
    second = snapshot()
    elapsed = second[0] - first[0]
    delta = [b - a for a, b in zip(first[1], second[1])]
    total = max(sum(delta), 1)
    memory = {line.split(':')[0]: int(line.split()[1]) * 1024 for line in read(PROC / 'meminfo').splitlines()}
    load = os.getloadavg()
    emit('system', cpu_pct=round(100 * (total - delta[3] - delta[4]) / total, 2),
         iowait_pct=round(100 * delta[4] / total, 2), cpu_count=os.cpu_count(),
         load1=load[0], load5=load[1], load15=load[2],
         memory_total_bytes=memory['MemTotal'], memory_available_bytes=memory['MemAvailable'],
         memory_used_pct=round(100 * (1 - memory['MemAvailable'] / memory['MemTotal']), 2),
         swap_used_bytes=memory['SwapTotal'] - memory['SwapFree'],
         uptime_seconds=float(read(PROC / 'uptime').split()[0]))
    seen = set()
    for line in read(PROC / 'self/mounts').splitlines():
        device, mount, fs = line.split()[:3]
        mount = mount.replace('\\040', ' ').replace('\\011', '\t').replace('\\134', '\\')
        if fs not in {'ext4', 'ext3', 'xfs', 'btrfs', 'zfs', 'vfat'} or mount in seen:
            continue
        seen.add(mount)
        try:
            stat = os.statvfs(mount)
            used = stat.f_blocks - stat.f_bfree
            denominator = used + stat.f_bavail
            emit('filesystem', mount=mount, device=device, filesystem=fs,
                 used_pct=round(100 * used / max(denominator, 1), 2),
                 available_bytes=stat.f_bavail * stat.f_frsize,
                 total_bytes=stat.f_blocks * stat.f_frsize,
                 inode_used_pct=round(100 * (stat.f_files-stat.f_ffree)/max(stat.f_files, 1), 2))
        except OSError as error:
            emit('collector_error', component='filesystem', error=str(error))
    for name, values in second[2].items():
        previous = first[2].get(name)
        if previous:
            emit('network', interface=name,
                 rx_bytes_sec=round(max(0, values[0]-previous[0])/elapsed, 2),
                 tx_bytes_sec=round(max(0, values[1]-previous[1])/elapsed, 2),
                 rx_errors=values[2], tx_errors=values[3], rx_drops=values[4], tx_drops=values[5])
    for name, values in second[3].items():
        previous = first[3].get(name)
        if previous:
            emit('disk_io', device=name,
                 read_bytes_sec=round(max(0, values[0]-previous[0])*512/elapsed, 2),
                 write_bytes_sec=round(max(0, values[1]-previous[1])*512/elapsed, 2),
                 busy_pct=round(min(100, max(0, values[2]-previous[2])/(elapsed*10)), 2))
    try:
        result = subprocess.run(['/usr/bin/systemctl', 'list-units', '--type=service', '--all', '--no-pager', '--plain', '--no-legend'], capture_output=True, text=True, timeout=8, check=True)
        failed = []
        for line in result.stdout.splitlines():
            fields = line.split()
            if len(fields) >= 4:
                if fields[2] == 'failed':
                    failed.append(fields[0])
                emit('service', unit=fields[0], load_state=fields[1], active_state=fields[2], sub_state=fields[3])
        emit('service_summary', failed_count=len(failed), failed_units=', '.join(failed))
    except (subprocess.SubprocessError, OSError) as error:
        emit('collector_error', component='systemd', error=str(error))
    # Only process names and resident memory, never arguments or environment.
    result = subprocess.run(['/usr/bin/ps', '-eo', 'pid=,comm=,rss=', '--sort=-rss'], capture_output=True, text=True, timeout=8, check=True)
    for line in result.stdout.splitlines()[:10]:
        pid, name, rss = line.split(None, 2)
        emit('process', pid=int(pid), process=name, rss_bytes=int(rss)*1024)

if __name__ == '__main__':
    main()
