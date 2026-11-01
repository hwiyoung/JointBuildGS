"""GPU unit verification on real GaussianModel, Adam, density and complete state APIs."""
import copy, random, sys
from pathlib import Path
from types import SimpleNamespace as NS
sys.path.insert(0,'/source')
import numpy as np, torch
from scipy.spatial import cKDTree
from argparse import ArgumentParser
from arguments import OptimizationParams
from scene import GaussianModel
from utils.graphics_utils import BasicPointCloud
import jbgs_state as S
from jbgs_target_r6 import META, restore_complete
from jbgs_target_r7 import TargetR7 as TargetR6
from gpu_preflight_r2 import unit_check
from common import *
ROOT=OUT/'r7/verification/unit';ROOT.mkdir(parents=True,exist_ok=False)

def setup(opt,folder):
    folder.mkdir(parents=True);(folder/'maps').mkdir();(folder/'maps/index.json').write_text('{}');(folder/'seeds.npz').write_bytes(b'unit input identity')
    g=GaussianModel(0);xyz=np.array([[0,0,.4],[2,0,.4],[0,0,3],[9,0,0]],np.float32)
    g.create_from_pcd(BasicPointCloud(xyz,np.full_like(xyz,.5),np.zeros_like(xyz)),1);g.training_setup(opt)
    g.origin=torch.tensor([1,1,0,1],device='cuda',dtype=torch.int8)
    c=TargetR6.__new__(TargetR6);c.root=folder;c.mon=None;c.n6000=4;c.events=[];c.iteration=0;c.target_hash='unit frozen target'
    c.points=np.array([[0,0,0],[2,0,0]],np.float64);c.tree=cKDTree(c.points);c.valid_patch=np.arange(2)
    c.patch_anchor=torch.tensor(c.points,device='cuda',dtype=torch.float32)
    c.patch_normal=torch.tensor([[0.,0.,1.],[0.,0.,1.]],device='cuda');c.patch_sigma=torch.tensor([.01,.02],device='cuda');c.patch_region=torch.tensor([1,3],device='cuda')
    g.target_tag=g.origin.clone();g.target_index=torch.tensor([1,0,-1,0],device='cuda');g.target_released_at=torch.full((4,),-1,device='cuda',dtype=torch.int32);g.target_r6=c
    return g,c

def equal(a,b):
    if torch.is_tensor(a):return torch.equal(a,b)
    if isinstance(a,dict):return a.keys()==b.keys() and all(equal(a[k],b[k]) for k in a)
    if isinstance(a,(list,tuple)):return len(a)==len(b) and all(equal(x,y) for x,y in zip(a,b))
    if isinstance(a,np.ndarray):return np.array_equal(a,b)
    return a==b

def environment(g,c,opt,folder):
    args=NS(model_path=str(folder),jbgs_target='on',jbgs_target_rev='r7',jbgs_release_protection=False,jbgs_input_manifest=None,
        lod2_building_xyz_lr_scale=1.,protect_bldg_lr_scale=1.,protect_bldg=False,jbgs_resume_full=None,jbgs_stop_after=0,jbgs_capture_iterations=[7000,15000,30000])
    train=[NS(image_name=str(i)) for i in range(7)];test=[NS(image_name='test')]
    scene=NS(getTrainCameras=lambda:train,getTestCameras=lambda:test)
    env=dict(gaussians=g,target_control=c,scene=scene,args=args,opt=opt,iteration=0,building_freeze_mask=None,viewpoint_stack=None)
    env.update({k:None for k in S.RUNTIME_KEYS});return env

def steps(env,start,end):
    g,c=env['gaussians'],env['target_control'];sequence=[]
    for i in range(start,end+1):
        c.iteration=i;env['iteration']=i;g.update_learning_rate(i)
        if not env['viewpoint_stack']:env['viewpoint_stack']=env['scene'].getTrainCameras().copy()
        camera=env['viewpoint_stack'].pop(random.randrange(len(env['viewpoint_stack'])));sequence.append(camera.image_name)
        g.optimizer.zero_grad(set_to_none=True)
        jitter=torch.rand_like(g._xyz)*.01+float(np.random.random())*.001+int(camera.image_name)*.001
        loss=((g._xyz-jitter)**2).mean()
        for v in [g._features_dc,g._features_rest,g._opacity,g._rotation,g._scaling]:loss=loss+v.square().sum()*.0001
        loss.backward();g.optimizer.step()
        if i%100==0:c.reattach(g,'periodic')
        c.project_bounds(g)
        if i in [110,160]:
            with torch.no_grad():
                g._scaling[:]=np.log(.001);grads=torch.zeros((len(g._xyz),1),device='cuda');grads[0]=1
                g.densify_and_clone(grads,.5,1)
                if i==160:
                    prune=torch.zeros(len(g._xyz),device='cuda',dtype=torch.bool);prune[1]=True;g.prune_points(prune)
    return sequence

