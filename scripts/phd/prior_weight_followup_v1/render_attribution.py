"""Frozen GeoGS checkpoint attribution, full-scene occlusion, no optimization.

Replays the historical renderer for exact-result diagnosis; this is not a new
training implementation. Group membership is a center-based diagnostic proxy.
"""
import gc
import hashlib
import json
import math
import sys
import time
import traceback
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
from PIL import Image
import torch
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

P = Path('/payload'); O = Path('/out')
cfg = json.loads((O/'config.json').read_text())
source = P/cfg['bundle']/'P1/source'
sys.path.insert(0, str(source))
sys.path.insert(0, '/repo/src/phd/geogs_mvs_pgsr_v1')
from scene.gaussian_model import GaussianModel
from scene.cameras import Camera
from gaussian_renderer import render
from jbgs_camera_adapter import apply_projection
from mvs_depth import load_view_depth

inputs = {}
def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(8 << 20), b''): h.update(block)
    return h.hexdigest()
def record(path):
    path = Path(path); inputs[str(path)] = sha(path); return path
def stats(a):
    a = np.asarray(a, float)
    return dict(n=a.size, mean=float(a.mean()), median=float(np.median(a)), p95=float(np.quantile(a,.95))) if a.size else dict(n=0)
def u8(a): return (a.detach().clamp(0,1).permute(1,2,0).cpu().numpy()*255+.5).astype('uint8')

