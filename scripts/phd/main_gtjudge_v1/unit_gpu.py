"""100 seeded real GaussianModel steps and synthetic opacity-only selection."""
import ast
import random
import sys
from argparse import ArgumentParser
from types import SimpleNamespace as NS
import numpy as np
import torch
from scipy.spatial import cKDTree
from common import *
sys.path.insert(0,'/source')
from arguments import OptimizationParams
from scene import GaussianModel
from utils.graphics_utils import BasicPointCloud
from jbgs_target_r8 import TargetR8
import jbgs_target
import jbgs_state as S

def default(label):
    root=O/'verification/default'/label
    root.mkdir(parents=True,exist_ok=False)
    parser=ArgumentParser();op=OptimizationParams(parser);jbgs_target.register_args(parser)
    args=parser.parse_args([])
    assert getattr(args,'jbgs_targets',None) is None
    assert getattr(args,'jbgs_preserve_freespace','off')=='off'
    opt=op.extract(args)
    path=R/'scripts/phd/main_target_v1/unit_r8.py'
    nodes=[n for n in ast.parse(path.read_text()).body if isinstance(n,ast.FunctionDef)
        and n.name in ['setup','steps','environment']]
    env=dict(np=np,torch=torch,NS=NS,GaussianModel=GaussianModel,BasicPointCloud=BasicPointCloud,
        cKDTree=cKDTree,TargetR6=TargetR8,S=S,random=random)
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),env)
    torch.use_deterministic_algorithms(True);torch.manual_seed(0);np.random.seed(0);random.seed(0)
    g,control=env['setup'](opt,root/'fixture');control.reattach(g,'initial')
    state=env['environment'](g,control,opt,root/'fixture')
    sequence=env['steps'](state,1,100)
    torch.save(dict(model=g.capture(),meta=control.capture(g),sequence=sequence),root/'state.pth')
    print('DEFAULT_100_COMPLETE',label,flush=True)

def equal(a,b):
    if torch.is_tensor(a):return torch.equal(a,b)
    if isinstance(a,dict):return a.keys()==b.keys() and all(equal(a[k],b[k]) for k in a)
    if isinstance(a,(list,tuple)):return len(a)==len(b) and all(equal(x,y) for x,y in zip(a,b))
    if isinstance(a,np.ndarray):return np.array_equal(a,b)
    return a==b

def compare():
    states=[torch.load(O/'verification/default'/label/'state.pth',map_location='cpu',weights_only=False)
            for label in ['r23','r25']]
    assert equal(*states),'Default model, optimizer, target metadata or camera sequence differs'
    result=dict(at=now(),status='PASS_100_STEP_FIXTURE',steps=100,seed=0,
        GaussianModel=True,model_and_Adam_bit_equal=True,decisions_equal=True,camera_order_equal=True,
        real_scene_training=False,rendered_photo_loss=False,
        scope='same small-example APIs as FINALTRAIN probe_default.py',scientific_verdict=None)
    dump(O/'verification/unit_default.json',result);dump(D/'tables/unit_default.json',result)
    print('PASS_R23_R25_DEFAULT_100')

def primitives():
    from jbgs_gtjudge import candidate_mask,opacity_penalty,calibrated_lambda,target_path,verify_override
    device='cuda'
    # Front, inside CI, behind, non-preserve, same patch, different patch, released/background.
    xyz=torch.tensor([[0.,0.,9.5],[0,0,9.9],[0,0,10.5],[9.5,0,9.5],
                      [0,0,9.5],[0,0,9.5],[0,0,9.5]],device=device,requires_grad=True)
    bound=torch.tensor([-1,-1,-1,-1,0,1,-1],device=device)
    depth=torch.full((3,3),10.,device=device);sigma=torch.full((3,3),.1,device=device)
    owner=torch.zeros((3,3),device=device,dtype=torch.long);owner[1,2]=1
    judge=torch.tensor([1,0],device=device)
    K=torch.tensor([[1.,0,1],[0,1,1],[0,0,1]],device=device,dtype=torch.float64)
    W=torch.eye(4,device=device,dtype=torch.float64)
    mask=candidate_mask(xyz,bound,depth,sigma,owner,judge,K,W)
    assert mask.tolist()==[True,False,False,False,False,True,True]
    opacity=torch.nn.Parameter(torch.zeros((7,1),device=device))
    colour=torch.nn.Parameter(torch.ones((7,3),device=device))
    scale=torch.nn.Parameter(torch.ones((7,2),device=device))
    photo=(torch.sigmoid(opacity)*.7).sum()
    weight,calibration=calibrated_lambda(photo,opacity,mask)
    assert abs(weight-2.1)<1e-6
    loss=opacity_penalty(opacity,mask,weight)
    loss.backward()
    assert xyz.grad is None and colour.grad is None and scale.grad is None
    before=torch.sigmoid(opacity.detach()).clone()
    with torch.no_grad():opacity-=.1*opacity.grad
    after=torch.sigmoid(opacity.detach())
    assert bool((after[mask]<before[mask]).all()) and torch.equal(after[~mask],before[~mask])
    root=O/'verification/target_fixture/stage1/example';root.mkdir(parents=True,exist_ok=True)
    (root/'maps').mkdir(exist_ok=True)
    target=O/'verification/target_fixture/정답판단_예제.npz'
    arr=dict(target=np.array([[1.,2.,3.],[4,5,6]]),sigma=np.array([.1,.2]),
        region=np.array([2,3],np.int8),judge_region=np.array([1,2],np.int8))
    np.savez(target,**arr)
    np.savez(root/'seeds.npz',origin=np.ones(2,np.int8),patch=np.arange(2),
        target=arr['target'].astype('f4'),sigma=arr['sigma'].astype('f4'),region=arr['region'])
    dump(root/'maps/index.json',dict(target_sha256=sha(target)))
    args=NS(jbgs_targets=str(target),jbgs_finaltrain='on',jbgs_target='on',jbgs_target_rev='r8')
    assert target_path(args,root)==target
    verify_override(args,root)
    with np.load(target_path(args,root)) as loaded:
        assert all(np.array_equal(loaded[k],v) for k,v in arr.items())
    dump(root/'maps/index.json',dict(target_sha256='incorrect'))
    try:verify_override(args,root)
    except ValueError:pass
    else:raise AssertionError('Stale maps accepted')
    result=dict(at=now(),status='PASS_SYNTHETIC_PRIMITIVES_ONLY',candidate_mask=mask.tolist(),
        only_selected_opacity_decreased=True,position_scale_colour_gradients_absent=True,
        lambda_fs=weight,calibration=calibration,override_fixture_exact=True,stale_maps_rejected=True,
        real_section3_target_file_check='NOT_RUN_NO_SECTION3_TARGETS',
        A2_runtime_ready=False,reason='500..999 loss weight unspecified; stage0 inputs unavailable',
        scientific_verdict=None)
    dump(O/'verification/unit_primitives.json',result);dump(D/'tables/unit_primitives.json',result)
    print('PASS_OPACITY_AND_OVERRIDE_PRIMITIVES; A2_RUNTIME_NOT_READY')

if __name__=='__main__':
    cfg();mode,label=sys.argv[1:]
    if mode=='default':default(label)
    elif mode=='compare':compare()
    elif mode=='primitives':primitives()
    else:raise ValueError(mode)
