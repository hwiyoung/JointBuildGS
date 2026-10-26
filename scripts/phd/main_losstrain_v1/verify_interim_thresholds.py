"""Check the requested 8.4 interim values directly against both saved patch arrays."""
import json
import math
from pathlib import Path
import numpy as np
from inputs import OUT,save,sha


def main():
    path=Path('/docs/tables/interim_thresholds.json');rows=json.loads(path.read_text())['rows']
    assert len(rows)==21
    root=OUT/'direct_stage1_v2/B173nb_b10__ALS'
    with np.load(root/'evaluation.npz') as z:e={k:z[k] for k in ['area','cell','in_eval','scoring_allowed','has_mvs','p_mvs','p_gt','tau']}
    with np.load(root/'values.npz') as z:
        unexpl=np.abs(e['p_mvs'])/np.sqrt(z['sigma_prior'].astype(float)**2+z['sigma_mvs'].astype(float)**2)>3
    ok=e['in_eval']&e['scoring_allowed'];both=ok&e['has_mvs']&(e['cell']<4)
    masks={'all_0_3':both,'unexplained':both&unexpl}
    masks.update({f'cell_{i}':ok&(e['cell']==i) for i in range(6)})
    masks.update({f'unexplained_cell_{i}':both&unexpl&(e['cell']==i) for i in [1,2]})
    cached={};maximum_difference=0.
    for r in rows:
        values=[];counts=[];m=masks[r['subset']]
        for source in r['seed_sources']:
            p=Path(source['source'])
            assert sha(p)==source['sha256']
            if str(p) not in cached:
                with np.load(p) as z:cached[str(p)]=z['z']
            z=cached[str(p)];metric=r['metric'];error=np.abs(z-e['p_gt'])
            if metric=='error_patch_median_m':
                finite=m&np.isfinite(error);N=int(finite.sum());value=float(np.median(error[finite])) if N else None
            else:
                N=int(m.sum());area=float(e['area'][m].sum())
                hit=(error<=e['tau']) if metric=='within_tau_percent' else ~np.isfinite(z)
                value=100*float(e['area'][m&hit].sum())/area if area else None
            assert N==source['N'];values.append(value);counts.append(N)
        assert r['N']==min(counts) and r['pooled'] is None
        for a,b in zip(values,[r['seed_0'],r['seed_1']]):
            assert a is not None and b is not None
            delta=abs(a-b);maximum_difference=max(maximum_difference,delta);assert delta<=1e-10
        case=2.8*abs(values[0]-values[1])/math.sqrt(2)
        three=None if r['metric']=='error_patch_median_m' else 300/min(counts)
        assert abs(case-r['case_spread'])<=1e-10
        assert r['three_points']==three
        assert abs(max(x for x in [case,three] if x is not None)-r['threshold'])<=1e-10
    result=dict(status='PASS',rows=len(rows),seed_patch_arrays=len(cached),max_absolute_difference=maximum_difference,
        direct_recomputation_from_patch_z=True,table_sha256=sha(path),scientific_verdict=None)
    save(OUT/'checks/interim_threshold_verification.json',result)
    save('/docs/provenance/interim_threshold_verification.json',result)
    print(result,flush=True)


if __name__=='__main__':main()
