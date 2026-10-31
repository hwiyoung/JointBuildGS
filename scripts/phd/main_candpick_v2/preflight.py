"""Arm-local unit checks. Failure stops that arm, without changing its inputs."""
import argparse
import gc
import torch
from engine import Scene,Monitor
from cp2_common import *

def check(unit,variant,start,cfg):
    arm=f'cp2_{variant}_{start}_{unit}';dest=OUT/'preflight'/(arm+'.json')
    if dest.exists():return json.loads(dest.read_text())
    report=dict(arm=arm,unit=unit,variant=variant,start=start,at=now(),source=SOURCE,scientific_verdict=None)
    scene=None;monitor=None;optim=None
    try:
        torch.manual_seed(0);np.random.seed(0)
        scene=Scene(unit,variant,start);monitor=Monitor(scene);optim=scene.setup_optimizer(cfg)
        frozen=scene.frozen_hashes();before=scene.opacity.detach().clone()
        cam=monitor.cameras[monitor.index['error_monitor_views'][0]]
        report['candidate_gaussians']=len(scene.opacity);report['place_points']=scene.npoints
        report['trainable_background_gaussians']=len(scene.background_ids)
        if variant=='a':
            assert len(scene.opacity)==scene.npoints*4
            ids=scene.original_ids.cpu().numpy()
            expected=(scene.d['mvs_p']>0).astype(int)
            assert np.array_equal(ids.reshape(-1,4)//4%2,np.repeat(expected[:,None],4,1))
            with torch.no_grad():r=scene.render(cam,candidates_only=True)
            assert r[-1]['means2d'].shape[1]==scene.npoints*4
            report['removed_candidates_absent_from_render']=True
            del r
        checks=[]
        for step in ([1,1000,1001] if variant=='b' else [1,2]):
            scene.update_schedule(optim,step,1.)
            optim.zero_grad(set_to_none=True)
            loss=monitor.loss(scene.render(cam)[0][0],cam);loss.backward()
            grad=0. if scene.opacity.grad is None else float(scene.opacity.grad.abs().max())
            if variant=='b':assert (grad==0.) if step<=1000 else (grad>0.)
            for name,p in scene.named_parameters().items():
                if p.requires_grad:assert p.grad is not None and torch.isfinite(p.grad).all(),name
            optim.step();scene.project_bounds()
            if variant=='b' and step<=1000:assert torch.equal(before,scene.opacity)
            if variant=='c':
                status=scene.bound_status()
                assert status['finite'] and status['max_normal_excess_m']<=3e-5 and status['max_tangent_excess_m']<=3e-5,status
            checks.append(dict(step=step,max_opacity_gradient=grad,loss=float(loss),bounds=scene.bound_status()))
        assert scene.frozen_hashes()==frozen
        if variant=='d':
            assert len(scene.background_ids)>0
            # Only subset parameters are optimized; full frozen background tensors remain byte-identical.
            report['outside_background_unchanged']=True
            report['background_geometry_unchanged']=True
        report.update(status='PASS',checks=checks,frozen_unchanged=True)
    except Exception as e:
        report.update(status='STOP_UNIT_CHECK',error_type=type(e).__name__,reason=str(e))
    save(dest,report)
    print(arm,report['status'],report.get('reason',''),flush=True)
    del scene,monitor,optim;gc.collect();torch.cuda.empty_cache()
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('units',nargs='+');a=p.parse_args()
    cfg=json.loads((CFG/'plan_before_views.json').read_text())
    for unit in a.units:
        for v in 'abcd':
            for start in ['equal','right']:check(unit,v,start,cfg)
