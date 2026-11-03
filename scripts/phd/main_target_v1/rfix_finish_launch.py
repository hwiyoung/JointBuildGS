"""One continuation, exclusive GPU after current read-only inference; no retry."""
import sys,fcntl,subprocess,time
from r8_screen_prepare import *
mode,gpu=sys.argv[1:3];assert mode in ['unit','train'];root=O/'rfix_continue/attempt2';cfg=j(C/'rfix_finish.json');old=j(O/'rfix_continue/runs/r8_LoD2_rfix/command.json');cut=old.index('/repo/scripts/phd/main_target_v1/rfix_continue_entry.py');cmd=old[:cut];args=old[cut+1:]
cmd[cmd.index('--name')+1]='jbgs-rfix-finish-'+mode
if mode=='unit':
 i=cmd.index('--gpus');cmd[i:i+2]=['--runtime','runc'];cmd+=['/repo/scripts/phd/main_target_v1/rfix_finish_unit.py'];dest=root/'execution';dest.mkdir(exist_ok=True)
else:
 handle=(PH/'main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/checks'/f'photo_gpu_{gpu}.lock').open('r');fcntl.flock(handle,fcntl.LOCK_EX)
 active=subprocess.check_output(['nvidia-smi','-i',gpu,'--query-compute-apps=process_name','--format=csv,noheader'],text=True);assert all(not n.strip() or n.strip() in ['/usr/libexec/gnome-remote-desktop-daemon','/usr/lib/xorg/Xorg','/usr/share/rustdesk/rustdesk'] for n in active.splitlines()),'GPU_BUSY'
 cmd[cmd.index('--gpus')+1]='device='+gpu;args[args.index('-m')+1]=cfg['model'];args[args.index('--jbgs_resume_full')+1]=cfg['checkpoint']
 for flag,key in [('--save_iterations','save_iterations'),('--jbgs_capture_iterations','capture_iterations')]:
  i=args.index(flag)+1;k=i
  while k<len(args) and not args[k].startswith('-'):k+=1
  args[i:k]=list(map(str,cfg[key]))
 cmd+=['/repo/scripts/phd/main_target_v1/rfix_finish_entry.py']+args;dest=root/'runs/r8_LoD2_rfix';dest.mkdir(parents=True,exist_ok=False)
dump(dest/(mode+'_command.json'),cmd);start=time.time()
with (dest/(mode+'.log')).open('x') as f:rc=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT).returncode
dump(dest/(mode+'_receipt.json'),dict(exit_code=rc,seconds=time.time()-start,automatic_retry=False,scientific_verdict=None));print('FINISH',mode,rc,flush=True);raise SystemExit(rc)
