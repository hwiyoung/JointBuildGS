"""Validate new diagnostic metadata without optimization or altered initialization."""
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
def main():
    site,prior=sys.argv[1:3];cfg,lock=locked_r3()
    root=OUT/'r3/monitorcheck'/f'{site}_{prior}';root.mkdir(parents=True,exist_ok=False)
    parser=ArgumentParser();lp=ModelParams(parser);pp=PipelineParams(parser);op=OptimizationParams(parser)
    args=parser.parse_args(['-s',str(S0/'fork_inputs/s61'/site/f'scene_{prior}'),'-m',str(root/'model'),'--eval','-r','1','--data_device','cpu'])
    (root/'model').mkdir();safe_state(False);args.jbgs_target='on';args.jbgs_target_dir=str(OUT/'r2/stage1'/f'{site}_{prior}')
    args.jbgs_target_lambda=.05;args.jbgs_judgment='off';args.jbgs_appearance='off';args.jbgs_mv_consistency='off'
    g=GaussianModel(args.sh_degree);scene=Scene(lp.extract(args),g);pipe=pp.extract(args)
    state=torch.get_rng_state().clone();cuda=torch.cuda.get_rng_state().clone()
    control=jbgs_target.create(args,scene,g,render,pipe)
    assert torch.equal(state,torch.get_rng_state()) and torch.equal(cuda,torch.cuda.get_rng_state())
    old=OUT/'r2/preflight'/f'{site}_{prior}/model/target_monitor/snapshot_0.npz'
    with np.load(old) as a,np.load(root/'model/target_monitor/snapshot_0.npz') as b:
        for key in a.files:assert np.array_equal(a[key],b[key]),key
    census=json.loads((OUT/'r3/census'/f'{site}_{prior}/initial_background_sizes.json').read_text())
    actual=json.loads((root/'model/target_monitor/initial_large_background.json').read_text())
    assert census['count_gt_1m']==actual['count_gt_1m']
    assert census['max_scale_m']==actual['top10'][0]['max_scale_m']
    cam=next(c for c in scene.getTrainCameras() if c.image_name=='DJI_20241217091253_0149_D')
    labels=torch.zeros((len(g._xyz),3),device='cuda');labels[:,0]=(g.origin==0).float();labels[:,1]=control.initial_large_background.float();labels[:,2]=(g.origin==1).float()
    pkg=render(cam,g,pipe,torch.zeros(3,device='cuda'),override_color=labels)
    alpha=pkg['rend_alpha'].squeeze();valid=alpha>1e-5
    sumerror=float((pkg['render'][0]+pkg['render'][2]-alpha)[valid].abs().max())
    assert sumerror<2e-6,sumerror
    assert bool((pkg['render'][1]<=pkg['render'][0]+2e-6).all())
    # Exercise real clone/split/prune on small GaussianModel; ancestry must survive.
    small=GaussianModel(0);xyz=np.array([[0.,0,0],[1,0,0],[0,1,0],[0,0,1]],np.float32)
    small.create_from_pcd(BasicPointCloud(xyz,np.ones_like(xyz)*.5,np.zeros_like(xyz)),1);small.training_setup(op.extract(args))
    test=jbgs_target.Target.__new__(jbgs_target.Target);test.anchor=small._xyz.detach().clone()
    test.normal=torch.tensor([[0.,0,1]]*4,device='cuda');test.initial_large_background=torch.tensor([True,True,False,False],device='cuda')
    small._scaling[:]=np.log(.001);small._scaling[1]=0
    grads=torch.zeros((4,1),device='cuda');grads[0]=1;small.densify_and_clone(grads,.5,1)
    grads=torch.zeros((5,1),device='cuda');grads[1]=1;small.densify_and_split(grads,.5,1)
    prune=torch.tensor([False,True,False,False,False,False],device='cuda');small.prune_points(prune)
    test.large_background_evidence(7000,small,root)
    result=json.loads((root/'large_background_descendants.json').read_text())
    assert result['surviving_gaussians']==4 and result['counts_by_ancestor']=={'0':2,'1':2}
    # Explicitly label this as a synthetic check, never a real iteration-7000 result.
    result.update(synthetic_unit_check=True,actual_training_steps=0);dump(root/'large_background_descendants.json',result)
    record=dict(at=stamp(),status='PASS_MONITOR_DIAGNOSTICS',existing_snapshot_arrays_byte_identical=True,
        random_states_unchanged=True,large_background_count=actual['count_gt_1m'],max_background_scale_m=census['max_scale_m'],
        attribution_sum_error=sumerror,large_subset_of_background=True,synthetic_clone_split_prune_counts=result['counts_by_ancestor'],
        actual_training_steps=0,scientific_verdict=None)
    dump(root/'verification.json',record);dump(DOC/'tables/monitor_verification_r3.json',record);print('MONITOR_CHECK_PASS',flush=True)

if __name__=='__main__':main()
