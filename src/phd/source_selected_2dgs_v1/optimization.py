"""Bounded source-assembled 2DGS optimization with the stock gsplat library."""
from __future__ import annotations
import math
import numpy as np
import torch
from torch import nn
from torch.nn import functional as F


def normal_quaternions(normals):
    """Deterministic shortest-arc wxyz; includes the antipodal -Z case."""
    n=F.normalize(normals,dim=-1)
    if not bool(torch.isfinite(n).all()) or bool((normals.norm(dim=-1)<1e-8).any()):raise ValueError('Nonzero finite source normals required')
    q=torch.cat((1+n[:,2:3],-n[:,1:2],n[:,0:1],torch.zeros_like(n[:,0:1])),dim=1)
    anti=n[:,2]<-1+1e-7
    q[anti]=q.new_tensor([0.,1.,0.,0.])
    return F.normalize(q,dim=-1)


def quaternion_normals(quats):
    q=F.normalize(quats,dim=-1);w,x,y,z=q.unbind(-1)
    return torch.stack((2*(x*z+w*y),2*(y*z-w*x),1-2*(x*x+y*y)),dim=-1)


class SourceGaussians(nn.Module):
    def __init__(self,points,cfg,device='cuda'):
        super().__init__();self.cfg=cfg
        xyz=np.asarray(points['xyz'],np.float32);normal=np.asarray(points['normal'],np.float32)
        rgb=np.asarray(points['rgb'],np.float32);scale=np.asarray(points['scale'],np.float32).reshape(-1)
        mask=np.asarray(points['trainable_geometry'],bool)
        if (xyz.ndim!=2 or xyz.shape[1]!=3 or normal.shape!=xyz.shape or rgb.shape!=xyz.shape
                or len(scale)!=len(xyz) or mask.shape!=(len(xyz),) or not len(xyz)
                or not all(np.isfinite(x).all() for x in (xyz,normal,rgb,scale))
                or (scale<=0).any() or (rgb<0).any() or (rgb>1).any()):raise ValueError('Invalid frozen source points')
        self.means=nn.Parameter(torch.as_tensor(xyz.copy(),device=device))
        self.quats_raw=nn.Parameter(normal_quaternions(torch.as_tensor(normal.copy(),device=device)))
        self.log_scales=nn.Parameter(torch.as_tensor(np.log(scale)[:,None].repeat(2,axis=1),device=device))
        alpha=float(cfg.get('initial_opacity',.8))
        self.opacity_raw=nn.Parameter(torch.full((len(xyz),),math.log(alpha/(1-alpha)),device=device))
        color=torch.as_tensor(rgb,device=device).clamp(1e-4,1-1e-4)
        self.rgb_raw=nn.Parameter(torch.logit(color))
        self.register_buffer('geometry_mask',torch.as_tensor(mask,device=device))
        for name in ('means','quats_raw','log_scales','opacity_raw'):
            param=getattr(self,name);self.register_buffer('initial_'+name,param.detach().clone())
            param.register_hook(lambda grad,shape=param.shape:grad*self.geometry_mask.reshape((-1,)+(1,)*(len(shape)-1)))
        self.register_buffer('initial_rgb_raw',self.rgb_raw.detach().clone())

    @property
    def quats(self):return F.normalize(self.quats_raw,dim=-1)
    @property
    def scales(self):return torch.cat((self.log_scales.exp(),torch.full((len(self.means),1),1e-6,device=self.means.device)),dim=1)
    @property
    def opacities(self):return self.opacity_raw.sigmoid()
    @property
    def colors(self):return self.rgb_raw.sigmoid()

    def optimizer(self,cfg):
        rates=cfg.get('learning_rates',{})
        aliases=dict(means='xyz',quats_raw='rotation',log_scales='scale',opacity_raw='opacity',rgb_raw='color')
        return torch.optim.Adam([dict(params=[getattr(self,k)],lr=float(rates[v]),name=k) for k,v in aliases.items()],eps=1e-15)

    @torch.no_grad()
    def constrain(self):
        cfg=self.cfg;mask=self.geometry_mask
        d=self.means-self.initial_means;n=d.norm(dim=-1,keepdim=True)
        self.means.copy_(self.initial_means+d*(float(cfg.get('maximum_center_displacement_m',.25))/n.clamp_min(1e-12)).clamp(max=1))
        low=self.initial_log_scales+math.log(float(cfg.get('minimum_scale_ratio',.5)))
        high=self.initial_log_scales+math.log(float(cfg.get('maximum_scale_ratio',2.)))
        self.log_scales.copy_(torch.maximum(torch.minimum(self.log_scales,high),low))
        q=F.normalize(self.quats_raw,dim=-1);q0=self.initial_quats_raw
        sign=torch.where((q*q0).sum(-1,keepdim=True)<0,-1.,1.);q=q*sign
        angle=torch.acos((q*q0).sum(-1,keepdim=True).clamp(-1+1e-7,1-1e-7))
        bound=math.radians(float(cfg.get('maximum_rotation_degrees',10.)))/2
        # Normalized linear interpolation is conservative for the small bound.
        fraction=(bound/angle.clamp_min(1e-12)).clamp(max=1)
        self.quats_raw.copy_(F.normalize(q0+(q-q0)*fraction,dim=-1))
        self.opacity_raw.clamp_(math.log(.01/.99),math.log(.99/.01))
        self.rgb_raw.clamp_(-10,10)
        for key in ('means','quats_raw','log_scales','opacity_raw'):
            getattr(self,key)[~mask]=getattr(self,'initial_'+key)[~mask]

    @torch.no_grad()
    def invariants(self):
        result={key:bool(torch.equal(getattr(self,key)[~self.geometry_mask],getattr(self,'initial_'+key)[~self.geometry_mask])) for key in ('means','quats_raw','log_scales','opacity_raw')}
        result['maximum_center_displacement_m']=float((self.means-self.initial_means).norm(dim=-1).max())
        result['finite_parameters']=all(bool(torch.isfinite(p).all()) for p in self.parameters())
        if not all(result[key] for key in ('means','quats_raw','log_scales','opacity_raw','finite_parameters')):raise ValueError('Protected geometry or finite-parameter invariant failed')
        if result['maximum_center_displacement_m']>float(self.cfg.get('maximum_center_displacement_m',.25))+3e-5:raise ValueError('Center motion bound exceeded')
        return result

    @torch.no_grad()
    def arrays(self,points):
        result=dict(xyz=self.means.cpu().numpy(),normal=quaternion_normals(self.quats).cpu().numpy(),
            quat_wxyz=self.quats.cpu().numpy(),scale_xy=self.scales[:,:2].cpu().numpy(),opacity=self.opacities.cpu().numpy(),
            rgb=self.colors.cpu().numpy(),initial_xyz=self.initial_means.cpu().numpy())
        for key in ('stable_source_id','source_kind','trainable_geometry'):result[key]=np.asarray(points[key])
        return result


