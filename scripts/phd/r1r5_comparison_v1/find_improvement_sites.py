"""Rank spatially distinct output discrepancies for human review; evaluation only."""
from pathlib import Path
import csv
import numpy as np
from analyze_final_surfaces import read, write, sha

OUT=Path('/out');CFG=read(OUT/'config.json');ROOT=Path('/art')/CFG['attempt_relative'];U=ROOT/CFG['uas_folder']
t=np.deg2rad(70);B=np.array([[np.cos(t),np.sin(t)],[np.sin(t),-np.cos(t)]])
SIZE=np.array(CFG['cell_size_m']);records=[];counts={};FAR=CFG.get('far_m',1.)
for r in CFG['regions']:
    ref=np.load(U/(r+'_reference.npz'))['xyz'];uv=ref[:,:2]@B.T;uvz=np.column_stack([uv,ref[:,2]])
    a=np.load(U/(r+'_uas_distances.npz'));p=np.load(U/(r+'_uas_to_prior.npy'));m=a['mvs'];d=a['da3']
    zones=read(Path('/art')/CFG['r1_review_relative']/'config.json' if r=='R1' else ROOT/r/'review_zones.json')['zones']
    names={int(z['id'][1:]):z for z in zones}
    key,inv=np.unique(np.floor(uvz/SIZE).astype(np.int32),axis=0,return_inverse=True);n=np.bincount(inv)
    _,xyinv=np.unique(np.floor(uv/.5).astype(np.int32),axis=0,return_inverse=True)
    ztop=np.full(xyinv.max()+1,-np.inf);np.maximum.at(ztop,xyinv,ref[:,2]);top=ref[:,2]>=ztop[xyinv]-.5
    order=np.argsort(inv,kind='stable');offset=np.r_[0,np.cumsum(n)];local=[]
    for i in np.flatnonzero(n>=CFG['minimum_points']):
        ix=order[offset[i]:offset[i+1]];zs=a['zone'][ix];z=int(np.bincount(zs).argmax())
        if names[z]['kind']!='building' or np.mean(zs==z)<.8 or top[ix].mean()<CFG.get('minimum_top_fraction',0):continue
        pts=uvz[ix];center=pts.mean(0);v=pts-center
        vals,vecs=np.linalg.eigh(v.T@v/len(v));rms=float(np.sqrt(max(0,vals[0])))
        if rms>CFG['plane_rms_max_m'] or abs(vecs[2,0])<CFG['normal_z_min']:continue
        bands={'mvs_prior_preservation':(p[ix]<=.25)&(m[ix]>FAR),
               'da3_prior_preservation':(p[ix]<=.25)&(d[ix]>FAR),
               'da3_vs_mvs':(m[ix]<=.25)&(d[ix]>FAR),
               'mvs_vs_da3':(d[ix]<=.25)&(m[ix]>FAR),
               'both_unresolved':(p[ix]>FAR)&(m[ix]>FAR)&(d[ix]>FAR)}
        fractions={k:float(x.mean()) for k,x in bands.items()}
        if max(fractions.values())<CFG['minimum_category_fraction']:continue
        item=dict(region=r,zone=names[z]['id'],zone_name=names[z]['name'],uvz_min=(key[i]*SIZE).tolist(),
                  size=SIZE.tolist(),center=center.tolist(),n=int(n[i]),plane_rms_m=rms,top_reference_fraction=float(top[ix].mean()),normal_uvz=vecs[:,0].tolist(),
                  fraction=fractions,median_m={k:float(np.median(x[ix])) for k,x in [('prior',p),('mvs',m),('da3',d),('local_prior0',a['local_prior0'])]},
                  p90_m={k:float(np.quantile(x[ix],.9)) for k,x in [('prior',p),('mvs',m),('da3',d)]})
        local.append(item)
    counts[r]=dict(reference_points=len(ref),occupied_cells=len(n),eligible_discrepancy_cells=len(local));records+=local
    print(r,counts[r],flush=True)
# Retain the full search table and a spatially separated shortlist for each category/region.
write(OUT/'all_ranked_cells.json',dict(role='EVALUATION_ONLY',scientific_verdict=None,counts=counts,cells=records))
selected={}
for category in ['mvs_prior_preservation','da3_prior_preservation','da3_vs_mvs','mvs_vs_da3','both_unresolved']:
    selected[category]=[]
    for r in CFG['regions']:
        eligible=[x for x in records if x['region']==r and x['fraction'][category]>=CFG['minimum_category_fraction']]
        eligible.sort(key=lambda x:(-x['fraction'][category]*x['n'],x['uvz_min']))
        chosen=[]
        for x in eligible:
            if any(np.linalg.norm(np.array(x['center'][:2])-np.array(y['center'][:2]))<CFG['separation_m'] for y in chosen):continue
            chosen.append(x)
            if len(chosen)>=CFG['shortlist_per_region']:break
        selected[category]+=chosen
write(OUT/'shortlist.json',dict(status='PASS_OUTPUT_DISCREPANCY_SEARCH',scientific_verdict=None,categories=selected,
    inputs_sha256={r:{f:sha(U/(r+f)) for f in ['_reference.npz','_uas_distances.npz','_uas_to_prior.npy']} for r in CFG['regions']}))
print('COMPLETE',sum(map(len,selected.values())),flush=True)
