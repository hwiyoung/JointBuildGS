"""Check whether evaluated case samples belong to the upper sampled UAS layer."""
from pathlib import Path
import numpy as np
from analyze_final_surfaces import read,write
from build_failure_inspector import transform
OUT=Path('/out');CFG=read(OUT/'config.json');U=Path('/art')/CFG['attempt_relative']/CFG['uas_folder']
cases=read(OUT/'reviewed_sites.json')['cases'];rows=[]
for r in CFG['regions']:
    ref=np.load(U/(r+'_reference.npz'));x=transform(ref['xyz']);x[:,1]*=-1
    _,inv=np.unique(np.floor(x[:,:2]/.5).astype(np.int32),axis=0,return_inverse=True)
    top=np.full(inv.max()+1,-np.inf);np.maximum.at(top,inv,x[:,2])
    for c in [c for c in cases if c['region']==r]:
        lo=np.array(c['uvz_min']);hi=lo+c['size'];sel=((x>=lo)&(x<hi)).all(1);gap=top[inv[sel]]-x[sel,2]
        ids,counts=np.unique(ref['classification'][sel],return_counts=True)
        rows.append(dict(id=c['id'],n=int(sel.sum()),fraction_within_05m_of_upper_sample=float(np.mean(gap<=.5)),median_upper_gap_m=float(np.median(gap)),
                         classification_counts={str(i):int(n) for i,n in zip(ids,counts)}))
write(OUT/'reference_layer_audit.json',dict(status='PASS_REFERENCE_LAYER_DIAGNOSTIC',role='EVALUATION_ONLY_NOT_ROOF_LABELS',scientific_verdict=None,cases=rows,
    method='Upper sampled z within0.5m XY columns. This is an evaluation correspondence clue, not calibrated visibility or semantic truth.'))
print(rows,flush=True)