def render(model,view,distloss=True):
    from gsplat import rasterization_2dgs
    device=model.means.device
    k=torch.as_tensor(view['K'],device=device,dtype=torch.float32).clone()
    # Source observations use integer image rays; stock gsplat samples x+.5/y+.5.
    k[0,2]+=.5;k[1,2]+=.5
    mat=torch.eye(4,device=device);mat[:3,:3]=torch.as_tensor(view['R'],device=device);mat[:3,3]=torch.as_tensor(view['t'],device=device)
    out=rasterization_2dgs(means=model.means,quats=model.quats,scales=model.scales,opacities=model.opacities,
        colors=model.colors,viewmats=mat[None],Ks=k[None],width=int(view['width']),height=int(view['height']),
        render_mode='RGB+ED',sh_degree=None,packed=False,near_plane=.01,far_plane=1e4,
        distloss=distloss,depth_mode='expected')
    return dict(rgb=out[0][0,:,:,:3],depth=out[0][0,:,:,3],alpha=out[1][0,:,:,0],
        normal=out[2][0],normal_from_depth=out[3],distortion=out[4][0,:,:,0],meta=out[-1])


def ssim_map(x,y):
    x=x.permute(2,0,1)[None];y=y.permute(2,0,1)[None]
    line=torch.arange(11,device=x.device,dtype=x.dtype)-5
    g=torch.exp(-line.square()/(2*1.5**2));g/=g.sum();kernel=(g[:,None]*g[None,:])[None,None].repeat(3,1,1,1)
    conv=lambda value:F.conv2d(value,kernel,padding=5,groups=3)
    mx,my=conv(x),conv(y);vx=conv(x*x)-mx*mx;vy=conv(y*y)-my*my;cov=conv(x*y)-mx*my
    s=((2*mx*my+.01**2)*(2*cov+.03**2))/((mx*mx+my*my+.01**2)*(vx+vy+.03**2)).clamp_min(1e-12)
    return s[0].mean(0)


