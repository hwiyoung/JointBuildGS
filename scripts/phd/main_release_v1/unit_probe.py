"""Inherited 100-step actual GaussianModel/Adam fixture, same seed/cameras."""
import ast,random,sys
from argparse import ArgumentParser
from types import SimpleNamespace as NS
from common import *
sys.path.insert(0,'/source')
import torch
from scipy.spatial import cKDTree
from arguments import OptimizationParams
from scene import GaussianModel
from utils.graphics_utils import BasicPointCloud
import jbgs_state as S
from jbgs_target_r8 import TargetR8
import jbgs_target
label=sys.argv[1];cls=TargetR8
if label!='r23':
    from jbgs_release import Release
    cls=Release
root=O/'verification/default'/label;root.mkdir(parents=True,exist_ok=False)
p=ArgumentParser();op=OptimizationParams(p);jbgs_target.register_args(p);args=p.parse_args([]);opt=op.extract(args)
if label!='r23':assert args.jbgs_release_rule=='release' and args.jbgs_release_log=='off'
src=R/'scripts/phd/main_target_v1/unit_r8.py';tree=ast.parse(src.read_text());nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ['setup','steps','environment']]
env=dict(np=np,torch=torch,NS=NS,GaussianModel=GaussianModel,BasicPointCloud=BasicPointCloud,cKDTree=cKDTree,TargetR6=cls,S=S,random=random)
exec(compile(ast.Module(body=nodes,type_ignores=[]),str(src),'exec'),env)
torch.use_deterministic_algorithms(True);torch.manual_seed(0);np.random.seed(0);random.seed(0)
g,c=env['setup'](opt,root/'fixture');c.release_rule='release';c.release_log='on' if label=='r24_on' else 'off'
if label=='r24_on':c.mon=root/'events';c.mon.mkdir();c.initialize_tracking(g)
c.reattach(g,'initial');state=env['environment'](g,c,opt,root/'fixture');seq=env['steps'](state,1,100)
with torch.no_grad():
    g._scaling[:]=np.log(.001);grad=torch.ones((len(g._xyz),1),device='cuda');g.densify_and_clone(grad,.5,1)
    g._scaling[0]=np.log(.05);grad=torch.zeros((len(g._xyz),1),device='cuda');grad[0]=1;g.densify_and_split(grad,.5,1)
meta=c.capture(g);meta.pop('release_state',None)
torch.save(dict(model=g.capture(),meta=meta,sequence=seq),root/'state.pth')
print('PROBE_COMPLETE',label,flush=True)
