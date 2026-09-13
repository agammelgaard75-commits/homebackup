#!/usr/bin/env python3
"""Render deployment assets into a staging directory without touching services."""
import argparse
from pathlib import Path
import tomllib


def render(config, output):
    repo = Path(__file__).resolve().parents[1]
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    schedule = config['schedule']
    maintenance = days.index(schedule['maintenance_day'])
    preparation = days.index(schedule['preparation_day'])
    hour = schedule['maintenance_hour_utc']
    if (maintenance - preparation) % 7 != 1 or type(hour) is not int or not 0 <= hour <= 23:
        raise ValueError('Preparation must be the day before maintenance; hour must be 0..23 UTC')
    output.mkdir(parents=True, exist_ok=True)
    for phase, day in [('prepare', preparation), ('maintenance', maintenance)]:
        source = repo / 'systemd' / f'ai-sysadmin-{phase}.timer'
        lines = source.read_text().splitlines()
        lines = [f'OnCalendar={days[day][:3]} *-*-* {hour:02d}:00:00 UTC'
                 if line.startswith('OnCalendar=') else line for line in lines]
        (output / source.name).write_text('\n'.join(lines) + '\n')
    directories = set()
    for service in config.get('containers', {}).get('services', []):
        for filename in service['compose_files']:
            directory = Path(filename).parent
            if not directory.is_absolute() or str(directory) in ('/', '/home', '/root') or any(c in str(directory) for c in ' \t\n%'):
                raise ValueError('Compose directories must be specific absolute paths without whitespace or percent signs')
            directories.add(str(directory))
    for phase in ('prepare', 'maintenance'):
        text = '[Service]\n'
        if config.get('containers', {}).get('enabled') and directories:
            text += 'ProtectHome=tmpfs\nBindReadOnlyPaths=' + ' '.join(sorted(directories)) + '\n'
        (output / f'ai-sysadmin-{phase}.containers.conf').write_text(text)
    app = output / 'ai_sysadmin' 
    default = app / 'default'
    views = default / 'data/ui/views'
    views.mkdir(parents=True, exist_ok=True)
    (default / 'app.conf').write_text('[install]\nis_configured = 1\n[ui]\nis_visible = 1\nlabel = AI Sysadmin\n[launcher]\nauthor = Local Operations\ndescription = Auditable weekly maintenance, host health and anomalies\nversion = 1.0.1\n[package]\nid = ai_sysadmin\n')
    nav = default / 'data/ui/nav'
    nav.mkdir(parents=True, exist_ok=True)
    (nav / 'default.xml').write_text('<nav search_view="search" color="#234E70"><view name="health_dashboard" default="true"/><view name="anomaly_dashboard"/><view name="search"/></nav>\n')
    metadata = app / 'metadata'
    metadata.mkdir(exist_ok=True)
    (metadata / 'default.meta').write_text('[]\naccess = read : [ * ], write : [ admin ]\nexport = none\n')
    inputs, props = [], []
    for filename, suffix in [('audit', 'audit'), ('health', 'health'), ('anomalies', 'anomaly')]:
        path = Path(config['paths']['log_dir']) / (filename + '.jsonl')
        inputs.append(f'[monitor://{path}]\nindex = ai_sysadmin\nsourcetype = ai_sysadmin:{suffix}\ndisabled = 0\ncrcSalt = <SOURCE>\n')
        props.append(f'[ai_sysadmin:{suffix}]\nSHOULD_LINEMERGE = false\nLINE_BREAKER = ([\\r\\n]+)\nTRUNCATE = 0\nKV_MODE = json\nTIME_PREFIX = "timestamp":\\s*"\nTIME_FORMAT = %Y-%m-%dT%H:%M:%S%:z\nMAX_TIMESTAMP_LOOKAHEAD = 32\n')
    (default / 'inputs.conf').write_text('\n'.join(inputs))
    (default / 'props.conf').write_text('\n'.join(props))
    (default / 'indexes.conf').write_text('[ai_sysadmin]\nhomePath = $SPLUNK_DB/ai_sysadmin/db\ncoldPath = $SPLUNK_DB/ai_sysadmin/colddb\nthawedPath = $SPLUNK_DB/ai_sysadmin/thaweddb\nmaxTotalDataSizeMB = 2048\nfrozenTimePeriodInSecs = 31536000\nmaxDataSize = 100\nmaxHotBuckets = 2\n')
    for source in (repo / 'splunk').glob('*-dashboard.xml'):
        (views / source.name.replace('-', '_')).write_text(source.read_text().replace('index=os', 'index=ai_sysadmin'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('config', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    with args.config.open('rb') as handle:
        render(tomllib.load(handle), args.output)
