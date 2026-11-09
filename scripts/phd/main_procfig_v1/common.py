"""PROCFIG isolated paths. Inputs are mounted read-only; no training entrypoint."""
import ast, csv, datetime as dt, hashlib, json, os, sys, time
from pathlib import Path
import numpy as np
R,C,D,O=map(Path,['/repo','/cfg','/docs','/out'])
PH=Path('/art/phase-payloads/phd')
FT=PH/'main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1'
GT=PH/'main_gtjudge_v1/PHD-MAIN-GTJUDGE-v1'
S1=PH/'main_stage1_v1/PHD-MAIN-STAGE1-v1'
RS=PH/'main_rescore_v1/PHD-MAIN-RESCORE-v1'
JA=PH/'main_judgeapply_v1/PHD-MAIN-JUDGEAPPLY-v1'
SITE='B173nb_b10'; STEM=SITE+'__ALS'; CASE='c1_'+STEM
MODEL=FT/'runs'/SITE/'ft_ALS_s0/attempt1/model'
SHIFT=np.array([690953.,5336071.,604.])
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
def issue(s):
 with (D/'issues.md').open('a') as f:f.write('- '+now()+': '+s+'\n')
def inherit(path,names,env):
 nodes=[n for n in ast.parse(Path(path).read_text()).body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name in names];assert len(nodes)==len(names)
 exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),env);return {n:env[n] for n in names}
def cfg():
 p=C/'procfig_v1.json';assert sha(p)==json.loads((C/'procfig_v1.lock.json').read_text())['config_sha256'];value=json.loads(p.read_text());fix=C/'procfig_v1.display_fix1.json'
 if fix.exists():
  record=json.loads(fix.read_text());assert record['base_config_sha256']==sha(p);assert sha(fix)==json.loads(fix.with_suffix('.lock.json').read_text())['config_sha256'];value['rendering']['wrong_lineage_always_visible_in_threshold_selection']=record['d_wrong_lineage_threshold_exception'];value['display_fix1_sha256']=sha(fix)
 return value
def table(name,rows):
 keys=list(dict.fromkeys(k for r in rows for k in r));p=D/'tables'/name
 with p.with_suffix('.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=keys,lineterminator='\n');w.writeheader();w.writerows(rows)
 p.with_suffix('.md').write_text('| '+' | '.join(keys)+' |\n|'+'|'.join(['---']*len(keys))+'|\n'+'\n'.join('| '+' | '.join('확인 불가' if r.get(k) is None else str(r.get(k,'')) for k in keys)+' |' for r in rows)+'\n')
