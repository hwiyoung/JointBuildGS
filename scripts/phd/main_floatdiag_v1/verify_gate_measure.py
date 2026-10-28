"""Independent float64 formula verification of the measured gate pixels."""
import json
import math
import cv2
import numpy as np
from scipy.special import expit
from common import *
from recount import load_eval,classes

def dead(z,term):
    sigma=z['sigma_'+term].astype(float);v=z['v_'+term].astype(float);r=z[term+'_r_sigma'].astype(float)
    good=np.isfinite(sigma)&(sigma>0)&np.isfinite(v)&(v>0)&(v<1)
    if term=='mvs':good&=z['has_mvs']
    out=np.zeros(len(r),bool);force=np.zeros(len(r),float)
    s,v,r=sigma[good],v[good],r[good]
    loga=np.log(v)-np.log1p(-v)-np.log(s)-math.log(.1*math.sqrt(2*math.pi))
    lo=np.ones_like(s);hi=np.maximum(2*loga+30,30)
    for _ in range(64):
        t=(lo+hi)/2;left=t*expit(.5*t-loga)<1
        lo=np.where(left,t,lo);hi=np.where(left,hi,t)
    t=np.sqrt((lo+hi)/2);peak=.0025*expit(loga-.5*t*t)*t/s
    value=.0025*expit(loga-.5*r*r)*np.abs(r)/s
    force[good]=value;out[good]=value<.01*peak
    return out,force,good

rows=[]
for site in ['R1rep_b10','B173nb_b10']:
    result='lt_dynnow_ALS_s0';root=OUT/'diagnostics'/site/result
    receipt=json.loads((root/'receipt.json').read_text());e,_=load_eval(site,'ALS')
    with np.load(LT/'patch_z'/f'{site}__ALS__{result}.npz') as f:cat=classes(e,{k:f[k] for k in f.files})
    floating=e['in_eval']&e['scoring_allowed']&(e['cell']>=0)&(e['cell']<=3)&(cat==1)
    total=both_n=disagree=missing_prior=map_total=0;max_abs_error=0.
    for view in receipt['views']:
        name=view['view']
        with np.load(root/(name+'.npz')) as f:z={k:f[k] for k in f.files}
        p,pf,pg=dead(z,'prior');m,mf,mg=dead(z,'mvs');f=z['pixel_type']==0
        total+=int(f.sum());both_n+=int((f&p&(~z['has_mvs']|m)).sum())
        disagree+=int((p!=z['dynamic_prior_dead']).sum())+int(((m!=z['dynamic_mvs_dead'])&z['has_mvs']).sum())
        for key,force,good in [('prior',pf,pg),('mvs',mf,mg)]:
            if good.any():max_abs_error=max(max_abs_error,float(np.max(np.abs(force[good]-z['dynamic_'+key+'_force'][good]))))
        maps=S0/'fork_inputs/s61'/site/'maps'
        def load(folder):
            path=maps/folder;path=path/'raw_depth' if (path/'raw_depth').exists() else path
            return np.load(path/(name+'.npy'))
        loc=load('locmap_ALS').astype(np.int32);P=load('prior_ALS')
        valid=(loc>=0)&(loc<len(cat));fp=valid&floating[np.clip(loc,0,len(cat)-1)]
        map_total+=int(fp.sum());missing_prior+=int((fp&(~np.isfinite(P)|(P<=0))).sum())
    assert total==receipt['gate_counts']['floating_pixels']
    assert map_total==total+missing_prior,(map_total,total,missing_prior)
    # Float64 and float32 can differ exactly at a threshold. No such difference
    # is silently accepted: both exact counts are preserved and must agree.
    assert both_n==receipt['gate_counts']['all_own_dead'] and disagree==0
    assert max_abs_error<1e-5 and missing_prior==0
    rows.append(dict(site=site,pixels=total,all_terms_dead=both_n,fraction=both_n/total,
        formula_vs_autograd_dead_disagreements=disagree,max_abs_force_difference=max_abs_error,
        mapped_float_pixels_without_prior=missing_prior,source=str(root/'receipt.json'),source_sha256=sha(root/'receipt.json')))
save(DOC/'provenance/gate_pixel_formula_verification.json',dict(at=now(),status='PASS',rows=rows,
    method='float64 analytic derivative, 64-step peak solve, original-map denominator audit; no optimization',scientific_verdict=None))
print(json.dumps(rows,ensure_ascii=False))
