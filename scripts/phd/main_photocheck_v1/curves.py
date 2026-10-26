"""Image-batched plane sweep. GPU operations are exclusively photo-curve arithmetic."""
import time
import torch
import torch.nn.functional as F
from common import *
from cameras import Cameras

def height_array(g):
    base=np.array(load(C/'photocheck_v1.json')['heights']['base_m'],np.float32)
    h=np.full((len(g['centre']),148),np.nan,np.float32);h[:,:141]=base
    extra=np.isfinite(g['mvs_p'])&(abs(g['mvs_p'])>5)
    h[extra,141:]=g['mvs_p'][extra,None]+np.arange(-3,4,dtype=np.float32)[None,:]*.1
    return h

def project_torch(X,R,t,p,w,h):
    Q=X@R.T+t;z=Q[...,2];x=Q[...,0]/z;y=Q[...,1]/z
    fx,fy,cx,cy,k1,k2,p1,p2,k3,k4,k5,k6=p;r=x*x+y*y
    radial=(1+k1*r+k2*r*r+k3*r**3)/(1+k4*r+k5*r*r+k6*r**3)
    px=fx*x+cx;py=fy*y+cy
    u=fx*(x*radial+2*p1*x*y+p2*(r+2*x*x))+cx;v=fy*(y*radial+p1*(r+2*y*y)+2*p2*x*y)+cy
    guard=(z>0)&torch.isfinite(u)&torch.isfinite(v)&(px>=-200)&(px<=w+200)&(py>=-200)&(py<=h+200)&((u-px)**2+(v-py)**2<400**2)
    return u,v,guard

