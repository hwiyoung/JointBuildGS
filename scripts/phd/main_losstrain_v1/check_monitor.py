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
        j=NS(args=NS(jbgs_lt_monitor=1,jbgs_lt_gradient_from=1,jbgs_lt_gradient_to=1,jbgs_lt_opacity_reset_grace=0),mon=mon)
        g=NS(origin=torch.tensor([1,1]),get_opacity=torch.tensor([.5,.7]),_xyz=xyz)
        if observe:
            ns['lt_observe'](j,1,g,total,rgb,depth,{'viewspace_points':vsp,'visibility_filter':torch.tensor([True,False])},'synthetic')
            assert xyz.grad is None and torch.equal(vsp.grad,torch.full_like(vsp,7.))
        total.backward();return xyz.grad,vsp.grad
    a=make(False);b=make(True);assert all(torch.equal(x,y) for x,y in zip(a,b))
    dest=OUT/'checks/opacity_grace_v1';dest.mkdir(exist_ok=True)
    reference=dest/'synthetic_nojudge.json'
    save(reference,dict(observation_phase='after optimizer and opacity floors, before density/reset',
        medians={'3100':.2},source='synthetic',source_sha256='synthetic'))
    checked=[]
    for reset in [None,3000]:
        for iteration in [3001,3099,3100,3101]:
            for value in [.01,.05,.1,float('nan')]:
                j=NS(args=NS(jbgs_lt_monitor=1,jbgs_lt_opacity_reset_grace=100,
                    jbgs_lt_nojudge_opacity=str(reference)),mon=mon)
                if reset is not None:ns['lt_reset_observed'](j,reset,True)
                g=NS(origin=torch.tensor([1,1]),get_opacity=torch.tensor([value,value]))
                expected=not math.isfinite(value) or (value < .05 and not(reset==3000 and 3001<=iteration<=3099))
                stopped=False
                try:ns['lt_opacity_health'](j,iteration,g,'synthetic','after optimizer and opacity floors, before density/reset')
                except RuntimeError:stopped=True
                assert stopped==expected,(reset,iteration,value,stopped,expected)
                checked.append(dict(reset=reset,iteration=iteration,value=value if math.isfinite(value) else 'NaN',stopped=stopped))
    j=NS(args=NS(jbgs_lt_monitor=1,jbgs_lt_opacity_reset_grace=100),mon=mon,lt_last_periodic_reset=3000)
    stopped=False
    try:ns['lt_observe'](j,3001,g,torch.tensor(float('nan')),None,None,{},'synthetic')
    except RuntimeError:stopped=True
    assert stopped
    save(dest/'monitor_check.json',dict(status='PASS',boundary_cases=checked,nonfinite_loss_during_grace_stops=True,
        parameter_and_retained_gradients_equal=True,observer_optimizer_steps=0,scientific_verdict=None))
    print('observer parameter + retained gradients identical PASS')

if __name__=='__main__':main()
