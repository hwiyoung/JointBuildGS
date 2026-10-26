"""Read-only inspection of UNCERT patch inputs for the requested direct rules.

This inventory does not choose unspecified C.5 rules, assign probabilities,
read GT values, or decide the new 95%/90% gates.
"""
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
import numpy as np
from inputs import OUT, PH, S0, SITES, PRIORS, save, sha

def main():
    U=PH/'main_uncert_v1/PHD-MAIN-UNCERT-v1'
    rows=[]
    for site in SITES:
        for prior in PRIORS:
            path=U/'patch_values'/f'{site}__{prior}__R1.5.npz'
            store=S0/'fork_inputs/s61'/site/f'store_{prior}.npz'
            with np.load(path,allow_pickle=False) as z, np.load(store,allow_pickle=False) as st:
                centres=z['centre'];ev=z['in_eval'].astype(bool)
                same=np.array_equal(centres,st['loc_center'])
                assert same, f'UNCERT row geometry differs from training: {site}/{prior}'
                row=dict(site=site,prior=prior,patches=len(centres),eval_patches=int(ev.sum()),
                    row_centres_equal_training=True,uncert_source=str(path),uncert_sha256=sha(path),
                    stage1_store=str(store),store_sha256=sha(store),fields=list(z.files),
                    edge_finite=int(np.isfinite(z['edge']).sum()),edge_positive_infinity=int(np.isposinf(z['edge']).sum()),
                    edge_nan=int(np.isnan(z['edge']).sum()),
                    normal_unit_in_eval=int((ev&np.isclose(np.linalg.norm(z['normal'],axis=1),1,atol=1e-5)).sum()),
                    required_rule_specification='modified order 6.4 and C.5 pending',GT_values_read=False,
                    scientific_verdict=None)
                for field in ['u_prior','mvs_a_u','mvs_a_p','als_u','als_s','als_q','als_s0']:
                    if field not in z.files:continue
                    x=z[field].astype(float);m=ev&np.isfinite(x)
                    row[field]=dict(eval_finite=int(m.sum()),eval_finite_fraction=float(m.sum()/ev.sum()),
                        finite_quantiles=np.quantile(x[m],[0,.25,.5,.75,1]).tolist() if m.any() else None)
                if prior=='LoD2':
                    row['roof_types']={k:int(((z['roof_type']==k)&ev).sum()) for k in np.unique(z['roof_type'])}
                rows.append(row)
                print(site,prior,'rows',len(centres),'eval',int(ev.sum()),'exact training row match',same,
                    'u_prior finite in eval',row['u_prior']['eval_finite_fraction'],flush=True)
    save(OUT/'checks/direct_stage1/input_inventory.json',dict(task_id='PHD-MAIN-LOSSTRAIN-v1',
        saved_at=datetime.now(timezone(timedelta(hours=9))).isoformat(),rows=rows,
        status='INPUT_INVENTORY_ONLY_NOT_NEW_GATE',scientific_verdict=None))

if __name__=='__main__':main()
