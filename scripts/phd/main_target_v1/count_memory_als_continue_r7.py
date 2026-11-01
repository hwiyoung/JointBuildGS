"""Read existing iteration traces only; do not infer missing lineage or GPU observations."""
import json
from pathlib import Path
from common import *
from report_stage0 import plt,save,csvout

def lines(p):return [json.loads(x) for x in p.read_text().splitlines()]
def main():
 root=OUT/'r7_continue/diagnostics/ALS';old=OUT/'r7/runs/tg_B173nb_b10_ALS_s0_r7/model';continued=OUT/'r7_continue/attempt2/runs/tg_B173nb_b10_ALS_s0_r7/model';r6=OUT/'r6/runs/tg_B173nb_b10_ALS_s0_r6/model';baseline=PH/'main_stage3_v1/PHD-MAIN-STAGE3-v1/runs/B173nb_b10/nojudge_ALS_s0/model'
 sources={};curves={}
 for label,files in [('r7',[old/'target_monitor/curve.jsonl',continued/'target_monitor/curve.jsonl']),('r6',[r6/'target_monitor/curve.jsonl']),('nojudge_ALS_s0',[baseline/'jbgs_trace.jsonl'])]:
  data=[]
  for i,p in enumerate(files):
   q=lines(p);data += [r for r in q if (label!='r7' or ((i==0 and r['iteration']<=7000) or (i==1 and r['iteration']>7000))) and (label!='r6' or r['iteration']<=9000)];sources[str(p)]=sha(p)
  curves[label]={r['iteration']:r for r in data}
 table=[]
 for label,byit in curves.items():
  for it,r in sorted(byit.items()):
   if it%1000:continue
   tags=r.get('tags');table.append(dict(method=label,iteration=it,gaussians=r['gaussians'],background=tags.get('0') if tags else None,patch=tags.get('1') if tags else None,released=tags.get('2') if tags else None,lineage_status='available' if tags else 'not recorded; protected count is not a lineage tag',peak_cuda_allocated_GiB=r.get('peak_cuda_allocated_bytes',0)/2**30 if 'peak_cuda_allocated_bytes' in r else None,peak_cuda_reserved_GiB=r.get('peak_cuda_reserved_bytes',0)/2**30 if 'peak_cuda_reserved_bytes' in r else None))
 last=curves['r7'][14100];six=curves['r7'][6000];lasttags=[]
 for tag,name in [('0','background'),('1','patch'),('2','released')]:
  a,b=last['tags'][tag],six['tags'][tag];lasttags.append(dict(tag=name,count_14100=a,count_6000=b,multiple=a/b if b else None))
 brange=[dict(iteration=i,gaussians=r['gaussians'],peak_cuda_allocated_GiB=r['peak_cuda_allocated_bytes']/2**30,peak_cuda_reserved_GiB=r['peak_cuda_reserved_bytes']/2**30) for i,r in curves['nojudge_ALS_s0'].items() if 14000<=i<=15000];comparison=[]
 for it in [14000,14100]:
  a,b=curves['r7'][it]['gaussians'],curves['nojudge_ALS_s0'][it]['gaussians'];comparison.append(dict(iteration=it,r7=a,baseline=b,multiple_r7_over_baseline=a/b,difference=a-b,relative_increase_pct=100*(a/b-1)))
 result=dict(at=stamp(),status='COMPLETE_READ_ONLY_COMPARISON',sources=sources,per_1000=table,baseline_14000_to15000=brange,r7_14100=lasttags,r7_total_14100=last['gaussians'],r7_total_6000=six['gaussians'],r7_total_multiple=last['gaussians']/six['gaussians'],same_iteration_comparison=comparison,baseline_peak_note='GPU peak counters are cumulative since process start at each logged iteration; not isolated interval peaks',causal_identification='not determined by these recorded comparisons; no same-seed replicate training performed',als_training='NOT_RESTARTED; submit recorded count difference for decision under 21:50 item 3',scientific_verdict=None)
 dump(root/'count_memory_comparison.json',result);dump(DOC/'tables/continue_r7_ALS_count_memory.json',result);csvout('continue_r7_ALS_counts_1000',table);csvout('continue_r7_ALS_baseline_memory_14000_15000',brange);csvout('continue_r7_ALS_tags_14100',lasttags)
 fig,axes=plt.subplots(1,3,figsize=(15,4.7))
 for label,color in [('r7','#b3536c'),('r6','#438bb6'),('nojudge_ALS_s0','#56895f')]:
  rr=[r for r in table if r['method']==label and r['iteration']<=15000];axes[0].plot([r['iteration'] for r in rr],[r['gaussians']/1e6 for r in rr],'-o',ms=3,label=label,c=color)
 axes[0].set(xlabel='반복',ylabel='가우시안 (백만)',title='1,000회 간격');axes[0].legend(fontsize=7)
 for tag,color in [('background','#61a8a7'),('patch','#a94e83'),('released','#e09c36')]:
  rr=[r for r in table if r['method']=='r7'];axes[1].plot([r['iteration'] for r in rr],[r[tag]/1e6 for r in rr],'-o',ms=3,label=tag,c=color)
 axes[1].set(xlabel='반복',ylabel='가우시안 (백만)',title='r7 꼬리표별');axes[1].legend(fontsize=7)
 for field,lab in [('peak_cuda_allocated_GiB','할당 최대'),('peak_cuda_reserved_GiB','예약 최대')]:axes[2].plot([r['iteration'] for r in brange],[r[field] for r in brange],'-o',ms=3,label=lab)
 axes[2].set(xlabel='반복',ylabel='GiB',title='기준선 14,000~15,000회 GPU');axes[2].legend(fontsize=7);fig.subplots_adjust(top=.8,bottom=.2,wspace=.3);save(fig,'continue_r7_ALS_counts_memory','항공 LiDAR: 저장 기록의 수와 GPU 메모리',result,'기준선 꼬리표는 미기록 · GPU 최대는 실행 시작 이후 누적 최대 · 비교에서 원인을 확정하지 않음')
 doc=DOC/'항공LiDAR_r7_원인점검.md';L=['# 항공 LiDAR r7 기록·저장 상태 점검','',f'- 기록: {stamp()}. 학습 없음. scientific_verdict: null.','- 21:15 결정 4와 21:50 결정 2를 한 보고로 묶는다. 아래는 측정값이며 원인을 확정하지 않는다.','','## 가우시안 수 비교','','| 반복 | r7 | 기존 깊이 기준선 | r7 / 기준선 |','|---|---:|---:|---:|']
 for r in comparison:L.append(f'| {r["iteration"]:,} | {r["r7"]:,} | {r["baseline"]:,} | {r["multiple_r7_over_baseline"]:.3f} |')
 L+=['',f'- 기준선 15,000회: {brange[-1]["gaussians"]:,}개. 14,000~15,000회 기록의 할당 최대 {max(r["peak_cuda_allocated_GiB"] for r in brange):.3f} GiB, 예약 최대 {max(r["peak_cuda_reserved_GiB"] for r in brange):.3f} GiB. 누적 최대 기록이다.',f'- r7 마지막 건강 기록 14,100회: {last["gaussians"]:,}개, 6,000회 {six["gaussians"]:,}개의 {last["gaussians"]/six["gaussians"]:.3f}배.','','| 꼬리표 | 6,000회 | 14,100회 | 배수 |','|---|---:|---:|---:|']
 for r in lasttags:L.append(f'| {r["tag"]} | {r["count_6000"]:,} | {r["count_14100"]:,} | '+(f'{r["multiple"]:.3f}' if r['multiple'] is not None else '확인 불가')+' |')
 L+=['','![수와 GPU 메모리](figures/continue_r7_ALS_counts_memory.png)','','- 1,000회 전체 표: `tables/continue_r7_ALS_counts_1000.csv`. r6은 9,000회까지. 기준선의 배경·패치·풀림 꼬리표는 저장되지 않아 확인 불가로 둔다. 보호 수를 출신으로 대신 쓰지 않았다.','','## 설정·씨앗·다시 붙이기·뜬 면','','- r20→r21에서 달라진 파일은 5개다. 전체 파일별 SHA와 줄 차이는 전달 묶음의 `source_differences.json`, `source_changes.diff`에 있다. 설정 차이 29개는 `tables/continue_r7_ALS_config_changes.csv`, 바뀐 파일과 줄은 `tables/continue_r7_ALS_code_changes.json`에 모두 적었다.','- 배경 씨앗 555,259개는 두 판에서 위치가 바이트 단위로 같다. 패치 씨앗은 r6 50,518개, r7 50,391개다. 학습·평가 영상 순서, 7,000회 남은 영상 스택과 저장된 난수 상태는 두 판에서 같았다. 매 반복의 영상 이름은 저장되지 않아 전 구간 순서를 완전 대조할 수는 없다.','- 원본 씨앗 번호로 맞춘 50,391개 사전 씨앗은 초기 위치·크기·불투명도·법선·σ가 같다. 배경 555,259개의 위치·불투명도·법선·σ도 같고 처음 크기는 5개가 다르다. 세부 표는 `tables/continue_r7_ALS_initial_comparison.csv`와 `figures/continue_r7_ALS_initial_comparison.png`다.','- r7 패치 꼬리표 38,133개 중 r6의 0.5 m 규칙이면 47개가 풀린다. r7 목표와 원래 r6 목표를 각각 사용한 두 참고 셈의 수가 같았다.','- 그 47개가 최대 기여인 모든 1,562개 화소를 검사했다. 원본 ALS 격자 접선으로 복원한 뜬 면 패치와 깊이 0.25 m 안에서 연결된 것은 124개 화소, 가우시안 3개다. 면 위 정사각형으로 둔 이전 119화소 계산은 잘못된 면적 가정으로 대체되었으며 보존했다. 패치 면적 밖 화소에는 참값 뜬 면 표지를 추정하지 않았다. 중심 표본만 사용한 이전 참고 셈은 26개 화소·2개 가우시안이다.','- 출신 × 판단 영역 × 목표 반폭의 넓이 표와 그림: `tables/continue_r7_ALS_floating_cross.csv`·JSON, `figures/continue_r7_ALS_floating_cross.png`. 혼합과 확인 불가를 별도로 유지했다.','- 같은 씨앗의 새 학습 반복은 하지 않았다. 저장 상태에서 재개한 겹치는 구간도 모든 기록값이 같지는 않았다. 영상 순서·수·손실 비교는 `resume_and_rng.json`에 있다.','','## 추가 학습 상태','','- 14,100회의 r7 수는 같은 반복 기준선보다 약 78% 많다. 21:50 결정 3의 후속 결정을 받기 전까지 항공 LiDAR는 재개하지 않는다.','- 이 비교만으로 다시 붙이기 규칙, 실행 흔들림, 메모리 한계의 인과를 확정하지 않는다.','']
 doc.write_text('\n'.join(L));print('ALS_COUNT_MEMORY_DONE',comparison,lasttags,flush=True)
if __name__=='__main__':main()
