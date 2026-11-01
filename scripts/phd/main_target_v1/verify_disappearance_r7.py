"""Independent small-sample view replay plus complete vote/exclusion arithmetic."""
import numpy as np
from scipy.spatial import cKDTree
from common import *
from disappearance_r7 import loadz
def main():
    rows=[]
    for path in sorted((OUT/'r7/targets').glob('*.npz')):
        site,prior=path.stem.rsplit('_',1);old=loadz(OUT/'r2/targets'/path.name);new=loadz(path);a=loadz(OUT/'r7/stage0'/f'{path.stem}.votes.npz')
        decided=(old['region']==0)&(a['votes'][:,0]>=2)&(2*a['votes'][:,0]>a['votes'][:,:3].sum(1))
        assert np.array_equal(decided,new['region']==5);assert np.array_equal(new['region'][~decided],old['region'][~decided])
        assert (a['fallback_samples']<=a['valid_samples']).all();ids=np.flatnonzero(old['region']==0);ids=ids[np.linspace(0,len(ids)-1,min(16,len(ids)),dtype=int)]
        tree=cKDTree(old['centre']);median=np.median(old['u'][np.isfinite(old['u'])&~old['u_replaced']]);counts=np.zeros((len(ids),4),int);refs=np.zeros_like(counts)
        index=json.loads((OUT/'r2/stage1'/path.stem/'maps/index.json').read_text())
        for name,view in index['views'].items():
            base=S0/'fork_inputs/s61'/site/'maps';depth=np.load(base/'mvs'/f'{name}.npy',mmap_mode='r');conf=np.load(base/'conf'/f'{name}.npy',mmap_mode='r');H,W=depth.shape;K=np.array(view['K']);M=np.array(view['W2C']);inv=np.linalg.inv(M)
            for j,pid in enumerate(ids):
                q=M[:3,:3]@old['centre'][pid]+M[:3,3]
                if not .2<=q[2]<=300:continue
                uf=K[0,0]*q[0]/q[2]+K[0,2];vf=K[1,1]*q[1]/q[2]+K[1,2]
                if not (0<=uf<W and 0<=vf<H):continue
                x,y=np.rint([uf,vf]).astype(int);ds=[];sig=[]
                for v in range(y-1,y+2):
                    for u in range(x-1,x+2):
                        if not (0<=v<H and 0<=u<W):continue
                        dd=depth[v,u]
                        if not np.isfinite(dd) or dd<=0 or conf[v,u]<=0:continue
                        world=inv[:3,:3]@np.array([(u-K[0,2])/K[0,0]*dd,(v-K[1,2])/K[1,1]*dd,dd])+inv[:3,3]
                        dist,near=tree.query(world,k=2);idx=int(near[0])
                        if dist[1]<=1 and abs(dist[1]-dist[0])<=1e-12:
                            ii=np.array(tree.query_ball_point(world,dist[0]+1e-12));distance=np.linalg.norm(old['centre'][ii]-world,axis=1);idx=int(ii[distance==distance.min()].min())
                        uu=old['u'][idx] if dist[0]<=1 and not old['u_replaced'][idx] and np.isfinite(old['u'][idx]) else median
                        ds.append(dd);sig.append(np.hypot(uu,.0275))
                if not ds:counts[j,3]+=1;refs[j,3]+=1;continue
                delta=float(np.median(ds))-q[2]
                for arr,sm in [(counts,float(np.median(sig))),(refs,np.hypot(old['u'][pid],.0275))]:
                    m=1.96*np.hypot(sm,old['sigma_p'][pid]);arr[j,0 if delta>m else 1 if delta < -m else 2]+=1
        assert np.array_equal(counts,a['votes'][ids]),(site,prior,'main vote replay')
        assert np.array_equal(refs,a['reference_votes'][ids]),(site,prior,'reference vote replay')
        rows.append(dict(site=site,prior=prior,patches=len(old['region']),sampled_patches=len(ids),views=len(index['views']),all_votes_match=True,disappeared=int(decided.sum()),target_sha256=sha(path)))
    assert len(rows)==8
    result=dict(at=stamp(),status='PASS_DISAPPEARANCE_VOTES_AND_REPLAY',rows=rows,scientific_verdict=None);dump(OUT/'r7/verification/stage0.json',result);dump(DOC/'tables/disappearance_verification_r7.json',result);print(result['status'],flush=True)
if __name__=='__main__':main()
