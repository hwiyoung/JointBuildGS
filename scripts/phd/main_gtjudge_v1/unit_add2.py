import sys,tempfile,os
os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG',':4096:8')
from types import SimpleNamespace as NS
from common import *
import numpy as np
import torch
import unit_gpu as old
from jbgs_gtjudge import PreserveFreespace,candidate_mask

def main():
    if not (O/'verification/default/r26/state.pth').exists():old.default('r26')
    a=torch.load(O/'verification/default/r25/state.pth',map_location='cpu',weights_only=False)
    b=torch.load(O/'verification/default/r26/state.pth',map_location='cpu',weights_only=False)
    assert old.equal(a,b),'r26 default differs from unchanged r25 100-step receipt'
    old.O=O/'addendum2/unit_primitive';old.D=D/'verification/addendum2'
    old.primitives()
    with tempfile.TemporaryDirectory(dir=O/'tmp') as tmp:
        root=Path(tmp);target=root/'target.npz';patch=root/'patches.npz'
        np.savez(target,patch_id=np.array(['a','b','c']),judge_region=[1,2,4])
        np.savez(patch,patch_id=np.array(['b']))
        ctrl=NS(root=root,mon=root)
        args=NS(jbgs_targets=str(target),jbgs_finaltrain='on',jbgs_freespace_patches=str(patch))
        fs=PreserveFreespace(args,ctrl);assert fs.judge.tolist()==[0,1,0]
        xyz=torch.tensor([[0.,0.,1.],[1.,0.,1.],[2.,0.,1.]])
        mask=candidate_mask(xyz,torch.full((3,),-1),torch.full((1,3),2.),torch.full((1,3),.1),torch.tensor([[0,1,2]]),fs.judge,torch.eye(3,dtype=torch.float64),torch.eye(4,dtype=torch.float64))
        assert mask.tolist()==[False,True,False]
    rec=dict(at=now(),status='PASS',default_100_steps='bit-identical r25 saved fixture and r26 new fixture',seed=0,explicit_patch_pixels_only=True,opacity_only_primitive='PASS',r25_tests_reused=True,scientific_verdict=None)
    dump(O/'verification/unit_r26.json',rec);dump(D/'tables/addendum2/unit_r26.json',rec);print('PASS_R26')
if __name__=='__main__':main()
