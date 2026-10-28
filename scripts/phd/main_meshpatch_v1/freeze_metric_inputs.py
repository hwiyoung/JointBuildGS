"""Pin unchanged Stage-1 metric definitions before any full mesh execution."""
from mesh_common import *
p=C/'mesh_metric_inputs_v1.json';assert not p.exists()
rows=[]
for site in ['B0_b10','B173nb_b10','R1rep_b10']:
    for name in ['gt_classes.npz','rows_ALS.npz','rows_LoD2.npz','bsurf.npz']:
        f=S1/'defs'/site/name;rows.append(dict(site=site,path=str(f),sha256=sha(f),bytes=f.stat().st_size))
files=list((R/'src/phd/metrics_v3').glob('*.py'))+[R/'scripts/phd/main_stage1_v1/metrics_s1.py',R/'scripts/phd/main_stage1_v1/s1_common.py',R/'scripts/phd/main_stage0_v1/common.py',R/'scripts/phd/main_losstrain_v1/mesh_score.py',R/'scripts/phd/main_floatdiag_v1/geometry.py']
for f in files:rows.append(dict(site=None,path=str(f),sha256=sha(f),bytes=f.stat().st_size))
dump(p,dict(frozen_at=now(),before_first_full_mesh_cleanup=True,inputs=rows,scientific_verdict=None))
dump(C/'mesh_metric_inputs_v1.lock.json',dict(sha256=sha(p),scientific_verdict=None));print('metric inputs frozen',len(rows))
