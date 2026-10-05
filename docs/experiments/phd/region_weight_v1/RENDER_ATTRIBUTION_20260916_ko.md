# 단계 1: P1 렌더 기여 진단

사용자 요청에 따라 기존 결과의 기제를 먼저 시각화했다. 자동 가중치 생성 및 새 학습은
다음 검토 단계다. 현재 진단은 GT를 사용하지 않고 동일 checkpoint를 forward render한다.

- 결과: `PASS_FORWARD_ATTRIBUTION`, 기제 해석 PARTIAL, `scientific_verdict: null`.
- payload: `geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1/viewer_rgb_v1/mechanism_diagnostic_v1/attempt.2TRgwhGr`.
- 보고서: `/data/mechanism_diagnostic_v1/attempt.2TRgwhGr/report.html` (기존 8910 서비스).
- 설정: `configs/phd/region_weight_v1/render_attribution_v1.json`.
- 실행: `bash scripts/phd/prior_weight_followup_v1/run_attribution.sh`.
- 그림·HTML: `build_attribution_report.py`, 브라우저 검사: `attribution_browser_qa.mjs`.

## 방법

0100_D의 기존 R1 중 prior와 MVS가 유효하고 MVS가 2m 이상 뒤에 있는 113,102픽셀을
고정 진단 ROI로 삼았다. 시작 상태의 보호 Gaussian 중 중심이 ROI에 투영되고 prior
camera-Z와 1m 이내인 4,455개를 순서 보존으로 추적했다. 기존 4,557개 집계보다 좁다.
원 소스의 보호 대상 clone/split/prune 제외와 보호 개수 보존을 확인했다.

모든 Gaussian의 위치·크기·방향·opacity와 가림을 유지하고, 집단 indicator를 색으로
입력해 합성 가중치의 집단별 합을 얻었다. ROI 내 이 합을 전체 누적 alpha 합으로 나눴다.
최종 세 조건의 예상 depth는 저장된 depth와 최대 차이 0이었다. 보호/비보호 집단 합과
전체 alpha의 최대 차이는 약 1.1e-6 이하였다.

| 조건 | 시작 지붕 집단 기여 | MVS 근처 중심 집단 기여 | 비보호 집단 기여 | MVS 평균 절대차 |
|---|---:|---:|---:|---:|
| 공통 Anchor8k | 69.17% | 0.002% | 28.47% | 387.81cm |
| 전역 prior .0005 | 16.46% | 53.25% | 82.77% | 8.91cm |
| 영역별 prior .005 / R1=4 | 12.78% | 36.30% | 83.07% | 231.66cm |
| 영역별 prior .0005 / R1=4 | 0.34% | 74.25% | 99.66% | 3.96cm |

MVS 근처 집단은 중심 camera-Z가 입력 MVS와 0.5m 이내인 Gaussian이다. 집단은
서로 배타적이지 않다. 중심의 위치는 Gaussian 표면 전체나 픽셀별 교차 위치와 다르다.
수치가 낮다고 모든 과거 표면이 제거됐다고 판단하지 않는다.

## 확인한 결론과 후속 실험의 관계

현재 영역별 .0005 결과에서 시작 지붕 집단의 opacity만 메모리상 0으로 만들었을 때
예상 depth의 평균 절대 변화는 0.52cm였다. MVS 평균 절대차는 3.96→4.27cm였다.
opacity를 복원한 뒤 원 렌더와 일치함을 검증했다. 저장된 모델은 변경하지 않았다.

이 시점에서는 해당 집단의 강제 제거를 우선 해결책으로 삼을 근거가 약하다.
현재 렌더는 비보호 집단이 대부분 담당한다. 다만 기존 비보호/신규 Gaussian의 구분,
전체 출생·삭제 이력은 불가능하다. 다른 시점의 잔여층·추출 표면 진단도 별도다.

두 .0005 조건에서 추적 집단의 opacity 중앙값은 약 .0013으로 비슷하지만 기여는
16.46%와 0.34%다. 위치/방향/크기/가림 및 주변 집단의 차이를 포함한 결과이며,
opacity 감소만으로 전체 반응을 설명할 수 없다.

후속 분기:

1. 과거 집단 기여가 크고 제거 조작이 도움이 됨 → 국소 prior 손실과 보호 완화를 각각 비교.
2. 과거 기여는 작지만 현재 표면이 부족함 → 관측 신뢰도·가시성·현재 표면 seed 공급을 분리.
3. 현재 관측 근처 집단으로 표현이 전환됨 → 국소 가중치의 보정/보존 절충 검증을 우선.
4. 렌더만 맞고 mesh에 잔여층 존재 → 같은 checkpoint의 표면 추출과 다층 기하를 별도 평가.

현재 단일 시점의 결과는 3번을 지지한다. 보정 영역 하나의 진단을 지붕 끝 보존이나
전체 P1의 완전한 표면 제거로 확대하지 않는다.

## MVS 입력 점검

원 geometric depth를 재사용하며 현 loader는 유효성만 사용하고 confidence를 추정하지 않는다.
원 workspace의 consistency_graphs는 비어 있다. 대표 영상의 patch-match.cfg는
`__auto__, 20`이다. 이는 후보 영상 선택 설정이며 픽셀별 지지 수가 아니다.
원 실행의 정확한 필터 임계값은 이번 진단에 결박하지 못했으므로 기본값을 추정해 쓰지 않았다.
`mvs_inventory.json`에 설정 SHA와 파일 수를 기록했다.

추가 점수는 동일 이진 선별을 반복하는 목적이 아니다. 통과한 관측 사이의 잔차·관측각·
지지 강도가 품질 차이를 구분하는지 확인할 진단 후보다. 자동 가중치에 넣기 전에
각 근거 지도를 보여주고 유용성을 평가해야 한다.

## 실행 이슈

첫 진단 `attempt.05Z60yGP`는 frozen Torch의 mmap loader가 pathlib.Path를 허용하지
않아 checkpoint 로딩에서 중단됐다. 원 입력은 변경하지 않았다. 경로를 문자열로 바꾸고
별도 `attempt.2TRgwhGr`에서 재실행해 완료했다. 첫 로그와 failure.txt는 보존했다.
