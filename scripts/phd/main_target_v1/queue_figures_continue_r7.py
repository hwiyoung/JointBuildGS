"""Render one figure set per available mesh result as the serial metrics finish."""
import json,time,subprocess,os
from run_pilot_r7 import REPO,PH,OUT,CFG

def main():
 c=json.loads((CFG/'scoring_continue_r7.json').read_text());rows=[r for r in c['rows'] if r['family']!='r7' or r['iteration']==7000];pending=[(r['key'],k) for r in rows for k in ['current','final']];env=dict(os.environ,TARGET_LANE='continue_figure_queue',IMG='jointbuildgs:geogs-conf-guided-v1',MEM='6',CPUS='2')
 while pending:
  did=False
  for key,kind in pending.copy():
   if not (OUT/'r7_continue/scoring'/key/kind/'values.json').exists():continue
   subprocess.run(['bash',str(REPO/'scripts/phd/main_target_v1/run_cpu.sh'),'fig-'+key+'-'+kind,'figures_continue_r7.py',key,kind],env=env,check=True);pending.remove((key,kind));did=True
  if not did:time.sleep(10)
 print('FIGURES_16_AVAILABLE_MESHES_COMPLETE',flush=True)
if __name__=='__main__':main()
