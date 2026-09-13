"""Live verification; credentials are read by the existing loopback-only helper."""
import collections
import json
from pathlib import Path
import sys
import time
import xml.etree.ElementTree as ET
sys.path.insert(0,'/home/bot/splunk/scripts')
from splunk_api import get,search
ROOT=Path('/home/bot/sysadmin')
report={}
info=get('/services/server/info')['entry'][0]['content']
report['server']={k:info.get(k) for k in ('version','build','licenseState','kvStoreStatus')}
assert info['licenseState']=='OK' and info['kvStoreStatus']=='ready'
report['health']=get('/services/server/health/splunkd')['entry'][0]['content']['health']
if report['health'] != 'green':
    report['health_details']=get('/services/server/health/splunkd/details')['entry'][0]['content']
report['inputs']=[]
inputs=get('/services/data/inputs/monitor?count=0')['entry']
for filename,suffix in [('audit','audit'),('health','health'),('anomalies','anomaly')]:
    source=Path('/var/log/ai-sysadmin')/(filename+'.jsonl')
    entries=[e for e in inputs if e['name']==str(source)]
    assert len(entries)==1, entries
    content=entries[0]['content']
    assert content['index']=='ai_sysadmin' and not content['disabled'], content
    lines=collections.Counter(source.read_text().splitlines())
    deadline=time.monotonic()+30
    while True:
        indexed=collections.Counter(r['_raw'] for r in search(f'search index=ai_sysadmin sourcetype=ai_sysadmin:{suffix} earliest=0 | table _raw','0'))
        if lines==indexed or time.monotonic()>=deadline:
            break
        time.sleep(2)
    assert lines==indexed, (filename,len(lines),len(indexed),sum((lines-indexed).values()),sum((indexed-lines).values()))
    report['inputs'].append({'file':str(source),'sourcetype':'ai_sysadmin:'+suffix,'source_events':sum(lines.values()),'indexed_events':sum(indexed.values()),'exact_source_match':True})
report['timestamp_validation']=search('search index=ai_sysadmin earliest=0 | eval parsed=strptime(timestamp,"%Y-%m-%dT%H:%M:%S%:z") | stats count as total count(eval(isnull(parsed) OR abs(_time-parsed)>1)) as invalid','0')
assert report['timestamp_validation'][0]['invalid']=='0',report['timestamp_validation']
report['dashboards']=[]
for name in ('health_dashboard','anomaly_dashboard'):
    view=get('/servicesNS/nobody/ai_sysadmin/data/ui/views/'+name)['entry'][0]
    root=ET.fromstring(view['content']['eai:data'])
    panels=[]
    for panel in root.findall('./row/panel'):
        node=panel.find('.//search')
        query=node.findtext('query')
        rows=search('search '+query,node.findtext('earliest') or '-30d')
        assert rows, (name,panel.findtext('.//title'))
        panels.append({'title':panel.findtext('.//title'),'rows':len(rows)})
    report['dashboards'].append({'view':name,'label':root.findtext('label'),'panels':panels})
report['latest_health']=search("search index=ai_sysadmin sourcetype=ai_sysadmin:health earliest=-30d | head 1 | eval failed_count=coalesce(mvcount('failed_units{}'),0) | table timestamp root_free_percent failed_count upgradable_package_count reboot_required",'-30d')
assert report['latest_health'][0]['failed_count']=='0'
report['closed_change']=search('search index=ai_sysadmin sourcetype=ai_sysadmin:audit event_type=closure change_id=CHG-20260913-R2 status=CLOSED earliest=-30d | stats count as count','-30d')
assert int(report['closed_change'][0]['count'])>=1
report['splunk_outage_anomaly']=search('search index=ai_sysadmin sourcetype=ai_sysadmin:anomaly change_id=SPLUNK-20260913 earliest=-30d | table timestamp severity message','-30d')
assert report['splunk_outage_anomaly']
(ROOT/'reports/splunk-live-verification.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
