"""Independent read-only invariants and immutable-input checks."""
import numpy as np
from common import *
ROOT=OUT/'r8_screen_prune'
def read(p):return json.loads(Path(p).read_text())
def main():
 cfg=read(CFG/'r8_screen.json');lock=read(CFG/'r8_screen.lock.json');checked=[]
 for i,(p,h) in enumerate(lock['files'].items()):
  assert sha(p)==h,p;checked.append(p)
  if i%20==0:print('SCREEN_VERIFY_HASH',i,len(lock['files']),flush=True)
 alpha=read(ROOT/'alpha_measure.json');assert alpha['status']=='VALIDATED_FLOAT32_CPU_REPLAY';assert read(ROOT/'alpha_export.json')['render_rgb_byte_equal']
 cameras=read(ROOT/'camera_distance.json')['rows'];by={r['camera']:r for r in cameras};counts=read(ROOT/'camera_near_gaussians.json')['rows'];checks=[]
 b=read(cfg['boundaries']);basis=np.array(b['basis']);lo=np.array(b['lo']);hi=np.array(b['hi']);polygon=np.array([[lo[0],lo[1]],[hi[0],lo[1]],[hi[0],hi[1]],[lo[0],hi[1]]])@basis
 def edge_distance(p):
  v=np.roll(polygon,-1,axis=0)-polygon;t=np.clip(np.sum((p-polygon)*v,axis=1)/np.sum(v*v,axis=1),0,1);d=np.linalg.norm(p-polygon-t[:,None]*v,axis=1).min();uv=p@basis.T;return 0. if np.all(uv>=lo) and np.all(uv<=hi) else d
 err=max(abs(edge_distance(np.array([r['x'],r['y']]))-r['eval_box_xy_distance_m']) for r in cameras);assert err<1e-9
 for state in cfg['states']:
  rr=sorted([r for r in counts if r['state']==state['key']],key=lambda r:(-r['gaussians_within30m'],r['camera']));test=[rr[0],rr[len(rr)//2]]
  with np.load(state['arrays']) as z:xyz=z['xyz'].astype('f8')
  for r in test:
   c=by[r['camera']];cc=np.array([c['x'],c['y'],c['z']]);n=int((np.sum((xyz-cc)**2,axis=1)<=900).sum());assert n==r['gaussians_within30m'];checks.append(dict(state=state['key'],camera=r['camera'],brute_count=n,tree_count=r['gaussians_within30m']))
 thresholds=read(ROOT/'screen_thresholds.json')['rows'];pre=[r for r in thresholds if r['population']=='pre_density'];assert all(r['parent_survival_verified'] and r['saved_max_radii_above20'] is None and r['world_above_parent_survivors']==0 for r in pre)
 assert all(r['nonzero']==0 for r in read(ROOT/'stored_radius_audit.json')['rows'])
 sequence=read(ROOT/'camera_sequence.json')['rows'];assert len(sequence)==7030 and sequence[0]['iteration']==7001 and sequence[-1]['iteration']==14030
 for r in read(ROOT/'camera_counts_100.json')['rows']:assert sum(x['camera']==r['camera'] for x in sequence if r['start_exclusive']<x['iteration']<=r['end_inclusive'])==r['chosen_count']
 dump(ROOT/'verification.json',dict(at=stamp(),status='PASS_WITH_PRE_RADIUS_NOT_SAVED',input_files_verified=len(checked),immutable_input_paths=checked,camera_distance_alternative_polygon_max_abs_m=err,camera_near_brute_force_checks=checks,post_density_all_zero_7=True,parent_prefix_survival_checks=True,alpha_forward_parity=True,alpha_replay_errors=alpha['errors'],training=False,source_code_changes=False,scientific_verdict=None));print('SCREEN_VERIFY_COMPLETE',len(checked),flush=True)
if __name__=='__main__':main()