@torch.no_grad()
def main():
    assert Path('/.dockerenv').exists()
    started = time.time(); torch.set_num_threads(2)
    for name in ['gaussian_renderer/__init__.py','scene/gaussian_model.py','jbgs_camera_adapter.py']:
        record(source/name)
    native = (source/'scene/gaussian_model.py').read_text()
    assert 'prune_mask = torch.logical_and(prune_mask, ~self.frozen_mask)' in native
    assert native.count('selected_pts_mask = torch.logical_and(selected_pts_mask, ~self.frozen_mask)') == 2
    binding = json.loads(record(P/cfg['global']/'inputs_v2/P1/bindings.json').read_text())
    c = next(v for v in binding['train'] if v['name']==cfg['camera'])
    mvs, valid, _ = load_view_depth(c, verify_rgb=False, depth_path=record(P/cfg['global']/'inputs_v2/P1'/c['local_depth']))
    prior = cv2.resize(np.load(record(P/cfg['base']/('inputs/P1/prior/raw_depth/'+Path(c['name']).stem+'.npy'))), (c['width'],c['height']), interpolation=cv2.INTER_LINEAR)
    labels = np.load(record(P/cfg['bundle']/'P1/mask/r1_mask.npz'))['region_id']
    photo_path = Path('/artifacts')/Path(c['path']).relative_to('/artifacts/JointBuildGS')
    photo = np.asarray(Image.open(record(photo_path)).convert('RGB')); assert sha(photo_path)==c['sha256']
    R, t, K = np.asarray(c['R']), np.asarray(c['t']), np.asarray(c['K'])
    camera = Camera(colmap_id=c['camera_id'], R=R.T,T=t,FoVx=2*math.atan(c['width']/(2*K[0,0])),FoVy=2*math.atan(c['height']/(2*K[1,1])), image=torch.from_numpy(photo.copy()).permute(2,0,1).float()/255,gt_alpha_mask=None,image_name=Path(c['name']).stem,uid=0)
    apply_projection(camera,c)
    pipe = SimpleNamespace(compute_cov3D_python=False,convert_SHs_python=False,depth_ratio=0.)
    black = torch.zeros(3,device='cuda')
    roi = (labels==1)&valid&np.isfinite(prior)&(prior>0)&((mvs-prior)>cfg['minimum_prior_mvs_gap_m'])
    assert roi.any()
    yy,xx = np.where(labels==1); y0=max(0,int(yy.min())-75);y1=min(c['height'],int(yy.max())+76);x0=max(0,int(xx.min())-75);x1=min(c['width'],int(xx.max())+76); sl=np.s_[y0:y1,x0:x1]
    def classify(xyz):
        xc=xyz@R.T+t; uvh=xc@K.T; uv=np.rint(uvh[:,:2]/uvh[:,2:]).astype(int)
        inside=(xc[:,2]>0)&(uv[:,0]>=0)&(uv[:,0]<c['width'])&(uv[:,1]>=0)&(uv[:,1]<c['height'])
        xx=np.clip(uv[:,0],0,c['width']-1);yy=np.clip(uv[:,1],0,c['height']-1)
        allowed=inside&roi[yy,xx]
        return allowed, xc[:,2]-prior[yy,xx], xc[:,2]-mvs[yy,xx]
    rows=[]; images=[]; cohort=None; anchor_protected=None
    for case in cfg['states']:
        root=P/case['path']; receipt=json.loads(record(root/'receipt.json').read_text())
        checkpoint=record(root/'checkpoint.pth'); assert sha(checkpoint)==receipt['checkpoint_sha256']
        s=torch.load(str(checkpoint),map_location='cpu',weights_only=False,mmap=True)
        assert not s['hook_state']['release']
        protected=s['frozen_mask'].bool().numpy(); xyz=s['model'][1].detach().numpy(); allowed,dp,dm=classify(xyz)
        if cohort is None:
            anchor_protected=xyz[protected].copy()
            cohort=(allowed&(np.abs(dp)<=cfg['anchor_cohort_prior_tolerance_m']))[protected]
            assert cohort.any()
        assert int(protected.sum())==len(cohort)
        tracked=np.zeros(len(protected),bool);tracked[np.flatnonzero(protected)]=cohort
        old=allowed&(np.abs(dp)<=cfg['current_center_tolerance_m'])
        ground=allowed&(np.abs(dm)<=cfg['current_center_tolerance_m'])
        pc=GaussianModel(3); pc.active_sh_degree=int(s['model'][0])
        for field,index in [('_xyz',1),('_features_dc',2),('_features_rest',3),('_scaling',4),('_rotation',5),('_opacity',6)]: setattr(pc,field,s['model'][index].detach().cuda())
        bg=torch.full((3,),float(s['args']['white_background']),device='cuda')
        original=render(camera,pc,pipe,bg); alpha=original['rend_alpha'].squeeze().cpu().numpy(); depth=original['surf_depth'].squeeze().cpu().numpy(); rgb=u8(original['render'])
        parity=None
        if case.get('saved_depth'):
            saved=np.asarray(Image.open(record(P/case['saved_depth'])),dtype=np.float32)
            parity=float(np.max(np.abs(depth-saved))); assert parity<1e-4, parity
        flags=torch.from_numpy(np.stack([tracked,ground,old],1).astype('float32')).cuda()
        tagged=render(camera,pc,pipe,black,override_color=flags)
        assert float((tagged['rend_alpha']-original['rend_alpha']).abs().max())<1e-6
        mass=tagged['render'].cpu().numpy(); assert (mass>=-1e-6).all() and (mass<=alpha[None]+2e-5).all()
        flags2=torch.from_numpy(np.stack([protected,~protected,np.ones(len(protected),bool)],1).astype('float32')).cuda()
        lineage=render(camera,pc,pipe,black,override_color=flags2)['render'].cpu().numpy()
        partition_error=float(np.max(np.abs(lineage[:2].sum(0)-alpha))); assert partition_error<2e-5
        assert np.max(np.abs(lineage[2]-alpha))<2e-5
        supported=roi&(alpha>.95); denom=float(alpha[roi].sum())
        share=lambda a:float(a[roi].sum()/denom)
        distance=np.linalg.norm(xyz[protected][cohort]-anchor_protected[cohort],axis=1)
        row=dict(id=case['id'],label=case['label'],iteration=s['iteration'],gaussians=len(protected),tracked_count=int(tracked.sum()),protected_count=int(protected.sum()),roi_pixels=int(roi.sum()),alpha_mean=float(alpha[roi].mean()),alpha_ge_095_fraction=float(supported.sum()/roi.sum()),mvs_depth_abs_error=stats(np.abs(depth[roi]-mvs[roi])),tracked_displacement_m=stats(distance),tracked_opacity=stats(pc.get_opacity.detach().cpu().numpy()[tracked]),contribution_fraction=dict(tracked_old_roof=share(mass[0]),mvs_near_centers=share(mass[1]),prior_near_centers=share(mass[2]),all_protected=share(lineage[0]),all_unprotected=share(lineage[1])),saved_depth_max_abs_delta=parity,partition_max_abs_error=partition_error)
        if case['id']=='regional_0005':
            before=pc._opacity.clone(); mask=torch.from_numpy(tracked).cuda()
            pc._opacity[mask]=-torch.inf
            erased=render(camera,pc,pipe,bg)
            pc._opacity.copy_(before)
            restored=render(camera,pc,pipe,bg)
            assert float((restored['render']-original['render']).abs().max())<1e-6
            ed=erased['surf_depth'].squeeze().cpu().numpy(); ea=erased['rend_alpha'].squeeze().cpu().numpy()
            row['counterfactual_tracked_opacity_zero']=dict(depth_change_m=stats(np.abs(ed[roi]-depth[roi])),alpha_change=stats(np.abs(ea[roi]-alpha[roi])),mvs_depth_abs_error=stats(np.abs(ed[roi]-mvs[roi])),restored=True)
            del erased,restored,before,mask
        np.savez_compressed(O/(case['id']+'.npz'),alpha=alpha,depth=depth,group_contribution=mass,protected_contribution=lineage[0],roi=roi,labels=labels,group_names=np.array(['tracked_old_roof','mvs_near_centers','prior_near_centers']))
        fraction=mass/np.maximum(alpha[None],1e-8)
        images.append((case,rgb[sl],fraction[:,y0:y1,x0:x1]))
        rows.append(row);print(json.dumps(row),flush=True)
        del s,pc,original,tagged,flags,flags2;gc.collect();torch.cuda.empty_cache()
    fig,axes=plt.subplots(1,3,figsize=(13,5),constrained_layout=True)
    axes[0].imshow(photo[sl]);axes[0].contour(roi[sl],levels=[.5],colors=['red'],linewidths=.7);axes[0].set_title('0100_D / diagnostic ROI (red)')
    a=axes[1].imshow(np.where(roi,prior,np.nan)[sl],cmap='viridis');fig.colorbar(a,ax=axes[1],label='Prior camera-Z (m)');axes[1].set_title('Prior depth in diagnostic ROI')
    a=axes[2].imshow(np.where(roi,mvs-prior,np.nan)[sl],cmap='magma',vmin=0,vmax=12);fig.colorbar(a,ax=axes[2],label='MVS - prior (m)');axes[2].set_title('Gap; this is not confidence')
    for ax in axes:ax.axis('off')
    fig.savefig(O/'inputs.png',dpi=130);plt.close(fig)
    fig,axes=plt.subplots(4,4,figsize=(16,16),constrained_layout=True)
    for k,(case,rgb,frac) in enumerate(images):
        axes[k,0].imshow(rgb);axes[k,0].set_title(case['label'],fontsize=11)
        for j,title in enumerate(['Tracked old-roof cohort','Centers near current MVS','Centers near old prior']):
            a=axes[k,j+1].imshow(frac[j],vmin=0,vmax=1,cmap='magma');axes[k,j+1].set_title(title,fontsize=10)
        for ax in axes[k]:ax.contour(roi[sl],levels=[.5],colors=['cyan'],linewidths=.5);ax.axis('off')
    fig.colorbar(a,ax=axes[:,1:].ravel().tolist(),shrink=.5,label='Group share of accumulated alpha (0-1)')
    fig.savefig(O/'attribution.png',dpi=130);plt.close(fig)
    result=dict(status='PASS_FORWARD_ATTRIBUTION',scientific_verdict=None,reference_accessed=False,training_performed=False,scope='P1 0100_D; center-defined groups, unchanged full-scene occlusion; no complete birth/death history',config_sha256=sha(O/'config.json'),script_sha256=sha(__file__),runtime=cfg['runtime'],python=sys.version,torch=torch.__version__,numpy=np.__version__,inputs=inputs,rows=rows,wall_seconds=time.time()-started)
    (O/'result.json').write_text(json.dumps(result,indent=2))

if __name__=='__main__':
    try: main()
    except Exception:
        (O/'failure.txt').write_text(traceback.format_exc());raise
