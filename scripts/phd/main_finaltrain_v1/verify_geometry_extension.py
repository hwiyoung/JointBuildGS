"""Compare recomputed full-scope geometry with frozen evaluation geometry."""
import sys
from common import *
site=sys.argv[1];rows=[]
keys=['source_index','normal','prior_height_m','mvs_mean_m','u_mvs','sigma_P_m','r_m','L_m','geometry','n']
for prior in ['ALS','LoD2']:
    stem=f'{site}__{prior}';a=loadz(O/'outside'/site/'geometry'/f'{stem}.npz',keys);b=loadz(JA/'core_points'/f'{stem}.npz',keys)
    lookup={int(v):i for i,v in enumerate(a['source_index'])};ii=np.array([lookup[int(v)] for v in b['source_index']]);diffs={}
    for k in keys[1:]:
        x=a[k][ii];y=b[k];finite=np.isfinite(x)&np.isfinite(y)
        diffs[k]=dict(finite_masks_equal=bool(np.array_equal(np.isfinite(x),np.isfinite(y))),max_abs=float(np.max(abs(x[finite]-y[finite]))) if finite.any() else None,
            differences=int((~np.isclose(x,y,atol=1e-12,rtol=0,equal_nan=True)).sum()))
    rows.append(dict(site=site,prior=prior,eval_patches=len(ii),fields=diffs))
dump(O/'verification'/f'geometry_extension_{site}.json',dict(at=now(),rows=rows,scientific_verdict=None))
print(json.dumps(rows),flush=True)
