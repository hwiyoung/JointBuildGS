"""Order 6.4: geometry-only join, before GT scoring or any training.

Primary rule: Euclidean 3-D nearest centre in registered training coordinates,
same prior, <= 0.05 m. Raw-centre distances are diagnostic only. Evaluation
membership is the frozen stage-1 in_eval mask, without reading outcome labels.
"""
import csv
import json
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
from inputs import OUT, S0, S1, W, SITES, PRIORS, sha, save

def quant(x):
    return dict(zip(['min','p25','median','p75','p95','max'],
                    np.quantile(x, [0,.25,.5,.75,.95,1]).tolist()))

def load_geometry(prior):
    parts, sources = [], []
    for vf in sorted((OUT/'vfile_v1').glob(f'*__{prior}__vfile.npz')):
        wf = W/'patch_values'/vf.name.replace('__vfile.npz','__R1.5.npz')
        with np.load(vf, allow_pickle=False) as v, np.load(wf, allow_pickle=False) as w:
            assert np.array_equal(v['patch_id'], w['patch_id']), wf
            assert not w['holdout'].any(), 'sealed patches must not enter this check'
            parts.append({k:w[k] for k in ['centre','raw_centre','patch_id','normal']})
        sources.append(dict(vfile=str(vf), vfile_sha256=sha(vf), geometry=str(wf), geometry_sha256=sha(wf)))
    return {k:np.concatenate([p[k] for p in parts]) for k in parts[0]}, sources

def main():
    rows=[]; all_sources=[]
    for prior in PRIORS:
        g, sources = load_geometry(prior)
        tree=cKDTree(g['centre']); rawtree=cKDTree(g['raw_centre'])
        all_sources.extend(sources)
        for site in SITES:
            I=S0/'fork_inputs/s61'/site
            sf=I/f'store_{prior}.npz'
            rf=S1/'regions_v3'/f'regions_ext_v3_{site}_{prior}.npz'
            with np.load(sf, allow_pickle=False) as z:
                centres=z['loc_center']; shift=z['frame_shift']
            with np.load(rf, allow_pickle=False) as z:
                assert np.array_equal(centres,z['centre'])
                ev=z['in_eval'].astype(bool)
            d,idx=tree.query(centres,workers=8)
            dr,_=rawtree.query(centres-shift,workers=8)
            joined=d<=.05
            row=dict(site=site,prior=prior,patches=len(centres),joined_patches=int(joined.sum()),
                joined_fraction=float(joined.mean()),eval_patches=int(ev.sum()),eval_joined_patches=int((joined&ev).sum()),
                eval_joined_fraction=float(joined[ev].mean()),distance_m=quant(d),eval_distance_m=quant(d[ev]),
                raw_geometry_diagnostic_joined_fraction=float((dr<=.05).mean()),
                raw_geometry_diagnostic_eval_fraction=float((dr[ev]<=.05).mean()),
                raw_geometry_diagnostic_distance_m=quant(dr),stage1_frame_shift_m=shift.tolist(),
                rule='registered centre 3D nearest, same prior, <=0.05m; denominator all stage-1 patches',
                gate='PASS' if joined.mean()>=.95 else 'STOP',
                store=str(sf),store_sha256=sha(sf),eval_range_file=str(rf),eval_range_sha256=sha(rf),
                scientific_verdict=None)
            out=OUT/'checks/join'/f'{site}__{prior}.npz';out.parent.mkdir(parents=True,exist_ok=True)
            np.savez_compressed(out,stage1_patch=np.arange(len(d)),vfile_patch_id=g['patch_id'][idx],
                distance_m=d,joined=joined,in_eval=ev,nearest_index=idx,raw_distance_m=dr)
            row['mapping_sha256']=sha(out)
            rows.append(row)
            save(OUT/'checks/join_patches.json',dict(rows=rows,sources=all_sources,scientific_verdict=None))
            print(site,prior,'all',row['joined_fraction'],'eval',row['eval_joined_fraction'],
                  'raw eval',row['raw_geometry_diagnostic_eval_fraction'],row['gate'],flush=True)
    save(Path('/docs/tables/patch_join.json'),dict(rows=rows,sources=all_sources,scientific_verdict=None))
    cols=['site','prior','patches','joined_patches','joined_fraction','eval_patches','eval_joined_patches','eval_joined_fraction','gate']
    with Path('/docs/tables/patch_join.csv').open('w') as f:
        writer=csv.DictWriter(f,cols,extrasaction='ignore');writer.writeheader();writer.writerows(rows)

if __name__=='__main__':
    main()
