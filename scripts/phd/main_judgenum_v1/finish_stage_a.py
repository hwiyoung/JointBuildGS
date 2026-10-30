import subprocess
import sys
from pathlib import Path
S=Path(__file__).parent;O=Path('/out')
old=O/'core_points_stage_a';archive=O/'core_points_stage_a_export_r0'
if old.exists() and not archive.exists():old.rename(archive)
for args in [['stage_a.py'],['figures.py','--stage-a'],['verify_stage_a.py']]:
    subprocess.run([sys.executable,'-B','-u',str(S/args[0]),*args[1:]],check=True)
