"""r6 scientific measurement report; fixed views, source sidecars and no verdict."""
import numpy as np
from matplotlib.colors import ListedColormap
from common import *
from report_stage0 import plt,save

def read(p):return json.loads(p.read_text())
def loadz(p):
 with np.load(p) as z:return {k:z[k] for k in z.files}
def quant(x):return dict(zip(['min','median','p95','max'],map(float,np.quantile(x,[0,.5,.95,1])))) if len(x) else None
def pc(x):return f'{100*x:.3f}%' if x is not None else '확인 불가'
REGION_NAMES=['관측 없음','일치','보존','보정']
NAMES=['배경','패치','풀림'];COLORS=['#61a8a7','#a94e83','#e09c36']

def movement(prior,run):
 root=OUT/'r6/movement'/prior;root.mkdir(parents=True,exist_ok=True)
 if (root/'summary.json').exists():
  cached=read(root/'summary.json');assert cached['snapshot_sha256']==sha(run/'model/target_monitor/snapshot_7000.npz');return cached['origins'],cached['reattach']
 s=loadz(run/'model/target_monitor/snapshot_7000.npz');zero=loadz(run/'model/target_monitor/snapshot_0.npz')
 old=loadz(OUT/'r4n/runs'/f'tg_B173nb_b10_{prior}_s0/model/target_monitor/snapshot_7000.npz')
 t=loadz(OUT/'r2/targets'/f'B173nb_b10_{prior}.npz');gt=np.load(UN/'points/B173nb_b10/gt_xyz.npy',mmap_mode='r');gts=gt[::max(1,len(gt)//100000)]
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
  xy=s['xyz'][far];oldxy=old['xyz'][(old['origin']==tag)&(otan>1)] if tag!=2 else np.empty((0,3))
  bounds=np.concatenate([xy,oldxy,p,gts]);lower=bounds.min(0);upper=bounds.max(0);pad=(upper-lower)*.05;lower-=pad;upper+=pad
  for view in ['top','oblique']:
   fig=plt.figure(figsize=(16,5))
   for cc,(pts,label) in enumerate([(oldxy,'r4n 전체 범위'),(xy,'r6 전체 범위'),(xy,'r6 입력 범위 확대')]):
    ax=fig.add_subplot(1,3,cc+1,projection='3d');ax.scatter(*gts.T,s=.1,c='#333333',alpha=.25,rasterized=True)
    ax.add_collection3d(Poly3DCollection(polygons,facecolor='#e7ab35',edgecolor='none',alpha=.6,rasterized=True))
    selected=pts if cc<2 else pts[((pts>=lo)&(pts<=hi)).all(1)]
    ax.scatter(*selected.T,s=.15,c=COLORS[tag],alpha=.25,rasterized=True)
    l,h=(lower,upper) if cc<2 else (lo,hi)
    ax.set(xlim=(l[0],h[0]),ylim=(l[1],h[1]),zlim=(l[2],h[2]),xlabel='동쪽 (m)',ylabel='북쪽 (m)',zlabel='높이 (m)',title=label+(' · 꼬리표 없음' if cc==0 and tag==2 else ''))
    ax.view_init(elev=90 if view=='top' else 27,azim=-65)
   fig.subplots_adjust(top=.80,bottom=.18,left=.02,right=.93,wspace=.05)
   save(fig,f'r6_{prior}_{name}_movement_{view}',f'{prior} · {NAMES[tag]}: 처음 목표 면을 따라 1 m 넘게 이동한 중심',dict(**row,view=view,full_limits=[lower.tolist(),upper.tolist()],zoom_limits=[lo.tolist(),hi.tolist()],r4n_tag_available=tag!=2,gt_displayed=len(gts),prior_patches_displayed=len(p)),
    '앞 두 칸 같은 축·세 칸 같은 시점 · 주황: 사전 패치 면 표본 · 검정: 참값 점 · r4n에는 풀림 꼬리표 없음')
 events=read(run/'model/target_monitor/reattach_7000.json')['events'];prior_mask=s['origin']==1;released=s['target_tag']==2
 releases={str(i):int((s['target_released_at'][released]==i).sum()) for i in np.unique(s['target_released_at'][released])}
 stats=dict(query_events=len(events),attached_events=sum(r['attached'] for r in events),changed_target_events=sum(r['changed_target'] for r in events),released_transition_events=sum(r['released'] for r in events),current_released=int(released.sum()),current_prior_lineage=int(prior_mask.sum()),current_released_fraction=float(released.sum()/prior_mask.sum()) if prior_mask.any() else None,surviving_release_iteration_counts=releases,max_reassignment_projection_m=max((r['max_projection_m'] for r in events),default=0.))
 dump(root/'summary.json',dict(prior=prior,origins=rows,reattach=stats,snapshot_sha256=sha(run/'model/target_monitor/snapshot_7000.npz'),scientific_verdict=None))
 return rows,stats

def main():
 rep=next(r for r in read(CFG/'representatives_v1.json')['rows'] if r['id']==1);name=rep['camera']['name'];table=[]
 text=['# r6 · 7,000회 점검','', '[이 발주에서 냄] r19와 r4n 결과를 보존하고 r20에서 배경·풀림 묶기를 해제했다. 패치 꼬리표만 같은 단위의 잠근 목표점에 다시 붙인다. 단계 0, 씨앗, 목표 지도, 손실·무게와 λ, 학습률과 밀도 제어 일정은 그대로다.','',
 '설정 잠금: 2026-11-01 17:46 KST. SHA-256 `1fce3f0a7b9142e37ec3c9c323dec589ba998ad725e73cf23cf49342c9d35593`.','',
 '두 판은 7,000회 상태를 저장한 뒤 계속 학습하다가, ALS 9,000회 정기 불투명도 초기화 직후의 기존 감시 조건으로 공동 중단했다. 이는 아래 7,000회 기하 판정과 별개이며 [경위 보고](정기초기화_감시중단_r6.md)에 기록했다.','',
 '판정 기준은 건강·칸 0~3 뜬 면 5% 이하·일치 영역 결과 τ 안(항공 LiDAR 69.3%, LoD2 74.1% 이상)·칸 0~3 면 없음 비율 비증가다. 전체 화소 목표 따름 80%는 기록만 한다.','']
 for prior in ['ALS','LoD2']:
  run=OUT/'r6/runs'/f'tg_B173nb_b10_{prior}_s0_r6';oldrun=OUT/'r4n/runs'/f'tg_B173nb_b10_{prior}_s0';score=read(run/'post7000/score.json');ref=read(OUT/'r6/reference'/prior/'score.json');ver=read(run/'verification7000.json');coverage=read(run/'model/check7000/coverage.json')
  t=loadz(OUT/'r2/targets'/f'B173nb_b10_{prior}.npz');snap=loadz(run/'model/target_monitor/snapshot_7000.npz');zero=loadz(run/'model/target_monitor/snapshot_0.npz')
  rows,reattach=movement(prior,run);table.append(dict(prior=prior,score=score,reference=ref,coverage=ver['strata'],movement=rows,reattach=reattach))
  text +=[f'## {prior} · {score["status"]}','', '| 항목 | r4n 7,000회 | r6 7,000회 | 기준 |','|---|---:|---:|---:|',
   f'| 뜬 면 | {pc(ref["floating_fraction_cells_0_3"])} | {pc(score["floating_fraction_cells_0_3"])} | ≤5% |',
   f'| 일치 영역 결과 τ 안 | {pc(ref["agreement_within_tau_fraction"])} | {pc(score["agreement_within_tau_fraction"])} | ≥{pc(score["agreement_threshold"])} |',
   f'| 칸 0~3 면 없음 | {pc(ref["no_surface_fraction_cells_0_3"])} | {pc(score["no_surface_fraction_cells_0_3"])} | r4n 이하 |','',
   'r4n의 저장 메시를 같은 첫 면 탐색·칸·넓이 분모로 다시 채점했다. 문서의 반올림된 69.3%/74.1%를 통과 문턱으로 적용하고 실제 상승 폭도 별도 기록했다.','',
   '| 목표 화소 구분 | 화소 수 | 폭 안 | 깊이 없음 |','|---|---:|---:|---:|']
  labels={'all':'전체','prior':'사전 패치','background':'배경 MVS','prior_roof':'사전 지붕','prior_wall':'사전 벽','prior_original':'사전 원값','prior_replaced':'사전 대체','region_0':'관측 없음','region_1':'일치','region_2':'보존','region_3':'보정'}
  for key,r in ver['strata'].items():text.append(f'| {labels[key]} | {r["target_pixels"]:,} | {pc(r["fraction"])} | {pc(r["missing_fraction"])} |')
  fig,axes=plt.subplots(1,2,figsize=(11,4));oldver=read(oldrun/'verification7000.json')
  keys=['all','prior','background','prior_roof','prior_wall'];xx=np.arange(len(keys))
  for offset,source,label,col in [(-.18,oldver,'r4n','#999999'),(.18,ver,'r6','#438bb6')]:
   axes[0].bar(xx+offset,[100*source['strata'][k]['fraction'] if source['strata'][k]['fraction'] is not None else np.nan for k in keys],width=.36,label=label,color=col)
  axes[0].set(xticks=xx,xticklabels=['전체','사전','배경','지붕','벽'],ylim=(0,100),ylabel='목표 폭 안 (%)');axes[0].legend()
  metrics=['floating_fraction_cells_0_3','agreement_within_tau_fraction','no_surface_fraction_cells_0_3']
  for offset,source,label,col in [(-.18,ref,'r4n','#999999'),(.18,score,'r6','#438bb6')]:axes[1].bar(np.arange(3)+offset,[100*source[k] for k in metrics],width=.36,label=label,color=col)
  axes[1].set(xticks=np.arange(3),xticklabels=['뜬 면','일치 τ 안','면 없음'],ylim=(0,100),ylabel='넓이 (%)');axes[1].legend();fig.subplots_adjust(top=.8,bottom=.2,wspace=.25)
  save(fig,f'r6_{prior}_gate_coverage',f'{prior}: 같은 셈의 7,000회 비교',table[-1],'화소 목표 따름은 기록 · 기하 표는 넓이 비율 · missing은 0으로 대체하지 않음')
  text +=['',f'![같은 셈의 비교](figures/r6_{prior}_gate_coverage.png)','']
  # Fixed photo/render and fixed [-5,5] normal-height range.
  current=loadz(run/'model/check7000/renders'/f'{name}.npz');old=loadz(oldrun/'model/check7000/renders'/f'{name}.npz');m=loadz(OUT/'r2/stage1'/f'B173nb_b10_{prior}/maps'/f'{name}.npz');ix=read(OUT/'r2/stage1'/f'B173nb_b10_{prior}/maps/index.json')['views'][name]
  photo=loadz(OUT/'r2/preflight'/f'B173nb_b10_{prior}'/f'{name}.npz')['photo_rgb'].transpose(1,2,0);fig,axes=plt.subplots(1,3,figsize=(12,4))
  for ax,im,label in zip(axes,[photo,old['rgb'],current['rgb']],['원본 사진','r4n 7,000회','r6 7,000회']):ax.imshow(im);ax.set_title(label);ax.axis('off')
  fig.subplots_adjust(top=.82,bottom=.15,wspace=.03);save(fig,f'r6_{prior}_fixed_render',f'B173 날개 · {prior} · 고정 영상',dict(camera=name,old_sha256=sha(oldrun/'model/check7000/renders'/f'{name}.npz'),new_sha256=sha(run/'model/check7000/renders'/f'{name}.npz')),'전체 영상 · 같은 카메라·해상도')
  owner=m['owner'];has=owner>=0;patch=np.maximum(owner,0);K=np.asarray(ix['K']);inv=np.linalg.inv(np.asarray(ix['W2C']));vv,uu=np.indices(owner.shape)
  def height(a):
   d=a['depth'];q=np.stack([(uu-K[0,2])/K[0,0]*d,(vv-K[1,2])/K[1,1]*d,d,np.ones_like(d)],-1);world=(q.reshape(-1,4)@inv.T)[:,:3].reshape(*owner.shape,3);h=((world-t['centre'][patch])*t['normal'][patch]).sum(2);h[~has|(d<=0)]=np.nan;return h
  fig,axes=plt.subplots(1,3,figsize=(12,4))
  for ax,arr,label in zip(axes,[np.where(has,t['h'][patch],np.nan),height(old),height(current)],['잠근 목표','r4n 렌더','r6 렌더']):im=ax.imshow(arr,cmap='coolwarm',vmin=-5,vmax=5);ax.set_title(label);ax.axis('off');fig.colorbar(im,ax=ax,fraction=.04,extend='both')
  fig.subplots_adjust(top=.82,bottom=.2,wspace=.12);save(fig,f'r6_{prior}_fixed_height',f'{prior}: 같은 사전 패치 법선의 높이 h',dict(camera=name,h_color_range_m=[-5,5]),'m · 사전 원반 소유 패치로 역투영 · 끝 색은 범위 밖')
  for suffix in ['fixed_render','fixed_height']:text +=[f'![{suffix}](figures/r6_{prior}_{suffix}.png)','']
  big=read(run/'model/check7000/large_background_descendants.json');bdata=loadz(run/'model/check7000/large_background_descendants.npz')
  text +=[f'처음 1 m 초과 배경 씨앗 {big["initial_large_background_count"]:,}개 중 {big["surviving_original_ancestors"]:,}개 계보의 자손 {big["surviving_gaussians"]:,}개가 남았다. 초기 상위 열 개는 r4n과 같은 초기 배열이므로 [기존 목록](초기배경_크기_r3.md)을 계승한다.','', '| 처음 큰 배경의 남은 자손 | 최소 | 중앙 | 95% | 최대 |','|---|---:|---:|---:|---:|']
  for key,label in [('size_max_axis_m','긴 축(m)'),('opacity','불투명도'),('normal_displacement_abs_m','법선 이동(m)'),('tangent_displacement_m','접선 이동(m)')]:
   q=big[key];text.append('| '+label+' | '+(' | '.join(f'{q[k]:.6f}' for k in ['min','median','p95','max']) if q else '해당 없음 | 해당 없음 | 해당 없음 | 해당 없음')+' |')
  fig,axes=plt.subplots(1,2,figsize=(11,4));size=bdata['scale'].max(1)
  if len(size):axes[0].hist(size,bins=np.geomspace(max(size.min(),1e-8),max(size.max(),size.min()*1.01),55),color=COLORS[0]);axes[0].set_xscale('log')
  axes[0].set(xlabel='긴 축(m)',ylabel='남은 자손 수');axes[1].hist(bdata['opacity'],bins=np.linspace(0,1,51),color=COLORS[0]);axes[1].set(xlabel='불투명도',ylabel='남은 자손 수',xlim=(0,1));fig.subplots_adjust(top=.8,bottom=.2,wspace=.25)
  save(fig,f'r6_{prior}_large_background',f'{prior}: 처음 1 m 초과 배경 계보의 남은 자손',big,'처음 씨앗과 모든 자손을 같은 init_id로 셈 · 추가 멈춤 기준 아님')
  text +=['',f'![큰 배경 계보](figures/r6_{prior}_large_background.png)','']
  text +=['| 현재 꼬리표 | 수 | 처음 목표 면을 따라 1 m 초과 | 긴 축 중앙값(m) | 불투명도 중앙값 | 법선 이동 중앙값(m) | 접선 이동 중앙값(m) |','|---|---:|---:|---:|---:|---:|---:|']
  for key,r in rows.items():
   def med(k):return f'{r[k]["median"]:.6f}' if r[k] else '해당 없음'
   text.append(f'| {dict(patch="패치",background="배경",released="풀림")[key]} | {r["gaussians"]:,} | {r["tangent_over_1m"]:,} | {med("size_max_axis_m")} | {med("opacity")} | {med("normal_displacement_abs_m")} | {med("tangent_displacement_m")} |')
  text +=['',f'현재 풀림: {reattach["current_released"]:,}/{reattach["current_prior_lineage"]:,} = {pc(reattach["current_released_fraction"])}. 재연결 점검 호출 {reattach["query_events"]:,}회에서 0.5 m 안 연결 갱신 {reattach["attached_events"]:,}건(같은 목표 번호 유지 포함), 목표 번호가 바뀐 사건 {reattach["changed_target_events"]:,}건, 풀림 전환 사건 {reattach["released_transition_events"]:,}회. 사건 합에는 이후 삭제된 가우시안도 포함한다. 이동은 r5와 같이 처음 씨앗의 목표·법선 기준이며 현재 목표로 다시 쓴 이동이 아니다.','']
  text +=[f'![참값·사전 면 기준 보기](figures/r6_{prior}_movement_reference.png)','']
  for tag in ['patch','background','released']:
   for view in ['top','oblique']:text +=[f'![{tag} {view}](figures/r6_{prior}_{tag}_movement_{view}.png)','']
  fig,axes=plt.subplots(1,2,figsize=(11,4));events=read(run/'model/target_monitor/reattach_7000.json')['events'];it=sorted(set(r['iteration'] for r in events))
  axes[0].bar(it,[sum(r['released'] for r in events if r['iteration']==i) for i in it],width=75,color=COLORS[2]);axes[0].set(xlabel='풀림이 된 반복',ylabel='전환 사건 수')
  hist=reattach['surviving_release_iteration_counts'];axes[1].bar([int(i) for i in hist],list(hist.values()),width=75,color=COLORS[2]);axes[1].set(xlabel='풀림이 된 반복',ylabel='7,000회에 남은 가우시안 수');fig.subplots_adjust(top=.8,bottom=.2,wspace=.25)
  save(fig,f'r6_{prior}_reattach',f'{prior}: 목표 다시 붙이기와 풀림 기록',dict(**reattach,near_target_counts=coverage['near_target_counts'],near_target_mean_contribution=coverage['near_target_mean_contribution']),
   '왼쪽: 당시 전환 사건 · 오른쪽: 살아남은 자손(풀림 반복 물려받음) · 풀림은 재연결하지 않음')
  text +=[f'![풀림 시점](figures/r6_{prior}_reattach.png)','','건물 목표점 0.5 m 안의 수: '+', '.join(NAMES[i]+' '+format(coverage['near_target_counts'][str(i)],',')+'개' for i in [0,2,1])+'. 모든 목표 화소의 평균 렌더 기여(배경·풀림·패치): '+', '.join(pc(v) for v in coverage['near_target_mean_contribution'])+'.','']
  fig,axes=plt.subplots(1,3,figsize=(13,4));order=[0,2,1];axes[0].bar(range(3),[coverage['near_target_counts'][str(i)] for i in order],color=[COLORS[i] for i in order]);axes[0].set(xticks=range(3),xticklabels=[NAMES[i] for i in order],ylabel='목표점 0.5 m 안 가우시안 수')
  good=np.isfinite(m['depth'])&(m['depth']>0)&np.isfinite(m['sigma'])&(m['sigma']>0)
  for ax,ch,label in [(axes[1],0,'가까운 배경 기여'),(axes[2],1,'가까운 풀림 기여')]:
   im=ax.imshow(np.where(good,current['near_origin_fraction'][:,:,ch],np.nan),vmin=0,vmax=1,cmap='viridis');ax.set_title(label);ax.axis('off');fig.colorbar(im,ax=ax,fraction=.04)
  fig.subplots_adjust(top=.8,bottom=.2,wspace=.3);save(fig,f'r6_{prior}_near_target_contribution',f'{prior}: 건물 목표점 가까이 있는 배경·풀림의 기여',dict(camera=name,counts=coverage['near_target_counts'],mean_contribution=coverage['near_target_mean_contribution'],channels=['background','released','patch'],radius_m=.5),
   '거리: 같은 단위 목표점까지의 3차원 거리 · 화소 값: 해당 집단 기여/전체 alpha · 범위 0~1')
  text +=[f'![가까운 배경과 풀림의 렌더 기여](figures/r6_{prior}_near_target_contribution.png)','']
  fail=read(OUT/'r6/failures'/prior/'summary.json');oldfail=read(OUT/'r5/failures'/prior/'summary.json');counts=np.asarray(fail['cross_counts']);frac=np.asarray(fail['cross_fraction_of_outside'])
  text +=['| 깊이 방향 | 같은 현재 패치 | 다른 현재 패치 | 배경 | 풀림 | 확인 불가 |','|---|---:|---:|---:|---:|---:|']
  for i,label in enumerate(['앞(가림 방향)','뒤(비침 방향)']):text.append('| '+label+' | '+' | '.join(pc(x) for x in frac[i])+' |')
  text +=['','방향과 최대 렌더 기여의 분해다. 방향만으로 물리적 원인을 확정하지 않는다. 현재 붙은 목표와 처음 부모의 패치 계보를 구분하여 두 교차표 모두 JSON에 보존했다.','']
  initial_matrix=np.asarray(fail['initial_lineage_cross_counts']);initial_fraction=initial_matrix/max(1,fail['totals']['outside'])
  text +=['| 처음 계보 기준(r5와 같은 셈) | 같은 처음 패치 | 다른 처음 패치 | 배경 | 확인 불가 |','|---|---:|---:|---:|---:|']
  for revision,fractions in [('r4n',np.asarray(oldfail['cross_fraction_of_outside'])),('r6',initial_fraction)]:
   for i,direction in enumerate(['앞','뒤']):text.append('| '+revision+' '+direction+' | '+' | '.join(pc(v) for v in fractions[i])+' |')
  fig,axes=plt.subplots(1,2,figsize=(11,4))
  for ax,fractions,label in [(axes[0],np.asarray(oldfail['cross_fraction_of_outside']),'r4n'),(axes[1],initial_fraction,'r6')]:
   im=ax.imshow(fractions*100,vmin=0,vmax=100,cmap='Blues');ax.set(title=label,xticks=range(4),xticklabels=['같은 처음 패치','다른 처음 패치','배경','확인 불가'],yticks=[0,1],yticklabels=['앞','뒤'])
   for i in range(2):
    for j in range(4):ax.text(j,i,f'{fractions[i,j]*100:.2f}',ha='center',va='center',fontsize=8)
   fig.colorbar(im,ax=ax,fraction=.04)
  fig.subplots_adjust(top=.8,bottom=.24,wspace=.25);save(fig,f'r6_{prior}_initial_lineage_failure',f'{prior}: r5와 같은 불변 처음 계보 기준으로 실패 화소를 비교했다',dict(r4n=oldfail['cross_counts'],r6=initial_matrix.tolist(),r4n_denominator=oldfail['totals']['outside'],r6_denominator=fail['totals']['outside']),
   '풀림도 처음 패치의 자손으로 셈 · 현재 붙은 목표를 기준으로 한 교차표와 구분 · 분모는 각 판의 폭 밖 사전 화소')
  text +=['',f'![불변 처음 계보 비교](figures/r6_{prior}_initial_lineage_failure.png)','']
  fig,axes=plt.subplots(1,2,figsize=(12,4));im=axes[0].imshow(frac*100,vmin=0,vmax=100,cmap='Blues');axes[0].set(xticks=range(5),xticklabels=['같은 패치','다른 패치','배경','풀림','확인 불가'],yticks=[0,1],yticklabels=['앞','뒤'])
  for i in range(2):
   for j in range(5):axes[0].text(j,i,f'{frac[i,j]*100:.2f}',ha='center',va='center',fontsize=8)
  fig.colorbar(im,ax=axes[0],fraction=.04);bins=fail['sigma_hist_bins'];n=len(bins)-1
  for h,label,col in [(oldfail,'r4n','#999999'),(fail,'r6','#438bb6')]:
   vals=np.asarray(h['sigma_hist_counts']).sum(0);axes[1].plot(range(n),100*vals/max(1,vals.sum()),'o-',label=label,c=col)
  axes[1].set(xticks=range(n),xticklabels=[str(x) for x in bins[:-1]],xlabel='|깊이 차이|/σ 구간의 아래끝',ylabel='폭 밖 사전 화소 (%)',ylim=(0,100));axes[1].legend();fig.subplots_adjust(top=.8,bottom=.23,wspace=.3)
  save(fig,f'r6_{prior}_failure_table',f'{prior}: 폭 밖 화소의 방향·최대 기여와 벗어난 크기',fail,'교차표 분모: 폭 밖 사전 화소 · 마지막 σ 구간: 1,000 이상 · r4n과 같은 σ 구간')
  pix=loadz(OUT/'r6/failures'/prior/'pixels'/f'{name}.npz');opix=loadz(OUT/'r5/failures'/prior/'pixels'/f'{name}.npz');fig,axes=plt.subplots(1,2,figsize=(11,4))
  cmap=ListedColormap(['#eeeeee','#55a577','#a94e83','#438bb6','#e09c36','#444444'])
  for ax,a,label in [(axes[0],opix,'r4n · 처음 패치'),(axes[1],pix,'r6 · 현재 패치')]:
   lineage=a['lineage'].copy()
   if label.startswith('r4n'):lineage[lineage==3]=4
   image=np.where(a['front_back']>=0,lineage+1,0);ax.imshow(image,cmap=cmap,vmin=0,vmax=5);ax.set_title(label);ax.axis('off')
  fig.subplots_adjust(top=.8,bottom=.2,wspace=.03);save(fig,f'r6_{prior}_failure_map',f'{prior}: 고정 영상의 폭 밖 사전 화소',dict(camera=name,summary=fail['totals']),
   '초록: 같은 패치 · 자주: 다른 패치 · 파랑: 배경 · 주황: 풀림 · 검정: 확인 불가 · 회색: 분석 대상 밖')
  for suffix in ['failure_table','failure_map','section_comparison','within_tau','floating_origin']:text +=[f'![{suffix}](figures/r6_{prior}_{suffix}.png)','']
  text +=['| 구분 | 영역 | 넓이(m²) | 결과 τ 안 | 목표 자체 τ 안 |','|---|---|---:|---:|---:|']
  for r in score['result_vs_target']:text.append(f'| {dict(all="전체",original="원값",replaced="대체")[r["replacement"]]} | {REGION_NAMES[r["region"]]} | {r["area_m2"]:.3f} | {pc(r["result_within_tau_fraction"])} | {pc(r["target_within_tau_fraction"])} |')
  health=read(run/'model/target_monitor/health_7000.json');full=read(run/'model/jbgs_complete/iteration_7000/receipt.json')
  text +=['',f'건강: {health["status"]}; 처음 사전 패치에서 심은 계보(풀림 포함)의 불투명도 중앙값 {health["prior_opacity_median"]:.6f}; 가우시안 {health["gaussians"]:,}, 6,000회 {health["count_at_6000"]:,}. 전체 상태 SHA-256 `{full["checkpoint_sha256"]}`.','']
 fig,axes=plt.subplots(1,3,figsize=(14,4));curve_rows=[]
 for prior,col in [('ALS','#438bb6'),('LoD2','#a94e83')]:
  for revision,style in [('r4n','--'),('r6','-')]:
   model=OUT/revision/'runs'/('tg_B173nb_b10_'+prior+'_s0'+('_r6' if revision=='r6' else ''))/'model'
   rows=[json.loads(x) for x in (model/'target_monitor/curve.jsonl').read_text().splitlines() if json.loads(x)['iteration']<=7000]
   curve_rows.append(dict(prior=prior,revision=revision,rows=rows))
   for ax,key,label in zip(axes,['loss','prior_opacity_median','gaussians'],['총 손실','처음 패치 계보 불투명도 중앙값','가우시안 수']):
    ax.plot([r['iteration'] for r in rows],[r[key] for r in rows],style,c=col,label=prior+' '+revision);ax.set(xlabel='반복',ylabel=label,xlim=(0,7000));ax.legend(fontsize=6)
 fig.subplots_adjust(top=.8,bottom=.2,wspace=.3);save(fig,'r6_training_curves','r4n과 r6의 7,000회까지 학습 기록',curve_rows,'r4n은 6,900회까지의 로그 · r6는 7,000회 포함 · 재설정 일정은 동일')
 text +=['![학습 곡선](figures/r6_training_curves.png)','']
 text +=['## 구현·검증 범위','',
  'r20 변경 파일·줄은 `tables/r20_changes_r6.json`과 패치 파일에 기록했다. 목표 검색은 같은 단위·사전 정보의 유효 단계 0 목표점 전체이며, 거리 동률은 원 패치 번호가 작은 것을 택한다. 꼬리표와 init_id를 별도로 유지하며, 배경·풀림은 묶지 않는다.','',
  '저장에는 Adam 모멘트·매개변수 묶음, 난수 상태, 영상 순서와 남은 영상 목록, 현재 꼬리표·목표 번호·풀림 시각·6,000회 수가 포함된다. 작은 예제의 결정적 100회 연속/이어 학습은 모델·Adam·영상 순서가 바이트 단위로 같았다. 이는 실제 실험 영상의 100회 재학습 비교를 뜻하지 않는다.','',
  '채점용 7,000회 모델은 밀도 제어 직전이며, 이어 학습용 전체 상태는 그 반복의 밀도 제어·목표 갱신 뒤다. 15,000·30,000회 전체 상태는 해당 반복에 도달한 경우에만 생성된다. 중단으로 미도달한 반복을 완료로 적지 않는다.','',
  '참값은 채점·점검에만 사용했다. 대체 패치는 원값과 별도 줄로 기록했다. scientific_verdict: null.','',stamp()]
 dump(DOC/'tables/summary_r6.json',dict(rows=table,scientific_verdict=None));(DOC/'단계1_7000회_점검_r6.md').write_text('\n'.join(text)+'\n');print('REPORT_R6_DONE',flush=True)
if __name__=='__main__':main()