def compute(g,selection,device='cuda',chunk_points=8192,subbatch=48,progress=None):
    torch.set_num_threads(8)
    cam=Cameras();n=len(g['centre']);heights=height_array(g)
    scores=np.full((n,148),np.nan,np.float32);texture=np.full(n,np.nan,np.float32);valid_count=np.zeros((n,148),np.uint8)
    texture_by_view=np.full((n,10),np.nan,np.float32);zero_count=np.zeros((n,148),np.uint8)
    levels=np.full((n,10),-1,np.int8);timing=[]
    dev=torch.device(device);to=lambda a:torch.as_tensor(np.asarray(a),device=dev,dtype=torch.float64)
    p=to(cam.p);R=to(cam.R);t=to(cam.t)
    uv=np.stack(np.meshgrid(np.arange(25)*.02-.24,np.arange(25)*.02-.24,indexing='xy'),-1).reshape(625,2)
    offsets=to(uv);corners=to([[-.25,-.25],[.25,-.25],[.25,.25],[-.25,.25]])
    t0=time.monotonic()
    for start in range(0,n,chunk_points):
        stop=min(n,start+chunk_points);ids0=np.arange(start,stop);N=len(ids0)
        acc=torch.zeros((N,148,625),device=dev);normsum=torch.zeros((N,148),device=dev);counts=torch.zeros((N,148),device=dev);missing_variance=torch.zeros((N,148),device=dev)
        c=to(g['centre'][ids0]);normal=to(g['normal'][ids0]);e1=to(g['tangent1'][ids0]);e2=to(g['tangent2'][ids0]);hh=to(heights[ids0]);sel=selection['selected_images'][ids0]
        for j in np.unique(sel[sel>=0]):
            local,slots=np.where(sel==j)
            distance=np.linalg.norm(g['centre'][ids0[local]]-cam.centres[j],axis=1)
            gsd=distance/np.sqrt(cam.p[0]*cam.p[1]);opts=gsd[:,None]*2.**np.arange(6)
            lev=np.argmin(abs(opts-.02),axis=1);lev[gsd>=.02]=0
            levels[ids0[local],slots]=lev
            for level in np.unique(lev):
                inds=np.flatnonzero(lev==level);local2=local[inds];slots2=slots[inds]
                image=cam.gray(int(j),int(level));ih,iw=image.shape
                # Explicit owned copy avoids non-writable NumPy mappings and releases after one camera.
                im=torch.as_tensor(np.array(image,copy=True),device=dev,dtype=torch.float32)[None,None];del image
                for pos in range(0,len(local2),subbatch):
                    ii=local2[pos:pos+subbatch];ss=slots2[pos:pos+subbatch];ix=torch.as_tensor(ii,device=dev)
                    centres=c[ix,None,:]+hh[ix,:,None]*normal[ix,None,:]
                    X=centres[:,:,None,:]+offsets[None,None,:,0,None]*e1[ix,None,None,:]+offsets[None,None,:,1,None]*e2[ix,None,None,:]
                    u,v,guard=project_torch(X,R[j],t[j],p,cam.w,cam.h)
                    # Full 50 cm square, beyond the +/-24 cm sample-centre support.
                    cornerX=centres[:,:,None,:]+corners[None,None,:,0,None]*e1[ix,None,None,:]+corners[None,None,:,1,None]*e2[ix,None,None,:]
                    cu,cv,cg=project_torch(cornerX,R[j],t[j],p,cam.w,cam.h)
                    good=cg.all(-1)&(cu>=0).all(-1)&(cu<cam.w-1).all(-1)&(cv>=0).all(-1)&(cv<cam.h-1).all(-1)&guard.all(-1)&torch.isfinite(hh[ix])
                    # Resize uses exact actual image dimensions, including odd-height pyramid levels.
                    u=(u+.5)*(iw/cam.w)-.5;v=(v+.5)*(ih/cam.h)-.5
                    good&=(u>=0).all(-1)&(u<=iw-1).all(-1)&(v>=0).all(-1)&(v<=ih-1).all(-1)
                    grid=torch.stack([2*u/(iw-1)-1,2*v/(ih-1)-1],-1).reshape(1,len(ii)*148,625,2)
                    grid=torch.nan_to_num(grid,nan=-3.,posinf=3.,neginf=-3.).float()
                    samples=F.grid_sample(im,grid,mode='bilinear',padding_mode='zeros',align_corners=True).reshape(len(ii),148,625)
                    centered=samples-samples.mean(-1,keepdim=True);std=(centered.square().mean(-1)).sqrt()
                    texture_by_view[ids0[ii],ss]=torch.where(good[:,70],std[:,70],torch.nan).cpu().numpy()
                    nonzero=std>1e-6
                    vectors=centered/(std[:,:,None]*25).clamp_min(1e-12)
                    vectors=torch.where((good&nonzero)[:,:,None],vectors,0.)
                    acc[ix]+=vectors;normsum[ix]+=vectors.square().sum(-1);counts[ix]+=good;missing_variance[ix]+=good&~nonzero
                    del X,u,v,grid,samples,centered,vectors
                del im
        score=(acc.square().sum(-1)-normsum)/(counts*(counts-1)).clamp_min(1.)
        good=(counts>=3)&(missing_variance==0)
        scores[ids0]=torch.where(good,score,torch.nan).cpu().numpy()
        valid_count[ids0]=counts.cpu().numpy().astype(np.uint8);zero_count[ids0]=missing_variance.cpu().numpy().astype(np.uint8)
        for i in ids0:
            vv=texture_by_view[i];texture[i]=np.median(vv[np.isfinite(vv)]) if np.isfinite(vv).any() else np.nan
        if device=='cuda':torch.cuda.synchronize()
        timing.append(dict(done=stop,total=n,elapsed_seconds=time.monotonic()-t0))
        print('curve progress',device,stop,n,round(time.monotonic()-t0,2),flush=True)
        if progress:dump(progress,dict(device=device,**timing[-1],at=now(),scientific_verdict=None))
        del acc,normsum,counts,missing_variance
    return dict(heights=heights,curve=scores,texture=texture,texture_by_view=texture_by_view,valid_images_per_height=valid_count,zero_variance_images_per_height=zero_count,pyramid_levels=levels),dict(seconds=time.monotonic()-t0,points=n,device=device,chunk_points=chunk_points,subbatch=subbatch,peak_gpu_gib=torch.cuda.max_memory_allocated()/2**30 if device=='cuda' else None,environment=env())
