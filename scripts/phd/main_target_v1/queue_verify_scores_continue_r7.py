"""Validate each saved result after its companion figures; never starts training."""
import json,time,subprocess
from run_pilot_r7 import REPO,OUT,CFG

def main():
 c=json.loads((CFG/'scoring_continue_r7.r1.json').read_text());pending=[(r['key'],k) for r in c['rows'] for k in ['current','final'] if not (r['prior']=='ALS' and r['family']=='r7' and r['iteration']>7000)]
 while pending:
  for key,kind in pending.copy():
   root=OUT/'r7_continue/scoring'/key/kind
   if (root/'verification.json').exists():pending.remove((key,kind));continue
   if not (REPO/'docs/experiments/phd/main_target_v1/figures'/f'continue_r7_{key}_{kind}_clumps.json').exists():continue
   subprocess.run(['bash',str(REPO/'scripts/phd/main_target_v1/run_verify_scores_continue_r7.sh'),key,kind],check=True);pending.remove((key,kind))
  if pending:time.sleep(10)
 print('AVAILABLE_MESH_SCORES_ALL_VERIFIED',flush=True)
if __name__=='__main__':main()
