"""Host continuation; keep the original stopped runs and frozen r21 code intact."""
import fcntl,hashlib,json,os,subprocess,sys,time
from run_pilot_r7 import REPO,PH,OUT,CFG,stamp,dump
R=OUT/'r7_continue/lod2_retry'
def stop_both(reason):
 try:
  with (R/'STOP_LoD2.json').open('x') as f:json.dump(dict(at=stamp(),reason=reason,scientific_verdict=None),f,ensure_ascii=False,indent=2)
 except FileExistsError:pass
 active=subprocess.check_output(['docker','ps','--format','{{.Names}}'],text=True).splitlines()
 for p in ['LoD2']:
  n='jbgs-target-continue-r7lod2-'+p
  if n in active:subprocess.run(['docker','stop','--time','10',n],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
def main():
 gpu,prior=sys.argv[1:3];assert (gpu,prior) in [('1','LoD2')]
 lock=(PH/'main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/checks'/f'photo_gpu_{gpu}.lock').open('r');fcntl.flock(lock,fcntl.LOCK_EX)
 assert not (R/'STOP_LoD2.json').exists()
 active=subprocess.check_output(['nvidia-smi','-i',gpu,'--query-compute-apps=process_name','--format=csv,noheader'],text=True)
 assert all(not x.strip() or x.strip() in ['/usr/libexec/gnome-remote-desktop-daemon','/usr/lib/xorg/Xorg'] for x in active.splitlines()),'GPU_BUSY'
 c=json.loads((CFG/'continue_r7.lod2_r2.json').read_text());row=c['runs'][prior];root=R/'runs'/row['name'];root.mkdir(parents=True,exist_ok=False)
 cmd=json.loads((OUT/'r7/runs'/row['name']/'command.json').read_text());cmd[cmd.index('--name')+1]='jbgs-target-continue-r7lod2-'+prior
 cmd[cmd.index('/repo/scripts/phd/main_target_v1/train_entry_r7.py')]='/repo/scripts/phd/main_target_v1/train_entry_continue_r7_lod2.py'
 cmd[cmd.index('-m')+1]='/out/r7_continue/lod2_retry/runs/'+row['name']+'/model'
 cmd+=['--jbgs_resume_full','/out/r7/runs/'+row['name']+'/model/jbgs_complete/iteration_7000/checkpoint.pth']
 assert subprocess.check_output(['docker','image','inspect','-f','{{.Id}}','jointbuildgs:geogs-conf-guided-v1'],text=True).strip()==c['image_id']
 dump(root/'command.json',cmd);dump(root/'launch.json',dict(at=stamp(),gpu=gpu,checkpoint_sha256=row['checkpoint_sha256'],config_sha256=hashlib.sha256((CFG/'continue_r7.lod2_r2.json').read_bytes()).hexdigest(),scientific_verdict=None))
 start=time.time()
 with (root/'train.log').open('x') as f:
  proc=subprocess.Popen(cmd,stdout=f,stderr=subprocess.STDOUT)
  while proc.poll() is None:
   p=root/'model/target_monitor/STOP.json'
   if p.exists():stop_both(dict(prior=prior,health=json.loads(p.read_text())))
   if (R/'STOP_LoD2.json').exists():stop_both('existing continuation health/execution stop')
   time.sleep(2)
  rc=proc.returncode
 if rc:stop_both(dict(prior=prior,execution_exit_code=rc))
 dump(root/'receipt.json',dict(at=stamp(),exit_code=rc,seconds=time.time()-start,status='TRAINING_COMPLETE_30000' if rc==0 else 'STOPPED',automatic_retry=False,scientific_verdict=None));print(prior,rc,flush=True);raise SystemExit(rc)
if __name__=='__main__':main()
