"""Exercise the full Stage-1 metric adapter on an explicitly empty fixture."""
from mesh_worker import *
x=stage1_metrics(o3d.geometry.TriangleMesh(),'B0_b10','ALS')
assert x['summary']['n_result']==0 and x['summary']['n_gt']>0
assert x['summary']['f1_0.2'] is None and x['summary']['f1_0.5'] is None
assert 'prior_error' in x['spread'] and 'missing_agreement' in x['completeness']
dump(D/'tables/mesh_metrics_adapter_preflight.json',dict(status='PASS',fixture='empty mesh, existing B0 ALS evaluation definitions; not an experimental result',summary=x['summary'],at=now(),scientific_verdict=None))
print('Stage1 metric adapter empty-mesh preflight PASS')
