"""One shared CPU admission; serial independent existing-snapshot reductions."""
import argparse
import subprocess
import sys
from common import *
p=argparse.ArgumentParser();p.add_argument('--replays',action='store_true');a=p.parse_args()
if a.replays:jobs=[('R1rep_b10',r) for r in ['fd_dynnow_ALS_s0','fd_current_ALS_s0','fd_current_ALS_s0_record_only']]
else:jobs=[(s,r) for s in SITES for r in RESULTS]
for site,result in jobs:
    subprocess.run([sys.executable,str(Path(__file__).with_name('formation_cpu.py')),'--site',site,'--result',result],check=True)
