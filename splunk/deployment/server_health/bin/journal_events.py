#!/usr/bin/python3
"""Bounded journal reader, with atomic cursor checkpoint after stdout flush.
A crash before checkpoint may replay a batch; log rotation recovery is reported.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

STATE = Path('/opt/splunk/var/lib/splunk/server_health')
FIELDS = ('MESSAGE', 'PRIORITY', '_SYSTEMD_UNIT', '_TRANSPORT', '_PID', '_UID', '_COMM', 'SYSLOG_IDENTIFIER')

def error(message):
    print(json.dumps({'time':time.time(), 'kind':'collector_error', 'component':'journald', 'MESSAGE':message, 'PRIORITY':'3'}), flush=True)

def main():
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    cursor_file = STATE / 'journal.cursor'
    cursor = cursor_file.read_text().strip() if cursor_file.exists() else None
    command = ['/usr/bin/journalctl', '--no-pager', '--quiet', '--output=json', '--priority=6', '--output-fields='+','.join(FIELDS)]
    command += ['--after-cursor='+cursor] if cursor else ['--since=-5min']
    last = None
    capped = False
    with tempfile.TemporaryFile(mode='w+') as stderr:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=stderr, text=True)
        try:
            for count, line in enumerate(process.stdout):
                event = json.loads(line)
                last = event.get('__CURSOR', last)
                record = {key:event[key] for key in FIELDS if key in event}
                record['time'] = int(event['__REALTIME_TIMESTAMP']) / 1000000
                record['kind'] = 'journal'
                if isinstance(record.get('MESSAGE'), str) and len(record['MESSAGE']) > 12000:
                    record['MESSAGE'] = record['MESSAGE'][:12000]
                    record['message_truncated'] = True
                print(json.dumps(record), flush=True)
                if count >= 1999:
                    capped = True
                    process.terminate()
                    break
            result = process.wait(timeout=5)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
        stderr.seek(0)
        diagnostic = stderr.read(2000)
    if result and not capped:
        error('journalctl failed: '+diagnostic)
        # Preserve the failed cursor for diagnosis; recover only a vacuumed cursor.
        if cursor and ('seek' in diagnostic.lower() or 'cursor' in diagnostic.lower()):
            cursor_file.replace(STATE / 'journal.cursor.expired')
            error('Journal cursor unavailable; next run recovers the last 5 minutes. Older entries may have been vacuumed.')
        return
    if last:
        temporary = STATE / 'journal.cursor.tmp'
        temporary.write_text(last+'\n')
        temporary.replace(cursor_file)

if __name__ == '__main__':
    main()
