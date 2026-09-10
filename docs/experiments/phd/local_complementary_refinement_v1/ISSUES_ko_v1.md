# 국소 상보 depth refinement — 기술 이슈 기록

- task_id: `PHD-LOCAL-COMPLEMENTARY-REFINEMENT-v1`
- scientific_verdict: null
- 이 파일은 새 작업의 기술 실패·조치 계보다. 기존 run의 실패 기록을 수정하거나 대체하지 않는다.

## LC-TEST-001 — 임시 source fixture 들여쓰기 오류

- 발생일: 2026-09-10
- 상태: `RESOLVED / CPU_TEST_ONLY`
- 실행: GPU를 연결하지 않은 `jointbuildgs:dev` Docker에서 `python -m unittest discover -s tests/phd/local_complementary_refinement_v1 -p 'test_local_depth_loss.py' -v`.
- 현상: 첫 검증의 16개 중 15개 통과, `test_copy_patch_exact_provenance_and_tamper_rejection` 1개 오류. `prepare_source.py`가 임시 복사본을 compile하면서 `IndentationError: unexpected indent`를 반환했다.
- 확인한 원인: 테스트용 가짜 `train.py` fixture가 실제 source의 `for iteration` 루프를 생략하여, 루프 내부 8칸 들여쓰기를 전제로 한 원래 depth-loss block과 구조가 맞지 않았다. 실제 upstream source나 국소 loss 계산에서 발생한 학습 오류가 아니다.
- 조치: 새 테스트 파일의 임시 fixture에 실제와 같은 루프 들여쓰기 구조를 추가했다. 기존 source·checkpoint·서비스는 변경하지 않았다.
- 확인: 동일 CPU Docker 단위검증 16개 모두 통과. 이어 실제 원본 `GeoGS-state-camera-v1`의 26MB snapshot을 컨테이너 `/tmp`의 새 경로로 복사하여 exact-string patch·파이썬 구문·raw native loss 함수 AST 불변·parent와 prepared runtime hash 검증도 통과했다.
- 경계: GPU 학습·추론·렌더·재구성은 이 검증에서 실행하지 않았다. 테스트 통과는 학습 성능이나 과학적 판정이 아니다.

테스트 파일: [test_local_depth_loss.py](../../../../tests/phd/local_complementary_refinement_v1/test_local_depth_loss.py). 실제 실행 중 생기는 후속 오류는 새로운 항목으로 기록한다.

## LC-SCOPE-002 — 실험 세션 범위 오해와 P2 native 1-step probe

- 발생일: 2026-09-10
- 상태: `EXECUTION_STOPPED / MAIN_MATRIX_NOT_STARTED`
- 현상: 완료 시각 관련 앞선 지시를 이번 세션의 실험 실행으로 해석하는 과정에서 P2 `.005 × native`의 GPU 기술 probe를 시작했다. 사용자는 이후 **실험은 새 세션에서 진행하고 이번에는 실험 계획을 다시 정리**하라고 범위를 정정했다.
- 실제 실행: 기존 complete Anchor iteration8000에서 iteration8001까지 1 step. `probe_receipt.json`은 native/validated exit code 0, `status: PASS`, wall time 약29.019초를 기록한다. 조건은 `LC_D005_Pnative`이며 \(\lambda_P=.005\), 보호 해제는 false다.
- 사용한 문턱: 초기 train-input Q50/Q90의 \(\tau_0=30.826555252075195\)m, \(\tau_1=138.23462524414063\)m. 검토 중인 0.5m/2m 후보로 수행한 probe가 아니다.
- 산출물: 새 task root의 `preflight/P2_LC_D005_Pnative/probe_receipt.json`, `model/local_trace.jsonl`, `model/jbgs_complete/iteration_8001/`을 보존한다. 기존 Anchor checkpoint SHA는 `91bc9ad74b115c37d4ae35ec4eb197832e730be165d36f52ebe4bb291f1ebcfd`이며 원 Anchor와 입력은 변경하지 않았다.
- 조치: 범위 오해를 명시하고 추가 GPU 실행·종속 구현·검증을 중단했다. 전체18조건 본실험은 시작하지 않았다. 작성 중이던 `execution_gate.py`는 초안으로 보존하며 실행하거나 검증하지 않았다.
- 남은 범위: 다음 세션에서 본실험 문턱·입력 결박·준비 gate·실행/실패 복구 계획을 명세한다. 이번 문서의 0.5m/2m는 미확정 제안 후보이며, 이전 기술 probe의 문턱이나 결과를 소급 변경하지 않는다.
- 해석: 기술 PASS는 1-step 코드 경로의 성공일 뿐 국소 가중의 복원 성능, 보존·수정 가설 또는 박사 기여의 검증이 아니다. `scientific_verdict: null`을 유지한다.

## LC-CAL-003 — 입력 Q50/Q90 문턱의 적용 범위 재검토

- 상태: `MAIN_THRESHOLD_UNCONFIRMED / INITIAL_BINDING_PRESERVED`
- 확인 사실: view별 최대4,096 valid-pixel 표본, 지역별 최대200,000개, 지역 간 같은 표본 수의 합집합에서 약30.8266m/138.2346m가 산출됐다. 이 값은 건물별 균등·표면 면적별 균등 표본의 quantile이 아니다.
- 문제: 이 공통 분포가 건물의 필요한 보정 규모를 구별하는 실행 경계로 적합한지 의문이 제기됐다. 계산 실패나 GT에 의한 성능 실패가 확인된 것은 아니다.
- 조치: 초기 binding·표본·1-step probe를 보존하고 본실험 문턱 확정을 보류했다. 0.5m/2m의 고정 미터 경계는 비교할 수 있는 제안 후보로만 계획에 남긴다. 추가 계산·학습으로 값을 고르는 작업은 이번 범위 정정 후 실행하지 않았다.

## LC-EVALCPU-004 — 평가 CPU 검증 컨테이너의 WORKDIR 충돌

- 발생일: 2026-09-10
- 상태: `RESOLVED / CPU_CHECK_ONLY`
- 현상·원인: 평가용 CPU 검증의 첫 컨테이너 실행에서 이미지 기본 작업 경로 `/workspace/geogs`와 저장소의 `/workspace:ro` 연결이 충돌했다.
- 조치·확인: 작업 경로를 `--workdir /tmp`로 명시하여 경로 문제를 해결했다. 이 기록은 상위 작업의 확인을 받아 남긴다.
- 경계: 실제 GT 기하 평가 실행은 0건이다. 이 컨테이너 경로 조치나 CPU 검증을 본실험 평가 완료로 해석하지 않는다. 사용자 범위 정정 후 이 문서 기록을 위해 코드를 추가 실행하지 않았다.
