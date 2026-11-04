from common import *
rows=[]
for site in SITES:
 for prior in ['ALS','LoD2']:
  core=loadz(JA/'core_points'/f'{site}__{prior}.npz',['kind']);v=loadz(CELLS/f'{site}__{prior}.npz',['tau_v2_m'])
  roof=np.unique(v['tau_v2_m'][core['kind']==1]);assert len(roof)==1
  wall=roof if prior=='ALS' else np.unique(v['tau_v2_m'][core['kind']==2]);assert len(wall)==1
  rows.append(dict(site=site,prior=prior,roof_tau_m=float(roof[0]),wall_tau_m=float(wall[0]),source=str(CELLS/f'{site}__{prior}.npz'),sha256=sha(CELLS/f'{site}__{prior}.npz'),rule='surface_tau.by_wall; ALS uses inherited roof tau for all reference kinds'))
table('stage0/tau_values',rows)
top=json.loads((O/'stage0/complete.json').read_text())['top3'];out=[]
for r in top:
 explanation='핵심점의 MVS n<4 또는 비유한 평균으로 결측을 정의하지만, 원래 MVS 메시의 표면 존재와 전역 최근접 거리는 별개' if r['cell']==4 else '핵심점 법선 방향의 MVS 평균과 gt_p 차이로 칸2를 정하지만, 표면 채점은 참값 행과 원래 MVS 삼각형의 최근접 거리'
 out.append(dict(**r,confirmed_definition_difference=explanation,mvs_surface_in_column_pct=r['mvs_column_presence_fraction']*100,causal_contribution='분리 실험 없음; 각 차이의 기여율은 확인 불가',source='tau_cells.py:26-31; score_mesh.py:9-13; geometry.py:21-34'))
table('stage0/top3_definition_differences',out)
scene=json.loads((D/'tables/stage0/scene_tau.json').read_text())['rows']
table('stage0/scene_tau_by_basis',[dict(**r,cell_basis=b,note='scene population unchanged by cell labels') for r in scene for b in ['original','score']])
with (D/'tables/stage0/table4_all.csv').open() as f:values=list(csv.DictReader(f))
summary=json.loads((D/'tables/stage0/summary.json').read_text())['rows'];annotated=[]
for r in summary:
 v=next(v for v in values if v['site']==r['max_gap_site'] and v['prior']==r['max_gap_prior'] and int(v['cell'])==r['max_gap_cell'] and v['method']==r['method'] and v['cell_basis']==r['cell_basis'] and float(v['tau_multiplier'])==r['tau_multiplier'])
 annotated.append(dict(**r,max_gap_n_gt=int(v['n_gt']),max_gap_small=v['small']))
table('stage0/summary_size_annotations',annotated)
lines=['# 단계 0 추가 표','', 'scientific_verdict: null. 채점 기준 칸, τ 1배. 최대 차이의 칸이 작은 경우를 직접 표시했다. 기존 계산값은 그대로다.','', '| 방법 | 범위 | 최대 차이 %p | 자리 | 참값 점 |','|---|---|---:|---|---:|']
for r in annotated:
 if r['cell_basis']=='score' and r['tau_multiplier']==1:
  lines.append(f"| {r['method']} | {r['scope']} | {r['max_gap_pp']:.3f} | {r['max_gap_site']} {r['max_gap_prior']} 칸 {r['max_gap_cell']} | {r['max_gap_n_gt']} {r['max_gap_small']} |")
lines+=['','실제 지붕·벽 τ는 tables/stage0/tau_values.csv, 상위 세 어긋남의 정의 차이와 MVS 기둥 존재 비율은 top3_definition_differences.csv. 장면 전체는 칸을 바꿔도 분모가 같아 (가)·(나)의 값이 같으며 scene_tau_by_basis.csv에 각각 표시했다.']
(D/'단계0_추가표.md').write_text('\n'.join(lines)+'\n')
