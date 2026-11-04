import ast,random,sys
from types import SimpleNamespace as NS
from argparse import ArgumentParser
from common import *
sys.path.insert(0,'/source')
import torch
from scipy.spatial import cKDTree
from arguments import OptimizationParams
from scene import GaussianModel
from utils.graphics_utils import BasicPointCloud
from jbgs_release import Release
from release_search import TangentTree
def same(a,b):
    if torch.is_tensor(a):return torch.equal(a,b)
    if isinstance(a,dict):return a.keys()==b.keys() and all(same(a[k],b[k]) for k in a)
    if isinstance(a,(list,tuple)):return len(a)==len(b) and all(same(x,y) for x,y in zip(a,b))
    if isinstance(a,np.ndarray):return np.array_equal(a,b)
    return a==b
base=torch.load(O/'verification/default/r23/state.pth',map_location='cpu',weights_only=False)
for label in ['r24_off','r24_on']:
    assert same(base,torch.load(O/'verification/default'/label/'state.pth',map_location='cpu',weights_only=False)),label
dump(O/'verification/unit_default.json',dict(at=now(),status='PASS',steps=100,actual_model_Adam_decisions_camera_equal=True,clone_split_prune_equal=True,scientific_verdict=None))
p=ArgumentParser();op=OptimizationParams(p);opt=op.extract(p.parse_args([]))
src=R/'scripts/phd/main_target_v1/unit_r8.py';node=next(n for n in ast.parse(src.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='setup')
env=dict(np=np,torch=torch,GaussianModel=GaussianModel,BasicPointCloud=BasicPointCloud,cKDTree=cKDTree,TargetR6=Release)
exec(compile(ast.Module(body=[node],type_ignores=[]),str(src),'exec'),env)
for rule in ['pull','delete','mix']:
    g,c=env['setup'](opt,O/'verification/rules'/rule);c.release_rule=rule;c.release_log='off';c.initialize_tracking(g)
    with torch.no_grad():g._xyz[0]=torch.tensor([.3,0,2.0196],device='cuda');g._xyz[1]=torch.tensor([2.6,0,0],device='cuda')
    # Populate Adam moments before deletion so stale-state rows cannot pass.
    loss=sum(v['params'][0].square().sum() for v in g.optimizer.param_groups);loss.backward();g.optimizer.step();g.optimizer.zero_grad(set_to_none=True)
    with torch.no_grad():g._xyz[0]=torch.tensor([.3,0,2.0196],device='cuda');g._xyz[1]=torch.tensor([2.6,0,0],device='cuda')
    c.reattach(g,'periodic');c.project_bounds(g)
    if rule=='pull':
        assert g.target_tag.tolist()==[1,2,0,2];assert abs(float(g._xyz[0,2])-.0196)<1e-6
        with torch.no_grad():g._xyz[1]=torch.tensor([2.3,0,.1],device='cuda')
        c.reattach(g,'periodic');c.project_bounds(g);assert int(g.target_tag[1])==1
    elif rule=='delete':assert len(g._xyz)==1 and g.origin.tolist()==[0]
    else:assert len(g._xyz)==2 and g.target_tag.tolist()==[1,0] and abs(float(g._xyz[0,2])-.0196)<1e-6
    for group in g.optimizer.param_groups:
        v=group['params'][0]
        if v.ndim:
            assert v.shape[0]==len(g._xyz)
            st=g.optimizer.state.get(v,{})
            for k in ['exp_avg','exp_avg_sq']:
                if k in st:assert st[k].shape[0]==len(g._xyz)
    assert g.xyz_gradient_accum.shape[0]==g.denom.shape[0]==len(g._xyz)
rng=np.random.default_rng(92);points=rng.normal(size=(139,3));normals=rng.normal(size=(139,3));normals/=np.linalg.norm(normals,axis=1)[:,None];width=rng.uniform(.01,.3,139);q=rng.normal(size=(241,3))
tree=TangentTree(points,normals,width,np.arange(139));d,e,j=tree.query(q)
for k,x in enumerate(q):
    delta=x-points;h=(delta*normals).sum(1);t=np.linalg.norm(delta-h[:,None]*normals,axis=1);ex=np.maximum(abs(h)-width,0);expected=np.lexsort((np.arange(139),ex,t))[0]
    assert j[k]==expected and abs(d[k]-t[expected])<1e-12
dump(O/'verification/unit_rules.json',dict(at=now(),status='PASS',pull_normal2_tangent03=True,pull_tangent06_releases=True,reattachment=True,delete_Adam_rows=True,mix=True,exact_tangent_search_bruteforce=241,scientific_verdict=None))
print('PASS_RELEASE_UNITS',flush=True)
