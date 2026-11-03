import subprocess
from r8_screen_prepare import *
root=O/'rfix_speed/execution';cmd=j(O/'rfix/execution/build_target_command.json');cmd[cmd.index('--name')+1]='jbgs-rfix-speed-probe-build';cmd[cmd.index('/repo/scripts/phd/main_target_v1/rfix_build.py')]='/repo/scripts/phd/main_target_v1/rfix_speed_probe_build.py';dump(root/'probe_build_command.json',cmd)
with (root/'probe_build.log').open('x') as f:rc=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT).returncode
dump(root/'probe_build_receipt.json',dict(exit_code=rc,scientific_verdict=None));assert rc==0
