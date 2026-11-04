import datetime as dt
import hashlib,json,os,sys,time
from pathlib import Path
import numpy as np
C,D,O,R=Path('/repo/configs/phd/main_judgeapply_v1'),Path('/docs'),Path('/out/outside')/os.environ['FINALTRAIN_SITE'],Path('/repo')
PH=Path('/art/phase-payloads/phd')
TG=PH/'main_target_v1/PHD-MAIN-TARGET-v1'
UN=PH/'main_uncert_v1/PHD-MAIN-UNCERT-v1'
S0=PH/'main_stage0_v1/PHD-MAIN-STAGE0-v1'
S1=PH/'main_stage1_v1/PHD-MAIN-STAGE1-v1'
JC=PH/'main_judgecheck_v1/PHD-MAIN-JUDGECHECK-v1'
W=PH/'main_widen0_v2/PHD-MAIN-WIDEN0-v2'
HERE=Path(__file__).parent
def now():return dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat()
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(8<<20),b''):h.update(b)
    return h.hexdigest()
def dump(p,v):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def loadz(p,keys=None):
    with np.load(p,allow_pickle=False) as z:return {k:z[k] for k in (z.files if keys is None else keys)}
def savez(p,**v):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);np.savez_compressed(p,**v)
def cfg():
    assert sha(C/'judgeapply_v1.json')==json.loads((C/'judgeapply_v1.initial.lock.json').read_text())['config_sha256']
    return json.loads((C/'judgeapply_v1.json').read_text())
def progress(s):
    with (D/'progress.md').open('a') as f:f.write(f'- {now()}: {s}\n')
def issue(s):
    with (D/'issues.md').open('a') as f:f.write(f'- {now()}: {s}\n')
