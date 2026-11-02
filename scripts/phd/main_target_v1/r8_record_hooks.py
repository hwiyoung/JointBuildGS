"""Recording and stop hooks. The r8 losses, optimization and density rules are unchanged."""
import importlib.util,random,copy,sys,traceback
import numpy as np
import torch
from common import *
from cause_r8_spatial import bins
ROOT=OUT/'r8_recorded_continue'
MODULE=None
BEGIN=None
CONFIG=None
BOUNDARIES=None
PHASE='initialization'

def load_extension():
    global MODULE
    if MODULE is None:
        p=ROOT/'runtime/build/jbgs_r8_record_guard.so'
        spec=importlib.util.spec_from_file_location('jbgs_r8_record_guard',p);MODULE=importlib.util.module_from_spec(spec);spec.loader.exec_module(MODULE)
    return MODULE

def cpu(t):return t.detach().cpu().numpy()

def classification(g):
    xyz=cpu(g._xyz);tag=cpu(g.target_tag).astype('i1');released=cpu(g.target_released_at)
    tag[(tag==2)&(released!=100)]=3
    finite=np.isfinite(xyz).all(1);group=np.full(len(xyz),-1,'i4')
    if finite.any():
        x,h=bins(xyz[finite],BOUNDARIES);group[finite]=tag[finite].astype('i4')*16+x*4+h
    return group,np.bincount(group[group>=0],minlength=64).astype('i8'),int((~finite).sum())

def memory():
    free,total=torch.cuda.mem_get_info()
    return dict(allocated_bytes=torch.cuda.memory_allocated(),reserved_bytes=torch.cuda.memory_reserved(),
        peak_allocated_bytes=torch.cuda.max_memory_allocated(),peak_reserved_bytes=torch.cuda.max_memory_reserved(),free_bytes=free,total_bytes=total)

def append(path,row):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a') as f:f.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n')

def begin_iteration(env):
    global BEGIN,PHASE
    PHASE='before_training_forward'
    # Only small control/RNG values are copied; no parameter or optimizer updates.
    BEGIN=dict(iteration=env['iteration']-1,active_sh_degree=env['gaussians'].active_sh_degree,
        lr=[p['lr'] for p in env['gaussians'].optimizer.param_groups],
        target_iteration=env['target_control'].iteration,
        viewpoint_stack=None if env['viewpoint_stack'] is None else [c.image_name for c in env['viewpoint_stack']],
        rng=dict(python=random.getstate(),numpy=np.random.get_state(),torch_cpu=torch.get_rng_state(),torch_cuda=torch.cuda.get_rng_state_all()))

def training_render(env,render,cam,g,pipe,bg):
    global PHASE
    PHASE='training_forward_before_optimizer'
    sample=env['iteration']%100==0
    if sample:group,counts,invalid=classification(g)
    pkg=render(cam,g,pipe,bg)
    if sample:
        stats=MODULE.jbgs_get_guard();assert stats[0]==len(g._xyz) and not stats[5]
        # Exact per-Gaussian tiles are exposed by the unchanged forward geometry tuple.
        from r8_record_proxy import observer
        tiles=observer.last_tiles
        assert tiles is not None and int(tiles.astype('i8').sum())==stats[1]
        grouped=np.bincount(group[group>=0],weights=tiles[group>=0],minlength=64).astype('i8')
        row=dict(at=stamp(),iteration=env['iteration'],phase='pre_optimizer_training_forward',camera=cam.image_name,gaussians=len(g._xyz),
            counts=counts.reshape(4,4,4).tolist(),invalid_position_count=invalid,overlaps=stats[1],overlaps_by_cell=grouped.reshape(4,4,4).tolist(),
            binning_bytes=stats[2],free_bytes_before_binning=stats[3],total_gpu_bytes=stats[4],guard_limit_bytes=stats[3]*.5,
            gpu=memory(),scientific_verdict=None)
        append(Path(env['args'].model_path)/'recording/forward_100.jsonl',row)
        observer.last_tiles=None
    PHASE='after_training_forward'
    return pkg

@torch.no_grad()
def save_gradient(g,iteration,stage):
    path=Path(CONFIG['model'])
    dest=path/'recording/pre_densification'/f'iteration_{iteration}';dest.mkdir(parents=True,exist_ok=False)
    accum=cpu(g.xyz_gradient_accum);denom=cpu(g.denom)
    with np.errstate(divide='ignore',invalid='ignore'):norm=accum/denom
    norm[np.isnan(norm)]=0
    np.savez_compressed(dest/'gradient.npz',xyz=cpu(g._xyz),init_id=cpu(g.init_id),target_tag=cpu(g.target_tag),target_released_at=cpu(g.target_released_at),
        accum=accum,denom=denom,normalized=norm,above=norm>=CONFIG['densify_grad_threshold'],scale=cpu(g._scaling),opacity=cpu(g._opacity))
    dump(dest/'receipt.json',dict(at=stamp(),iteration=iteration,phase=stage,gaussians=len(g._xyz),threshold=CONFIG['densify_grad_threshold'],
        gradient_sha256=sha(dest/'gradient.npz'),accum_nonzero=int(np.count_nonzero(accum)),denom_positive=int((denom>0).sum()),scientific_verdict=None))

