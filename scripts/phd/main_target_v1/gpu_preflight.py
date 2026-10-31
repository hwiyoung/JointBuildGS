"""Actual r19 clamp/clone/split and untouched initial-scene rendering; no optimization."""
import sys
sys.path.insert(0,'/source')
from argparse import ArgumentParser
import numpy as np
import torch
from common import *
from arguments import ModelParams,PipelineParams,OptimizationParams
from scene import Scene,GaussianModel
from utils.graphics_utils import BasicPointCloud
from utils.general_utils import safe_state
from gaussian_renderer import render
import jbgs_target


@torch.no_grad()
def unit_check(opt):
    anchor=torch.tensor([[1.,2.,3.],[4.,5.,6.],[0.,0.,0.]],device='cuda')
    normal=torch.tensor([[0.,0.,1.],[0.,1.,0.],[1.,0.,0.]],device='cuda')
    sigma=torch.tensor([.1,.2,.3],device='cuda')
    x=anchor+torch.tensor([[3.,4.,.5],[2.,-.6,3.],[.1,7.,8.]],device='cuda')
    y=jbgs_target.normal_projection(x,anchor,normal,sigma)
    expected=anchor+torch.tensor([[3.,4.,.196],[2.,-.392,3.],[.1,7.,8.]],device='cuda')
    assert torch.allclose(y,expected,atol=1e-6,rtol=0)
    g=GaussianModel(0);xyz=np.array([[0,0,0],[1,0,0],[0,1,0],[0,0,1]],np.float32)
    g.create_from_pcd(BasicPointCloud(xyz,np.ones_like(xyz)*.5,np.zeros_like(xyz)),1)
    g.training_setup(opt);g._scaling[:]=np.log(.001);g._scaling[1]=0
    grads=torch.zeros((4,1),device='cuda');grads[0]=1;g.densify_and_clone(grads,.5,1)
    assert g.init_id.tolist()==[0,1,2,3,0]
    grads=torch.zeros((5,1),device='cuda');grads[1]=1;g.densify_and_split(grads,.5,1)
    assert g.init_id.tolist()==[0,2,3,0,1,1]
    parent_targets=torch.arange(12,device='cuda').reshape(4,3)
    assert torch.equal(parent_targets[g.init_id.long()][-2:],parent_targets[1].repeat(2,1))
    # After pruning, children still index the same immutable target metadata.
    prune=torch.tensor([False,True,False,False,False,False],device='cuda');g.prune_points(prune)
    assert g.init_id.tolist()==[0,3,0,1,1]
    return dict(status='PASS',normal_clamp=True,inside_unchanged=True,tangential_unchanged=True,
                actual_clone_split_prune=True,child_init_ids=g.init_id.tolist(),scientific_verdict=None)


@torch.no_grad()
def main():
    site,prior=sys.argv[1:3];cfg,lock=training_locked()
    repfile=CFG/'representatives_v1.json';assert sha(repfile)==json.loads((CFG/'representatives_v1.lock.json').read_text())['sha256']
    reps=[r for r in json.loads(repfile.read_text())['rows'] if r['site']==site and prior in r['priors']]
    root=OUT/'preflight'/f'{site}_{prior}';root.mkdir(parents=True,exist_ok=False)
    parser=ArgumentParser();lp=ModelParams(parser);op=OptimizationParams(parser);pp=PipelineParams(parser)
    args=parser.parse_args(['-s',str(S0/'fork_inputs/s61'/site/f'scene_{prior}'),'-m',str(root/'model'),
        '--eval','-r','1','--data_device','cpu'])
    (root/'model').mkdir();opt=op.extract(args);pipe=pp.extract(args)
    dump(root/'unit.json',unit_check(opt));safe_state(False)
    args.jbgs_target='on';args.jbgs_target_dir=str(OUT/'stage1'/f'{site}_{prior}');args.jbgs_target_lambda=.05
    args.jbgs_judgment='off';args.jbgs_appearance='off';args.jbgs_mv_consistency='off'
    g=GaussianModel(args.sh_degree);scene=Scene(lp.extract(args),g)
    controller=jbgs_target.create(args,scene,g,render,pipe)
    bg=torch.zeros(3,device='cuda');rows=[];errors=[];prior_errors=[];repnames={r['camera']['name'] for r in reps}
    for i,cam in enumerate(sorted(scene.getTrainCameras(),key=lambda c:c.image_name)):
        pkg=render(cam,g,pipe,bg);D=pkg['surf_depth'].squeeze().cpu().numpy();m=controller.maps[cam.image_name]
        T=m['depth'].numpy();owner=m['owner'].numpy();good=np.isfinite(T)&(T>0)
        available=np.isfinite(D)&(D>0);valid=good&available;err=np.abs(D[valid]-T[valid]);pe=np.abs(D[valid&(owner>=0)]-T[valid&(owner>=0)])
        errors.append(err);prior_errors.append(pe)
        row=dict(camera=cam.image_name,target_pixels=int(good.sum()),rendered_target_pixels=int(valid.sum()),
            missing_render_fraction=float((good&~available).sum()/max(1,good.sum())),
            absolute_depth_error_median_m=float(np.median(err)) if len(err) else None,
            prior_error_median_m=float(np.median(pe)) if len(pe) else None)
        if cam.image_name in repnames:
            np.savez_compressed(root/f'{cam.image_name}.npz',render_depth=D,target_depth=T,owner=owner,
                render_rgb=pkg['render'].cpu().numpy(),photo_rgb=cam.original_image.cpu().numpy())
            row['representative']=True
        rows.append(row)
        if (i+1)%40==0:print('INITIAL_RENDER',site,prior,i+1,len(scene.getTrainCameras()),flush=True)
    error=np.concatenate(errors);p_error=np.concatenate(prior_errors);median=float(np.median(error))
    record=dict(site=site,prior=prior,at=stamp(),status='PASS' if median<=.05 else 'FAIL_INITIAL_RENDER_DEPTH_5CM',
        views=rows,pooled_pixels=len(error),pooled_median_m=median,prior_pooled_pixels=len(p_error),prior_pooled_median_m=float(np.median(p_error)),
        criterion_m=.05,optimization_steps=0,seed=0,config_sha256=lock['config_sha256'],representatives_sha256=sha(repfile),
        missing_render_policy='reported separately, never counted as correct',scientific_verdict=None)
    dump(root/'initial_render.json',record);print('INITIAL_RENDER_COMPLETE',site,prior,median,record['status'],flush=True)

if __name__=='__main__':main()
