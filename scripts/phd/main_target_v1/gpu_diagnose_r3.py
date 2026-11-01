"""Diagnose prior-only depth discrepancy without changing the locked gate or training."""
import sys
sys.path.insert(0,'/source');sys.path.insert(0,'/repo')
from argparse import ArgumentParser
import numpy as np
import torch
from common import *
from arguments import ModelParams,PipelineParams
from scene import Scene,GaussianModel
from utils.graphics_utils import BasicPointCloud
from utils.general_utils import safe_state,build_rotation
from gaussian_renderer import render
from src.phd.prior_propagation_v6.orientation import quat_from_normal
import jbgs_target

def stats(a):
    a=np.asarray(a);a=a[np.isfinite(a)]
    return dict(count=len(a),quantiles=np.quantile(a,[0,.1,.5,.9,1]).tolist()) if len(a) else dict(count=0,quantiles=None)

@torch.no_grad()
def main():
    site,prior=sys.argv[1:3];cfg,lock=locked_r3()
    root=OUT/'r3/diagnose'/f'{site}_{prior}';root.mkdir(parents=True,exist_ok=False)
    parser=ArgumentParser();lp=ModelParams(parser);pp=PipelineParams(parser)
    args=parser.parse_args(['-s',str(S0/'fork_inputs/s61'/site/f'scene_{prior}'),'-m',str(root/'model'),'--eval','-r','1','--data_device','cpu'])
    (root/'model').mkdir();safe_state(False);args.jbgs_target='on';args.jbgs_target_dir=str(OUT/'r3/prior_only'/f'{site}_{prior}')
    args.jbgs_target_lambda=.05;args.jbgs_judgment='off';args.jbgs_appearance='off';args.jbgs_mv_consistency='off'
    g=GaussianModel(args.sh_degree);scene=Scene(lp.extract(args),g);pipe=pp.extract(args);controller=jbgs_target.create(args,scene,g,render,pipe)
    reps=[r for r in json.loads((CFG/'representatives_v1.json').read_text())['rows'] if r['site']==site and prior in r['priors']]
    bg=torch.zeros(3,device='cuda');rows=[]
    with np.load(OUT/'r2/targets'/f'{site}_{prior}.npz') as z:t={k:z[k] for k in z.files}
    with np.load(OUT/'r3/prior_only'/f'{site}_{prior}/seeds.npz') as z:s={k:z[k] for k in z.files}
    with np.load(OUT/'stage0_r1/inputs'/f'{site}_{prior}.npz') as z:kind=z['kind']
    normals=build_rotation(g._rotation)[:,:,2];normalerr=float((normals-controller.normal).abs().max())
    saved={k:getattr(g,k) for k in ['_xyz','_features_dc','_features_rest','_opacity','_scaling','_rotation']}
    seedkind=kind[s['patch']];counts=np.bincount(s['patch'],minlength=len(kind))
    for rep in reps:
        cam=next(c for c in scene.getTrainCameras() if c.image_name==rep['camera']['name'])
        pkg=render(cam,g,pipe,bg);D=pkg['surf_depth'].squeeze().cpu().numpy();alpha=pkg['rend_alpha'].squeeze().cpu().numpy()
        m=controller.maps[cam.image_name];T=m['depth'].numpy();owner=m['owner'].numpy();has=owner>=0
        valid=has&np.isfinite(T)&(T>0)&np.isfinite(D)&(D>0);pixelkind=kind[np.maximum(owner,0)]
        strata={}
        for label,mask in [('all_prior',valid),('roof',valid&(pixelkind==1)),('wall',valid&(pixelkind==2)),
            ('owner_has_seed',valid&(counts[np.maximum(owner,0)]>0)),('owner_no_seed',valid&(counts[np.maximum(owner,0)]==0))]:
            strata[label]=dict(error=stats(abs(D[mask]-T[mask])),alpha=stats(alpha[mask]))
        for k,label in [(1,'roof_only'),(2,'wall_only')]:
            keep=torch.as_tensor(seedkind==k,device='cuda')
            if not keep.any():continue
            for key,value in saved.items():setattr(g,key,torch.nn.Parameter(value[keep].detach()))
            dep=render(cam,g,pipe,bg)['surf_depth'].squeeze().cpu().numpy();mask=valid&(pixelkind==k)&(dep>0)&np.isfinite(dep)
            strata[label]=dict(error=stats(abs(dep[mask]-T[mask])),combined_error_same_pixels=stats(abs(D[mask]-T[mask])),
                note='diagnostic only; subset is not a replacement gate')
        for key,value in saved.items():setattr(g,key,value)
        pipe.depth_ratio=1.;median_depth=render(cam,g,pipe,bg)['surf_depth'].squeeze().cpu().numpy();pipe.depth_ratio=0.
        mask=valid&np.isfinite(median_depth)&(median_depth>0)
        strata['median_depth_diagnostic']=dict(error=stats(abs(median_depth[mask]-T[mask])),
            expected_error_same_pixels=stats(abs(D[mask]-T[mask])),note='depth_ratio=1 diagnostic only; baseline depth_ratio=0 retained')
        # Render a deterministic selection of individual owning patches, with their original scales.
        eligible=np.flatnonzero(valid&(counts[np.maximum(owner,0)]>0));selected=eligible[np.linspace(0,len(eligible)-1,24,dtype=int)]
        own=[]
        for flat in selected:
            y,x=np.unravel_index(flat,D.shape);patch=int(owner[y,x]);keep=torch.as_tensor(s['patch']==patch,device='cuda')
            for key,value in saved.items():setattr(g,key,torch.nn.Parameter(value[keep].detach()))
            dp=render(cam,g,pipe,bg)['surf_depth'].squeeze().cpu().numpy()[y,x]
            own.append(dict(pixel=[int(x),int(y)],patch=patch,kind=int(kind[patch]),seed_count=int(keep.sum()),
                target_m=float(T[y,x]),combined_m=float(D[y,x]),owner_only_m=float(dp) if np.isfinite(dp) and dp>0 else None))
        for key,value in saved.items():setattr(g,key,value)
        np.savez_compressed(root/f'rep_{rep["id"]}.npz',depth=D,alpha=alpha,target=T,owner=owner,
            median_depth=median_depth,rgb=pkg['render'].cpu().numpy(),photo=cam.original_image.cpu().numpy())
        rows.append(dict(representative=rep['id'],camera=cam.image_name,strata=strata,individual_owner_samples=own))
    scales=g.get_scaling.max(1).values.cpu().numpy();rank=np.lexsort((np.arange(len(scales)),-scales))[:10]
    record=dict(at=stamp(),site=site,prior=prior,rows=rows,quaternion_normal_max_error=normalerr,
        seed_target_max_error_m=float(np.max(abs(s['xyz']-t['target'][s['patch']]))),
        renderer_depth='baseline expected depth (alpha-weighted multiple contributions), depth_ratio=0; target map is nearest oriented patch disc',
        initial_opacity=stats(g.get_opacity[:,0].cpu().numpy()),prior_scale=stats(scales),
        prior_scale_top10=[dict(init_id=int(i),kind=int(seedkind[i]),patch=int(s['patch'][i]),scale_m=float(scales[i]),xyz=s['xyz'][i].tolist()) for i in rank],
        optimization_steps=0,config_sha256=lock['config_sha256'],scientific_verdict=None)
    dump(root/'diagnosis.json',record);print('DIAGNOSIS_COMPLETE',site,prior,flush=True)

if __name__=='__main__':main()
