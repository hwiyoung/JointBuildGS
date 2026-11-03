"""One large CPU mesh/scoring job at a time; never starts training."""
import os,sys,json,time,fcntl,subprocess
from r8_screen_prepare import R,A,PH,O,C,dump,sha
ROOT=O/'rfix_continue/final_endpoint'
def run(args,logname):
 while int(next(l.split()[1] for l in open('/proc/meminfo') if l.startswith('MemAvailable:')))/1024**2<48:time.sleep(15)
 cmd=['docker','run','--rm','--read-only','--network','none','--runtime','runc','--name','jbgs-rfix-final-cpu','--user',f'{os.getuid()}:{os.getgid()}','--cpus','6','--memory','32g','--memory-swap','32g','--shm-size','1g']
 for e in ['PYTHONDONTWRITEBYTECODE=1','PYTHONUNBUFFERED=1','OMP_NUM_THREADS=6','OPENBLAS_NUM_THREADS=1','MKL_NUM_THREADS=1','CUDA_VISIBLE_DEVICES=','NVIDIA_VISIBLE_DEVICES=void','PYTHONPATH=/repo','TMPDIR=/target/tmp','NUMBA_CACHE_DIR=/target/tmp/numba','MPLCONFIGDIR=/target/tmp/mpl','TZ=Asia/Seoul']:cmd+=['-e',e]
 mounts=[(R,'/repo'),(A,'/art'),(PH,'/ph'),(C,'/cfg'),(PH/'main_stage1_v1/PHD-MAIN-STAGE1-v1','/out'),(PH/'main_stage0_v1/PHD-MAIN-STAGE0-v1','/s0'),(PH/'metrics_trial_v1/PHD-MAIN-METRICS-TRIAL-v1','/mt'),(PH/'metrics_fix_v1/PHD-MAIN-METRICS-FIX-v1','/mf'),(PH/'main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1','/dr'),(PH/'main_prep_measure_v1/PHD-MAIN-PREP-MEASURE-v1','/prep'),(PH/'main_stage1_diag_v1/PHD-MAIN-STAGE1-DIAG-v1','/diag')]
 for p,d in mounts:cmd+=['-v',f'{p}:{d}:ro']
 cmd+=['-v',f'{O}:/target:rw','--entrypoint','python','sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774','-B','-u','/repo/scripts/phd/main_target_v1/rfix_final_mesh.py']+args
 log=ROOT/'execution'/(logname+'.log');start=time.time();dump(log.with_suffix('.command.json'),cmd)
 with log.open('x') as f:rc=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT).returncode
 dump(log.with_suffix('.receipt.json'),dict(exit_code=rc,seconds=time.time()-start));assert rc==0,(args,rc,str(log));print('SIM_CPU',args,round(time.time()-start),flush=True)
def main():
 (ROOT/'execution').mkdir(exist_ok=True)
 handle=(PH/'main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/checks/tsdf.lock').open('r');fcntl.flock(handle,fcntl.LOCK_EX)
 wd=ROOT/'meshes/r8_LoD2_rfix/current'
 for step in ['prep','plan']:run([step],step)
 for tile in json.loads((wd/'plan/layout.json').read_text())['tiles']:run(['tile',str(tile['k'])],'tile'+str(tile['k']))
 for step in ['merge','score']:run([step],step)
 dump(ROOT/'cpu_receipt.json',dict(status='PASS',scientific_verdict=None))
if __name__=='__main__':main()
