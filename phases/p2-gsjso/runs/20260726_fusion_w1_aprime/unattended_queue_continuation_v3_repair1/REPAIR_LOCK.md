# A′ continuation v3 repair1 lock

- 기록: 2026-07-27 15:35 KST
- 대상 branch: `exp/fusion-w1`
- 원 실패 제어 namespace: `unattended_queue_continuation_v3/` (HEAD `ca8089f5f29a1405d90dbe3300ab21cac924a752`)
- 재개 제어 namespace: `unattended_queue_continuation_v3_repair1/`
- 과학적 판정: 없음

## 고정 사항

- 원 continuation 계약의 20-job 명단, 19개 신규 학습, 11개 pair, GPU0/GPU1 배치,
  30k 학습 레시피, failure threshold, 전역 직렬 readout은 바꾸지 않는다.
- 원 v3의 `queue_plan.json`, `source_boundary_receipt.json`, service log, stop audit는
  실패 당시 상태로 보존하며 새 HEAD에서 덮어쓰거나 재해석하지 않는다.
- `DEBY_LOD2_42364659 / A′ / r1`의 training, readout, 정량 score, 정성 A-I bundle은
  현재 파일을 전량 재해시한 뒤 repair1 terminal의 네 구성요소로 재사용한다.
- 첫 신규 pair는 GPU0 `DEBY_LOD2_42364663 / A′ / r1`, GPU1
  `DEBY_LOD2_4907182 / A′ / r1`이며 둘 다 materialize부터 시작한다.

## 수리 범위

- queue가 기존 qualitative renderer의 5번째 인자 `output_root=None`을 명시한다.
- systemd가 `StandardOutput/StandardError=append`로 축약 보고하는 경우, 기대 unit
  fragment·빈 drop-in·정확한 절대 로그 directive가 모두 확인될 때만 terminal-close
  runtime evidence를 통과시킨다.
- qualitative renderer 네 파일은 수정하지 않는다. 기존 정성 receipt의 implementation
  hash binding을 유지한다.

## T2 및 재시작

- 구현 수리 커밋 뒤 새 고정 HEAD에 맞춰 T2 canonical receipt를 다시 발행한다.
- 직전 T2 receipt는 history에 보존하고 8개 geometry/sample artifact hash가 불변인지
  확인한다.
- repair1 service가 active/running, null stdin, 정확한 user-systemd cgroup과 append log를
  실측하고 첫 두 training container가 각각 physical GPU0/GPU1에 올라온 뒤 세션 종료를
  허용한다. OS logout/reboot 지속성은 linger와 별도다.

이 문서는 실행 제어 수리만 잠그며 결과 해석이나 합격/불합격 판정을 포함하지 않는다.
