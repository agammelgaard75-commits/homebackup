from admin import *
import xml.etree.ElementTree as E
from urllib.parse import quote
APP='sysadmin'
existing=api('splunk-sh','/services/apps/local')['entry']
if not any(e['name']==APP for e in existing):api('splunk-sh','/services/apps/local',{'name':APP,'label':'Sandbox Sysadmin','visible':'1'})
path='/servicesNS/nobody/sysadmin/configs/conf-props'
entries=api('splunk-sh',path)['entry']
if not any(e['name']=='sysadmin:json' for e in entries):api('splunk-sh',path,{'name':'sysadmin:json'})
api('splunk-sh',path+'/'+quote('sysadmin:json',safe=''),{'KV_MODE':'json','AUTO_KV_JSON':'true','SHOULD_LINEMERGE':'false','TRUNCATE':'20000'})
# Lookup ensures expected collectors remain visible even when no recent events arrive.
lookup='host,role,vmid\nsandboxpve,pve,\nsplunk-cm,vm,100\nsplunk-idx1,vm,101\nsplunk-idx2,vm,102\nsplunk-sh,vm,103\ndns01,container,104\n'
ssh('splunk-sh','sudo mkdir -p /opt/splunk/etc/apps/sysadmin/lookups && sudo tee /opt/splunk/etc/apps/sysadmin/lookups/sysadmin_hosts.csv >/dev/null && sudo chown -R splunk:splunk /opt/splunk/etc/apps/sysadmin',lookup.encode())
Path('deployment/sysadmin_hosts.csv').write_text(lookup)
def sub(parent,tag,text=None,**attrs):
 e=E.SubElement(parent,tag,attrs)
 if text is not None:e.text=text
 return e
def base(root,id,q,earliest='$window.earliest$',latest='$window.latest$'):
 s=sub(root,'search',id=id);sub(s,'query',q);sub(s,'earliest',earliest);sub(s,'latest',latest);sub(s,'refresh','120s');sub(s,'refreshType','delay')
def panel(row,title,q,baseid=None,typ='table',chart=None):
 p=sub(row,'panel');sub(p,'title',title);v=sub(p,typ)
 s=sub(v,'search',**({'base':baseid} if baseid else {}));sub(s,'query',q)
 if not baseid:sub(s,'earliest','$window.earliest$');sub(s,'latest','$window.latest$');sub(s,'refresh','120s');sub(s,'refreshType','delay')
 if typ=='table':sub(v,'option','10',name='count');sub(v,'option','true',name='wrap')
 if typ=='chart':sub(v,'option',chart or 'line',name='charting.chart');sub(v,'option','bottom',name='charting.legend.placement')
 if typ=='single':sub(v,'option','true',name='useColors');sub(v,'option','block',name='colorMode')
 return v
