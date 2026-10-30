import json
from pathlib import Path
import subprocess
import sys
from lock_config import dump,sha,stamp
S=Path(__file__).parent;C=Path('/cfg')
subprocess.run([sys.executable,'-B','-u',str(S/'verify_analysis.py')],check=True)
lock=C/'analysis_implementation.r2.lock.json'
assert not lock.exists(), 'Immutable implementation lock already exists'
dump(lock,{'at':stamp(),
  'reason':'Resume after stage A commit 52e91da1; cache building encoding and group labels without changing rules; export a in float64 cm',
  'stage_a_commit':'52e91da1',
  'previous_lock_sha256':sha(C/'analysis_implementation.r1.lock.json'),
  'config_sha256':sha(C/'judgenum_v1.json'),
  'sources':{p.name:sha(p) for p in [S/'analysis_core.py',S/'analyse.py',S/'verify_analysis.py']},
  'scientific_verdict':None})
subprocess.run([sys.executable,'-B','-u',str(S/'analyse.py')],check=True)
