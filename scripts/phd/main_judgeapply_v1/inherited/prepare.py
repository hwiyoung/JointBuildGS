"""Select development rows by IDs before decoding geometry or photo scores."""
import json
import time
import zipfile
import numpy as np
from preflight import C,D,O,R,Path,dump,sha,now
from selected_npz import selected,building_ids


def array(z,k):
    with z.open(k+'.npy') as f:
        return np.lib.format.read_array(f,allow_pickle=False)


def main():
    t0=time.monotonic();cfg=json.loads((C/'judgecheck_v1.json').read_text())
    assert sha(C/'judgecheck_v1.json')==json.loads((C/'judgecheck_v1.initial.lock.json').read_text())['config_sha256']
    # Identity-only scope audit must succeed before decoding any photo value.
    # Initial join is preserved in /out/source_snapshots/initial_join/prepare.py.
    from audit_photo_scope import audit
    gate=audit()
    if gate['status']!='PASS_PHOTO_POINT_SCOPE':
        raise SystemExit('STOP_PHOTO_POINT_SCOPE_CONFLICT: user scope decision required; no photo values read')
    wanted=set(cfg['scope']['development']);w=Path(cfg['sources']['widen']);jn=Path(cfg['sources']['judgenum'])
    lock=C/'prepare.implementation.lock.json'
    if not lock.exists():
        dump(lock,dict(at=now(),before_first_calculation=True,config_sha256=sha(C/'judgecheck_v1.json'),
            sources={p.name:sha(p) for p in Path(__file__).parent.glob('*.py')},scientific_verdict=None))
    records=[];failures=[];seen={'ALS':set(),'LoD2':set()}
    for p in sorted((jn/'inputs').glob('*.npz')):
        tile,prior=p.stem.split('__');dst=O/'inputs'/p.name
        dst.parent.mkdir(exist_ok=True,parents=True)
        with zipfile.ZipFile(p) as z:
            bids=building_ids(z)
            assert set(bids)<=wanted,'JN input contains nondevelopment IDs'
            kind=array(z,'kind');mask=np.isin(kind,cfg['scope']['kinds'][prior])
            keys=['patch_id','kind','area','centre','building','normal','tangent1','tangent2','surf','roof_type','u_prior']
            d={k:selected(z,k,mask) for k in keys}
        if not len(d['patch_id']):continue
        wf=w/'patch_values'/f'{tile}__{prior}__R1.5.npz'
        with zipfile.ZipFile(wf) as z:
            ids=array(z,'patch_id');take=np.isin(ids,d['patch_id']);picked=ids[take]
            pos={v:i for i,v in enumerate(picked)};idx=np.array([pos[v] for v in d['patch_id']])
            assert len(picked)==len(d['patch_id'])
            for k in ['u_mvs','mvs_a_a','gt_p','gt_status','cell','holdout']:
                if k+'.npy' not in z.namelist():
                    failures.append(dict(file=str(wf),reason='required key absent',key=k));continue
                d[k]=selected(z,k,take)[idx]
            assert not d['holdout'].any()
        d['photo_point_id']=np.full(len(d['patch_id']),'',dtype='<U96')
        for kind,source in [(1,cfg['sources']['roof_photo']),(2,cfg['sources']['wall_photo'])]:
            ix=np.flatnonzero(d['kind']==kind)
            if not len(ix):continue
            pp=Path(source)/'points'/p.name;mp=Path(source)/'geometry'/f'{tile}__{prior}__mapping.npz'
            if not pp.exists() or not mp.exists():
                failures.append(dict(file=str(pp),mapping=str(mp),reason='old photo source missing'));continue
            with zipfile.ZipFile(mp) as z:
                pids=array(z,'patch_id');take=np.isin(pids,d['patch_id'][ix]);idxs=selected(z,'point_index',take)
                owners=dict(zip(pids[take],idxs))
            with zipfile.ZipFile(pp) as z:
                pb=building_ids(z);take=np.isin(pb,list(wanted))
                # Only the allowed buildings' array values are decoded.
                pd={k[:-4]:selected(z,k[:-4],take) for k in z.namelist() if k.endswith('.npy')}
            assert not pd['holdout'].any()
            lookup=dict(zip(pd['geometry_index'],pd['point_id']))
            for i in ix:
                d['photo_point_id'][i]=lookup.get(owners.get(d['patch_id'][i],-1),'')
            dest=O/'photo_inputs'/f'{tile}__{prior}__{kind}.npz';dest.parent.mkdir(exist_ok=True)
            np.savez_compressed(dest,**pd)
        missing=d['photo_point_id']==''
        if missing.any():failures.append(dict(file=str(p),reason='photo mapping missing',count=int(missing.sum())))
        np.savez_compressed(dst,**d)
        seen[prior].update(d['building'])
        records.append(dict(tile=tile,prior=prior,core_points=len(d['patch_id']),
            area_m2=float(d['area'].sum()),photo_missing_count=int(missing.sum()),
            missing_u_mvs=int((~np.isfinite(d['u_mvs'])).sum()),
            missing_u_prior=int((~np.isfinite(d['u_prior'])).sum()),
            source=str(wf),selected_sha256=sha(dst)))
        print('JOIN',tile,prior,len(d['patch_id']),flush=True)
    report=dict(at=now(),status='STOP_INPUT_ALIGNMENT' if failures else 'PASS_DEVELOPMENT_JOIN',
        building_count={k:len(v) for k,v in seen.items()},rows=records,failures=failures,
        seconds=time.monotonic()-t0,scientific_verdict=None,source_tag='[이 발주에서 냄]')
    dump(O/'input_join.json',report);dump(D/'tables/input_join.json',report)
    print(json.dumps({k:v for k,v in report.items() if k!='rows'},ensure_ascii=False))


if __name__=='__main__':main()
