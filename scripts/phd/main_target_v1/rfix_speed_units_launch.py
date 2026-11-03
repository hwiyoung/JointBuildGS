import sys,subprocess,fcntl
from r8_screen_prepare import *
gpu=sys.argv[1];handle=(PH/'main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/checks'/f'photo_gpu_{gpu}.lock').open('r');fcntl.flock(handle,fcntl.LOCK_EX)
for label in ['target','imageonly','geogs']:
 cmd=j(O/'rfix/execution'/('unit_'+label+'_command.json'));cmd[cmd.index('--name')+1]='jbgs-rfix-speed-unit-'+label;cmd[cmd.index('--gpus')+1]='device='+gpu;cmd[cmd.index('/repo/scripts/phd/main_target_v1/rfix_unit.py')]='/repo/scripts/phd/main_target_v1/rfix_speed_unit.py';dest=O/'rfix_speed/execution';dump(dest/('unit_r2_'+label+'_command.json'),cmd)
 with (dest/('unit_r2_'+label+'.log')).open('x') as f:rc=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT).returncode
 dump(dest/('unit_r2_'+label+'_receipt.json'),dict(exit_code=rc,scientific_verdict=None));assert rc==0
