"""Same JUDGENUM cylinders and fixed radii, now on exact experimental MVS clouds."""
import sys
import numpy as np
from common import *
import cylinder_runtime as cr


def main():
    cfg,lock=locked();root=OUT/'stage0_r1/cylinders';root.mkdir(parents=True,exist_ok=True)
    assert json.loads((OUT/'stage0_r1/T2.json').read_text())['status']=='PASS_T2_MIXTURE'
    assert sha(Path(__file__).parent/'cylinders.cpp')==sha(REPO/'scripts/phd/main_judgenum_v1/cylinders.cpp')
    cr.verify();binary=OUT/'tmp/cylinders'
    dump(root/'implementation.lock.json',{'at':stamp(),'config_sha256':lock['config_sha256'],
        'code_sha256':sha(Path(__file__).parent/'cylinders.cpp'),'scientific_verdict':None})
    deferred='--deferred' in sys.argv
    for site in cfg['deferred_sites'] if deferred else cfg['sites']:
        for prior in cfg['priors']:
            inp=OUT/'stage0_r1/inputs'/f'{site}_{prior}.npz';dest=root/f'{site}_{prior}.bin'
            complete=dest.with_suffix('.complete.json')
            if complete.exists():continue
            with np.load(inp) as z:d={k:z[k] for k in ['centre','normal','kind']}
            source=OUT/'b173_uncert_r1' if deferred else UN
            points=source/'points'/site/'mvs_a_xyz.npy'
            cr.run(points,d['centre'],d['normal'],dest,binary)
            stats=np.memmap(dest,dtype='<f8',mode='r',shape=(len(d['kind']),3,10,7))
            chosen=cfg['inherited_radius'][prior]
            ridx=np.array([chosen.get(str(int(k)),{}).get('radius_index',9) for k in d['kind']])
            # No ALS wall radius existed in JUDGENUM; such patches are explicitly unavailable.
            unavailable=np.array([chosen.get(str(int(k)),{}).get('radius_m') is None for k in d['kind']])
            selected=np.array(stats[np.arange(len(ridx)),0,ridx,:]);selected[unavailable]=np.nan;selected[unavailable,0]=-1
            np.savez_compressed(dest.with_suffix('.selected.npz'),stats=selected,radius_index=ridx,unavailable_radius=unavailable)
            dump(complete,{'at':stamp(),'input_sha256':sha(inp),'points_sha256':sha(points),
                'raw_sha256':sha(dest),'status':'COMPLETE','unavailable_radius_count':int(unavailable.sum()),'scientific_verdict':None})
            print('CYLINDER_DONE',site,prior,flush=True)


if __name__=='__main__':main()
