"""Join unchanged numerical outputs and export by the frozen building split."""
import json
from pathlib import Path
import numpy as np
from preflight import dump,sha
O=Path('/out');R=O/'holdout/internal';C=json.loads(Path('/cfg/widen0_v2.json').read_text())
CELLS=C['cells']['order']

def classify(gt_status,gt_p,e,tau):
    # Scalar and per-patch thresholds must have identical precision semantics,
    # including historical float32 values immediately around the fixed limit.
    gt_p=np.asarray(gt_p,dtype=np.float64);e=np.asarray(e,dtype=np.float64);tau=np.asarray(tau,dtype=np.float64)
    assert np.isfinite(tau).all() and np.all(tau>0), 'classification requires a finite positive threshold'
    gt=(gt_status==0)&np.isfinite(gt_p);m=np.isfinite(e);p=np.abs(gt_p)<=tau
    cell=np.full(len(gt),6,np.int8)
    cell[gt&m&p&(e<=tau)]=0;cell[gt&m&~p&(e<=tau)]=1
    cell[gt&m&p&(e>tau)]=2;cell[gt&m&~p&(e>tau)]=3
    cell[gt&~m&p]=4;cell[gt&~m&~p]=5
    return cell

def export(tile,prior):
    geom=R/'patch_geometry'/f'{tile}_{prior}.npz'
    with np.load(geom) as z:d={k:z[k] for k in z.files}
    shift=d.pop('frame_shift');n=len(d['centre'])
    for data in ['gt','mvs_a']+(['als'] if prior=='ALS' else []):
        path=R/'work'/(f'gt_{tile}_{prior}.npz' if data=='gt' else f'val_{tile}_{prior}_{data}_R1.5.npz')
        with np.load(path) as z:
            assert len(z['status'])==n and np.all(z['status']>=0),path
            d.update({f'{data}_{k}':z[k] for k in z.files})
    d['mvs_p']=np.where(d['mvs_a_status']==0,d['mvs_a_p'],np.nan)
    d['u_mvs']=np.where(d['mvs_a_status']==0,d['mvs_a_u'],np.nan)
    d['u_prior']=np.full(n,C['definitions']['lod2_u_m']) if prior=='LoD2' else np.where(d['als_status']==0,d['als_u'],np.nan)
    d['prior_error']=np.where(d['gt_status']==0,np.abs(d['gt_p']),np.nan) if prior=='LoD2' else d['als_e']
    d['prior_position_error']=np.where(d['gt_status']==0,np.abs(d['gt_p']),np.nan)
    den=np.sqrt(d['u_mvs']**2+d['u_prior']**2)
    d['difference_over_uncertainty']=np.divide(np.abs(d['mvs_p']),den,out=np.full(n,np.nan),where=den>0)
    d['cell']=classify(d['gt_status'],d['gt_p'],d['mvs_a_e'],d['tau'])
    split=json.loads((O/'building_split.json').read_text());held=set(split['holdout']);dev=set(split['development'])
    assert np.array_equal(d['holdout'],np.array([b in held for b in d['building']]))
    assert all(b in held|dev for b in d['building'])
    assert len(set(d['patch_id']))==n
    for seal in [False,True]:
        mask=d['holdout']==seal;dest=O/('holdout/patch_values' if seal else 'patch_values');dest.mkdir(parents=True,exist_ok=True)
        f=dest/f'{tile}__{prior}__R1.5.npz'
        np.savez_compressed(f,**{k:v[mask] for k,v in d.items()})
        dump(f.with_suffix('.json'),dict(tile=tile,prior=prior,patches=int(mask.sum()),area_m2=float(d['area'][mask].sum()),
            fraction_patches_with_GT=float(np.mean(d['gt_status'][mask]==0)) if mask.any() else None,
            sha256=sha(f),keys=sorted(d),frame_shift=shift.tolist(),cells=CELLS,config_sha256=sha('/cfg/widen0_v2.json'),
            scientific_verdict=None))
    print('export sealed by building',tile,prior,flush=True)

if __name__=='__main__':
    import sys
    if len(sys.argv)>1:export(*sys.argv[1:3])
    else:
        for t in json.loads((O/'inputs/tiles.json').read_text()):
            for p in ['LoD2','ALS']:export(t['id'],p)
