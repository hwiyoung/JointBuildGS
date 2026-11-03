"""Separate immutable Docker commands; build uses CPU only, checks acquire GPU lease."""
import sys,os,fcntl,subprocess,datetime
from r8_screen_prepare import *
def main():
 mode,key,gpu=sys.argv[1:4];assert mode in ['build','measure','gradient','unit','addends_build','addends']
 root=O/'rfix_speed';cfg=j(C/'rfix.json');label=key if mode in ['build','unit'] else {'image_only':'imageonly','geogs':'geogs'}.get(next(r for r in cfg['states'] if r['key']==key)['family'],'target')
 template=O/'rfix/execution'/('build_'+label+'_command.json' if mode=='build' else 'gradient_'+key+'_command.json')
 cmd=j(template);cmd[cmd.index('--name')+1]='jbgs-rfix-speed-'+mode+'-'+key
 if mode not in ['build','addends_build']:
  handle=(PH/'main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/checks'/f'photo_gpu_{gpu}.lock').open('r');fcntl.flock(handle,fcntl.LOCK_EX)
  active=subprocess.check_output(['nvidia-smi','-i',gpu,'--query-compute-apps=process_name','--format=csv,noheader'],text=True);assert all(not n.strip() or n.strip() in ['/usr/libexec/gnome-remote-desktop-daemon','/usr/lib/xorg/Xorg','/usr/share/rustdesk/rustdesk'] for n in active.splitlines()),'GPU_BUSY'
  cmd[cmd.index('--gpus')+1]='device='+gpu
 old=next(v for v in cmd if v in ['/repo/scripts/phd/main_target_v1/rfix_build.py','/repo/scripts/phd/main_target_v1/rfix_gradient.py','/repo/scripts/phd/main_target_v1/rfix_gradient_fast.py']);cmd[cmd.index(old)]='/repo/scripts/phd/main_target_v1/rfix_speed_'+mode+'.py'
 dest=root/'execution';dest.mkdir(exist_ok=True);prefix=mode+'_'+key;dump(dest/(prefix+'_command.json'),cmd)
 with (dest/(prefix+'.log')).open('x') as f:rc=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT).returncode
 dump(dest/(prefix+'_receipt.json'),dict(at=datetime.datetime.now().astimezone().isoformat(),exit_code=rc,scientific_verdict=None));print(mode,key,rc,flush=True);raise SystemExit(rc)
if __name__=='__main__':main()
