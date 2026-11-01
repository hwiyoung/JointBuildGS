"""Record-only continuation tables and plots, including baseline 30k against r7 targets."""
import numpy as np
from common import *
from report_stage0 import plt,save,csvout

def read(p):return json.loads(p.read_text())
def main():
 root=OUT/'r7_continue';rows=read(CFG/'scoring_continue_r7.r1.json')['rows'];coverage=[];geometry=[];large=[];sources={}
 for r in rows:
  if r['family']=='r6':continue
  if r['family']=='base':
   check=OUT/'r7/baselines'/f"base7k_B173nb_b10_{r['prior']}_s0"/'verification7000.json' if r['iteration']==7000 else root/'post'/r['key']/'coverage.json'
   score=OUT/'r7/baselines'/f"base7k_B173nb_b10_{r['prior']}_s0"/'post7000/score.json' if r['iteration']==7000 else root/'post'/r['key']/'score.json'
  else:
   run=Path(r['model'].replace('/ph',str(PH),1)).parent;check=run/f"verification{r['iteration']}.json";score=run/f"post{r['iteration']}/score.json"
   lg=run/f"model/check{r['iteration']}/large_background_descendants.json"
   if lg.exists():large.append(dict(key=r['key'],value=read(lg)));sources[str(lg)]=sha(lg)
  if check.exists():
   a=read(check);sources[str(check)]=sha(check)
   for stratum,v in a['strata'].items():coverage.append(dict(key=r['key'],prior=r['prior'],iteration=r['iteration'],stratum=stratum,**v))
  if score.exists():
   a=read(score);sources[str(score)]=sha(score)
   for v in a['result_vs_target']:geometry.append(dict(key=r['key'],prior=r['prior'],iteration=r['iteration'],**v))
 memory=root/'lod2_retry/runs/tg_B173nb_b10_LoD2_s0_r7/model/target_monitor/memory_1000.jsonl';mem=[json.loads(x) for x in memory.read_text().splitlines()] if memory.exists() else []
 payload=dict(at=stamp(),coverage=coverage,geometry=geometry,large_background_descendants=large,lod2_memory_per1000=mem,sources=sources,scientific_verdict=None);dump(DOC/'tables/continue_r7_record_only.json',payload);csvout('continue_r7_pixel_coverage',coverage);csvout('continue_r7_judgment_region_geometry',geometry)
 labels={'all':'전체','prior':'사전 패치','background':'배경 MVS','prior_roof':'사전 지붕','prior_wall':'사전 벽','region_0':'관측 없음','region_5':'사라짐','region_1':'일치','region_2':'보존','region_3':'보정','prior_original':'원값','prior_replaced':'대체'}
 for prior in ['ALS','LoD2']:
  fig,axes=plt.subplots(2,1,figsize=(13,8));ks=list(dict.fromkeys(r['key'] for r in coverage if r['prior']==prior));xs=list(labels)
  for key in ks:
   data={r['stratum']:r for r in coverage if r['key']==key}
   for ax,field in zip(axes,['fraction','missing_fraction']):ax.plot(range(len(xs)),[100*data.get(x,{}).get(field) if data.get(x,{}).get(field) is not None else np.nan for x in xs],'-o',ms=3,label=key)
  for ax,lab in zip(axes,['목표 ±1.96σ 안, %','렌더 깊이 없음, %']):ax.set(xticks=range(len(xs)),xticklabels=list(labels.values()),ylabel=lab);ax.grid(alpha=.2);ax.legend(fontsize=7,ncol=2);ax.tick_params(axis='x',rotation=20)
  axes[0].set_ylim(0,100);fig.subplots_adjust(top=.87,bottom=.12,hspace=.4);save(fig,f'continue_r7_{prior}_pixel_coverage',f'{prior}: 같은 r7 목표 지도의 목표 따름',dict(rows=[r for r in coverage if r['prior']==prior]),'정기 기록 · 통과 문턱 아님 · 원반이 없는 사라짐 화소는 배경 MVS 목표로 집계')
  for replacement in ['all','original','replaced']:
   rr=[r for r in geometry if r['prior']==prior and r['replacement']==replacement];ks=list(dict.fromkeys(r['key'] for r in rr));fig,axes=plt.subplots(1,3,figsize=(15,4.8));regions=[0,5,1,2,3]
   for key in ks:
    d={r['region']:r for r in rr if r['key']==key}
    for ax,field in zip(axes,['result_within_tau_fraction','floating_fraction','no_surface_fraction']):ax.plot(range(5),[d[i][field]*100 if i in d and d[i][field] is not None else np.nan for i in regions],'-o',ms=3,label=key)
   d={r['region']:r for r in rr};axes[0].plot(range(5),[d[i]['target_within_tau_fraction']*100 if i in d and d[i]['target_within_tau_fraction'] is not None else np.nan for i in regions],'k--',label='목표 자체')
   for ax,lab in zip(axes,['결과 τ 안, %','뜬 면, %','면 없음, %']):ax.set(xticks=range(5),xticklabels=[labels[f'region_{i}'] for i in regions],title=lab,ylim=(0,100));ax.grid(alpha=.2);ax.tick_params(axis='x',rotation=25)
   axes[-1].legend(fontsize=6);fig.subplots_adjust(top=.80,bottom=.20,wspace=.3);save(fig,f'continue_r7_{prior}_regions_{replacement}',f'{prior}: 판단 영역별 기록 ({replacement})',dict(rows=rr),'지금 채점 메시 · 원래 넓이 가중 셈 · 사라짐은 목표 자체가 없음 · 참값 열두 칸 본표와 별도')
 if mem:
  fig,axes=plt.subplots(1,2,figsize=(12,4.5))
  for key,lab in [('0','배경'),('1','패치'),('2','풀림')]:axes[0].plot([m['iteration'] for m in mem],[m['tags'][key]/1e6 for m in mem],'-o',ms=3,label=lab)
  for key,lab in [('cuda_allocated_bytes','현재 할당'),('peak_cuda_allocated_bytes','누적 최대 할당'),('peak_cuda_reserved_bytes','누적 최대 예약')]:axes[1].plot([m['iteration'] for m in mem],[m[key]/2**30 for m in mem],'-o',ms=3,label=lab)
  axes[0].set(xlabel='반복',ylabel='가우시안 (백만)');axes[1].set(xlabel='반복',ylabel='GiB')
  for ax in axes:ax.legend(fontsize=8);ax.grid(alpha=.2)
  fig.subplots_adjust(top=.82,bottom=.18,wspace=.3);save(fig,'continue_r7_LoD2_memory','LoD2 독립 이어 학습: 1,000회 기록',mem,'관측용 기록 · 초기화·최적화·난수·감시 문턱 변경 없음')
 p=root/'diagnostics/ALS/full_pixel_enumeration_r1/summary.json';full=read(p);fig,axes=plt.subplots(1,2,figsize=(11,4.6));axes[0].bar(['r6 규칙이면 풀림','뜨는 면 화소에 최대 기여'],[full['candidate_gaussians'],full['would_release_and_float_max_unique_gaussians']],color=['#d69b3a','#437ea9']);axes[0].set_ylabel('가우시안 수');axes[1].bar(['해당 가우시안의 최대 기여 화소','뜬 면 패치에 연결된 화소'],[full['all_candidate_max_pixels'],full['floating_footprint_pixels']],color=['#d69b3a','#437ea9']);axes[1].set_ylabel('화소 수')
 for ax in axes:
  for bar in ax.patches:ax.text(bar.get_x()+bar.get_width()/2,bar.get_height(),f'{bar.get_height():,.0f}',ha='center',va='bottom')
  ax.set_ylim(0,ax.get_ylim()[1]*1.12);ax.tick_params(axis='x',labelsize=8)
 fig.subplots_adjust(top=.8,bottom=.21,wspace=.3);save(fig,'continue_r7_ALS_counterfactual_full','r7 항공 LiDAR: r6 규칙을 대입한 화소 전수 검사',full,'203개 학습 영상 · 원본 ALS 패치 접선 사용 · 깊이 연결 허용 0.25 m · 측정 패치 밖은 뜬 면 여부를 추정하지 않음')
 print('RECORD_ONLY_TABLES_FIGURES',len(coverage),len(geometry),flush=True)
if __name__=='__main__':main()
