"""Independent source-column, derived-flag and NPZ/CSV round-trip verification."""
import argparse,json
from pathlib import Path
import numpy as np
import pandas as pd
from mesh_common import O,D,C,PH,sha,dump,now
from column_store import unpack_npz

def equal(a,b):
    if a.dtype.kind in 'fc':return np.array_equal(a,b,equal_nan=True)
    return np.array_equal(a,b)

def verify(prior):
    f=O/'patch_table'/f'{prior}_patch_table.npz';z=unpack_npz(f,O/'cache/validation_columns'/prior);cfg=json.loads((C/'meshpatch_v1.json').read_text())
    fields=cfg['patches']['preserve']+['raw_centre','tau','gt_status','mvs_a_status','mvs_p','gt_p']
    files=sorted((PH/'main_widen0_v2/PHD-MAIN-WIDEN0-v2/patch_values').glob(f'*__{prior}__R1.5.npz'))
    offsets=[];n=0;area=0.;holdout=0
    for x in files:
        with np.load(x) as s:
            size=len(s['patch_id']);offsets.append((x,n,n+size));n+=size;area+=float(s['area'].sum());holdout+=int(s['holdout'].sum())
    assert holdout==0
    for field in fields:
        values=z[field];assert len(values)==n
        for x,a,b in offsets:
            with np.load(x) as s:
                assert values.dtype==s[field].dtype,(field,'dtype changed')
                assert equal(values[a:b],s[field]),(field,x.name)
    # Check unique source IDs without materializing a second huge Unicode array.
    ids=z['patch_id'];seen=set()
    for st in range(0,n,50000):seen.update(ids[st:st+50000].tolist())
    assert len(seen)==n;del seen
    assert np.isclose(z['area'].sum(),area,rtol=1e-14,atol=1e-8)
    assert equal(z['mvs_absent'],~np.isfinite(z['mvs_p']))
    gt=(z['gt_status']==0)&np.isfinite(z['gt_p']);correct=gt&(np.abs(z['gt_p'].astype(np.float64))<=z['tau'].astype(np.float64))
    assert equal(z['prior_within_tau_code'],np.where(gt,correct.astype(np.int8),-1))
    assert equal(z['prior_within_tau'],np.where(gt,np.where(correct,'맞음','틀림'),'확인 불가'))
    r=z['region_code'];assert np.isin(r,[-1,2,3,4,5,11,12,13,14]).all();assert (r[~gt]==-1).all()
    assert (r[z['region_geometry_joined']==False]==-1).all()
    assert (z['mvs_face_id'][z['mvs_absent']]==-1).all()
    # CSV is a second encoding of every NPZ field, including all string cells and NaNs.
    table={k:z[k] for k in z};flat={}
    for k,v in table.items():
        if v.ndim==1:flat[k]=v
        else:
            for j,axis in enumerate('xyz'):flat[k+'_'+axis]=v[:,j]
    start=0
    for frame in pd.read_csv(f.with_suffix('.csv.gz'),chunksize=50000,dtype=str,keep_default_na=False):
        assert set(frame.columns)==set(flat)
        end=start+len(frame)
        for k,v in flat.items():
            a=frame[k].to_numpy();b=v[start:end]
            if b.dtype.kind in 'fc':a=np.where(a=='',np.nan,a).astype(np.float64) if a.dtype.kind in 'OUS' else a
            elif b.dtype.kind in 'iu':a=np.where(a=='',-1,a).astype(b.dtype)
            elif b.dtype.kind=='b':a=np.array([str(x).lower()=='true' for x in a])
            assert equal(a,b),(k,start,'CSV round trip')
        start=end
    assert start==n
    summary=json.loads((D/'tables'/f'patch_{prior}_table.json').read_text());regions=[]
    for row in summary['region_rows']:
        site=row['site'];ref=np.load(PH/'main_stage1_v1/PHD-MAIN-STAGE1-v1/regions_v3'/f'regions_ext_v3_{site}_{prior}.npz')
        indices=z['region_source_row_'+site];used=np.unique(indices[indices>=0]);assert len(used)==(indices>=0).sum(),'non-injective regional join'
        joined=indices>=0;srcrows=indices[joined]
        assert ref['in_eval'][srcrows].all()
        assert np.all(np.linalg.norm(z['raw_centre'][joined]-(ref['centre'][srcrows]-ref['frame_shift']),axis=1)<1e-6)
        assert np.allclose(z['area'][joined],ref['area'][srcrows],rtol=1e-8,atol=1e-9)
        assigned=z['region_code_'+site]>=0
        assert np.array_equal(z['region_code_'+site][assigned],ref['code_ext_v3'][indices[assigned]])
        m=ref['in_eval'].copy();m[used]=False
        regions.append(dict(row,reference_unjoined_patches=int(m.sum()),reference_unjoined_area_m2=float(ref['area'][m].sum())))
    result=dict(prior=prior,status='PASS',verified_at=now(),patches=n,area_m2=area,source_columns=fields,all_npz_csv_columns_match=True,
        holdout_patches=holdout,region_rows=regions,face_benchmark_status='PASS' if z['mvs_face_benchmark_passed'].all() else 'FAIL',
        note='Encoding and source conservation PASS does not override the separate face benchmark or unavailable regional data.',scientific_verdict=None,provenance='[이 발주에서 냄]')
    dump(D/'tables'/f'patch_{prior}_validation.json',result);print(json.dumps(result,ensure_ascii=False),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('prior',choices=['ALS','LoD2']);verify(p.parse_args().prior)
