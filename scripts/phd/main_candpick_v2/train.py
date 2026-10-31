"""Frozen-config training queue; each arm has its own completion/failure receipt."""
import argparse
import gc
import os
import time
import torch
from engine import Scene,Monitor
from cp2_common import *

def run(unit,variant,start):
    cfg=config();digest=sha(CFG/'candpick_v2.json');arm=f'cp2_{variant}_{start}_{unit}'
    root=OUT/'runs'/arm;root.mkdir(parents=True,exist_ok=True)
    gate=json.loads((OUT/'preflight'/(arm+'.json')).read_text())
    if gate['status']!='PASS':
        if not (root/'stopped.json').exists():save(root/'stopped.json',dict(arm=arm,status='STOP_UNIT_CHECK',reason=gate.get('reason'),at=now(),scientific_verdict=None))
        print(arm,'STOP_UNIT_CHECK',flush=True);return
    if (root/'complete.json').exists():
        assert json.loads((root/'complete.json').read_text())['config_sha256']==digest
        print(arm,'already complete',flush=True);return
    for p,h in cfg['training_implementation_sha256'].items():assert sha(p)==h,p
    torch.manual_seed(0);np.random.seed(0);scene=None;monitor=None;optimizer=None
    begin=time.monotonic();receipt=dict(arm=arm,unit=unit,variant=variant,start=start,at=now(),config_sha256=digest,
        commit=os.environ.get('CANDPICK_COMMIT'),docker_image=os.environ.get('CANDPICK_IMAGE'),source=SOURCE,scientific_verdict=None)
    try:
        scene=Scene(unit,variant,start);monitor=Monitor(scene);optimizer=scene.setup_optimizer(cfg)
        frozen=scene.frozen_hashes();first=0;elapsed=0.;resume=root/'resume.pt'
        if resume.exists():
            state=torch.load(resume,map_location='cpu',weights_only=False)
            assert state['config_sha256']==digest and state['frozen']==frozen
            with torch.no_grad():
                for k,p in scene.named_parameters().items():p.copy_(state['parameters'][k])
            optimizer.load_state_dict(state['optimizer']);first=state['iteration'];elapsed=state['elapsed_seconds']
            torch.set_rng_state(state['torch_rng']);torch.cuda.set_rng_state(state['cuda_rng'])
            del state
            logs=[json.loads(x) for x in (root/'metrics.jsonl').read_text().splitlines()]
            (root/'metrics.jsonl').write_text(''.join(json.dumps(x,allow_nan=False)+'\n' for x in logs if x['iteration']<=first))
        save(root/('attempt_'+now().replace(':','-')+'.json'),dict(**receipt,resumed_from=first))
        def checkpoint(step):
            state=dict(iteration=step,parameters={k:p.detach().cpu() for k,p in scene.named_parameters().items()},
                optimizer=optimizer.state_dict(),torch_rng=torch.get_rng_state(),cuda_rng=torch.cuda.get_rng_state(),
                frozen=frozen,config_sha256=digest,elapsed_seconds=elapsed+time.monotonic()-begin)
            torch.save(state,root/'resume.tmp.pt');os.replace(root/'resume.tmp.pt',resume)
        def log(step):
            r=dict(iteration=step,at=now(),opacity=monitor.opacity(),photo_error=monitor.errors(),
                elapsed_seconds=elapsed+time.monotonic()-begin,peak_gpu_bytes=torch.cuda.max_memory_allocated(),bounds=scene.bound_status())
            with (root/'metrics.jsonl').open('a') as f:f.write(json.dumps(clean(r),allow_nan=False)+'\n');f.flush();os.fsync(f.fileno())
            save(root/'progress.json',dict(**receipt,status='RUNNING',iteration=step,elapsed_seconds=r['elapsed_seconds']),replace=True)
            print(arm,step,'L1',r['photo_error']['candidate_l1'],flush=True)
        end=cfg['arms'][variant]['iterations']
        if first==0 and not resume.exists():
            save(root/'photo_error_0.json',monitor.errors(all_views=True))
            scene.snapshot(root/'candidate_0.npz',0);log(0);checkpoint(0)
        for step in range(first+1,end+1):
            scene.update_schedule(optimizer,step,cfg['units'][unit]['spatial_lr_scale'])
            optimizer.zero_grad(set_to_none=True)
            cam=monitor.cameras[cfg['units'][unit]['camera_sequence'][step-1]]
            loss=monitor.loss(scene.render(cam)[0][0],cam)
            assert torch.isfinite(loss),f'nonfinite loss at {step}'
            loss.backward()
            for name,p in scene.named_parameters().items():
                if p.requires_grad:assert p.grad is not None and torch.isfinite(p.grad).all(),f'bad gradient {name} at {step}'
            optimizer.step();scene.project_bounds()
            assert all(torch.isfinite(p).all() for p in scene.named_parameters().values()),f'nonfinite parameters {step}'
            if variant=='c':
                b=scene.bound_status();assert b['finite'] and b['max_normal_excess_m']<=3e-5 and b['max_tangent_excess_m']<=3e-5,b
            if step in [500,1000,end]:scene.snapshot(root/f'candidate_{step}.npz',step)
            if step%100==0:log(step)
            if step%500==0:checkpoint(step)
            del loss
        after=scene.frozen_hashes();assert after==frozen,'frozen values changed'
        save(root/f'photo_error_{end}.json',monitor.errors(all_views=True))
        if variant=='c':
            delta=scene.extra['means'].detach()-scene.origin
            normal=((delta*scene.axes[2]).sum(1)-scene.heights).cpu().numpy()
            np.savez_compressed(root/'normal_displacement.npz',normal_displacement_m=normal.reshape(-1,2,4),point_id=scene.d['point_id'])
        save(root/'complete.json',dict(**receipt,status='COMPLETE',finished_at=now(),iterations=end,
            elapsed_seconds=elapsed+time.monotonic()-begin,frozen_before=frozen,frozen_after=after,frozen_unchanged=True,
            final_candidate_sha256=sha(root/f'candidate_{end}.npz'),trainable_background_gaussians=len(scene.background_ids),
            truth_used_in_loss=False,depth_loss_used=False,densification=False,opacity_reset=False,opacity_prune=False))
        print(arm,'COMPLETE',round(elapsed+time.monotonic()-begin,1),'seconds',flush=True)
    except BaseException as e:
        save(root/('failure_'+now().replace(':','-')+'.json'),dict(**receipt,status='FAILED',error_type=type(e).__name__,reason=str(e)))
        print(arm,'FAILED',repr(e),flush=True)
        if isinstance(e,(KeyboardInterrupt,SystemExit)):raise
    finally:
        del scene,monitor,optimizer;gc.collect();torch.cuda.empty_cache()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('lane',type=int,choices=[0,1]);a=p.parse_args()
    jobs=[(u,v,s) for v in 'abcd' for u in UNITS for s in ['equal','right']]
    for u,v,s in jobs[a.lane::2]:run(u,v,s)
