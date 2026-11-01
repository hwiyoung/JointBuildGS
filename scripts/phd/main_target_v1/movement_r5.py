"""Both ancestry classes, input-relative movement and fixed input camera footprints."""
import numpy as np
from scipy.spatial import ConvexHull
from plyfile import PlyData
from common import *
from report_stage0 import plt,save
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

def loadz(p):
 with np.load(p) as z:return {k:z[k] for k in z.files}
def quant(x):return dict(zip(['min','median','p95','max'],map(float,np.quantile(x,[0,.5,.95,1])))) if len(x) else None

def main():
 gtpath=UN/'points/B173nb_b10/gt_xyz.npy';gt=np.load(gtpath,mmap_mode='r');gtplot=gt[::max(1,len(gt)//100000)]
 for prior in ['ALS','LoD2']:
  run=OUT/'r4n/runs'/f'tg_B173nb_b10_{prior}_s0/model';root=OUT/'r5/movement'/prior;root.mkdir(parents=True,exist_ok=True)
  s=loadz(run/'target_monitor/snapshot_7000.npz');zero=loadz(run/'target_monitor/snapshot_0.npz');t=loadz(OUT/'r2/targets'/f'B173nb_b10_{prior}.npz');seed=loadz(OUT/'r2/stage1'/f'B173nb_b10_{prior}/seeds.npz')
  ids=s['init_id'];normal=s['normal'][ids].astype('f8');norm=np.linalg.norm(normal,axis=1);assert np.max(abs(norm-1))<1e-5;unit=normal/norm[:,None]
  delta=s['xyz'].astype('f8')-s['anchor'][ids].astype('f8');signed=(delta*unit).sum(1);tangent=np.linalg.norm(delta-signed[:,None]*unit,axis=1);size=s['scale'].max(1)
  rows={};lo=t['centre'].min(0);hi=t['centre'].max(0);pad=np.array([5,5,5]);zoom=(lo-pad,hi+pad)
  # Literal patch tangent squares provide a visible prior-plane support; no GT controls this geometry.
  pids=np.arange(0,len(t['centre']),max(1,len(t['centre'])//10000));pc=t['centre'][pids];pn=t['normal'][pids];ok=np.isfinite(pn).all(1);pc,pn=pc[ok],pn[ok]
  axis=np.tile([0.,0.,1.],(len(pn),1));axis[abs(pn[:,2])>.9]=[1.,0.,0.];u=np.cross(pn,axis);u/=np.maximum(np.linalg.norm(u,axis=1)[:,None],1e-12);v=np.cross(pn,u)
  polygons=np.stack([pc+.125*(du*u+dv*v) for du,dv in [(-1,-1),(-1,1),(1,1),(1,-1)]],1)
  for origin,name in [(0,'background'),(1,'prior')]:
   m=s['origin']==origin;far=m&(tangent>1)
   rows[name]=dict(gaussians=int(m.sum()),surviving_ancestors=len(np.unique(ids[m])),initial_ancestors=int((zero['origin']==origin).sum()),tangent_over_1m=int(far.sum()),
    size_max_axis_m=quant(size[m]),opacity=quant(s['opacity'][m]),normal_displacement_abs_m=quant(abs(signed[m])),tangent_displacement_m=quant(tangent[m]),
    far_size_max_axis_m=quant(size[far]),far_opacity=quant(s['opacity'][far]))
   np.savez_compressed(root/f'{name}_movement.npz',gaussian_index=np.flatnonzero(m),init_id=ids[m],xyz=s['xyz'][m],size=size[m],opacity=s['opacity'][m],normal_displacement=signed[m],tangent_displacement=tangent[m])
   xy=s['xyz'][far];inside=((xy>=zoom[0])&(xy<=zoom[1])).all(1)
   for view in ['top','oblique']:
    fig=plt.figure(figsize=(16,5));axes=[fig.add_subplot(131,projection='3d'),fig.add_subplot(132,projection='3d'),fig.add_subplot(133,projection='3d')]
    for ax,pts,title in [(axes[0],xy,'전체 이동 범위'),(axes[1],xy[:0],'참값과 사전 면'),(axes[2],xy[inside],'이동 중심 겹쳐 보기')]:
     ax.scatter(gtplot[:,0],gtplot[:,1],gtplot[:,2],s=.1,c='#333333',alpha=.25,label='참값 점',rasterized=True)
     ax.add_collection3d(Poly3DCollection(polygons,facecolor='#e7ab35',edgecolor='none',alpha=.6,rasterized=True))
     ax.scatter(pts[:,0],pts[:,1],pts[:,2],s=.15,c='#3f8da9' if origin==0 else '#b44187',alpha=.25,label='면을 따라 >1 m 이동한 중심',rasterized=True)
     ax.set(title=title,xlabel='동쪽 (m)',ylabel='북쪽 (m)',zlabel='높이 (m)');ax.view_init(elev=90 if view=='top' else 27,azim=-65)
     if title!='전체 이동 범위':ax.set(xlim=(zoom[0][0],zoom[1][0]),ylim=(zoom[0][1],zoom[1][1]),zlim=(zoom[0][2],zoom[1][2]))
     ax.legend(fontsize=6,loc='upper right')
    fig.subplots_adjust(top=.80,bottom=.18,left=.02,right=.93,wspace=.05)
    save(fig,f'r5_{prior}_{name}_movement_{view}',f'{prior} · '+('배경' if origin==0 else '사전 패치')+' 출신: 목표 면을 따라 1 m 넘게 이동한 중심',
     dict(**rows[name],view=view,zoom_visible_centres=int(inside.sum()),full_points_plotted=len(xy),gt_points_total=len(gt),gt_points_displayed=len(gtplot),prior_patches_displayed=len(pc)),
     '주황: 사전 패치 면 표본(0.25 m 접선 사각형) · 검정: 참값 점 · 전체 그림은 모든 이동 중심 · 확대 범위는 입력으로 고정')
  base=PH/'main_stage3_v1/PHD-MAIN-STAGE3-v1/runs/B173nb_b10'/f'nojudge_{prior}_s0/model/input.ply';p=PlyData.read(base)['vertex'];bxyz=np.c_[p['x'],p['y'],p['z']]
  assert np.array_equal(bxyz,seed['original_xyz'])
  index=json.loads((OUT/'r2/stage1'/f'B173nb_b10_{prior}/maps/index.json').read_text());plane=float(np.median(t['centre'][t['kind']==1,2]));polys=[];no_plane=[]
  for name,c in index['views'].items():
   mp=OUT/'r2/stage1'/f'B173nb_b10_{prior}/maps'/c['file']
   with np.load(mp) as z:H,W=z['depth'].shape
   K=np.asarray(c['K']);M=np.linalg.inv(np.asarray(c['W2C']));corn=np.array([[0,0,1],[W-1,0,1],[W-1,H-1,1],[0,H-1,1]])
   rays=(corn@np.linalg.inv(K).T)@M[:3,:3].T
   vertices=np.concatenate([M[:3,3]+depth*rays for depth in [.2,300.]])
   edges=[(i,(i+1)%4) for i in range(4)]+[(i+4,(i+1)%4+4) for i in range(4)]+[(i,i+4) for i in range(4)]
   cuts=[]
   for ia,ib in edges:
    a,b=vertices[ia],vertices[ib]
    if (a[2]-plane)*(b[2]-plane)<=0 and abs(b[2]-a[2])>1e-12:cuts.append(a+(plane-a[2])/(b[2]-a[2])*(b-a))
   if len(cuts)>=3:
    cut=np.asarray(cuts);polys.append(cut[ConvexHull(cut[:,:2]).vertices])
   else:no_plane.append(name)
  bg=seed['xyz'][seed['origin']==0];fig,axes=plt.subplots(1,3,figsize=(15,5))
  for ax,title in zip(axes,['학습 영상의 전체 시야','배경 MVS 씨앗 확대','기준선 처음 점 확대']):
   for poly in polys:ax.fill(poly[:,0],poly[:,1],color='#888888',alpha=.006,edgecolor='#888888',linewidth=.15)
   if title!='배경 MVS 씨앗 확대':ax.scatter(bxyz[:,0],bxyz[:,1],s=.15,c='#c16535',alpha=.6,label='기존 깊이 기준선 처음 점')
   if title!='기준선 처음 점 확대':ax.scatter(bg[:,0],bg[:,1],s=.15,c='#3688af',alpha=.35,label='r4n 배경 MVS 씨앗')
   if title=='학습 영상의 전체 시야':
    for pts,col in [(bxyz,'#ba5020'),(bg,'#236f9b')]:
     h=ConvexHull(pts[:,:2]);ii=np.r_[h.vertices,h.vertices[0]];ax.plot(pts[ii,0],pts[ii,1],c=col,lw=1)
   ax.set(title=title,xlabel='동쪽 (m)',ylabel='북쪽 (m)');ax.set_aspect('equal');ax.legend(fontsize=7)
   if title!='학습 영상의 전체 시야':ax.set(xlim=(lo[0]-15,hi[0]+15),ylim=(lo[1]-15,hi[1]+15))
  fig.subplots_adjust(top=.82,bottom=.18,wspace=.2)
  footprint=dict(background_seeds=len(bg),baseline_initial_points=len(bxyz),baseline_initial_byte_equal_r4n_original=True,baseline_path=str(base),baseline_sha256=sha(base),views=len(index['views']),plane_intersecting_views=len(polys),views_without_plane_intersection=no_plane,reference_plane_z_m=plane,camera_depth_range_m=[.2,300.],footprint_definition='camera frustum between camera depth .2 and 300m intersect horizontal plane at median input prior-roof height; geometric FOV, not occlusion-aware observed footprint')
  save(fig,f'r5_{prior}_seed_view_extent',f'{prior}: 배경 씨앗·기준선 처음 점·203개 학습 영상의 시야',footprint,
   f'회색: 사전 지붕 중앙 높이 {plane:.2f} m 평면과 0.2~300 m 시야의 교차 · 실제 가림·경사지형 가시성은 뜻하지 않음 · 모든 씨앗을 그림')
  dump(root/'summary.json',dict(at=stamp(),prior=prior,origins=rows,extent=footprint,gt_path=str(gtpath),gt_sha256=sha(gtpath),snapshot_sha256=sha(run/'target_monitor/snapshot_7000.npz'),scientific_verdict=None))
  print('MOVEMENT_DONE',prior,rows,flush=True)
if __name__=='__main__':main()
