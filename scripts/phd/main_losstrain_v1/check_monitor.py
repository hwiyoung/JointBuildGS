"""Observer cannot change parameter/retained gradients; CPU check in Docker."""
import json
import math
from pathlib import Path
from types import SimpleNamespace as NS
import torch
from inputs import OUT,save

def main():
    ns={'torch':torch,'json':json,'math':math,'ORIGIN_PRIOR':1}
    exec(Path('/repo/scripts/phd/main_losstrain_v1/r17_monitor.py').read_text(),ns)
    mon=OUT/'checks/direct_stage1/monitor_test';mon.mkdir(parents=True,exist_ok=True)
    def make(observe):
        xyz=torch.tensor([[.1,.2,.3],[.4,.5,.6]],requires_grad=True)
        vsp=xyz*2;vsp.retain_grad();vsp.grad=torch.full_like(vsp,7.)
        rgb=vsp.square().sum();depth=xyz.sin().sum();total=rgb+depth
        j=NS(args=NS(jbgs_lt_monitor=1,jbgs_lt_gradient_from=1,jbgs_lt_gradient_to=1),mon=mon)
        g=NS(origin=torch.tensor([1,1]),get_opacity=torch.tensor([.5,.7]),_xyz=xyz)
        if observe:
            ns['lt_observe'](j,1,g,total,rgb,depth,{'viewspace_points':vsp,'visibility_filter':torch.tensor([True,False])},'synthetic')
            assert xyz.grad is None and torch.equal(vsp.grad,torch.full_like(vsp,7.))
        total.backward();return xyz.grad,vsp.grad
    a=make(False);b=make(True);assert all(torch.equal(x,y) for x,y in zip(a,b))
    save(OUT/'checks/direct_stage1/monitor_check.json',dict(status='PASS',
        parameter_and_retained_gradients_equal=True,observer_optimizer_steps=0,scientific_verdict=None))
    print('observer parameter + retained gradients identical PASS')

if __name__=='__main__':main()
