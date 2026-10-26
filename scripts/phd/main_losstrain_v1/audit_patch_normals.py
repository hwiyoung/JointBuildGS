"""Inspect zero-tangent centroid patches against their OWN prior surface table.

Read-only diagnosis. No GT, nearest-surface substitution, or geometry changes.
"""
import json
import numpy as np
from inputs import OUT,PH,S0,SITES,PRIORS,save,sha

def main():
    rows=[];DR=PH/'main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1'
    U=PH/'main_uncert_v1/PHD-MAIN-UNCERT-v1'
    for site in SITES:
        for prior in PRIORS:
            src=DR/'s02_box'/site/f'{prior.lower()}_surfaces.json'
            tab={int(s['ext']):s for s in json.loads(src.read_text())['surfaces']}
            with np.load(S0/'fork_inputs/s61'/site/f'store_{prior}.npz') as st,np.load(U/'patch_values'/f'{site}__{prior}__R1.5.npz') as u:
                n=u['normal'];bad=~np.isclose(np.linalg.norm(n,axis=1),1,atol=1e-5)
                ids=np.flatnonzero(bad);ext=st['surf_ext'][st['loc_surface']][ids]
                assert st['loc_extra'][ids].all()
                normals=np.array([tab[int(e)]['normal'] for e in ext]).reshape(-1,3)
                assert np.isclose(np.linalg.norm(normals,axis=1),1,atol=1e-6).all()
                row=dict(site=site,prior=prior,zero_normal_patches=len(ids),all_centroid_extra=True,
                    own_surface_normal_available=len(normals),eval_patches=int(u['in_eval'][ids].sum()),
                    n_tri_counts={str(k):int(v) for k,v in zip(*np.unique([tab[int(e)].get('n_tri',0) for e in ext],return_counts=True))},
                    source=str(src),source_sha256=sha(src),GT_used=False,
                    proposed_rule='use existing normal of exact owning prior surface for centroid-only patches, retain every existing nonzero patch normal',
                    scientific_verdict=None)
                rows.append(row)
                print(site,prior,row['zero_normal_patches'],'all exact-owning-surface normals available',row['n_tri_counts'],flush=True)
    save(OUT/'checks/direct_stage1/zero_normals.json',dict(rows=rows,scientific_verdict=None))

if __name__=='__main__':main()
