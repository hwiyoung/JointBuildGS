"""Read-only instrumentation around the frozen GeoGS training implementation."""
import json,os,runpy,sys,time
from pathlib import Path
sys.path.insert(0,'/source')
import torch
import jbgs_state
import intervention
if os.environ.get('JBGS_MEMORY_RASTER')=='1':
    import memory_raster
    memory_raster.install()
if os.environ.get('JBGS_RUN_PHASE')!='anchor':intervention.setup()
probe_path=os.environ.get('JBGS_CAUSAL_PROBES')
probes=json.loads(Path(probe_path).read_text()) if probe_path else {}

original_after=jbgs_state.after_step
original_step=torch.optim.Adam.step
step_count=0
gradient_rows=Path('/output/gradient_checks.jsonl').open('x')
sampling=Path('/output/camera_sampling.jsonl').open('x')
started=time.monotonic()

def checked_step(self,*args,**kwargs):
    global step_count
    step_count+=1
    if step_count==1 or step_count%100==0:
        rows=[]
        for group in self.param_groups:
            for p in group['params']:
                if p.grad is not None:
                    finite=bool(torch.isfinite(p.grad).all().item())
                    if not finite:raise FloatingPointError('Nonfinite optimizer gradient')
                    rows.append({'name':group.get('name'),'finite':finite,'nonzero':int(torch.count_nonzero(p.grad).item())})
        gradient_rows.write(json.dumps({'optimizer_step':step_count,'groups':rows})+'\n');gradient_rows.flush()
    return original_step(self,*args,**kwargs)

def observed(env):
    it=env['iteration'];loss=float(env['total_loss'].detach().item())
    if not torch.isfinite(env['total_loss']).item():raise FloatingPointError('Nonfinite total loss')
    row={'iteration':it,'camera':env['cam_name'],'visual_source':'DA3_CAMERA_Z' if intervention.BRANCH=='da3' else 'COLMAP_MVS_CAMERA_Z','mvs_weight':float(env['current_da_weight']), 'prior_weight':float(env['current_lod_weight'])}
    if env['da_depth'] is not None:
        target=env['da_depth'].squeeze();pred=env['render_pkg']['surf_depth'].squeeze()
        if target.shape==pred.shape:
            row['valid_mvs_loss_pixels']=int((torch.isfinite(target)&torch.isfinite(pred)&(target>0)).sum().item())
    sampling.write(json.dumps(row)+'\n')
    if row['camera'] in probes:
        x,y=probes[row['camera']]
        with Path('/output/probe_depth_trace.jsonl').open('a') as f:
            f.write(json.dumps(dict(iteration=it,camera=row['camera'],pixel=[x,y],
                depth=float(env['render_pkg']['surf_depth'].detach().squeeze()[y,x]),
                alpha=float(env['render_pkg']['rend_alpha'].detach().squeeze()[y,x]),
                prior_inside_multiplier=intervention.INSIDE_MULTIPLIER))+'\n')
    result=original_after(env)
    if it==1 or it==8001 or it%20==0 or result:
        sampling.flush();g=env['gaussians']
        value={**row,'total_loss':loss,'finite':True,'gaussians':len(g.get_xyz),'elapsed_seconds':time.monotonic()-started,'peak_cuda_allocated_bytes':torch.cuda.max_memory_allocated(),'scientific_verdict':None}
        p=Path('/output/progress.json');tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(value,allow_nan=False));tmp.replace(p)
    return result

torch.optim.Adam.step=checked_step
jbgs_state.after_step=observed
sys.argv[0]='/source/train.py'
source=Path('/source/train.py').read_text()
if os.environ.get('JBGS_MEMORY_RASTER')=='1':
    before='render_pkg = render(viewpoint_cam, gaussians, pipe, background)'
    assert source.count(before)==1
    source=source.replace(before,'memory_raster.set_context(cam_name, iteration, gaussians)\n        '+before)
if os.environ.get('JBGS_COMPARISON_BRANCH')=='local_prior0':
    before='lod_depth_loss = compute_depth_loss('
    assert source.count(before)==1
    source=source.replace(before,'lod_depth_loss = intervention.prior_loss(cam_name, iteration, compute_depth_loss,')
Path('/output/executed_train.py').write_text(source)
exec(compile(source,'/source/train.py','exec'),dict(__name__='__main__',__file__='/source/train.py',intervention=intervention,**({'memory_raster':memory_raster} if os.environ.get('JBGS_MEMORY_RASTER')=='1' else {})))
