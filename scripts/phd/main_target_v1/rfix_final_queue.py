"""Read-only final endpoint after the single authorized continuation ends."""
import sys,time,subprocess
from r8_screen_prepare import *
root=O/'rfix_continue/attempt2'
while not (root/'runs/r8_LoD2_rfix/train_receipt.json').exists():time.sleep(15)
assert (root/'STOP_LoD2.json').exists() or (root/'TRAINING_COMPLETE.json').exists(),'No restorable endpoint'
for script,args in [('rfix_final_prepare.py',[]),('rfix_final_launch.py',['1']),('rfix_final_cpu.py',[]),('rfix_final_verify_launch.py',[])]:
 subprocess.run([sys.executable,str(R/'scripts/phd/main_target_v1'/script),*args],check=True)
print('FINAL_ENDPOINT_COMPLETE',flush=True)
