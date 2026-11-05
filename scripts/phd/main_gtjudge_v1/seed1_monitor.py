"""Read-only baseline health/state hook; changes no model or optimizer values."""
import json,time
from pathlib import Path
import torch
_n6000=None
_started=time.monotonic()
def after_step(env):
    global _n6000
    i=env['iteration'];g=env['gaussians'];root=Path(env['args'].model_path);mon=root/'target_monitor';mon.mkdir(exist_ok=True)
    loss=env['total_loss']
    if not bool(torch.isfinite(loss)):
        (mon/'STOP.json').write_text(json.dumps(dict(iteration=i,reason='nonfinite_loss',scientific_verdict=None)));raise RuntimeError('SEED1_HEALTH_STOP_NONFINITE')
    if i%100:return
    n=len(g._xyz)
    if i==6000:_n6000=n
    row=dict(iteration=i,gaussians=n,loss=float(loss),elapsed_seconds=time.monotonic()-_started,scientific_verdict=None);reason=None
    if i in [7000,15000,30000]:
        folder=root/'jbgs_complete'/f'iteration_{i}';folder.mkdir(parents=True,exist_ok=True)
        torch.save(dict(iteration=i,gaussians=g.capture(),lineage={k:getattr(g,k).detach().cpu() for k in ['origin','init_id','seat'] if hasattr(g,k)},scientific_verdict=None),folder/'checkpoint.pth')
    if i==7000:
        mask=g.origin==1;median=float(g.get_opacity[mask].median()) if mask.any() else None;row['prior_opacity_median']=median
        if median is None or median<.05:reason='prior_seed_lineage_opacity_median_below_0.05'
    if 7000<=i<=15000 and i%1000==0:
        row['count_at_6000']=_n6000
        if n>3*_n6000:reason='count_gt_3x_6000'
    with (mon/'curve.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
    if i in [7000,15000,30000]:(mon/f'health_{i}.json').write_text(json.dumps(dict(row,status='STOP' if reason else 'PASS_HEALTH')))
    if reason:(mon/'STOP.json').write_text(json.dumps(dict(row,reason=reason)));raise RuntimeError('SEED1_HEALTH_STOP_'+reason)
