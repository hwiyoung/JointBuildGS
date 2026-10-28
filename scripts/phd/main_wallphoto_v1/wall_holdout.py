"""Sealed geometry counts only, to include all work in the CPU time estimate."""
from common import *
from prepare import group
from wall_measure import atomic_npz
def main():
    count=0;base=paths(True)
    for f in sorted((W/'holdout/patch_values').glob('*__LoD2__R1.5.npz')):
        tile=f.stem.split('__')[0];dest=base/'geometry'/f'{tile}__LoD2.npz'
        if dest.exists():count+=len(npz(dest)['point_id']);continue
        raw=npz(f);take=raw['kind']==2
        if not take.any():continue
        d={k:v[take] for k,v in raw.items()};g,owner,_=group(d,'LoD2',tile);_,first=np.unique(owner,return_index=True);g['face_ext']=d['face_ext'][first]
        atomic_npz(dest,g);atomic_npz(base/'geometry'/f'{tile}__LoD2__mapping.npz',dict(patch_id=d['patch_id'],point_index=owner,source_index=np.flatnonzero(take),kind=d['kind']));count+=len(g['point_id'])
    inv=load(O/'inventory.json');inv['holdout']['points']=count;dump(O/'inventory.json',inv);dump(D/'tables/inventory.json',inv)
    print('sealed geometry totals',count,flush=True)
if __name__=='__main__':main()
