"""Evaluation-only spatial cases; never export optimizer masks or source authority."""
import json
from pathlib import Path
import numpy as np
from analyze_final_surfaces import read,write,sha

out=Path('/out');cfg=read(out/'config.json');root=Path('/art')/cfg['attempt_relative']
assert read(out/'receipt.json')['status']=='PASS_UAS_REFERENCE_DISTANCE_DIAGNOSTIC'
theta=np.deg2rad(70);basis=np.array([[np.cos(theta),np.sin(theta)],[np.sin(theta),-np.cos(theta)]])
result=dict(scientific_verdict=None,role='EVALUATION_ONLY_SPATIAL_DIAGNOSTIC_NOT_TRAINING_LABELS',
            bands=dict(near_m=.25,far_m=1.,cell_m=2,minimum_cell_reference_points=20),regions={})
for r in cfg['regions']:
    ref=np.load(out/(r+'_reference.npz'))['xyz'];uv=ref[:,:2]@basis.T
    a=np.load(out/(r+'_uas_distances.npz'));dp=np.load(out/(r+'_uas_to_prior.npy'));db=a['mvs'];zid=a['zone']
    zp=Path('/art')/cfg['r1_review_relative']/'config.json' if r=='R1' else root/r/'review_zones.json'
    zones=read(zp)['zones'];names={int(z['id'][1:]):z for z in zones}
    masks={'prior_near_baseline_far':(dp<=.25)&(db>1.),'both_far':(dp>1.)&(db>1.),
           'prior_far_baseline_near':(dp>1.)&(db<=.25)}
    zones_rows=[]
    for z in zones:
        sel=zid==int(z['id'][1:]);row=dict(zone=z['id'],name=z['name'],kind=z['kind'],n=int(sel.sum()),
               counts={k:int((sel&m).sum()) for k,m in masks.items()});zones_rows.append(row)
    # Inspect all frozen regions with one fixed 3D grouping, not just favorable outcomes.
    key=np.floor(np.column_stack([uv,ref[:,2]])/2).astype(int);_,inv=np.unique(key,axis=0,return_inverse=True)
    sizes=np.bincount(inv);nz=max(names)+1
    zone_hist=np.bincount(inv*nz+zid,minlength=len(sizes)*nz).reshape(-1,nz)
    dominant=zone_hist.argmax(1);is_building=np.array([names[int(z)]['kind']=='building' for z in dominant])
    eligible=np.flatnonzero((sizes>=20)&is_building)
    cell_counts={k:np.bincount(inv,weights=m.astype(np.int32),minlength=len(sizes)).astype(int) for k,m in masks.items()}
    selected={k:eligible[np.argsort(-n[eligible],kind='stable')[:8]] for k,n in cell_counts.items()}
    cells={}
    for idx in np.unique(np.concatenate(list(selected.values()))):
        ix=np.flatnonzero(inv==idx);n=len(ix);z=int(dominant[idx])
        cell=dict(zone=names[z]['id'],name=names[z]['name'],uvz_min=(key[ix[0]]*2).tolist(),n=int(n),
                  median_prior_distance=float(np.median(dp[ix])),median_baseline_distance=float(np.median(db[ix])),
                  median_da3_distance=float(np.median(a['da3'][ix])),median_release_distance=float(np.median(a['local_prior0'][ix])),
                  counts={k:int(m[ix].sum()) for k,m in masks.items()})
        cells[int(idx)]=cell
    result['regions'][r]=dict(zones=zones_rows,top_cells={k:[cells[int(idx)] for idx in selected[k]] for k in masks},
                             inputs_sha256={name:sha(out/name) for name in [r+'_reference.npz',r+'_uas_distances.npz',r+'_uas_to_prior.npy']})
    print('COMPLETE',r,flush=True)
result['status']='PASS_REFERENCE_CASE_LOCATION_DIAGNOSTIC'
result['limitations']=['Distance bands are descriptive reference-error strata, not calibrated correctness/change labels.',
                      'No claim that MVS caused a discrepancy; nearest-reference-surface association and source attribution need review.',
                      'Building XY context and 2m 3D cells are not semantic roof masks.',
                      'These cases must not be fed back as source-authority labels, training masks, registration, or threshold tuning.']
write(out/'case_locations.json',result)
print(json.dumps({r:{k:v[:2] for k,v in d['top_cells'].items()} for r,d in result['regions'].items()},ensure_ascii=False))
