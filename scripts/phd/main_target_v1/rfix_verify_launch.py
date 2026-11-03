"""Serialize endpoint verification after the large scoring job."""
import subprocess,time,fcntl
from r8_screen_prepare import *
root=O/'rfix_continue/endpoint'
while not (root/'cpu_receipt.json').exists():time.sleep(15)
handle=(PH/'main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/checks/tsdf.lock').open('r');fcntl.flock(handle,fcntl.LOCK_EX)
cmd=j(root/'execution/score.command.json');cmd[cmd.index('--name')+1]='jbgs-rfix-endpoint-verify';cmd[cmd.index('/repo/scripts/phd/main_target_v1/rfix_endpoint_mesh.py')]='/repo/scripts/phd/main_target_v1/rfix_endpoint_verify.py';cmd=cmd[:-1];dump(root/'execution/verify.command.json',cmd)
with (root/'execution/verify.log').open('x') as f:rc=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT).returncode
dump(root/'execution/verify.receipt.json',dict(exit_code=rc,scientific_verdict=None));assert rc==0
