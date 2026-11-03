"""Write the stage 1–3 factual handover after every locked measurement finishes."""
from common import *
ROOT=OUT/'rfix';DEST=DOC/'rfix';TAB=DEST/'tables'

def main():
 cfg=json.loads((CFG/'rfix.json').read_text());done=json.loads((DEST/'completion.json').read_text());assert done['states_completed']==8 and not done['missing']
 rows=json.loads((TAB/'state_summary.json').read_text())['rows'];views=json.loads((TAB/'per_view.json').read_text())['rows'];probe=json.loads((TAB/'atomic_addend_probe.json').read_text())['rows'];build=json.loads((ROOT/'provenance.json').read_text())
 from rfix_tables import LABEL
 passed=done['formal_pass'];status='PASS' if passed else 'STOP_GRADIENT_PARITY'
 assert not passed,'This report template is for the observed failed gate; do not silently authorize training.'
 def lines(keys,rs):
  return '\n'.join(['| '+' | '.join(keys)+' |','|'+'|'.join(['---']*len(keys))+'|']+['| '+' | '.join(str(r[k]) for k in keys)+' |' for r in rs])
 overview=[]
 for r in rows:
  overview.append({'상태':LABEL[r['state']],'출력/203':r['render_pass'],'기울기/30':r['gradient_pass'],'실패 비교/210':r['gradient_comparisons_failed'],'겹침 합 원본→고침':f"{r['original_overlaps_sum']:,} → {r['fixed_overlaps_sum']:,}",'버퍼 최대 GiB 원본→고침':f"{r['original_buffer_max_bytes']/2**30:.4f} → {r['fixed_buffer_max_bytes']/2**30:.4f}",'렌더 중앙 ms 원본→고침':f"{r['original_render_median_s']*1000:.2f} → {r['fixed_render_median_s']*1000:.2f}"})
 heavy=next(v for v in views if v['state']=='r8_LoD2_stop' and v['camera']=='DJI_20241217102535_0020_D')
 burst=[]
 for r in rows:
  vs=[v for v in views if v['state']==r['state']];n=sum(v['burst_pairs'] for v in vs);c=sum(v['burst_color_contributors'] for v in vs);ov=sum(v['burst_overlaps'] for v in vs)
  burst.append({'상태':LABEL[r['state']],'터진 쌍 수':f'{n:,}','전체 겹침 중 몫':f"{100*ov/r['original_overlaps_sum']:.4f}%",'실제 색 기여 쌍 수':f'{c:,}','터진 쌍 중 색 기여':f'{100*c/n:.4f}%' if n else '해당 없음'})
 gradient=[]
 for r in rows:
  gradient.append({'상태':LABEL[r['state']],'기울기 최대 차':f"{r['max_gradient_abs']:.9g}",'원본 반복 최대 차':f"{r['max_original_gradient_repeat_abs']:.9g}",'실패 비교 수':r['gradient_comparisons_failed']})
 bindings=[]
 for r in build['rows']:
  bindings.append({'구현':r['implementation'],'원본 바이너리 SHA256':r.get('original_extension_sha256','완료 학습 없음'),'별도 빌드 SHA256':r.get('fixed_extension_sha256','미적용 패치만 준비')})
 txt=f'''# 렌더러 화면 상자 고침 — 1~3단계 점검

- 작업: PHD-MAIN-TARGET-v1, 2026-11-03 10:40 발주문.
- 작성: {stamp()}
- 기술 판정: **{status}**. 1~3단계의 요청한 저장 상태 비교를 완료했다. 기울기 같음 조건을 충족하지 못해 r8 LoD2 이어 학습을 시작하지 않았다. 나머지 여섯 판도 시작하지 않았다.
- `scientific_verdict: null`. 학술 결론과 결과 해석은 이 문서에 두지 않는다.

## 1. 잠금과 범위

`rfix.json` 잠금 시각은 {cfg['at']}, SHA256은 `{sha(CFG/'rfix.json')}`이다. 첫 모델 계산 전에 대상 8개 상태, 학습 영상 203장, 상태마다 역전파 30장, 판정식, 조건부 학습 설정을 고정했다. `rfix.lock.json`은 원본 입력·소스 1,058개를 묶는다. 새 렌더러는 빌드별 잠금, 실제 실행은 상태별 소스·바이너리 잠금을 남겼다.

판정식은 영상·출력 또는 영상·매개변수마다 `max_abs(원본 A − 고침) ≤ max_abs(원본 A − 원본 B)`다. 허용 오차를 더하지 않았다. 유한/비유한 위치가 같고 `radii`가 바이트 단위로 같으며, 상태별 203장 겹침 합이 줄어야 한다. 기울기 영상은 이전 모의에서 겹침이 가장 큰 다섯 장, 0020, 0109를 포함해 첫 셈 전에 30장을 고정했다.

원본 모델·학습 코드·설치된 렌더러는 읽기 전용으로 썼다. 이전 화면 크기 정리 패치 다섯 개는 적용하지 않았고 밀도 제어와 정리 차례를 바꾸지 않았다. 이번 실행의 최적화 횟수는 0이다. 조건부 이어 학습, 새 메시 추출, 새 30,000회 채점은 실행하지 않았다.

이전 모의의 출신/자리 배열과 색 기여 계측 바이너리는 이전 전달물의 봉인된 SHA256을 계승했다. 이 파생 입력들의 현재 바이트 확인은 첫 rfix 렌더 뒤에 수행했으며, 이를 새 계산 전 잠금으로 소급 표기하지 않았다. 파일별 근거는 `reused_input_bindings.json`에 있다. 원래 입력·코드의 사전 잠금과 이 파생 입력의 이전 봉인을 구분한다.

## 2. 상태별 결과

{lines(list(overview[0]),overview)}

모든 출력의 영상별 차는 `rfix/tables/all_render_outputs.*`, 기울기 1,680개 비교는 `gradient_comparisons.*`에 있다. 표의 상태 전체 최댓값 두 개는 요약값이며, 통과 여부는 같은 영상·같은 매개변수의 차끼리 비교했다.

![상태별 부하](rfix/figures/all_states_load.png)

![기울기 기준](rfix/figures/all_states_gradient_gate.png)

r8 LoD2 중단 상태의 0020 영상에서 겹침은 {heavy['original_overlaps']:,} → {heavy['fixed_overlaps']:,}개, 정렬 버퍼는 {heavy['original_buffer_bytes']:,} → {heavy['fixed_buffer_bytes']:,}바이트였다. 렌더 시간은 {heavy['original_render_s']*1000:.3f} → {heavy['fixed_render_s']*1000:.3f} ms였다. 버퍼 감소와 실행 시간 증가는 별도 관측값이다. 원본 시간은 색 기여 계측을 하지 않은 두 번째 원본 실행을 썼다. 최초 실행의 계측 포함 시간도 원시 JSON에 보존했다. GPU 최대 할당·예약량은 `per_view` 원시 결과와 상태 요약에 있다. 시간은 해당 실행 관측값이며 반복 시간 벤치마크로 확대하지 않는다.

## 3. 터진 가우시안–영상 쌍

영상마다 `radii > hypot(width,height)`인 쌍을 센다. 가우시안 하나가 여러 영상에서 잡히면 영상마다 한 쌍이다. 실제 색 기여는 원래 렌더러가 채택한 화소의 `alpha × T` 합과 최댓값이다. alpha 문턱 이후의 가림/조기 종료 때문에 실제 기여가 없는 경우도 0으로 기록한다. 타일 등록용 가능성 검사는 T를 사용하지 않아 이러한 실제 기여 집계와 구분된다.

{lines(list(burst[0]),burst)}

쌍마다 중심 깊이, 중심 투영 위치와 영상 밖 거리, 원판의 가까운/먼 깊이, `d`, 실제 기여 합·최댓값을 `states/<상태>/bursts/<영상>.npz`에 저장했다. 출신 × 가로 4칸 × 높이 4칸 × 가까운 카메라 30 m 여부의 분포는 `burst_groups.*`에 있다. 분위수는 최소·25·50·75·95·최대다. 카메라 30 m 주 집계는 203장 가운데 가장 가까운 카메라 중심을 기준으로 한다. 해당 영상 카메라까지의 거리와 그 카메라 30 m 여부도 원시 자료에 별도로 있다.

가로 칸은 평가 상자 안 / 밖 50 m 안 / 50~200 m / 200 m 넘음이다. 높이 경계는 공통 지역 좌표로 −43.640 m, −10.180 m, 0.476505482 m다. 네 칸은 지면 아래 / 지면~지붕 최고+10 m / 그 위~카메라 중앙값 / 그 위다. EPSG:25832 XY와 기존 지역 높이 변환을 계승했다. 출신 코드와 경계 원본은 이전 모의 및 `boundaries.json`을 따른다.

원본 `cuda_rasterizer/auxiliary.h:185–200`의 `in_frustum`은 중심의 카메라 깊이가 0.2 m 이하이면 거른다. 같은 조건문의 화면 X/Y 검사는 주석으로 꺼져 있다. `forward.cu:184–187`에서 이를 호출한다. `forward.cu`의 `compute_aabb`는 `d == 0`만 거르며, 작은 비영(非零) d는 나눗셈에 들어간다. 원판 깊이 범위는 `Tw.z ± 3·sqrt(Tw.x²+Tw.y²)`, 기록한 분모는 `9·(Tw.x²+Tw.y²)−Tw.z²`다. 고침은 이 원본 전처리와 `radii` 반환을 그대로 보존한다.

## 4. 별도 렌더러의 수정 범위

원본 사각형 안의 각 타일에서, 원본 화소 식으로 `depth ≥ 0.2 m`이고 `alpha ≥ 1/255`가 될 수 있는 정수 화소가 하나라도 있는지 검사한다. 없으면 그 타일을 등록하지 않는다. 원판이 앞 평면을 가로지르는 경우에도 화소별 원본 깊이 조건을 사용한다. 낮은 주파수 필터의 `min(rho3d,rho2d)`도 포함한다. T나 다른 가우시안의 가림 결과는 이 검사에 쓰지 않는다.

바깥 방향 반올림 구간 계산으로 확실히 불가능한 타일을 먼저 제외한다. 분모가 0을 걸치거나 비유한 값이 있거나 경계가 확정되지 않으면 원본 float 화소 식을 직접 검사한다. 이는 원본 등록 범위에서 기여 불가능한 타일을 빼기 위한 구현이다. 화면 반지름의 이상값 자체를 고치거나 새 화소 지지 범위를 더하지 않는다.

수정은 `rasterizer_impl.cu`의 `rf_count` 호출과 `duplicateWithKeys` 타일 조건, 새 `rfix_tiles.cuh`다. `ext.cpp`와 같은 CU에는 이전 r8 정렬 버퍼 감시의 관측 인터페이스를 함께 넣었다. 검사 중 중단 장치는 비활성이고, 수치 커널에는 관여하지 않는다. 원본 `forward.cu`, `backward.cu`, `auxiliary.h`, `config.h`의 바이트는 세 빌드에서 모두 같다. 각 차이 파일은 ZIP의 `renderer_patches/`에 있다.

{lines(list(bindings[0]),bindings)}

r15·r21·r22는 target 빌드를 공유하며 영상만 2DGS와 GeoGS는 각각의 원본 Docker 이미지에서 따로 빌드했다. CDGS 어댑터는 준비 기록에 완료 학습 판이 없었다. CDGS의 3D conic alpha 식에 맞춘 같은 타일 조건의 미적용 패치를 별도로 준비했고 `git apply --check`만 통과했다. CDGS 새 바이너리나 저장 모델 검증 완료로 표기하지 않는다.

## 5. 단위 점검과 기울기 차이의 기록

세 빌드에서 렌즈 앞 기울임·화면 밖 상자·앞 평면 걸침·보통 가우시안의 네 경우를 점검했다. 화소 출력과 반지름이 같고, 타일 수는 독립 화소 참조 셈과 같다. target 빌드에는 d가 0에 가까운 여섯 경우를 덧붙였다. 반지름 450,975 px인 경우 1,410 → 27타일, 43,739,636 px인 화면 밖 경우 3,008 → 0타일이었으며 출력과 반환 반지름은 같았다. `unit_comparison.*`, `extra_near_plane_units.*`에 전체 수가 있다.

{lines(list(gradient[0]),gradient)}

기울기 비교는 저장 상태에서 원래 학습 손실을 같은 가중치로 계산했다. 위치·SH DC·나머지 SH·크기·회전·불투명도와 화면 위치 기울기를 모두 비교했다. 파라미터를 갱신하거나 최적화기를 실행하지 않았다. 손실의 원본 함수와 입력 지도는 역전파 전에 따로 해시를 남겼다. 손실 종류와 가중치는 `provenance.json`의 `losses`, 모든 실제 손실 스칼라는 `same_losses.*`에 있다.

차이가 큰 가우시안의 행 ID·지역 좌표·영상·매개변수·차이 크기는 `differing_gaussians.*`, 해당 원본 A/B/고침 기울기 배열은 `gradients/<상태>/*_differing_rows.npz`에 있다. 이 파일은 다음 재설계가 같은 대상을 확인할 수 있게 보존한다.

추가 관측에서는 첫 실패 영상 0020의 위치·DC·화면 위치 기울기 차이가 가장 큰 행 3271259, 3055338, 2351355를 골랐다. 세 행 모두 화소별 원자적 덧셈 **입력항은 바이트 단위로 같았고** 서로 다른 항은 0개였다. 실제 합산 후 기울기 차이는 `atomic_addend_probe.*`에 따로 있다. 원본 역전파는 `backward.cu:421–443` 등에서 `atomicAdd`로 합산한다. 이 세 행의 관측은 전체 기울기 같음을 대신하지 않으며 잠근 실패 판정을 바꾸지 않는다. 관측용 빌드는 전달한 고침 빌드와 분리했다. 나머지 행의 차이 원인은 이 관측만으로 확정하지 않는다.

CPU 기울기 차 집계는 뒤의 상태에서 동일한 65,536행 청크 계산을 병렬로 실행하고 원래 순서로 합쳤다. 실제 실패 행을 반복한 검증 입력에서 일곱 매개변수의 원래/병렬 결과 사전이 정확히 같음을 확인했다. CUDA 계산·판정식·원시 기울기를 바꾸지 않았으며 검증 영수증과 코드 해시를 남겼다.

## 6. 기존 GeoGS·2DGS 채점의 메시 출처

GeoGS 항공 LiDAR의 전체 R/P는 0.5474095330749325 / 0.47920042874658025, 영상만 2DGS의 ALS τ 전체 R/P는 0.3997773431018615 / 0.4199856431272774다. 기존 AXES71-v2와 이번 모의의 지우기 전 값이 반올림 전까지 같다. 기존 전체 줄의 메시도 학습 영상 203장, TSDF 0.05 m, sdf truncation 0.25 m, depth truncation 300 m였다.

다만 기존 `a3_metrics.py:22–45`는 `c_inh_invis`, `c_invis_wrong` 두 칸에서 가상 시점 메시가 있으면 그 메시를 썼다. 모의는 이 두 칸도 학습 영상 메시를 썼다. 따라서 전체 줄의 동일성과 모든 칸의 메시 규칙 동일성은 다르다. 기존 경로·post.json·거리 메타 해시와 칸별 차이는 `rfix/기존메시_출처.md`, `mesh_history.json`, `mesh_history_summary.*`에 있다.

## 7. 보존·실패·전달 경계

첫 CUDA 빌드는 상수 헤더 누락으로 실패했고, 이미지 전용 단위 점검 첫 실행은 합성 크기 자료형 문제로 실패했다. 관측용 빌드는 생성기 치환 범위 오류로 한 번 실패했다. 모두 계산 대상·실패 로그를 보존하고 해당 구현 오류만 고쳤다. 첫 그림의 한글 폰트 등록 문제는 데이터와 그림 시점을 유지한 폰트 전용 실행기로 고쳤다. `issues.md`와 `failures/`에 기록했다. 실패한 기울기 결과는 재실행으로 골라 바꾸지 않았다.

ZIP에는 보고서, md/json/csv 표, png/pdf/json 그림, 잠금 설정, 원본과 고친 빌드의 출처·차이 파일, 단위 점검 및 수치 비교 기록, 실행 스크립트, 무결성 목록을 넣는다. 큰 모델·화소별 원시 배열·별도 컴파일 바이너리는 외부 경로·크기·SHA256 목록으로 연결한다. ZIP만으로 원본 학습 자료 전체를 대체하지 않는다. ZIP CRC와 SHA256 검증은 전달물 무결성 점검이며 학술 판정이 아니다.

발주문 3단계 통과 조건 미충족으로 조건부 이어 학습은 실행하지 않았다. 따라서 4단계 이어 학습 ZIP과 새 30,000회 결과는 없다. `scientific_verdict: null`을 유지한다.
'''
 (DOC/'렌더러_화면상자_고침.md').write_text(txt)
 dump(DEST/'report_status.json',dict(at=stamp(),status=status,measurement_completed=True,training_started=False,new_30000_model=False,other_six_started=False,scientific_verdict=None))
 print('RFIX_REPORT',status,flush=True)

if __name__=='__main__':main()