def fixed_mean(value,mask):
    if bool(mask.any()):return value[mask].mean()
    return value.sum()*0


def stratified_mean(value,target,context,balance=.5):
    present_target=bool(target.any());present_context=bool(context.any())
    wt=float(balance) if present_target else 0.;wc=1-float(balance) if present_context else 0.
    if wt+wc==0:return value.sum()*0
    return (wt*fixed_mean(value,target)+wc*fixed_mean(value,context))/(wt+wc)


def objective(pred,photo,arrays,arm,cfg):
    device=pred['rgb'].device
    mask=lambda key:torch.as_tensor(arrays[key],device=device,dtype=torch.bool)
    pm=mask('photo_mask');authority=mask('authority_mask');target_window=mask('target_mask')
    abstain=mask('projection_abstain_mask') if 'projection_abstain_mask' in arrays else torch.zeros_like(pm)
    target_key='prior_depth' if arm=='prior_only' else 'selected_depth'
    target=torch.as_tensor(arrays[target_key],device=device,dtype=torch.float32)
    valid=mask('depth_valid')&torch.isfinite(target)&(target>0)&~abstain
    target=torch.nan_to_num(target,nan=0,posinf=0,neginf=0)
    candidate=valid&authority;context=valid&~authority
    rgb_err=(pred['rgb']-photo).abs().mean(-1)
    balance=float(cfg['target_context_balance']);weights=cfg['loss_weights']
    photo_l1=stratified_mean(rgb_err,pm&target_window,pm&~target_window,balance)
    ssim=stratified_mean(1-ssim_map(pred['rgb'],photo),pm&target_window,pm&~target_window,balance)
    absolute_depth=(pred['depth']-target).abs();delta=float(cfg['depth_huber_delta_m'])
    depth_err=torch.where(absolute_depth<=delta,.5*absolute_depth.square()/delta,absolute_depth-.5*delta)
    candidate_depth=fixed_mean(depth_err,candidate);context_depth=fixed_mean(depth_err,context)
    coverage=F.relu(float(cfg.get('coverage_alpha_minimum',.5))-pred['alpha']).square()
    coverage_loss=stratified_mean(coverage,candidate,context,balance)
    n=F.normalize(pred['normal'],dim=-1);nd=F.normalize(pred['normal_from_depth'],dim=-1)
    normal_mask=pm&~abstain&(pred['alpha'].detach()>=.5)&torch.isfinite(nd).all(-1)&(nd.norm(dim=-1)>.1)
    normal=stratified_mean(1-(n*nd).sum(-1).abs().clamp(max=1),normal_mask&target_window,normal_mask&~target_window,balance)
    normal_key='prior_normal' if arm=='prior_only' else 'selected_normal'
    source_normal=torch.as_tensor(arrays[normal_key],device=device,dtype=torch.float32)
    source_normal_mask=mask('normal_valid')&~abstain&torch.isfinite(source_normal).all(-1)&(source_normal.norm(dim=-1)>.1)
    source_normal=torch.nan_to_num(source_normal,nan=0,posinf=0,neginf=0)
    source_normal_loss=stratified_mean(1-(n*F.normalize(source_normal,dim=-1)).sum(-1).abs().clamp(max=1),source_normal_mask&authority,source_normal_mask&~authority,balance)
    distortion=stratified_mean(pred['distortion'],pm&target_window,pm&~target_window,balance)
    lam=float(weights['ssim']);rgb=float(weights['rgb'])*((1-lam)*photo_l1+lam*ssim)
    depth_loss=stratified_mean(depth_err,candidate,context,balance)
    loss=rgb+float(weights['source_depth'])*depth_loss+float(weights['source_normal'])*source_normal_loss
    loss+=float(weights['coverage'])*coverage_loss+float(weights['normal_consistency'])*normal+float(weights['depth_distortion'])*distortion
    terms=dict(total=loss,photo_l1=photo_l1,photo_ssim_loss=ssim,candidate_depth_m=candidate_depth,
        context_depth_m=context_depth,source_depth_huber=depth_loss,
        candidate_depth_mae_m=fixed_mean(absolute_depth,candidate),context_depth_mae_m=fixed_mean(absolute_depth,context),
        coverage=coverage_loss,normal=normal,source_normal=source_normal_loss,distortion=distortion)
    counts=dict(photo_pixels=int(pm.sum()),candidate_depth_pixels=int(candidate.sum()),context_depth_pixels=int(context.sum()),normal_pixels=int(normal_mask.sum()),source_normal_pixels=int(source_normal_mask.sum()))
    if not all(bool(torch.isfinite(v)) for v in terms.values()):raise ValueError('Nonfinite training loss')
    return loss,terms,counts


