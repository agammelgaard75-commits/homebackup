"""Audited, bounded deployment for EMPTY-POINTER-20260913."""
import fcntl
import hashlib
from pathlib import Path
import sys

ROOT = Path('/home/bot/sysadmin')
sys.path.insert(0, str(ROOT / 'src'))
from ai_sysadmin import Controller, atomic_write, record_status

c = Controller(Path('/etc/ai-sysadmin/config.toml'))
change_id = 'EMPTY-POINTER-20260913'
backup = c.state / 'empty-pointer-backup-20260913'
report = (ROOT / 'reports/2026-09-13-empty-pointer.md').read_text()

def snapshot():
    files = sorted(c.changes.glob('*.txt')) + sorted(c.state.glob('*.plan.json'))
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}

def action(name, argv):
    result = c.command(name, argv, timeout=60)
    print(name, result['returncode'], result['stdout'], result['stderr'], flush=True)
    if result['returncode']:
        raise RuntimeError(f'{name} failed: {result["returncode"]}')

try:
    with (c.state / 'controller.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert record_status((c.changes / 'CHG-20260913-R2.txt').read_text()) == 'CLOSED'
        assert all(record_status(p.read_text()) != 'RUNNING' for p in c.changes.glob('*.txt'))
        pointer = c.state / 'current-change'
        assert pointer.read_text().strip() in ('', 'CHG-20260913-R2')
        before = snapshot()
        c.event('inspection', 'Confirmed blank or recovered pointer and completed latest change',
                change_id=change_id, pointer=pointer.read_text(), artifact_hashes=before)
        c.event('decision', 'Deploy empty-pointer recovery fix', change_id=change_id, plan=report)
        backup.mkdir(mode=0o750, exist_ok=True)
        if not (backup / 'change-plan.md').exists():
            atomic_write(backup / 'change-plan.md', report)
        pairs = [(ROOT / 'src/ai_sysadmin.py', Path('/opt/ai-sysadmin/bin/ai-sysadmin'), 0o755),
                 (ROOT / 'README.md', Path('/opt/ai-sysadmin/README.md'), 0o644)]
        for target in [p[1] for p in pairs] + [pointer]:
            dest = backup / target.name
            if not dest.exists():
                c.event('command_start', 'Back up existing file', action='atomic_backup',
                        source=str(target), destination=str(dest), change_id=change_id)
                atomic_write(dest, target.read_text(), target.stat().st_mode & 0o777)
                c.event('command_result', 'Backup completed', action='atomic_backup',
                        change_id=change_id, sha256=hashlib.sha256(dest.read_bytes()).hexdigest())
        for source, target, mode in pairs:
            if target.read_bytes() != source.read_bytes():
                c.event('command_start', 'Atomically install reviewed file', action='atomic_install',
                        source=str(source), destination=str(target), change_id=change_id)
                atomic_write(target, source.read_text(), mode)
                c.event('command_result', 'Installation completed', action='atomic_install',
                        change_id=change_id, sha256=hashlib.sha256(target.read_bytes()).hexdigest())
            assert target.read_bytes() == source.read_bytes()
    action('verify_installed_prepare', ['/opt/ai-sysadmin/bin/ai-sysadmin', 'prepare'])
    first_pointer = pointer.read_bytes()
    action('verify_repeated_prepare', ['/opt/ai-sysadmin/bin/ai-sysadmin', 'prepare'])
    assert pointer.read_text().strip() == 'CHG-20260913-R2'
    assert pointer.read_bytes() == first_pointer
    assert snapshot() == before
    c.event('verification', 'Two installed prepare calls succeeded; change records and plans unchanged',
            change_id=change_id, pointer=pointer.read_text().strip(), artifact_hashes=snapshot())
    c.event('closure', 'Empty-pointer recovery deployed and verified; existing completed change restored. '
            'No maintenance executed; no outstanding issues for this corrective change.',
            change_id=change_id, status='CLOSED')
except Exception as exc:
    c.event('closure', 'Empty-pointer deployment failed; review audit and backups',
            change_id=change_id, status='FAILED', error=str(exc))
    raise
