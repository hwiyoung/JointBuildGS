"""Finite read-only rendering queue for the explicitly named twelve saved models."""
import sys,time,json,subprocess
from run_pilot_r7 import REPO,PH,OUT,CFG,stamp,dump
def main():
 gpu,prior=sys.argv[1:3];cfg=json.loads((CFG/'scoring_continue_r7.json').read_text());rows=[r for r in cfg['rows'] if r['prior']==prior and not r['existing_virtual']]
 for row in rows:
  key=row['key'];dest=OUT/'r7_continue/mesh_commands'/key
  if gpu=='0' and key=='r6_ALS_7000':
   while not (dest/'receipt.json').exists():time.sleep(5)
   assert json.loads((dest/'receipt.json').read_text())['exit_code']==0;continue
  source=Path(row['model'].replace('/ph',str(PH),1))/f"point_cloud/iteration_{row['iteration']}/point_cloud.ply"
  if row['iteration']>7000:
   source=Path(row['model'].replace('/ph',str(PH),1))/f"check{row['iteration']}/coverage.json"
  while not source.exists():
   if (OUT/'r7_continue/attempt2/STOP_BOTH.json').exists():raise RuntimeError('HEALTH_STOP_FUTURE_CHECKPOINT_UNAVAILABLE')
   time.sleep(5)
  subprocess.run([sys.executable,str(REPO/'scripts/phd/main_target_v1/run_render_final_continue_r7.py'),gpu,key],check=True)
 print('RENDER_QUEUE_COMPLETE',prior,flush=True)
if __name__=='__main__':
 from pathlib import Path
 main()
