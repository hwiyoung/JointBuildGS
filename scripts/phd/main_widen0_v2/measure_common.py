"""Task paths for the unchanged uncertainty definitions; all intermediates sealed."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import resource
import time
import numpy as np

OUT=Path('/out');CFG=json.loads(Path('/cfg/widen0_v2.json').read_text());D=CFG['definitions']
ROOT=OUT/'holdout/internal';WORK=ROOT/'work';PTS=ROOT/'points'
WORK.mkdir(parents=True,exist_ok=True);PTS.mkdir(parents=True,exist_ok=True)
TILES=json.loads((OUT/'inputs/tiles.json').read_text())
SITE_ID={t['id']:i for i,t in enumerate(TILES)}
SET_ID={'LoD2':0,'ALS':1};DATA_ID={'mvs_a':0,'als':2,'gt':3};R_ID={1.5:1}
CFG['seed']=CFG['split']['seed']

def patches(site,prior):return np.load(ROOT/'patch_geometry'/f'{site}_{prior}.npz')
def log(*a):print(*a,flush=True)
def now():return dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat()
def peak_gb():return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024**2
def _environment():
    # The worktree's .git points outside the read-only /repo mount. The host
    # records its HEAD inside the task payload after each task commit; exact
    # executing script hashes below remain authoritative for dirty-file changes.
    reference=OUT/'repository_head_at_pipeline_preparation.txt'
    commit=reference.read_text().strip() if reference.exists() else os.environ.get('WIDEN_COMMIT')
    return dict(image=os.environ.get('WIDEN_IMAGE_ID'),commit=commit,container_launch_commit=os.environ.get('WIDEN_COMMIT'),
        commit_reference=str(reference),
        captured_at=now(),config_sha256=hashlib.sha256(Path('/cfg/widen0_v2.json').read_bytes()).hexdigest(),
        task_script_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(__file__).parent.glob('*.py')},scientific_verdict=None)
ENVIRONMENT=_environment()
def env():return ENVIRONMENT
def jdump(p,obj):
    def conv(x):
        if isinstance(x,np.ndarray):return x.tolist()
        if isinstance(x,np.generic):return x.item()
        if isinstance(x,Path):return str(x)
        raise TypeError(type(x))
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(obj,ensure_ascii=False,indent=2,default=conv)+'\n')
class Timer:
    def __init__(self):self.t0=time.monotonic();self.marks={}
    def mark(self,k):self.marks[k]=time.monotonic()-self.t0;return self.marks[k]
