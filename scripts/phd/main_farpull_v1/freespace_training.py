"""Runtime observation and stop capture for the freespace-only experiment."""
import json
from pathlib import Path
import torch
import jbgs_freespace as F

OPTIONS=None


def install_median():
    import gaussian_renderer as R
    original_cls=R.GaussianRasterizer;original_render=R.render
    captured={}
    class Rasterizer(original_cls):
        def forward(self,*args,**kwargs):
            out=super().forward(*args,**kwargs)
            captured['median']=torch.nan_to_num(out[2][5:6].detach(),nan=0.,posinf=0.,neginf=0.)
            return out
    def render(*args,**kwargs):
        result=original_render(*args,**kwargs)
        result['fs_median_depth']=captured.pop('median')
        return result
    R.GaussianRasterizer=Rasterizer;R.render=render


def create(args,g):
    if OPTIONS.jbgs_freespace=='off':return None
    assert args.jbgs_lt_farpull_lambda==0 and args.jbgs_mv_consistency=='off' and args.jbgs_appearance=='off'
    assert args.jbgs_sw_depth_loss=='dynamic' and args.jbgs_vfile_vprior=='now'
    control=F.Control(OPTIONS.jbgs_freespace_support,OPTIONS.jbgs_freespace_lambda)
    # Observe exactly native opacity culling, excluding split-parent deletion.
    original=g.densify_and_prune
    def density(*a,**kw):
        prune=g.prune_points
        def cut(mask):
            cutoff=float(a[1] if len(a)>1 else kw['min_opacity'])
            control.deleted+=int((mask & (g.get_opacity.detach().flatten()<cutoff)).sum())
            return prune(mask)
        g.prune_points=cut
        try:return original(*a,**kw)
        finally:g.prune_points=prune
    g.densify_and_prune=density
    return control


def after_step(control,env):
    if control is None or env['iteration']%100:return
    import jbgs_judgment as J
    from gaussian_renderer import render
    g=env['gaussians'];j=env['judgment'];iteration=env['iteration']
    psnr,views=J.lt_five_psnr(j,g,render,env['pipe'],env['background'])
    row=dict(iteration=iteration,train_psnr_legacy5=psnr,psnr_per_view=views,gaussians=len(g.get_xyz),
        opacity_culled_last_100=control.deleted,whole_opacity_median=float(torch.quantile(g.get_opacity.detach().flatten(),.5)),
        **(control.last if control.last else dict(L_free=0.,G_gt_half_fraction=None)),scientific_verdict=None)
    J.lt_write(j,'freespace.jsonl',row);control.deleted=0


def save_stop(env,exc):
    import jbgs_state
    root=Path(env['args'].model_path)/'health_stop'/f'iteration_{env["iteration"]}'
    root.mkdir(parents=True,exist_ok=False)
    env['judgment'].fd_iteration=env['iteration']
    state=jbgs_state.capture_state(env);state['freespace']=vars(OPTIONS)
    state['capture_phase']='before propagating original health failure'
    torch.save(state,root/'checkpoint.pth');env['gaussians'].save_ply(str(root/'point_cloud.ply'))
    (root/'receipt.json').write_text(json.dumps(dict(iteration=env['iteration'],reason=str(exc),
        status='SAVED_BEFORE_HEALTH_STOP',optimizer_state_saved=True,
        checkpoint_sha256=jbgs_state.digest(root/'checkpoint.pth'),model_sha256=jbgs_state.digest(root/'point_cloud.ply'),
        automatic_resume=False,scientific_verdict=None),indent=2)+'\n')
