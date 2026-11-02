"""One TSDF mesh and one completed-mesh score at a time, disjoint output paths."""
import os,json,time,fcntl,subprocess,concurrent.futures
from r8_screen_prepare import R,A,PH,O,C,dump,sha
ROOT=O/'screen_sim'
def run(args,name):
 while int(next(l.split()[1] for l in open('/proc/meminfo') if l.startswith('MemAvailable:')))/1024**2<48:time.sleep(10)
 lane='score' if args[0]=='score' else 'mesh';cmd=['docker','run','--rm','--read-only','--network','none','--runtime','runc','--name','jbgs-screen-sim-'+lane,'--user',f'{os.getuid()}:{os.getgid()}','--cpus','24','--memory','32g','--memory-swap','32g','--shm-size','1g']
 for e in ['PYTHONDONTWRITEBYTECODE=1','PYTHONUNBUFFERED=1','OMP_NUM_THREADS=6','OPENBLAS_NUM_THREADS=1','MKL_NUM_THREADS=1','CUDA_VISIBLE_DEVICES=','NVIDIA_VISIBLE_DEVICES=void','PYTHONPATH=/repo','TMPDIR=/target/tmp','NUMBA_CACHE_DIR=/target/tmp/numba','MPLCONFIGDIR=/target/tmp/mpl','TZ=Asia/Seoul']:cmd+=['-e',e]
 mounts=[(R,'/repo'),(A,'/art'),(PH,'/ph'),(C,'/cfg'),(PH/'main_stage1_v1/PHD-MAIN-STAGE1-v1','/out'),(PH/'main_stage0_v1/PHD-MAIN-STAGE0-v1','/s0'),(PH/'metrics_trial_v1/PHD-MAIN-METRICS-TRIAL-v1','/mt'),(PH/'metrics_fix_v1/PHD-MAIN-METRICS-FIX-v1','/mf'),(PH/'main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1','/dr'),(PH/'main_prep_measure_v1/PHD-MAIN-PREP-MEASURE-v1','/prep'),(PH/'main_stage1_diag_v1/PHD-MAIN-STAGE1-DIAG-v1','/diag')]
 for p,d in mounts:cmd+=['-v',f'{p}:{d}:ro']
 cmd+=['-v',f'{O}:/target:rw','--entrypoint','python','jointbuildgs:dev','-B','-u','/repo/scripts/phd/main_target_v1/screen_sim_mesh.py']+args
 p=ROOT/'execution'/(name+'_p2.log');dump(p.with_suffix('.command.json'),cmd);start=time.time()
 with p.open('x') as f:rc=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT).returncode
 dump(p.with_suffix('.receipt.json'),dict(exit_code=rc,seconds=time.time()-start,lane=lane));assert rc==0,(args,rc,str(p));print('SIM_PIPELINE',args,round(time.time()-start),flush=True)
def meshes(jobs):
 for r,v in jobs:
  k=r['key'];wd=ROOT/'meshes'/k/v;pre=k+'_'+v
  if (wd/'merged.json').exists():continue
  if not (wd/'inputs/binding.json').exists():run(['prep',k,v],pre+'_prep')
  if not (wd/'plan/plan.json').exists():run(['plan',k,v],pre+'_plan')
  for t in json.loads((wd/'plan/layout.json').read_text())['tiles']:
   if not (wd/f'tiles/tile{t["k"]}.json').exists():run(['tile',k,v,str(t['k'])],pre+'_tile'+str(t['k']))
  run(['merge',k,v],pre+'_merge');dump(ROOT/'mesh_progress.json',dict(completed=len(list((ROOT/'meshes').glob('*/*/merged.json'))),expected=40,scientific_verdict=None))
def scores(jobs):
 for r,v in jobs:
  k=r['key']
  while not (ROOT/'meshes'/k/v/'merged.json').exists():time.sleep(5)
  for p in (['ALS','LoD2'] if r['family']=='image_only' else [r['prior']]):
   if not (ROOT/'scores'/k/v/p/'values.json').exists():run(['score',k,v,p],k+'_'+v+'_score_'+p)
  dump(ROOT/'score_progress.json',dict(completed=len(list((ROOT/'scores').glob('*/*/*/values.json'))),expected=45,scientific_verdict=None))
def main():
 cfg=json.loads((C/'screen_sim.json').read_text());lock=json.loads((C/'screen_sim_pipeline.lock.json').read_text());assert sha(__file__)==lock['script_sha256'];jobs=[(r,v) for r in cfg['states'] for v in ['before']+[x['key'] for x in cfg['candidates']]]
 handle=(PH/'main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/checks/tsdf.lock').open('r');fcntl.flock(handle,fcntl.LOCK_EX)
 with concurrent.futures.ThreadPoolExecutor(2) as executor:
  fs=[executor.submit(meshes,jobs),executor.submit(scores,jobs)]
  for f in concurrent.futures.as_completed(fs):f.result()
 assert len(list((ROOT/'meshes').glob('*/*/merged.json')))==40 and len(list((ROOT/'scores').glob('*/*/*/values.json')))==45
 dump(ROOT/'cpu_receipt.json',dict(status='PASS',meshes=40,score_partitions=45,mesh_parallel=1,completed_mesh_score_parallel=1,training=False,scientific_verdict=None))
if __name__=='__main__':main()
