"""Candidate speed/parity evidence; no scientific verdict and no training use."""
import csv
import numpy as np
from common import *
from report_stage0 import plt
import rfix_continue_report as V
ROOT=OUT/'rfix_speed';D=DOC/'rfix_continue'
def main():
 cfg=V.read(CFG/'rfix_speed.json');rows=[];views=[];add=[];grad=[];sass=[];units=[];repeat_grad=[]
 rank=V.read(ROOT/'rank_refinement/ranking_complete.json');assert rank['status']=='PASS'
 refined=set(V.read(CFG/'rfix_speed_rank_full.json')['states'])
 for r in cfg['states']:
  key=r['key'];a=V.read(ROOT/'states'/key/'result.json');b=V.read(ROOT/'gradients'/key/'result.json');add_root=ROOT/('rank_refinement/addends' if key in refined else 'addends');c=V.read(add_root/key/'result.json');assert a['status']==b['status']==c['status']=='PASS'
  assert len(a['records'])==203 and len(b['rows'])==30 and len(c['rows'])==20
  times=np.array([[p['seconds'] for p in v['performance']] for v in a['records']]);over=np.array([[p['overlaps'] for p in v['performance']] for v in a['records']]);buffers=np.array([[p['binning_bytes'] for p in v['performance']] for v in a['records']]);vals=[p['relative_l2'] for v in b['rows'] for p in v['parameters'].values()]
  if key in refined:
   repeat=V.read(ROOT/'rank_refinement/gradients'/key/'result.json');assert repeat['status']=='PASS' and len(repeat['rows'])==30
   repeat_grad += [dict(state=key,camera=v['camera'],parameter=k,relative_l2=p['relative_l2'],pass_=p['pass_']) for v in repeat['rows'] for k,p in v['parameters'].items()]
   vals += [p['relative_l2'] for v in repeat['rows'] for p in v['parameters'].values()]
  rows.append(dict(state=key,views=203,all_outputs_byte_equal=all(all(t['byte_equal'] for t in v['comparison'].values()) for v in a['records']),original_median_ms=float(np.median(times[:,0])*1000),approved_median_ms=float(np.median(times[:,1])*1000),speed_median_ms=float(np.median(times[:,2])*1000),approved_over_speed_median=float(np.median(times[:,1])/np.median(times[:,2])),speed_total_overlap_over_original=float(over[:,2].sum()/over[:,0].sum()),speed_maximum_binning_GiB=float(buffers[:,2].max()/2**30),max_relative_l2=max(vals),addend_rows=20,addends_byte_equal=all(v['byte_equal'] for v in c['rows'])))
  for v in a['records']:
   d=dict(state=key,camera=v['camera'],pass_=v['pass_'])
   for p in v['performance']:
    d.update({p['variant']+'_'+k:p[k] for k in ['seconds','overlaps','binning_bytes','peak_allocated_bytes']})
   views.append(d)
  grad += [dict(state=key,camera=v['camera'],parameter=k,relative_l2=p['relative_l2'],pass_=p['pass_']) for v in b['rows'] for k,p in v['parameters'].items()]
  add += [dict(state=key,**v) for v in c['rows']]
 for label in ['target','imageonly','geogs']:
  u=V.read(ROOT/'units_r2'/label/'result.json');assert u['status']=='PASS';units += [dict(build=label,case=r['case']['name'],pass_=r['pass_'],max_abs=r['max_abs'],radii_equal=r['radii_equal'],original_overlaps=r['original_overlaps'],speed_overlaps=r['fixed_overlaps']) for r in u['rows']]
  s=V.read(ROOT/'sass_audit'/label/'result.json');native=[v for v in s['rows'] if 'renderCUDA' in v['kernel'] or 'preprocessCUDA' in v['kernel']];assert len(native)==4 and all(v['instruction_listing_equal'] for v in native);sass += [dict(build=label,**v) for v in native]
 for name,data in [('speed_summary',rows),('speed_views',views),('speed_gradients',grad),('speed_addends',add),('speed_units',units),('speed_native_kernels',sass),('speed_ranking',rank['rows']),('speed_ranking_repeat_gradients',repeat_grad)]:V.table(name,data)
 fig,axes=plt.subplots(1,2,figsize=(15,5));xx=np.arange(len(rows))
 for dx,k,label in [(-.25,'original_median_ms','원본'),(0,'approved_median_ms','이번 학습 빌드'),(.25,'speed_median_ms','속도 후보')]:axes[0].bar(xx+dx,[r[k] for r in rows],width=.25,label=label)
 axes[0].set(xticks=xx,xticklabels=[r['state'] for r in rows],ylabel='203장 렌더 시간 중앙값 (ms)');axes[0].tick_params(axis='x',rotation=50,labelsize=7);axes[0].legend();axes[1].scatter([r['approved_seconds'] for r in views],[r['speed_seconds'] for r in views],s=3,alpha=.4);mx=max(max(r['approved_seconds'],r['speed_seconds']) for r in views);axes[1].plot([.001,mx],[.001,mx],'k--');axes[1].set(xscale='log',yscale='log',xlabel='이번 학습 빌드 렌더 시간 (초)',ylabel='속도 후보 렌더 시간 (초)');V.save(fig,'speed_runtime','별도 속도 후보: 같은 상태·영상의 렌더 시간',dict(summary=rows,views=views))
 fig,ax=plt.subplots(figsize=(11,5));ax.bar(xx,[r['max_relative_l2'] for r in rows]);ax.axhline(1e-4,color='red',ls='--',label='새 기준 1e-4');ax.set(yscale='log',xticks=xx,xticklabels=[r['state'] for r in rows],ylabel='상태별 상대 L2 최댓값');ax.tick_params(axis='x',rotation=45,labelsize=8);ax.legend();V.save(fig,'speed_gradient','별도 속도 후보: 새 기울기 기준',rows)
 lines=['# 렌더러 속도 후보 검증','', 'scientific_verdict: null','', '이 빌드는 준비·검증만 했다. r8 LoD2 이어 학습에는 적용하지 않았다. 작은 원래 사각형(16타일 이하)은 등록을 유지하고, 큰 사각형은 4×4타일 묶음의 보수적 구간 검사 후 개별 타일 검사를 한다. 반환 반지름과 수치 커널은 그대로다. 작은 사각형에서는 실제 기여가 없는 타일을 일부 유지할 수 있다.','', '렌더 출력·반지름: 8개 상태 × 203장 모두 바이트 단위 일치. 기울기: 8 × 30장 × 7항목 모두 상대 L2 ≤ 1e-4. 상태별 최대 차 20개 행의 화소별 덧셈 입력항: 160개 모두 바이트 단위 일치. 합성 4경우 × 3빌드: 12개 통과. 수치 커널 기계어: 12개 일치.','', '[상태별 표](tables/speed_summary.md) · [영상별 부하](tables/speed_views.csv) · [기울기](tables/speed_gradients.csv) · [입력항](tables/speed_addends.csv)','', '시간은 같은 프로세스에서 원본·현재 학습용·속도 후보 순으로 렌더 호출 전후 CUDA를 동기화해 잰 값이다. 기여 재집계와 디스크 쓰기 시간은 제외했다.','', '![시간](figures/speed_runtime.png)','', '![기울기](figures/speed_gradient.png)','', 'CDGS는 기존 준비용 차이 파일만 있으며 실행된 저장 상태가 없다. 이번 수치 대조 범위는 저장 상태가 있는 2DGS 계열 세 빌드다.']
 lines += ['', '두 상태(r8 LoD2 중단, GeoGS LoD2)는 기존 요약 순위만으로 최대 차 20개 행을 증명할 수 없어 같은 30장 기울기를 다시 기록했다. 전역 64개 행을 정확히 보존한 순위에서 20개를 골랐으며, 이 두 상태의 최종 입력항 표는 보강된 순위를 사용한다. 기존 결과와 추가 420개 상대 L2 비교는 모두 보존했다. [순위 증명](tables/speed_ranking.md) · [추가 기울기](tables/speed_ranking_repeat_gradients.csv).']
 (D/'속도후보_검증.md').write_text('\n'.join(lines)+'\n');dump(ROOT/'VALIDATION.json',dict(at=stamp(),status='PASS',render_views=1624,gradient_comparisons=1680,ranking_repeat_gradient_comparisons=len(repeat_grad),addend_rows=160,total_probed_rows=200,ranking_verified=True,synthetic_cases=12,native_kernels=12,training_use=False,summary=rows,scientific_verdict=None));print('SPEED_VALIDATION_PASS')
if __name__=='__main__':main()
