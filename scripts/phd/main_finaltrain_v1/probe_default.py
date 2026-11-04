"""100 identical-seed optimizer steps on actual GaussianModel/controller APIs."""
import ast,copy,random,sys
from argparse import ArgumentParser
from pathlib import Path
from types import SimpleNamespace as NS
import numpy as np
import torch
from scipy.spatial import cKDTree
sys.path.insert(0,'/source')
from arguments import OptimizationParams
from scene import GaussianModel
from utils.graphics_utils import BasicPointCloud
import jbgs_state as S
import jbgs_target
from jbgs_target_r8 import TargetR8

label=sys.argv[1];root=Path('/out/verification/default')/label
root.mkdir(parents=True,exist_ok=False)
parser=ArgumentParser();op=OptimizationParams(parser);jbgs_target.register_args(parser);args=parser.parse_args([])
assert getattr(args,'jbgs_finaltrain','off')=='off';opt=op.extract(args)
src=Path('/repo/scripts/phd/main_target_v1/unit_r8.py');tree=ast.parse(src.read_text())
nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ['setup','steps','environment']]
env=dict(np=np,torch=torch,NS=NS,GaussianModel=GaussianModel,BasicPointCloud=BasicPointCloud,cKDTree=cKDTree,TargetR6=TargetR8,S=S,random=random)
exec(compile(ast.Module(body=nodes,type_ignores=[]),str(src),'exec'),env)
torch.use_deterministic_algorithms(True);torch.manual_seed(0);np.random.seed(0);random.seed(0)
g,c=env['setup'](opt,root/'fixture');c.reattach(g,'initial');state=env['environment'](g,c,opt,root/'fixture')
sequence=env['steps'](state,1,100)
torch.save(dict(model=g.capture(),meta=c.capture(g),sequence=sequence),root/'state.pth')
print('DEFAULT_100_COMPLETE',label,flush=True)
