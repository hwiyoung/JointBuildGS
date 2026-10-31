"""Explain status 1 from stored columns and their exact retained ALS coverage."""
import numpy as np
from scipy.spatial import cKDTree
from common import *

c,lock=locked();rows=[]
for site in c['sites']+c['deferred_sites']:
    src=OUT/'b173_uncert_r1' if site in c['deferred_sites'] else UN
    f=src/'patch_values'/f'{site}__ALS__R1.5.npz'
    with np.load(f) as z:d={k:z[k] for k in ['centre','normal','in_eval','area','als_status','als_n_col']}
    p=np.load(src/'points'/site/'als_xyz.npy',mmap_mode='r')
    dist,idx=cKDTree(p[:,:2]).query(d['centre'][:,:2],workers=1)
    dz=p[idx,2]-d['centre'][:,2]
    angle=np.radians(70.);basis=np.array([[np.cos(angle),np.sin(angle)],[np.sin(angle),-np.cos(angle)]])
    uv=d['centre'][:,:2]@basis.T
    ranges=json.loads((PH/'main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1/s02_box'/site/'range.json').read_text())
    lo=np.array([ranges['u_m'][0],ranges['v_m'][0]])-3;hi=np.array([ranges['u_m'][1],ranges['v_m'][1]])+3
    outside=(np.maximum(lo-uv,uv-hi)>.5).any(1)
    for scope,mask in [('eval',d['in_eval']),('band',~d['in_eval'])]:
        m=mask&(d['als_status']==1);empty=m&(d['als_n_col']==0)
        row=dict(site=site,range=scope,state1_patches=int(m.sum()),state1_area_m2=float(d['area'][m].sum()),
            empty_column_patches=int(empty.sum()),nonempty_without_20pct_layer=int((m&~empty).sum()),
            empty_outside_crop_by_gt_05m=int((empty&outside).sum()),empty_inside_crop_or_near_edge=int((empty&~outside).sum()),
            crop_uv=[lo.tolist(),hi.tolist()],patch_uv_range=[uv.min(0).tolist(),uv.max(0).tolist()],
            nearest_XY_gt_05m=int((empty&(dist>.5)).sum()),nearest_XY_gt_15m=int((empty&(dist>1.5)).sum()),
            nearest_XY_le_05m_but_abs_dz_gt_10m=int((empty&(dist<=.5)&(abs(dz)>10)).sum()),
            empty_nearest_XY_quantile_m=np.quantile(dist[empty],[0,.5,.95,1]).tolist() if empty.any() else [],
            empty_nearest_XY_dz_quantile_m=np.quantile(dz[empty],[0,.5,.95,1]).tolist() if empty.any() else [],
            empty_patch_Z_quantile_m=np.quantile(d['centre'][empty,2],[0,.5,.95,1]).tolist() if empty.any() else [])
        rows.append(row);print(row,flush=True)
    np.savez_compressed(OUT/'stage0_r1'/f'als_diagnosis_{site}.npz',centre=d['centre'],in_eval=d['in_eval'],state1=d['als_status']==1,
        empty_column=d['als_n_col']==0,nearest_XY=dist,nearest_XY_dz=dz)
dump(DOC/'tables/als_status1_diagnosis_r1.json',dict(rows=rows,config_sha256=lock['config_sha256'],scientific_verdict=None))
