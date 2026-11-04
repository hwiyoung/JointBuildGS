"""FARPULL freespace v1. Decisions detached; native weights, opacity gradients only.

The explicitly requested historical lt_dynnow renderer is retained for exact
comparability. This opt-in module does not change its normal/depth/RGB renders.
"""
import json
import math
from pathlib import Path
import numpy as np
import torch


@torch.no_grad()
def source_gate(depth, sources):
    """Each source is (D, sigma, V, present); absent values never participate."""
    gate=torch.ones_like(depth);any_source=torch.zeros_like(depth,dtype=torch.bool)
    margins=[];responsibilities=[]
    for target,sigma,validity,present in sources:
        present=present.bool()
        if bool(present.any()):
            assert bool((torch.isfinite(target[present]) & torch.isfinite(sigma[present]) &
                         (sigma[present]>0) & torch.isfinite(validity[present]) &
                         (validity[present]>0) & (validity[present]<1)).all())
        r=torch.zeros_like(depth);margin=torch.full_like(depth,float('inf'))
        # The clipping is exactly lt_term's inherited numerical convention.
        v=validity[present].clamp(1e-4,1.-1e-4);s=sigma[present]
        log_odds=torch.log(v)-torch.log1p(-v)-math.log(.1)-torch.log(s)-.5*math.log(2*math.pi)
        residual=(depth[present]-target[present])/s
        r[present]=torch.sigmoid(log_odds-.5*residual.square())
        margin[present]=torch.where(log_odds>0,s*torch.sqrt((2*log_odds).clamp_min(0)),float('inf'))
        gate*=1-r;any_source|=present;margins.append(margin);responsibilities.append(r)
    gate[~any_source]=0
    assert bool(torch.isfinite(gate).all())
    return gate.detach(),margins,responsibilities


@torch.no_grad()
def sources_for(j,cam):
    """Copy the exact eligibility and ray-normal uncertainty in lt_losses."""
    name=cam.image_name;P,M,A=j.P[name],j.M[name],j.A[name]
    loc=j.lt_locations[name].long();table=j.lt_values
    eligible=(loc>=0)&(loc<len(table['v_prior']))&torch.isfinite(P)&(P>0)
    yy,xx=torch.where(eligible);ids=loc[eligible];H,W=P.shape
    proj=cam.projection_matrix.T
    fx,fy=proj[0,0]*W/2,proj[1,1]*H/2
    cx,cy=proj[0,2]*W/2+(W-1)/2,proj[1,2]*H/2+(H-1)/2
    ray=torch.stack(((xx-cx)/fx,(yy-cy)/fy,torch.ones_like(xx,dtype=P.dtype)),1)
    ray=torch.nn.functional.normalize(ray@cam.world_view_transform.inverse()[:3,:3],dim=1)
    normal=table['normal'][ids].to(P.dtype)
    assert bool((torch.isfinite(normal).all(1)&((normal.norm(dim=1)-1).abs()<1e-4)).all())
    cos=(ray*normal).sum(1).abs().clamp_min(.25)
    sp,sm,vp,vm=[torch.zeros_like(P) for _ in range(4)]
    sp[eligible]=table['sigma_prior'][ids].to(P.dtype)/cos
    sm[eligible]=table['sigma_mvs'][ids].to(P.dtype)/cos
    vp[eligible]=table['v_prior'][ids].to(P.dtype)
    vm[eligible]=table['v_mvs'][ids].to(P.dtype)
    obs=eligible&torch.isfinite(M)&(M>0)&(A>0)&torch.isfinite(vm)
    return [(P,sp,vp,eligible),(M,sm,vm,obs)],loc