def install(config):
    global CONFIG,BOUNDARIES
    CONFIG=config;BOUNDARIES=json.loads(Path(config['boundaries']).read_text())
    import diff_surfel_rasterization as raster
    from r8_record_proxy import Observer
    import r8_record_proxy
    mod=load_extension();mod.jbgs_set_guard(.5);r8_record_proxy.observer=Observer(mod);raster._C=r8_record_proxy.observer
    from scene import GaussianModel
    from jbgs_target_r8 import TargetR8
    original_densify=GaussianModel.densify_and_prune
    def densify(g,*a,**kw):
        iteration=g.target_r6.iteration
        if 8000<=iteration<=14000 and iteration%1000==0:save_gradient(g,iteration,'after_current_gradient_accumulation_immediately_before_densification')
        return original_densify(g,*a,**kw)
    GaussianModel.densify_and_prune=densify
    original_snapshot=TargetR8.snapshot
    def snapshot(self,iteration,g):
        result=original_snapshot(self,iteration,g)
        if iteration in [15000,30000]:save_gradient(g,iteration,'snapshot_time_no_densification_scheduled')
        return result
    TargetR8.snapshot=snapshot
    original_evidence=TargetR8.checkpoint_evidence
    def evidence(self,iteration,*a,**kw):
        global PHASE
        PHASE='scheduled_checkpoint_readout'
        if iteration in config['additional_readout_suppressed']:return None
        return original_evidence(self,iteration,*a,**kw)
    TargetR8.checkpoint_evidence=evidence
    original_observe=TargetR8.observe
    def observe(self,iteration,g,*a,**kw):
        global PHASE
        PHASE='after_iteration_health'
        if iteration%100==0:
            group,counts,invalid=classification(g)
            append(Path(config['model'])/'recording/after_iteration_100.jsonl',dict(at=stamp(),iteration=iteration,phase='after_iteration',gaussians=len(g._xyz),
                counts=counts.reshape(4,4,4).tolist(),invalid_position_count=invalid,gpu=memory(),scientific_verdict=None))
        return original_observe(self,iteration,g,*a,**kw)
    TargetR8.observe=observe
    # Preserve the inherited comparison-only compatibility for equal NaN defaults.
    import math,jbgs_target_r6
    original_restore=jbgs_target_r6.restore_complete
    def restore(path,state,env):
        keys=[k for k,v in state['args'].items() if isinstance(v,float) and isinstance(getattr(env['args'],k),float) and math.isnan(v) and math.isnan(getattr(env['args'],k))]
        assert set(keys)<=set(['jbgs_tau_v','jbgs_tau_roof','jbgs_tau_wall'])
        view=dict(state);view['args']={k:v for k,v in state['args'].items() if k not in keys}
        result=original_restore(path,view,env)
        dump(Path(config['model'])/'recording/restore_comparison.json',dict(equal_unspecified_keys=keys,original_checkpoint_sha256=sha(path),scientific_verdict=None))
        return result
    jbgs_target_r6.restore_complete=restore

def save_stop(error,tb):
    import jbgs_state
    frames=[]
    while tb is not None:frames.append(tb.tb_frame);tb=tb.tb_next
    frame=next((f for f in reversed(frames) if f.f_code.co_name=='training' and 'gaussians' in f.f_locals),None)
    if frame is None:return False
    env=frame.f_locals;g=env['gaussians'];it=env['iteration'];dest=Path(CONFIG['model'])/'recording/stop'/f'iteration_{it}';dest.mkdir(parents=True,exist_ok=False)
    guard='JBGS_BINNING_GUARD_STOP' in str(error);stats=MODULE.jbgs_get_guard() if MODULE else None
    state=jbgs_state.capture_state(env)
    resumable=PHASE in ['training_forward_before_optimizer','after_iteration_health']
    if PHASE=='training_forward_before_optimizer':
        state['iteration']=BEGIN['iteration'];state['rng']=BEGIN['rng'];state['viewpoint_stack']=BEGIN['viewpoint_stack']
        model=list(state['model']);model[0]=BEGIN['active_sh_degree']
        for group,lr in zip(model[10]['param_groups'],BEGIN['lr']):group['lr']=lr
        state['model']=tuple(model);state['target_r6']['iteration']=BEGIN['target_iteration']
    state['recording_stop']=dict(attempted_iteration=it,phase=PHASE,ordinary_resume_ready=resumable,
        restore_boundary='before attempted iteration with camera/RNG/LR/SH restored' if PHASE=='training_forward_before_optimizer' else PHASE,
        guard=guard,scientific_verdict=None)
    torch.save(state,dest/'checkpoint.pth');g.save_ply(str(dest/'point_cloud.ply'))
    from jbgs_target_r6 import TargetR6
    old=env['target_control'].mon;env['target_control'].mon=dest
    try:TargetR6.snapshot(env['target_control'],it,g)
    finally:env['target_control'].mon=old
    np.savez_compressed(dest/'gradient.npz',xyz=cpu(g._xyz),init_id=cpu(g.init_id),accum=cpu(g.xyz_gradient_accum),denom=cpu(g.denom),target_tag=cpu(g.target_tag),target_released_at=cpu(g.target_released_at))
    if guard:
        tiles=MODULE.jbgs_get_guard_tiles().numpy();assert int(tiles.astype('i8').sum())==stats[1]
        np.savez_compressed(dest/'guard_tiles.npz',tiles=tiles)
    receipt=dict(at=stamp(),status='STOPPED_BUFFER_GUARD' if guard else 'STOPPED_HEALTH_OR_EXECUTION',attempted_iteration=it,completed_iteration=state['iteration'],phase=PHASE,
        camera=env.get('cam_name'),gaussians=len(g._xyz),guard_stats=stats,ordinary_resume_ready=resumable,error=str(error),automatic_retry=False,
        checkpoint_sha256=sha(dest/'checkpoint.pth'),ply_sha256=sha(dest/'point_cloud.ply'),scientific_verdict=None)
    dump(dest/'receipt.json',receipt);dump(ROOT/'STOP_LoD2.json',dict(receipt,stop_dir=str(dest)))
    print('R8_RECORDED_STOP_SAVED',json.dumps(receipt),flush=True);return True
