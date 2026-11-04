"""Stage-1 chapter-7 tables: primary training-view scores and preserved mesh checks."""
from common import *
from publish_tables import CELL_NAMES,NAMES
SITE='B173nb_b10';BASE=Path('/out');FT=PH/'main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1'
NAMES.update(FINALTRAIN_30000='본 방법 FINALTRAIN 30,000회',fusion_mvswalls='결합 + MVS 벽',judgment_mesh_mvswalls='판단 조합 + MVS 벽',oracle_mvswalls='상한 + MVS 벽')
FAMILIES=['prior','mvs','baseline_30000','GeoGS_30000','2DGS_30000','CDGS_30000','fusion','judgment_mesh','oracle','FINALTRAIN_30000']
def pct(x):return '확인 불가' if x is None else f'{100*x:.3f}'
def main():
 rows={k:[] for k in [3,4,5,6,7,8]};diagnostics=[];inputs=[]
 for prior in ['ALS','LoD2']:
  for family in FAMILIES+(['fusion_mvswalls','judgment_mesh_mvswalls','oracle_mvswalls'] if prior=='ALS' else []):
   key=f'{SITE}__{prior}__{family}';p=O/'scores'/key/'values.json';v=json.loads(p.read_text());base=dict(site=SITE,prior=prior,key=key,method=NAMES[family],source=str(p),source_sha256=sha(p),surface=v['mesh'],surface_sha256=v['mesh_sha256'],mesh_rule='original input surface' if family in ['prior','mvs'] else '203 training views, TSDF .05/.25 m, top50, eval crop',source_tag='[이 발주에서 냄]')
   diag={('n_result_sample_total' if k=='n_result' else k):x for k,x in v['diagnostic'].items()};rows[3].append(dict(base,**v['scene'],**diag))
   for c in v['cells']:
    row=dict(base,**c,cell_name=CELL_NAMES[c['cell']],**diag);rows[4].append(row)
    if family in ['baseline_30000','judgment_mesh','oracle','FINALTRAIN_30000','judgment_mesh_mvswalls','oracle_mvswalls']:rows[7].append(row)
   rows[5].extend(dict(base,**x) for x in v['offsets']);rows[8].append(dict(base,**v['band']))
   if family in ['prior','mvs']:inputs.append(dict(prior=prior,family=family,source_surface=v['mesh'],surface_sha256=v['mesh_sha256'],mode='기존 새 τ·cells_v2·기둥·400점/m² 채점과 점 위치 캐시 재사용; 재표본·재거리 계산 없음',original_score=str(BASE/'scores'/key/'values.json'),score_sha256=sha(p)))
   if family=='FINALTRAIN_30000':old=FT/'rescore/scores'/f'ft_{SITE}__{prior}/values.json'
   else:old=BASE/'scores'/key/'values.json'
   if old.exists() and family not in ['prior','mvs']:
    oldv=json.loads(old.read_text());diagnostics.append(dict(prior=prior,method=NAMES[family],role='메시 규칙 점검',preserved_final_source=str(old),preserved_final_sha256=sha(old),training_view_source=str(p),final_views=219,primary_views=203,final_scene=oldv['scene'],training_scene=v['scene'],difference_primary_minus_final={k:None if oldv['scene'][k] is None or v['scene'][k] is None else v['scene'][k]-oldv['scene'][k] for k in ['completeness','accuracy','gt_mean_m','result_mean_m']}))
 for p in sorted((D/'tables').glob('target_quality_*.json')):rows[6].extend(json.loads(p.read_text())['rows'])
 for k,rr in rows.items():
  assert all('r8' not in r.get('method','') for r in rr);table('b173_table'+str(k),rr)
 table('mesh_rule_check',diagnostics);table('input_reuse',inputs)
 lines=['| 항목 | 규칙 |','|---|---|','| 범위 | 단계 1 · B173 주변 × 항공 LiDAR·LoD2 |','| 결과 메시 | 학습 시점 203개 · 가상 시점 0개 · TSDF 0.05/0.25 m · 큰 덩어리 50개 · 평가 범위 자르기 |','| 입력 | 원래 면의 검증된 새 규칙 점수·점 위치 재사용 |','| 고정 | 학습·판단·τ·칸·기둥 규칙 변경 없음 |','| 옛 최종 메시 | [메시 규칙 점검](tables/mesh_rule_check.md)으로 보존 |','','| 표 3 · 사전 정보 | 방법 | 완전성 % | 정확성 % | 참값 거리 cm | 결과 거리 cm |','|---|---|---:|---:|---:|---:|']
 for r in rows[3]:lines.append('| '+' | '.join([r['prior'],r['method'],*[pct(r[k]) for k in ['completeness','accuracy','gt_mean_m','result_mean_m']]])+' |')
 lines+=['','| 표 4 · 사전 정보 | 방법 | 맞는 판단 칸 | 완전성 % | 정확성 % | 참값 거리 cm | 결과 거리 cm |','|---|---|---|---:|---:|---:|---:|']
 for r in rows[4]:lines.append('| '+' | '.join([r['prior'],r['method'],r['cell_name'],*[pct(r[k]) for k in ['completeness','accuracy','gt_mean_m','result_mean_m']]])+' |')
 lines+=['','- 표 3~8의 반올림 전 값·표본 수·면 경로·SHA-256: `tables/b173_table*.json`, `.csv`, `.md`.','- 본 방법: FINALTRAIN 30,000회, 씨앗 0. r8은 주 표에서 제외.','- scientific_verdict: null.'];(D/'B173주변_비교방법_채점.md').write_text('\n'.join(lines)+'\n');progress(f'학습 시점 메시 표 3~8 생성: 장면 {len(rows[3])}줄, 영역 {len(rows[4])}줄. 기존 최종 메시 값 {len(diagnostics)}줄을 메시 규칙 점검으로 연결.')
if __name__=='__main__':main()
