"""Inspect precision at the finite-status mismatch; no measurement changes."""
from common import *
from cameras import Cameras
import torch
import torch.nn.functional as F
from curves import project_torch


def main():
    folder=O/'validation/independent_replay_diagnostic'
    source=npz(folder/'6908_53360__point_137.npz')
    p={k[len('point_'):]:v for k,v in source.items() if k.startswith('point_')}
    cam=Cameras();rows=[]
    to=lambda x:torch.as_tensor(np.asarray(x),dtype=torch.float64)
    offsets=np.stack(np.meshgrid(np.arange(25)*.02-.24,np.arange(25)*.02-.24),-1).reshape(-1,2)
    centre=p['centre'][0]+p['heights'][0,12]*p['normal'][0]
    X=centre[None,:]+offsets[:,0,None]*p['tangent1'][0]+offsets[:,1,None]*p['tangent2'][0]
    for j,level in zip(p['selected_images'][0],p['pyramid_levels'][0]):
        if j<0:continue
        im=np.array(cam.gray(int(j),int(level)),copy=True);ih,iw=im.shape
        uv,_,guard=cam.project(X,int(j));uv=(uv+.5)*[iw/cam.w,ih/cam.h]-.5
        x=uv[:,0];y=uv[:,1];x0=np.floor(x).astype(int);y0=np.floor(y).astype(int);x1=x0+1;y1=y0+1;dx=x-x0;dy=y-y0
        v=(1-dx)*(1-dy)*im[y0,x0]+dx*(1-dy)*im[y0,x1]+(1-dx)*dy*im[y1,x0]+dx*dy*im[y1,x1]
        u,vv,tguard=project_torch(to(X),to(cam.R[j]),to(cam.t[j]),to(cam.p),cam.w,cam.h)
        u=(u+.5)*(iw/cam.w)-.5;vv=(vv+.5)*(ih/cam.h)-.5
        grid=torch.stack([2*u/(iw-1)-1,2*vv/(ih-1)-1],-1).reshape(1,1,625,2).float()
        sample=F.grid_sample(torch.from_numpy(im)[None,None],grid,mode='bilinear',padding_mode='zeros',align_corners=True).reshape(-1)
        std=(sample-sample.mean()).square().mean().sqrt().item()
        row=dict(image=int(j),level=int(level),numpy_float64_std=float(v.std()),torch_float32_std=std,
                 numpy_nonzero=bool(v.std()>1e-6),torch_nonzero=bool(std>1e-6),
                 numpy_min=float(v.min()),numpy_max=float(v.max()),torch_min=float(sample.min()),torch_max=float(sample.max()),
                 source_pixel_min=float(min(im[y0,x0].min(),im[y0,x1].min(),im[y1,x0].min(),im[y1,x1].min())),
                 source_pixel_max=float(max(im[y0,x0].max(),im[y0,x1].max(),im[y1,x0].max(),im[y1,x1].max())),
                 guards_equal=bool(np.array_equal(guard,tguard.numpy())),max_projection_difference=float(np.max(abs(np.stack([u.numpy(),vv.numpy()],-1)-uv))))
        rows.append(row);print(json.dumps(row),flush=True)
    rec=dict(at=now(),tile='6908_53360',point_id=p['point_id'][0],height=float(p['heights'][0,12]),stored_curve=source['stored'][12],reference_curve=source['expected'][12],rows=rows,scientific_verdict=None)
    dump(folder/'variance_boundary.json',rec)


if __name__=='__main__':main()
