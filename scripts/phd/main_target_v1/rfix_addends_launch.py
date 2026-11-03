"""Finite eight-state audit on the GPU separate from continuation."""
import sys,subprocess,fcntl,os,datetime
from r8_screen_prepare import *
def main():
 gpu=sys.argv[1];root=O/'rfix_addends';handle=(PH/'main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/checks'/f'photo_gpu_{gpu}.lock').open('r');fcntl.flock(handle,fcntl.LOCK_EX)
 active=subprocess.check_output(['nvidia-smi','-i',gpu,'--query-compute-apps=process_name','--format=csv,noheader'],text=True);assert all(not n.strip() or n.strip() in ['/usr/libexec/gnome-remote-desktop-daemon','/usr/lib/xorg/Xorg','/usr/share/rustdesk/rustdesk'] for n in active.splitlines()),'GPU_BUSY'
 for row in j(C/'rfix.json')['states']:
  key=row['key']
  if (root/key/'result.json').exists():
   assert j(root/key/'result.json')['status']=='PASS';continue
  cmd=j(O/'rfix/execution'/('gradient_'+key+'_command.json'));cmd[cmd.index('--name')+1]='jbgs-rfix-addends-'+key;cmd[cmd.index('--gpus')+1]='device='+gpu
  cmd[next(i for i,v in enumerate(cmd) if v in ['/repo/scripts/phd/main_target_v1/rfix_gradient.py','/repo/scripts/phd/main_target_v1/rfix_gradient_fast.py'])]='/repo/scripts/phd/main_target_v1/rfix_addends.py';dest=root/'execution';dest.mkdir(exist_ok=True);dump(dest/(key+'_command.json'),cmd)
  with (dest/(key+'.log')).open('x') as f:rc=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT).returncode
  dump(dest/(key+'_receipt.json'),dict(exit_code=rc,at=datetime.datetime.now().astimezone().isoformat(),scientific_verdict=None));print(key,rc,flush=True)
  if rc:raise SystemExit(rc)
if __name__=='__main__':main()
