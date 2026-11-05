"""Read-only add4 milestone renders. Reference geometry is diagnostic only."""
import json
import random
from pathlib import Path
import numpy as np
import torch
from PIL import Image


def measure(depth, loc, prior, K, E, evaluation, bbox):
    e=evaluation
    eligible=(loc>=0)&(loc<len(e['centre']))&np.isfinite(prior)&(prior>0)
    y,x=np.where(eligible);pi=loc[eligible].astype(np.int64);dv=depth[y,x]
    rays=np.stack([(x-K[0,2])/K[0,0],(y-K[1,2])/K[1,1],np.ones(len(x))],1).astype(np.float32)
    inv=np.linalg.inv(E);world=(rays*dv[:,None])@inv[:3,:3].T+inv[:3,3]
    n=e['normal'][pi];gt=e['centre'][pi]+e['p_gt'][pi,None]*n
    with np.errstate(divide='ignore',invalid='ignore'):
        gtz=gt[:,2]-np.sum((world[:,:2]-gt[:,:2])*n[:,:2],axis=1)/n[:,2]
    delta=world[:,2]-gtz
    valid=np.isfinite(delta)&(dv>0)&(np.abs(n[:,2])>1e-6)&e['in_eval'][pi]&e['scoring_allowed'][pi]&(e['cell'][pi]>=0)&(e['cell'][pi]<=3)
    b=np.asarray(bbox);xy=e['centre'][pi,:2];region=((xy>=b[:2]-3)&(xy<=b[2:]+3)).all(1)
    m=valid&region;floating=m&(delta>e['tau'][pi]);roof=m&(np.abs(delta)<=e['tau'][pi]);count=int(m.sum())
    row=dict(pixels=count,floating_pixels=int(floating.sum()),floating_fraction=float(floating.sum()/count) if count else None,roof_pixels=int(roof.sum()))
    if not region.any():return row,None,None
    yy,xx=y[region],x[region];crop=[max(0,int(xx.min())-12),max(0,int(yy.min())-12),min(depth.shape[1],int(xx.max())+13),min(depth.shape[0],int(yy.max())+13)]
    # Fixed GT-derived range for this camera and case; same at every iteration.
    z=(gt[region]@E[:3,:3].T+E[:3,3])[:,2]
    return row,crop,[float(np.min(z)-6),float(np.max(z)+6)]


def capture(control,gaussians,pipe,bg,iteration):
    from gaussian_renderer import render
    from matplotlib import colormaps
    site=control.binding['site'];selection=json.loads((control.root/'early_views.json').read_text())
    with np.load(Path('/ph/main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/direct_stage1_v2')/(site+'__ALS')/'evaluation.npz') as z:e={k:z[k] for k in z.files}
    dest=control.out/'mv_early'/f'iteration_{iteration}';dest.mkdir(parents=True,exist_ok=False)
    state=(random.getstate(),np.random.get_state(),torch.get_rng_state(),torch.cuda.get_rng_state_all())
    rows=[]
    try:
        with torch.no_grad():
            for name in sorted({r['view'] for r in selection['rows'] if r['view']}):
                cam=control.cameras[name];pkg=render(cam,gaussians,pipe,bg)
                depth=pkg['surf_depth'][0].cpu().numpy();rgb=(pkg['render'].clamp(0,1).permute(1,2,0).cpu().numpy()*255).astype(np.uint8)
                K,_,_=control.calibration(cam);K=K.cpu().numpy();E=cam.world_view_transform.T.cpu().numpy()
                loc=control.j.lt_locations[name].cpu().numpy();prior=control.j.P[name].cpu().numpy()
                np.savez_compressed(dest/(name+'.npz'),depth=depth,world_to_camera=E,intrinsic=K)
                for r in [r for r in selection['rows'] if r['view']==name]:
                    row,crop,limits=measure(depth,loc,prior,K,E,e,r['bbox']);row.update(r,iteration=iteration,scientific_verdict=None)
                    if crop:
                        stem=r['case']+'_'+r['role'];x0,y0,x1,y1=crop
                        color=Image.fromarray(rgb[y0:y1,x0:x1]);color.thumbnail((1000,800));color.save(dest/(stem+'_color.png'))
                        d=depth[y0:y1,x0:x1];scaled=np.clip((d-limits[0])/(limits[1]-limits[0]),0,1)
                        heat=(colormaps['viridis'](scaled)[...,:3]*255).astype(np.uint8);heat[~np.isfinite(d)|(d<=0)]=0
                        im=Image.fromarray(heat);im.thumbnail((1000,800));im.save(dest/(stem+'_depth.png'))
                        row.update(crop_xyxy=crop,depth_color_range_m=limits,depth_colormap='viridis; camera depth',color=stem+'_color.png',depth=stem+'_depth.png')
                    rows.append(row)
                del pkg
        (dest/'receipt.json').write_text(json.dumps(dict(status='PASS',iteration=iteration,rows=rows,definition='formation_gpu.py early_formation: world vertical delta to local GT plane, cells 0..3, bbox +/-3m, same valid denominator',optimizer_steps=0,scientific_verdict=None),ensure_ascii=False,indent=2)+'\n')
    finally:
        random.setstate(state[0]);np.random.set_state(state[1]);torch.set_rng_state(state[2]);torch.cuda.set_rng_state_all(state[3])
