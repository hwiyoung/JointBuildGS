"""CPU, GT-free per-view disappearance votes; immutable r2 values outside region 0."""
import sys,warnings
import numpy as np
from scipy.spatial import cKDTree
from common import *

def loadz(p):
    with np.load(p) as z:return {k:z[k] for k in z.files}

def nearest(tree,centres,q):
    if not len(q):return np.empty(0),np.empty(0,np.int64)
    ds,ix=tree.query(q,k=2,workers=1);d=ds[:,0];ind=ix[:,0].copy()
    for j in np.flatnonzero((ds[:,1]<=1)&np.isclose(ds[:,0],ds[:,1],atol=1e-12,rtol=0)):
        ids=np.asarray(tree.query_ball_point(q[j],d[j]+1e-12));dd=np.linalg.norm(centres[ids]-q[j],axis=1)
        ind[j]=ids[dd==dd.min()].min();d[j]=dd.min()
    return d,ind

def test(d,cameras,read_depth):
    n=len(d['region']);ids=np.flatnonzero(d['region']==0);points=d['centre'][ids].astype(float)
    valid_u=np.isfinite(d['u'])&~d['u_replaced'];donors=d['u'][valid_u]
    assert len(donors),'NO_ORIGINAL_U_DONORS';median=float(np.median(donors));assert median>0
    tree=cKDTree(d['centre'].astype(float));count=np.zeros((n,4),np.int32);ref=np.zeros_like(count)
    # Columns: through, occluded, surface, no evidence (in-frame tested views only).
    fallback=np.zeros(n,np.int64);samples=np.zeros(n,np.int64);windows=np.zeros(n,np.int32);fallback_windows=np.zeros(n,np.int32)
    reasons=np.zeros(3,np.int64);rows=[];binding={}
    for j,cam in enumerate(cameras):
        K=np.asarray(cam['K'],float);M=np.asarray(cam['W2C'],float);q=points@M[:3,:3].T+M[:3,3];z=q[:,2]
        with np.errstate(divide='ignore',invalid='ignore'):
            uf=K[0,0]*q[:,0]/z+K[0,2];vf=K[1,1]*q[:,1]/z+K[1,2]
        visible=(z>=.2)&(z<=300)&np.isfinite(uf)&np.isfinite(vf)&(uf>=0)&(vf>=0)&(uf<cam['W'])&(vf<cam['H'])
        local=np.flatnonzero(visible);dest=ids[local]
        if not len(dest):continue
        dep,conf,paths=read_depth(cam['name']);binding.update({str(p):sha(p) for p in paths})
        assert dep.shape==(cam['H'],cam['W']) and conf.shape==dep.shape
        uv=np.rint(np.c_[uf[local],vf[local]]).astype(int)
        offs=np.array([(u,v) for v in [-1,0,1] for u in [-1,0,1]])
        pixels=uv[:,None,:]+offs;px,py=pixels[:,:,0],pixels[:,:,1]
        inside=(px>=0)&(py>=0)&(px<cam['W'])&(py<cam['H']);xx=np.clip(px,0,cam['W']-1);yy=np.clip(py,0,cam['H']-1)
        depth=dep[yy,xx].astype(float);valid=inside&np.isfinite(depth)&(depth>0)&(conf[yy,xx]>0)
        vu,vv=px[valid],py[valid];dd=depth[valid]
        xyz=np.c_[(vu-K[0,2])/K[0,0]*dd,(vv-K[1,2])/K[1,1]*dd,dd]
        inv=np.linalg.inv(M);world=xyz@inv[:3,:3].T+inv[:3,3]
        distance,owner=nearest(tree,d['centre'],world);missing=distance>1;replaced=(~missing)&d['u_replaced'][owner];bad=(~missing)&~replaced&~np.isfinite(d['u'][owner]);use=missing|replaced|bad
        u=np.where(use,median,d['u'][owner]);sigma=np.full(depth.shape,np.nan);sigma[valid]=np.hypot(u,.0275)
        depth[~valid]=np.nan
        with warnings.catch_warnings():
            warnings.simplefilter('ignore',RuntimeWarning);dm=np.nanmedian(depth,axis=1);sm=np.nanmedian(sigma,axis=1)
        margin=1.96*np.hypot(sm,d['sigma_p'][dest]);reference=1.96*np.sqrt(d['u'][dest]**2+.0275**2+d['sigma_p'][dest]**2)
        good=np.isfinite(dm)&np.isfinite(margin);delta=dm-z[local]
        for counts,m in [(count,margin),(ref,reference)]:
            cls=np.full(len(dest),3,np.int8);cls[good]=2;cls[good&(delta>m)]=0;cls[good&(delta < -m)]=1
            counts[dest,cls]+=1
        rep=np.zeros_like(valid);rep[valid]=use;fallback[dest]+=rep.sum(1);samples[dest]+=valid.sum(1)
        windows[dest]+=good;fallback_windows[dest]+=good&rep.any(1);reasons+=np.array([missing.sum(),replaced.sum(),bad.sum()])
        rows.append(dict(camera=cam['name'],tested=len(dest),evidence=int(good.sum()),valid_samples=int(valid.sum()),fallback_samples=int(use.sum())))
        if j%40==0:print('DISAPPEAR',j+1,len(cameras),len(ids),flush=True)
    disappears=(count[:,0]>=2)&(count[:,0]*2>count[:,:3].sum(1))&(d['region']==0)
    reference=(ref[:,0]>=2)&(ref[:,0]*2>ref[:,:3].sum(1))&(d['region']==0)
    data=dict(votes=count,reference_votes=ref,disappeared=disappears,reference_disappeared=reference,fallback_samples=fallback,valid_samples=samples,evidence_windows=windows,fallback_windows=fallback_windows)
    return data,dict(u_median=median,original_u_donors=len(donors),valid_samples=int(samples.sum()),fallback_samples=int(fallback.sum()),fallback_fraction=float(fallback.sum()/samples.sum()) if samples.sum() else None,
        fallback_reason_counts=dict(zip(['no_neighbour','replaced_neighbour','missing_u'],reasons.tolist())),views=rows,files=binding,GT_loaded_before_decision=False)

