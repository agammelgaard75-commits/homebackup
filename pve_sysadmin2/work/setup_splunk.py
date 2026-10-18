from admin import *
import io,tarfile,uuid
conf=''
for name,cap in [('sysadmin_pve',768),('sysadmin_vm',1536)]:
 conf+=f'''[{name}]
homePath = $SPLUNK_DB/{name}/db
coldPath = $SPLUNK_DB/{name}/colddb
thawedPath = $SPLUNK_DB/{name}/thaweddb
repFactor = auto
maxTotalDataSizeMB = {cap}
maxDataSize = 10
maxHotBuckets = 2
frozenTimePeriodInSecs = 604800

'''
Path('deployment/indexes.conf').write_text(conf)
print(ssh('splunk-cm','sudo mkdir -p /opt/splunk/etc/manager-apps/sysadmin_indexes/local && sudo tee /opt/splunk/etc/manager-apps/sysadmin_indexes/local/indexes.conf >/dev/null && sudo chown -R splunk:splunk /opt/splunk/etc/manager-apps/sysadmin_indexes',conf.encode()))
print('Bundle:',api('splunk-cm','/services/cluster/manager/control/default/apply',{}).get('messages',[]))
