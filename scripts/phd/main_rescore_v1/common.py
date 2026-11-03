"""RESCORE-only outputs; inherited inputs are mounted read-only."""
import csv, datetime as dt, hashlib, json, os, time
from pathlib import Path
import numpy as np
R,C,D,O=map(Path,('/repo','/cfg','/docs','/out'))
PH=Path('/art/phase-payloads/phd')
TG=PH/'main_target_v1/PHD-MAIN-TARGET-v1'
JA=PH/'main_judgeapply_v1/PHD-MAIN-JUDGEAPPLY-v1'
S0=PH/'main_stage0_v1/PHD-MAIN-STAGE0-v1'
S1=PH/'main_stage1_v1/PHD-MAIN-STAGE1-v1'
SITES=['B0_b10','B173nb_b10','R1rep_b10','B173_b0']
LABELS=dict(zip(SITES,['B0','B173 주변','R1','B173만']))
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
 assert sha(C/'rescore_v1.json')==json.loads((C/'rescore_v1.initial.lock.json').read_text())['config_sha256']
 return json.loads((C/'rescore_v1.json').read_text())
def progress(s):
 with (D/'progress.md').open('a') as f:f.write(f'- {now()}: {s}\n')
def table(name,rows):
 dump(D/'tables'/f'{name}.json',dict(rows=rows,source_tag='[이 발주에서 냄]',scientific_verdict=None))
 keys=list(dict.fromkeys(k for r in rows for k in r))
 with (D/'tables'/f'{name}.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows([{k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in r.items()} for r in rows])
 (D/'tables'/f'{name}.md').write_text('| '+' | '.join(keys)+' |\n| '+' | '.join(['---']*len(keys))+' |\n'+'\n'.join('| '+' | '.join(str(r.get(k,'')) for k in keys)+' |' for r in rows)+'\n')
def timing(stage,start,**extra):
 d=dict(at=now(),stage=stage,seconds=time.monotonic()-start,gpu_wait_seconds=0,scientific_verdict=None,**extra)
 dump(O/'timing'/f'{stage}.json',d);progress(f'{stage}: {d["seconds"]:.1f}초; GPU 대기 {d["gpu_wait_seconds"]}초.');return d
