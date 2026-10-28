"""Bounded CPU check that observer delegates unchanged and records save-state birth."""
import ast
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import torch
from common import *
source=Path(__file__).with_name('replay_observer.py')
nodes=[x for x in ast.parse(source.read_text()).body if isinstance(x,ast.FunctionDef)]
calls=[]
class G:
    def __init__(self):self.get_xyz=np.zeros((2,3));self.origin=torch.tensor([0,1])
    def densification_postfix(self,amount):
        calls.append(('post',amount));self.get_xyz=np.r_[self.get_xyz,np.ones((amount,3))];self.origin=torch.cat([self.origin,torch.zeros(amount,dtype=torch.long)]);return 'post-return'
    def prune_points(self,mask):
        calls.append(('prune',mask.tolist()));self.get_xyz=self.get_xyz[~mask.numpy()];self.origin=self.origin[~mask];return 'prune-return'
    def save_ply(self,path):calls.append(('save',str(path)));Path(path).write_bytes(b'exact-test');return 'save-return'
def original_track(j,g):
    j.lt_initial_survivor=np.ones(len(g.get_xyz),bool);post,cut=g.densification_postfix,g.prune_points
    def p(n):
        ret=post(n);j.lt_initial_survivor=np.r_[j.lt_initial_survivor,np.zeros(n,bool)];return ret
    def c(m):
        ret=cut(m);j.lt_initial_survivor=j.lt_initial_survivor[~m.numpy()];return ret
    g.densification_postfix,g.prune_points=p,c
def original_step(j,iteration,*args,**kw):calls.append(('step',iteration));return 'step-return'
exec(compile(ast.Module(body=nodes,type_ignores=[]),str(source),'exec'))
root=OUT/'checks/replay_observer';root.mkdir(parents=True,exist_ok=False)
g=G();j=SimpleNamespace();torch_rng=torch.get_rng_state().clone();np_rng=np.random.get_state()
track(j,g);assert step(j,500)=='step-return';assert g.densification_postfix(2)=='post-return'
assert step(j,600)=='step-return';assert g.prune_points(torch.tensor([False,True,False,False]))=='prune-return'
assert g.save_ply(root/'point_cloud.ply')=='save-return'
with np.load(root/'floatdiag_birth.npz') as f:
    assert np.array_equal(f['birth_iteration'],[0,500,500]);assert np.array_equal(f['initial_survivor'],[True,False,False])
assert torch.equal(torch_rng,torch.get_rng_state());assert all(np.array_equal(a,b) for a,b in zip(np_rng,np.random.get_state()))
save(DOC/'provenance/replay_observer_check.json',dict(at=now(),status='PASS',source_sha256=sha(source),calls=calls,
    unchanged_returns=True,unchanged_RNG=True,exact_saved_population=True,scientific_verdict=None))
print('birth observer delegation and save-state alignment PASS')
