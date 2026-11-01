"""Retain baseline prior count/scales; add the locked MVS background point-patches."""
import sys
import numpy as np
from plyfile import PlyData
from common import *
sys.path.insert(0,str(REPO))
from src.phd.prior_propagation_v6.locations import locate
from src.phd.prior_propagation_v6.orientation import quat_from_normal


def main():
    cfg,lock=locked_r2()
    for site in sys.argv[1:]:
        for prior in cfg['priors']:
            root=OUT/'r2/stage1'/f'{site}_{prior}';root.mkdir(parents=True,exist_ok=True)
            if (root/'seed_receipt.json').exists():continue
            f=S0/'fork_inputs/s61'/site;ply=f/f'scene_{prior}/sparse/0/points3D.ply'
            v=PlyData.read(str(ply))['vertex'];xyz=np.c_[v['x'],v['y'],v['z']].astype(np.float64)
            origin=np.load(f/f'scene_{prior}/sparse/0/origin.npy');seat=np.load(f/f'seat_{prior}.npy')
            with np.load(f/f'store_{prior}.npz') as z:store={k:z[k] for k in z.files}
            with np.load(OUT/'r2/targets'/f'{site}_{prior}.npz') as z:t={k:z[k] for k in z.files}
            bf=OUT/'r2/background'/site/prior/'background.npz'
            with np.load(bf) as z:b={k:z[k] for k in z.files}
            loc=np.full(len(xyz),-1,np.int64);has=(origin==1)&(seat>=0);loc[has]=locate(store,seat[has],xyz[has])
            keep=np.flatnonzero(has&(loc>=0)&(t['region'][np.maximum(loc,0)]>=0));pid=loc[keep];nb=len(b['xyz'])
            pos=np.r_[t['target'][pid],b['xyz']];normal=np.r_[t['normal'][pid],b['normal']]
            sigma=np.r_[t['sigma'][pid],b['sigma']];regions=np.r_[t['region'][pid],np.full(nb,4,np.int8)]
            origins=np.r_[np.ones(len(pid),np.int8),np.zeros(nb,np.int8)]
            assert np.isfinite(pos).all() and np.isfinite(sigma).all() and (sigma>0).all()
            np.savez_compressed(root/'seeds.npz',original_xyz=xyz.astype('f4'),keep_original=keep,xyz=pos.astype('f4'),target=pos.astype('f4'),
                normal=normal.astype('f4'),sigma=sigma.astype('f4'),quaternion=quat_from_normal(normal).astype('f4'),
                origin=origins,region=regions,patch=np.r_[pid,np.full(nb,-1,np.int64)],background_rgb=b['rgb'].astype('f4'),
                uncertainty_replaced=np.r_[t['any_replaced'][pid],b['u_replaced']])
            dump(root/'seed_receipt.json',dict(at=stamp(),site=site,prior=prior,prior_kept=len(pid),background_kept=nb,
                target_patches_without_baseline_seed=int(((np.bincount(pid,minlength=len(t['region']))==0)&(t['region']>=0)).sum()),
                background_source='confidence-masked MVS A',baseline_background_source='SfM sparse',
                prior_scales='retained exactly',background_scales='baseline distCUDA2 rule on combined initial XYZ',
                seeds_sha256=sha(root/'seeds.npz'),background_sha256=sha(bf),config_sha256=lock['config_sha256'],scientific_verdict=None))
            print('R2_SEEDS',site,prior,len(pid),nb,flush=True)


if __name__=='__main__':main()
