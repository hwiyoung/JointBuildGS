"""Export unique patch-to-point joins and seal holdout; no outcome aggregation for holdout."""
import shutil
from common import *
def main():
    summary=[]
    for seal in [False,True]:
        base=paths(seal);building_sets={'LoD2':set(),'ALS':set()}
        for prior in ['LoD2','ALS']:
            counts=dict(prior=prior,holdout=seal,points=0,patches=0,area_m2=0.,files=[])
            for geo in sorted((base/'geometry').glob(f'*__{prior}.npz')):
                g=npz(geo);roof=g['kind']==1;tile=geo.stem.split('__')[0]
                f=base/'work/full'/geo.name
                if not roof.any():continue
                assert f.exists(),f
                p=npz(f);assert np.all(p['kind']==1) and len(p['point_id'])==int(roof.sum())
                assert len(np.unique(p['point_id']))==len(p['point_id']);assert np.array_equal(p['holdout'],np.full(len(p['point_id']),seal))
                assert p['curve'].dtype==np.float16 and p['judgment'].dtype==np.int8 and p['judgment'].shape==(len(p['point_id']),15)
                mapping=npz(geo.with_name(geo.stem+'__mapping.npz'));mask=mapping['kind']==1
                lookup=np.full(len(g['point_id']),-1,np.int32);lookup[p['geometry_index']]=np.arange(len(p['point_id']))
                ix=lookup[mapping['point_index'][mask]];assert (ix>=0).all()
                patches=dict(patch_id=mapping['patch_id'][mask],point_id=p['point_id'][ix],judgment=p['judgment'][ix])
                assert len(np.unique(patches['patch_id']))==len(ix)
                dest=base/'points'/geo.name;shutil.copyfile(f,dest);patchdest=base/'patches'/geo.name;np.savez_compressed(patchdest,**patches)
                counts['points']+=len(p['point_id']);counts['patches']+=len(ix);counts['area_m2']+=float(p['area'].sum())
                for names in p.get('building_ids',p['building']):building_sets[prior].update(str(names).split(';'))
                for q in [dest,patchdest]:counts['files'].append(dict(file=str(q.relative_to(base)),bytes=q.stat().st_size,sha256=sha(q)))
            counts['buildings']=len(building_sets[prior]);summary.append(counts)
    dump(O/'final_export.json',dict(rows=summary,scientific_verdict=None,environment=env()))
    dump(D/'tables/final_scope_and_hashes.json',dict(rows=summary,source='[이 발주에서 냄]',scientific_verdict=None))
    print('point/patch export verified',[(r['prior'],r['holdout'],r['points'],r['patches']) for r in summary])
if __name__=='__main__':main()
