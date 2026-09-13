#!/usr/bin/env python3
"""Local standalone adapter. Called via existing sudo, never by generated shell text."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile


def call(*args):
    return subprocess.run(args, check=True, text=True, capture_output=True, timeout=3000)


def digest(path):
    h = hashlib.sha512()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def checked_archive(path, root):
    """Reject traversal, special files and escaping links before extraction."""
    with tarfile.open(path) as archive:
        members = archive.getmembers()
        if not members:
            raise ValueError('Empty package')
        for member in members:
            name = Path(member.name)
            if name.is_absolute() or '..' in name.parts or not name.parts or name.parts[0] != root:
                raise ValueError('Package path escapes expected app/installation')
            if not (member.isfile() or member.isdir() or member.issym() or member.islnk()):
                raise ValueError('Package contains a special file')
            # data_filter also validates symlink/hardlink destinations.
            tarfile.data_filter(member, '/tmp/splunk-package-check')
    return members


def main():
    action, config_path, run_id, *rest = sys.argv[1:]
    if os.geteuid() != 0:
        raise RuntimeError('Local adapter requires sudo')
    if not re.fullmatch(r'[0-9a-f]{32}', run_id):
        raise ValueError('Invalid transaction ID')
    cfg = json.loads(Path(config_path).read_text())
    home = Path(cfg['splunk_home'])
    # Deliberately narrow v1 adapter; portability requires a separate adapter.
    if home != Path('/opt/splunk') or cfg['service'] != 'Splunkd' or cfg['service_user'] != 'splunk':
        raise ValueError('This adapter supports only the inspected standalone installation')
    base = Path(cfg['backup_dir'])
    if base != Path('/var/backups/splunk-upgrade'):
        raise ValueError('Unexpected backup location')
    base.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(base, 0o700)
    target = base / run_id
    archive = target / 'splunk.tar'
    if action == 'backup':
        target.mkdir(mode=0o700)
        used = int(call('du', '-sb', str(home)).stdout.split()[0])
        # Space for backup, staged package and a retained failed installation.
        if shutil.disk_usage(base).free < used * 2 + cfg['minimum_free_bytes']:
            raise RuntimeError('Insufficient space for backup and recovery')
        call('systemctl', 'stop', cfg['service'])
        try:
            call('tar', '--acls', '--xattrs', '-cpf', str(archive), '-C', str(home.parent), home.name)
            call('tar', '--acls', '--xattrs', '-df', str(archive), '-C', str(home.parent))
            (target / 'sha512').write_text(digest(archive) + '\n')
            unit = Path('/etc/systemd/system/Splunkd.service')
            shutil.copy2(unit, target / unit.name)
            dropins = Path(str(unit) + '.d')
            if dropins.exists():
                shutil.copytree(dropins, target / dropins.name)
            (target / 'complete').write_text('cold backup verified\n')
        finally:
            call('systemctl', 'start', cfg['service'])
        print(json.dumps({'backup': str(target), 'verified': True}))
    elif action == 'core':
        package, expected_hash = rest
        if not (target / 'complete').exists():
            raise RuntimeError('No verified cold backup')
        staged = target / 'installer.tgz'
        shutil.copyfile(package, staged)
        if digest(staged) != expected_hash:
            raise RuntimeError('Installer checksum mismatch')
        checked_archive(staged, home.name)
        call('systemctl', 'stop', cfg['service'])
        # Extraction uses Python's data filter, including checks against existing links.
        with tarfile.open(staged) as package_file:
            package_file.extractall(home.parent, filter='data')
        # Preserve the existing systemd/THP wrapper while allowing unattended migration prompts.
        wrapper = home / 'etc/system/local/splunk-launch-no-thp.py'
        source = wrapper.read_text()
        original = "['/opt/splunk/bin/splunk', '_internal_launch_under_systemd']"
        replacement = "['/opt/splunk/bin/splunk', '_internal_launch_under_systemd', '--accept-license', '--answer-yes', '--no-prompt']"
        if original in source:
            wrapper.write_text(source.replace(original, replacement))
        elif replacement not in source:
            raise RuntimeError('Startup wrapper changed; cannot qualify unattended startup')
        call('chown', '-R', 'splunk:splunk', str(home))
        call('systemctl', 'start', cfg['service'])
    elif action == 'restore':
        if not (target / 'complete').exists() or digest(archive) != (target / 'sha512').read_text().strip():
            raise RuntimeError('Backup missing or corrupt; refusing restore')
        failed = home.parent / ('splunk-failed-' + run_id)
        if failed.exists():
            raise RuntimeError('Restore already attempted; inspect retained directories')
        call('systemctl', 'stop', cfg['service'])
        home.rename(failed)
        # Archive was locally created and its checksum verified, not vendor content.
        call('tar', '--acls', '--xattrs', '-xpf', str(archive), '-C', str(home.parent))
        call('systemctl', 'start', cfg['service'])
        print(json.dumps({'restored': str(target), 'failed_installation': str(failed)}))
    else:
        raise ValueError('Unknown local adapter action')


if __name__ == '__main__':
    main()
