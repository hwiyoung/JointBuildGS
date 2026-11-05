"""Small RELEASE-compatible bindings; all new outputs stay in RECOUNT."""
import csv, datetime as dt, hashlib, json, os, time, sys, ast
from pathlib import Path
import numpy as np
R,C,D,O=map(Path,['/repo','/cfg','/docs','/recount'])
PH=Path('/art/phase-payloads/phd'); FT=PH/'main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1'
JA=PH/'main_judgeapply_v1/PHD-MAIN-JUDGEAPPLY-v1'; S1=PH/'main_stage1_v1/PHD-MAIN-STAGE1-v1'
RELEASE=Path('/release'); BASE=Path('/out')
SITES=['B173nb_b10','B0_b10','R1rep_b10']; PRIORS=['ALS','LoD2']
LABELS=dict(zip(SITES,['B173 주변','B0','R1']))
CASES={0:'둘 다 맞음',1:'영상만 맞음',2:'사전 정보만 맞음',4:'영상 없음',3:'둘 다 틀림',-1:'사전 정보 면 없음(별도)'}
REGIONS={0:'일치',1:'보존',2:'보정',4:'결측',3:'보정(빈 공간)',9:'미판정'}
EXPECTED={0:0,1:2,2:1,4:4}
METHODS=['prior','mvs','fusion','baseline_30000','GeoGS_30000','2DGS_30000','CDGS_30000','judgment_mesh','FINALTRAIN_30000']
NAMES=dict(zip(METHODS,['사전 정보','MVS','결합','기준선 30,000회','GeoGS','2DGS','CDGS','판단으로 조합한 메시','본 방법']))
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
    assert sha(C/'recount_v1.json')==json.loads((C/'recount_v1.initial.lock.json').read_text())['config_sha256']
    return json.loads((C/'recount_v1.json').read_text())
def issue(s):
    with (D/'issues.md').open('a') as f:f.write(f'- {now()}: {s}\n')
def table(name,rows):
    p=D/'tables'/name;p.parent.mkdir(parents=True,exist_ok=True)
    keys=list(dict.fromkeys(k for r in rows for k in r))
    with p.with_suffix('.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=keys,lineterminator='\n');w.writeheader();w.writerows(rows)
    dump(p.with_suffix('.json'),dict(rows=rows,scientific_verdict=None))
def readcsv(p):
    with Path(p).open() as f:return list(csv.DictReader(f))
def score_dir(site,prior,method):
    return BASE/('addendum3_stage1' if site=='B173nb_b10' else 'addendum3_stage2')/'scores'/f'{site}__{prior}__{method}'
def cells_path(site,prior):return RELEASE/'stage0'/f'{site}__{prior}'/'cells.npz'
def pct(a,b):return 100*int(a)/int(b) if b else None
def source_functions(path,names,scope):
    """Reuse exact inherited functions without running their module entrypoints."""
    tree=ast.parse(Path(path).read_text());nodes=[x for x in tree.body if isinstance(x,(ast.FunctionDef,ast.ClassDef)) and x.name in names]
    assert {x.name for x in nodes}==set(names)
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),scope)
    return {name:scope[name] for name in names}
