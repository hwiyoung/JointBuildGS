"""Assemble measurements and execution state; no scientific verdict or causal claim."""
import sys,csv
import numpy as np
from common import *
from report_stage0 import plt,save,csvout

def read(p):return json.loads(p.read_text())
def pct(v):return '확인 불가' if v is None else f'{100*v:.2f}'
def num(v):return '확인 불가' if v is None else f'{v:.2f}'

def main():
 cfg=read(CFG/'scoring_continue_r7.r1.json');axcfg=read(REPO/'configs/phd/main_axes71_v2/axes71_v2.json');root=OUT/'r7_continue';records=[];flat=[];available=[];wanted=cfg['rows'];states=[]
 for row in wanted:
  for kind in ['current','final']:
   p=root/'scoring'/row['key']/kind/'values.json'
   if p.exists():
    a=read(p);assert a['status']=='PASS';available.append((row,kind,a));states.append(dict(key=row['key'],kind=kind,status='PASS',mesh_sha256=a['mesh_sha256']))
    for cell in ['all']+axcfg['cells']['order']:
     b=a['metrics'][cell];surface=a['surface'][cell];flat.append(dict(key=row['key'],prior=row['prior'],method=row['family'],iteration=row['iteration'],mesh_kind=kind,cell=cell,R_tau=b['gt'].get('R_tau'),P_tau=b['res']['E'].get('P_tau'),gt_mean_cm=b['gt'].get('mean'),result_mean_cm=b['res']['E'].get('mean'),n_gt=b['gt'].get('n_gt'),n_result=b['res']['E'].get('n'),excluded_result=b['res']['E'].get('excluded'),floating_fraction=surface['floating_fraction'],no_surface_fraction=surface['no_surface_fraction'],scored_patch_area_m2=surface['area_m2'],status=b['status']))
   else:
    state='NOT_REACHED_TRAINING_STOPPED' if row['family']=='r7' and row['iteration']>7000 and (row['prior']=='ALS' or (root/'lod2_retry/STOP_LoD2.json').exists()) else 'PENDING'
    states.append(dict(key=row['key'],kind=kind,status=state))
 # Existing comparison values are copied, with their original mixed-view provenance.
 axroot=PH/'main_axes71_v2/PHD-MAIN-AXES71-v2';sources={};comparisons={}
 for filename in ['a3_metrics.json','a4_axes.json','a6_clumps.json']:
  p=axroot/'tables'/filename;a=read(p);sources[filename]=sha(p)
  if filename!='a6_clumps.json':comparisons[filename]={f'B173nb_b10/{prior}':a['data'][f'B173nb_b10/{prior}'] for prior in ['ALS','LoD2']}
  else:comparisons[filename]={part:{f'B173nb_b10/{prior}':a['data'][part].get(f'B173nb_b10/{prior}') for prior in ['ALS','LoD2']} for part in a['data']}
 reference=[]
 for prior in ['ALS','LoD2']:
  d=comparisons['a3_metrics.json'][f'B173nb_b10/{prior}']
  for method,block in d.items():
   for res,cells in block['values'].items():
    for cell in ['all']+axcfg['cells']['order']:
     r=cells[cell];g=r.get('gt',{});s=r.get('res',{}).get('E',{});reference.append(dict(prior=prior,method=method,result=res,cell=cell,status=r.get('status'),R_tau=g.get('R_tau'),P_tau=s.get('P_tau'),gt_mean_cm=g.get('mean'),result_mean_cm=s.get('mean'),n_gt=g.get('n_gt'),n_result=s.get('n'),mesh_rule='AXES71-v2 original: current view for visible cells, virtual view for original invisible cells; not relabeled as a uniformly final mesh'))
 result=dict(at=stamp(),task_id='PHD-MAIN-TARGET-v1',states=states,values=flat,axes71_reference=reference,reference_sources=sources,metric_definitions=cfg['axes'],scientific_verdict=None);dump(DOC/'tables/continue_r7_summary.json',result);dump(root/'summary.json',result);dump(DOC/'tables/continue_r7_axes71_reference_full.json',dict(sources=sources,values=comparisons,scientific_verdict=None));csvout('continue_r7_metrics',flat);csvout('continue_r7_axes71_reference',reference)
 L=['# r7 이어 학습·기준선·7장 틀 채점 [이 발주에서 냄]','',f'- 작성: {stamp()}. scientific_verdict: null.','- 21:15·21:50 사용자 결정에 따른 두 판의 이어 학습과 저장 모델 채점. 나머지 여섯 판은 시작하지 않았다.','- 참값 열두 칸, τ, 거리 정의와 덩어리 ID는 AXES71-v2에서 그대로 받았다. 참값은 채점에만 썼다.','','## 실행과 산출 상태','','| 판·반복 | 지금 채점 메시 | 최종 메시 |','|---|---|---|']
 for r in wanted:
  ss=[next(x['status'] for x in states if x['key']==r['key'] and x['kind']==k) for k in ['current','final']];L.append(f'| {r["key"]} | {ss[0]} | {ss[1]} |')
 L+=['','- 첫 이어 학습: 항공 LiDAR 진행 표시 14,160회 직후 CUDA 메모리 부족, LoD2는 공용 제어로 종료. 원래 7,000회 상태와 실패 시도는 보존했다.','- 21:50 결정 뒤 LoD2는 원래 7,000회에서 독립 재개했다. 1,000회마다 수와 GPU 메모리를 기록한다. 22:20 r8 결정에 따라 r7 항공 LiDAR는 다시 잇지 않는다. r8 새 학습은 별도 결과로 기록한다.','- 15,000·30,000회 상태가 없는 줄은 결과 없음이며 0점이나 완료로 셈하지 않았다.','','## 전체 범위 네 값과 면 상태','','| 사전 정보 | 판·반복 | 메시 | R(τ), % | P(τ), % | 참값 평균, cm | 결과 평균, cm | 뜬 면, % | 면 없음, % |','|---|---|---|---:|---:|---:|---:|---:|---:|']
 for r in flat:
  if r['cell']=='all':L.append(f'| {r["prior"]} | {r["key"]} | {r["mesh_kind"]} | {pct(r["R_tau"])} | {pct(r["P_tau"])} | {num(r["gt_mean_cm"])} | {num(r["result_mean_cm"])} | {pct(r["floating_fraction"])} | {pct(r["no_surface_fraction"])} |')
 L+=['','- 평균 거리는 잘라내지 않은 값이다. 정밀도와 결과 평균은 AXES71-v2 셈 마(E)이며 A~F와 제외 점 수는 개별 JSON에 모두 있다.','- 전체 R은 기존 규칙의 장면 참값 점, 칸별 R은 해당 칸의 참값 행이다. 뜬 면·면 없음은 채점 가능한 패치 넓이를 분모로 하며 점 지표의 분모와 다르다.','- 지금 채점 메시: 학습 시점 TSDF 0.05 m/0.25 m. 최종 메시: 학습+16 가상 시점 TSDF 0.10 m/0.50 m, 원본 연결 성분 처리 50, 고정 평가 범위.','','## 참값 열두 칸·두 축·덩어리','','- 전체 숫자: `tables/continue_r7_metrics.csv`, `tables/continue_r7_summary.json`. 각 저장 시점과 메시의 전체 배열·개수는 `tables/continue_r7/<key>_<kind>.json`.','- 채점이 끝난 줄마다 셀 그림, 두 축 곡선, 덩어리 그림과 JSON을 만든다. 덩어리의 경계·ID·2.5/10 m² 기준과 50% 초과 달성 규칙은 기존 값을 사용했다.','- 이 작업은 각 메시를 열두 칸 모두에서 독립 채점한다. 기존 AXES71-v2 비교 행은 가시 칸/비가시 칸에 서로 다른 메시를 쓰던 원래 출처를 유지한다.','','## AXES71-v2 비교 방법: 전체 행','','| 사전 정보 | 비교 방법·저장 결과 | R(τ), % | P(τ), % | 참값 평균, cm | 결과 평균, cm | 상태 |','|---|---|---:|---:|---:|---:|---|']
 for r in reference:
  if r['cell']=='all':L.append(f'| {r["prior"]} | {r["result"]} | {pct(r["R_tau"])} | {pct(r["P_tau"])} | {num(r["gt_mean_cm"])} | {num(r["result_mean_cm"])} | {r["status"]} |')
 L+=['','- 비교 방법의 열두 칸·두 축·덩어리 값은 `tables/continue_r7_axes71_reference_full.json`에 기존 숫자를 그대로 실었다. 재학습이나 재해석을 하지 않았다.','','## 기록용 목표 따름·판단 영역·계보','','- 전체·사전 패치·배경 MVS·지붕·벽·판단 영역·원값/대체별 목표 따름: `tables/continue_r7_pixel_coverage.csv`. 기준선 30,000회는 저장 깊이를 r7 목표 지도에 다시 대었다.','- 판단 영역별 결과 τ 안·목표 자체 τ 안·뜬 면·면 없음: `tables/continue_r7_judgment_region_geometry.csv`와 `continue_r7_<사전정보>_regions_<원값/대체>.png`. 참값 열두 칸 본표와 구분된 추가 기록이다.','- 1,000회 GPU·수, 초기 큰 배경 자손 표는 `tables/continue_r7_record_only.json`과 해당 시점의 계보 JSON/그림에 있다.','- 표를 나란히 놓은 비교 그림: `figures/continue_r7_compare_<사전정보>_<메시>_*.png` 및 JSON.','','## 항공 LiDAR 기록·진단','','- [통합 진단](항공LiDAR_r7_원인점검.md): 1,000회 수, 기준선 GPU 최대, 14,100회 꼬리표 수, 설정·씨앗·코드 차이, r6 규칙의 반사실 검사, 뜬 면 넓이 교차표.','- [실행 중단 기록](이어학습_r7_중단기록.md): 실제 CUDA 오류와 가우시안 수 감시의 적용 시점.','- 배경·패치·풀림의 기여는 렌더 연관을 센 값이다. 메시 생성의 인과로 바꾸어 쓰지 않는다.','','## 검증과 범위','','- AXES71-v2 저장 자료 재집계 732개 항목 일치. 새 메시의 개별 점 수·분모·GT 칸 결합과 원본 입력 해시는 별도 검증 파일에 기록한다.','- 초기 재개 때 미사용 NaN 인수 쌍 비교 오류를 보완했다. 비교용 보기만 바꿨고 원래 인수·상태·r21 소스는 보존했다.','- 가상 시점 렌더 첫 시도의 읽기 경로 누락은 기존 읽기 전용 자료 경로로 연결했다. 실패 로그는 보존했고 해당 시도에서는 프레임이 생성되지 않았다.','- 큰 메시·거리 계산은 공용 메모리 잠금 아래 한 건씩 실행했다.','- 확인용 지역의 패치별 값과 그림은 이 묶음에 넣지 않았다. 결론과 논문 해석은 쓰지 않는다.','']
 (DOC/'이어학습과채점_r7.md').write_text('\n'.join(L));print('REPORT_ASSEMBLED',len(available),'meshes',len(flat),'metric rows',flush=True)
if __name__=='__main__':main()
