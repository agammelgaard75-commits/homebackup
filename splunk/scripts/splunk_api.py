"""Loopback-only Splunk API helper; credentials stay in a mode-0600 file."""
import base64
import json
import pathlib
import ssl
import urllib.parse
import urllib.request

BASE='https://127.0.0.1:8089'
# Trust the installation's CA; default Splunk certificates use a non-DNS name.
CONTEXT=ssl.create_default_context(cafile='/home/bot/splunk/evidence/splunk-ca.pem')
CONTEXT.check_hostname=False

def request(path, data=None):
    credential=json.loads(pathlib.Path('/home/bot/splunk/.secrets/splunk-admin.json').read_text())
    token=base64.b64encode((credential['username']+':'+credential['password']).encode()).decode()
    separator='&' if '?' in path else '?'
    req=urllib.request.Request(BASE+path+separator+'output_mode=json',data=urllib.parse.urlencode(data).encode() if data is not None else None,headers={'Authorization':'Basic '+token})
    with urllib.request.urlopen(req,context=CONTEXT,timeout=90) as response:
        text=response.read().decode()
    return text

def get(path):
    return json.loads(request(path))

def search(query, earliest='-15m'):
    text=request('/services/search/jobs/export',{'search':query,'earliest_time':earliest,'latest_time':'now','preview':'false'})
    events=[json.loads(line) for line in text.splitlines() if line]
    failures=[e for e in events if 'messages' in e and any(m.get('type') in ('ERROR','FATAL') for m in e['messages'])]
    if failures: raise RuntimeError(failures)
    return [e['result'] for e in events if 'result' in e]
