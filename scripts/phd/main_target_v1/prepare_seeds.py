"""Keep baseline seed counts/scales, move prior seeds to frozen targets, own background u."""
import sys
import numpy as np
from scipy.spatial import cKDTree
from plyfile import PlyData
from common import *
sys.path.insert(0,str(REPO))
from src.phd.prior_propagation_v6.locations import locate
from src.phd.prior_propagation_v6.orientation import quat_from_normal


def image_covered(x,d):
    covered=np.zeros(len(x),bool)
    for kind in [1,2]:
        ids=np.flatnonzero(d['kind']==kind)
        if not len(ids):continue
        centers=d['centre'][ids];radius=np.sqrt(d['area'][ids]/np.pi)
        if kind==1:
            # The source roof's XY support owns the image seed independently of its height.
            candidates=cKDTree(centers[:,:2]).query_ball_point(x[:,:2],float(radius.max()),workers=1)
            for i,nb in enumerate(candidates):
                if nb:
                    q=np.asarray(nb);covered[i]|=bool((np.linalg.norm(centers[q,:2]-x[i,:2],axis=1)<=radius[q]+1e-8).any())
        else:
            candidates=cKDTree(centers).query_ball_point(x,float(np.hypot(3,radius.max())),workers=1)
            for i,nb in enumerate(candidates):
                if covered[i] or not nb:continue
                q=np.asarray(nb);delta=x[i]-centers[q];normal=d['normal'][ids[q]];h=(delta*normal).sum(1)
                lateral=np.linalg.norm(delta-h[:,None]*normal,axis=1)
                covered[i]=bool(((abs(h)<=3)&(lateral<=radius[q]+1e-8)).any())
    return covered


def own_background_u(site,prior,x,n,d,root):
    if not len(x):return np.empty(0),np.zeros(0,bool),[]
    sys.path.insert(0,str(REPO/'scripts/phd/main_uncert_v1'))
    import uc_common as U
    U.SITE_ID['B173_b0']=3
    U.PTS=(OUT/'b173_uncert_r1' if site=='B173_b0' else UN)/'points'
    U.WORK=root/'background_uncert';U.WORK.mkdir(exist_ok=True)
    roof=np.abs(n[:,2])>=np.cos(np.radians(45));kind=np.where(roof,1,2)
    np.savez_compressed(U.WORK/f'patches_{site}_{prior}.npz',centre=x,normal=n,roof_like=roof)
    import u2_run as run
    assert not (U.WORK/f'gt_{site}_{prior}.npz').exists()
    run.run(site,prior,'mvs_a',[1.5],4)
    with np.load(U.WORK/f'val_{site}_{prior}_mvs_a_R1.5.npz') as z:
        u=z['u'].copy();status=z['status'];u[status!=0]=np.nan
    replaced=~np.isfinite(u);medians=[]
    for k in [1,2]:
        missing=replaced&(kind==k)
        if not missing.any():continue
        donor=d['mvs_a_u'][(d['kind']==k)&np.isfinite(d['mvs_a_u'])]
        assert len(donor) and np.median(donor)>0,('BACKGROUND_U_UNAVAILABLE',site,prior,k)
        median=float(np.median(donor));u[missing]=median
        medians.append(dict(kind=k,donors=len(donor),median=median,replaced=int(missing.sum())))
    return u,replaced,medians


