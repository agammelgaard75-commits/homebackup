import json
from pathlib import Path
import xml.etree.ElementTree as E
from splunk_api import get, search

path=Path('/home/bot/splunk/deployment/server_health/default/data/ui/views/server_health.xml')
root=E.parse(path).getroot()
bases={s.attrib['id']:s for s in root.findall('search')}
report=[]
for panel in root.findall('./row/panel'):
    title=panel.findtext('title')
    s=panel.find('.//search')
    q=s.findtext('query')
    if 'base' in s.attrib:
        base=bases[s.attrib['base']]
        query='search '+base.findtext('query')+' '+q
        earliest=base.findtext('earliest')
    else:
        query='search '+q
        earliest=s.findtext('earliest')
    earliest={'$trends_earliest$':'-1h','$journal_earliest$':'-15m'}.get(earliest,earliest)
    rows=search(query,earliest)
    report.append({'panel':title,'rows':len(rows),'sample':rows[:2]})
    print(title,':',len(rows),'rows',json.dumps(rows[:1])[:350],flush=True)
Path('/home/bot/splunk/evidence/dashboard-queries.json').write_text(json.dumps(report,indent=2)+'\n')
view=get('/servicesNS/admin/server_health/data/ui/views/server_health')['entry'][0]
assert view['content']['eai:data']
print('Dashboard registered in Splunk:',view['name'])
