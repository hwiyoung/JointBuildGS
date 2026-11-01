"""Background lineage, independent cylinder masks, prior seed and map checks."""
import sys
import numpy as np
from scipy.spatial import cKDTree
from common import *


def main():
    cfg,lock=locked_r2();rows=[];rng=np.random.default_rng(20261101)
    for site in sys.argv[1:] or cfg['sites']+cfg['deferred_sites']:
        source=(OUT/'b173_uncert_r1' if site=='B173_b0' else UN)/'points'/site
        x=np.load(source/'mvs_a_xyz.npy',mmap_mode='r')
        for prior in cfg['priors']:
            root=OUT/'r2/stage1'/f'{site}_{prior}';meta=json.loads((root/'seed_receipt.json').read_text())
            assert sha(root/'seeds.npz')==meta['seeds_sha256']
            with np.load(root/'seeds.npz') as z:s={k:z[k] for k in z.files}
            with np.load(OUT/'r2/targets'/f'{site}_{prior}.npz') as z:d={k:z[k] for k in z.files}
            with np.load(OUT/'r2/background'/site/prior/'background.npz') as z:b={k:z[k] for k in z.files}
            bg=s['origin']==0;po=~bg
            assert np.array_equal(s['xyz'][bg],b['xyz']) and np.array_equal(b['xyz'],x[b['source_index']])
            assert np.array_equal(s['target'],s['xyz'])
            assert np.max(abs(s['xyz'][po]-d['target'][s['patch'][po]]))<=1.6e-5
            assert np.allclose(s['normal'][bg],b['normal'],atol=0,rtol=0)
            assert np.allclose(np.linalg.norm(s['normal'],axis=1),1,atol=1e-6,rtol=0)
            assert np.all(s['sigma']>0) and np.isfinite(s['sigma']).all()
            vox=np.floor(b['xyz'].astype(float)/.25).astype('i4');assert len(np.unique(vox,axis=0))==len(vox)
            radius=np.array([cfg['inherited_radius'][prior][str(int(k))]['radius_m'] or np.nan for k in d['kind']]);H=np.where(d['kind']==1,10.,5.)
            normal=d['normal'];valid=np.isfinite(normal).all(1)&np.isfinite(radius)&(abs((normal*normal).sum(1)-1)<1e-6)
            ids=np.flatnonzero(valid);tree=cKDTree(d['centre'][ids]);sample=rng.choice(len(b['xyz']),min(512,len(b['xyz'])),replace=False)
            for point in b['xyz'][sample]:
                cand=ids[tree.query_ball_point(point,np.hypot(10,.125)+1e-5)]
                delta=point.astype(float)-d['centre'][cand];h=(delta*normal[cand]).sum(1);lateral=((delta-h[:,None]*normal[cand])**2).sum(1)
                assert not ((abs(h)<=H[cand])&(lateral<=radius[cand]**2)).any(),'background inside a prior cylinder'
            with np.load(OUT/'stage1'/f'{site}_{prior}'/'seeds.npz') as z:
                oldcounts=np.bincount(z['patch'][z['origin']==1],minlength=len(d['region']))
            assert np.array_equal(oldcounts,np.bincount(s['patch'][po],minlength=len(d['region'])))
            index=json.loads((root/'maps/index.json').read_text())
            for m in index['views'].values():assert sha(root/'maps'/m['file'])==m['sha256']
            rows.append(dict(site=site,prior=prior,status='PASS',background_points=int(bg.sum()),prior_points=int(po.sum()),
                independent_cylinder_samples=len(sample),map_files_checked=len(index['views']),scientific_verdict=None))
            print('R2_STAGE1_INPUTS_VERIFIED',site,prior,flush=True)
    dest=OUT/'r2/verification'/('stage1_'+('_'.join(sys.argv[1:]) or 'all')+'.json')
    dump(dest,dict(at=stamp(),status='PASS_STAGE1_INPUTS',rows=rows,config_sha256=lock['config_sha256'],scientific_verdict=None))


if __name__=='__main__':main()
