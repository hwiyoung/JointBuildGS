"""Image-at-a-time NCC for both candidate planes, clipped and full. No training."""
import json,time,sys,resource
import numpy as np
import torch
import torch.nn.functional as F
from preflight import C,O,Path,dump,sha,now
from geometry import loadz,savez
from photo_cameras import Cameras
BASE=O/'r1'

def project(X,R,t,p,w,h):
    Q=X@R.T+t;z=Q[...,2];x=Q[...,0]/z;y=Q[...,1]/z
    fx,fy,cx,cy,k1,k2,p1,p2,k3,k4,k5,k6=p;r=x*x+y*y
    radial=(1+k1*r+k2*r*r+k3*r**3)/(1+k4*r+k5*r*r+k6*r**3)
    px=fx*x+cx;py=fy*y+cy
    u=fx*(x*radial+2*p1*x*y+p2*(r+2*x*x))+cx;v=fy*(y*radial+p1*(r+2*y*y)+2*p2*x*y)+cy
    guard=(z>0)&torch.isfinite(u)&torch.isfinite(v)&(px>=-200)&(px<=w+200)&(py>=-200)&(py<=h+200)&((u-px)**2+(v-py)**2<400**2)
    return u,v,guard

def ncc_vectors(samples,mask):
    count=mask.sum(-1);mean=(samples*mask).sum(-1)/count.clamp_min(1)
    centered=(samples-mean[...,None])*mask;ss=centered.square().sum(-1)
    std=(ss/count.clamp_min(1)).sqrt()
    vectors=centered/ss.sqrt().clamp_min(1e-12)[...,None]
    return vectors,std,count

