#!/usr/bin/env python3
"""Bounded ARP probes; no address/route changes, spoofing of another host, or ARP replies.
Uses this NIC's MAC and 0.0.0.0 sender IP (address-conflict-detection style).
Accounts for kernel VLAN stripping via PACKET_AUXDATA. Run with sudo.
"""
import socket,struct,time,json,pathlib
iface='ens18'
mac=bytes.fromhex(pathlib.Path('/sys/class/net/'+iface+'/address').read_text().strip().replace(':',''))
s=socket.socket(socket.AF_PACKET,socket.SOCK_RAW,socket.htons(3))
s.bind((iface,0));s.setsockopt(263,8,1);s.settimeout(.15)
results=[]
for vlan,target in [(None,'192.168.2.1'),(None,'192.168.1.1'),(None,'192.168.1.50'),(2,'192.168.2.1'),(3,'192.168.3.1')]:
 arp=struct.pack('!HHBBH',1,0x0800,6,4,1)+mac+bytes(4)+bytes(6)+socket.inet_aton(target)
 eth=bytes.fromhex('ffffffffffff')+mac
 eth+=struct.pack('!H',0x0806) if vlan is None else struct.pack('!HHH',0x8100,vlan,0x0806)
 frame=(eth+arp).ljust(60,b'\x00')
 sent=0;answers=[];end=time.monotonic()+2
 while time.monotonic()<end:
  if sent<2:
   s.send(frame);sent+=1
  try:d,anc,flags,addr=s.recvmsg(2048,256)
  except socket.timeout:continue
  if addr[2]==socket.PACKET_OUTGOING or len(d)<42:continue
  typ=struct.unpack('!H',d[12:14])[0];off=14;observed_vlan=None
  for level,kind,data in anc:
   if level==263 and kind==8 and len(data)>=20:
    status,_,_,_,_,tci,tpid=struct.unpack('=IIIHHHH',data[:20])
    if status & 16:observed_vlan=tci&4095
  if typ==0x8100:
   tci,typ=struct.unpack('!HH',d[14:18]);observed_vlan=tci&4095;off=18
  if typ!=0x0806 or len(d)<off+28:continue
  op=struct.unpack('!H',d[off+6:off+8])[0]
  sender=socket.inet_ntoa(d[off+14:off+18])
  if op==2 and sender==target and d[off+18:off+24]==mac:
   ans={'sender_ip':sender,'sender_mac':d[off+8:off+14].hex(':'),'observed_vlan':observed_vlan}
   if ans not in answers:answers.append(ans)
 row={'sent_vlan':vlan,'target':target,'requests':sent,'replies':answers};results.append(row);print(json.dumps(row),flush=True)
pathlib.Path('/home/bot/scan/isolation-audit/retest-20261005T1411Z/l2-probe.json').write_text(json.dumps(results,indent=2)+'\n')
