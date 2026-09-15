# 실행 이슈

- task_id: `PHD-P1-SINGLE-VIEW-WEIGHT-v1`
- scientific_verdict: null

실패와 복구 시도는 발생 순서대로 추가하며 기존 attempt는 보존한다.

## 2026-09-15 — 사용자 범위 정정으로 첫 실행 중단

- 첫 `attempt.UB7vkBLu`는 R1 밖의 모든 유효 MVS를 기존값 1로 유지하는 비교였다.
- 세 200회 GPU 기술 점검은 PASS했고 카메라 순서와 첫 렌더, 영역별 gradient 수식 검사를 통과했다.
- 사용자는 “PDF에서 수동으로 판단한 영역만 사용하고, 미분류·범위 밖은 0”을 선택했다.
- 당시 본 학습으로 넘어간 alpha0/1의 큐와 컨테이너를 명시적으로 중단했다.
  마지막 기록은 각각 iteration 8888/8889이며 alpha4 본 학습은 시작되지 않았다.
- 모든 산출물은 보존했고 `interruption_receipt.json`과 operational status에 중단 이유를 기록했다.
  GPU0/1 메모리는 기존 서비스 수준으로 돌아갔다. 이 부분 실행은 완료 결과가 아니다.
- 수정 설계는 0100_D의 R1/R2/R3만 허용하고 R4/R5/R6/결측을 제외한다. 다른 97개 depth는 고정한다.
  새로운 마스크·source·attempt에서 대조군부터 다시 점검한다.

## 2026-09-15 — v2 테스트 fixture 수정

use_mask 검사 추가 중 기존 membership 검사 일부가 잘못된 테스트 함수에 붙어 첫 테스트가
실패했다. fixture 배치를 수정했고 Docker CPU 22개 검사와 실제 pinned parent 준비 검사가
통과했다. 해당 실패는 GPU 실행 또는 과학적 결과가 아니다.