def main():
    torch.use_deterministic_algorithms(True);torch.manual_seed(0);np.random.seed(0);random.seed(0)
    p=ArgumentParser();op=OptimizationParams(p);opt=op.extract(p.parse_args([]));old=unit_check(opt)
    g,c=setup(opt,ROOT/'geometry')
    initial=g._xyz.detach().clone();c.reattach(g,'unit')
    assert g.target_index[:2].tolist()==[0,1] and g.target_tag.tolist()==[1,1,0,2]
    assert torch.equal(g._xyz[2:],initial[2:]);assert float(torch.linalg.vector_norm(g._xyz-initial,dim=1).max())<=.5
    with torch.no_grad():g._xyz[3]=torch.tensor([0.,0.,8.],device='cuda')
    c.reattach(g,'unit_no_rejoin');assert g.target_tag[3]==2 and float(g._xyz[3,2])==8
    # Children inherit a released tag even if placed close to a valid target.
    with torch.no_grad():
        g._xyz[3]=torch.tensor([0.,0.,.1],device='cuda');g._scaling[:]=np.log(.001)
        grad=torch.zeros((4,1),device='cuda');grad[3]=1;g.densify_and_clone(grad,.5,1)
        assert g.target_tag[-1]==2 and g.target_released_at[-1]==g.target_released_at[3]
        # Actual split: far children must release, near children must bind to their nearest target.
        g._scaling[0]=np.log(.03);grad=torch.zeros((len(g._xyz),1),device='cuda');grad[0]=1
        g.densify_and_split(grad,.5,1)
        for j in torch.where(g.target_tag==1)[0]:
            d,ix=c.nearest(g._xyz[j:j+1]);assert d[0]<=.5 and int(g.target_index[j])==ix[0]
    wide,cw=setup(opt,ROOT/'wide')
    with torch.no_grad():
        cw.patch_sigma[:]=1.;wide._xyz[0]=torch.tensor([0.,0.,.8],device='cuda');wide._xyz[1]=torch.tensor([2.6,0.,0.],device='cuda')
    cw.reattach(wide,'wide_normal_and_tangent')
    assert wide.target_tag[:2].tolist()==[1,2] and float(wide._xyz[0,2])==float(np.float32(.8))
    with torch.no_grad():
        wide._scaling[:]=np.log(.001);grad=torch.zeros((len(wide._xyz),1),device='cuda');grad[0]=1;wide.densify_and_clone(grad,.5,1)
        assert wide.target_tag[-1]==1
        wide._scaling[0]=np.log(.03);grad=torch.zeros((len(wide._xyz),1),device='cuda');grad[0]=1;wide.densify_and_split(grad,.5,1)
        assert (wide.target_tag[-2:]==1).all()
    # Independent all-target search, arbitrary normals and wide intervals.
    rng=np.random.default_rng(9);br=TargetR6.__new__(TargetR6);br.points=rng.normal(size=(137,3));br.valid_patch=np.arange(137)
    normal=rng.normal(size=(137,3));normal/=np.linalg.norm(normal,axis=1)[:,None]
    br.patch_normal=torch.tensor(normal,device='cuda',dtype=torch.float32);br.patch_sigma=torch.tensor(10**rng.uniform(-2,1,137),device='cuda',dtype=torch.float32)
    q=rng.normal(size=(731,3));tt,ee,ii=br.candidates(torch.tensor(q,device='cuda',dtype=torch.float64))
    normal=br.patch_normal.double().cpu().numpy();normal/=np.linalg.norm(normal,axis=1)[:,None];width=(1.96*br.patch_sigma).double().cpu().numpy()
    for j,x in enumerate(q):
        d=x-br.points;h=(d*normal).sum(1);t=np.linalg.norm(d-h[:,None]*normal,axis=1);e=np.maximum(abs(h)-width,0);keep=np.flatnonzero((t<=.5)&(e<=.5))
        if not len(keep):assert not np.isfinite(tt[j]);continue
        expected=keep[np.lexsort((br.valid_patch[keep],e[keep],t[keep]))[0]];assert ii[j]==expected
    cw.last_opacity_reset=3000
    assert cw.opacity_grace(3000) and cw.opacity_grace(3500) and not cw.opacity_grace(3501)
    g,c=setup(opt,ROOT/'continuous');c.reattach(g,'initial');env=environment(g,c,opt,ROOT/'continuous')
    steps(env,1,100);c.last_opacity_reset=95;state=S.capture_state(env);torch.save(state,ROOT/'checkpoint_100.pth')
    seq_a=steps(env,101,200);model_a=copy.deepcopy(g.capture());meta_a=c.capture(g)
    g2,c2=setup(opt,ROOT/'resumed');env2=environment(g2,c2,opt,ROOT/'resumed')
    restored=restore_complete(ROOT/'checkpoint_100.pth',torch.load(ROOT/'checkpoint_100.pth'),env2);env2.update(restored)
    seq_b=steps(env2,101,200)
    assert equal(model_a,g2.capture()),'model/Adam differs after resumed 100 steps'
    assert equal(meta_a,c2.capture(g2)),'dynamic metadata differs'
    assert seq_a==seq_b,'camera sequence differs'
    assert c2.last_opacity_reset==95
    result=dict(at=stamp(),status='PASS_R7_UNIT',legacy_bounds_inheritance=old,background_unchanged=True,released_never_rejoins=True,
        nearest_reassignment=True,clone_split_prune=True,wide_sigma_normal_08_retained=True,tangent_06_released=True,arbitrary_normals_bruteforce_queries=731,opacity_grace_and_resume=True,resume_100_steps_model_and_adam_bit_identical=True,
        resume_rng_camera_order_and_dynamic_target_equal=True,deterministic=True,project_dependencies='Docker',scientific_verdict=None)
    dump(ROOT.parent/'unit.json',result);print(json.dumps(result),flush=True)
if __name__=='__main__':main()
