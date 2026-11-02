"""One large CPU mesh/scoring job at a time; never starts training."""
import os,sys,json,time,fcntl,subprocess
from r8_screen_prepare import R,A,PH,O,C,dump,sha
ROOT=O/'screen_sim'
def run(args,logname):
 while int(next(l.split()[1] for l in open('/proc/meminfo') if l.startswith('MemAvailable:')))/1024**2<48:time.sleep(15)
 cmd=['docker','run','--rm','--read-only','--network','none','--runtime','runc','--name','jbgs-screen-sim-cpu','--user',f'{os.getuid()}:{os.getgid()}','--cpus','6','--memory','32g','--memory-swap','32g','--shm-size','1g']
 for e in ['PYTHONDONTWRITEBYTECODE=1','PYTHONUNBUFFERED=1','OMP_NUM_THREADS=6','OPENBLAS_NUM_THREADS=1','MKL_NUM_THREADS=1','CUDA_VISIBLE_DEVICES=','NVIDIA_VISIBLE_DEVICES=void','PYTHONPATH=/repo','TMPDIR=/target/tmp','NUMBA_CACHE_DIR=/target/tmp/numba','MPLCONFIGDIR=/target/tmp/mpl','TZ=Asia/Seoul']:cmd+=['-e',e]
 mounts=[(R,'/repo'),(A,'/art'),(PH,'/ph'),(C,'/cfg'),(PH/'main_stage1_v1/PHD-MAIN-STAGE1-v1','/out'),(PH/'main_stage0_v1/PHD-MAIN-STAGE0-v1','/s0'),(PH/'metrics_trial_v1/PHD-MAIN-METRICS-TRIAL-v1','/mt'),(PH/'metrics_fix_v1/PHD-MAIN-METRICS-FIX-v1','/mf'),(PH/'main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1','/dr'),(PH/'main_prep_measure_v1/PHD-MAIN-PREP-MEASURE-v1','/prep'),(PH/'main_stage1_diag_v1/PHD-MAIN-STAGE1-DIAG-v1','/diag')]
 for p,d in mounts:cmd+=['-v',f'{p}:{d}:ro']
 cmd+=['-v',f'{O}:/target:rw','--entrypoint','python','jointbuildgs:dev','-B','-u','/repo/scripts/phd/main_target_v1/screen_sim_mesh.py']+args
 log=ROOT/'execution'/(logname+'.log');start=time.time();dump(log.with_suffix('.command.json'),cmd)
 with log.open('x') as f:rc=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT).returncode
 dump(log.with_suffix('.receipt.json'),dict(exit_code=rc,seconds=time.time()-start));assert rc==0,(args,rc,str(log));print('SIM_CPU',args,round(time.time()-start),flush=True)
def main():
 cfg=json.loads((C/'screen_sim.json').read_text());pending=[(r,v) for r in cfg['states'] for v in ['before']+[x['key'] for x in cfg['candidates']]];handle=(PH/'main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/checks/tsdf.lock').open('r');fcntl.flock(handle,fcntl.LOCK_EX)
 while pending:
  ready=next(((r,v) for r,v in pending if (ROOT/'states'/r['key']/v/'summary.json').exists()),None)
  if ready is None:time.sleep(15);continue
  r,v=ready;k=r['key'];wd=ROOT/'meshes'/k/v;prefix=k+'_'+v
  if not (wd/'inputs/binding.json').exists():run(['prep',k,v],prefix+'_prep')
  if not (wd/'plan/plan.json').exists():run(['plan',k,v],prefix+'_plan')
  lay=json.loads((wd/'plan/layout.json').read_text())
  for t in lay['tiles']:
   if not (wd/f'tiles/tile{t["k"]}.json').exists():run(['tile',k,v,str(t['k'])],prefix+'_tile'+str(t['k']))
  if not (wd/'merged.json').exists():run(['merge',k,v],prefix+'_merge')
  for p in (['ALS','LoD2'] if r['family']=='image_only' else [r['prior']]):
   if not (ROOT/'scores'/k/v/p/'values.json').exists():run(['score',k,v,p],prefix+'_score_'+p)
  pending.remove(ready);dump(ROOT/'cpu_progress.json',dict(completed=40-len(pending),pending=[r['key']+'/'+v for r,v in pending],scientific_verdict=None))
 dump(ROOT/'cpu_receipt.json',dict(status='PASS',meshes=40,score_partitions=45,training=False,scientific_verdict=None))
if __name__=='__main__':main()
