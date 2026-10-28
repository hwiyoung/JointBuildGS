"""Actual-image independent pairwise NCC replay and earlier wall-control agreement."""
from common import *
from cameras import Cameras
from verify_image_score import reference
from wall_report import point_sets
def main():
    cam=Cameras();rng=np.random.default_rng(20261028);rows=[]
    for tile,p in point_sets('pilot'):
        ids=np.flatnonzero((p['selected_count']>=3)&(p['texture']>=5))
        if not len(ids):continue
        i=int(rng.choice(ids));score=reference(cam,p,i);stored=p['curve'][i].astype(float);valid=np.isfinite(score)&np.isfinite(stored)
        finite_diff=int((np.isfinite(score)!=np.isfinite(stored)).sum());diff=abs(score[valid]-stored[valid])
        assert finite_diff==0 and (not len(diff) or diff.max()<.01)
        rows.append(dict(tile=tile,point_id=p['point_id'][i],heights=int(valid.sum()),finite_disagreement=finite_diff,max_difference=float(diff.max()) if len(diff) else None))
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
    rec=dict(at=now(),status='PASS' if rows else 'UNAVAILABLE_NO_ELIGIBLE_CURVE',sampled_points=len(rows),pairwise_replay=rows,earlier_4906968_walls=compare,scientific_verdict=None)
    dump(O/'gates/independent_replay.json',rec);dump(D/'tables/independent_replay.json',rec)
    print('independent wall replay',rec['status'],len(rows),flush=True)
if __name__=='__main__':main()
