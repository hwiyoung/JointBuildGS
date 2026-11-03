"""Finish candidate validation only after all full-array gradient checks succeed."""
import sys,time,subprocess
from r8_screen_prepare import *
keys=[r['key'] for r in j(C/'rfix.json')['states']]
while not all((O/'rfix_speed/gradients'/key/'result.json').exists() for key in keys):time.sleep(15)
assert all(j(O/'rfix_speed/gradients'/key/'result.json')['status']=='PASS' for key in keys)
subprocess.run([sys.executable,str(R/'scripts/phd/main_target_v1/rfix_speed_addends_prepare.py')],check=True)
subprocess.run([sys.executable,str(R/'scripts/phd/main_target_v1/rfix_ranking_audit.py'),'speed'],check=True)
subprocess.run([sys.executable,str(R/'scripts/phd/main_target_v1/rfix_speed_addends_launch.py'),'0'],check=True)
