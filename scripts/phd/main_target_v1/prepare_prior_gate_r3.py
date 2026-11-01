"""Exact retained r2 prior seeds; background is excluded only for the r3 rendering gate."""
import sys
import numpy as np
from plyfile import PlyData
from common import *
sys.path.insert(0,str(REPO))
from src.phd.prior_propagation_v6.locations import locate
from src.phd.prior_propagation_v6.orientation import quat_from_normal


def main():
    cfg,lock=locked_r3()
    for site,prior in [('B173nb_b10','ALS'),('B173nb_b10','LoD2'),('R1rep_b10','LoD2'),('B0_b10','LoD2')]:
        root=OUT/'r3/prior_only'/f'{site}_{prior}';root.mkdir(parents=True,exist_ok=False)
        f=S0/'fork_inputs/s61'/site;ply=f/f'scene_{prior}/sparse/0/points3D.ply'
        v=PlyData.read(str(ply))['vertex'];xyz=np.c_[v['x'],v['y'],v['z']].astype(np.float64)
        origin=np.load(f/f'scene_{prior}/sparse/0/origin.npy');seat=np.load(f/f'seat_{prior}.npy')
        with np.load(f/f'store_{prior}.npz') as z:store={k:z[k] for k in z.files}
        target=OUT/'r2/targets'/f'{site}_{prior}.npz'
        with np.load(target) as z:t={k:z[k] for k in z.files}
        loc=np.full(len(xyz),-1,np.int64);has=(origin==1)&(seat>=0);loc[has]=locate(store,seat[has],xyz[has])
        keep=np.flatnonzero(has&(loc>=0)&(t['region'][np.maximum(loc,0)]>=0));pid=loc[keep]
        np.savez_compressed(root/'seeds.npz',original_xyz=xyz.astype('f4'),keep_original=keep,
            xyz=t['target'][pid].astype('f4'),target=t['target'][pid].astype('f4'),normal=t['normal'][pid].astype('f4'),
            sigma=t['sigma'][pid].astype('f4'),quaternion=quat_from_normal(t['normal'][pid]).astype('f4'),
            origin=np.ones(len(pid),np.int8),region=t['region'][pid],patch=pid,uncertainty_replaced=t['any_replaced'][pid])
        (root/'maps').symlink_to(Path('../../../r2/stage1')/f'{site}_{prior}'/'maps',target_is_directory=True)
        assert (root/'maps/index.json').exists()
        combined=OUT/'r2/stage1'/f'{site}_{prior}'/'seeds.npz'
        if combined.exists():
            with np.load(combined) as z, np.load(root/'seeds.npz') as p:
                for key in ['xyz','target','normal','sigma','quaternion','origin','region','patch']:
                    assert np.array_equal(p[key],z[key][:len(pid)]),key
                assert np.array_equal(p['keep_original'],z['keep_original'])
        dump(root/'seed_receipt.json',dict(at=stamp(),site=site,prior=prior,prior_count=len(pid),background_count=0,
            purpose='prior-only initial rendering gate, never a training input',config_sha256=lock['config_sha256'],
            seeds_sha256=sha(root/'seeds.npz'),target_sha256=sha(target),baseline_ply_sha256=sha(ply),
            map_index_sha256=sha(root/'maps/index.json'),scientific_verdict=None))
        print('R3_PRIOR_GATE_SEEDS',site,prior,len(pid),flush=True)


if __name__=='__main__':main()
