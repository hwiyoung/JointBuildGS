"""Isolated paths and receipts, avoiding previous tasks' module-name collisions."""
import hashlib,json
from pathlib import Path
from datetime import datetime,timezone,timedelta
import numpy as np
O=Path('/out');D=Path('/docs');C=Path('/config');R=Path('/repo');PH=Path('/ph')
LT=PH/'main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1'
S0=PH/'main_stage0_v1/PHD-MAIN-STAGE0-v1';S1=PH/'main_stage1_v1/PHD-MAIN-STAGE1-v1'
S3=PH/'main_stage3_v1/PHD-MAIN-STAGE3-v1';SB=PH/'main_baselines_v1/PHD-MAIN-BASELINES-v1';SF=PH/'main_fix_v1/PHD-MAIN-FIX-v1'
def now():return datetime.now(timezone(timedelta(hours=9))).isoformat()
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(8<<20),b''):h.update(b)
    return h.hexdigest()
def safe(x):
    if isinstance(x,dict):return {str(k):safe(v) for k,v in x.items()}
    if isinstance(x,(list,tuple)):return [safe(v) for v in x]
    if isinstance(x,np.ndarray):return safe(x.tolist())
    if isinstance(x,np.generic):return safe(x.item())
    if isinstance(x,float) and not np.isfinite(x):return None
    if isinstance(x,Path):return str(x)
    return x
def dump(p,x):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);t=p.with_suffix(p.suffix+'.tmp');t.write_text(json.dumps(safe(x),ensure_ascii=False,indent=2,allow_nan=False)+'\n');t.replace(p)
def status(key,stage,**kw):
    x=dict(key=key,stage=stage,at=now(),scientific_verdict=None,**kw);dump(O/'status'/f'mesh_{key}.json',x);print(json.dumps(safe(x),ensure_ascii=False),flush=True)
def resolve(site,prior,result):
    rec=LT/'patch_z'/f'{site}__{prior}__{result}.json'
    if rec.exists():
        x=json.loads(rec.read_text());p=Path(x['path'])
        if str(p).startswith('/out/'):p=LT/p.relative_to('/out')
        return p,dict(patch_z_receipt=str(rec),expected_sha256=x['mesh_sha256'])
    if result.startswith('lt_'):root=LT/'runs'/site/result
    elif result.startswith('nojudge_'):
        root=S3/'runs'/site/result
        if root.with_name(result+'.finite').exists():root=root.with_name(result+'.finite')
    elif result in ['imgonly_2dgs_s0','geogs_ALS_fix1']:root=SB/'runs'/site/result
    elif result=='trust_LoD2_fix1':root=SF/'runs'/site/result
    elif site=='B173nb_b10' and result.startswith('prop_'):root=S0/'stage0'/f'b{int(result[-1])+1}_{prior}'
    else:root=S1/'stage1'/site/result
    return root/'post/mesh_tsdf.ply',{}
def classes(e,z):
    good=np.isfinite(z['z'])&~z['no_surface'];within=good&(np.abs(z['z']-e['p_gt'])<=e['tau'])
    floating=good&~within&(z['side']==2)&(z['z']>e['p_gt']+e['tau']);out=np.full(len(e['area']),4,np.uint8)
    out[good&~within&(z['side']==1)]=2;out[good&~within&(z['side']==0)]=3;out[within]=0;out[floating]=1
    return out
CATEGORIES=['within_tau','floating','mvs','prior','other_missing']
def summarize(e,z):
    elig=e['in_eval']&e['scoring_allowed'];cat=classes(e,z);rows=[]
    for group,mask in [(str(k),elig&(e['cell']==k)) for k in range(7)]+[('0~3',elig&(e['cell']>=0)&(e['cell']<=3)),('전체',elig)]:
        area=float(e['area'][mask].sum());r=dict(cell=group,patches=int(mask.sum()),area_m2=area)
        for i,key in enumerate(CATEGORIES):
            m=mask&(cat==i);r[key+'_patches']=int(m.sum());r[key+'_area_m2']=float(e['area'][m].sum());r[key+'_pct']=100*r[key+'_area_m2']/area if area else None
        r['no_surface_area_m2']=float(e['area'][mask&z['no_surface']].sum());r['no_surface_pct']=100*r['no_surface_area_m2']/area if area else None
        rows.append(r)
    return rows
