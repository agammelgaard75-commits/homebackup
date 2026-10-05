import subprocess,pathlib,concurrent.futures
out=pathlib.Path(__file__).resolve().parent
base=['sudo','-n','nmap','-n','-Pn','-sS','--reason','--max-retries','1','--max-rate','40','-p','22,53,80,443,445,8006,8080,8443,11434']
targets=['192.168.1.1','192.168.1.43','192.168.1.201','192.168.2.1','192.168.3.1','192.168.3.189']
def run(pair):
 label,extra=pair;cmd=base+extra+['-oA',str(out/label)]+targets
 p=subprocess.run(cmd,capture_output=True,text=True,timeout=60);(out/(label+'.log')).write_text(repr(cmd)+'\n'+p.stdout+p.stderr);print(label,p.returncode)
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
 for x in pool.map(run,[('source-port53',['--source-port','53']),('source-port443',['--source-port','443']),('fragmented-syn',['-f'])]):pass
