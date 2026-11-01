"""Unoccluded GT/prior reference panels accompanying the dense Gaussian movement plots."""
import numpy as np
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from common import *
from report_stage0 import plt,save
for prior in ['ALS','LoD2']:
 with np.load(OUT/'r7/targets'/f'B173nb_b10_{prior}.npz') as z:c=z['centre'];normal=z['normal']
 gt=np.load(UN/'points/B173nb_b10/gt_xyz.npy',mmap_mode='r');points=gt[::max(1,len(gt)//100000)]
 ids=np.arange(0,len(c),max(1,len(c)//10000));p=c[ids];n=normal[ids];ok=np.isfinite(n).all(1);p,n=p[ok],n[ok]
 axis=np.tile([0.,0.,1.],(len(n),1));axis[abs(n[:,2])>.9]=[1,0,0];u=np.cross(n,axis);u/=np.maximum(np.linalg.norm(u,axis=1)[:,None],1e-12);v=np.cross(n,u)
 polygons=np.stack([p+.125*(du*u+dv*v) for du,dv in [(-1,-1),(-1,1),(1,1),(1,-1)]],1);lo=c.min(0)-5;hi=c.max(0)+5
 fig=plt.figure(figsize=(11,5))
 for i,view in enumerate(['top','oblique']):
  ax=fig.add_subplot(1,2,i+1,projection='3d');ax.scatter(*points.T,s=.1,c='#333333',alpha=.25);ax.add_collection3d(Poly3DCollection(polygons,facecolor='#e7ab35',edgecolor='none',alpha=.6))
  ax.set(xlim=(lo[0],hi[0]),ylim=(lo[1],hi[1]),zlim=(lo[2],hi[2]),xlabel='동쪽(m)',ylabel='북쪽(m)',zlabel='높이(m)',title='위에서 본 입력' if i==0 else '비스듬히 본 입력');ax.view_init(elev=90 if i==0 else 27,azim=-65)
 fig.subplots_adjust(top=.8,bottom=.18,left=.03,right=.9,wspace=.12)
 save(fig,f'r7_{prior}_movement_reference',f'{prior}: 이동 중심에 가려지지 않은 참값 점과 사전 면',dict(gt_points_total=len(gt),gt_points_displayed=len(points),prior_patches_displayed=len(p),zoom_limits=[lo.tolist(),hi.tolist()],views=[dict(elev=90,azim=-65),dict(elev=27,azim=-65)]),'검정: 참값 점 · 주황: 사전 패치 면 표본 · 이동 그림의 확대 칸과 같은 범위·시점')
