"""Docker CPU: boundary stops and density bookkeeping without optimizer changes."""
import json,math
from pathlib import Path
from types import SimpleNamespace as NS
import numpy as np
import torch
from inputs import OUT,save

def main():
    ns=dict(json=json,math=math,np=np,torch=torch,ORIGIN_PRIOR=1)
    exec(Path('/repo/scripts/phd/main_losstrain_v1/r17_monitor.py').read_text(),ns)
    checks=[]
    for offset in [None,1,99,100,101,500]:
        for value in [.01,.05,.5]:
            actual=ns['lt_whole_stop'](True,value,offset)
            assert bool(actual)==(offset is not None and offset>=100 and value<.05)
            checks.append(dict(offset=offset,median=value,stop=actual))
        assert ns['lt_whole_stop'](False,None,offset)=='nonfinite opacity'
    ref={7000:20.,15000:23.,30000:25.}
    for it in [1000,3100,7000,15000,30000]:
        for delta in [2.99,3.,3.0001]:
            value=ref.get(it,20.)-delta
            assert bool(ns['lt_psnr_stop'](it,value,ref))==(it in ref and delta>3.)
        assert ns['lt_psnr_stop'](it,float('nan'),ref)
    class G:
        def __init__(self):self.get_xyz=torch.arange(9).reshape(3,3).float()
        def densification_postfix(self,xyz):self.get_xyz=torch.cat([self.get_xyz,xyz]);return 'postfix'
        def prune_points(self,mask):self.get_xyz=self.get_xyz[~mask];return 'prune'
    a,b=G(),G();j=NS();ns['lt_track_birth'](j,b)
    xyz=torch.tensor([[9.,10.,11.],[12.,13.,14.]])
    assert a.densification_postfix(xyz)==b.densification_postfix(xyz)
    assert j.lt_initial_survivor.tolist()==[True,True,True,False,False]
    mask=torch.tensor([False,True,False,False,True])
    assert a.prune_points(mask)==b.prune_points(mask)
    assert torch.equal(a.get_xyz,b.get_xyz) and j.lt_initial_survivor.tolist()==[True,True,False]
    summary=ns['lt_population_summary'](np.array([.001,.8,.9]),np.array([1,0,0]),np.array([0,1,1]),np.array([1,6]),j.lt_initial_survivor)
    assert summary['prior_lineage']['opacity_median']==.001 and summary['all']['opacity_median']==.8
    assert ns['lt_whole_stop'](True,summary['all']['opacity_median'],100) is None
    assert summary['prior_gt_incorrect']['count']==1 and summary['density_born']['count']==1
    mon=OUT/'checks/monitor_v2/synthetic';mon.mkdir(parents=True,exist_ok=True)
    grads=[]
    for observe in [False,True]:
        xyz=torch.tensor([[.1,.2,.3],[.4,.5,.6]],requires_grad=True)
        vsp=xyz*2;vsp.retain_grad();vsp.grad=torch.full_like(vsp,7.)
        rgb=vsp.square().sum();depth=xyz.sin().sum()
        j=NS(mon=mon,args=NS(jbgs_lt_monitor=1,jbgs_lt_monitor_v2=1,jbgs_lt_opacity_reset_grace=100,
            jbgs_lt_gradient_from=1,jbgs_lt_gradient_to=1))
        g=NS(_xyz=xyz,get_opacity=torch.tensor([.001,.7]),origin=torch.tensor([1,0]))
        if observe:
            ns['lt_observe'](j,1,g,rgb+depth,rgb,depth,dict(viewspace_points=vsp,visibility_filter=torch.tensor([True,False])),'synthetic')
            assert xyz.grad is None and torch.equal(vsp.grad,torch.full_like(vsp,7.))
        (rgb+depth).backward();grads.append((xyz.grad,vsp.grad))
    assert all(torch.equal(x,y) for x,y in zip(*grads))
    save(OUT/'checks/monitor_v2/monitor_check.json',dict(status='PASS',opacity_boundary_cases=checks,
        psnr_strict_boundary_and_exact_iteration=True,birth_wrapper_delegation_identical=True,
        clone_split_prune_birth_alignment=True,prior_low_whole_high_does_not_stop=True,
        parameter_and_retained_gradients_equal=True,optimizer_steps=0,scientific_verdict=None))
    print('monitor v2 CPU boundaries, density bookkeeping and unchanged gradients PASS')

if __name__=='__main__':main()
