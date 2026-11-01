"""Final user-requested diagnostic comparison, source figures and place-stratum report."""
import csv
import numpy as np
from matplotlib.colors import ListedColormap
from common import *
from report_stage0 import plt,save,csvout
LABEL={'small_raised':'작은 구조물','edge_band':'가장자리','glass_or_textureless':'유리·무늬 없음','other':'그 밖','photo_missing':'사진 없음'}
STRATA={'all':'전체','prior':'사전 패치','background':'배경 MVS','prior_roof':'사전 지붕','prior_wall':'사전 벽','region_0':'관측 없음','region_1':'일치','region_2':'보존','region_3':'보정','prior_original':'사전 원값','prior_replaced':'사전 대체'}
SITES={'B0_b10':'B0','B173nb_b10':'B173 주변','B173_b0':'B173만','R1rep_b10':'R1'}
def read(p):return json.loads(p.read_text())
def zload(p):
 with np.load(p) as z:return {k:z[k] for k in z.files}
def pct(v):return '확인 불가' if v is None else f'{100*v:.2f}%'
def main():
 text=['# 7,000회 중단 후 비교·원인 점검 · r5','',
 '두 판의 7,000회 중단과 목표 따름 80% 기준을 유지했다. 나머지 여섯 판은 시작하지 않았다. 기존 모델 비교와 저장 모델 진단, 단계 0의 자리별 판단 집계를 마쳤다. 최적화 상태가 없어 기록용 이어 학습은 실행하지 않았다. 모든 새 수치와 그림은 [이 발주에서 냄]이며 scientific_verdict는 null이다.','',
 '## 1. 같은 목표 지도로 센 기존 모델 비교','',
 '모든 판에 r4n과 같은 203개 학습 영상, 같은 목표 깊이·σ 지도, 같은 화소 구분을 적용했다. 깊이 없는 화소도 분모에 포함했다. 기존 깊이 손실 기준선에는 7,000회 모델이 없어 30,000회를, 영상만 쓴 2DGS에는 저장된 7,000회를 썼다. 학습 횟수가 다르므로 같은 학습량의 성능 비교로 해석하지 않는다. 기준선의 재학습은 0회다.','']
 rows=[];baselines={k:read(OUT/'r5/baselines'/k/'coverage.json') for k in ['depth_ALS','depth_LoD2','image_2dgs']}
 for prior in ['ALS','LoD2']:
  current=read(OUT/'r4n/runs'/f'tg_B173nb_b10_{prior}_s0/verification7000.json')['strata'];depth=baselines['depth_'+prior]['strata'][prior];image=baselines['image_2dgs']['strata'][prior]
  text += [f'### {prior}','','| 화소 구분 | r4n 7,000회 | 깊이 기준선 30,000회 | 영상 2DGS 7,000회 |','|---|---:|---:|---:|']
  for label in STRATA:
   text.append(f'| {STRATA[label]} | {pct(current[label]["fraction"])} | {pct(depth[label]["fraction"])} | {pct(image[label]["fraction"])} |')
   for method,it,s in [('r4n',7000,current),('depth_baseline',30000,depth),('image_2dgs',7000,image)]:rows.append(dict(prior=prior,method=method,iteration=it,stratum=label,**s[label]))
  fig,ax=plt.subplots(figsize=(10,4));keys=['all','prior','background','prior_roof','prior_wall'];xx=np.arange(len(keys))
  for i,(name,s,color) in enumerate([('r4n · 7천',current,'#ad477b'),('깊이 기준선 · 3만',depth,'#428a92'),('영상 2DGS · 7천',image,'#c29c4a')]):
   vals=[s[k]['fraction'] for k in keys];ax.bar(xx+(i-1)*.25,[0 if x is None else 100*x for x in vals],.25,label=name,color=color)
  ax.axhline(80,c='black',ls='--',lw=1);ax.set(ylim=(0,100),ylabel='목표 ±1.96σ 안 (%)');ax.set_xticks(xx,[STRATA[k] for k in keys]);ax.legend(loc='upper right',fontsize=8)
  if prior=='ALS':ax.text(4,3,'벽 목표 없음',ha='center',fontsize=8)
  fig.subplots_adjust(top=.8,bottom=.2);save(fig,f'r5_{prior}_baseline_coverage',f'{prior}: 저장 모델을 같은 목표 지도로 비교했다',[r for r in rows if r['prior']==prior],'점선 80%는 그대로 유지 · 깊이 기준선 3만 회, 나머지 7천 회 · 학습량이 다른 참고 비교')
  text += ['',f'![같은 목표 지도 비교](figures/r5_{prior}_baseline_coverage.png)','']
 csvout('baseline_coverage_r5',rows);dump(DOC/'tables/baseline_coverage_r5.json',dict(rows=rows,scientific_verdict=None))
 text += ['## 2. 목표 폭 밖 사전 화소의 앞·뒤와 최대 기여 출신','',
 '최대 기여는 실제 CUDA 렌더 순서에서 개별 가우시안의 α×누적 투과율이 가장 큰 항목이다. 같은 값이면 먼저 나타난 항목을 썼다. 진단용 사본의 왜곡 출력 채널에 번호만 기록했고, 두 판 각 203개 깊이 배열이 기존 r4n 배열과 바이트 단위로 같았다. 출신 묶음의 합계 기여를 대신 쓰지 않았다. 앞은 렌더 깊이가 목표 폭보다 카메라 쪽, 뒤는 반대쪽이다. 이 구분과 출신 연관만으로 인과를 확정하지 않는다.','']
 rep=next(r for r in read(CFG/'representatives_v1.json')['rows'] if r['id']==1);camera=rep['camera']['name'];crossrows=[]
 for prior in ['ALS','LoD2']:
  r=read(OUT/'r5/failures'/prior/'summary.json');text += [f'### {prior}','',f"사전 패치 화소 {r['totals']['prior_pixels']:,}개 중 폭 밖 {r['totals']['outside']:,}개. 깊이 없음 {r['totals']['missing']:,}개.",'','| 방향 | 그 자리 패치 | 다른 패치 | 배경 | 확인 불가 |','|---|---:|---:|---:|---:|']
  for i,name in enumerate(['앞 · 가림 쪽','뒤 · 비침 쪽']):
   text.append('| '+name+' | '+' | '.join(pct(x) for x in r['cross_fraction_of_outside'][i])+' |')
   for j,lineage in enumerate(r['lineage']):crossrows.append(dict(prior=prior,direction=r['direction'][i],lineage=lineage,pixels=r['cross_counts'][i][j],fraction_of_outside=r['cross_fraction_of_outside'][i][j],fraction_of_all_prior=r['cross_fraction_of_all_prior'][i][j]))
  text += ['','표의 분모는 해당 판의 폭 밖 사전 화소 전체다. 전체 사전 화소를 분모로 한 값과 원 화소 수는 CSV에 함께 있다.','']
  pixels=zload(OUT/'r5/failures'/prior/'pixels'/f'{camera}.npz');m=zload(OUT/'r2/stage1'/f'B173nb_b10_{prior}/maps'/f'{camera}.npz');rend=zload(OUT/'r4n/runs'/f'tg_B173nb_b10_{prior}_s0/model/check7000/renders'/f'{camera}.npz')
  cat=np.full(m['depth'].shape,-1);outside=pixels['front_back']>=0;cat[outside]=pixels['front_back'][outside]*3+pixels['lineage'][outside]
  colors=['#e8e8e8','#f4b3cc','#db7258','#6eabd5','#9b577e','#8f422e','#285c92'];fig,axes=plt.subplots(1,2,figsize=(12,4.8));axes[0].imshow(rend['rgb']);axes[0].set_title('7,000회 고정 영상');im=axes[1].imshow(cat,cmap=ListedColormap(colors),vmin=-1.5,vmax=5.5);axes[1].set_title('폭 밖 화소의 방향 × 최대 기여 출신')
  from matplotlib.patches import Patch
  labs=['폭 안·사전 목표 없음','앞·그 자리','앞·다른 패치','앞·배경','뒤·그 자리','뒤·다른 패치','뒤·배경'];axes[1].legend(handles=[Patch(color=c,label=l) for c,l in zip(colors,labs)],loc='upper left',bbox_to_anchor=(1,1),fontsize=7)
  for ax in axes:ax.axis('off')
  fig.subplots_adjust(top=.82,bottom=.17,wspace=.03);save(fig,f'r5_{prior}_front_back_lineage',f'{prior}: 목표 폭 밖인 사전 패치 화소의 최대 기여 출신',dict(camera=camera,full_counts=r['cross_counts'],fixed_view_outside=int(outside.sum())), '고정 영상 한 장 · 회색은 이 표의 대상 밖 · 각 화소에서 개별 αT 최대 가우시안의 불변 부모 패치로 구분')
  counts=np.array(r['sigma_hist_counts']);fig,ax=plt.subplots(figsize=(10,4));xx=np.arange(counts.shape[1]);bins=r['sigma_hist_bins'];names=[f'{a:g}–{b:g}' if isinstance(b,(int,float)) else f'≥{a:g}' for a,b in zip(bins[:-1],bins[1:])]
  for i,(name,color) in enumerate([('앞','#cb6a60'),('뒤','#478ab9')]):ax.bar(xx+(i-.5)*.36,100*counts[i]/r['totals']['outside'],.36,label=name,color=color)
  ax.set_xticks(xx,names);ax.set(xlabel='|렌더 깊이 − 목표 깊이| / σ',ylabel='폭 밖 사전 화소 전체 대비 (%)');ax.legend();fig.subplots_adjust(top=.8,bottom=.2)
  save(fig,f'r5_{prior}_outside_sigma',f'{prior}: 목표를 벗어난 거리의 σ 배수 분포',r['sigma_hist_counts'],'폭 경계는 1.96σ · 가로축 구간 폭은 서로 다름 · 범위 밖 초과량은 표시된 값에서 1.96을 뺀 값')
  text += [f'![방향과 최대 기여 계보](figures/r5_{prior}_front_back_lineage.png)','',f'![σ 배수 분포](figures/r5_{prior}_outside_sigma.png)','']
 csvout('outside_pixels_lineage_r5',crossrows)
 text += ['## 3. 두 출신의 이동과 씨앗·영상 범위','','긴 축 크기는 활성화된 접선 두 축 중 큰 값이며 지름이 아니다. 부모의 목표 점과 단위 법선을 기준으로 법선 이동과 접선 이동을 분해했다. 처음 1 m 초과 배경 계보의 별도 표는 r4n 점검 보고서에 유지하고, 여기서는 전체 배경과 전체 사전 출신을 같은 방식으로 센다.','']
 movement=[]
 for prior in ['ALS','LoD2']:
  r=read(OUT/'r5/movement'/prior/'summary.json');text += [f'### {prior}','','| 출신 | 남은 수 | 접선 >1 m | 긴 축 중앙값 / 최대 (m) | 불투명도 중앙값 | 법선 이동 중앙값 / 최대 (m) | 접선 이동 중앙값 / 최대 (m) |','|---|---:|---:|---:|---:|---:|---:|']
  for name,label in [('background','배경'),('prior','사전 패치')]:
   q=r['origins'][name];text.append(f"| {label} | {q['gaussians']:,} | {q['tangent_over_1m']:,} | {q['size_max_axis_m']['median']:.3f} / {q['size_max_axis_m']['max']:.3f} | {q['opacity']['median']:.4f} | {q['normal_displacement_abs_m']['median']:.3f} / {q['normal_displacement_abs_m']['max']:.3f} | {q['tangent_displacement_m']['median']:.3f} / {q['tangent_displacement_m']['max']:.3f} |")
   movement.append(dict(prior=prior,origin=name,**q))
  text += ['','최솟값·95% 분위와 1 m 초과 집단의 크기·불투명도도 JSON에 있다. 각 그림은 전체 이동 범위, 입력 지역의 참값·사전 면, 같은 자리에 이동 중심을 겹친 보기 순서다. 검정은 실제 참값 점, 주황은 사전 패치 면 표본이다.','']
  for name in ['background','prior']:
   for view in ['top','oblique']:text += [f'![출신별 이동 3차원 보기](figures/r5_{prior}_{name}_movement_{view}.png)','']
  text += [f'![처음 씨앗과 영상 시야](figures/r5_{prior}_seed_view_extent.png)','',
   f"배경 씨앗 {r['extent']['background_seeds']:,}개와 기준선 처음 점 {r['extent']['baseline_initial_points']:,}개를 모두 표시했다. 영상 시야는 입력 지붕 중앙 높이 평면과 카메라 깊이 0.2~300 m의 교차다. 203개 중 {r['extent']['plane_intersecting_views']}개가 그 평면과 교차했다. 실제 가림을 반영한 관측 넓이와 구분한다.",'']
 dump(DOC/'tables/movement_r5.json',dict(rows=movement,scientific_verdict=None))
 text += ['## 4. 뜬 면·결과와 목표의 τ 비교','','현재 TSDF와 고정된 채점 규칙을 그대로 적용했다. 두 판 모두 2,048개 독립 첫 면 광선과 넓이 재계산을 통과했다. 항공 LiDAR의 보고서 메타데이터 누락은 보완했고, 보완 전후 메시 SHA-256이 같았다.','', '| 사전 정보 | 칸 0~3 뜬 면 | 뜬 면 넓이 / 평가 넓이 (m²) |','|---|---:|---:|']
 for prior in ['ALS','LoD2']:
  r=read(OUT/'r4n/runs'/f'tg_B173nb_b10_{prior}_s0/verification_post7000.json');text.append(f"| {prior} | {pct(r['floating_fraction'])} | {r['floating_area_m2']:.3f} / {r['evaluation_area_m2']:.3f} |")
 text += ['','결과와 목표의 τ 비교, 고정 단면, 배경 출신 뜬 면 지도는 [7,000회 점검](단계1_7000회_점검_r4n.md)에 있다. 해당 지도는 출신별 기여의 합계이고, 2절의 개별 최대 기여 지도와 계산이 다르다.','',
 '## 5. 기록용 이어 학습','','두 판 모두 **NOT_RUN_NO_OPTIMIZER_STATE**. 실행 명령에는 `--checkpoint_iterations`가 없고 기본값은 빈 목록이다. 전체 상태 자동 저장은 기본 8,000·30,000회라 7,000회 중단 전에 발생하지 않았다. 전체 모델 폴더에 `.pt`, `.pth`, `.ckpt` 상태 파일이 없었고, PLY와 스냅샷에는 Adam의 모멘트·매개변수 묶음 상태가 없다. 이를 새로 초기화하면 같은 최적화 상태에서 잇는 것이 아니므로 사용자 결정 6에 따라 실행하지 않았다. 15,000·30,000회 `_rec` 목표 따름과 계보 표는 확인 불가이며 0이나 통과로 적지 않는다.','',
 '## 6. 자리별 판단 정확도','','[자리별 보고서](자리별_판단점검_r5.md)와 `tables/places_r5_*.json`, 전체 CSV를 함께 제공한다. 분류는 MVS·사전 정보·사진 입력으로만 만들고, 참값 칸은 집계와 대표 단면을 고른 뒤에만 사용했다. 작은 구조물 → 가장자리 → 유리·무늬 없음 → 그 밖 순서이며, 남은 그 밖 중 사진 곡선이 없는 곳은 사진 없음으로 별도 행을 냈다. 앞선 세 자리에도 사진 없음 넓이를 별도 열로 기록했다.','',
 '## 7. 기록과 남은 범위','','설정과 사용자 결정은 `diagnostics_r5.json` 및 잠금 파일에 있다. 80%, 배경 크기·묶기, 분할 자식 목표, 깊이 손실 무게를 바꾸지 않았다. 이 점검 묶음 이후에는 진행하지 않는다. 확인용 패치 상세, 큰 모델·메시·지도는 ZIP 밖의 지정 경로에 보존하며, ZIP의 외부 자료 manifest에 재계산 경계를 적는다.','']
 (DOC/'중단후_비교진단_r5.md').write_text('\n'.join(text).rstrip()+'\n')
 print('REPORT_R5_DONE',flush=True)
if __name__=='__main__':main()
