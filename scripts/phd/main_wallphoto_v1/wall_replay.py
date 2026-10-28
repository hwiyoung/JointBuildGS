"""Actual-image independent pairwise NCC replay and earlier wall-control agreement."""
from common import *
from cameras import Cameras
from verify_image_score import reference
from wall_report import point_sets
from replay_precision import reference_at_sampler_precision
from curves import compute
def main():
    cam=Cameras();rng=np.random.default_rng(20261028);rows=[]
    for tile,p in point_sets('pilot'):
        ids=np.flatnonzero((p['selected_count']>=3)&(p['texture']>=5))
        if not len(ids):continue
        i=int(rng.choice(ids));score=reference(cam,p,i);stored=p['curve'][i].astype(float);valid=np.isfinite(score)&np.isfinite(stored)
        finite_diff=int((np.isfinite(score)!=np.isfinite(stored)).sum());diff=abs(score[valid]-stored[valid])
        precision,details=reference_at_sampler_precision(cam,p,i)
        precision_valid=np.isfinite(precision)&np.isfinite(stored)
        precision_diff=abs(precision[precision_valid]-stored[precision_valid])
        assert np.array_equal(np.isfinite(precision),np.isfinite(stored)),(tile,i,'sampler precision finite status')
        assert not len(precision_diff) or precision_diff.max()<.01,(tile,i,'sampler precision score')
        assert not len(diff) or diff.max()<.01,(tile,i,'float64 score')
        boundaries=[]
        for k in np.flatnonzero(np.isfinite(score)!=np.isfinite(stored)):
            # Only the demonstrated inherited zero-variance rounding boundary is classified.
            # No generic mismatch exemption or changed scoring threshold is permitted.
            valid_views=details['valid'][:,k]
            boundary=valid_views&(details['float64_std'][:,k]<=1e-6)&(details['torch_std'][:,k]>1e-6)&(details['source_range'][:,k]==0)
            assert not np.isfinite(score[k]) and np.isfinite(stored[k]) and boundary.any(),(tile,i,int(k),'unexplained finite mismatch')
            boundaries.append(dict(height=float(p['heights'][i,k]),images=p['selected_images'][i][np.flatnonzero(boundary)],float64_std=details['float64_std'][boundary,k],float32_std=details['torch_std'][boundary,k],source_pixel_range=details['source_range'][boundary,k]))
        one={k:v[i:i+1] for k,v in p.items()};fresh,_=compute(one,one,'cpu',chunk_points=1)
        exact=bool(np.array_equal(fresh['curve'][0].astype(np.float16),p['curve'][i],equal_nan=True))
        assert exact,(tile,i,'production replay differs')
        rows.append(dict(tile=tile,point_id=p['point_id'][i],heights=int(valid.sum()),finite_disagreement=finite_diff,max_difference=float(diff.max()) if len(diff) else None,float64_status='FAIL_FINITE_STATUS' if finite_diff else 'PASS',sampler_precision_status='PASS',sampler_precision_max_difference=float(precision_diff.max()) if len(precision_diff) else None,production_replay_float16_equal=exact,constant_source_variance_boundaries=boundaries))
        if len(rows)==4:break
    compare=[];refroot=Path('/art/phase-payloads/phd/main_photocheck_v1/PHD-MAIN-PHOTOCHECK-v1')
    for tile,p in point_sets('pilot'):
        f=refroot/'work/pilot'/f'{tile}__LoD2.npz'
        if not f.exists():continue
        old=npz(f);a=np.flatnonzero((p['building']=='DEBY_LOD2_4906968')&(p['kind']==2));b=np.flatnonzero((old['building']=='DEBY_LOD2_4906968')&(old['kind']==2))
        if not len(a) or not len(b):continue
        keys={tuple(np.round(old['centre'][i],8)):int(i) for i in b};matched=[(int(i),keys[tuple(np.round(p['centre'][i],8))]) for i in a if tuple(np.round(p['centre'][i],8)) in keys]
        ia=np.array([x for x,_ in matched],int);ib=np.array([y for _,y in matched],int)
        same_geometry=bool(np.allclose(p['normal'][ia],old['normal'][ib],atol=1e-10) and np.allclose(p['tangent1'][ia],old['tangent1'][ib],atol=1e-10))
        assert same_geometry and len(matched)==len(a)
        delta=abs(p['curve'][ia].astype(float)-old['curve'][ib].astype(float));valid=np.isfinite(delta)
        compare.append(dict(tile=tile,new_wall_points=len(a),old_wall_points=len(b),matched=len(matched),geometry_equal=same_geometry,selected_photos_equal=bool(np.array_equal(p['selected_images'][ia],old['selected_images'][ib])),judgments_equal=int((p['judgment'][ia]==old['judgment'][ib]).sum()),judgments_total=len(ia)*15,max_curve_difference=float(delta[valid].max()) if valid.any() else None,old_file_sha256=sha(f),old_device=load(f.with_suffix('.json')).get('device')))
    limitations=any(r['finite_disagreement'] for r in rows)
    rec=dict(at=now(),status=('PASS_REFERENCE_REPRODUCTION_WITH_PRECISION_LIMITATION' if limitations else 'PASS') if rows else 'UNAVAILABLE_NO_ELIGIBLE_CURVE',float64_finite_check='FAIL_FINITE_STATUS' if limitations else 'PASS',limitation='Inherited float32 interpolation and variance reduction can treat a constant image patch as nonzero variance. Preserved per same-code order; no scoring/config/threshold change. This sample does not bound whole-area frequency.' if limitations else None,sampled_points=len(rows),pairwise_replay=rows,earlier_4906968_walls=compare,scientific_verdict=None)
    dump(O/'gates/independent_replay.json',rec);dump(D/'tables/independent_replay.json',rec)
    print('independent wall replay',rec['status'],len(rows),flush=True)
if __name__=='__main__':main()
