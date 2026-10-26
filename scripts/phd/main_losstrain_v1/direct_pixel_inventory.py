"""Count amended fallback pixels through the exact inherited stage-1 maps.

No new pixel-coverage gate: amended 6.4 uses patch area. Record ratios against
all image pixels and mapped positive-prior-depth pixels, both explicitly.
"""
import json
import numpy as np
from inputs import OUT,S0,SITES,PRIORS,save,sha
from direct_rules import RULES

def main():
    root=OUT/RULES['revision'];rows=[]
    for site in SITES:
        I=S0/'fork_inputs/s61'/site;split=json.loads((I/'split.json').read_text())
        for prior in PRIORS:
            unit=site+'__'+prior;dest=root/unit
            with np.load(dest/'values.npz',allow_pickle=False) as z:
                flags={k:z[k] for k in ['missing_als_prior','outside_uncert','direct_prior','has_mvs']}
                flags['invalid_normal']=~np.isclose(np.linalg.norm(z['normal'],axis=1),1,atol=1e-5)
            with np.load(dest/'evaluation.npz',allow_pickle=False) as z:ev=z['in_eval']
            N=len(ev);views=[]
            for name in split['train']:
                lf=I/f'maps/locmap_{prior}'/f'{name}.npy';pf=I/f'maps/prior_{prior}'/f'{name}.npy'
                if not pf.exists():pf=I/f'maps/prior_{prior}/raw_depth'/f'{name}.npy'
                loc=np.load(lf);P=np.load(pf)
                assert loc.shape==P.shape==(741,1024) and np.equal(loc,loc.astype(np.int64)).all()
                assert not (loc>=N).any()
                has=(loc>=0)&(loc<N);valid=np.isfinite(P)&(P>0);on=has&valid
                ids=loc[on].astype(np.int64);row=dict(view=name,pixels=P.size,prior_patch_pixels=int(on.sum()),
                    eval_prior_patch_pixels=int(ev[ids].sum()),no_patch_prior_pixels=int((valid&~has).sum()))
                for k,mask in flags.items():
                    row[k+'_pixels']=int(mask[ids].sum());row['eval_'+k+'_pixels']=int((mask[ids]&ev[ids]).sum())
                row.update(locmap_sha256=sha(lf),prior_depth_sha256=sha(pf));views.append(row)
            counts={k:sum(r[k] for r in views) for k in views[0] if k.endswith('pixels')}
            row=dict(site=site,prior=prior,views=len(views),**counts,
                fractions={k:dict(all_image_pixels=counts[k+'_pixels']/counts['pixels'],
                    mapped_prior_pixels=counts[k+'_pixels']/counts['prior_patch_pixels'],
                    eval_mapped_prior_pixels=counts['eval_'+k+'_pixels']/counts['eval_prior_patch_pixels'])
                    for k in flags},evaluation_pixels='mapped patch centre has frozen stage-1 in_eval; not a new geometric crop',
                pixel_coverage_gate='NOT_APPLICABLE_IN_AMENDED_ORDER',scientific_verdict=None)
            save(dest/'pixels.json',dict(summary=row,per_view=views));rows.append(row)
            save('/docs/tables/direct_stage1_pixels.json',dict(rows=rows,scientific_verdict=None))
            print(unit,'fallback',row['fractions']['missing_als_prior'],'invalid-normal pixels',row['invalid_normal_pixels'],flush=True)

if __name__=='__main__':main()
