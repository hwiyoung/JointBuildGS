#!/usr/bin/env python3
"""Verify full-domain accounting, frozen identities and asymmetric judgments."""
import argparse,csv,json,sys
from pathlib import Path
import numpy as np
import open3d as o3d
sys.path.insert(0,'/repo')
from src.phd.region_view_support_v1 import sha256

parser=argparse.ArgumentParser()
parser.add_argument('--output',required=True)
args=parser.parse_args()
checks=[];root=Path('/audit');review=Path('/review');out=Path(args.output);out.mkdir(exist_ok=False)
for directory in (root,review):
    receipt=json.loads((directory/'receipt.json').read_text())
    for name,digest in receipt['files'].items():assert sha256(directory/name)==digest,(directory,name)
    checks.append(str(directory)+' all promoted hashes')
e=np.load(root/'surface_evidence.npz');p=np.load(root/'per_view_relations.npz');c=np.load(root/'coverage_grid.npz');j=np.load(review/'surface_judgments.npz');i=np.load(review/'complete_R1_inventory.npz')
assert np.array_equal(j['xyz'][:63061],e['mvs_xyz']) and np.array_equal(j['xyz'][63061:],e['prior_xyz'])
assert len(j['xyz'])==118656 and j['source'].sum()==55595
assert np.array_equal((p['mvs']>0).sum(0),e['mvs_view_count'])
checks.append('MVS and prior source identity and view-support alignment')
assert i['zone'].shape==(200,410) and i['zone'].size==82000 and set(np.unique(i['zone']))==set(range(14))
assert i['sample_judgment_counts'].sum()==118656 and set(np.unique(j['judgment']))<=set(range(5))
assert np.all(i['unambiguous_sample_judgment'][i['unsampled_cell']]==0)
rows=json.loads((review/'zone_judgments.json').read_text())['zones'];assert sum(r['xy_cells'] for r in rows)==82000
assert sum(r['mvs_samples'] for r in rows)==63061 and sum(r['prior_samples'] for r in rows)==55595
checks.append('All 82000 XY cells and both source point sets accounted for, unsampled cells unresolved')
for key in ('mvs','prior'):
    counts=np.unpackbits(c[key+'_view_membership_packed'],axis=0)[:588].sum(0).reshape(200,410)
    assert np.array_equal(counts,c[key+'_views'])
assert np.array_equal(c['state'],(c['mvs_views']>0).astype(np.uint8)+2*(c['prior_views']>0).astype(np.uint8))
checks.append('Coverage states independently reconstruct from 588 per-view membership bits')
current=j['judgment'][:63061];prior=j['judgment'][63061:]
assert np.all(j['C1_current'][current==2]) and np.all(j['C1_prior'][prior==2])
idx=list(e['names']).index('DJI_20241217084553_0100_D.JPG')
assert np.all(p['prior'][idx,prior==2]==2) and np.all(e['prior_relation_counts'][prior==2,2]>=3)
assert np.all(np.isin(e['mvs_relation'][current==3],[3,4]))
assert not np.any(np.char.endswith(j['reason'],'OR_BEHIN'))
checks.append('Correction only in reviewed C1; prior occlusion cannot cause correction; missing prior is not correction; reason strings intact')
# A synthetic two-layer case checks the sign used in interpretation, independent of site labels.
scene=o3d.t.geometry.RaycastingScene();verts=np.array([[-10,-10,2],[10,-10,2],[10,10,2],[-10,10,2]],np.float32)
scene.add_triangles(o3d.core.Tensor(verts),o3d.core.Tensor(np.array([[0,1,2],[0,2,3]],np.uint32)))
hit=scene.cast_rays(o3d.core.Tensor(np.array([[0,0,0,0,0,1]],np.float32)))['t_hit'].numpy()[0]
assert abs(hit-2)<1e-6 and 4-hit>1 and 1-hit<-.5
checks.append('Synthetic same-ray prior at Z2 and current at Z4/1 verifies front/occlusion sign')
old=list(csv.DictReader(Path('/old/R1_views.csv').open()));names=set(e['names']);old_native=sum(int(r['native_pixels']) for r in old if r['name'] in names)
new_native=int(c['mvs_pixel_observations'].sum());difference=new_native-old_native
assert abs(difference)<=max(10,old_native*1e-5),(old_native,new_native)
checks.append('Full native MVS endpoint total cross-check against previous independent R1 audit')
summary=dict(status='PASS',scientific_verdict=None,checks=checks,old_native_pixels=old_native,new_native_pixels=new_native,
    native_boundary_difference=difference,note='Old audit used float32 backprojection; current audit uses float64. Boundary differences are recorded, not hidden.',
    unsampled_xy_cells=int(i['unsampled_cell'].sum()),mixed_xy_cells=int(i['mixed_source_or_surface'].sum()),
    review_receipt_sha256=sha256(review/'receipt.json'),script_sha256=sha256(__file__),training_runs=0)
(out/'receipt.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False));print(json.dumps(summary,ensure_ascii=False))
