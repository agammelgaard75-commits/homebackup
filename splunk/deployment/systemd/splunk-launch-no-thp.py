#!/usr/bin/python3
"""Disable THP for Splunk and its descendants, leaving other services untouched."""
import ctypes
import os
import subprocess
from pathlib import Path
libc = ctypes.CDLL(None, use_errno=True)
if libc.prctl(41, 1, 0, 0, 0) != 0:  # PR_SET_THP_DISABLE
    raise OSError(ctypes.get_errno(), 'Cannot disable THP for Splunk')
# Populate the local URI cache used by the 9.3 maintenance scripts.
uri = subprocess.check_output(['/opt/splunk/bin/splunk', 'cmd', 'splunkd', 'local-rest-uri', '-p', '8089'], text=True, timeout=15).strip()
if uri != 'https://127.0.0.1:8089':
    raise RuntimeError('Unexpected management listener: '+uri)
cache = Path('/opt/splunk/var/run/splunk/splunkd_uri.txt')
cache.parent.mkdir(parents=True, exist_ok=True)
cache.write_text(uri+'\n')
os.execv('/opt/splunk/bin/splunk', ['/opt/splunk/bin/splunk', '_internal_launch_under_systemd'])
