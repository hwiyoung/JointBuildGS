"""Complete authorized diagnostics after both pilot meshes are ready; no training."""
import fcntl,json,os,subprocess,time
from pathlib import Path
from run_pilot_r6 import OUT,PH,REPO,stamp,dump
S=REPO/'scripts/phd/main_target_v1';R=OUT/'r6'
def call(tag,args,mem='8',image='jointbuildgs:geogs-conf-guided-v1'):
 env=dict(os.environ,TARGET_LANE='r6-finish',IMG=image,MEM=mem,CPUS='4')
 with (R/(tag+'_driver.log')).open('x') as f:rc=subprocess.run(['bash',str(S/'run_cpu.sh'),tag,*args],env=env,stdout=f,stderr=subprocess.STDOUT).returncode
 dump(R/(tag+'_receipt.json'),dict(at=stamp(),exit_code=rc,scientific_verdict=None))
 if rc:raise RuntimeError((tag,rc))
def main():
 while not all((R/f'post7000-r6-{p}_receipt.json').exists() for p in ['ALS','LoD2']):time.sleep(5)
 for p in ['ALS','LoD2']:assert json.loads((R/f'post7000-r6-{p}_receipt.json').read_text())['exit_code']==0
 lock=(PH/'main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/checks/tsdf.lock').open('r');fcntl.flock(lock,fcntl.LOCK_EX)
 for prior in ['ALS','LoD2']:call('verify-post-r6-'+prior,['verify_post7000_r6.py',prior],'32')
 lock.close()
 while not all((R/'movement'/p/'summary.json').exists() for p in ['ALS','LoD2']):time.sleep(5)
 call('sections-r6',['report_section7000_r6.py'],'8')
 call('report-r6',['report_r6.py'],'12')
 call('main-report-r6',['update_main_r6.py'],'3')
 print('R6_REPORTS_AND_VERIFICATION_DONE',flush=True)
if __name__=='__main__':main()
