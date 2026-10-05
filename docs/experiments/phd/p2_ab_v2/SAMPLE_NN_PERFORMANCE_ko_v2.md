# 평가 NN 계산 속도와 native source 기준선

2026-09-07. 평가 전용 읽기 검사, `scientific_verdict: null`. 기존 C process·source·출력을
변경하거나 중지하지 않았다. 아래 성능 표본은 후속 renderer 오류가 확인된 B 출력에서
뽑은 **계산 부하 표본**이다. 해당 B 결과를 연구 성능 근거로 복귀시키지 않는다.
원본 native source 기준선은 이 renderer와 독립적으로 계산했다.

## 1. Worker 비교와 좌표 범위

원래 C는 4 CPU 할당 컨테이너에서 `cKDTree.query(..., workers=1)`을 실행하며 실제
CPU 사용률은 약 100%였다. 기존 실행은 계속 두고, 별도 Docker에서 UAS 2,325,976점과
`color_fixed/initial_extracted_surface.npz`의 고정 XY 영역 1,363,091점을 읽었다.
UAS tree 구성은 0.854 s였다.

| 검사 | workers=1 중앙 (s) | workers=4 중앙 (s) | 거리·index |
|---|---:|---:|---|
| 고정 순서 균등 1,000점 | 0.1994 | 0.0683 | 모든 값 bitwise 동일 |
| 첫 1,000점 | 0.00107 | 0.00130 | 모든 값 bitwise 동일 |

worker 순서는 1→4→4→1이었다. 균등 표본은 약 2.92배 빨랐지만, 매우 쉬운 첫 구간은
thread 비용이 더 컸다. 다른 서비스와 C가 동작하는 중의 작은 probe이며 전수 실행의
정확한 가속 배율을 보장하지 않는다.

| 자료 | XYZ 최소 (m) | XYZ 최대 (m) |
|---|---|---|
| UAS | [110, 86, -48.9382] | [157.9999, 131.9999, -17.6794] |
| 고정 XY 내 초기 render 표본 | [110.0000, 86.0000, -49.9583] | [158.0000, 132.0000, -15.5204] |

전체 원래 render 표본은 1,378,061점이다. C와 같은 XY 규칙으로 1,363,091점을 남기고
Z는 자르지 않았다. 균등 1,000점의 UAS NN 거리는 중앙 1.2021 m, p90 4.8894 m,
최대 9.1532 m였다. 좌표 폭발은 보이지 않았고, 첫 1,000점은 국소적으로 다른 쉬운
구간이었다. 작은 선두 표본의 시간이나 오차를 전체에 그대로 적용하지 않는다.

새 수정 C 실행에는 다음 가속을 권고한다. metric 정의나 참조를 바꾸는 조치가 아니다.

1. `workers=4`를 실행 config에 기록한다. 큰 batch는 정확 NN을 유지하고 진행 상황을
   출력한다. `eps>0`, 거리 절단, 점 제거를 속도 개선에 섞지 않는다.
2. 고정 reference의 3D/XY tree를 한 번 만들고 재사용한다.
3. 반복된 초기 표현은 **실제로 평가되는 float64 XYZ의 순서 포함 해시**와 reference
   해시·tolerance·XY radius·frame·metric 버전이 모두 같을 때만 metric을 재사용한다.
   zip 파일명이나 arm 이름만 같다는 이유로 cache하지 않는다. 행별 거리를 돌려주면
   같은 행 순서까지 필요하다. 조회 여부와 cache key를 새 receipt에 남긴다.

root가 이후 원래 C를 renderer 오류가 있는 입력의 실행으로 중지한 것은 이 진단과
별도 조치다. 이 subtask는 그 process에 signal이나 source 수정을 적용하지 않았다.

## 2. 원본 source 전체에 대한 별도 NN 기준선

같은 P2 prism의 모든 native ALS/MVS와 동일 UAS에 exact 3D NN을 계산했다.
source·reference 정합이나 수직 보정은 하지 않았다. 이 수치는 기존 numerical frame과
미보정 datum/epoch·참조 정확도의 한계 아래의 차이이며 현재성 승인이 아니다.

| 소스 | 원점 수 | source→UAS 중앙 / p90 (m) | UAS→source p90 (m) | ε=0.5 m precision / recall |
|---|---:|---:|---:|---:|
| Existing ALS | 45,986 | 0.2471 / 4.8215 | 3.7115 | 0.5361 / 0.5057 |
| Current MVS | 330,679 | 0.0873 / 0.4541 | 0.5080 | 0.9144 / 0.8975 |

전체 거리 배열과 0.25/0.5/1 m sweep을 보존했다. 원본 ALS 자체에도 약 4.82 m의
NN p90이 있으므로, 이전 render 결과의 약 4.96 m p90 전체를 low-alpha 또는 readout
오류만으로 설명할 수 없다. 반대로 native점과 여러 시점의 render 표본은 밀도·중복·
공간 가중이 다르므로 두 p90의 차이만으로 renderer의 기하 변형 기여량을 분해할 수도
없다. 확인된 overlay 오류와 수정 재실험의 필요성은 이 기준선과 별개다.

참고로 균등 초기 render 1,000점→native ALS NN은 중앙 0.2658 m, p90 1.0090 m,
최대 9.0505 m였다. 이는 오염된 초기 readout의 수치 진단으로만 보존한다.

## 3. 재현·산출물

- [성능 source](../../../../scripts/phd/p2_ab_v2/sample_nn_performance.py),
  [config](../../../../configs/phd/p2_ab_v2/sample_nn_performance_v1.json).
  외부 `PHD-P2-AB-V2-COMMON-NN-PERFORMANCE-v1/performance_receipt.json`과
  두 `*_1000_query.npz`에 원행·거리·NN index를 보존했다.
- [native 기준선 source](../../../../scripts/phd/p2_ab_v2/sample_native_reference_baseline.py),
  [config](../../../../configs/phd/p2_ab_v2/sample_native_reference_baseline_v1.json).
  외부 `PHD-P2-AB-V2-COMMON-NATIVE-REFERENCE-v1/native_reference_receipt.json`,
  `als_distances.npz`, `mvs_distances.npz`를 보존했다.
- 두 외부 root는 `phase-payloads/phd/p2_ab_v2/` 아래다. fresh 출력만 작성하고 기존
  출력이 있으면 실패한다. 각각 source/config snapshot, 입력 해시, Git commit,
  Docker image ID와 Python/NumPy/SciPy 버전을 기록했다.
- 참조는 이 평가 계산만 읽었다. A의 판단·B의 학습·정합·source 선택으로 전달하지
  않는다. baseline 수치로 parameter를 다시 고르거나 source를 교정하지 않았다.
