"""Recount delivered matrices and exact gate subset, independently of reducer."""
import numpy as np
from common import *
from recount import load_eval
rows=[]
for site in SITES:
    e,_=load_eval(site,'ALS')
    table=json.loads((DOC/'tables'/f'multiview_summary_{site}_ALS.json').read_text())['rows']
    for res in ['nojudge_ALS_s0','lt_dynnow_ALS_s0']:
        root=OUT/'multiview'/site/res
        with np.load(root/'patch_views.npz') as f:z={k:f[k] for k in f.files}
        ids=z['patch_id'];c=z['classification'];count=np.count_nonzero(c==2,axis=1)
        assert np.array_equal(count,z['float_photo_count']);assert np.array_equal((c>0).sum(1),z['in_frame_photo_count'])
        assert np.isin(c,[0,1,2,3,4]).all()
        assert np.array_equal((c==1),(np.abs(z['signed_normal_delta_m'])<=e['tau'][ids,None])&np.isin(c,[1,2,3]))
        num=den=original=0
        for view in z['view_names']:
            with np.load(root/(view+'.npz')) as f:
                ff=f['float_observed'];valid=f['valid'];delta=f['signed_normal_delta_m'];p=f['patch_id']
                # Saved float32 normal delta may lie at threshold; classification
                # remains the original float64 comparison, audit tolerance only.
                assert np.all(delta[ff]>e['tau'][p[ff]]-1e-5)
                num+=int(np.count_nonzero(ff&f['all_own_dead']));den+=int(np.count_nonzero(ff));original+=len(p)
        r=next(r for r in table if r['result']==res and r['case']=='전체')
        assert num==r['all_own_dead'] and den==r['float_observed_pixels'] and original==r['full_gate_original_pixels']
        assert np.isclose(e['area'][ids[count>0]].sum()/e['area'][ids].sum(),r['at_least_one_float_photo_area_fraction'])
        rows.append(dict(site=site,result=res,patches=len(ids),views=c.shape[1],gate_subset_pixels=den,all_dead=num,status='PASS'))
save(DOC/'provenance/multiview_validation.json',dict(at=now(),status='PASS',rows=rows,scientific_verdict=None))
print('all six multiview matrices and pixel denominators PASS')
