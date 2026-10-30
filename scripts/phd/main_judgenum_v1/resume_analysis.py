import json
from pathlib import Path
import subprocess
import sys
from lock_config import dump,sha,stamp
S=Path(__file__).parent;C=Path('/cfg')
subprocess.run([sys.executable,'-B','-u',str(S/'verify_analysis.py')],check=True)
dump(C/'analysis_implementation.r1.lock.json',{'at':stamp(),
  'reason':'Fix ndarray dictionary key in minimum_area; mathematical definition unchanged; spatial boundary checks added',
  'previous_lock_sha256':sha(C/'analysis_implementation.lock.json'),
  'config_sha256':sha(C/'judgenum_v1.json'),
  'sources':{p.name:sha(p) for p in [S/'analysis_core.py',S/'analyse.py',S/'verify_analysis.py']},
  'scientific_verdict':None})
subprocess.run([sys.executable,'-B','-u',str(S/'analyse.py')],check=True)
