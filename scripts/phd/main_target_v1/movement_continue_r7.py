"""r7 scientific measurement report; fixed views, source sidecars and no verdict."""
import numpy as np
from matplotlib.colors import ListedColormap
from common import *
from report_stage0 import plt,save

def read(p):return json.loads(p.read_text())
def loadz(p):
 with np.load(p) as z:return {k:z[k] for k in z.files}
def quant(x):return dict(zip(['min','median','p95','max'],map(float,np.quantile(x,[0,.5,.95,1])))) if len(x) else None
def pc(x):return f'{100*x:.3f}%' if x is not None else '확인 불가'
REGION_NAMES={0:'관측 없음',5:'사라짐',1:'일치',2:'보존',3:'보정'}
NAMES=['배경','패치','풀림'];COLORS=['#61a8a7','#a94e83','#e09c36']

def movement(prior,run,iteration,redraw=False):
 root=OUT/'r7_continue/movement'/f'{prior}_{iteration}';root.mkdir(parents=True,exist_ok=True)
 if (root/'summary.json').exists() and not redraw:
  cached=read(root/'summary.json');assert cached['snapshot_sha256']==sha(run/f'model/target_monitor/snapshot_{iteration}.npz');return cached['origins'],cached['reattach']
 s=loadz(run/f'model/target_monitor/snapshot_{iteration}.npz');zero=loadz(run/'model/target_monitor/snapshot_0.npz')
 old=loadz(OUT/'r6/runs'/f'tg_B173nb_b10_{prior}_s0_r6/model/target_monitor/snapshot_7000.npz')
 t=loadz(OUT/'r7/targets'/f'B173nb_b10_{prior}.npz');gt=np.load(UN/'points/B173nb_b10/gt_xyz.npy',mmap_mode='r');gts=gt[::max(1,len(gt)//100000)]
 def displacement(a):
  ids=a['init_id'];n=a['normal'][ids].astype(float);n/=np.linalg.norm(n,axis=1)[:,None];v=a['xyz'].astype(float)-a['anchor'][ids].astype(float);signed=(v*n).sum(1)
  return signed,np.linalg.norm(v-signed[:,None]*n,axis=1)
 signed,tan=displacement(s);osign,otan=displacement(old);rows={};lo=t['centre'].min(0)-5;hi=t['centre'].max(0)+5
 # Fixed input support samples; match r5, and distinguish them from a reconstructed mesh.
 from mpl_toolkits.mplot3d.art3d import Poly3DCollection
 pi=np.arange(0,len(t['centre']),max(1,len(t['centre'])//10000));p=t['centre'][pi];n=t['normal'][pi];valid=np.isfinite(n).all(1);p,n=p[valid],n[valid]
 axis=np.tile([0.,0.,1.],(len(n),1));axis[abs(n[:,2])>.9]=[1,0,0];u=np.cross(n,axis);u/=np.maximum(np.linalg.norm(u,axis=1)[:,None],1e-12);v=np.cross(n,u)
 polygons=np.stack([p+.125*(du*u+dv*v) for du,dv in [(-1,-1),(-1,1),(1,1),(1,-1)]],1)
 for tag in [1,0,2]:
  m=s['target_tag']==tag;far=m&(tan>1);ids=s['init_id'];name=['background','patch','released'][tag]
  row=dict(gaussians=int(m.sum()),surviving_ancestors=len(np.unique(ids[m])),tangent_over_1m=int(far.sum()),size_max_axis_m=quant(s['scale'][m].max(1)),
   opacity=quant(s['opacity'][m]),normal_displacement_abs_m=quant(abs(signed[m])),tangent_displacement_m=quant(tan[m]),
   movement_reference='immutable initial seed target and normal; reassignment does not rewrite provenance')
  rows[name]=row;np.savez_compressed(root/(name+'_movement.npz'),gaussian_index=np.flatnonzero(m),init_id=ids[m],xyz=s['xyz'][m],size=s['scale'][m].max(1),opacity=s['opacity'][m],normal_displacement=signed[m],tangent_displacement=tan[m])
  xy=s['xyz'][far];oldxy=old['xyz'][(old['target_tag']==tag)&(otan>1)]
  bounds=np.concatenate([xy,oldxy,p,gts]);lower=bounds.min(0);upper=bounds.max(0);pad=(upper-lower)*.05;lower-=pad;upper+=pad
  for view in ['top','oblique']:
   fig=plt.figure(figsize=(16,5))
   for cc,(pts,label) in enumerate([(oldxy,'r6 전체 범위'),(xy,f'r7 {iteration:,}회 전체 범위'),(xy,f'r7 {iteration:,}회 입력 범위 확대')]):
    ax=fig.add_subplot(1,3,cc+1,projection='3d');ax.scatter(*gts.T,s=.1,c='#333333',alpha=.25,rasterized=True)
    ax.add_collection3d(Poly3DCollection(polygons,facecolor='#e7ab35',edgecolor='none',alpha=.6,rasterized=True))
    selected=pts if cc<2 else pts[((pts>=lo)&(pts<=hi)).all(1)]
    ax.scatter(*selected.T,s=.15,c=COLORS[tag],alpha=.25,rasterized=True)
    l,h=(lower,upper) if cc<2 else (lo,hi)
    ax.set(xlim=(l[0],h[0]),ylim=(l[1],h[1]),zlim=(l[2],h[2]),xlabel='동쪽 (m)',ylabel='북쪽 (m)',zlabel='높이 (m)',title=label)
    ax.view_init(elev=90 if view=='top' else 27,azim=-65)
   fig.subplots_adjust(top=.80,bottom=.18,left=.02,right=.93,wspace=.05)
   save(fig,f'continue_r7_{prior}_{iteration}_{name}_movement_{view}',f'{prior} · {NAMES[tag]}: 처음 목표 면을 따라 1 m 넘게 이동한 중심',dict(**row,view=view,full_limits=[lower.tolist(),upper.tolist()],zoom_limits=[lo.tolist(),hi.tolist()],r6_tag_available=True,gt_displayed=len(gts),prior_patches_displayed=len(p)),
    '앞 두 칸 같은 축·세 칸 같은 시점 · 색 점: 제목의 출신 중심 · 작은 주황 면: 사전 패치 표본 · 검정: 참값 점')
 events=read(run/f'model/target_monitor/reattach_{iteration}.json')['events'];prior_mask=s['origin']==1;released=s['target_tag']==2
 releases={str(i):int((s['target_released_at'][released]==i).sum()) for i in np.unique(s['target_released_at'][released])}
 stats=dict(query_events=len(events),attached_events=sum(r['attached'] for r in events),changed_target_events=sum(r['changed_target'] for r in events),released_transition_events=sum(r['released'] for r in events),current_released=int(released.sum()),current_prior_lineage=int(prior_mask.sum()),current_released_fraction=float(released.sum()/prior_mask.sum()) if prior_mask.any() else None,surviving_release_iteration_counts=releases,max_reassignment_projection_m=max((r['max_projection_m'] for r in events),default=0.))
 dump(root/'summary.json',dict(iteration=iteration,prior=prior,origins=rows,reattach=stats,snapshot_sha256=sha(run/f'model/target_monitor/snapshot_{iteration}.npz'),scientific_verdict=None))
 return rows,stats


if __name__=='__main__':
 import sys
 prior=sys.argv[1];iteration=int(sys.argv[2]);movement(prior,OUT/'r7_continue/attempt2/runs'/f'tg_B173nb_b10_{prior}_s0_r7',iteration)
