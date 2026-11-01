"""Independently join every saved baseline contribution sample to original first hits."""
import sys
import numpy as np
from common import *


def loadz(path):
    with np.load(path) as z:return {k:z[k] for k in z.files}


def main():
    prior=sys.argv[1];root=OUT/'r8/baseline_origin'/prior
    info=json.loads((root/'summary.json').read_text());assert info['status']=='PASS_BASELINE_PROVENANCE_REPLAY'
    assert info['optimization_steps']==0 and len(info['views'])==203
    lock=json.loads((CFG/'baseline_origin_r8.lock.json').read_text())
    for path,digest in lock['inputs'][prior].items():assert sha(path)==digest
    base=OUT/'r7/baselines'/f'base7k_B173nb_b10_{prior}_s0';cover=json.loads((base/'model/check7000/coverage.json').read_text())
    matrices={v['camera']:v for v in cover['views']}
    e=loadz(PH/'main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/direct_stage1_v2'/f'B173nb_b10__{prior}/evaluation.npz')
    z=loadz(base/'post7000/patch_z.npz');a=loadz(root/'origin_attribution.npz')
    points=e['centre']+e['normal']*z['z'][:,None];eligible=e['in_eval']&e['scoring_allowed'];candidate=np.flatnonzero(eligible&~z['no_surface'])
    assert np.array_equal(points,a['hit_xyz'],equal_nan=True) and np.array_equal(z['category'],a['category'])
    total=np.zeros_like(a['mean_fraction']);count=np.zeros(len(points),np.int32);samples=0;max_partition_error=0.
    for record in info['views']:
        name=record['camera'];p=root/'views'/f'{name}.npz';assert sha(p)==record['sha256'] and record['depth_alpha_byte_equal']
        sample=loadz(p);saved=loadz(base/'model/check7000/renders'/f'{name}.npz');m=matrices[name]
        W=np.asarray(m['W2C']);K=np.asarray(m['K']);q=points[candidate]@W[:3,:3].T+W[:3,3]
        front=q[:,2]>0;ix=candidate[front];q=q[front]
        uv=np.column_stack((np.rint(q[:,0]*K[0,0]/q[:,2]+K[0,2]),np.rint(q[:,1]*K[1,1]/q[:,2]+K[1,2]))).astype(np.int64)
        inside=(uv[:,0]>=0)&(uv[:,1]>=0)&(uv[:,0]<saved['depth'].shape[1])&(uv[:,1]<saved['depth'].shape[0]);ix=ix[inside];q=q[inside];uv=uv[inside]
        observed=saved['depth'][uv[:,1],uv[:,0]];alpha=saved['alpha'][uv[:,1],uv[:,0]]
        visible=np.isfinite(observed)&(observed>0)&(np.abs(q[:,2]-observed)<=.25)&(alpha>1e-5)
        assert np.array_equal(ix[visible],sample['patch_index'])
        assert np.array_equal(uv[visible,0],sample['u']) and np.array_equal(uv[visible,1],sample['v'])
        values=sample['fraction'];assert np.isfinite(values).all() and ((values>=0)&(values<=1)).all() and (values[:,1]==0).all()
        if len(values):max_partition_error=max(max_partition_error,float(abs(values[:,[0,2]].sum(1)-1).max()))
        np.add.at(total,sample['patch_index'],values);np.add.at(count,sample['patch_index'],1);samples+=len(values)
    expected=np.divide(total,count[:,None],out=np.full_like(total,np.nan),where=count[:,None]>0)
    assert np.array_equal(count,a['views']) and np.array_equal(expected,a['mean_fraction'],equal_nan=True)
    assert max_partition_error<1e-5
    assert np.array_equal(a['background_dominant'],(count>0)&(expected[:,0]>=.5)) and not a['released_dominant'].any()
    floating=eligible&(z['category']==1);dominant={}
    for name,ch in [('background',0),('prior',2)]:dominant[name]=int((floating&(count>0)&(expected[:,ch]>=.5)).sum())
    result=dict(at=stamp(),status='PASS_BASELINE_ORIGIN_JOIN',prior=prior,views=203,joined_samples=samples,
                max_partition_error=max_partition_error,floating_dominant_patch_counts=dominant,
                attribution_sha256=sha(root/'origin_attribution.npz'),original_inputs_unchanged=True,scientific_verdict=None)
    dump(root/'verification.json',result);print('BASELINE_ORIGIN_VERIFIED',prior,samples,flush=True)


if __name__=='__main__':main()
