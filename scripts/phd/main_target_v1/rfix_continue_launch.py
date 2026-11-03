"""Host orchestration; one attempt, existing exclusive GPU lease."""
import os,sys,fcntl,subprocess,time
from r8_screen_prepare import *
def main():
 gpu=sys.argv[1];assert gpu in ['0','1'];root=O/'rfix_continue';cfg=j(C/'rfix_continue.json')
 handle=(PH/'main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/checks'/f'photo_gpu_{gpu}.lock').open('r');fcntl.flock(handle,fcntl.LOCK_EX)
 active=subprocess.check_output(['nvidia-smi','-i',gpu,'--query-compute-apps=process_name','--format=csv,noheader'],text=True)
 assert all(not x.strip() or x.strip() in ['/usr/libexec/gnome-remote-desktop-daemon','/usr/lib/xorg/Xorg','/usr/share/rustdesk/rustdesk'] for x in active.splitlines()),'GPU_BUSY'
 old=j(O/'r8/runs/tg_B173nb_b10_LoD2_s0_r8/command.json');cut=old.index('/repo/scripts/phd/main_target_v1/train_entry_r8.py');cmd=old[:cut];args=old[cut+3:]
 cmd[cmd.index('--name')+1]='jbgs-target-r8-lod2-rfix';cmd[cmd.index('--gpus')+1]='device='+gpu
 cmd[cmd.index('jointbuildgs:geogs-conf-guided-v1')]='sha256:ff4eba02c450573e3258ec4946b9c536f32c213dde9abc83ee2969aaf18384be'
 args[args.index('-m')+1]=cfg['model']
 for flag,key in [('--save_iterations','save_iterations'),('--jbgs_capture_iterations','capture_iterations')]:
  i=args.index(flag)+1;k=i
  while k<len(args) and not args[k].startswith('-'):k+=1
  args[i:k]=list(map(str,cfg[key]))
 args+=['--jbgs_resume_full',cfg['checkpoint']];cmd+=['/repo/scripts/phd/main_target_v1/rfix_continue_entry.py']+args
 dest=root/'runs/r8_LoD2_rfix';dest.mkdir(parents=True,exist_ok=False);dump(dest/'command.json',cmd);start=time.time()
 with (dest/'run.log').open('x') as f:rc=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT).returncode
 dump(dest/'launch_receipt.json',dict(exit_code=rc,seconds=time.time()-start,automatic_retry=False,scientific_verdict=None));print('TRAIN_EXIT',rc,flush=True)
if __name__=='__main__':main()
