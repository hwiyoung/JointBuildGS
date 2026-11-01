"""Regionview paths, exact input receipts and bounded output writes."""
import csv
import datetime as dt
import hashlib
import json
import os
import sys
from pathlib import Path
import numpy as np

REPO, OUT, CFG, DOC = map(Path, ['/repo', '/out', '/cfg', '/docs'])
PH = Path('/art/phase-payloads/phd')
TG = PH/'main_target_v1/PHD-MAIN-TARGET-v1'
S0 = PH/'main_stage0_v1/PHD-MAIN-STAGE0-v1'
S1 = PH/'main_stage1_v1/PHD-MAIN-STAGE1-v1'
JN = PH/'main_judgenum_v1/PHD-MAIN-JUDGENUM-v1'
W = PH/'main_widen0_v2/PHD-MAIN-WIDEN0-v2'
DR = PH/'main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1'
SITES = {'B0_b10':'B0', 'B173nb_b10':'B173 주변', 'B173_b0':'B173만', 'R1rep_b10':'R1'}
ALIASES = {'DEBY_LOD2_4959326':'B173', 'DEBY_LOD2_4959323':'B0', 'DEBY_LOD2_4906968':'R1'}
REV = sys.argv[1] if len(sys.argv)>1 and sys.argv[1] in ['r2','r7'] else 'r2'
LABELS = {-1:'셀 수 없음', 0:'관측 없음', 1:'일치', 2:'보존', 3:'보정', 5:'사라짐'}
NAMES = {-1:'unavailable', 0:'unobserved', 1:'agreement', 2:'preservation', 3:'correction', 5:'removed'}
CODE_TO_CELL = {-1:6, 0:6, 2:0, 3:2, 4:4, 5:4, 11:1, 12:3, 13:5, 14:5}
TAG = '[이 발주에서 냄]'

def stamp():
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat()

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
    return h.hexdigest()

def clean(x):
    if isinstance(x,dict):return {str(k):clean(v) for k,v in x.items()}
    if isinstance(x,(list,tuple)):return [clean(v) for v in x]
    if isinstance(x,np.ndarray):return clean(x.tolist())
    if isinstance(x,np.generic):return clean(x.item())
    if isinstance(x,float) and not np.isfinite(x):return None
    if isinstance(x,Path):return str(x)
    return x

def writable(path):
    p=Path(path).absolute()
    assert any(p.is_relative_to(root) for root in (OUT,CFG,DOC)),str(p)
    p.parent.mkdir(parents=True,exist_ok=True)
    return p

def dump(path,data):
    writable(path).write_text(json.dumps(clean(data),ensure_ascii=False,indent=2,allow_nan=False)+'\n')

def table(path,rows,**meta):
    path=writable(path)
    dump(path.with_suffix('.json'),dict(rows=rows,source_tag=TAG,scientific_verdict=None,**meta))
    if rows:
        keys=list(dict.fromkeys(k for row in rows for k in row))
        with path.with_suffix('.csv').open('w',newline='',encoding='utf-8-sig') as f:
            writer=csv.DictWriter(f,fieldnames=keys);writer.writeheader()
            writer.writerows([{k:json.dumps(v,ensure_ascii=False) if isinstance(v,(list,dict)) else v for k,v in clean(row).items()} for row in rows])

def read(path):return json.loads(Path(path).read_text())

def npz(path,keys=None):
    with np.load(path,allow_pickle=False) as z:return {k:z[k] for k in (z.files if keys is None else keys)}

def join(keys,query):
    assert len(np.unique(keys))==len(keys),'duplicate source keys'
    order=np.argsort(keys);s=keys[order];pos=np.searchsorted(s,query)
    assert len(s) and np.all(pos<len(s)) and np.all(s[pos]==query),'missing exact keys'
    return order[pos]

def building_label(b):
    return ALIASES.get(b,b.removeprefix('DEBY_LOD2_'))

class Ledger:
    def __init__(self):self.entries={}
    def add(self,path,role='input',sealed=False):
        p=Path(path);key=str(p)
        if key not in self.entries:self.entries[key]=dict(path=key,sha256=sha(p),bytes=p.stat().st_size,role=role,sealed=sealed)
        return p
    def json(self,path,**kw):return read(self.add(path,**kw))
    def arrays(self,path,keys=None,**kw):return npz(self.add(path,**kw),keys)
    def save(self):
        public=[v for v in self.entries.values() if not v['sealed']]
        sealed=[v for v in self.entries.values() if v['sealed']]
        dump(OUT/f'holdout/input_ledger_{REV}.json',dict(entries=sealed,scientific_verdict=None))
        dump(OUT/f'input_ledger_{REV}.json',dict(entries=public,sealed_files=len(sealed),sealed_ledger_sha256=sha(OUT/f'holdout/input_ledger_{REV}.json'),scientific_verdict=None))

def check_locked():
    lock=read(CFG/'regionview_v1.lock.json')
    assert sha(CFG/'regionview_v1.json')==lock['config_sha256']
    for name,value in lock['implementation_sha256'].items():assert sha(REPO/name)==value,name
    return read(CFG/'regionview_v1.json')
