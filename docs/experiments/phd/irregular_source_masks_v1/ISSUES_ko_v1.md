# 비정형 소스 판정 마스크 v1 이슈

## 2026-09-15 — 고정 탐색 간격과 엄격한 완전 지지 조건에 따른 높은 유보율

- 문제: 완료된 불일치 후보의 유보율은 P1 100%, P2 95.472%, P3 97.420%다.
- 확인된 원인: 33개 깊이 표본과 간격 ≤0.25m 조건의 조합 때문에 다른 모든
  저장 조건을 통과한 P1 1,252 / P2 99,897 / P3 9,451픽셀이 유보된다.
  완전한 패치·전체 탐색 지지 조건에서도 많은 후보가 탈락한다.
- 조치: 원본을 변경하지 않는 [조건별 감사](ABSTENTION_AUDIT_ko_v1.md)를 수행하고,
  원 NPZ 해시 및 최종 판정 재계산 일치 0차이를 검증했다.
- 해결 여부: **원인 진단 완료, 계산 방법 개선 및 영역 정확도 검증 미실행**.
- 남은 범위: 비교 가능성·완전 곡선 실패에는 실제 관측 부족과 설계 조건이
  섞여 있다. 임계값을 없앤 추가 통과 수는 정확도 개선이나 올바른 수정 범위가 아니다.

## 2026-09-15 — 초기 브라우저 QA의 NumPy 실행기 부재

- 문제: `qa_initial/receipt.json`은 `FAIL_BROWSER_QA`, 오류는 `spawn python ENOENT`이다. 106개 브라우저 검사를 진행한 뒤 선택적 NPZ 수치 대조 도구를 실행하는 지점에서 실패했다.
- 원인: 고정 Node/Chromium 이미지 `sha256:5043f84d76db9d54e64fcf457125aad90ac5423fded88eca6cf487d2b4713a9e`에 `python` 실행기가 없다. 페이지의 영상 로딩 오류나 원픽셀 수치 불일치가 확인된 실패가 아니다.
- 보존: 최초 실패 기록과 스크린샷은 외부 실행 경로 `phase-payloads/phd/irregular_source_masks_v1/PHD-IRREGULAR-SOURCE-MASKS-v1/attempt_20260915T014234Z_NtoOoy/qa_initial/`에 그대로 남긴다. 실행 소스 스냅샷과 관측 산출물은 수정하지 않았다.
- 조치: 별도 `qa_retry_browser_only/`에서 고정 Chromium 이미지로 실제 브라우저/API 전달 검사를 수행했다. NPZ 직접 대조는 읽기 전용 evidence 마운트와 NumPy가 있는 고정 이미지 `sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e`로 분리했다. 검증 스크립트 `check_native_api.py`와 결과 `numeric_api_validation.json`을 같은 QA 경로에 보존했다.
- 해결 여부: 브라우저 재검사는 `PASS_ACTUAL_BROWSER_PARTIAL_DATA` — 354개 검사, 80개 화면 상태, 원픽셀/API 3개 표본. 별도 수치 검사는 `PASS_SAMPLED_NATIVE_ARRAY_API_EQUALITY` — 당시 완료된 P1 영상 2개의 실제 ROI 표본 총 6개. 깊이 불일치 후보·비용곡선 검사·사진 비용 검사 위치를 사용했고, 모든 해당 스칼라 및 이웃별 필드와 NaN→null 의미를 비교했다.
- 남은 범위: 완료되지 않은 영상은 수치 대조에서 제외했다. 표본 대조와 브라우저 정상 동작은 소스 판정 정확도, 경계 정확도 또는 실제 시간 변화의 검증이 아니다. `scientific_verdict: null`을 유지한다.

## 2026-09-15 — 초기 스크린샷의 레이어 선택

- 문제: 레이어 순회 검사 직후 캡처하여 `profiled` 레이어가 찍혔고, 상단 조작부 때문에 두 영상 패널의 하부가 잘렸다. 이는 결정 마스크를 시각 검토하기에 부적절했다.
- 조치: 작업 소스의 브라우저 QA에서 캡처 전 `decision` 레이어 선택·실제 이미지 로드 대기·ROI 맞춤·패널 위치 스크롤을 명시했다. 새 캡처는 별도 `qa_mask_preview/`에 기록하며 기존 QA 기록과 실행 스냅샷은 유지한다.
- 해결 여부: `qa_mask_preview/receipt.json`은 `PASS_ACTUAL_BROWSER_PARTIAL_DATA` — 700개 검사, 154개 화면 상태, 당시 완료된 P1 영상 3개의 브라우저/API 표본 9개. `P1_available_1440.png`에 실제 비정형 유보 마스크와 원영상의 두 패널 전체가 표시됨을 육안 확인했다. `P2_partial_1440.png`와 `P3_pending_1440.png`는 각 계산 중·대기 상태이다. 사용한 QA 소스는 `browser_qa_source.mjs`로 별도 보존했고 영수증에 해시가 있다.
