"""Finite saved-state checks after the original addend queue releases GPU0."""
import sys,os,fcntl,subprocess,datetime
from r8_screen_prepare import *
root=O/'rfix_speed/rank_refinement';dest=root/'execution';dest.mkdir(exist_ok=True)
env=os.environ.copy();env.update(IMG='sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774',MEM='4',CPUS='4',TARGET_LANE='rfix_post')
subprocess.run(['bash',str(R/'scripts/phd/main_target_v1/run_cpu.sh'),'rfix-rank-unit','rfix_speed_rank_full.py','--unit'],env=env,check=True)
handle=(PH/'main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/checks/photo_gpu_0.lock').open('r');fcntl.flock(handle,fcntl.LOCK_EX)
active=subprocess.check_output(['nvidia-smi','-i','0','--query-compute-apps=process_name','--format=csv,noheader'],text=True);assert all(not n.strip() or n.strip() in ['/usr/libexec/gnome-remote-desktop-daemon','/usr/lib/xorg/Xorg','/usr/share/rustdesk/rustdesk'] for n in active.splitlines()),'GPU_BUSY'
for key in j(C/'rfix_speed_rank_full.json')['states']:
 cmd=j(O/'rfix/execution'/('gradient_'+key+'_command.json'));cmd[cmd.index('--name')+1]='jbgs-rfix-rank-'+key;cmd[cmd.index('--gpus')+1]='device=0'
 old=next(v for v in cmd if v in ['/repo/scripts/phd/main_target_v1/rfix_gradient.py','/repo/scripts/phd/main_target_v1/rfix_gradient_fast.py']);cmd[cmd.index(old)]='/repo/scripts/phd/main_target_v1/rfix_speed_rank_full.py'
 dump(dest/(key+'_command.json'),cmd)
 with (dest/(key+'.log')).open('x') as f:rc=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT).returncode
 dump(dest/(key+'_receipt.json'),dict(exit_code=rc,at=datetime.datetime.now().astimezone().isoformat(),scientific_verdict=None));assert rc==0
print('FULL_RANK_GRADIENTS_COMPLETE',flush=True)
