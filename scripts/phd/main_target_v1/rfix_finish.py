"""Finish the locked read-only handover after all eight existing workers finish."""
import os,sys,time,subprocess
from pathlib import Path
from r8_screen_prepare import R,O,C,j,sha,dump
ROOT=O/'rfix'
def main():
 cfg=j(C/'rfix.json');keys=[r['key'] for r in cfg['states']];previous=None
 while True:
  done=[k for k in keys if (ROOT/'states'/k/'result.json').exists() and (ROOT/'gradients'/k/'result.json').exists()]
  if done!=previous:print('READY_STATES',done,flush=True);previous=done
  if len(done)==8:break
  time.sleep(10)
 env=os.environ.copy();env.update(TARGET_LANE='rfix_finish',IMG='sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774',MEM='24',CPUS='4')
 scripts=R/'scripts/phd/main_target_v1';stages=['rfix_tables_r2.py','rfix_evidence.py','rfix_load_tables.py','rfix_report.py','rfix_report_sass.py','rfix_validate_r2.py']
 for stage in stages:
  name=stage.removesuffix('.py');log=ROOT/'execution'/('finish_'+name+'.log');assert not log.exists()
  with log.open('x') as f:rc=subprocess.run(['bash',str(scripts/'run_cpu.sh'),name,stage],cwd=R,env=env,stdout=f,stderr=subprocess.STDOUT).returncode
  print('FINISH_STAGE',stage,rc,flush=True)
  if rc:raise SystemExit(rc)
 with (ROOT/'execution/finish_handover.log').open('x') as f:rc=subprocess.run([sys.executable,str(scripts/'rfix_handover.py')],cwd=R,stdout=f,stderr=subprocess.STDOUT).returncode
 print('HANDOVER',rc,flush=True);raise SystemExit(rc)
if __name__=='__main__':main()
