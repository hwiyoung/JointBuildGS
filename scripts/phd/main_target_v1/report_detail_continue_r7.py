"""15k/30k readouts matching the recorded 7k diagnostics, with fixed camera and section."""
import sys
import numpy as np
from matplotlib.colors import ListedColormap
from common import *
from report_stage0 import plt,save
from report_movement_r7 import loadz,read

def pct(v):return '확인 불가' if v is None else f'{v*100:.3f}%'
def main():
 prior=sys.argv[1];root=OUT/'r7_continue';run=root/'lod2_retry/runs'/f'tg_B173nb_b10_{prior}_s0_r7';rep=next(r for r in read(CFG/'representatives_v1.json')['rows'] if r['id']==1);cam=rep['camera']['name'];L=[f'# {prior} r7 이어 학습 기록 [이 발주에서 냄]','','scientific_verdict: null. 아래는 기록이며 기하 통과 판정이나 원인 해석이 아니다.',''];records=[]
 for it in [15000,30000]:
  check=run/f'model/check{it}';ratio=read(run/f'origin_ratio_{it}.json');fail=read(root/'failures'/f'{prior}_{it}/summary.json');move=read(root/'movement'/f'{prior}_{it}/summary.json');big=read(check/'large_background_descendants.json');events=read(run/f'model/target_monitor/reattach_{it}.json')['events'];data=loadz(check/'large_background_descendants.npz');ver=read(run/f'verification{it}.json');records.append(dict(iteration=it,origin_ratio=ratio,failure=fail,movement=move,large_background=big,verification=ver));L +=[f'## {it:,}회','','| 출신 | 그리는 몫 | 폭 밖 최대 기여 몫 | 틀린 몫 / 그리는 몫 |','|---|---:|---:|---:|']
  for r in ratio['rows']:L.append('| '+r['origin']+' | '+pct(r['draw_share'])+' | '+pct(r['outside_max_share'])+' | '+(f"{r['wrong_share_over_draw_share']:.4f}" if r['wrong_share_over_draw_share'] is not None else '확인 불가')+' |')
  L +=['','| 현재 출신 | 수 | 접선 1 m 초과 | 긴 축 중앙(m) | 불투명도 중앙 | 법선 이동 중앙(m) | 접선 이동 중앙(m) |','|---|---:|---:|---:|---:|---:|---:|']
  for tag,r in move['origins'].items():
   vals=[f"{r[k]['median']:.6f}" if r[k] else '해당 없음' for k in ['size_max_axis_m','opacity','normal_displacement_abs_m','tangent_displacement_m']];L.append(f"| {tag} | {r['gaussians']:,} | {r['tangent_over_1m']:,} | "+' | '.join(vals)+' |')
  L +=['',f"처음 1 m 초과 배경의 생존 자손 {big['surviving_gaussians']:,}개, 생존 원래 부모 {big['surviving_original_ancestors']:,}개. 부모별 개수와 크기·불투명도·이동 분포는 동반 JSON에 모두 있다.",'']
  fig,axes=plt.subplots(2,2,figsize=(12,9));xx=np.arange(3)
  for dx,k,lab,col in [(-.18,'draw_share','렌더 αT 합의 몫','#61a8a7'),(.18,'outside_max_share','폭 밖 최대 기여 몫','#e09c36')]:axes[0,0].bar(xx+dx,[r[k]*100 if r[k] is not None else np.nan for r in ratio['rows']],width=.36,label=lab,color=col)
  axes[0,0].set(xticks=xx,xticklabels=['배경','풀림','패치'],ylim=(0,100),ylabel='%');axes[0,0].legend(fontsize=8)
  matrix=np.array(fail['cross_fraction_of_outside'])*100;im=axes[0,1].imshow(matrix,vmin=0,vmax=100,cmap='Blues');axes[0,1].set(xticks=range(5),xticklabels=['같은 패치','다른 패치','배경','풀림','확인 불가'],yticks=[0,1],yticklabels=['앞','뒤']);axes[0,1].tick_params(axis='x',labelsize=7)
  for i in range(2):
   for j in range(5):axes[0,1].text(j,i,f'{matrix[i,j]:.2f}',ha='center',va='center',fontsize=8)
  fig.colorbar(im,ax=axes[0,1],fraction=.04);h=np.array(fail['sigma_hist_counts']).sum(0);axes[1,0].plot(range(len(h)),100*h/max(h.sum(),1),'o-',color='#438bb6');axes[1,0].set(xticks=range(len(h)),xticklabels=fail['sigma_hist_bins'][:-1],xlabel='|렌더 깊이−목표| / σ 구간 아래끝',ylabel='폭 밖 화소, %',ylim=(0,100));pix=loadz(root/'failures'/f'{prior}_{it}/pixels'/f'{cam}.npz');axes[1,1].imshow(np.where(pix['front_back']>=0,pix['lineage']+1,0),cmap=ListedColormap(['#eeeeee','#55a577','#a94e83','#438bb6','#e09c36','#444444']),vmin=0,vmax=5);axes[1,1].axis('off');axes[1,1].set_title('같은 고정 영상의 폭 밖 화소');fig.subplots_adjust(top=.88,bottom=.14,hspace=.4,wspace=.3);save(fig,f'continue_r7_{prior}_{it}_failure',f'{prior} {it:,}회: 기여·폭 밖 화소·벗어난 크기',dict(ratio=ratio,failure=fail,camera=cam),'지도: 초록 같은 패치 · 자주 다른 패치 · 파랑 배경 · 주황 풀림 · 검정 확인 불가 · 회색 대상 밖')
  fig,axes=plt.subplots(1,2,figsize=(11,4));times=sorted({r['iteration'] for r in events});axes[0].bar(times,[sum(r['released'] for r in events if r['iteration']==i) for i in times],width=75,color='#e09c36');hh=move['reattach']['surviving_release_iteration_counts'];axes[1].bar([int(k) for k in hh],list(hh.values()),width=75,color='#e09c36');axes[0].set(xlabel='풀린 반복',ylabel='전환 사건 수');axes[1].set(xlabel='물려받은 풀림 반복',ylabel='남은 자손 수');fig.subplots_adjust(top=.8,bottom=.2,wspace=.3);save(fig,f'continue_r7_{prior}_{it}_release',f'{prior} {it:,}회: 풀림 사건과 생존 계보',move['reattach'],'전체 상태에서 이어받은 과거 사건 포함 · 사건 수와 살아남은 자손 수 구분')
  fig,axes=plt.subplots(1,2,figsize=(11,4));size=data['scale'].max(1)
  if len(size):axes[0].hist(size,bins=np.geomspace(max(size.min(),1e-8),max(size.max(),size.min()*1.01),55),color='#61a8a7');axes[0].set_xscale('log')
  axes[0].set(xlabel='긴 축 (m)',ylabel='남은 자손 수');axes[1].hist(data['opacity'],bins=np.linspace(0,1,51),color='#61a8a7');axes[1].set(xlabel='불투명도',ylabel='남은 자손 수');fig.subplots_adjust(top=.8,bottom=.2,wspace=.3);save(fig,f'continue_r7_{prior}_{it}_large_background',f'{prior} {it:,}회: 처음 1 m 초과 배경의 자손',big,'초기 크기 상한 없음 · 기록용 · 정기 저장 직전 모델의 값')
  for suffix in ['failure','release','large_background']:L +=[f'![{suffix}](figures/continue_r7_{prior}_{it}_{suffix}.png)','']
  for tag in ['patch','background','released']:
   for view in ['top','oblique']:L +=[f'![{tag} {view}](figures/continue_r7_{prior}_{it}_{tag}_movement_{view}.png)','']
 # Wall and roof point samples and Gaussian centres share the exact previous section limits.
 t=loadz(OUT/'r7/targets'/f'B173nb_b10_{prior}.npz');a,b=np.asarray(rep['start']),np.asarray(rep['end']);vec=(b-a)/np.linalg.norm(b-a);length=np.linalg.norm(b-a);limits=read(DOC/'figures'/f'r6_{prior}_section_comparison.json')['values']['height_limits_m']
 def crop(x):
  q=x[:,:2]-a;d=q@vec;off=abs(q[:,0]*vec[1]-q[:,1]*vec[0]);return d,(d>=0)&(d<=length)&(off<=rep['half_width'])
 fig,axes=plt.subplots(1,4,figsize=(17,5));d,m=crop(t['centre']);axes[0].scatter(d[m],t['centre'][m,2],s=4,c='#e6ab42',label='사전 지붕·벽')
 for filename,color,label in [('gt_xyz.npy','black','참값 점'),('mvs_a_xyz.npy','#478ac3','MVS 점')]:
  points=np.load(UN/'points/B173nb_b10'/filename,mmap_mode='r');dd,mask=crop(points);ix=np.flatnonzero(mask);ix=ix[::max(1,len(ix)//4000)];axes[0].scatter(dd[ix],points[ix,2],s=.5,c=color,alpha=.3,label=label)
 sections=[]
 for ax,it in zip(axes[1:],[7000,15000,30000]):
  sr=OUT/'r7/runs'/f'tg_B173nb_b10_{prior}_s0_r7' if it==7000 else run;s=loadz(sr/f'model/target_monitor/snapshot_{it}.npz');dd,mm=crop(s['xyz'])
  for tag,label,color in [(0,'배경','#61a8a7'),(1,'패치','#a94e83'),(2,'풀림','#e09c36')]:sel=mm&(s['target_tag']==tag);ax.scatter(dd[sel],s['xyz'][sel,2],s=2,c=color,label=label)
  sections.append(dict(iteration=it,in_section=int(mm.sum()),outside_fixed_height=int((mm&((s['xyz'][:,2]<limits[0])|(s['xyz'][:,2]>limits[1]))).sum())));ax.set_title(f'{it:,}회 중심')
 axes[0].set_title('고정 입력')
 for ax in axes:ax.set(xlim=(0,length),ylim=limits,xlabel='고정 단면 거리 (m)');ax.legend(fontsize=6)
 fig.subplots_adjust(top=.8,bottom=.2,wspace=.2);save(fig,f'continue_r7_{prior}_section_centres',f'B173 날개 · {prior}: 지붕·벽 입력과 출신별 중심',dict(section=rep,height_limits_m=limits,counts=sections),'r6·r7과 같은 폭·높이 범위 · 벽은 점과 가우시안 중심으로 표시 · 높이 범위 밖 수는 JSON에 기록')
 L +=[f'![날개 중심 단면](figures/continue_r7_{prior}_section_centres.png)',''];dump(DOC/'tables'/f'continue_r7_detail_{prior}.json',dict(records=records,scientific_verdict=None));(DOC/f'이어학습기록_{prior}_r7.md').write_text('\n'.join(L));print('DETAILED_CHECKPOINT_REPORT_COMPLETE',prior,flush=True)
if __name__=='__main__':main()
