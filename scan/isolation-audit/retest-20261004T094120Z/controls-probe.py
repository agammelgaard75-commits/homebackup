import subprocess,pathlib,concurrent.futures,socket,struct,time,json,os
out=pathlib.Path('/home/bot/scan/isolation-audit/latest-retest-path.txt').read_text().strip();out=pathlib.Path(out)
def container():
 pid=subprocess.check_output(['sudo','-n','docker','inspect','--format','{{.State.Pid}}','n8n'],text=True).strip()
 args=['sudo','-n','nsenter','-t',pid,'-n','nmap','--unprivileged','-n','-sT','-Pn','--reason','--max-retries','1','--max-rate','10','--host-timeout','30s','-p','22,53,80,443,445,8006','192.168.1.1','192.168.2.1','192.168.3.1']
 r=subprocess.run(args,capture_output=True,text=True,timeout=45);(out/'container-ipv4.txt').write_text(repr(args)+'\n'+r.stdout+r.stderr+'\nexit='+str(r.returncode)+'\n');print(r.stdout+r.stderr)
 args=['sudo','-n','nsenter','-t',pid,'-n','curl','--noproxy','*','-4','-sS','-I','--connect-timeout','4','--max-time','8','--resolve','example.com:443:'+socket.gethostbyname('example.com'),'https://example.com']
 r=subprocess.run(args,capture_output=True,text=True,timeout=12);(out/'container-internet.txt').write_text(repr(args)+'\n'+r.stdout+r.stderr+'\nexit='+str(r.returncode)+'\n');print(r.stdout+r.stderr)
def multicast(iface,ident):
 s=socket.socket(socket.AF_INET6,socket.SOCK_RAW,socket.IPPROTO_ICMPV6);s.setsockopt(socket.SOL_SOCKET,socket.SO_BINDTODEVICE,iface.encode()+b'\0');s.setsockopt(socket.IPPROTO_IPV6,socket.IPV6_MULTICAST_HOPS,1);s.settimeout(.2)
 replies=[];sent=0;end=time.monotonic()+4
 while time.monotonic()<end:
  if sent<2:
   s.sendto(struct.pack('!BBHHH',128,0,0,ident,sent)+b'isolation-retest',('ff02::1',0,0,socket.if_nametoindex(iface)));sent+=1
  try:d,src=s.recvfrom(2048)
  except socket.timeout:continue
  if len(d)>=8 and d[0]==129 and struct.unpack('!H',d[4:6])[0]==ident and src[0] not in replies:replies.append(src[0])
 row=dict(iface=iface,requests=sent,reply_addresses=replies,other_addresses=[a for a in replies if a!='fe80::be24:11ff:feac:52ab']);(out/('multicast-'+iface+'.json')).write_text(json.dumps(row,indent=2)+'\n');print(json.dumps(row));s.close()
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
 fs=[pool.submit(container),pool.submit(multicast,'ens18',30241)]
 for f in fs:f.result()
