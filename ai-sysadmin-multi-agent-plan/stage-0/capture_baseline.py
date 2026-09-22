#!/usr/bin/env python3
"""Stage 0 evidence capture. Writes only a new report and root-private backup.

Never executes the live controller, changes timers, or prints credential values.
Invoke once as root with explicit --report and --backup directories.
"""
import argparse
import collections
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tarfile
import tomllib

SOURCE = Path('/home/bot/sysadmin')
SECRET = re.compile(r'password|secret|token|authorization|api.?key|credential', re.I)


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def run(argv, timeout=30):
    try:
        p = subprocess.run(argv, text=True, capture_output=True, timeout=timeout,
                           env={**os.environ, 'LC_ALL': 'C', 'PYTHONDONTWRITEBYTECODE': '1'})
        return {'argv': argv, 'returncode': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr}
    except subprocess.TimeoutExpired:
        return {'argv': argv, 'returncode': 124, 'error': 'timeout'}


def redact(value):
    if isinstance(value, dict):
        return {k: ('[REDACTED]' if SECRET.search(k) and not k.endswith(('_file', '_path'))
                    else redact(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str):
        return re.sub(r'(https?://)[^/@\s]+:[^/@\s]+@', r'\1[REDACTED]@', value)
    return value


def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def write_json(path, value, private=False):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
    path.chmod(0o600 if private else 0o644)


def metadata(path):
    st = path.lstat()
    row = {'path': str(path), 'uid': st.st_uid, 'gid': st.st_gid,
           'mode': oct(stat.S_IMODE(st.st_mode)), 'size': st.st_size,
           'mtime_ns': st.st_mtime_ns}
    if path.is_symlink():
        row.update(type='symlink', target=os.readlink(path))
    elif path.is_file():
        row.update(type='file', sha256=digest(path))
    else:
        row['type'] = 'directory'
    return row


def list_tree(roots):
    paths = set()
    for root in roots:
        if root.exists() or root.is_symlink():
            paths.add(root)
            if root.is_dir() and not root.is_symlink():
                paths.update(root.rglob('*'))
    return sorted(paths)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--backup', type=Path, required=True)
    args = parser.parse_args()
    assert os.geteuid() == 0
    assert args.report.resolve().parent == Path('/home/bot/ai-sysadmin-multi-agent-plan/stage-0')
    assert args.backup.resolve().parent == Path('/var/backups/ai-sysadmin-migration')
    assert not args.report.exists() and not args.backup.exists(), 'Use fresh capture directories'
    args.report.mkdir(mode=0o755)
    args.backup.mkdir(parents=True, mode=0o700)
    args.backup.parent.chmod(0o700)
    os.umask(0o077)
    started = now()
    configuration = tomllib.loads(Path('/etc/ai-sysadmin/config.toml').read_text())
    write_json(args.report/'effective-config.redacted.json', redact(configuration))
    shutil.copyfile('/etc/ai-sysadmin/IGNORE.md', args.report/'IGNORE.md')
    (args.report/'IGNORE.md').chmod(0o644)
    units = ['ai-sysadmin-prepare.service', 'ai-sysadmin-maintenance.service',
             'ai-sysadmin-prepare.timer', 'ai-sysadmin-maintenance.timer']
    props = ['Id', 'FragmentPath', 'DropInPaths', 'UnitFileState', 'ActiveState', 'SubState',
             'Result', 'MainPID', 'ExecMainStatus', 'LastTriggerUSec',
             'NextElapseUSecRealtime', 'TimersCalendar', 'Persistent', 'ExecStart']
    unit_state = run(['systemctl', 'show', *units, *[f'--property={p}' for p in props]])
    write_json(args.report/'units.json', unit_state)
    source_files = [p for p in list_tree([SOURCE]) if not any(
        part in ('.git', '.secrets', '__pycache__') for part in p.relative_to(SOURCE).parts)]
    source_manifest = [metadata(p) for p in source_files]
    with tarfile.open(args.backup/'source.tar.gz', 'w:gz', dereference=False) as archive:
        for p in source_files:
            archive.add(p, arcname='sysadmin' if p == SOURCE else 'sysadmin/'+str(p.relative_to(SOURCE)), recursive=False)
    patch = run(['git', '-C', str(SOURCE), 'diff', '--binary', 'HEAD', '--', '.'])
    (args.backup/'working-tree.patch').write_text(patch['stdout'])
    source_info = {'root': str(SOURCE), 'revision': run(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD']),
                   'status': run(['git', '-C', str(SOURCE), 'status', '--short', '--', '.']),
                   'files': source_manifest,
                   'source_tar_sha256': digest(args.backup/'source.tar.gz'),
                   'working_tree_patch_sha256': digest(args.backup/'working-tree.patch')}
    write_json(args.report/'source-manifest.json', source_info)
    roots = [Path('/etc/ai-sysadmin'), Path('/var/lib/ai-sysadmin'), Path('/var/log/ai-sysadmin'),
             Path('/opt/ai-sysadmin'), Path('/opt/splunk/etc/apps/ai_sysadmin'),
             Path('/etc/logrotate.d/ai-sysadmin')]
    for unit in units:
        roots.extend([Path('/etc/systemd/system')/unit, Path('/etc/systemd/system')/(unit+'.d')])
    lock_path = Path(configuration['paths']['state_dir'])/'controller.lock'
    with lock_path.open('rb') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for unit in units[:2]:
            active = run(['systemctl', 'show', unit, '--property=MainPID', '--value'])
            assert active['stdout'].strip() == '0', f'{unit} has an active main process'
        paths = list_tree(roots)
        before = [metadata(p) for p in paths]
        with tarfile.open(args.backup/'deployment-state.tar.gz', 'w:gz', dereference=False) as archive:
            for p in paths:
                archive.add(p, arcname=str(p).lstrip('/'), recursive=False)
        after = [metadata(p) for p in list_tree(roots)]
        assert before == after, 'Source changed during backup; do not accept this capture'
        write_json(args.backup/'deployment-manifest.private.json', before, True)
        records = []
        for p in sorted((Path(configuration['paths']['state_dir'])/'changes').glob('*.txt')):
            content = p.read_text()
            status = re.search(r'^Status: (\w+)$', content.partition('\n\n')[0], re.M)
            plan = p.parent.parent/(p.stem+'.plan.json')
            records.append({'change_id': p.stem, 'status': status[1] if status else 'INVALID',
                            'record_sha256': digest(p), 'plan_exists': plan.exists(),
                            'closure_count': content.count('Closed at:')})
        write_json(args.report/'lifecycle-summary.json', {
            'current_change': (Path(configuration['paths']['state_dir'])/'current-change').read_text().strip(),
            'records': records, 'status_counts': dict(collections.Counter(r['status'] for r in records))})
    with tarfile.open(args.backup/'deployment-state.tar.gz', 'r:gz') as archive:
        readback = []
        for m in archive.getmembers():
            if m.isfile():
                with archive.extractfile(m) as f:
                    readback.append((m.name, hashlib.file_digest(f, 'sha256').hexdigest()))
    original = [(r['path'].lstrip('/'), r['sha256']) for r in before if r['type'] == 'file']
    assert sorted(readback) == sorted(original), 'Archive read-back mismatch'
    public_files = []
    for row in before:
        row = dict(row)
        if SECRET.search(Path(row['path']).name) or row['path'].endswith('.key'):
            row['sha256'] = '[PRIVATE: retained only inside protected backup]'
        public_files.append(row)
    write_json(args.report/'deployment-manifest.json', public_files)
    pairs = [('src/ai_sysadmin.py', '/opt/ai-sysadmin/bin/ai-sysadmin'),
             ('src/container_maintenance.py', '/opt/ai-sysadmin/bin/container_maintenance.py'),
             ('scripts/litellm_planner.py', '/opt/ai-sysadmin/bin/litellm-planner.py')]
    matches = [{'source': str(SOURCE/a), 'deployed': b, 'match': digest(SOURCE/a) == digest(Path(b))}
               for a,b in pairs]
    commands = [(['python3','--version'],30), (['apt-get','--version'],30), (['dpkg','--version'],30),
                (['systemctl','--version'],30), (['docker','version','--format','{{json .}}'],30),
                (['docker','compose','version'],30), (['docker','buildx','version'],30),
                (['dpkg','--audit'],60), (['dpkg-query','-W','-f=${binary:Package}\t${Version}\t${db:Status-Status}\n'],60),
                (['docker','ps','--format','{{.Names}}\t{{.Image}}\t{{.Status}}'],30),
                (['systemctl','list-units','--state=failed,auto-restart','--no-legend','--plain','--all'],30),
                (['snap','changes'],30), (['snap','list'],30)]
    write_json(args.report/'host-commands.json', [run(a,t) for a,t in commands])
    write_json(args.report/'capture.json', {
        'started_at': started, 'completed_at': now(), 'backup_path': str(args.backup),
        'backup_archive_sha256': digest(args.backup/'deployment-state.tar.gz'),
        'backup_regular_files': len(readback), 'backup_consistent_under_lifecycle_lock': True,
        'archive_readback_verified': True, 'vm_restore_verified': False,
        'deployed_source_matches': matches, 'os_release': Path('/etc/os-release').read_text(),
        'known_tooling_deviation': 'LXC availability check invoked Ubuntu launcher and installed LXD snap 5.21.7-1018661 revision 40585; no LXD pool/network configured.'})
    for p in args.backup.iterdir():
        if p.is_file(): p.chmod(0o600)
    for p in args.report.iterdir():
        os.chown(p, 1000, 1000)
    os.chown(args.report, 1000, 1000)
    print(json.dumps({'report':str(args.report), 'backup':str(args.backup),
                      'verified_backup_files':len(readback),'code_matches':matches}))


if __name__ == '__main__':
    main()
