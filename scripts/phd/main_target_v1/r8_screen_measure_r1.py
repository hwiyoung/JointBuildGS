"""CPU-only saved-data measurements; no training imports, optimizer calls, or file mutations."""
import gc,math,random,csv
import numpy as np
import torch
from scipy.spatial import cKDTree
from common import *
ROOT=OUT/'r8_screen_prune';REC=OUT/'r8_recorded_continue';H=REC/'heavy'
def read(p):return json.loads(Path(p).read_text())
def pc(p):return torch.load(p,map_location='cpu')
def arr(t):return t.detach().cpu().numpy()
def stat(v):
 v=np.asarray(v);return dict(n=v.size,min=float(v.min()),p01=float(np.percentile(v,1)),p05=float(np.percentile(v,5)),median=float(np.median(v)),p95=float(np.percentile(v,95)),p99=float(np.percentile(v,99)),max=float(v.max())) if v.size else dict(n=0)
def table(name,rows):
 dump(ROOT/(name+'.json'),dict(rows=rows,scientific_verdict=None))
 with (ROOT/(name+'.csv')).open('w') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
def extent_from_json(records,names):
    points=[]
    for n in names:
        camera=records[n];C=np.eye(4);C[:3,:3]=camera['rotation'];C[:3,3]=camera['position'];W=np.linalg.inv(C).astype('f4');points.append(np.linalg.inv(W)[:3,3:4])
    pts=np.hstack(points);center=np.mean(pts,axis=1,keepdims=True);return float(np.max(np.linalg.norm(pts-center,axis=0,keepdims=True))*1.1)
