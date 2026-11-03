"""Repair only threshold assignment using saved distances/xyz; retain old receipts."""
from common import *
from geometry import context
from metrics import four,inherited_result_mask
from score_mesh import subset_metrics
from surface_tau import by_wall,RULE
def main():
 start=time.monotonic();ctx=context('B173nb_b10','LoD2');gt=ctx['gt'];wall=gt.G['vert_gt_points'][gt.bs_idx].astype(bool);changed=[]
 for p in sorted((O/'scores').glob('B173nb_b10__LoD2__*/values.json')):
  v=json.loads(p.read_text())
  if v['provenance'].get('tau_assignment')==RULE:continue
  root=p.parent;z=loadz(root/'points.npz');old_gt=z['scene_tau_m'].copy();old_q=z['sample_tau_m'].copy();old_row=z['row_tau_m'].copy();good=inherited_result_mask(z['sample_distance_m'],z['sample_lat_m']);idx=np.flatnonzero(good);nearest=np.zeros(len(good),np.int64)
  bound=np.hypot(z['sample_distance_m'][idx].astype(float),z['sample_lat_m'][idx].astype(float));_,_,_,near=ctx['ref'].query(z['sample_xyz'][idx],bound=bound);nearest[idx]=near
  z['scene_tau_m']=by_wall(ctx,wall);z['sample_tau_m']=by_wall(ctx,wall[nearest]);z['row_tau_m']=by_wall(ctx,ctx['row_kind']==2)
  # Unknown reference normals remain excluded exactly as in the original receipt.
  z['sample_tau_m'][~good]=old_q[~good]
  scene=four(z['scene_distance_m'],z['sample_distance_m'],z['scene_tau_m'],z['sample_tau_m'],result_mask=good)
  for name in ['gt_mean_m','result_mean_m']:scene[name]=v['scene'][name]
  cells,band,offsets=subset_metrics(ctx,z['row_distance_m'],z['sample_region_distance_m'],z['row_tau_m'],z['sample_tau_m'],z['sample_owner'],inherited_result_mask(z['sample_region_distance_m'],z['sample_region_lat_m']))
  for row in cells:
   old=next(x for x in v['cells'] if x['cell']==row['cell'])
   for name in ['gt_mean_m','result_mean_m']:row[name]=old[name]
  before=root/'values.before_wall_tau.json';assert not before.exists();before.write_text(p.read_text());savez(root/'tau.before_wall_correction.npz',scene_tau_m=old_gt,sample_tau_m=old_q,row_tau_m=old_row)
  repair=dict(source=str(before),source_sha256=sha(before),scene_tau_changed=int((old_gt!=z['scene_tau_m']).sum()),sample_tau_changed=int((old_q!=z['sample_tau_m']).sum()),saved_distance_dtype='float32',means_retained_from_original_float64=True,scorer_sha256=sha(Path(__file__).with_name('score_mesh.py')),recount_source_sha256=sha(__file__),gt_xyz_join='stored sample_xyz; exact nearest reference query with an upper bound and unlimited fallback')
  v.update(scene=scene,cells=cells,band=band,offsets=offsets,wall_tau_recount=repair);v['provenance']['tau_assignment']=RULE;savez(root/'points.npz',**z);dump(p,v);changed.append(dict(key=v['key'],**repair));print('RECOUNTED',v['key'],flush=True)
 table('wall_tau_recount',changed);timing('wall_tau_recount',start)
if __name__=='__main__':main()
