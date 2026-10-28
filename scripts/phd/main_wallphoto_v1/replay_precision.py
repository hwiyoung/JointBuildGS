"""Independent NumPy projection and explicit pairs at the inherited sampler precision.

The float64 direct-bilinear reference remains unchanged and is reported separately.
This check shares only float32 grid_sample and variance reduction with production;
projection and pairwise aggregation follow independent implementations.
"""
from common import *
import torch
import torch.nn.functional as F


def reference_at_sampler_precision(cam,p,i):
    h=p['heights'][i];H=len(h)
    uv0=np.stack(np.meshgrid(np.arange(25)*.02-.24,np.arange(25)*.02-.24),-1).reshape(-1,2)
    centre=p['centre'][i]+h[:,None]*p['normal'][i]
    X=centre[:,None,:]+uv0[None,:,0,None]*p['tangent1'][i]+uv0[None,:,1,None]*p['tangent2'][i]
    corners=np.array([[-.25,-.25],[.25,-.25],[.25,.25],[-.25,.25]])
    Q=centre[:,None,:]+corners[None,:,0,None]*p['tangent1'][i]+corners[None,:,1,None]*p['tangent2'][i]
    vectors=[];valids=[];stds=[];exact_stds=[];sources=[]
    for j,level in zip(p['selected_images'][i],p['pyramid_levels'][i]):
        if j<0:continue
        im=np.array(cam.gray(int(j),int(level)),copy=True);ih,iw=im.shape
        uv,_,guard=cam.project(X,int(j));cu,_,cg=cam.project(Q,int(j))
        valid=np.isfinite(h)&guard.all(1)&cg.all(1)&(cu[:,:,0]>=0).all(1)&(cu[:,:,0]<cam.w-1).all(1)&(cu[:,:,1]>=0).all(1)&(cu[:,:,1]<cam.h-1).all(1)
        uv=(uv+.5)*[iw/cam.w,ih/cam.h]-.5
        valid&=(uv[:,:,0]>=0).all(1)&(uv[:,:,0]<=iw-1).all(1)&(uv[:,:,1]>=0).all(1)&(uv[:,:,1]<=ih-1).all(1)
        grid=np.stack([2*uv[:,:,0]/(iw-1)-1,2*uv[:,:,1]/(ih-1)-1],-1)
        grid=np.nan_to_num(grid,nan=-3.,posinf=3.,neginf=-3.).astype(np.float32)
        sample=F.grid_sample(torch.from_numpy(im)[None,None],torch.from_numpy(grid)[None],mode='bilinear',padding_mode='zeros',align_corners=True)[0,0]
        centered=sample-sample.mean(-1,keepdim=True);std=centered.square().mean(-1).sqrt()
        vectors.append((centered/(std[:,None]*25).clamp_min(1e-12)).numpy().astype(float));stds.append(std.numpy());valids.append(valid)
        # Independent double-precision interpolation, including constant-source proof.
        safe=np.nan_to_num(uv,nan=0,posinf=0,neginf=0);x=np.clip(safe[:,:,0],0,iw-1);y=np.clip(safe[:,:,1],0,ih-1)
        x0=np.floor(x).astype(int);y0=np.floor(y).astype(int);x1=np.minimum(x0+1,iw-1);y1=np.minimum(y0+1,ih-1);dx=x-x0;dy=y-y0
        a,b,c,d=im[y0,x0],im[y0,x1],im[y1,x0],im[y1,x1]
        value=(1-dx)*(1-dy)*a+dx*(1-dy)*b+(1-dx)*dy*c+dx*dy*d
        exact_stds.append(value.std(-1));sources.append(np.max([a.max(-1),b.max(-1),c.max(-1),d.max(-1)],axis=0)-np.min([a.min(-1),b.min(-1),c.min(-1),d.min(-1)],axis=0))
    vectors=np.array(vectors);valids=np.array(valids);stds=np.array(stds);exact_stds=np.array(exact_stds);sources=np.array(sources)
    scores=np.full(H,np.nan)
    for k in range(H):
        ids=np.flatnonzero(valids[:,k])
        if len(ids)<3 or (stds[ids,k]<=1e-6).any():continue
        scores[k]=np.mean([np.dot(vectors[a,k],vectors[b,k]) for t,a in enumerate(ids) for b in ids[t+1:]])
    return scores,dict(valid=valids,torch_std=stds,float64_std=exact_stds,source_range=sources)
