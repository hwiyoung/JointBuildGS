"""Continue after the committed intermediate report and completed development calibration."""
import subprocess
import sys
from pathlib import Path
from lock_config import dump,sha,stamp
S=Path(__file__).parent;C=Path('/cfg');O=Path('/out')
assert (O/'analysis_complete.json').exists()
assert (O/'spacing_repair_complete.json').exists(), 'Verify distinct photo-task grouping before sealed holdout'
lock=C/'figures_holdout_implementation.lock.json'
assert not lock.exists()
dump(lock,{'at':stamp(),'stage_a_commit':'52e91da1','before_holdout':True,
  'config_sha256':sha(C/'judgenum_v1.json'),'calibration_sha256':sha(O/'calibration.json'),
  'sources':{p.name:sha(p) for p in [S/'holdout.py',S/'figures.py',S/'metric_figures.py',S/'montage.py']},
  'montage_rule_detail':'Largest summed front-facing projected patch-support area among 819 TRAIN cameras; complete component fits image; source tangent 3m crop margin; no new visibility or photo score',
  'scientific_verdict':None})
for name in ['holdout.py','metric_figures.py','figures.py','montage.py']:
    print('START',name,flush=True)
    subprocess.run([sys.executable,'-B','-u',str(S/name)],check=True)
print('MEASUREMENTS_AND_FIGURES_COMPLETE',flush=True)
