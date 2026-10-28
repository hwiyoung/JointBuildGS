"""Frozen checkpoints: exact training depth functions and centre gradients, no step."""
import argparse
import json
import math
import sys
from types import SimpleNamespace
import numpy as np
import torch
import cv2
sys.path.insert(0,'/source')
import jbgs_judgment as JJ
from utils.loss_utils import l1_loss,ssim
from common import *
from render_gpu import load,matrices
from recount import load_eval,classes

def read_map(site,prior,name,key,shape):
    root=S0/'fork_inputs/s61'/site/'maps'/key
    if (root/'raw_depth').exists():root=root/'raw_depth'
    p=root/(name+'.npy')
    dtype=np.int32 if key.startswith('locmap_') else np.float32
    loaded=JJ._load_set(root,[name],shape,'cuda',dtype=dtype)
    assert name in loaded,p
    return loaded[name],p

def dynamic_peak(s,v,lam=.0025):
    loga=torch.log(v)-torch.log1p(-v)-torch.log(s)-math.log(.1*math.sqrt(2*math.pi))
    lo=torch.ones_like(s);hi=torch.maximum(2*loga+30,torch.full_like(s,30.))
    for _ in range(32):
        mid=(lo+hi)/2;q=mid*torch.sigmoid(.5*mid-loga)
        lo=torch.where(q<1,mid,lo);hi=torch.where(q>=1,mid,hi)
    t=torch.sqrt((lo+hi)/2);w=torch.sigmoid(loga-.5*t*t)
    return lam*w*t/s