def areas(d,a,site,prior,split):
    rows=[]
    for scope,mask in [('eval',d['in_eval']),('band',~d['in_eval'])]:
        for kind in [1,2]:
            for replacement,sub in [('all',np.ones(len(mask),bool)),('original',~d['any_replaced']),('replaced',d['any_replaced'])]:
                sel=mask&(d['kind']==kind)&sub;old=sel&(d['region']==0);moved=sel&a['disappeared'];reference=sel&a['reference_disappeared'];den=int(a['valid_samples'][old].sum());num=int(a['fallback_samples'][old].sum())
                rows.append(dict(split=split,site=site,prior=prior,range=scope,kind=kind,replacement=replacement,old_unobserved_count=int(old.sum()),old_unobserved_area_m2=float(d['area'][old].sum()),disappeared_count=int(moved.sum()),disappeared_area_m2=float(d['area'][moved].sum()),remaining_unobserved_area_m2=float(d['area'][old&~moved].sum()),reference_disappeared_area_m2=float(d['area'][reference].sum()),valid_samples=den,fallback_samples=num,fallback_fraction=num/den if den else None))
    return rows

def main():
    assert sha(CFG/'target_v1.r7.stage0.json')==json.loads((CFG/'target_v1.r7.stage0.lock.json').read_text())['config_sha256']
    cfg,_=locked_r2();sites=sys.argv[1:] or cfg['sites']+cfg['deferred_sites'];rows=[]
    sys.path.insert(0,str(REPO/'scripts/phd/main_axes71_v2'));import mvs_surface as MS
    for site in sites:
        cameras,_=MS.cameras(site)
        for prior in cfg['priors']:
            root=OUT/'r7/stage0';dest=OUT/'r7/targets'/f'{site}_{prior}.npz';assert not dest.exists()
            src=OUT/'r2/targets'/dest.name;d=loadz(src);base=S0/'fork_inputs/s61'/site/'maps'
            def read(name):
                paths=[base/'mvs'/f'{name}.npy',base/'conf'/f'{name}.npy'];return np.load(paths[0],mmap_mode='r'),np.load(paths[1],mmap_mode='r'),paths
            a,record=test(d,cameras,read);np.savez_compressed(root/f'{site}_{prior}.votes.npz',**a)
            out={k:v.copy() for k,v in d.items()};gone=a['disappeared'];out['region'][gone]=5
            for key in ['h','sigma','target']:out[key][gone]=np.nan
            out['disappeared']=gone;np.savez_compressed(dest,**out)
            record.update(at=stamp(),input_sha256=sha(src),output_sha256=sha(dest),config_sha256=sha(CFG/'target_v1.r7.stage0.json'),scientific_verdict=None)
            dump(root/f'{site}_{prior}.json',record);rr=areas(d,a,site,prior,'experiment');rows+=rr;dump(root/f'{site}_{prior}.areas.json',dict(rows=rr,scientific_verdict=None))
            print('DISAPPEAR_DONE',site,prior,int(gone.sum()),float(d['area'][gone].sum()),flush=True)
    # Per-pair files allow separately queued sites without clobbering prior calculations.
    public=[]
    for p in (OUT/'r7/stage0').glob('*.areas.json'):public+=json.loads(p.read_text())['rows']
    dump(DOC/'tables/disappearance_areas_r7.json',dict(rows=public,scientific_verdict=None))
if __name__=='__main__':main()
