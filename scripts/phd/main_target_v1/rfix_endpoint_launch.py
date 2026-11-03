"""Read-only endpoint render after the live process has exited."""
import sys,os,fcntl,subprocess,time
from r8_screen_prepare import *
gpu=sys.argv[1];root=O/'rfix_continue/endpoint';handle=(PH/'main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/checks'/f'photo_gpu_{gpu}.lock').open('r');fcntl.flock(handle,fcntl.LOCK_EX)
active=subprocess.check_output(['nvidia-smi','-i',gpu,'--query-compute-apps=process_name','--format=csv,noheader'],text=True);assert all(not n.strip() or n.strip() in ['/usr/libexec/gnome-remote-desktop-daemon','/usr/lib/xorg/Xorg','/usr/share/rustdesk/rustdesk'] for n in active.splitlines()),'GPU_BUSY'
cmd=j(O/'rfix/execution/gradient_r8_LoD2_stop_command.json');cmd[cmd.index('--name')+1]='jbgs-rfix-endpoint-render';cmd[cmd.index('--gpus')+1]='device='+gpu
old=next(v for v in cmd if v in ['/repo/scripts/phd/main_target_v1/rfix_gradient.py','/repo/scripts/phd/main_target_v1/rfix_gradient_fast.py']);cmd[cmd.index(old)]='/repo/scripts/phd/main_target_v1/rfix_endpoint_render.py';(root/'execution').mkdir(exist_ok=True);dump(root/'execution/render_command.json',cmd)
with (root/'execution/render.log').open('x') as f:rc=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT).returncode
dump(root/'execution/render_receipt.json',dict(exit_code=rc,scientific_verdict=None));assert rc==0
