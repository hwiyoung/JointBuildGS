"""Task-local paths and serialization; inherited payloads are read-only."""
import datetime as dt
import hashlib
import json
import os
import resource
from pathlib import Path
import numpy as np

O=Path('/out'); D=Path('/docs'); C=Path('/cfg'); S=Path(__file__).parent
W=Path('/art/phase-payloads/phd/main_widen0_v2/PHD-MAIN-WIDEN0-v2')
RAW=Path('/art/phase-payloads/p0-audit/data')
DENSE=RAW/'work/mvs/colmap_dense'
CAL=RAW/'work/mvs/colmap_input_db_ids'
EXAMPLES=['DEBY_LOD2_'+x for x in ['4959326','4906975','60042','4907519','4906993','4906968']]
LABELS=['지지','반박','모름(애매)','모름(무늬 없음)','모름(사진 부족)']
def now(): return dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat()
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(4<<20),b''): h.update(b)
    return h.hexdigest()
def clean(x):
    if isinstance(x,dict): return {str(k):clean(v) for k,v in x.items()}
    if isinstance(x,(tuple,list)): return [clean(v) for v in x]
    if isinstance(x,np.ndarray): return clean(x.tolist())
    if isinstance(x,np.generic): return clean(x.item())
    if isinstance(x,Path): return str(x)
    if isinstance(x,float) and not np.isfinite(x): return None
    return x
def dump(p,x):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(clean(x),ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def load(p): return json.loads(Path(p).read_text())
def npz(p):
    with np.load(p,allow_pickle=False) as z: return {k:z[k] for k in z.files}
def env(): return dict(at=now(),commit=os.environ.get('PHOTOCHECK_COMMIT'),image=os.environ.get('PHOTOCHECK_IMAGE'),scripts_sha256={p.name:sha(p) for p in S.glob('*.py')},peak_rss_gib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024**2,scientific_verdict=None)
def paths(sealed=False):
    base=O/'holdout' if sealed else O
    for sub in ['geometry','points','patches','work']: (base/sub).mkdir(parents=True,exist_ok=True)
    return base
def sigmas(d,prior):
    sm=np.sqrt(d['u_mvs'].astype(float)**2+.0275**2)
    if prior=='ALS': sp=np.sqrt(d['u_prior'].astype(float)**2+.0275**2)
    else:
        mapping={'1000':.166,'2100':.098,'3100':.223,'3200':.114,'3900':.238}
        sp=np.array([mapping.get(str(x),.11) for x in d['roof_type']]);sp[d['kind']==2]=.144
    return sp,sm
