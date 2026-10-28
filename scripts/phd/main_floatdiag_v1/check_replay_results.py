"""Actual saved iterations, policy records and early replay differences."""
import json
import numpy as np
from common import *
names=['fd_dynnow_ALS_s0','fd_current_ALS_s0','fd_current_ALS_s0_record_only'];rows=[]
base=OUT/'runs/R1rep_b10'
for res in names:
    root=base/res;receipt=json.loads((root/'receipt.json').read_text())
    its=sorted(int(p.name.split('_')[1]) for p in (root/'model/point_cloud').glob('iteration_*'))
    expected=list(range(500,7001,500)) if receipt['status']=='PASS' else list(range(500,3001,500))
    assert its==expected,(res,its)
    meta=json.loads((root/'model/monitor/meta.json').read_text())
    lam=.0025 if res=='fd_dynnow_ALS_s0' else .05
    assert meta['lambda_prior']==meta['lambda_mvs']==lam
    assert meta['seed']==0 and meta['revision']=='r17'
    assert not any(meta['fixes'].values()) and not any(meta['ablations'].values())
    health=[json.loads(l) for l in (root/'model/monitor/losstrain_health_v2.jsonl').read_text().splitlines()]
    around=[x for x in health if x['iteration'] in [3000,3100,3200]]
    births=[]
    for it in its:
        path=root/f'model/point_cloud/iteration_{it}/floatdiag_birth.npz'
        with np.load(path) as f:
            assert int(f['iteration'])==it;assert (f['birth_iteration']<=it).all();births.append(dict(iteration=it,count=len(f['origin']),sha256=sha(path)))
    rows.append(dict(result=res,receipt=receipt,saved_iterations=its,lambda_depth=lam,health_around_3100=around,birth_records=births))
orig=base/names[1];retry=base/names[2];diff=[]
for it in range(500,3001,500):
    rel=f'model/point_cloud/iteration_{it}/point_cloud.ply';aa=sha(orig/rel);bb=sha(retry/rel)
    diff.append(dict(iteration=it,original_sha256=aa,retry_sha256=bb,byte_identical=aa==bb))
initial={}
with np.load(orig/'model/monitor/init_points.npz') as a,np.load(retry/'model/monitor/init_points.npz') as b:
    assert set(a.files)==set(b.files)
    for k in a.files:
        initial[k]=bool(np.array_equal(a[k],b[k],equal_nan=True) if a[k].dtype.kind in 'fc' else np.array_equal(a[k],b[k]))
events=[json.loads(l) for l in (retry/'model/monitor/floatdiag_opacity_record_only.jsonl').read_text().splitlines()]
around=[r for r in events if r['iteration'] in [3000,3100,3200,6100,6200]]
save(DOC/'provenance/replay_results.json',dict(at=now(),status='PASS_RECEIPTS',rows=rows,early_checkpoint_comparison=diff,initial_arrays_identical=initial,
    retry_opacity_events_around_reset=around,record_only_trigger_calls=sum(r['opacity_stop_record_only'] for r in events),
    caution='Same configured seed is not a bitwise trajectory guarantee. Early checkpoints differ before the changed opacity policy can take effect. Cause of numerical divergence is not established. Do not attribute surviving iteration 3100 to threshold suppression when its actual median exceeds 0.05.',
    no_mesh_score=True,scientific_verdict=None))
print('three replay receipts, saved times, lambda, births and early differences checked')