for scope in ['vm','pve']:
 idx='sysadmin_'+scope;isvm=scope=='vm';title='VM & Container Sysadmin' if isvm else 'PVE Sysadmin'
 root=E.Element('form',{'version':'1.1','theme':'dark'});sub(root,'label',title)
 sub(root,'description','System logs, health and collection status. Health updates every minute; dashboard searches refresh every 2 minutes. Stale means no heartbeat for 3 minutes. Historical panels use the selected time range; current status uses recent samples. At-least-once events are deduplicated by event_id.')
 fs=sub(root,'fieldset',submitButton='false');t=sub(fs,'input',type='time',token='window',searchWhenChanged='true');sub(t,'label','Time range');d=sub(t,'default');sub(d,'earliest','-4h');sub(d,'latest','now')
 host=sub(fs,'input',type='dropdown',token='host',searchWhenChanged='true');sub(host,'label','Host');sub(host,'choice','All hosts',value='*');sub(host,'default','*')
 for h,role in [('sandboxpve','pve'),('splunk-cm','vm'),('splunk-idx1','vm'),('splunk-idx2','vm'),('splunk-sh','vm'),('dns01','container')]:
  if (role=='pve') != isvm:sub(host,'choice',h,value=h)
 # Shared base searches reduce concurrent work on this small search head.
 base(root,'metrics',f'index={idx} source=sysadmin:health host=$host|s$ | dedup event_id | fields _time host cpu_pct memory_pct load1 failed_services failed_units queue_events uptime')
 base(root,'logs',f'index={idx} (source=sysadmin:journal OR source=sysadmin:collector_error OR source=sysadmin:pve_access) host=$host|s$ | dedup event_id | fields _time host kind priority severity unit process message http_status component')
 base(root,'current',f'| inputlookup sysadmin_hosts.csv | where '+('role!="pve"' if isvm else 'role="pve"')+f' | search host=$host|s$ | join type=left host [search index={idx} source=sysadmin:health earliest=-24h latest=now | stats latest(_time) as last_seen latest(cpu_pct) as cpu_pct latest(memory_pct) as memory_pct latest(failed_services) as failed_services latest(queue_events) as queue_events latest(uptime) as uptime by host] | eval age_seconds=round(now()-last_seen), collection=case(isnull(last_seen),"MISSING",age_seconds>180,"STALE",true(),"OK")',earliest='-24h',latest='now')
 base(root,'disks',f'index={idx} source=sysadmin:filesystem host=$host|s$ | stats latest(_time) as last_seen latest(disk_pct) as disk_pct latest(disk_available) as disk_available latest(inode_pct) as inode_pct by host mount',earliest='-5m',latest='now')
 if isvm:
  base(root,'guests','index=sysadmin_pve source=sysadmin:guest | stats latest(_time) as last_seen latest(status) as status latest(type) as type latest(cpu_pct) as cpu_pct latest(memory_pct) as memory_pct latest(uptime) as uptime by vmid name | search name=$host|s$',earliest='-5m',latest='now')
 else:
  base(root,'tasks','index=sysadmin_pve source=sysadmin:pve_task host=$host|s$ | dedup event_id | fields _time type id user status upid starttime endtime')
 row=sub(root,'row')
 panel(row,'Collectors reporting / expected','| stats count(eval(collection="OK")) as reporting count as expected | eval coverage=reporting." / ".expected | fields coverage','current','single')
 panel(row,'Stale or missing collectors','| stats count(eval(collection!="OK")) as stale','current','single')
 panel(row,'Errors in selected time range','| where priority<=3 | stats count as errors','logs','single')
 panel(row,'Failed services (fresh hosts)','| where collection="OK" | stats sum(failed_services) as failed_services','current','single')
 row=sub(root,'row');panel(row,'Current host health and collection status','| eval last_seen=strftime(last_seen,"%F %T"), uptime_hours=round(uptime/3600,1) | table host role collection age_seconds cpu_pct memory_pct failed_services queue_events uptime_hours last_seen','current')
 if isvm:
  row=sub(root,'row');panel(row,'PVE guest inventory (last 5 minutes)','| eval age_seconds=round(now()-last_seen) | table vmid name type status cpu_pct memory_pct age_seconds','guests')
 row=sub(root,'row');panel(row,'CPU utilization (%)','| timechart span=5m avg(cpu_pct) by host','metrics','chart');panel(row,'Memory utilization (%)','| timechart span=5m avg(memory_pct) by host','metrics','chart')
 row=sub(root,'row');panel(row,'Filesystem capacity (last 5 minutes)','| eval available_GiB=round(disk_available/1024/1024/1024,2), status=case(disk_pct>=90,"CRITICAL",disk_pct>=80,"WARNING",true(),"OK") | sort - disk_pct | table host mount status disk_pct available_GiB inode_pct','disks')
 if isvm:
  panel(row,'Network throughput (Kbit/s)',f'index={idx} source=sysadmin:network host=$host|s$ | dedup event_id | eval throughput_kbps=rx_kbps+tx_kbps | timechart span=5m avg(throughput_kbps) by host',typ='chart')
 else:
  panel(row,'PVE storage pools (last 5 minutes)','index=sysadmin_pve source=sysadmin:storage earliest=-5m latest=now host=$host|s$ | stats latest(active) as active latest(disk_pct) as disk_pct latest(avail) as available by storage type | eval available_GiB=round(available/1024/1024/1024,2) | table storage type active disk_pct available_GiB')
  row=sub(root,'row');panel(row,'VM and container state (last 5 minutes)','index=sysadmin_pve source=sysadmin:guest earliest=-5m latest=now host=$host|s$ | stats latest(status) as status latest(type) as type latest(cpu_pct) as cpu_pct latest(memory_pct) as memory_pct by vmid name | table vmid name type status cpu_pct memory_pct')
  panel(row,'PVE tasks by result','| stats count by status','tasks','chart','bar')
  row=sub(root,'row');panel(row,'Recent PVE tasks / backups / migrations','| sort - _time | eval duration_s=endtime-starttime | table _time type id user status duration_s | head 50','tasks')
  panel(row,'Failed or warning PVE tasks','| search status!="OK" | sort - _time | table _time type id user status | head 50','tasks')
 row=sub(root,'row');panel(row,'Log volume by severity','| timechart span=5m count by severity','logs','chart','column')
 panel(row,'Authentication failures','| where match(message,"(?i)(failed password|authentication failure|invalid user|failed authentication|authentication failed)") | sort - _time | table _time host process message | head 50','logs')
 row=sub(root,'row');panel(row,'Recent warnings and errors','| where priority<=4 | sort - _time | table _time host severity unit process message | head 100','logs')
 panel(row,'Collector errors','| search kind=collector_error | sort - _time | table _time host component message | head 50','logs')
 row=sub(root,'row');panel(row,'Recent system logs','| sort - _time | table _time host severity unit process message | head 100','logs')
 xml=E.tostring(root,encoding='unicode');name=scope+'_sysadmin';Path('deployment/'+name+'.xml').write_text(xml)
 path='/servicesNS/nobody/sysadmin/data/ui/views'
 existing=api('splunk-sh',path)['entry'];data={'eai:data':xml}
 if not any(e['name']==name for e in existing):data['name']=name
 api('splunk-sh',path+('/'+name if 'name' not in data else ''),data)
 api('splunk-sh',path+'/'+name+'/acl',{'owner':'nobody','sharing':'app','perms.read':'*','perms.write':'admin'})
 print('Published',name)
nav='<nav search_view="search"><view name="vm_sysadmin" default="true"/><view name="pve_sysadmin"/><view name="search"/></nav>'
path='/servicesNS/nobody/sysadmin/data/ui/nav'
try:api('splunk-sh',path+'/default',{'eai:data':nav})
except RuntimeError:api('splunk-sh',path,{'name':'default','eai:data':nav})
