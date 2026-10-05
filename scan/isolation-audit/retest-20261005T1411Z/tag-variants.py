import socket,struct,time,json,pathlib
out=pathlib.Path(__file__).resolve().parent
iface='ens18';mac=bytes.fromhex(pathlib.Path('/sys/class/net/ens18/address').read_text().strip().replace(':',''))
s=socket.socket(socket.AF_PACKET,socket.SOCK_RAW,socket.htons(3));s.bind((iface,0));s.setsockopt(263,8,1);s.settimeout(.1);results=[]
variants=[([], '192.168.2.1'),([], '192.168.3.189'),([(0x8100,0)],'192.168.2.1'),([(0x8100,1)],'192.168.1.1'),([(0x8100,3)],'192.168.3.189'),([(0x8100,2),(0x8100,3)],'192.168.3.1'),([(0x8100,0),(0x8100,3)],'192.168.3.1'),([(0x88a8,2),(0x8100,3)],'192.168.3.1'),([(0x8100,2),(0x8100,1)],'192.168.1.1')]
for tags,target in variants:
 arp=struct.pack('!HHBBH',1,0x0800,6,4,1)+mac+bytes(4)+bytes(6)+socket.inet_aton(target)
 frame=bytes.fromhex('ffffffffffff')+mac+b''.join(struct.pack('!HH',*t) for t in tags)+struct.pack('!H',0x0806)+arp
 for _ in range(2):s.send(frame.ljust(60,b'\x00'))
 end=time.monotonic()+1.5;answers=[]
 while time.monotonic()<end:
  try:d,anc,flags,addr=s.recvmsg(2048,256)
  except socket.timeout:continue
  if addr[2]==socket.PACKET_OUTGOING or len(d)<42:continue
  typ=struct.unpack('!H',d[12:14])[0];off=14;seen=[]
  for level,kind,data in anc:
   if level==263 and kind==8 and len(data)>=20:
    status,_,_,_,_,tci,tpid=struct.unpack('=IIIHHHH',data[:20])
    if status&16:seen.append([hex(tpid),tci&4095])
  while typ in (0x8100,0x88a8) and len(d)>=off+4:
   tci,nxt=struct.unpack('!HH',d[off:off+4]);seen.append([hex(typ),tci&4095]);typ=nxt;off+=4
  if typ!=0x0806 or len(d)<off+28:continue
  if struct.unpack('!H',d[off+6:off+8])[0]==2 and socket.inet_ntoa(d[off+14:off+18])==target and d[off+18:off+24]==mac:
   row={'sender':target,'mac':d[off+8:off+14].hex(':'),'tags':seen}
   if row not in answers:answers.append(row)
 results.append({'sent_tags':[[hex(a),b] for a,b in tags],'target':target,'requests':2,'replies':answers})
s.close();(out/'tag-variants.json').write_text(json.dumps(results,indent=2)+'\n');print(json.dumps(results,indent=2))
