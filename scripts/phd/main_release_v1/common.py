"""RELEASE scope; inherited RESCORE modules resolve their input constants here."""
import csv, datetime as dt, hashlib, json, os, time
from pathlib import Path
import numpy as np
R,C,D,O=map(Path,['/repo','/cfg','/docs','/release'])
PH=Path('/art/phase-payloads/phd'); TG=PH/'main_target_v1/PHD-MAIN-TARGET-v1'
JA=PH/'main_judgeapply_v1/PHD-MAIN-JUDGEAPPLY-v1'; S0=PH/'main_stage0_v1/PHD-MAIN-STAGE0-v1'; S1=PH/'main_stage1_v1/PHD-MAIN-STAGE1-v1'
FT=PH/'main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1'; BASE=Path('/out'); CELLS=BASE/'cells_v2'
SITES=['B173nb_b10','B0_b10','R1rep_b10']; LABELS=dict(zip(SITES,['B173 주변','B0','R1']))
def now():return dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat()
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(8<<20),b''):h.update(b)
    return h.hexdigest()
def dump(p,v):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def loadz(p,keys=None):
    with np.load(p,allow_pickle=False) as z:return {k:z[k] for k in (z.files if keys is None else keys)}
def savez(p,**v):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);np.savez_compressed(p,**v)
def cfg():
    assert sha(C/'release_v1.json')==json.loads((C/'release_v1.initial.lock.json').read_text())['config_sha256']
    return json.loads((C/'release_v1.json').read_text())
def progress(s):
    with (D/'progress.md').open('a') as f:f.write(f'- {now()}: {s}\n')
def issue(s):
    with (D/'issues.md').open('a') as f:f.write(f'- {now()}: {s}\n')
def table(name,rows,csv_only=False):
    p=D/'tables'/name;p.parent.mkdir(parents=True,exist_ok=True)
    keys=list(dict.fromkeys(k for r in rows for k in r))
    with p.with_suffix('.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=keys,lineterminator='\n');w.writeheader();w.writerows(rows)
    if not csv_only:dump(p.with_suffix('.json'),dict(rows=rows,scientific_verdict=None))
def timing(stage,start,**extra):
    d=dict(at=now(),stage=stage,seconds=time.monotonic()-start,scientific_verdict=None,**extra);dump(O/'timing'/f'{stage}.json',d);return d
def score_root(site):return BASE/('addendum3_stage1' if site=='B173nb_b10' else 'addendum3_stage2')
def score_dir(site,prior,family):return score_root(site)/'scores'/f'{site}__{prior}__{family}'
