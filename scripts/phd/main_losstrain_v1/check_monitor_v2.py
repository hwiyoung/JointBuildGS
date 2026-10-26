"""Docker CPU: boundary stops and density bookkeeping without optimizer changes."""
import argparse,json,math
from pathlib import Path
from types import SimpleNamespace as NS
import numpy as np
import torch
from inputs import OUT,save

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--revision');a=ap.parse_args()
    root=OUT/'checks/monitor_v2';root=root/a.revision if a.revision else root
    root.mkdir(parents=True,exist_ok=True)
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
    mon=root/'synthetic';mon.mkdir(parents=True,exist_ok=True)
    init_xyz=np.array([[0.,0.,0.],[1.,0.,0.]],dtype=np.float32)
    np.savez_compressed(mon/'init_points.npz',planted=np.ones(2,bool),xyz=init_xyz,location=np.array([0,1]))
    np.savez_compressed(mon/'evaluation.npz',cell=np.array([0,1]))
    cams=[NS(image_name='view_'+str(i)) for i in range(30)]
    save(mon/'baseline.json',dict(legacy5_camera_names=sorted(cams[i].image_name for i in range(5,30,5)),
        train_psnr_legacy5=[dict(iteration=i,psnr_db=20.) for i in [7000,15000,30000]]))
    j=NS(mon=mon,init_xyz=torch.from_numpy(init_xyz),lt_cameras={'existing_loss_camera':'do not replace'},
        args=NS(jbgs_lt_diagnostic_cells=str(mon/'evaluation.npz'),jbgs_lt_nojudge_inventory=str(mon/'baseline.json')))
    existing=j.__dict__.copy();g=G();g.get_xyz=torch.from_numpy(init_xyz)
    ns['lt_monitor_initialize'](j,g,NS(getTrainCameras=lambda:cams))
    assert all(j.__dict__[key] is value for key,value in existing.items())
    j.lt_last_periodic_reset=3000
    g.origin=torch.tensor([1,0]);g.init_id=torch.tensor([0,1]);g.get_opacity=torch.tensor([.01,.01])
    original_psnr=ns['lt_five_psnr'];ns['lt_five_psnr']=lambda *args:(19.,[])
    stopped=False
    try:ns['lt_monitor_step'](j,3100,g,'synthetic',None,None,None)
    except RuntimeError:stopped=True
    assert stopped
    row=json.loads((mon/'losstrain_observations_v2.jsonl').read_text().splitlines()[-1])
    assert row['groups']['all']['count']==2 and row['stop'].startswith('whole-population')
    ns['lt_five_psnr']=original_psnr
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
    save(root/'monitor_check.json',dict(status='PASS',opacity_boundary_cases=checks,
        preexisting_judgment_attributes_unchanged=True,collapse_observation_written_before_stop=True,
        psnr_strict_boundary_and_exact_iteration=True,birth_wrapper_delegation_identical=True,
        clone_split_prune_birth_alignment=True,prior_low_whole_high_does_not_stop=True,
        parameter_and_retained_gradients_equal=True,optimizer_steps=0,scientific_verdict=None))
    print('monitor v2 CPU boundaries, density bookkeeping and unchanged gradients PASS')

if __name__=='__main__':main()
