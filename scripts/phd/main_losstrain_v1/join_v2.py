"""User revision: <=18cm centre distance and <=10cm along BOTH patch normals.

No GT access. Keep the 5cm receipts immutable. Select the nearest same-prior
centre, then apply the two requested geometric checks. Undefined normals
are not imputed and cannot establish the same-plane criterion.
"""
import csv
import json
from datetime import datetime
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
from inputs import OUT, S0, S1, SITES, PRIORS, sha, save
from join_preflight import load_geometry, quant

def main():
    config=dict(task_id='PHD-MAIN-LOSSTRAIN-v1',revision='join_v2',
        saved_at=datetime.now().astimezone().isoformat(),reason='explicit user reply replacing 5cm rule',
        nearest='registered Euclidean 3D nearest, same prior',centre_max_m=.18,normal_height_max_m=.10,
        same_plane='abs(delta dot unit_stage1_normal)<=0.10 AND abs(delta dot unit_vfile_normal)<=0.10',
        unknown_normal='unmatched; never infer a normal',minimum_joined_fraction=.95,
        patch_denominator='all stage-1 patches; evaluation-only denominator also reported',
        pixel_denominator='all positive finite prior-depth pixels inside the frozen evaluation XY box',
        GT_used=False,scientific_verdict=None)
    cfg=Path('/config/join_v2.json')
    assert not cfg.exists(),'refuse to replace frozen rule'
    save(cfg,config);save('/config/join_v2.lock.json',dict(sha256=sha(cfg),saved_at=config['saved_at']))
    rows=[];sources=[]
    for prior in PRIORS:
        g,src=load_geometry(prior);sources+=src;tree=cKDTree(g['centre'])
        for site in SITES:
            I=S0/'fork_inputs/s61'/site;sf=I/f'store_{prior}.npz'
            rf=S1/'regions_v3'/f'regions_ext_v3_{site}_{prior}.npz'
            with np.load(sf,allow_pickle=False) as z:
                centres=z['loc_center'];normals=np.cross(z['loc_t1'],z['loc_t2'])
                lengths=np.linalg.norm(normals,axis=1)
                defined=np.isfinite(lengths)&(lengths>1e-8)
                normals[defined]/=lengths[defined,None]
            with np.load(rf,allow_pickle=False) as z:
                assert np.array_equal(z['centre'],centres);ev=z['in_eval'].astype(bool)
            d,idx=tree.query(centres,workers=8)
            vn=g['normal'][idx];vl=np.linalg.norm(vn,axis=1)
            known=defined&np.isfinite(vl)&(vl>1e-8)
            vn=np.divide(vn,vl[:,None],out=np.zeros_like(vn),where=vl[:,None]>1e-8)
            delta=centres-g['centre'][idx]
            h1=np.abs(np.sum(delta*normals,axis=1));h2=np.abs(np.sum(delta*vn,axis=1))
            h=np.maximum(h1,h2)
            near=d<=config['centre_max_m'];same_plane=known&(h<=config['normal_height_max_m'])
            joined=near&same_plane
            row=dict(site=site,prior=prior,patches=len(d),joined_patches=int(joined.sum()),joined_fraction=float(joined.mean()),
                eval_patches=int(ev.sum()),eval_joined_patches=int((joined&ev).sum()),eval_joined_fraction=float(joined[ev].mean()),
                nearest_distance_m=quant(d),eval_nearest_distance_m=quant(d[ev]),
                centre_within_18cm=int(near.sum()),within_18cm_rejected_plane=int((near&known&~same_plane).sum()),
                within_18cm_unknown_normal=int((near&~known).sum()),
                normal_height_m=quant(h[known]),eval_normal_height_m=quant(h[known&ev]),
                unique_vfile_patches=int(len(np.unique(idx[joined]))),
                gate='PASS' if joined.mean()>=.95 else 'STOP',
                stage1_store=str(sf),store_sha256=sha(sf),rules_sha256=sha(cfg),GT_used=False,scientific_verdict=None)
            with np.load(sf,allow_pickle=False) as z:area=z['loc_area']
            row.update(unmatched_area_m2=float(area[~joined].sum()),eval_unmatched_area_m2=float(area[ev&~joined].sum()),
                eval_area_m2=float(area[ev].sum()))
            dest=OUT/'checks/join_v2'/f'{site}__{prior}.npz';dest.parent.mkdir(parents=True,exist_ok=True)
            np.savez_compressed(dest,stage1_patch=np.arange(len(d)),vfile_patch_id=g['patch_id'][idx],nearest_index=idx,
                distance_m=d,normal_height_stage1_m=h1,normal_height_vfile_m=h2,normal_defined=known,joined=joined,in_eval=ev)
            rows.append(row)
            save(OUT/'checks/join_v2.json',dict(config=config,rows=rows,sources=sources,scientific_verdict=None))
            save('/docs/tables/patch_join_v2.json',dict(config=config,rows=rows,scientific_verdict=None))
            print(site,prior,'join',row['joined_fraction'],'eval',row['eval_joined_fraction'],
                  'distance',row['nearest_distance_m'],row['gate'],flush=True)
    cols=['site','prior','patches','joined_patches','joined_fraction','eval_patches','eval_joined_patches',
          'eval_joined_fraction','eval_unmatched_area_m2','gate']
    with Path('/docs/tables/patch_join_v2.csv').open('w') as f:
        w=csv.DictWriter(f,cols,extrasaction='ignore');w.writeheader();w.writerows(rows)

if __name__=='__main__':main()
