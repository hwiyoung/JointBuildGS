"""Checkpoint figures with the frozen section, camera and color ranges."""
import sys
import numpy as np
from common import *
from report_stage0 import plt,save
from report_movement_r7 import loadz,read

def main():
 prior=sys.argv[1];rep=next(r for r in read(CFG/'representatives_v1.json')['rows'] if r['id']==1);camera=rep['camera']['name'];t=loadz(OUT/'r7/targets'/f'B173nb_b10_{prior}.npz');e=loadz(PH/'main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/direct_stage1_v2'/f'B173nb_b10__{prior}/evaluation.npz')
 roots=[OUT/'r7/runs'/f'tg_B173nb_b10_{prior}_s0_r7']+[OUT/'r7_continue/lod2_retry/runs'/f'tg_B173nb_b10_{prior}_s0_r7']*2;its=[7000,15000,30000];posts=[p/f'post{it}' for p,it in zip(roots,its)];names=[f'r7 {it:,}회' for it in its];zs=[loadz(p/'patch_z.npz') for p in posts];basepost=OUT/'r7_continue/post'/f'base_{prior}_30000';zs.append(loadz(basepost/'patch_z.npz'));names.append('기존 방법 30,000회');posts.append(basepost)
 a,b=np.array(rep['start']),np.array(rep['end']);direction=(b-a)/np.linalg.norm(b-a);length=np.linalg.norm(b-a)
 def crop(x):
  q=x[:,:2]-a;d=q@direction;off=abs(q[:,0]*direction[1]-q[:,1]*direction[0]);return d,(d>=0)&(d<=length)&(off<=rep['half_width'])
 d,sel=crop(t['centre']);roof=sel&(t['kind']==1)&e['scoring_allowed'];limits=read(DOC/'figures'/f'r6_{prior}_section_comparison.json')['values']['height_limits_m'];gt=t['centre'][:,2]+e['p_gt']*t['normal'][:,2];fig,axes=plt.subplots(1,4,figsize=(17,4.7))
 for ax,z,name in zip(axes,zs,names):
  h=t['centre'][:,2]+z['z']*t['normal'][:,2];ok=roof&np.isfinite(h);ax.scatter(d[roof],gt[roof],s=5,c='black',label='참값');ax.scatter(d[sel],t['centre'][sel,2],s=3,c='#e6ab42',label='사전 정보');ax.errorbar(d[roof],t['target'][roof,2],yerr=1.96*t['sigma'][roof]*abs(t['normal'][roof,2]),fmt='.',ms=1,c='gray',alpha=.25,label='목표 폭');ax.scatter(d[ok],h[ok],s=5,c='#438bb6',label='결과');ax.set(title=name,ylim=limits,xlim=(0,length),xlabel='고정 단면 거리 (m)');ax.legend(fontsize=6)
 fig.subplots_adjust(top=.81,bottom=.20,wspace=.22);save(fig,f'continue_r7_{prior}_section',f'{prior}: B173 날개 고정 단면',dict(iterations=its,section=rep,limits=limits,source_scores=[str(p/'score.json') for p in posts]),'지금 채점 메시의 첫 교차점 · r6 그림과 같은 단면·높이 범위 · 영역/목표는 r7 고정')
 fig,axes=plt.subplots(1,4,figsize=(17,5));counts=[];eligible=e['in_eval']&e['scoring_allowed']
 for ax,z,post,name in zip(axes,zs,posts,names):
  floating=eligible&(z['category']==1);label=np.full(len(floating),3,np.int8);attpath=post/'origin_attribution.npz'
  if attpath.exists():
   att=loadz(attpath);seen=att['views']>0
   for code,ch in [(0,0),(1,2),(2,1)]:label[seen&(att['mean_fraction'][:,ch]>=.5)]=code
  ax.scatter(t['centre'][eligible,0],t['centre'][eligible,1],s=.3,c='#dddddd')
  for i,color,lab in [(0,'#61a8a7','배경 우세'),(1,'#a94e83','패치 우세'),(2,'#e09c36','풀림 우세'),(3,'#444444','혼합·확인 불가')]:
   m=floating&(label==i);ax.scatter(t['centre'][m,0],t['centre'][m,1],s=1.4,c=color,label=lab)
  ax.set_aspect('equal');ax.set(title=name,xlabel='동쪽 (m)',ylabel='북쪽 (m)');ax.legend(fontsize=6);counts.append(dict(name=name,floating_patches=int(floating.sum()),origin_counts={str(i):int((floating&(label==i)).sum()) for i in range(4)}))
 fig.subplots_adjust(top=.82,bottom=.17,wspace=.25);save(fig,f'continue_r7_{prior}_floating_origin',f'{prior}: 뜬 면 출신 지도',counts,'동일 평가 범위 · 우세는 보이는 영상의 평균 기여 ≥0.5 · 기존 방법 계보는 확인 불가')
 renders=[loadz(root/f'model/check{it}/renders'/f'{camera}.npz') for root,it in zip(roots,its)];photo=loadz(OUT/'r2/preflight'/f'B173nb_b10_{prior}'/f'{camera}.npz')['photo_rgb'].transpose(1,2,0);fig,axes=plt.subplots(1,4,figsize=(16,4))
 for ax,img,name in zip(axes,[photo]+[x['rgb'] for x in renders],['사진']+names[:3]):ax.imshow(img);ax.set_title(name);ax.axis('off')
 fig.subplots_adjust(top=.81,bottom=.15,wspace=.03);save(fig,f'continue_r7_{prior}_fixed_render',f'{prior}: 고정 영상 렌더',dict(camera=camera,iterations=its),'동일 카메라·해상도 · 학습 반복만 다름')
 maps=OUT/'r7/stage1'/f'B173nb_b10_{prior}/maps';m=loadz(maps/f'{camera}.npz');meta=read(maps/'index.json')['views'][camera];owner=m['owner'];has=owner>=0;j=np.maximum(owner,0);K=np.array(meta['K']);inv=np.linalg.inv(np.array(meta['W2C']));vv,uu=np.indices(owner.shape)
 def height(arr):
  dd=arr['depth'];q=np.stack([(uu-K[0,2])/K[0,0]*dd,(vv-K[1,2])/K[1,1]*dd,dd,np.ones_like(dd)],-1);world=(q.reshape(-1,4)@inv.T)[:,:3].reshape(*owner.shape,3);h=((world-t['centre'][j])*t['normal'][j]).sum(2);h[~has|~np.isfinite(dd)|(dd<=0)]=np.nan;return h
 fig,axes=plt.subplots(1,4,figsize=(16,4))
 for ax,arr,name in zip(axes,[np.where(has,t['h'][j],np.nan)]+[height(a) for a in renders],['r7 목표']+names[:3]):im=ax.imshow(arr,cmap='coolwarm',vmin=-5,vmax=5);ax.set_title(name);ax.axis('off');fig.colorbar(im,ax=ax,fraction=.04,extend='both')
 fig.subplots_adjust(top=.8,bottom=.17,wspace=.13);save(fig,f'continue_r7_{prior}_fixed_height',f'{prior}: 같은 사전 패치 법선의 높이',dict(camera=camera,iterations=its,h_color_range_m=[-5,5]),'r6·r7과 같은 −5~5 m 색 범위 · 목표 원반 없는 화소는 빈칸')
 print('CHECKPOINT_FIGURES_COMPLETE',prior,flush=True)
if __name__=='__main__':main()
