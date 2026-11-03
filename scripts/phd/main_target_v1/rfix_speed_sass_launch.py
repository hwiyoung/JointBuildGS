import subprocess
from r8_screen_prepare import *
for label in ['target','imageonly','geogs']:
 cmd=j(O/'rfix/execution'/('build_'+label+'_command.json'));cmd[cmd.index('--name')+1]='jbgs-rfix-speed-sass-'+label;cmd[cmd.index('/repo/scripts/phd/main_target_v1/rfix_build.py')]='/repo/scripts/phd/main_target_v1/rfix_speed_sass.py';root=O/'rfix_speed/execution';dump(root/('sass_'+label+'_command.json'),cmd)
 with (root/('sass_'+label+'.log')).open('x') as f:rc=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT).returncode
 dump(root/('sass_'+label+'_receipt.json'),dict(exit_code=rc,scientific_verdict=None));assert rc==0
