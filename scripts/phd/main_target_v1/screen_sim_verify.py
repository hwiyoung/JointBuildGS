"""Independent reconciliation of retained raw radii, counts, quality and scores."""
import numpy as np
from common import *
ROOT=OUT/'screen_sim';DEST=DOC/'screen_sim'
def main():
 cfg=json.loads((CFG/'screen_sim.json').read_text());inp=json.loads((ROOT/'inputs/index.json').read_text());checks=[]
 for row in cfg['states']:
  root=ROOT/'states'/row['key']
  if not (root/'table_receipt.json').exists():continue
  if (root/'verification.json').exists():checks.append(json.loads((root/'verification.json').read_text()));continue
  a=np.load(root/'gaussians.npz');N=len(a['max_radius']);mx=np.zeros(N,'i4');arg=np.full(N,-1,'i2');maxratio=np.zeros(N,'f8')
  for i,v in enumerate(inp['views']):
   r=np.load(root/'radii'/(v['camera']+'.npz'))['radius'];greater=r>mx;mx[greater]=r[greater];arg[greater]=i;maxratio=np.maximum(maxratio,r/v['width'])
  assert np.array_equal(mx,a['max_radius']);assert np.array_equal(arg,a['max_radius_view']);assert np.allclose(maxratio,a['max_radius_over_width'],rtol=1e-7,atol=0)
  masks=[]
  for c in cfg['candidates']:
   m=np.load(root/(c['key']+'_remove.npy'));expected=mx>c['value'] if c['mode']=='pixels' else maxratio>c['value'];assert np.array_equal(m,expected);masks.append(m)
  for lo,hi in zip(masks,masks[1:]):assert not np.any(hi&~lo)
  groups=json.loads((root/'groups_table.json').read_text())['rows'];quality_checks=[]
  for variant in ['before']+[c['key'] for c in cfg['candidates']]:
   summary=json.loads((root/variant/'summary.json').read_text());assert len(summary['views'])==203 and [r['camera'] for r in summary['views']]==cfg['views'];gg=[r for r in groups if r['variant']==variant];assert sum(r['all_count'] for r in gg)==N;assert sum(r['removed'] for r in gg)==summary['selected']
   for camera in inp['fixed_views']:
    data=np.load(root/variant/(camera+'_float.npz'));delta=(data['rgb'].astype('f8')-data['gt'].astype('f8'))**2;roi=np.load(ROOT/'inputs'/(camera+'.npz'))['roi'];rec=next(r for r in summary['views'] if r['camera']==camera)
    for reg,mask in [('all',np.ones_like(roi)),('roi',roi)]:
     expected=float(delta[:,mask].mean()) if mask.any() else None;observed=rec['quality'][reg]['mse'];err=abs(expected-observed) if expected is not None else 0;assert err<2e-8,(row['key'],variant,camera,reg,err);quality_checks.append(err)
  z=dict(state=row['key'],status='PASS',raw_radius_views=203,gaussians=N,max_radius_exact=True,argmax_first_exact=True,candidate_masks_exact=True,nested_masks=True,group_count_conservation=True,max_fixed_image_MSE_error=max(quality_checks),scientific_verdict=None);dump(root/'verification.json',z);checks.append(z);print('SIM_VERIFY',row['key'],flush=True)
 roi_checks=[]
 for v in inp['views']:
  assert v['projected_box_pixels']==v['missing_usable_mvs_pixels']+v['valid_mvs_outside_box_pixels']+v['roi_pixels'];assert v['missing_usable_mvs_pixels']==v['raw_depth_missing_pixels']+v['confidence_rejected_pixels'];roi_checks.append(v['camera'])
 scores=[];cells=json.loads((REPO/'configs/phd/main_axes71_v2/axes71_v2.json').read_text())['cells'];keys=['all']+cells['order']+list(cells['sums'])
 for p in sorted((ROOT/'scores').glob('*/*/*/values.json')):
  z=json.loads(p.read_text());assert list(z['metrics'])==keys and list(z['surface'])==keys;area=z['surface']['all']['area_m2'];assert abs(sum(z['surface'][k]['area_m2'] for k in cells['order'])-area)<1e-6
  for k in keys:
   g=z['metrics'][k]['gt'];r=z['metrics'][k]['res']['E'];assert r['n']+r['excluded']==z['metrics'][k]['res']['n_res_all'];
   for value in [g.get('R_tau'),r.get('P_tau'),z['surface'][k]['floating_fraction'],z['surface'][k]['no_surface_fraction']]:assert value is None or 0<=value<=1
  scores.append(dict(state=z['state'],variant=z['variant'],prior=z['prior'],cells=len(keys),status='PASS'))
 complete=len(checks)==8 and len(scores)==45
 result=dict(status='PASS' if complete else 'IN_PROGRESS',states=checks,roi_views_reconciled=len(roi_checks),score_partitions=scores,meshes=len(list((ROOT/'meshes').glob('*/*/merged.json'))),expected_meshes=40,expected_score_partitions=45,training=False,backward=False,scientific_verdict=None);dump(ROOT/'verification.json',result);dump(DEST/'tables/verification.json',result)
if __name__=='__main__':main()
