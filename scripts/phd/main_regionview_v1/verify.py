"""Independent summations, source preservation, disclosure and figure checks."""
import time
from collections import defaultdict
from PIL import Image
from common import *

def close(a,b):assert abs(a-b)<=max(1e-7,abs(b)*1e-10),(a,b)

def main():
    t=time.monotonic();check_locked();held=set(read(JN/'holdout/scope_membership.json')['buildings'])
    checks=[];face_count=0;patch_count=0
    for scope in [*SITES,'development','holdout']:
        for prior in ['ALS','LoD2']:
            if scope in SITES:
                paths=[OUT/f'{REV}/patches/{scope}_{prior}.npz'];facepath=OUT/f'{REV}/tables/faces_full_{scope}_{prior}.json'
            else:
                root=OUT/('holdout' if scope=='holdout' else 'development')/REV
                paths=sorted((root/'patches').glob(f'*__{prior}.npz'));facepath=root/f'tables/faces_full_{prior}_{REV}.json'
            expected=defaultdict(lambda:defaultdict(float));total=attached=0.;ids=set()
            for path in paths:
                d=npz(path);a=d['area'];region=d['region'];cell=d['cell']
                assert np.isfinite(a).all() and np.all(a>=0)
                assert np.isin(region,[-1,0,1,2,3,5] if REV=='r7' else [-1,0,1,2,3]).all()
                assert np.isin(cell,range(7)).all()
                if 'patch_id' in d:
                    assert not ids&set(d['patch_id']);ids.update(d['patch_id'])
                if scope!='holdout':assert not set(d['assigned_building'])&held
                if scope in SITES:
                    original=npz(TG/f'{REV}/targets/{scope}_{prior}.npz',['region','area','in_eval','centre'])
                    ix=d['source_index'];assert np.array_equal(ix,np.flatnonzero(original['in_eval']))
                    assert np.array_equal(region,original['region'][ix]) and np.array_equal(a,original['area'][ix])
                    assert np.array_equal(d['centre'],original['centre'][ix])
                else:
                    source_root=TG/('holdout/r2/stage0' if scope=='holdout' else 'r2/stage0/development')
                    original=npz(source_root/path.name,['patch_id','area','cell','region'])
                    assert np.array_equal(d['patch_id'],original['patch_id'])
                    assert np.array_equal(a,original['area']) and np.array_equal(cell,original['cell'])
                    if REV=='r2':assert np.array_equal(region,original['region'])
                    else:
                        vote_root=TG/('holdout/r7/stage0' if scope=='holdout' else 'r7/stage0/development')
                        gone=npz(vote_root/path.name,['disappeared'])['disappeared']
                        assert gone.dtype==np.bool_ and gone.shape==region.shape
                        expected_region=original['region'].copy()
                        assert np.all(expected_region[gone]==0)
                        expected_region[gone]=5
                        assert np.array_equal(region,expected_region),'saved r7 vote differs from derived region'
                if REV=='r7':
                    base=npz(Path(str(path).replace('/r7/','/r2/')))
                    for key in d:
                        if key=='region':continue
                        assert np.array_equal(d[key],base[key],equal_nan=True) if d[key].dtype.kind=='f' else np.array_equal(d[key],base[key]),key
                    assert np.all((region==base['region'])|((region==5)&(base['region']==0)))
                total+=float(a.sum());attached+=float(a[d['face']!=''].sum());patch_count+=len(a)
                # Recompute grouped matrix with a different implementation: flatten
                # face/region/cell keys and NumPy indexed reduction, no measure helpers.
                faces,inv=np.unique(d['face'],return_inverse=True)
                rc=region+1;matrix=np.zeros((len(faces),7,7));np.add.at(matrix,(inv,rc,cell),a)
                nums=np.bincount(inv,minlength=len(faces))
                for j,f in enumerate(faces):
                    if f=='':continue
                    expected[f]['area']+=float(matrix[j].sum());expected[f]['count']+=int(nums[j])
                    for k in LABELS:expected[f][f'r{k}']+=float(matrix[j,k+1].sum())
                    expected[f]['match']+=float(matrix[j,2,0]+matrix[j,3,2]+matrix[j,4,1])
                    expected[f]['comparable']+=float(matrix[j,2:5,:3].sum())
                    expected[f]['prior_wrong']+=float(matrix[j,:,[1,3]].sum())
                    expected[f]['image_wrong']+=float(matrix[j,:,[2,3]].sum())
                    for c in range(7):expected[f][f'c{c}']+=float(matrix[j,:,c].sum())
            rows=read(facepath)['rows'];assert set(r['face_id'] for r in rows)==set(expected)
            close(sum(r['eval_area_m2'] for r in rows),attached)
            for r in rows:
                e=expected[r['face_id']];close(r['eval_area_m2'],e['area']);assert r['patch_count']==e['count']
                close(r['match_area_m2'],e['match']);close(r['match_comparable_area_m2'],e['comparable'])
                close(r['prior_only_wrong_area_m2'],e['prior_wrong']);close(r['image_only_wrong_area_m2'],e['image_wrong'])
                for k,name in NAMES.items():close(r[name+'_area_m2'],e[f'r{k}'])
                for c in range(7):close(r[f'cell{c}_area_m2'],e[f'c{c}'])
                close(r['purity'],max(e[f'r{k}'] for k in LABELS)/e['area'])
            face_count+=len(rows)
            pu=[r for r in read(DOC/f'tables/purity_{REV}.json')['rows'] if r['scope']==scope and r['prior']==prior and r['dominant_region']=='all']
            for kind in ['roof','wall']:
                subset=[r for r in rows if r['face_kind']==kind]
                mass=sum(r['eval_area_m2'] for r in subset);bins=[r for r in pu if r['face_kind']==kind]
                close(sum(r['eval_area_m2'] for r in bins),mass)
                assert sum(r['face_count'] for r in bins)==len(subset)
            if scope!='holdout':
                public=read(DOC/f'tables/faces_{scope}_{prior}_{REV}.json')['rows']
                close(sum(r['eval_area_m2'] for r in public),attached)
                assert sum(r['face_count'] for r in public)==len(rows)
            checks.append(dict(scope=scope,prior=prior,face_count=len(rows),patch_count=sum(r['patch_count'] for r in rows),
                eval_area_m2=total,attached_area_m2=attached,status='PASS'))
    figures=list((DOC/'figures').glob(f'*{REV}*.png'));photo_count=0
    assert figures,'no figures'
    for p in figures:
        side=p.with_suffix('.json');assert side.exists(),p
        meta=read(side)
        assert meta.get('scope') not in ['holdout','development']
        assert meta.get('building') not in held
        if p.name.startswith('map_'):
            assert meta['band_included'] is False and meta['raster']['step']==.25
            photo=meta['photo'];assert photo['status']=='selected',(p,photo)
            split=read(S0/'fork_inputs/s61'/meta['scope']/'split.json')
            assert photo['name'] in split['train'];assert photo['outside_building_masked']
            photo_count+=1
        with Image.open(p) as im:
            im.verify()
        assert meta['scientific_verdict'] is None
    leak_count=0
    for p in DOC.rglob('*'):
        if p.suffix not in ['.md','.json','.csv']:continue
        txt=p.read_text(encoding='utf-8-sig')
        hits=[b for b in held if b in txt];assert not hits,('sealed identifier in public document',str(p))
        if 'faces_holdout_' in p.name:
            assert 'face_id' not in txt and 'building_name' not in txt
    ledger=read(OUT/f'input_ledger_{REV}.json')['entries']+read(OUT/f'holdout/input_ledger_{REV}.json')['entries']
    if (OUT/f'figure_inputs_{REV}.json').exists():ledger+=read(OUT/f'figure_inputs_{REV}.json')['entries']
    unique={r['path']:r for r in ledger}
    for p,rec in unique.items():assert sha(p)==rec['sha256'],('source changed',p)
    receipt=dict(status='PASS_TECHNICAL_VERIFICATION',at=stamp(),revision=REV,units=checks,faces_verified=face_count,patches_verified=patch_count,
        figures_verified=len(figures),selected_training_photos=photo_count,unchanged_input_files=len(unique),holdout_leaks=leak_count,
        validation='independent face-by-class-by-cell indexed reduction, area conservation, exact source label/geometry checks, holdout public text scan, PNG decoding, photo training membership, before/after SHA256',
        visual_review='separate image inspection required',scientific_verdict=None,seconds=time.monotonic()-t)
    dump(OUT/f'verification_{REV}.json',receipt);dump(DOC/f'tables/verification_{REV}.json',receipt)
    print('VERIFIED',REV,face_count,patch_count,len(figures),len(unique),flush=True)

if __name__=='__main__':main()
