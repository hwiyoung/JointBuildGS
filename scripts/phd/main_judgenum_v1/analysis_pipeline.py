import subprocess
import sys
from pathlib import Path
S=Path(__file__).parent
for script in ['verify_analysis.py','finish_setup.py','analyse.py']:
    subprocess.run([sys.executable,'-B','-u',str(S/script)],check=True)
