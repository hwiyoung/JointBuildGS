"""New addendum-only schedule and prune bookkeeping checks; old units reused."""
import sys,tempfile
from types import SimpleNamespace
import numpy as np
import torch
from common import *
sys.path.insert(0,'/source')
from jbgs_gtjudge import PreserveFreespace

class G:
    def __init__(self,n):
        self._xyz=torch.tensor([[0.,0.,1.]]*n)
        self._opacity=torch.full((n,1),-1.,requires_grad=True)
        self.target_tag=torch.zeros(n,dtype=torch.long)
        self.target_index=torch.zeros(n,dtype=torch.long)
    @property
    def get_opacity(self):return self._opacity.sigmoid()

def main():
    with tempfile.TemporaryDirectory(dir=O/'tmp') as tmp:
        root=Path(tmp);target=root/'target.npz';np.savez(target,judge_region=[1])
        control=SimpleNamespace(root=root,mon=root,valid_patch=np.array([0]),
            maps={'view':dict(depth=torch.tensor([[2.]]),sigma=torch.tensor([[.1]]),owner=torch.tensor([[0]]))},
            index={'views':{'view':dict(K=np.eye(3).tolist(),W2C=np.eye(4).tolist())}})
        args=SimpleNamespace(jbgs_targets=str(target),jbgs_finaltrain='on')
        g=G(100);fs=PreserveFreespace(args,control)
        def loss(i):return fs.loss(i,g,g.get_opacity.sum()*2,'view')
        assert float(loss(499))==0 and fs.weight is None
        loss(500);assert fs.calibration_iteration==500 and abs(fs.weight-200)<1e-5
        loss(600);assert fs.weight==200
        g=G(99);fs=PreserveFreespace(args,control)
        assert float(loss(500))==0 and fs.weight is None
        fs.extend(1,'cpu');g=G(100);assert float(loss(600))==0 and fs.weight is None
        fs.extend(1,'cpu');g=G(101);loss(700)
        assert fs.calibration_iteration==700 and abs(fs.weight-202)<1e-5
        fs.iteration=799;mask=torch.zeros(101,dtype=torch.bool);mask[:3]=True
        opacity=mask.clone();opacity[2]=False
        fs.before_prune(mask,opacity);assert fs.pruned_recent==2 and len(fs.last_targeted)==98
        fs.extend(2,'cpu');assert len(fs.last_targeted)==100 and (fs.last_targeted[-2:]==-100000).all()
        fs.iteration=800;mask=torch.ones(100,dtype=torch.bool)
        fs.before_prune(mask,mask);assert fs.pruned_recent==2
    rec=dict(at=now(),status='PASS',calibration_at_500_with_100=True,deferred_until_over_100=True,
        fixed_after_calibration=True,opacity_prune_recent_window=100,old_passed_units_repeated=False,scientific_verdict=None)
    dump(O/'verification/unit_fs_schedule.json',rec);dump(D/'tables/unit_fs_schedule.json',rec);print('PASS_NEW_FS_SCHEDULE_AND_PRUNE')
if __name__=='__main__':main()