def terms(D,j,mode):
    name=next(iter(j.P));P,M,A=j.P[name],j.M[name],j.A[name]
    if mode=='current':
        mv=JJ.weighted_l1(D.squeeze(0),M,A,D.numel())[0]
        pr=JJ.truncated_prior_loss(D.squeeze(0),P,j.TAU[name],torch.ones_like(P),4.,D.numel())[0]
        return .05*mv,.05*pr
    mv,pr,_=JJ.lt_losses(j,name,{'surf_depth':D})
    return .0025*mv,.0025*pr

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--site',required=True);ap.add_argument('--result',required=True);ap.add_argument('--prior',default='ALS');a=ap.parse_args()
    cfg=config();quality=OUT/'renders'/a.site/a.result/'iteration_30000/quality.json'
    q=json.loads(quality.read_text());assert all(x['status']=='PASS' for x in q['checks']),'PSNR gate required'
    pipe,g,scene,model=load(a.site,a.prior,a.result,30000)
    meta=json.loads((model/'monitor/meta.json').read_text())
    assert meta['switches']['judgment'] is False and meta['r6']['depth_norm']=='pixels'
    expected_lambda=.05 if a.result.startswith('nojudge') else .0025
    assert meta['lambda_mvs']==meta['lambda_prior']==expected_lambda and meta['trunc_hi']==4.
    assert meta['switches']['prior_band'] and meta['switches']['confidence_mask']
    assert not any(meta['ablations'].values())
    if a.result.startswith('nojudge'):
        assert meta['revision']=='r14' and 'fixes' not in meta
    else:assert not any(meta['fixes'].values())
    e,root=load_eval(a.site,a.prior)
    with np.load(root/'values.npz') as f:v={k:f[k] for k in f.files}
    with np.load(LT/'patch_z'/f'{a.site}__{a.prior}__{a.result}.npz') as f:pred={k:f[k] for k in f.files}
    cat=classes(e,pred);valid=e['in_eval']&e['scoring_allowed']&(e['cell']>=0)&(e['cell']<=3)
    patch_type=np.full(len(cat),-1,np.int8);patch_type[valid&(cat==1)]=0;patch_type[valid&(cat==0)]=1
    type_t=torch.tensor(patch_type,device='cuda')
    vpkey='v_prior_gt' if a.result.startswith('lt_dyngt') else 'v_prior_now'
    vp=v[vpkey].copy();vp[v['outside_uncert'].astype(bool)]=v['v_prior_now'][v['outside_uncert'].astype(bool)]
    tab={k:torch.as_tensor(v[k],device='cuda') for k in ['sigma_prior','sigma_mvs','v_mvs','normal','fallback']}
    tab['v_prior']=torch.as_tensor(vp,device='cuda')
    bg=torch.zeros(3,device='cuda');centre_sums={k:torch.zeros(len(g.get_xyz),device='cuda',dtype=torch.float64) for k in ['photo','depth']}
    dest=OUT/'diagnostics'/a.site/a.result;dest.mkdir(parents=True,exist_ok=False)
    pixelrows=[];gate_counts=dict(floating_pixels=0,all_own_dead=0,unmapped_or_no_prior=0)
    for i,cam in enumerate(scene.getTrainCameras()):
        name=cam.image_name;shape=(cam.image_height,cam.image_width);maps={}
        for key,folder in [('P',f'prior_{a.prior}'),('M','mvs'),('A','conf'),('TAU',f'tau_{a.prior}'),('loc',f'locmap_{a.prior}')]:
            maps[key],_=read_map(a.site,a.prior,name,folder,shape)
        maps['loc']=maps['loc'].long();P,M,A=maps['P'],maps['M'],maps['A'];loc=maps['loc']
        j=SimpleNamespace(P={name:P},M={name:M},A={name:A},TAU={name:maps['TAU']},lt_locations={name:loc},
            lt_values=tab,lt_cameras={name:cam},args=SimpleNamespace(jbgs_sw_depth_loss='dynamic'))
        pkg=__import__('gaussian_renderer').render(cam,g,pipe,bg)
        mode='current' if a.result.startswith('nojudge') else 'dynamic'
        m,p=terms(pkg['surf_depth'],j,mode)
        photo=(1-.2)*l1_loss(pkg['render'],cam.original_image[:3].cuda())+.2*(1-ssim(pkg['render'],cam.original_image[:3].cuda()))
        for key,loss in [('photo',photo),('depth',m+p)]:
            grad=None
            if loss.requires_grad:
                grad,=torch.autograd.grad(loss,g._xyz,retain_graph=key=='photo',allow_unused=True)
                if grad is not None:
                    norm=grad.detach().norm(dim=1);assert torch.isfinite(norm).all()
                    centre_sums[key]+=norm.double()
            del grad
        D=pkg['surf_depth'].detach().clone().requires_grad_(True)
        forces={}
        for loss_mode in ['dynamic','current']:
            mv,pr=terms(D,j,loss_mode)
            for term,loss in [('prior',pr),('mvs',mv)]:
                grad=torch.autograd.grad(loss,D,retain_graph=True,allow_unused=True)[0] if loss.requires_grad else None
                forces[(loss_mode,term)]=torch.zeros_like(D[0]) if grad is None else grad.detach()[0].abs()*D.numel()
        eligible=(loc>=0)&(loc<len(vp))&torch.isfinite(P)&(P>0)
        yy,xx=torch.where(eligible);ids=loc[eligible]
        proj=cam.projection_matrix.T;H,W=shape
        ray=torch.stack(((xx-(proj[0,2]*W/2+(W-1)/2))/(proj[0,0]*W/2),
            (yy-(proj[1,2]*H/2+(H-1)/2))/(proj[1,1]*H/2),torch.ones_like(xx,dtype=D.dtype)),1)
        ray=torch.nn.functional.normalize(ray@cam.world_view_transform.inverse()[:3,:3],dim=1)
        cos=(ray*tab['normal'][ids].to(D.dtype)).sum(1).abs().clamp_min(.25)
        sp=tab['sigma_prior'][ids]/cos;sm=tab['sigma_mvs'][ids]/cos
        prior_ratio=(D.detach()[0][eligible]-P[eligible])/sp
        mvs_ratio=(D.detach()[0][eligible]-M[eligible])/sm
        obs=torch.isfinite(M[eligible])&(M[eligible]>0)&(A[eligible]>0)&torch.isfinite(tab['v_mvs'][ids])
        peakp=dynamic_peak(sp,tab['v_prior'][ids]);peakm=torch.zeros_like(sp)
        peakm[obs]=dynamic_peak(sm[obs],tab['v_mvs'][ids][obs])
        dead={}
        for lm in ['dynamic','current']:
            dead[(lm,'prior')]=(forces[(lm,'prior')][eligible]<.01*peakp) if lm=='dynamic' else (forces[(lm,'prior')][eligible]==0)
            # Constant L1 is defined as force-active at every mask-valid pixel,
            # including exact-zero residual where autograd chooses subgradient 0.
            dead[(lm,'mvs')]=(forces[(lm,'mvs')][eligible]<.01*peakm) if lm=='dynamic' else ~obs
        floatpix=type_t[ids]==0
        gate_counts['floating_pixels']+=int(floatpix.sum())
        gate_counts['all_own_dead']+=int((floatpix&dead[(mode,'prior')]&(~obs|dead[(mode,'mvs')])).sum())
        arrays=dict(patch_id=ids.cpu().numpy().astype(np.int32),pixel_y=yy.cpu().numpy(),pixel_x=xx.cpu().numpy(),
            pixel_type=type_t[ids].cpu().numpy(),has_mvs=obs.cpu().numpy(),prior_r_sigma=prior_ratio.cpu().numpy(),mvs_r_sigma=mvs_ratio.cpu().numpy(),
            sigma_prior=sp.cpu().numpy(),sigma_mvs=sm.cpu().numpy(),v_prior=tab['v_prior'][ids].cpu().numpy(),v_mvs=tab['v_mvs'][ids].cpu().numpy())
        for (lm,t),val in forces.items():arrays[lm+'_'+t+'_force']=val[eligible].cpu().numpy()
        for (lm,t),val in dead.items():arrays[lm+'_'+t+'_dead']=val.cpu().numpy()
        arrays['current_prior_inside_band']=(torch.abs(D.detach()[0][eligible]-P[eligible])<=maps['TAU'][eligible]).cpu().numpy()
        # Retain only evaluation cells 0..3 for complete exact quantiles; the
        # loss and centre gradients above used every original training pixel.
        keep=arrays['pixel_type']>=0
        np.savez_compressed(dest/(name+'.npz'),**{k:x[keep] for k,x in arrays.items()})
        pixelrows.append(dict(view=name,eligible_prior_pixels=len(ids),evaluation_pixels=int(keep.sum()),
            floating_pixels=int(floatpix.sum()),photo_loss=float(photo.detach()),depth_loss=float((m+p).detach())))
        del pkg,D,photo,m,p,forces,maps,j,arrays
        if i%10==0:print(a.site,a.result,'gradient and forces',i+1,'/',len(scene.getTrainCameras()),flush=True)
    np.savez_compressed(dest/'centre_gradients.npz',**{k:x.cpu().numpy() for k,x in centre_sums.items()})
    gate_counts['all_own_dead_fraction']=gate_counts['all_own_dead']/gate_counts['floating_pixels'] if gate_counts['floating_pixels'] else None
    save(dest/'receipt.json',dict(at=now(),site=a.site,result=a.result,views=pixelrows,gate_counts=gate_counts,
        source_sha256=sha('/source/jbgs_judgment.py'),model_sha256=sha(model/'point_cloud/iteration_30000/point_cloud.ply'),
        loss_GT_geometry_used=False,optimizer_steps=0,lambda_dssim=.2,
        exact_functions=['lt_losses','weighted_l1','truncated_prior_loss'],
        current_prior_weight='GW=1 everywhere, exact _g_init branch when judgment is off',
        scientific_verdict=None))

if __name__=='__main__':main()
