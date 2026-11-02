"""Recompute missing u_M exactly; retain unavailable rather than impute."""
import json,multiprocessing as mp,time,zipfile,resource,sys
import numpy as np
from scipy.spatial import cKDTree
from preflight import C,D,O,Path,sha,dump,now
from prepare import array
from geometry import loadz,savez
import ring_kernel as K
import ring_context as U
BASE=O/'r1'

def run_chunk(ids):return [(i,K.one_patch(int(i))[1.5]) for i in ids]

def main(tile_arg=None):
    lock=C/'ring.reply1.lock.json'
    if not lock.exists():dump(lock,dict(at=now(),config_sha256=sha(C/'judgecheck_v1.json'),
        source_sha256={p.name:sha(p) for p in [Path(__file__),Path(K.__file__),Path(U.__file__),Path(__file__).parent/'u_core.py']},
        inherited_normal_for_u=True,only_missing_u=True,no_truth=True,scientific_verdict=None))
    tiles=sorted({p.stem.split('__')[0] for p in (BASE/'inputs').glob('*.npz')})
    for tile in [tile_arg] if tile_arg else tiles:
        paths=[p for p in sorted((BASE/'inputs').glob(tile+'__*.npz')) if not (BASE/'ring_recompute'/p.name).exists()]
        if not paths:continue
        started=time.monotonic();X=np.load(U.PTS/tile/'mvs_a_xyz.npy').astype(float);views=np.load(U.PTS/tile/'mvs_a_view.npy');keys=np.load(U.PTS/tile/'mvs_a_key.npy')
        tree=cKDTree(X,leafsize=32,balanced_tree=False,compact_nodes=False);levels={}
        for k in range(1,6):
            nk=int(np.searchsorted(keys,4.**-k))
            if nk<1000:break
            levels[k]=(nk,cKDTree(X[:nk],leafsize=32,balanced_tree=False,compact_nodes=False))
        for p in paths:
            prior=p.stem.split('__')[1];d=loadz(p);missing=np.flatnonzero(~np.isfinite(d['u_mvs']));um=d['u_mvs'].astype(float);status=np.full(len(um),-1,np.int8)
            with zipfile.ZipFile(U.W/'holdout/internal/patch_geometry'/f'{tile}_{prior}.npz') as z:
                ids=array(z,'patch_id');lookup={pid:i for i,pid in enumerate(ids)}
            original=np.array([lookup[pid] for pid in d['patch_id']])
            K.G.update(X=X,V=views,data='mvs_a',radii=[1.5],site=tile,pset=prior,tree=tree,levels=levels,
                c=d['centre'],n=d['normal'],roof=d['kind']==1,gt=None,original_index=original)
            chunks=[missing[i:i+200] for i in range(0,len(missing),200)];done=0
            with mp.get_context('fork').Pool(4) as pool:
                for rows in pool.imap_unordered(run_chunk,chunks):
                    for i,r in rows:
                        status[i]=r['status'];um[i]=r.get('u',np.nan) if r['status']==0 else np.nan
                    done+=len(rows)
                    if done%10000<200:print('RING',tile,prior,done,len(missing),flush=True)
            savez(BASE/'ring_recompute'/p.name,patch_id=d['patch_id'],u_mvs=um,recomputed_status=status)
            dump((BASE/'ring_recompute'/p.name).with_suffix('.json'),dict(at=now(),tile=tile,prior=prior,
                attempted=len(missing),recovered=int(np.isfinite(um[missing]).sum()),
                unavailable=int((~np.isfinite(um[missing])).sum()),truth_opened=False,
                seconds_since_tile_start=time.monotonic()-started,scientific_verdict=None))
            print('RING_DONE',tile,prior,len(missing),'recovered',np.isfinite(um[missing]).sum(),flush=True)
        K.G.clear();del X,views,keys,tree,levels

if __name__=='__main__':main(sys.argv[1] if len(sys.argv)>1 else None)
