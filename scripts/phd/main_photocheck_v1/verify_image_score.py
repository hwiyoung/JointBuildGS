"""Independent NumPy bilinear/pairwise NCC replay on actual stored point curves."""
import argparse
from common import *
from cameras import Cameras
def reference(cam,p,i):
    h=p['heights'][i];goodh=np.isfinite(h);H=len(h);scores=np.full(H,np.nan);uv0=np.stack(np.meshgrid(np.arange(25)*.02-.24,np.arange(25)*.02-.24),-1).reshape(-1,2)
    centre=p['centre'][i]+h[:,None]*p['normal'][i];X=centre[:,None,:]+uv0[None,:,0,None]*p['tangent1'][i]+uv0[None,:,1,None]*p['tangent2'][i]
    corners=np.array([[-.25,-.25],[.25,-.25],[.25,.25],[-.25,.25]]);Q=centre[:,None,:]+corners[None,:,0,None]*p['tangent1'][i]+corners[None,:,1,None]*p['tangent2'][i]
    samples=[];valids=[]
    for j,level in zip(p['selected_images'][i],p['pyramid_levels'][i]):
        if j<0:continue
        im=cam.gray(int(j),int(level));ih,iw=im.shape;uv,_,guard=cam.project(X,int(j));cu,_,cg=cam.project(Q,int(j))
        valid=goodh&guard.all(1)&cg.all(1)&(cu[:,:,0]>=0).all(1)&(cu[:,:,0]<cam.w-1).all(1)&(cu[:,:,1]>=0).all(1)&(cu[:,:,1]<cam.h-1).all(1)
        uv=(uv+.5)*[iw/cam.w,ih/cam.h]-.5
        valid&=(uv[:,:,0]>=0).all(1)&(uv[:,:,0]<=iw-1).all(1)&(uv[:,:,1]>=0).all(1)&(uv[:,:,1]<=ih-1).all(1)
        safe=np.nan_to_num(uv,nan=0,posinf=0,neginf=0);x=np.clip(safe[:,:,0],0,iw-1);y=np.clip(safe[:,:,1],0,ih-1);x0=np.floor(x).astype(int);y0=np.floor(y).astype(int);x1=np.minimum(x0+1,iw-1);y1=np.minimum(y0+1,ih-1);dx=x-x0;dy=y-y0
        v=(1-dx)*(1-dy)*im[y0,x0]+dx*(1-dy)*im[y0,x1]+(1-dx)*dy*im[y1,x0]+dx*dy*im[y1,x1];samples.append(v);valids.append(valid)
    if not samples:return scores
    samples=np.array(samples);valids=np.array(valids)
    for k in range(H):
        a=samples[valids[:,k],k];n=len(a)
        if n<3:continue
        std=a.std(1)
        if (std<=1e-6).any():continue
        a=(a-a.mean(1,keepdims=True))/std[:,None]
        # Deliberately explicit pairs instead of the production vector-sum identity.
        scores[k]=np.mean([np.mean(a[i]*a[j]) for i in range(n) for j in range(i+1,n)])
    return scores
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--stage',default='pilot');a=ap.parse_args();cam=Cameras();rows=[];rng=np.random.default_rng(20261026)
    for prior in ['LoD2','ALS']:
        files=sorted((O/'work'/a.stage).glob(f'*__{prior}.npz'));assert files
        # Evenly spread files, one seeded point each; no GT filters.
        for fi in np.linspace(0,len(files)-1,min(4,len(files)),dtype=int):
            p=npz(files[fi]);candidates=np.flatnonzero((p['selected_count']>=3)&(p['texture']>=5)&(p['kind']==1))
            if not len(candidates):continue
            i=int(rng.choice(candidates));scores=reference(cam,p,i);stored=p['curve'][i].astype(float);mask=np.isfinite(scores)&np.isfinite(stored)
            diff=abs(scores[mask]-stored[mask]);finite_diff=int((np.isfinite(scores)!=np.isfinite(stored)).sum())
            row=dict(point_id=p['point_id'][i],file=files[fi].name,heights_compared=int(mask.sum()),finite_status_disagreement=finite_diff,max_abs_difference=float(diff.max()) if len(diff) else None,median_abs_difference=float(np.median(diff)) if len(diff) else None)
            assert finite_diff==0 and (not len(diff) or diff.max()<.01),row
            rows.append(row)
    dump(O/'gates/image_score.json',dict(status='PASS',sample_points=len(rows),scope='seeded actual-image NumPy float64 projection and direct bilinear interpolation, explicit pairwise NCC, compared to stored float16 curve; sample check only',rows=rows,environment=env()));print('independent image-score replay PASS',clean(rows))
if __name__=='__main__':main()
