"""Full wall census in frozen disagreement-area order, reusing pilot measurements."""
from common import *
from prepare import group
from wall_measure import measure,atomic_npz
from wall_report import point_sets,report

def main():
    assert load(O/'gates/full_decision.json')['decision']=='START_FULL'
    order=[r['tile'] for r in load(D/'tables/development_tiles.json')['rows']]
    hold_summary=dict(points=0,patches=0,area_m2=0.,files=[])
    for sealed in [False,True]:
        base=paths(sealed)
        if sealed:
            order=[f.stem.split('__')[0] for f in sorted((W/'holdout/patch_values').glob('*__LoD2__R1.5.npz'))]
        for tile in order:
            folder=base/'work/full';folder.mkdir(exist_ok=True);dest=folder/f'{tile}__LoD2.npz'
            if dest.exists() and dest.with_suffix('.json').exists():continue
            if sealed:
                raw=npz(W/'holdout/patch_values'/f'{tile}__LoD2__R1.5.npz');take=raw['kind']==2
                if not take.any():continue
                d={k:v[take] for k,v in raw.items()};g,owner,audit=group(d,'LoD2',tile);_,first=np.unique(owner,return_index=True);g['face_ext']=d['face_ext'][first]
                atomic_npz(base/'geometry'/f'{tile}__LoD2.npz',g)
                atomic_npz(base/'geometry'/f'{tile}__LoD2__mapping.npz',dict(patch_id=d['patch_id'],point_index=owner,source_index=np.flatnonzero(take),kind=d['kind']))
            else:g=npz(base/'geometry'/f'{tile}__LoD2.npz')
            old=[]
            if not sealed:
                for f in sorted((O/'work/pilot').glob(tile+'__*.npz')):
                    if f.with_suffix('.json').exists():old.append(npz(f))
            reused=np.concatenate([x['geometry_index'] for x in old]) if old else np.empty(0,np.int64)
            ids=np.setdiff1d(np.arange(len(g['point_id'])),reused)
            rec=None
            if len(ids):
                rec=measure(tile,ids,'full','LoD2_new',sealed);old.append(npz(folder/f'{tile}__LoD2_new.npz'))
            p={k:np.concatenate([x[k] for x in old]) for k in old[0]};idx=np.argsort(p['geometry_index']);p={k:v[idx] for k,v in p.items()}
            assert np.array_equal(p['geometry_index'],np.arange(len(g['point_id'])))
            atomic_npz(dest,p);dump(dest.with_suffix('.json'),dict(at=now(),config_sha256=sha(C/'wallphoto_v1.json'),reused_pilot_points=len(reused),new_points=len(ids),receipt=rec,scientific_verdict=None))
            if sealed:
                mp=npz(base/'geometry'/f'{tile}__LoD2__mapping.npz');ix=mp['point_index'];atomic_npz(base/'points'/dest.name,p);atomic_npz(base/'patches'/dest.name,dict(patch_id=mp['patch_id'],point_id=p['point_id'][ix],judgment=p['judgment'][ix]))
            else:report('full')
    for f in sorted((O/'holdout/points').glob('*__LoD2.npz')):
        p=npz(f);hold_summary['points']+=len(p['point_id']);hold_summary['patches']+=int(p['patch_count'].sum());hold_summary['area_m2']+=float(p['area'].sum())
        hold_summary['files'].append(dict(sha256=sha(f)))
    for f in sorted((O/'holdout/patches').glob('*__LoD2.npz')):hold_summary['files'].append(dict(sha256=sha(f)))
    dump(D/'tables/holdout_totals_hashes.json',dict(**hold_summary,scientific_verdict=None))
    dump(O/'full_complete.json',dict(at=now(),status='COMPLETE',scientific_verdict=None))
if __name__=='__main__':main()
