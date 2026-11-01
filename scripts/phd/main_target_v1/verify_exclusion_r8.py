"""Independent SciPy queries against all finite prior cylinders, no GT inputs."""
import numpy as np
from scipy.spatial import cKDTree
from common import *
def main():
    cfg,_=locked_r2();rows=[]
    for prior in ['ALS','LoD2']:
        root=OUT/'r8/stage1'/f'B173nb_b10_{prior}'
        x=np.load(root/'sfm_original_xyz.npy').astype(float)
        with np.load(OUT/'stage0_r1/inputs'/f'B173nb_b10_{prior}.npz') as z:c=z['centre'];n=z['normal'];kind=z['kind']
        rad=np.array([cfg['inherited_radius'][prior][str(int(k))]['radius_m'] or np.nan for k in kind]);height=np.where(kind==1,10.,5.)
        valid=np.isfinite(n).all(1)&(abs((n*n).sum(1)-1)<=1e-6)&np.isfinite(rad);c,n,rad,height=c[valid],n[valid],rad[valid],height[valid]
        assert rad.max()<=.5 and height.max()<=10.
        tree=cKDTree(c);bound=float(np.hypot(height,rad).max())+1e-5;excluded=np.zeros(len(x),bool);pairs=0
        for start in range(0,len(x),64):
            q=x[start:start+64];neighbours=tree.query_ball_point(q,bound,workers=1)
            for k,ids in enumerate(neighbours):
                if not ids:continue
                ids=np.asarray(ids);d=q[k]-c[ids];h=(d*n[ids]).sum(1);tan=d-h[:,None]*n[ids];pairs+=len(ids)
                excluded[start+k]=np.any((abs(h)<=height[ids])&((tan*tan).sum(1)<=rad[ids]**2))
        saved=np.fromfile(root/'excluded.bin',dtype=np.uint8).astype(bool);assert np.array_equal(saved,excluded)
        with np.load(root/'seeds.npz') as z:
            source=S0/'fork_inputs/s61/B173nb_b10'/f'scene_{prior}/sparse/0/origin.npy';origin=np.load(source);assert np.array_equal(z['background_original'],np.flatnonzero(origin==0)[~excluded])
        rows.append(dict(prior=prior,sfm_points=len(x),candidate_pairs=pairs,excluded=int(excluded.sum()),all_points_equal=True,scientific_verdict=None))
    record=dict(at=stamp(),status='PASS_INDEPENDENT_SFM_CYLINDERS',rows=rows,GT_used=False,scientific_verdict=None);dump(OUT/'r8/verification/exclusion.json',record);dump(DOC/'tables/r8_exclusion_verification.json',record);print(record['status'])
if __name__=='__main__':main()
