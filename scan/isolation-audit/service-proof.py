#!/usr/bin/env python3
import socket,struct,json,pathlib,time
rows=[]
for addr,port,kind in [('fe80::be24:11ff:fe4b:3ef5',22,'ssh'),('fe80::be24:11ff:febe:aa22',22,'ssh'),('fe80::f64d:30ff:fe60:69ad',22,'ssh'),('fe80::aef2:3cff:feab:af25',80,'http'),('fe80::be24:11ff:fe4b:3ef5',8080,'http')]:
 row=dict(address=addr,scope='ens18',port=port,protocol=kind)
 try:
  with socket.socket(socket.AF_INET6,socket.SOCK_STREAM) as s:
   s.settimeout(3);s.connect((addr,port,0,socket.if_nametoindex('ens18')))
   if kind=='http':s.sendall(b'HEAD / HTTP/1.0\r\nHost: ['+addr.encode()+b']\r\nConnection: close\r\n\r\n')
   data=s.recv(4096).decode('latin1')
   row['response']=[x for x in data.split('\r\n') if x.startswith(('SSH-','HTTP/')) or x.lower().startswith(('server:','content-type:'))]
 except OSError as e:row['error']=str(e)
 rows.append(row);print(json.dumps(row),flush=True)
 time.sleep(.2)
qname=b''.join(bytes([len(x)])+x.encode() for x in 'example.com'.split('.'))+b'\x00'
query=struct.pack('!HHHHHH',31902,0x0100,1,0,0,0)+qname+struct.pack('!HH',1,1)
for addr,iface in [('192.168.2.1',None),('fd8b:7c34:a921:20::1','ens18.2'),('fe80::6c63:f8ff:fe15:eaa0','ens18.2'),('fe80::6c63:f8ff:fe15:eaa0','ens18')]:
 row=dict(address=addr,scope=iface,port=53,protocol='udp DNS',query='example.com A')
 try:
  family=socket.AF_INET6 if ':' in addr else socket.AF_INET
  with socket.socket(family,socket.SOCK_DGRAM) as s:
   s.settimeout(2)
   dst=(addr,53,0,socket.if_nametoindex(iface)) if iface else (addr,53)
   s.sendto(query,dst);data,peer=s.recvfrom(4096)
   ident,flags,qd,an,ns,ar=struct.unpack('!HHHHHH',data[:12])
   row.update(reply_from=peer[0],transaction_matches=ident==31902,rcode=flags&15,answer_count=an,recursion_available=bool(flags&128))
 except OSError as e:row['error']=str(e)
 rows.append(row);print(json.dumps(row),flush=True)
pathlib.Path('isolation-audit/service-proof.json').write_text(json.dumps(rows,indent=2)+'\n')