def small(cp):return dict(iteration=cp['iteration'],rng=cp['rng']['python'],stack=cp['viewpoint_stack'],train_order=cp['train_order'])
def main():
 c=read(CFG/'r8_screen.json');lock=read(CFG/'r8_screen_measure.r1.lock.json')
 for p,h in lock['files'].items():assert sha(p)==h,p
 ROOT.mkdir(exist_ok=True);assert not any(ROOT.iterdir());model=Path(c['model']);orig=pc(c['original_7000']);prior=small(orig);extent=float(orig['model'][-1]);opt=orig['optimization'];full_train=prior['train_order'];assert len(full_train)==203
 cameras={r['img_name']:r for r in read(model/'cameras.json')};names=sorted(full_train);centers=np.array([cameras[n]['position'] for n in names]);mean=centers.mean(0);extent_camera=float(np.linalg.norm(centers-mean,axis=1).max()*1.1);extent_exact=extent_from_json(cameras,names);assert extent==extent_exact,(extent,extent_exact)
 b=read(c['boundaries']);uv=centers[:,:2]@np.array(b['basis']).T;delta=np.maximum(np.maximum(np.array(b['lo'])-uv,uv-np.array(b['hi'])),0);distance=np.linalg.norm(delta,axis=1)
 cr=[dict(camera=n,x=float(x[0]),y=float(x[1]),z=float(x[2]),eval_box_xy_distance_m=float(d),gt50=bool(d>50),gt100=bool(d>100),gt200=bool(d>200)) for n,x,d in zip(names,centers,distance)];table('camera_distance',cr)
 # Actual persisted extent and source-specific camera normalization from immutable model camera lists.
 source_extents=[]
 for source in c['sources']:
  if not source.get('model'):continue
  p=Path(source['model'])/'cameras.json'
  if not p.exists():continue
  cc={r['img_name']:r for r in read(p)};assert set(names)<=set(cc);pts=np.array([cc[n]['position'] for n in names]);ex=extent_from_json(cc,names)
  source_extents.append(dict(implementation=source['name'],cameras_extent_m=ex,world_size_threshold_m=.1*ex,canonical_camera_positions_equal=bool(np.array_equal(centers,pts)),max_camera_position_difference_m=float(np.abs(pts-centers).max()),basis='getNerfppNorm on actual model cameras.json and exact203 train membership',model_camera_file=str(p)))
 table('source_extents',source_extents)
 dump(ROOT/'settings.json',dict(cameras_extent_m=extent,camera_extent_recomputed_m=extent_exact,float64_camera_center_reference_extent_m=extent_camera,world_size_threshold_m=.1*extent,split_size_threshold_m=opt['percent_dense']*extent,optimization=opt,camera_distance_distribution=stat(distance),counts_farther={str(x):int((distance>x).sum()) for x in [50,100,200]},scientific_verdict=None));del orig;gc.collect()
 # Initial IDs are immutable source lineage; unavailable pre-density max-radius is never replaced by a fresh render.
 stopa=dict(np.load(H/'states/r8_14031_stop/arrays.npz'));cam=c['heavy_camera'];stopv=dict(np.load(H/'states/r8_14031_stop'/(cam+'.npz')));storder=np.lexsort((np.arange(len(stopa['xyz'])),-stopv['tiles'].astype('i8')));sttop=storder[:math.ceil(.01*len(storder))];seeds=np.unique(stopa['init_id'][sttop]);del storder
 trace={r['iteration']:r['camera'] for r in [json.loads(x) for x in (model/'recording/forward_100.jsonl').read_text().splitlines()]};sequences=[];replay=[];rows=[];details=[];stored=[]
 def rng_segment(endcp):
  nonlocal prior
  nxt=small(endcp);rng=random.Random();rng.setstate(prior['rng']);stack=None if prior['stack'] is None else list(prior['stack']);seq=[]
  for it in range(prior['iteration']+1,nxt['iteration']+1):
   if not stack:stack=list(prior['train_order'])
   name=stack.pop(rng.randint(0,len(stack)-1));seq.append(dict(iteration=it,camera=name))
   if it in trace:assert name==trace[it],('trace',it,name,trace[it])
  assert rng.getstate()==nxt['rng'],'end RNG mismatch';assert stack==nxt['stack'],'end camera stack mismatch';assert prior['train_order']==nxt['train_order'];replay.append(dict(start=prior['iteration'],end=nxt['iteration'],draws=len(seq),end_rng_equal=True,end_stack_equal=True,recorded_every100_cameras_equal=True));sequences.extend(seq);prior=nxt
 for it in range(8000,14001,1000):
  cp=pc(model/f'jbgs_complete/iteration_{it}/checkpoint.pth');rng_segment(cp);a=dict(np.load(H/f'states/r8_{it}_pre/arrays.npz'));v=dict(np.load(H/f'states/r8_{it}_pre/{cam}.npz'));gr=dict(np.load(model/f'recording/pre_densification/iteration_{it}/gradient.npz'));snapshot=np.load(model/f'target_monitor/snapshot_{it}.npz');available=['max_radii2D' in gr,'max_radii2D' in snapshot.files];snapshot.close();assert not any(available);n=len(a['xyz']);order=np.lexsort((np.arange(n),-v['tiles'].astype('i8')));top=order[:math.ceil(.01*n)];m=cp['model'];postrad=arr(m[7]);postxyz=arr(m[1]);postids=arr(cp['init_id']);frozen=cp.get('frozen_mask');assert frozen is None or not bool(frozen.any())
  split=(gr['normalized'].reshape(-1)>=opt['densify_grad_threshold'])&(a['longest_axis']>opt['percent_dense']*extent);keep=(~split)&(a['opacity']>=opt['opacity_cull'])&(a['longest_axis']<=.1*extent);kept=np.flatnonzero(keep);k=len(kept);idmatch=np.array_equal(postids[:k],a['init_id'][kept]);nonpatch=a['tag'][kept]!=1;xyzmatch=np.array_equal(postxyz[:k][nonpatch],a['xyz'][kept][nonpatch]);scalematch=np.array_equal(arr(m[4])[:k][nonpatch],gr['scale'][kept][nonpatch]);parent_verified=bool(idmatch and xyzmatch and scalematch)
  stored.append(dict(iteration=it,population='post_density_complete',count=len(postrad),max_radii=stat(postrad),nonzero=int(np.count_nonzero(postrad)),above20=int((postrad>20).sum()),frozen_count=0,parent_prefix_ids_equal=bool(idmatch),nonpatch_parent_prefix_xyz_equal=bool(xyzmatch),nonpatch_parent_prefix_scaling_equal=bool(scalematch),pre_density_max_radii_status='UNAVAILABLE_NOT_SAVED',pre_density_gradient_keys=list(gr)))
  for label,ix in [('per_state_top1',top),('stopped_top1_initial_seed_descendants',np.flatnonzero(np.isin(a['init_id'],seeds)))]:
   radii=v['radius'][ix];scale=a['longest_axis'][ix];world=scale>.1*extent;survive=keep[ix] if parent_verified else None
   rr=dict(iteration=it,population='pre_density',group=label,n=len(ix),saved_max_radii_status='UNAVAILABLE_NOT_SAVED',saved_max_radii_above20=None,saved_screen_above20_survivors=None,current_0020_radius_median=float(np.median(radii)),current_0020_radius_above20=int((radii>20).sum()),current_radius_above20_parent_survivors=int(((radii>20)&survive).sum()) if parent_verified else None,world_threshold_m=.1*extent,size_median_m=float(np.median(scale)),size_max_m=float(scale.max()),size_ratio_median=float(np.median(scale/(.1*extent))),world_above=int(world.sum()),world_above_parent_survivors=int((world&survive).sum()) if parent_verified else None,parent_survival_verified=parent_verified,parent_survivors=int(survive.sum()) if parent_verified else None,next_state='same_iteration_post_density_complete',post_max_radii_above20=int((postrad>20).sum()));rows.append(rr)
   details.append(dict(iteration=it,group=label,current_radius=stat(radii),longest_axis=stat(scale),size_over_threshold=stat(scale/(.1*extent)),saved_max_radii=None))
  print('SCREEN_STATE',it,extent,len(top),parent_verified,rows[-2]['world_above'],flush=True);del cp,a,v,gr,m,postxyz,postids,postrad;gc.collect()
 stopcp=pc(next(r['checkpoint'] for r in c['states'] if r['key']=='r8_LoD2_stop'));rng_segment(stopcp);rad=arr(stopcp['model'][7]);assert np.array_equal(arr(stopcp['model'][1]),stopa['xyz']);scale=stopa['longest_axis'][sttop];saved=rad[sttop];frozen=stopcp.get('frozen_mask');assert frozen is None or not bool(frozen.any())
 rows.append(dict(iteration=14031,population='completed14030_before_attempt',group='per_state_top1',n=len(sttop),saved_max_radii_status='AVAILABLE_PARTIAL_30_ITERATIONS_AFTER14000',saved_max_radii_above20=int((saved>20).sum()),saved_screen_above20_survivors=None,current_0020_radius_median=float(np.median(stopv['radius'][sttop])),current_0020_radius_above20=int((stopv['radius'][sttop]>20).sum()),current_radius_above20_parent_survivors=None,world_threshold_m=.1*extent,size_median_m=float(np.median(scale)),size_max_m=float(scale.max()),size_ratio_median=float(np.median(scale/(.1*extent))),world_above=int((scale>.1*extent).sum()),world_above_parent_survivors=None,parent_survival_verified=None,parent_survivors=None,next_state='UNAVAILABLE_NO_FURTHER_TRAINING',post_max_radii_above20=None));details.append(dict(iteration=14031,group='per_state_top1',current_radius=stat(stopv['radius'][sttop]),longest_axis=stat(scale),size_over_threshold=stat(scale/(.1*extent)),saved_max_radii=stat(saved)))
 table('screen_thresholds',rows);dump(ROOT/'screen_distributions.json',dict(rows=details,scientific_verdict=None));dump(ROOT/'stored_radius_audit.json',dict(rows=stored,stop_top1=stat(saved),stop_all=stat(rad),scientific_verdict=None));dump(ROOT/'camera_replay_verification.json',dict(rows=replay,optimization_steps=0,scientific_verdict=None));table('camera_sequence',sequences)
 focus=['DJI_20241217102533_0019_D',cam,'DJI_20241217100114_0043_D'];counts=[]
 for start in range(7000,14001,100):
  end=min(start+100,14030);seq=[r['camera'] for r in sequences if start<r['iteration']<=end]
  for name in focus:counts.append(dict(start_exclusive=start,end_inclusive=end,completed_draws=len(seq),camera=name,chosen_count=seq.count(name),interval_full100=len(seq)==100,attempt14031_excluded=True))
 table('camera_counts_100',counts)
 # Accepted contribution is nonnegative. Exact zero alpha for every subset pixel proves each selected row contributes zero; this does not infer from black RGB.
 sub=dict(np.load(H/'subset/top1.npz'));alpha=sub['alpha'];rgb=sub['rgb'];finite=bool(np.isfinite(alpha).all() and np.isfinite(rgb).all());zero=bool(np.count_nonzero(alpha)==0);meta=read(c['camera_index'])['views'][cam];W=np.array(meta['W2C']);points=stopa['xyz'][sttop].astype('f8');depth=(points@W[:3,:3].T+W[:3,3])[:,2];near=c['near_center_m'];proof=dict(finite=finite,selected=len(sttop),subset_alpha_nonzero_pixels=int(np.count_nonzero(alpha)),subset_alpha=stat(alpha),subset_rgb_max=float(rgb.max()),max_alphaT_per_gaussian=stat(np.zeros(len(sttop))) if zero and finite else None,status='PROVEN_ZERO_BY_EXACT_SUBSET_ALPHA' if zero and finite else 'UNAVAILABLE_PER_GAUSSIAN_MAX_NOT_STORED',proof='Every accepted alpha>=1/255 and T>0 before early termination, so an all-zero composed subset alpha implies no selected row accepted any pixel. Adding other rows only reduces transmittance and cannot create acceptance. Full scene per-row contribution is therefore also zero.',center_depth_m=stat(depth),center_behind_or_on_camera=int((depth<=0).sum()),center_front_inside_near=int(((depth>0)&(depth<=near)).sum()),center_beyond_near=int((depth>near).sum()),near_m=near,fragment_depth_is_different='Pixel ray/surfel intersection depth is tested separately in forward.cu; not inferred from center Z',scientific_verdict=None)
 dump(ROOT/'black_render.json',proof);np.savez_compressed(ROOT/'top1_depth_alpha.npz',row=sttop,init_id=stopa['init_id'][sttop],center_depth=depth,saved_max_radius=saved,max_alphaT=np.zeros(len(sttop),dtype='f4') if zero and finite else np.full(len(sttop),np.nan))
 del stopcp,stopa,stopv,sub;gc.collect()
 nearrows=[];extents=[]
 for state in c['states']:
  with np.load(state['arrays']) as a:xyz=a['xyz'].copy()
  tree=cKDTree(xyz);nums=tree.query_ball_point(centers,c['camera_radius_m'],return_length=True,workers=3);assert len(nums)==203
  for name,ct,d in zip(names,nums,distance):nearrows.append(dict(state=state['key'],camera=name,gaussians_within30m=int(ct),eval_box_xy_distance_m=float(d)))
  cp=pc(state['checkpoint']);extents.append(dict(state=state['key'],saved_cameras_extent=float(cp['model'][-1]),threshold_m=.1*float(cp['model'][-1])));del cp,tree,xyz;gc.collect();print('CAMERA_NEAR',state['key'],int(nums.max()),flush=True)
 table('camera_near_gaussians',nearrows);table('camera_near_top10',[dict(rank=i+1,**r) for state in c['states'] for i,r in enumerate(sorted([r for r in nearrows if r['state']==state['key']],key=lambda x:(-x['gaussians_within30m'],x['camera']))[:10])]);table('saved_extents',extents)
 dump(ROOT/'measure_receipt.json',dict(at=stamp(),status='PASS_WITH_EXPLICIT_UNAVAILABLE_PRE_RADIUS',pre_density_radius_available=False,post_density_radius_available=True,rng_camera_replay_verified=True,all_nonpatch_parent_survival_prefixes_verified=all(r['parent_survival_verified'] for r in rows if r['population']=='pre_density'),black_alpha_status=proof['status'],states_30m=4,cameras=203,training=False,source_code_changed=False,scientific_verdict=None))
if __name__=='__main__':main()
