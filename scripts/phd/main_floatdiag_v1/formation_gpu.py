"""Saved-iteration main-view depth and exact per-pixel forces, without updating."""
import argparse
import json
import sys
from types import SimpleNamespace
import numpy as np
import torch
from PIL import Image
from common import *
import render_gpu as R
from diagnose_gpu import read_map,terms,dynamic_peak
from recount import load_eval

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--site',required=True);ap.add_argument('--prior',default='ALS')
    ap.add_argument('--result',required=True);ap.add_argument('--iterations',type=int,nargs='+',default=[15000]);a=ap.parse_args()
    if a.result.startswith('fd_'):
        R.model_path=lambda s,r:OUT/'runs'/s/r/'model'
        assert a.site=='R1rep_b10'
    choices=json.loads((CFG/f'photos_{a.site}_{a.prior}.json').read_text())['cases']
    cases=[c for c in json.loads((CFG/f'cases_{a.prior}.json').read_text())['cases'] if c['site']==a.site]
    if a.result.startswith('fd_'):
        cases=[c for c in cases if c['id'] in ['R1-뜬면-1','R1-뜬면-2']]
        choices=[c for c in choices if c['case'] in [x['id'] for x in cases]]
    names=sorted({c['main']['view'] for c in choices if c['main']})
    e,root=load_eval(a.site,a.prior)
    with np.load(root/'values.npz') as f:v={k:f[k] for k in f.files}
    vp=v['v_prior_gt' if 'dyngt' in a.result else 'v_prior_now'].copy()
    vp[v['outside_uncert'].astype(bool)]=v['v_prior_now'][v['outside_uncert'].astype(bool)]
    tab={k:torch.as_tensor(v[k],device='cuda') for k in ['sigma_prior','sigma_mvs','v_mvs','normal','fallback']}
    tab['v_prior']=torch.as_tensor(vp,device='cuda')
    mode='current' if a.result.startswith(('nojudge','fd_current')) else 'dynamic'
    allrows=[]
    for iteration in a.iterations:
        pipe,g,scene,model=R.load(a.site,a.prior,a.result,iteration)
        dest=OUT/'formation'/a.site/a.result/f'iteration_{iteration}';dest.mkdir(parents=True,exist_ok=False)
        cams={c.image_name:c for c in scene.getTrainCameras()};rows=[]
        for name in names:
            cam=cams[name];shape=(cam.image_height,cam.image_width);maps={}
            for key,folder in [('P',f'prior_{a.prior}'),('M','mvs'),('A','conf'),('TAU',f'tau_{a.prior}'),('loc',f'locmap_{a.prior}')]:
                maps[key],_=read_map(a.site,a.prior,name,folder,shape)
            loc=maps['loc'].long();P,M,A=maps['P'],maps['M'],maps['A']
            j=SimpleNamespace(P={name:P},M={name:M},A={name:A},TAU={name:maps['TAU']},lt_locations={name:loc},
                lt_values=tab,lt_cameras={name:cam},args=SimpleNamespace(jbgs_sw_depth_loss='dynamic'))
            with torch.no_grad():pkg=R.render(cam,g,pipe,torch.zeros(3,device='cuda'))
            D=pkg['surf_depth'].detach().clone().requires_grad_(True)
            force={}
            for lm in ['current','dynamic']:
                mv,pr=terms(D,j,lm)
                for term,loss in [('prior',pr),('mvs',mv)]:
                    grad=torch.autograd.grad(loss,D,retain_graph=True,allow_unused=True)[0] if loss.requires_grad else None
                    force[lm+'_'+term]=torch.zeros_like(D[0]) if grad is None else grad.detach()[0].abs()*D.numel()
            eligible=(loc>=0)&(loc<len(vp))&torch.isfinite(P)&(P>0)
            y,x=torch.where(eligible);ids=loc[eligible];ext,K=R.matrices(cam)
            ray=torch.stack(((x-K[0,2])/K[0,0],(y-K[1,2])/K[1,1],torch.ones_like(x)),1).float()
            normray=torch.nn.functional.normalize(ray@cam.world_view_transform.inverse()[:3,:3],dim=1)
            cos=(normray*tab['normal'][ids].to(D.dtype)).sum(1).abs().clamp_min(.25)
            sp=tab['sigma_prior'][ids]/cos;sm=tab['sigma_mvs'][ids]/cos
            obs=torch.isfinite(M[eligible])&(M[eligible]>0)&(A[eligible]>0)&torch.isfinite(tab['v_mvs'][ids])
            arrays=dict(patch_id=ids.cpu().numpy().astype(np.int32),pixel_y=y.cpu().numpy(),pixel_x=x.cpu().numpy(),
                prior_r_sigma=((D.detach()[0][eligible]-P[eligible])/sp).cpu().numpy(),
                mvs_r_sigma=((D.detach()[0][eligible]-M[eligible])/sm).cpu().numpy(),has_mvs=obs.cpu().numpy())
            for key,val in force.items():arrays[key+'_force']=val[eligible].cpu().numpy()
            arrays['dynamic_prior_dead']=(force['dynamic_prior'][eligible]<.01*dynamic_peak(sp,tab['v_prior'][ids])).cpu().numpy()
            peakm=torch.zeros_like(sm);peakm[obs]=dynamic_peak(sm[obs],tab['v_mvs'][ids][obs])
            arrays['dynamic_mvs_dead']=(force['dynamic_mvs'][eligible]<.01*peakm).cpu().numpy()
            arrays['current_prior_dead']=(force['current_prior'][eligible]==0).cpu().numpy();arrays['current_mvs_dead']=(~obs).cpu().numpy()
            depth=D.detach()[0].cpu().numpy();inv=np.linalg.inv(ext);pi=arrays['patch_id'];dv=depth[arrays['pixel_y'],arrays['pixel_x']]
            world=(ray.cpu().numpy()*dv[:,None])@inv[:3,:3].T+inv[:3,3]
            n=e['normal'][pi];gt=e['centre'][pi]+e['p_gt'][pi,None]*n
            # Local tangent-plane height at each reconstructed XY, not camera Z.
            gtz=gt[:,2]-np.sum((world[:,:2]-gt[:,:2])*n[:,:2],axis=1)/n[:,2]
            delta=world[:,2]-gtz;valid=np.isfinite(delta)&(dv>0)&(np.abs(n[:,2])>1e-6)&e['in_eval'][pi]&e['scoring_allowed'][pi]&(e['cell'][pi]>=0)&(e['cell'][pi]<=3)
            arrays.update(world=world,gt_world_z=gtz,vertical_delta_m=delta,early_floating=valid&(delta>e['tau'][pi]),
                early_roof=valid&(np.abs(delta)<=e['tau'][pi]),valid=valid)
            np.savez_compressed(dest/(name+'.npz'),depth=depth,alpha=pkg['rend_alpha'][0].cpu().numpy(),
                world_to_camera=ext,intrinsic=K,**arrays)
            Image.fromarray((pkg['render'].clamp(0,1).permute(1,2,0).cpu().numpy()*255).astype(np.uint8)).save(dest/(name+'.png'))
            for c in cases:
                choice=next(x for x in choices if x['case']==c['id'])
                if choice['main'] is None or choice['main']['view']!=name:continue
                b=np.array(c['bbox']);xy=e['centre'][pi,:2];m=valid&((xy>=b[:2]-3)&(xy<=b[2:]+3)).all(1)
                f=m&arrays['early_floating'];roof=m&arrays['early_roof'];npx=int(m.sum())
                row=dict(site=a.site,result=a.result,iteration=iteration,case=c['id'],view=name,pixels=npx,
                    floating_pixels=int(f.sum()),floating_fraction=float(f.sum()/npx) if npx else None,
                    roof_pixels=int(roof.sum()),source=str(dest/(name+'.npz')),scientific_verdict=None)
                for label,mask in [('floating',f),('roof',roof)]:
                    for term in ['prior','mvs']:
                        take=mask if term=='prior' else mask&arrays['has_mvs']
                        rs=arrays[term+'_r_sigma'][take]
                        row[label+'_'+term+'_r_sigma_q25_q50_q75_q90']=np.quantile(rs,[.25,.5,.75,.9]).tolist() if len(rs) else None
                    for lm in ['current','dynamic']:
                        dead=arrays[lm+'_prior_dead']&(~arrays['has_mvs']|arrays[lm+'_mvs_dead'])
                        row[label+'_'+lm+'_all_dead_fraction']=float(dead[mask].mean()) if mask.any() else None
                rows.append(row)
            del pkg,D,force,maps,j
        save(dest/'receipt.json',dict(at=now(),site=a.site,result=a.result,iteration=iteration,rows=rows,
            model=str(model),model_sha256=sha(model/f'point_cloud/iteration_{iteration}/point_cloud.ply'),
            unavailable_cases=[x['case'] for x in choices if x['main'] is None],optimizer_steps=0,scientific_verdict=None))
        allrows+=rows;del g,scene;torch.cuda.empty_cache()
        print(a.site,a.result,iteration,'formation main-view renders PASS',flush=True)

if __name__=='__main__':main()
