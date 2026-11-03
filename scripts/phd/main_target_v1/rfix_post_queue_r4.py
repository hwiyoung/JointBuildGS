"""Finish report and independent full-state audit after verified endpoint-row binding."""
import os,sys,time,subprocess
from r8_screen_prepare import *
root=O/'rfix_continue'
def wait(p):
 while not p.exists():time.sleep(15)
def cpu(tag,script,mem=12):
 env=os.environ.copy();env.update(IMG='sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774',MEM=str(mem),CPUS='4',TARGET_LANE='rfix_post')
 subprocess.run(['bash',str(R/'scripts/phd/main_target_v1/run_cpu.sh'),tag,script],env=env,check=True)
wait(root/'released/30000_r2/result.json');assert j(root/'released/30000_r2/result.json')['status']=='PASS'
wait(root/'final_endpoint/verification.json');assert j(root/'final_endpoint/verification.json')['status'].startswith('PASS')
cpu('rfix-finalreport','rfix_final_report.py')
cpu('rfix-post15000-audit','rfix_post15000_audit.py',24)
print('POST_QUEUE_COMPLETE',flush=True)
