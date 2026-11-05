import ast,csv,gc,hashlib,json,os,sys,time,zipfile
from pathlib import Path
import numpy as np
from preflight import C,D,O,R,PH,now,sha,dump
W=PH/'main_widen0_v2/PHD-MAIN-WIDEN0-v2'
G=PH/'main_gtjudge_v1/PHD-MAIN-GTJUDGE-v1'
JA=PH/'main_judgeapply_v1/PHD-MAIN-JUDGEAPPLY-v1'
S0=PH/'main_stage0_v1/PHD-MAIN-STAGE0-v1'
S1=PH/'main_stage1_v1/PHD-MAIN-STAGE1-v1'
FT=PH/'main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1'
DR=PH/'main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1'
JC=PH/'main_judgecheck_v1/PHD-MAIN-JUDGECHECK-v1'
RAW=PH.parent/'p0-audit/data'
SHIFT=np.array([690953.,5336071.,604.])
def cfg():
    assert sha(C/'realbldg_v1.json')==json.loads((C/'realbldg_v1.initial.lock.json').read_text())['config_sha256']
    return json.loads((C/'realbldg_v1.json').read_text())
def loadz(p,keys=None):
    with np.load(p,allow_pickle=False) as z:return {k:z[k] for k in (z.files if keys is None else keys)}
def savez(p,**kw):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);np.savez_compressed(p,**kw)
def inherit(path,names,scope):
    nodes=[x for x in ast.parse(Path(path).read_text()).body if isinstance(x,(ast.FunctionDef,ast.ClassDef)) and x.name in names]
    assert {x.name for x in nodes}==set(names)
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),scope)
    return {n:scope[n] for n in names}
def issue(s):
    with (D/'issues.md').open('a') as f:f.write('- '+now()+': '+s+'\n')
def first_calculation():
    cfg()
    p=O/'first_calculation.json'
    if not p.exists():dump(p,dict(at=now(),config_sha256=sha(C/'realbldg_v1.json'),lock_sha256=sha(C/'realbldg_v1.initial.lock.json'),scientific_verdict=None))
def source(p):return dict(path=str(p),sha256=sha(p))
def table(name,rows):
    p=D/'tables'/name;p.parent.mkdir(parents=True,exist_ok=True)
    fields=list(dict.fromkeys(k for r in rows for k in r))
    with p.with_suffix('.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,lineterminator='\n');w.writeheader();w.writerows(rows)
