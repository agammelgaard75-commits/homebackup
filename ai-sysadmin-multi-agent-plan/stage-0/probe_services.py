#!/usr/bin/env python3
"""Read-only Splunk/gateway evidence; three small synthetic AI requests only."""
import datetime as dt
import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import sys
import time
import tomllib
import urllib.request
import xml.etree.ElementTree as ET

REPORT = Path('/home/bot/ai-sysadmin-multi-agent-plan/stage-0/2026-09-15T1455Z')


def save(name, obj):
    path = REPORT/name
    path.write_text(json.dumps(obj, indent=2, sort_keys=True)+'\n')
    path.chmod(0o644)
    os.chown(path, 1000, 1000)


def splunk_probe():
    sys.path.insert(0, '/home/bot/splunk/scripts')
    from splunk_api import get, search
    report = {'at': dt.datetime.now(dt.timezone.utc).isoformat(), 'writes_to_index': False}
    try:
        info = get('/services/server/info')['entry'][0]['content']
        report['server'] = {k:info.get(k) for k in ('version','build','licenseState','kvStoreStatus')}
        report['health'] = get('/services/server/health/splunkd')['entry'][0]['content']['health']
        monitors = get('/services/data/inputs/monitor?count=0')['entry']
        report['monitors'] = [{'name': e['name'], **{k:e['content'].get(k) for k in ('index','sourcetype','disabled')}}
                              for e in monitors if str(e['name']).startswith('/var/log/ai-sysadmin/')]
        report['counts'] = search('search index=ai_sysadmin earliest=0 | stats count latest(_time) as newest_event by sourcetype', '0')
        report['closure_counts'] = search('search index=ai_sysadmin sourcetype=ai_sysadmin:audit event_type=closure earliest=0 | stats count by change_id status', '0')
        report['latest_health'] = search('search index=ai_sysadmin sourcetype=ai_sysadmin:health earliest=-30d | head 1 | table timestamp root_free_percent upgradable_package_count reboot_required failed_units{}', '-30d')
        report['dashboards'] = []
        for name in ('health_dashboard','anomaly_dashboard','ignored_dashboard'):
            xml = get('/servicesNS/nobody/ai_sysadmin/data/ui/views/'+name)['entry'][0]['content']['eai:data']
            tree = ET.fromstring(xml)
            report['dashboards'].append({'name':name, 'sha256':hashlib.sha256(xml.encode()).hexdigest(),
                                         'title':tree.findtext('label'),
                                         'queries':[n.text for n in tree.findall('.//query')]})
        searches = get('/servicesNS/nobody/ai_sysadmin/saved/searches?count=0')['entry']
        report['saved_searches'] = [{'name':e['name'], **{k:e['content'].get(k) for k in ('search','disabled','is_scheduled','cron_schedule')}}
                                   for e in searches if e.get('acl',{}).get('app') == 'ai_sysadmin']
        report['status'] = 'PASS'
    except Exception as exc:
        report['status'] = 'ERROR'
        report['error_type'] = type(exc).__name__
    save('splunk-baseline.json', report)
    print(json.dumps({'probe':'splunk','status':report['status'],'server':report.get('server'),'counts':report.get('counts')}), flush=True)


def gateway_probe():
    ai = tomllib.loads(Path('/etc/ai-sysadmin/config.toml').read_text())['ai']
    key = Path(ai['api_key_file']).read_text().strip()
    base = ai['base_url'].rstrip('/')
    report = {'at':dt.datetime.now(dt.timezone.utc).isoformat(), 'configured_model':ai['model'],
              'base_url':base, 'configured_timeout_seconds':ai['timeout_seconds'],
              'synthetic_input_only': True, 'requests':[]}
    def request(url, payload=None, timeout=120):
        req = urllib.request.Request(url, data=json.dumps(payload).encode() if payload is not None else None,
                                     headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = response.read(262145)
        if len(data)>262144: raise ValueError('Oversized response')
        return json.loads(data)
    try:
        models = request(base+'/models', timeout=20)
        report['advertised_model_ids'] = [m.get('id') for m in models.get('data',[])]
    except Exception as exc:
        report['model_listing_error'] = type(exc).__name__
    for label, facts in [('healthy',{'health':'healthy','actions':['apt_update','apt_upgrade'],'major_upgrade':False}),
                         ('blocked',{'health':'failed_service','actions':[],'major_upgrade':False}),
                         ('no_update',{'health':'healthy','observed_updates':0,'actions':['apt_update','apt_upgrade']})]:
        payload = {'model':ai['model'],'stream':False,'temperature':0,'max_tokens':384,
                   'response_format':{'type':'json_object'},
                   'messages':[{'role':'system','content':'This is an isolated assessment test. Do not execute anything. Return JSON with proceed (boolean) and reasoning (short string). Defer maintenance when health is not healthy.'},
                               {'role':'user','content':json.dumps(facts)}]}
        start = time.monotonic()
        row={'scenario':label,'request_bytes':len(json.dumps(payload).encode())}
        try:
            result=request(base+'/chat/completions',payload)
            content=result['choices'][0]['message']['content']
            row.update(model=result.get('model'), usage=result.get('usage'),
                       finish_reason=result['choices'][0].get('finish_reason'),
                       content_characters=len(content) if isinstance(content,str) else None)
            answer=json.loads(content)
            row.update(model=result.get('model'),usage=result.get('usage'),finish_reason=result['choices'][0].get('finish_reason'),
                       schema_valid=isinstance(answer,dict) and type(answer.get('proceed')) is bool and isinstance(answer.get('reasoning'),str),
                       proceed=answer.get('proceed'),reasoning=answer.get('reasoning','')[:600])
        except Exception as exc:
            row.update(error_type=type(exc).__name__,schema_valid=False)
        row['seconds']=round(time.monotonic()-start,3)
        report['requests'].append(row)
        save('gateway-baseline.json',report)
        print(json.dumps({'probe':'gateway',**row}),flush=True)
    report['median_seconds']=statistics.median(r['seconds'] for r in report['requests'])
    report['scope']='Stage 0 three-request baseline, not the later 20-request v2 acceptance benchmark.'
    save('gateway-baseline.json',report)


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('probe', choices=['splunk','gateway'])
    parser.add_argument('--report',type=Path,default=REPORT)
    args=parser.parse_args()
    REPORT=args.report.resolve()
    assert REPORT.parent == Path('/home/bot/ai-sysadmin-multi-agent-plan/stage-0')
    assert REPORT.is_dir()
    if args.probe == 'splunk': splunk_probe()
    else: gateway_probe()
