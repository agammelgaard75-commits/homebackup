"""One-host deployment of the reviewed 2026-09-13 startup repair."""
import fcntl
from pathlib import Path
import sys

ROOT = Path('/home/bot/sysadmin')
sys.path.insert(0, str(ROOT / 'src'))
from ai_sysadmin import Controller, atomic_write

c = Controller(Path('/etc/ai-sysadmin/config.toml'))
backup = c.state / 'recovery-backup-20260913'
with (c.state / 'controller.lock').open('a') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    backup.mkdir(mode=0o750, exist_ok=True)
    report = (ROOT / 'reports/2026-09-13-recovery.md').read_text()
    if not (backup / 'change-plan.md').exists():
        atomic_write(backup / 'change-plan.md', report)
    c.event('decision', 'Deploy reviewed startup recovery',
            change_id='RECOVERY-20260913', plan=report)

    def action(name, argv, mutate=False):
        result = c.command(name, argv, timeout=120, mutate=mutate)
        if result['returncode']:
            c.event('closure', 'Recovery deployment failed; review command results',
                    status='FAILED', action=name, change_id='RECOVERY-20260913')
            raise SystemExit(result['returncode'])
        return result

    action('verify_vlan_readiness', ['/usr/lib/systemd/systemd-networkd-wait-online',
           '--interface=ens18.2:routable', '--ipv4', '--timeout=10'])
    action('inspect_effective_readiness_unit', ['systemctl', 'cat', 'systemd-networkd-wait-online.service'])
    for source in ['/opt/ai-sysadmin/bin/ai-sysadmin', '/opt/ai-sysadmin/README.md',
                   '/var/lib/ai-sysadmin/changes/CHG-20260913.txt']:
        dest = backup / Path(source).name
        if not dest.exists():
            action('backup_installed_artifact', ['cp', '-p', source, str(dest)], True)
    override = Path('/etc/systemd/system/systemd-networkd-wait-online.service.d/90-ai-sysadmin-readiness.conf')
    staged = ROOT / 'reports/90-ai-sysadmin-readiness.conf'
    if override.exists() and override.read_bytes() != staged.read_bytes():
        raise SystemExit('Unexpected existing override; refusing overwrite')
    action('install_controller', ['install', '-m', '0755', str(ROOT / 'src/ai_sysadmin.py'),
                                '/opt/ai-sysadmin/bin/ai-sysadmin'], True)
    action('install_readme', ['install', '-m', '0644', str(ROOT / 'README.md'),
                            '/opt/ai-sysadmin/README.md'], True)
    action('install_readiness_directory', ['install', '-d', '-m', '0755', str(override.parent)], True)
    action('install_readiness_override', ['install', '-m', '0644', str(staged), str(override)], True)
    action('reload_unit_definitions', ['systemctl', 'daemon-reload'], True)
    action('start_readiness_check', ['systemctl', 'start', 'systemd-networkd-wait-online.service'], True)
    action('verify_readiness_service', ['systemctl', 'is-active', 'systemd-networkd-wait-online.service'])
    action('verify_failed_units', ['systemctl', '--failed', '--no-legend', '--plain'])
    action('verify_package_database', ['dpkg', '--audit'])
    c.event('closure', 'Controller recovery deployed and network readiness check passed; fresh preparation pending',
            status='CLOSED', change_id='RECOVERY-20260913')