def compute(g,device):
    torch.set_num_threads(4);started=time.monotonic();cam=Cameras();N=len(g['centres']);H=g['heights'].shape[1];P=N*2
    c=g['centres'].reshape(P,3);normal=g['normals'].reshape(P,3);e1=g['tangent1'].reshape(P,3);e2=g['tangent2'].reshape(P,3)
    hh=np.repeat(g['heights'],2,axis=0);mask=g['masks'].reshape(P,H,625);sel=g['selected_images'].reshape(P,10)
    available=g['available'].reshape(P);sel=sel.copy();sel[~available]=-1
    dev=torch.device(device);to=lambda a:torch.as_tensor(np.asarray(a),device=dev,dtype=torch.float64)
    tt=time.monotonic();p=to(cam.p);R=to(cam.R);t=to(cam.t);c=to(c);normal=to(normal);e1=to(e1);e2=to(e2);hh=to(hh)
    offsets=to(np.stack(np.meshgrid(np.arange(25)*.02-.24,np.arange(25)*.02-.24,indexing='xy'),-1).reshape(625,2))
    corners=to([[-.25,-.25],[.25,-.25],[.25,.25],[-.25,.25]])
    masks=torch.as_tensor(mask,device=dev)
    acc=torch.zeros((2,P,H,625),device=dev,dtype=torch.float64);normsum=torch.zeros((2,P,H),device=dev,dtype=torch.float64);counts=torch.zeros((2,P,H),device=dev);zero=torch.zeros((2,P,H),device=dev)
    textures=np.full((2,P,10),np.nan);levels=np.full((P,10),-1,np.int8)
    validh=np.isfinite(g['heights']);zeroh=np.argmin(np.where(validh,abs(g['heights']),np.inf),axis=1).repeat(2)
    decode_seconds=0.;arithmetic_seconds=0.;cameras=np.unique(sel[sel>=0]);per_image=[]
    if device=='cuda':torch.cuda.synchronize()
    arithmetic_seconds+=time.monotonic()-tt
    for cj,j in enumerate(cameras):
        local,slots=np.where(sel==j);dist=np.linalg.norm(g['centres'].reshape(P,3)[local]-cam.centres[j],axis=1)
        gsd=dist/np.sqrt(cam.p[0]*cam.p[1]);lev=np.argmin(abs(gsd[:,None]*2.**np.arange(6)-.02),axis=1);lev[gsd>=.02]=0
        levels[local,slots]=lev;tt=time.monotonic();images=cam.gray_pyramid(int(j),set(lev.tolist()));decode=time.monotonic()-tt;decode_seconds+=decode;tt=time.monotonic()
        for level,image in images.items():
            ih,iw=image.shape;im=torch.as_tensor(np.array(image,copy=True),device=dev,dtype=torch.float64)[None,None]
            group=np.flatnonzero(lev==level)
            for pos in range(0,len(group),8):
                picked=group[pos:pos+8];ii=local[picked];ss=slots[picked];ix=torch.as_tensor(ii,device=dev)
                centres=c[ix,None,:]+hh[ix,:,None]*normal[ix,None,:]
                X=centres[:,:,None,:]+offsets[None,None,:,0,None]*e1[ix,None,None,:]+offsets[None,None,:,1,None]*e2[ix,None,None,:]
                u,v,guard=project(X,R[j],t[j],p,cam.w,cam.h)
                cornerX=centres[:,:,None,:]+corners[None,None,:,0,None]*e1[ix,None,None,:]+corners[None,None,:,1,None]*e2[ix,None,None,:]
                cu,cv,cg=project(cornerX,R[j],t[j],p,cam.w,cam.h)
                good=cg.all(-1)&(cu>=0).all(-1)&(cu<cam.w-1).all(-1)&(cv>=0).all(-1)&(cv<cam.h-1).all(-1)&guard.all(-1)&torch.isfinite(hh[ix])
                u=(u+.5)*(iw/cam.w)-.5;v=(v+.5)*(ih/cam.h)-.5
                good&=(u>=0).all(-1)&(u<=iw-1).all(-1)&(v>=0).all(-1)&(v<=ih-1).all(-1)
                grid=torch.stack([2*u/(iw-1)-1,2*v/(ih-1)-1],-1).reshape(1,len(ii)*H,625,2)
                grid=torch.nan_to_num(grid,nan=-3.,posinf=3.,neginf=-3.)
                samples=F.grid_sample(im,grid,mode='bilinear',padding_mode='zeros',align_corners=True).reshape(len(ii),H,625)
                for k in range(2):
                    mk=masks[ix] if k==0 else torch.ones_like(masks[ix]);vectors,std,pixels=ncc_vectors(samples,mk)
                    gv=good&(pixels>=313);nonzero=std>1e-6
                    vectors=torch.where((gv&nonzero)[...,None],vectors,0.)
                    acc[k,ix]+=vectors;normsum[k,ix]+=vectors.square().sum(-1);counts[k,ix]+=gv;zero[k,ix]+=gv&~nonzero
                    zi=torch.as_tensor(zeroh[ii],device=dev);row=torch.arange(len(ii),device=dev)
                    textures[k,ii,ss]=torch.where(gv[row,zi],std[row,zi],torch.nan).cpu().numpy()
                del X,u,v,grid,samples,vectors,cornerX
            del im
        if device=='cuda':torch.cuda.synchronize()
        arithmetic=time.monotonic()-tt;arithmetic_seconds+=arithmetic
        per_image.append(dict(camera=int(j),planes=len(local),decode_seconds=decode,arithmetic_seconds=arithmetic))
        del images,image
        if cj%25==0:print('PHOTO_SCORE',device,cj+1,len(cameras),'seconds',time.monotonic()-started,flush=True)
    tt=time.monotonic();score=(acc.square().sum(-1)-normsum)/(counts*(counts-1)).clamp_min(1)
    score=torch.where((counts>=3)&(zero==0),score,torch.nan).cpu().numpy().reshape(2,N,2,H)
    count=counts.cpu().numpy().reshape(2,N,2,H).astype(np.uint8)
    texture=np.full((2,N,2),np.nan)
    for k in range(2):
        for i in range(P):
            v=textures[k,i];v=v[np.isfinite(v)]
            if len(v):texture[k,i//2,i%2]=np.median(v)
    best=np.full((2,N,2),np.nan);best_height=best.copy()
    for k in range(2):
        for i in range(N):
            for j in range(2):
                if np.isfinite(score[k,i,j]).any():
                    ix=np.nanargmax(score[k,i,j]);best[k,i,j]=score[k,i,j,ix];best_height[k,i,j]=g['heights'][i,ix]
    if device=='cuda':torch.cuda.synchronize()
    arithmetic_seconds+=time.monotonic()-tt
    timing=dict(at=now(),device=device,points=N,cameras=len(cameras),height_slots=H,
        total_seconds=time.monotonic()-started,decode_seconds=decode_seconds,arithmetic_seconds=arithmetic_seconds,
        peak_cpu_rss_gib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024**2,
        peak_gpu_gib=torch.cuda.max_memory_allocated()/2**30 if device=='cuda' else None,
        gpu_name=torch.cuda.get_device_name() if device=='cuda' else None,
        torch_version=torch.__version__,per_image=per_image,scientific_verdict=None)
    return dict(curves=score,valid_image_count=count,best_score=best,best_height=best_height,
        texture=texture,texture_by_view=textures.reshape(2,N,2,10),pyramid_levels=levels.reshape(N,2,10)),timing

def main(device):
    p=BASE/'photo_benchmark/planes.npz';lock=C/f'photo_score.{device}.lock.json'
    dump(lock,dict(at=now(),config_sha256=sha(C/'judgecheck_v1.json'),planes_sha256=sha(p),
        source_sha256={f:sha(Path(__file__).parent/f) for f in ['photo_score.py','photo_cameras.py']},
        clipped_texture='per-view population SD at zero offset on retained pixels, median across views',
        interpolation_and_ncc_precision='float64; inherited grayscale pyramid values unchanged',
        ncc='normalized masked vectors; identical masks across views; mean over all unordered pairs; >=3 valid views and no zero-variance view',
        truth_opened=False,training=False,scientific_verdict=None))
    g=loadz(p);result,timing=compute(g,device);savez(BASE/f'photo_benchmark/scores_{device}.npz',**result)
    timing['output_sha256']=sha(BASE/f'photo_benchmark/scores_{device}.npz');dump(BASE/f'photo_benchmark/timing_{device}.json',timing)
    print('TIMING',json.dumps({k:v for k,v in timing.items() if k!='per_image'}),flush=True)

if __name__=='__main__':main(sys.argv[1])
