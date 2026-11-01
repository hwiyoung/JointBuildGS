"""Host-only orchestrator: serialize CPU mesh work while both GPU pilots continue."""
import fcntl,json,os,subprocess,time
from pathlib import Path
from run_pilot_r6 import OUT,PH,REPO,stamp,dump,stop_both
S=REPO/'scripts/phd/main_target_v1';R=OUT/'r6'
def call(tag,args,mem='32',cpus='4'):
 env=dict(os.environ,TARGET_LANE='r6-mesh',IMG='jointbuildgs:geogs-conf-guided-v1',MEM=mem,CPUS=cpus)
 with (R/(tag+'_driver.log')).open('x') as f:rc=subprocess.run(['bash',str(S/'run_cpu.sh'),tag,*args],env=env,stdout=f,stderr=subprocess.STDOUT).returncode
 dump(R/(tag+'_receipt.json'),dict(at=stamp(),exit_code=rc,scientific_verdict=None))
 if rc:raise RuntimeError((tag,rc))
def main():
 for prior in ['ALS','LoD2']:call('reference-r6-'+prior,['post7000_r6.py','ref','B173nb_b10',prior])
 done=set()
 while len(done)<2:
  for prior in ['ALS','LoD2']:
   if prior in done:continue
   model=R/'runs'/f'tg_B173nb_b10_{prior}_s0_r6/model'
   if not all((model/p).exists() for p in ['check7000/coverage.json','jbgs_complete/iteration_7000/receipt.json','target_monitor/health_7000.json']):continue
   lock=(PH/'main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/checks/tsdf.lock').open('r');fcntl.flock(lock,fcntl.LOCK_EX)
   while int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))/1024**2<48:time.sleep(5)
   call('post7000-r6-'+prior,['post7000_r6.py','run','B173nb_b10',prior],'40','8');lock.close();done.add(prior)
   if (R/'STOP_BOTH.json').exists():stop_both('r6 geometry score stop')
  dump(R/'watch_status.json',dict(at=stamp(),post_done=sorted(done),scientific_verdict=None))
  if len(done)<2:
   stopped=(R/'STOP_BOTH.json').exists()
   finished=all((R/'runs'/f'tg_B173nb_b10_{p}_s0_r6/receipt.json').exists() for p in ['ALS','LoD2'])
   if stopped and finished:
    missing=[p for p in ['ALS','LoD2'] if p not in done and not (R/'runs'/f'tg_B173nb_b10_{p}_s0_r6/model/target_monitor/health_7000.json').exists()]
    if missing:dump(R/'watch_incomplete.json',dict(at=stamp(),missing_7000_health=missing,scientific_verdict=None));break
   time.sleep(5)
 print('R6_POST_DONE',sorted(done),flush=True)
if __name__=='__main__':main()