def snapshot_cpu(pred):
    return {key:value.detach().cpu().numpy().copy() for key,value in pred.items() if key in ('rgb','depth','alpha','normal')}


def comparison_metrics(photo,before,after,masks):
    rows={};e0=np.abs(before['rgb']-photo).mean(-1);e1=np.abs(after['rgb']-photo).mean(-1)
    for domain,mask in masks.items():
        mask=np.asarray(mask,bool);count=int(mask.sum())
        if not count:rows[domain]=dict(pixels=0,status='NO_FIXED_SUPPORT');continue
        valid=mask&(before['alpha']>=.5)&(after['alpha']>=.5)&(before['depth']>0)&(after['depth']>0)
        mse0=float(np.mean((before['rgb'][mask]-photo[mask])**2));mse1=float(np.mean((after['rgb'][mask]-photo[mask])**2))
        rows[domain]=dict(pixels=count,photo_mae_before=float(e0[mask].mean()),photo_mae_after=float(e1[mask].mean()),
            photo_mae_delta=float((e1-e0)[mask].mean()),photo_rmse_before=math.sqrt(mse0),photo_rmse_after=math.sqrt(mse1),
            photo_psnr_before_db=-10*math.log10(mse0) if mse0 else None,photo_psnr_after_db=-10*math.log10(mse1) if mse1 else None,
            photo_worsened_gt_1_255=int((mask&((e1-e0)>1/255)).sum()),photo_improved_gt_1_255=int((mask&((e1-e0)<-1/255)).sum()),
            paired_depth_pixels=int(valid.sum()),depth_abs_change_mean_m=float(np.abs(after['depth'][valid]-before['depth'][valid]).mean()) if valid.any() else None,
            depth_abs_change_max_m=float(np.abs(after['depth'][valid]-before['depth'][valid]).max()) if valid.any() else None,
            coverage_lost=int((mask&(before['alpha']>=.5)&(after['alpha']<.5)).sum()),coverage_gained=int((mask&(before['alpha']<.5)&(after['alpha']>=.5)).sum()))
    return rows
