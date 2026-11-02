"""Final measurement report, with no threshold selection or scientific interpretation."""
from common import *
ROOT=OUT/'screen_sim';DEST=DOC/'screen_sim';TAB=DEST/'tables'
def f(v,d=3):return '없음' if v is None else f'{v:,.{d}f}'
def main():
 cfg=json.loads((CFG/'screen_sim.json').read_text());verification=json.loads((ROOT/'verification.json').read_text());assert verification['status']=='PASS';assert verification['meshes']==40
 rows=json.loads((TAB/'summary.json').read_text())['rows'];scores=json.loads((TAB/'axes71.json').read_text())['rows'];idx={(r['state'],r['variant'],r['prior'],r['cell']):r for r in scores};lines=['# 화면 크기 정리 모의 — 저장 상태 측정','',f'완료 시각: {stamp()}. 저장 상태 8개 × 지우기 전·후 5가지 × 학습 영상 203장 = 8,120회 원래 렌더러 forward. 여기에 지우기 전 1,624회 forward 버퍼의 색 기여 계산을 대조했다. 학습·역전파·최적화는 0회다. scientific_verdict: null.','',
 '## 범위와 고정 규칙','',
 '후보 문턱을 고르는 결론·권고·원인 해석은 쓰지 않았다. r8 LoD2 중단 상태(14,030회 완료, 14,031회 시도 전 저장)와 원 학습 소스를 보존했다. 나머지 여섯 판은 시작하지 않았다.','',
 '| 문턱 이름 | 이 자료에서의 문턱 | 삭제 조건 |','|---|---:|---|','| px20 | 20 px | 203장 중 한 장 이상에서 원래 반지름 > 20 |','| width10 | 102.4 px | 각 영상 가로의 10% 초과 |','| width25 | 256 px | 각 영상 가로의 25% 초과 |','| width50 | 512 px | 각 영상 가로의 50% 초과 |','',
 '203장의 해상도는 모두 1024 × 741이다. 저장 행을 한 번에 제외하고 다시 렌더했다. 반복해서 지우거나 학습으로 적응시키지 않았다. 불투명도·세계 크기·출신에 따른 추가 삭제는 모의에 넣지 않았다. 원래 렌더러의 반지름이 0인 행도 그대로 보존했다.','',
 '대상·입력·후보·집계·시점은 첫 계산 전 `screen_sim.json`과 SHA-256 잠금에 기록했다. GeoGS 원 실행의 `sparse_lod` 연결을 읽기 도구 r3에 반영했으며, 이 수정은 원 학습 코드 및 모델에 적용하지 않았다. 앞선 두 시도는 렌더 전 실패했고 로그를 보존했다.','',
 '## 영상 화소와 색 기여','',
 '공통 신뢰도 통과 MVS 깊이(유한·양수, confidence > 0)를 원래 카메라로 3차원 복원했다. XY는 고정 평가 사각형, Z는 기존 현재 TSDF 평가 높이 범위를 쓴다. 이 고정 화소를 모든 상태와 지우기 전·후에 재사용했다. 상자 투영은 평가 사각기둥의 화면 볼록껍질이며 near=0.2 m에서 자른다. 분모는 투영 상자 화소 수다. 유효 깊이가 없거나 신뢰도를 통과하지 못한 비율, 유효 깊이가 상자 밖을 가리키는 비율을 영상마다 따로 냈다. [공통 화소 표](screen_sim/tables/common_roi.md).','',
 '색 기여는 원래 정렬 순서의 실제 채택된 alpha × T다. 모든 가우시안과 203장 전체에서 합·최댓값·고정 평가 화소 합을 구했다. 후보 초과 행만 계산하는 생략은 사용하지 않았다. 보조 CUDA forward는 원래 버퍼를 읽으며 역전파가 없고 원래 출력은 그대로 돌려준다. 매 영상 색·알파 최대 절대 오차 ≤ 1e-5, 행 합과 원래 알파 합 상대 오차 ≤ 1e-6을 확인했다. 실제 오차는 상태별 contribution.json과 영상별 원본 summary.json에 있다.','',
 'PSNR은 float RGB를 [0,1]로 자른 뒤 원래 학습 RGB와 비교했다. SSIM은 기존 11×11, sigma=1.5, 영 패딩 5의 지도다. 상자 화소 SSIM은 같은 지도에서 고정 마스크 화소를 평균했다. 표의 PSNR은 유효 영상별 PSNR 평균이며, 화소를 모은 MSE/PSNR도 별도 냈다. 빈 마스크를 0점으로 채우지 않았다. [품질 표](screen_sim/tables/quality.md), [8,120개 영상별 값](screen_sim/tables/views.csv).','',
 '## 상태 × 문턱 요약','',
 '기여 몫은 지우기 전 장면의 전체 색 기여 대비 삭제 행의 기여다. R·P 변화는 같은 상태의 지우기 전 현재 메시 대비 %p이며 P는 셈 마다. 영상만 2DGS는 같은 메시를 ALS와 LoD2의 기존 참값 칸 구분에 각각 대어 냈다. 아래 전체 지표는 해당 구분을 함께 표시한다.','',
 '| 상태 | 칸 구분 | 문턱 | 삭제 수 (비율 %) | 색 기여 몫 % | 전체 PSNR 변화 dB | 상자 PSNR 변화 dB | 전체 R 변화 %p | 전체 P 변화 %p | 겹침 최댓값 |','|---|---|---|---:|---:|---:|---:|---:|---:|---:|']
 summary=[]
 for row in cfg['states']:
  key=row['key']
  for prior in (['ALS','LoD2'] if row['family']=='image_only' else [row['prior']]):
   base=idx[key,'before',prior,'all']
   for r in [r for r in rows if r['state']==key]:
    s=idx[key,r['variant'],prior,'all'];dr=(s['R_tau']-base['R_tau'])*100 if s['R_tau'] is not None and base['R_tau'] is not None else None;dp=(s['P_tau_E']-base['P_tau_E'])*100 if s['P_tau_E'] is not None and base['P_tau_E'] is not None else None;summary.append(dict(**r,score_partition=prior,R_tau=s['R_tau'],P_tau_E=s['P_tau_E'],R_change_pp=dr,P_change_pp=dp,floating_fraction=s['floating_fraction'],no_surface_fraction=s['no_surface_fraction']))
    if r['variant']=='before':continue
    lines.append(f'| {key} | {prior} | {r["variant"]} | {r["removed"]:,} ({f(r["removed_fraction"]*100)}) | {f(r["removed_contribution_fraction"]*100)} | {f(r["psnr_change_db"])} | {f(r["roi_psnr_change_db"])} | {f(dr)} | {f(dp)} | {r["overlap_max"]:,} |')
 from screen_sim_tables import table
 table('state_threshold_summary',summary)
 lines+=['','[요약 원수치](screen_sim/tables/state_threshold_summary.md) · [자리·출신·카메라 거리별 수와 기여](screen_sim/tables/groups.csv) · [겹침 상위 다섯 영상](screen_sim/tables/top5.md).','',
 '## 현재 메시와 열두 칸 채점','',
 '203장 expected depth를 기존 현재 메시와 같은 평가 상자에서 잘라 TSDF로 융합했다. voxel=0.05 m, truncation=0.25 m, depth truncation=300 m, volume unit=16, stride=4, 정리 없음이다. 기존 streamed_tsdf를 수정 없이 사용하고, 큰 메시 작업은 하나씩 수행했다. 타일별 메모리와 병합 기록은 외부 실행 증거에 있다.','',
 '참값 열두 칸·합계 세 줄·전체, 총 16줄을 각 메시/사전 정보 구분마다 냈다. 40개 메시와 45개 칸 구분의 총 720줄이다. 참값 기준 R(τ), 결과 기준 P(τ), 두 평균 거리(m), 뜬 면·면 없음, 참값 점 수, 셈 마 결과 점 수, 전체 결과 점 수와 제외 수, 채점 가능한 넓이와 셀 수 없는 넓이를 함께 제공한다. 합계 세 줄은 중첩 요약이므로 열두 칸에 더해 전체를 만들면 안 된다. 전체 참값 모집단과 패치 칸의 모집단도 기존 AXES71-v2 정의 그대로다.','',
 '[열두 칸·세 합계·전체 표](screen_sim/tables/axes71.md) · [CSV](screen_sim/tables/axes71.csv) · [JSON](screen_sim/tables/axes71.json).','',
 '## 그림과 자리','',
 '가로 칸은 평가 사각형 안 / 밖 (0,50] m / (50,200] m / 200 m 초과다. 높이 경계는 이전 결정의 지면 −43.640 m, 지붕 최고+10 m −10.180 m, 카메라 중심 높이 중앙값 0.477 m이며 집계에는 반올림 전 값을 쓴다. 지면·카메라 중간값은 쓰지 않는다. 카메라 30 m 안 여부는 203개 중심 가운데 가장 가까운 중심까지의 3차원 거리다. XY는 EPSG:25832의 기존 지역 원점을 뺀 좌표다.','',
 '기준선 출신은 origin.npy[init_id]와 PLY origin의 완전 일치를 확인했다. r7·r8은 같은 행의 snapshot 꼬리표를 사용했다. 영상만 2DGS는 SfM/영상 출신이다. GeoGS는 이 저장 상태에서 출신 계보를 확인할 수 없어 확인 불가로 표시했다.','',
 '반지름–기여 그림은 양수인 전체 행을 로그 격자에 모았다. 0인 행 수는 JSON에 따로 있다. 카메라 30 m 이내는 주황, 그 밖은 파랑이다. 삭제 무리 평면도는 모든 상태에 동일한 입력 평가 사각형 ±200 m 범위이며 밖으로 빠진 수를 JSON에 남겼다. 고정 렌더는 0020 영상과 입력만으로 상자 화소 수가 가장 큰 0109 영상이다. 모든 그림은 png·pdf·json으로 제공한다.','']
 for r in cfg['states']:
  k=r['key'];lines += [f'- {k}: [반지름·기여](screen_sim/figures/{k}_radius_contribution.png), [삭제 무리](screen_sim/figures/{k}_removed_overhead.png), [0020 전후](screen_sim/figures/{k}_DJI_20241217102535_0020_D_renders.png), [0109 전후](screen_sim/figures/{k}_DJI_20241217091133_0109_D_renders.png).']
 lines+=['','## 미적용 수정안과 확인 범위','',
 '[설계와 단위 점검 계획](screen_sim/patches/설계와_단위점검.md)에 화면 검사만 복제·분할 앞으로 옮긴 이유와 다섯 패치를 적었다. 반지름 기록 복사를 택하지 않았다. 문턱은 None이며 미래 실행에서 명시해야 한다. 기존 보호 마스크와 불투명도·세계 크기 검사 순서는 보존했다. 따라서 기존 기준선 보호 행의 예외는 남아 있으며 이 사실을 패치 인덱스에 명시했다. 패치를 원본에 적용하거나 학습 단위 시험을 실행하지 않았다. 문법 검사와 git apply --check만 통과했다. CDGS는 실행 완료 모델이 아닌 준비된 어댑터다.','',
 '독립 검산은 보관한 203장 반지름에서 최대·첫 최대 영상·네 삭제 마스크를 다시 만들고, 자리별 수 보존 및 고정 영상 MSE를 별도 계산했다. 공통 MVS 마스크의 누락·유효 영역 합과 16줄 채점의 넓이·결과 점 수를 대조했다. 원 입력·학습 소스 무결성과 ZIP CRC/SHA 확인은 전달 receipt에 따로 기록한다. 수치 검증·파일 무결성은 과학적 결론이 아니다.','',
 '대형 원본 모델·203장별 반지름·가우시안별 합/최대·마스크·렌더·TSDF·거리 배열은 외부 payload에 보존하고 경로·크기·SHA-256 목록을 묶음에 넣었다. ZIP의 표·그림은 바로 검토할 수 있으며, 전체 재계산에는 이 외부 입력과 잠긴 Docker 이미지가 필요하다.','',
 'scientific_verdict: null','']
 (DOC/'화면크기_정리모의.md').write_text('\n'.join(lines));dump(DEST/'report_receipt.json',dict(at=stamp(),status='PASS',states=8,render_passes=8120,meshes=40,score_partitions=45,score_rows=720,training=False,scientific_verdict=None));print('SIM_REPORT_COMPLETE',flush=True)
if __name__=='__main__':main()
