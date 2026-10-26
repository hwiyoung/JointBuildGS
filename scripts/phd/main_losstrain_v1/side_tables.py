"""8.2 area cross-tabulations of trained and analytic destinations on stage-1 rows."""
import argparse
import csv
from pathlib import Path
import numpy as np
from inputs import OUT,SITES,PRIORS,save,sha

VARS={'lt_fixgt':'fixed_gt','lt_dyngt':'dyn_gt','lt_dynsoft':'dyn_soft','lt_dynnow':'dyn_now','lt_fixnow':'fixed_now'}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--site',choices=SITES);ap.add_argument('--prior',choices=PRIORS);a=ap.parse_args()
    rows=[];sources=[]
    for site in [a.site] if a.site else SITES:
        for prior in [a.prior] if a.prior else PRIORS:
            root=OUT/'direct_stage1_v2'/(site+'__'+prior)
            with np.load(root/'evaluation.npz') as e,np.load(root/'values.npz') as v:
                area=e['area'];cell=e['cell'];valid=e['in_eval']&e['scoring_allowed']&e['has_mvs']&(cell<4)
                valid &= np.abs(e['p_mvs'])/np.sqrt(v['sigma_prior'].astype(np.float64)**2+v['sigma_mvs'].astype(np.float64)**2)>3
            for variant,analytic in VARS.items():
                p=OUT/'patch_z'/f'{site}__{prior}__{variant}_{prior}_s0.npz'
                if not p.exists():continue
                q=OUT/'patch_z'/f'{site}__{prior}__analytic_{analytic}.npz'
                with np.load(p) as z,np.load(q) as pred:
                    assert np.array_equal(z['patch_id'],pred['patch_id'])
                    actual=z['side'];expected=pred['side']
                sources.append(dict(path=str(p),sha256=sha(p),analytic=str(q),analytic_sha256=sha(q)))
                for name,m in [('unexplained',valid),('unexplained_cell_1',valid&(cell==1)),('unexplained_cell_2',valid&(cell==2))]:
                    A=float(area[m].sum());N=int(m.sum());same=float(area[m&(actual==expected)].sum())
                    for i,ename in enumerate(['prior','mvs','other']):
                        for j,aname in enumerate(['prior','mvs','other','no_surface']):
                            x=m&(expected==i)&(actual==j)
                            rows.append(dict(site=site,prior=prior,variant=variant,subset=name,analytic_side=ename,trained_side=aname,
                                patches=int(x.sum()),area_m2=float(area[x].sum()),denominator_patches=N,denominator_area_m2=A,
                                same_side_area_m2=same,same_side_percent=100*same/A if A else None,
                                minimum_sample='PASS' if N>=100 else 'INSUFFICIENT',origin='[이 발주에서 냄]'))
    tag='__'.join(x for x in [a.site,a.prior] if x) or 'all'
    save(f'/docs/tables/sides_{tag}.json',dict(rows=rows,sources=sources,scientific_verdict=None))
    if rows:
        with Path(f'/docs/tables/sides_{tag}.csv').open('w') as f:
            w=csv.DictWriter(f,list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    print('side table rows',len(rows),flush=True)

if __name__=='__main__':main()
