"""Reply 1: audit all memberships, exclude shared cores before decoding values.

Only identity metadata from holdout may be read here. Stage B is not implemented
by this entry point and requires a separate user decision.
"""
import json,time,zipfile
import numpy as np
from preflight import C,D,O,R,Path,dump,sha,now
from selected_npz import selected,building_ids
from prepare import array

def main():
    start=time.monotonic();cfg=json.loads((C/'judgecheck_v1.json').read_text())
    assert sha(C/'judgecheck_v1.json')==json.loads((C/'judgecheck_v1.reply1.lock.json').read_text())['config_sha256']
    out=O/'r1';wanted=set(cfg['scope']['development']);src=cfg['sources'];jn=Path(src['judgenum']);w=Path(src['widen'])
    # Membership numbers only. No holdout coordinates, scores, labels or curves.
    hm=json.loads((jn/'holdout/scope_membership.json').read_text());held=set(hm['buildings'])
    assert not wanted&held
    jcfg=json.loads((R/'configs/phd/main_judgenum_v1/judgenum_v1.json').read_text());excluded={r['building'] for r in jcfg['scope']['excluded']}
    plan=[];auditrows=[];auditcounts=[]
    for p in sorted((jn/'inputs').glob('*.npz')):
        tile,prior=p.stem.split('__')
        with zipfile.ZipFile(p) as z:
            bids=building_ids(z);assert set(bids)<=wanted
            ids=array(z,'patch_id');kind=array(z,'kind');area=array(z,'area')
        keep=np.isin(kind,cfg['scope']['kinds'][prior]);drop=np.zeros(len(ids),bool);photo=[]
        wf=w/'patch_values'/f'{tile}__{prior}__R1.5.npz'
        with zipfile.ZipFile(wf) as z:
            wids=array(z,'patch_id');wb=array(z,'building')
        identity=dict(zip(wids,wb))
        for k,root in [(1,Path(src['roof_photo'])),(2,Path(src['wall_photo']))]:
            ix=np.flatnonzero(keep&(kind==k))
            if not len(ix):continue
            mp=root/'geometry'/f'{tile}__{prior}__mapping.npz';pp=root/'points'/p.name
            with zipfile.ZipFile(mp) as z:
                pid=array(z,'patch_id');owner=array(z,'point_index')
            if not set(pid)<=set(identity):
                # Rare cross-split mapping: ID fields only from the sealed table.
                hp=w/'holdout/patch_values'/wf.name
                with zipfile.ZipFile(hp) as z:identity.update(zip(array(z,'patch_id'),array(z,'building')))
            assert set(pid)<=set(identity),'STOP_INPUT_ALIGNMENT: unmapped photo member ID'
            membership={}
            for pi,b in zip(owner,[identity[x] for x in pid]):membership.setdefault(int(pi),set()).add(str(b))
            inverse=dict(zip(pid,owner));assigned=np.array([inverse[x] for x in ids[ix]],int)
            with zipfile.ZipFile(pp) as z:
                gi=array(z,'geometry_index');pids=array(z,'point_id')
                stored=array(z,'building_ids') if 'building_ids.npy' in z.namelist() else None
            gl={int(g):i for i,g in enumerate(gi)};assert set(assigned)<=set(gl)
            safe=[];shared=0
            for ownerid in np.unique(assigned):
                mm=set(membership[int(ownerid)])
                if stored is not None:mm|=set(str(stored[gl[int(ownerid)]]).split(';'))
                forbidden=mm-wanted
                if forbidden:
                    assert forbidden<=held|excluded,'STOP_INPUT_ALIGNMENT: unknown nondevelopment member'
                    jj=ix[assigned==ownerid];drop[jj]=True;shared+=1
                    auditrows.append(dict(tile=tile,prior=prior,kind=k,point_id=str(pids[gl[int(ownerid)]]),
                        geometry_index=int(ownerid),patch_ids=ids[jj].tolist(),count=len(jj),area_m2=float(area[jj].sum()),
                        reason='experiment' if forbidden&excluded else 'holdout',
                        member_buildings=sorted(mm),identity_only=True))
                else:safe.append(int(ownerid))
            auditcounts.append(dict(tile=tile,prior=prior,kind=k,photo_points_checked=len(np.unique(assigned)),
                shared_photo_points=shared,all_member_IDs_reconstructed=True))
            photo.append(dict(kind=k,point_file=str(pp),mapping_file=str(mp),safe_geometry_indices=safe))
        plan.append(dict(path=str(p),tile=tile,prior=prior,keep=keep&~drop,drop=drop,photo=photo))
    prioraudit=json.loads((O/'photo_scope_audit.json').read_text());original=set(x for row in prioraudit['rows'] for x in row['selected_patch_ids'])
    current=set(x for r in auditrows for x in r['patch_ids']);assert original<=current and len(original)==73
    audit=dict(at=now(),status='PASS_SCOPE_EXCLUSIONS_REPLY1',rows=auditrows,coverage=auditcounts,
        excluded_core_count=sum(r['count'] for r in auditrows),excluded_area_m2=sum(r['area_m2'] for r in auditrows),
        holdout_measurements_read=False,identity_only=True,all_calculations_exclude_shared_cores=True,
        initial_22_curves_not_consumed=True,scientific_verdict=None)
    dump(out/'scope_audit.json',audit);dump(D/'tables/scope_audit_reply1.json',audit)
    lock=dict(at=now(),config_sha256=sha(C/'judgecheck_v1.json'),scope_audit_sha256=sha(out/'scope_audit.json'),
        source_sha256={p.name:sha(p) for p in Path(__file__).parent.glob('*.py')},scientific_verdict=None)
    dump(C/'stage_a_inputs.reply1.lock.json',lock)
    records=[]
    for planrow in plan:
        p=Path(planrow['path']);tile=planrow['tile'];prior=planrow['prior'];keep=planrow['keep']
        if not keep.any():continue
        with zipfile.ZipFile(p) as z:
            d={k:selected(z,k,keep) for k in ['patch_id','kind','area','centre','building','normal','tangent1','tangent2','surf','roof_type','u_prior','source_extra','normal_defined']}
        assert not set(d['patch_id'])&current
        wf=w/'patch_values'/f'{tile}__{prior}__R1.5.npz'
        with zipfile.ZipFile(wf) as z:
            ids=array(z,'patch_id');take=np.isin(ids,d['patch_id']);indices={p:i for i,p in enumerate(ids[take])};ix=np.array([indices[p] for p in d['patch_id']])
            for k in ['u_mvs','mvs_a_a','holdout']:d[k]=selected(z,k,take)[ix]
            evaluation={k:selected(z,k,take)[ix] for k in ['gt_p','gt_status','cell']};evaluation['patch_id']=d['patch_id']
        assert not d['holdout'].any()
        d['photo_point_id']=np.full(len(d['patch_id']),'',dtype='<U96')
        for pp in planrow['photo']:
            kind=pp['kind'];ix=np.flatnonzero(d['kind']==kind)
            with zipfile.ZipFile(pp['mapping_file']) as z:
                pid=array(z,'patch_id');mask=np.isin(pid,d['patch_id'][ix]);owners=dict(zip(pid[mask],selected(z,'point_index',mask)))
            with zipfile.ZipFile(pp['point_file']) as z:
                gi=array(z,'geometry_index');take=np.isin(gi,pp['safe_geometry_indices'])
                pd={k[:-4]:selected(z,k[:-4],take) for k in z.namelist() if k.endswith('.npy')}
            assert not pd['holdout'].any()
            look=dict(zip(pd['geometry_index'],pd['point_id']))
            for i in ix:d['photo_point_id'][i]=look[owners[d['patch_id'][i]]]
            dest=out/'photo_inputs'/f'{tile}__{prior}__{kind}.npz';dest.parent.mkdir(exist_ok=True)
            np.savez_compressed(dest,**pd)
        assert (d['photo_point_id']!='').all()
        for sub,data in [('inputs',d),('evaluation_inputs',evaluation)]:
            dest=out/sub/p.name;dest.parent.mkdir(exist_ok=True);np.savez_compressed(dest,**data)
        for k in np.unique(d['kind']):
            m=d['kind']==k;exc=[r for r in auditrows if r['tile']==tile and r['prior']==prior and r['kind']==int(k)]
            records.append(dict(tile=tile,prior=prior,kind=int(k),count=int(m.sum()),area_m2=float(d['area'][m].sum()),
                excluded_count=sum(r['count'] for r in exc),excluded_area_m2=sum(r['area_m2'] for r in exc),
                missing_u_mvs=int((~np.isfinite(d['u_mvs'][m])).sum()),missing_u_prior=int((~np.isfinite(d['u_prior'][m])).sum())))
        print('SAFE_JOIN',tile,prior,len(d['patch_id']),flush=True)
    receipt=dict(at=now(),status='PASS_SAFE_DEVELOPMENT_INPUTS',rows=records,seconds=time.monotonic()-start,
        config_sha256=sha(C/'judgecheck_v1.json'),scope_sha256=sha(out/'scope_audit.json'),
        initial_preparation_consumed=False,excluded_patch_ids_absent=True,scientific_verdict=None)
    dump(out/'input_receipt.json',receipt);dump(D/'tables/input_receipt_reply1.json',receipt)
    print(json.dumps({k:v for k,v in receipt.items() if k!='rows'},ensure_ascii=False))

if __name__=='__main__':main()