def main():
    cfg,lock=training_locked();sites=sys.argv[1:] or cfg['sites']+cfg['deferred_sites']
    for site in sites:
        for prior in cfg['priors']:
            root=OUT/'stage1'/f'{site}_{prior}';root.mkdir(parents=True,exist_ok=True)
            complete=root/'seed_receipt.json'
            if complete.exists():continue
            f=S0/'fork_inputs/s61'/site
            ply=f/f'scene_{prior}/sparse/0/points3D.ply'
            v=PlyData.read(str(ply))['vertex'];xyz=np.c_[v['x'],v['y'],v['z']].astype(np.float64)
            origin=np.load(f/f'scene_{prior}/sparse/0/origin.npy');seat=np.load(f/f'seat_{prior}.npy')
            with np.load(f/f'store_{prior}.npz') as z:store={k:z[k] for k in z.files}
            with np.load(OUT/'targets'/f'{site}_{prior}.npz') as z:target={k:z[k] for k in z.files}
            with np.load(OUT/'stage0_r1/inputs'/f'{site}_{prior}.npz') as z:d={k:z[k] for k in z.files}
            assert len(xyz)==len(origin)==len(seat)
            loc=np.full(len(xyz),-1,np.int64);has=(origin==1)&(seat>=0)
            loc[has]=locate(store,seat[has],xyz[has])
            prior_keep=has&(target['region'][np.maximum(loc,0)]>=0)
            image=np.flatnonzero(origin==0);covered=image_covered(xyz[image],d);bg=image[~covered]
            pi=np.flatnonzero(prior_keep);keep=np.sort(np.r_[pi,bg]);po=origin[keep]==1;own=loc[keep]
            pos=xyz[keep].copy();anchor=pos.copy();norm=np.zeros_like(pos);norm[:,2]=1
            sigma=np.full(len(keep),np.nan);region=np.full(len(keep),4,np.int8)
            pos[po]=target['target'][own[po]];anchor[po]=pos[po]
            norm[po]=target['normal'][own[po]];sigma[po]=target['sigma'][own[po]];region[po]=target['region'][own[po]]
            originalnorm=np.load(f/f'prior_normal_{prior}.npy')[keep]
            hasnorm=(~po)&np.isfinite(originalnorm).all(1)&(np.linalg.norm(np.nan_to_num(originalnorm),axis=1)>0)
            norm[hasnorm]=originalnorm[hasnorm]/np.linalg.norm(originalnorm[hasnorm],axis=1,keepdims=True)
            u,rep,med=own_background_u(site,prior,pos[~po],norm[~po],d,root)
            sigma[~po]=np.sqrt(u*u+.0275**2);flags=np.zeros(len(keep),bool);flags[~po]=rep;flags[po]=target['any_replaced'][own[po]]
            assert np.isfinite(pos).all() and np.isfinite(sigma).all() and (sigma>0).all()
            quaternion=quat_from_normal(norm)
            np.savez_compressed(root/'seeds.npz',original_xyz=xyz.astype(np.float32),keep_original=keep,xyz=pos.astype(np.float32),
                target=anchor.astype(np.float32),normal=norm.astype(np.float32),sigma=sigma.astype(np.float32),
                quaternion=quaternion.astype(np.float32),origin=origin[keep],region=region,patch=own,uncertainty_replaced=flags)
            baseline_counts=np.bincount(loc[prior_keep],minlength=len(d['area']))
            assert np.array_equal(np.bincount(own[po],minlength=len(d['area'])),baseline_counts)
            row=dict(site=site,prior=prior,status='SEEDS_PREPARED',at=stamp(),original=len(xyz),kept=len(keep),
                prior_original=int((origin==1).sum()),prior_kept=int(po.sum()),background_kept=int((~po).sum()),
                image_excluded_under_prior=int(covered.sum()),prior_target_patches=int((baseline_counts>0).sum()),
                target_patches_without_baseline_seed=int(((baseline_counts==0)&(target['region']>=0)).sum()),
                background_u_replaced=int(rep.sum()),background_medians=med,seeds_sha256=sha(root/'seeds.npz'),
                original_ply_sha256=sha(ply),target_sha256=sha(OUT/'targets'/f'{site}_{prior}.npz'),
                config_sha256=lock['config_sha256'],scientific_verdict=None)
            dump(complete,row);print('SEEDS_PREPARED',row,flush=True)

if __name__=='__main__':main()
