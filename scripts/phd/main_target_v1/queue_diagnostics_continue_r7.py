"""Finite inference-only follow-up on requested 15k and 30k checkpoints."""
import sys,time,json,subprocess,os
from run_pilot_r7 import REPO,PH,OUT,CFG

def main():
 gpu,prior=sys.argv[1:3]
 # Let the read-only final-mesh render queue finish its five models first.
 last=OUT/'r7_continue/mesh_commands'/f'r7_{prior}_30000/receipt.json'
 while not last.exists():time.sleep(5)
 assert json.loads(last.read_text())['exit_code']==0
 for it in [15000,30000]:
  subprocess.run([sys.executable,str(REPO/'scripts/phd/main_target_v1/run_diagnostic_continue_r7.py'),gpu,'max_contributor_continue_r7.py',prior,str(it)],check=True)
  env=dict(os.environ,TARGET_LANE='continue_diag_'+prior,IMG='jointbuildgs:geogs-conf-guided-v1',MEM='8',CPUS='2')
  for script in ['origin_ratio_continue_r7.py','movement_continue_r7.py']:
   subprocess.run(['bash',str(REPO/'scripts/phd/main_target_v1/run_cpu.sh'),'cont-'+script.split('_')[0]+'-'+prior+'-'+str(it),script,prior,str(it)],env=env,check=True)
 subprocess.run(['bash',str(REPO/'scripts/phd/main_target_v1/run_cpu.sh'),'cont-state-'+prior,'verify_full_state_continue_r7.py',prior],env=env,check=True)
 print('CHECKPOINT_DIAGNOSTICS_DONE',prior,flush=True)
if __name__=='__main__':main()
