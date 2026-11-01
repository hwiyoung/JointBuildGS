"""Independent CPU recount of current-tag contributor tables and reassignment evidence."""
import sys
import numpy as np
from scipy.spatial import cKDTree
from common import *
def loadz(p):
 with np.load(p) as z:return {k:z[k] for k in z.files}
def main():
 prior=sys.argv[1];run=OUT/'r6/runs'/f'tg_B173nb_b10_{prior}_s0_r6';model=run/'model';s=loadz(model/'target_monitor/snapshot_7000.npz')
 tags=s['target_tag'];patch=np.full(len(tags),-1,np.int64);patch[tags==1]=s['patch_ids'][s['target_index'][tags==1]]
 initial=loadz(OUT/'r2/stage1'/f'B173nb_b10_{prior}/seeds.npz');origpatch=initial['patch'][s['init_id']]
 root=OUT/'r6/failures'/prior;summary=json.loads((root/'summary.json').read_text());matrix=np.zeros((2,5),np.int64);oldmatrix=np.zeros((2,4),np.int64)
 ix=json.loads((OUT/'r2/stage1'/f'B173nb_b10_{prior}/maps/index.json').read_text());bins=np.array([float(v) for v in summary['sigma_hist_bins']]);hist=np.zeros((2,len(bins)-1),np.int64);near_sum=np.zeros(3);total=0
 for name,meta in ix['views'].items():
  p=loadz(root/'pixels'/f'{name}.npz');m=loadz(OUT/'r2/stage1'/f'B173nb_b10_{prior}/maps'/meta['file']);a=loadz(model/'check7000/renders'/f'{name}.npz')
  index=p['max_gaussian'];valid=index>=0;j=np.maximum(index,0);expected=np.full(index.shape,4,np.int8)
  expected[valid&(tags[j]==0)]=2;expected[valid&(tags[j]==2)]=3
  mask=valid&(tags[j]==1);expected[mask]=np.where(patch[j][mask]==m['owner'][mask],0,1)
  assert np.array_equal(expected,p['lineage'])
  old=np.full(index.shape,3,np.int8);old[valid&(s['origin'][j]==0)]=2;mask=valid&(s['origin'][j]==1);old[mask]=np.where(origpatch[j][mask]==m['owner'][mask],0,1)
  assert np.array_equal(old,p['initial_lineage'])
  good=np.isfinite(m['depth'])&(m['depth']>0)&np.isfinite(m['sigma'])&(m['sigma']>0)
  outside=good&(m['owner']>=0)&np.isfinite(a['depth'])&(a['depth']>0)&(abs(a['depth']-m['depth'])>np.float32(1.96)*m['sigma'])
  direction=np.where(outside,(a['depth']>=m['depth']).astype('i1'),-1);assert np.array_equal(direction,p['front_back'])
  for d in range(2):
   mask=direction==d
   for k in range(5):matrix[d,k]+=int((mask&(expected==k)).sum())
   for k in range(4):oldmatrix[d,k]+=int((mask&(old==k)).sum())
   hist[d]+=np.histogram(abs((a['depth'][mask]-m['depth'][mask])/m['sigma'][mask]),bins=bins)[0]
  near_sum+=a['near_origin_fraction'][good].sum(0,dtype=np.float64);total+=int(good.sum())
 assert np.array_equal(matrix,summary['cross_counts']);assert np.array_equal(oldmatrix,summary['initial_lineage_cross_counts']);assert np.array_equal(hist,summary['sigma_hist_counts'])
 assert len(summary['byte_equal_depth_replay_views'])==203
 target=loadz(OUT/'r2/targets'/f'B173nb_b10_{prior}.npz');valid=(target['region']>=0)&np.isfinite(target['target']).all(1)
 distances,_=cKDTree(target['target'][valid].astype(float)).query(s['xyz'].astype(float),workers=1);near=distances<=.5
 coverage=json.loads((model/'check7000/coverage.json').read_text());assert {str(i):int(((tags==i)&near).sum()) for i in range(3)}==coverage['near_target_counts']
 assert np.allclose(near_sum/total,coverage['near_target_mean_contribution'],rtol=0,atol=1e-12)
 events=json.loads((model/'target_monitor/reattach_7000.json').read_text())['events'];assert max(r['max_projection_m'] for r in events)<=.5+3e-5
 # A released descendant's recorded release iteration is never later than the snapshot.
 assert ((s['target_released_at'][tags==2]>=0)&(s['target_released_at'][tags==2]<=7000)).all()
 result=dict(at=stamp(),status='PASS_R6_DIAGNOSTIC_RECOUNT',prior=prior,views=203,max_contributor_replays=203,
  current_and_initial_lineage_cross_tables=True,sigma_distribution=True,near_target_counts_and_contribution=True,reassignment_projection_max_m=max(r['max_projection_m'] for r in events),scientific_verdict=None)
 dump(run/'verification_diagnostics.json',result);dump(DOC/'tables'/f'diagnostics_{prior}_r6.json',result);print(json.dumps(result),flush=True)
if __name__=='__main__':main()
