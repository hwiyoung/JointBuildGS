# P1 0100_D 단일 시점 영역 가중치 실험

- task_id: `PHD-P1-SINGLE-VIEW-WEIGHT-v1`
- 사용자 실행 승인: 2026-09-15, “0100_D의 depth 영역만 확실히 다시 점검하고 학습 진행하자.”
- scientific_verdict: null

## 현재 적용 revision: annotated_support_v2

사용자는 첫 실행 도중 “PDF에서 수동으로 판단한 영역만 사용하고, 미분류·범위 밖은 0”을
선택했다. 아래 초기 설계 중 **R1 밖 전체 유효 픽셀=1** 정책은 폐기한다.
현재 정본 설정은 `configs/phd/p1_single_view_weight_v1/experiment_v2.json`이다.

- 0100_D: R1=alpha(0/1/4), R2 건물·R3 기타 정적 지면=1,
  R4 제외 대상·R5 미분류·R6 범위 밖·결측=0.
- `use_mask`는 유효 R1/R2/R3의 합집합이고 `r1_mask`는 그 부분집합이다.
- 네 영역은 assistant가 RGB를 시각적으로 판독하고 다각형으로 지정했다. R1은 prior–MVS
  차이와 현재 지면 관찰을 함께 사용한 수동 후보이며 자동 임계값 분할이 아니다.
  segmentation 모델이나 calibrated MVS confidence를 사용하지 않았다.
- 0100_D의 감독 범위만 변경한다. 다른 97개의 MVS depth와 RGB 98장은 고정한다.
- 공통 분모는 원래 유효 픽셀 수이며, alpha=1은 새 수동 support 기준선이다.
  R1밖 모두 1이었던 초기 실행 및 과거 adaptive-MVS 실험과 같은 궤적이라고 하지 않는다.
- 첫 `attempt.UB7vkBLu`는 3개 기술 점검 PASS 후 alpha0/1 학습 초기에 중단됐고
  그대로 보존한다. 새 마스크·source·attempt에서 3조건을 다시 시작한다.

## 초기 설계 기록 — 위 revision으로 범위 정책 대체

## 질문과 비교

동일한 완전 상태 Anchor8k에서 `0100_D`의 고정 보정 영역 R1에만 MVS 감독 배수
0, 1, 4를 적용해 현재 지면 반영과 주변 형상 변화가 반응하는지 확인한다.
RGB 98장과 MVS depth 98개, prior 0.005, native 보호, 카메라 초기 순서/RNG,
optimizer 복원 및 30,000회 종료를 공유한다. 첫 200회 기술 점검 세 조건이 모두
통과한 뒤 본 학습 세 조건을 진행한다. 최대 두 GPU 작업을 병렬 실행한다.

MVS 전체 계수는 0.05로 고정한다. 원 Anchor의 모델·optimizer·controller 상태와
RNG를 검증해 복원하되 adaptive MVS 제어의 실행은 명시적으로 끈다. 따라서 alpha=1은
이 실험의 새로운 고정 계수 대조군이며, 과거 adaptive-MVS 학습과 동일한 궤적이라는
주장을 하지 않는다. alpha 비교는 이 세 신규 조건 사이에서 수행한다.

## 마스크와 손실

기존 98장 PDF의 각 페이지는 전체 RGB와 전체 depth를 보여준다. 보정 R1은 그중
일부이며, 80×80m 문맥 내의 기존 R1 전체를 사용한다. 원래 30×30m P1 범위는 별도로
표시·집계한다. 원RGB·MVS·prior 입력 점검으로 마스크를 동결하고 평가 참조로 선택하지 않는다.

학습 입력은 `r1_mask.npz:r1_mask` RGB 격자 boolean 하나다. R1의 가중치만 alpha로
덮어쓰며, 나머지 원래 유효한 depth는 1을 유지한다. 표시용 6분류 마스크에서 미분류나
범위 밖 픽셀에 주었던 0을 학습에 일괄 적용하지 않는다. 결측은 기존 규칙대로 제외한다.
손실 분모는 기존 유효 픽셀 수로 유지해 alpha 변화가 다른 영역의 평균 가중치를 바꾸지 않는다.

## 확인과 산출물

- CPU: alpha=1 원손실/gradient 일치, alpha=0/4의 R1 gradient 반응, 나머지 픽셀 불변,
  결측·비정상 배열·변조 입력 검증.
- GPU: 완전 상태 복원, 실제 98개 depth 로드, 0100_D가 등장할 때 적용한 alpha와 영역별
  손실/표본 수, 고정 계수 0.05, 끝 iteration과 체크포인트 해시 확인.
- 학습 완료 후 동일한 native TSDF512 추출과 0100_D/0099_D RGB-depth 비교, R1/주변
  입력-depth 잔차를 보고한다. 입력-depth 적합도는 독립적인 기하 정확도 지표가 아니다.
- 학습·추출·비교 receipt와 외부 REPORT를 보존한다. 과학적 판정은 null로 유지한다.

구현·설정·출력은 별도 workstream에 추가하며 기존 source, 입력, Anchor, 실험 산출물은
읽기 전용으로 사용한다. systemd user service가 큐를 소유한다.
