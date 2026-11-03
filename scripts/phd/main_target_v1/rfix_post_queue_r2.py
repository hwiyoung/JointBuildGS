"""Finite CPU-only documentation and validation for the two authorized endpoints."""
import os,sys,time,subprocess
from r8_screen_prepare import *
root=O/'rfix_continue'
def wait(p):
 while not p.exists():time.sleep(15)
def cpu(tag,script,*args,mem=12):
 env=os.environ.copy();env.update(IMG='sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774',MEM=str(mem),CPUS='4',TARGET_LANE='rfix_post')
 subprocess.run(['bash',str(R/'scripts/phd/main_target_v1/run_cpu.sh'),tag,script,*map(str,args)],env=env,check=True)
wait(root/'endpoint/verification.json');assert j(root/'endpoint/verification.json')['status'].startswith('PASS')
cpu('rfix-report15000','rfix_report15000.py')
wait(root/'attempt2/runs/r8_LoD2_rfix/train_receipt.json')
if not (root/'attempt2/TRAINING_COMPLETE.json').exists():raise SystemExit('Training stopped: root agent must report the preserved stop; no retry')
wait(root/'final_endpoint/gaussians.npz');wait(root/'final_endpoint/states/r8_LoD2_rfix/current/result.json')
cpu('rfix-released30000','rfix_released.py',30000)
wait(root/'final_endpoint/verification.json');assert j(root/'final_endpoint/verification.json')['status'].startswith('PASS')
cpu('rfix-finalreport','rfix_final_report.py')
cpu('rfix-post15000-audit','rfix_post15000_audit.py',mem=24)
print('POST_QUEUE_COMPLETE',flush=True)
