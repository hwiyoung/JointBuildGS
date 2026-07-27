# FUS-W1-APRIME-SMOKE-RECOVERY-LOCK-003

- authorization: 김휘영의 2026-07-27 지시 `그럼 42364609 나머지 진행하자.`
- scope: `DEBY_LOD2_42364609 / Aprime / r1` readout만 계속한다.
- preserved attempt: recovery `attempt_004` 전체와 `failure.json`을 수정하지 않는다.
- retry: 새 학습 없이 recovery `attempt_005` 한 번만 허용한다.
- observed attempt-004 stop: TSDF, primary Roofer/CityJSON/score, legacy-alpha 분류/비조립 score 이후 finalize에서 중단됐다.
- measured finalize cause: 유일한 0-byte 파일 `primary/engine/scores.csv.lock`을 원 readout artifact ledger가 빈 산출물로 거부했다.
- handling: attempt 005에서 scorer가 닫힌 뒤 생기는 정확한 0-byte `*/engine/scores.csv.lock`만 recovery 전용 격리 경로로 이동하고 영수증을 남긴다. 과학 산출물은 이동·수정하지 않는다.
- forbidden: training, 다른 건물/arm/run, 원 queue, 원 attempt 001--003, recovery attempt 004, 원 readout 구현의 수정.
- verdict: 없음. 에이전트는 산출·측정·예외 기록까지만 수행한다.

기계 판독 정본은 `recovery_lock_v3.json`이다.
