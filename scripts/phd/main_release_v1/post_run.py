"""Queue completion hook; bounded postprocessing then committed gate wait."""
import ctypes,json,os,select,subprocess,sys
from gpu_job import R,O,D,C,dump,now,command
from publish import lock,commit,bundle
S=R/'scripts/phd/main_release_v1'
def cpu(tag,script,*args):subprocess.run(['bash',str(S/'run_cpu.sh'),tag,script,*map(str,args)],cwd=R,check=True)
def await_file(p):
 p.parent.mkdir(parents=True,exist_ok=True);libc=ctypes.CDLL(None);fd=libc.inotify_init1(os.O_NONBLOCK);assert fd>=0
 libc.inotify_add_watch(fd,os.fsencode(p.parent),0x100|0x80|0x8)
 try:
  while not p.exists():
   select.select([fd],[],[])
   try:os.read(fd,65536)
   except BlockingIOError:pass
 finally:os.close(fd)
def main(site,prior,rule,stage):
 stage=int(stage);name=f'rlog_{prior}_s0' if stage==2 else f'rl_{rule}_{prior}_s0';run=O/'runs'/site/name
 receipt=json.loads((run/'receipt.json').read_text());key=f'{site}__{prior}__{name}'
 if receipt['status'].startswith('COMPLETED'):
  cpu('events-'+key,'event_report.py',site,prior,rule,stage)
  if stage==3:
   cpu('job-'+key,'run_result.py','prepare',site,prior,rule)
   subprocess.run(command(0 if prior=='ALS' else 1,'jbgs-release-result-'+key,'rescore_task.py',['render','/release/jobs/'+key+'.json'],site=site),check=True)
   subprocess.run([sys.executable,str(S/'mesh_job.py'),key],cwd=R,check=True)
   cpu('result-'+key,'run_result.py','report',site,prior,rule)
 else:
  dump(D/'runs'/f'{key}.json',dict(**receipt,result='결과 없음'))
 dump(O/'completion'/f'{key}.json',dict(at=now(),postprocess=True,status=receipt['status'],scientific_verdict=None))
 if stage==2:
  other='LoD2' if prior=='ALS' else 'ALS';await_file(O/'completion'/f'{site}__{other}__rlog_{other}_s0.json')
  with lock():
   if not (O/'delivery/stage2.json').exists():
    cpu('stage2-summary','event_report.py','summary')
    rec=bundle('PHD-MAIN-RELEASE-v1_단계2.zip',[C,D/'tables/stage2',D/'figures/stage2',D/'단계2_보고.md',S/'event_report.py',O/'verification',O/'events'])
    paths=[C,S,R/'src/phd/forks/GeoGS-conf-guided-v1-r24',D/'tables/stage2',D/'figures/stage2',D/'단계2_보고.md']
    head=commit('stage 2 event records', [p for p in paths if p.exists()]);dump(O/'delivery/stage2.json',dict(commit=head,bundle=rec,scientific_verdict=None))
  # A JSON can precede its commit receipt by seconds. Wait for the latter.
  await_file(O/'delivery/stage3_gate.json')
 else:
  with lock():
   paths=[D/'runs'/f'{key}.json',D/'tables/runs'/key,D/'figures/runs'/key]
   rec=bundle(f'PHD-MAIN-RELEASE-v1_{site}_{prior}_{rule}.zip',[C,*paths,O/'events'/key,run/'receipt.json'])
   head=commit('stage 3 '+key,[p for p in paths if p.exists()]);dump(O/'delivery'/f'{key}.json',dict(commit=head,bundle=rec,scientific_verdict=None))
if __name__=='__main__':main(*sys.argv[1:])
