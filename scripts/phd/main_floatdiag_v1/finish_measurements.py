"""Host stdlib dependency orchestration, all measurements remain in Docker."""
import json
import subprocess
import sys
import time
from pathlib import Path
repo=Path(__file__).resolve().parents[3]
out=repo.parent/'JointBuildGS-artifacts/phase-payloads/phd/main_floatdiag_v1/PHD-MAIN-FLOATDIAG-v1'
receipt=out/'runs/R1rep_b10/fd_current_ALS_s0_record_only/receipt.json'
last=out/'formation/R1rep_b10/fd_current_ALS_s0_record_only/iteration_7000/receipt.json'
while not receipt.exists():time.sleep(5)
assert json.loads(receipt.read_text())['status']=='PASS','retry stopped; report original reason, do not restart'
while not last.exists():time.sleep(5)
jobs=[('replay-results','check_replay_results.py',[]),
      ('formation-record-reduce','formation_cpu.py',['--site','R1rep_b10','--result','fd_current_ALS_s0_record_only']),
      ('formation-distances','formation_residuals.py',[]),
      ('formation-figures','formation_figures.py',[]),
      ('formation-population-figures','formation_population_figures.py',[]),
      ('final-tables-report','final_tables_report.py',[])]
for tag,script,args in jobs:
    print('dependency ready:',tag,flush=True)
    subprocess.run([sys.executable,str(Path(__file__).with_name('launch.py')),'cpu',tag,script,*args],check=True,cwd=repo)
print('final measurement/report pipeline complete',flush=True)
