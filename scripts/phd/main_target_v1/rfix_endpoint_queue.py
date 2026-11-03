"""Finite authorized endpoint tasks; no automatic training retry."""
import sys,time,subprocess
from r8_screen_prepare import *
root=O/'rfix_continue';receipt=root/'runs/r8_LoD2_rfix/launch_receipt.json'
while not receipt.exists():time.sleep(10)
assert (root/'STOP_LoD2.json').exists() or (root/'TRAINING_COMPLETE.json').exists(),'No valid completed endpoint'
for script,args in [('rfix_endpoint_prepare.py',[]),('rfix_endpoint_launch.py',['1'])]:subprocess.run([sys.executable,str(R/'scripts/phd/main_target_v1'/script),*args],check=True)
# Renderer use is finished; speed validation may use the now-free GPU.
sp=subprocess.Popen([sys.executable,str(R/'scripts/phd/main_target_v1/rfix_speed_queue.py'),'1','1'])
subprocess.run([sys.executable,str(R/'scripts/phd/main_target_v1/rfix_endpoint_cpu.py')],check=True)
assert sp.wait()==0
print('ENDPOINT_QUEUE_COMPLETE',flush=True)
