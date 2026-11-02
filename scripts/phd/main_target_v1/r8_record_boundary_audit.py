"""CPU-only verification of the interrupted forward's resumable checkpoint boundary."""
import random
import torch
from common import *
def main():
    root=OUT/'r8_recorded_continue';stop=json.loads((root/'STOP_LoD2.json').read_text());cp=Path(stop['stop_dir'])/'checkpoint.pth'
    dest=root/'verification/stop_boundary';dest.mkdir(exist_ok=False)
    dump(dest/'lock.json',dict(at=stamp(),script_sha256=sha(__file__),checkpoint_sha256=sha(cp),scientific_verdict=None))
    state=torch.load(cp,map_location='cpu');m=state['model'];n=len(m[1]);assert n==stop['gaussians'];assert state['iteration']==14030
    assert stop['phase']=='training_forward_before_optimizer' and state['recording_stop']['ordinary_resume_ready']
    rng=random.Random();rng.setstate(state['rng']['python']);stack=state['viewpoint_stack'] or state['train_order'];next_camera=stack[rng.randint(0,len(stack)-1)]
    assert next_camera==stop['camera'],(next_camera,stop['camera'])
    assert state['target_r6']['iteration']==state['iteration']
    model_checks=[]
    for i,name in [(1,'xyz'),(2,'features_dc'),(3,'features_rest'),(4,'scaling'),(5,'rotation'),(6,'opacity'),(7,'max_radii'),(8,'gradient_accum'),(9,'denom')]:
        assert len(m[i])==n and torch.isfinite(m[i]).all(),name
        model_checks.append(dict(name=name,shape=list(m[i].shape),finite=True))
    optimizer=[]
    for group in m[10]['param_groups']:
        s=m[10]['state'][group['params'][0]]
        assert s['exp_avg'].shape[0]==n and s['exp_avg_sq'].shape[0]==n
        assert torch.isfinite(s['exp_avg']).all() and torch.isfinite(s['exp_avg_sq']).all()
        optimizer.append(dict(name=group['name'],lr=group['lr'],shape=list(s['exp_avg'].shape),step=float(s['step']),finite=True))
    result=dict(at=stamp(),status='PASS_COMPLETE_BEFORE_ATTEMPT_BOUNDARY',completed_iteration=state['iteration'],attempted_iteration=stop['attempted_iteration'],
        next_camera_from_saved_rng_and_stack=next_camera,failed_camera_replayed=True,gaussians=n,model_checks=model_checks,optimizer=optimizer,optimization_steps=0,scientific_verdict=None)
    dump(dest/'result.json',result);print('PASS_STOP_BOUNDARY',next_camera,n,flush=True)
if __name__=='__main__':main()