@torch.no_grad()
def centre_flags(cam,g,sources,margins,inside):
    xyz=g.get_xyz.detach();H,W=cam.image_height,cam.image_width
    xyzh=torch.cat((xyz,torch.ones_like(xyz[:,:1])),1)
    camera=xyzh@cam.world_view_transform
    clip=xyzh@cam.full_proj_transform
    uv=(clip[:,:2]/clip[:,3:4]+1)*torch.tensor([W,H],device=xyz.device)/2-.5
    good=torch.isfinite(uv).all(1)&torch.isfinite(camera[:,2])&(camera[:,2]>0)
    pixels=torch.round(torch.nan_to_num(uv,nan=-1e6,posinf=-1e6,neginf=-1e6)).long()
    good&=(pixels[:,0]>=0)&(pixels[:,0]<W)&(pixels[:,1]>=0)&(pixels[:,1]<H)&inside
    if g.frozen_mask is not None:good&=~g.frozen_mask
    f=torch.zeros(len(xyz),device=xyz.device,dtype=xyz.dtype)
    ids=torch.where(good)[0];x,y=pixels[ids,0],pixels[ids,1]
    for (target,sigma,v,present),margin in zip(sources,margins):
        front=present[y,x]&(camera[ids,2]<target[y,x]-margin[y,x])
        f[ids]=torch.maximum(f[ids],torch.where(front,v[y,x].clamp(1e-4,1-1e-4),0.))
    return f.detach()


def feature_render(cam,g,feature,opacity=None):
    """Native compositing with geometry detached. No SH/normal/depth loss path."""
    from diff_surfel_rasterization import GaussianRasterizationSettings,GaussianRasterizer
    settings=GaussianRasterizationSettings(image_height=int(cam.image_height),image_width=int(cam.image_width),
        tanfovx=math.tan(cam.FoVx*.5),tanfovy=math.tan(cam.FoVy*.5),bg=torch.zeros(3,device=g.get_xyz.device),
        scale_modifier=1.,viewmatrix=cam.world_view_transform.detach(),projmatrix=cam.full_proj_transform.detach(),
        sh_degree=0,campos=cam.camera_center.detach(),prefiltered=False,debug=False)
    colour=feature[:,None].expand(-1,3).contiguous()
    rgb,radii,allmap=GaussianRasterizer(raster_settings=settings)(
        means3D=g.get_xyz.detach(),means2D=torch.zeros_like(g.get_xyz,requires_grad=False),
        shs=None,colors_precomp=colour,opacities=g.get_opacity if opacity is None else opacity,
        scales=g.get_scaling.detach(),rotations=g.get_rotation.detach(),cov3D_precomp=None)
    return rgb.mean(0),allmap


class XYScope:
    def __init__(self,folder):
        import open3d as o3d
        self.o3d=o3d;folder=Path(folder)
        self.meta=json.loads((folder/'support.json').read_text())
        assert self.meta['scope_buffer_m']==1.
        with np.load(folder/'prior.npz') as z:v=z['vertices'].copy();faces=z['faces']
        v[:,2]=0;tri=v[faces]
        area=np.abs(np.cross(tri[:,1,:2]-tri[:,0,:2],tri[:,2,:2]-tri[:,0,:2]))
        self.scene=o3d.t.geometry.RaycastingScene(nthreads=4)
        self.scene.add_triangles(o3d.core.Tensor(v.astype(np.float32)),o3d.core.Tensor(faces[area>1e-10].astype(np.uint32)))

    def __call__(self,xyz):
        # Exact previous scope, evaluated at this iteration's current centres.
        q=xyz.detach().cpu().numpy().copy();q[:,2]=0
        d=self.scene.compute_distance(self.o3d.core.Tensor(q.astype(np.float32)),nthreads=4).numpy()
        return torch.as_tensor(d<=1.,device=xyz.device)


class Control:
    def __init__(self,folder,weight):
        assert math.isfinite(weight) and weight>0
        self.scope=XYScope(folder);self.weight=weight;self.last={};self.deleted=0

    def loss(self,j,cam,g,median,iteration):
        if not 500<=iteration<=30000:return None
        sources,_=sources_for(j,cam)
        G,margins,_=source_gate(median.detach().squeeze(0),sources)
        f=centre_flags(cam,g,sources,margins,self.scope(g.get_xyz))
        F,_=feature_render(cam,g,f)
        free=(G*F).mean()
        self.last=dict(L_free=float(free.detach()),G_gt_half_fraction=float((G>.5).float().mean()))
        return self.weight*free


def add_loss(total,control,j,cam,g,median,iteration):
    if control is None:return total  # exact identity, no arithmetic or RNG call
    extra=control.loss(j,cam,g,median,iteration)
    return total if extra is None else total+extra
