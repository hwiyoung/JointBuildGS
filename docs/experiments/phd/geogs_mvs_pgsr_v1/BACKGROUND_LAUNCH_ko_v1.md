# P1/P2/P3 MVS + PGSR 백그라운드 실행 기록

`PHD-GEOGS-MVS-PGSR-v1` · 2026-09-14 23:44 KST 시점 · `scientific_verdict: null`

CPU 검사 30개와 지역별 실제 Anchor8k→8100 GPU 사전검증 6개가 통과한 뒤,
23:43:08 KST에 systemd user service로 본 비교 큐를 시작했다. 이 시점에는
P1 prior 0.005의 MVS와 MVS+PGSR이 각각 GPU 0/1에서 실제 학습 중이다.
신규 학습 12개 전체의 완료 또는 성능 개선을 뜻하지 않는다.

## 실행 조건과 완료 기준

- P1/P2/P3 × prior 0.005/0.0005 × MVS/MVS+PGSR = 새 학습 12개.
- 각 영역의 원래 complete Anchor8k에서 30,000 iteration까지 이어간다.
  구조 보호는 native를 유지한다. 기존 DA3 조건 6개는 봉인된 비교 결과를 사용한다.
- 새 학습 12개가 모두 끝난 뒤 GPU 추출을 순차 실행하고 raw/post TSDF512 표면
  36개를 같은 UAS 참조점 ID로 평가한다. 실제 RGB/depth, 지도·단면,
  회복/훼손 원표와 한국어 `REPORT.md`를 생성한다.
- 정확한 완료 receipt와 보고서를 확인한 뒤에만 `COMPLETE`로 바꾸고
  현지 GNOME 데스크톱 완료 알림을 보낸다. 중간 상태가 같으면 알리지 않으며
  실행 실패는 보존한 로그 경로와 함께 한 번 알린다.
- 이 세션에는 Codex 자동 task 재호출 도구가 없다. 자동 채팅 답변을 예약한
  상태가 아니라, 보고서 파일 생성과 데스크톱 알림까지 연결한 상태다.

## 실행 위치

외부 task root:

`../JointBuildGS-artifacts/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1`

| 항목 | 값 또는 task root 아래 상대 경로 |
|---|---|
| systemd user unit | `jbgs-mvs-pgsr-attempt-eh1jxgen.service` |
| 관찰 시점 supervisor PID | `2657104` |
| 큐 | `queue/attempt.eh1jxGEn` |
| 현재 상태 / supervisor 로그 | `queue/attempt.eh1jxGEn/status.txt`, `supervisor.log` |
| 실행 코드 해시 | `queue/attempt.eh1jxGEn/driver_hashes.sha256` |
| 사전검증 요약 | `preflight_summary_v1.json` |
| 학습 실행 gate | `execution_gate_v1.json` |
| 후처리 사전 봉인 | `finalization_ready_v1.json` |
| 본 학습 완료 뒤 생성될 목록 | `run_index_v1.json` |
| 모든 후처리 완료 뒤 생성될 resolver | `evaluation/finalization_receipt_v1.json` |

사용한 신규 실행 스크립트는 `scripts/phd/geogs_mvs_pgsr_v1/run_queue.sh`이고,
실험 조건은 `configs/phd/geogs_mvs_pgsr_v1/experiment_v2.json`이다.
service가 실행 shell과 독립적으로 유지되는 것을 별도 호출에서 확인했다.
알림 DBus 주소와 DISPLAY는 현재 systemd user manager 환경에 존재한다.
재부팅 후 자동 재개 설정은 하지 않았다.

첫 `nohup` attempt는 호출 shell 종료 후 supervisor가 사라졌다. 학습 시작 전이었고
CPU gate만 완료됐다. 해당 폴더와 완료 gate를 보존했으며, 새 큐는 모든 모델 payload
해시와 6개 소속을 다시 검증하고 내용이 완전히 같은 gate만 재사용했다.
직접 관찰과 추정 원인은 [이슈 기록](ISSUES_ko_v1.md)의 MGP-009에 구분했다.

MVS producer 이웃 명단 미복구, GeoGS expected-depth 위 PGSR loss 이식,
단기 사전검증과 장기 실행의 차이는 [계획](EXPERIMENT_PLAN_ko_v1.md)과
[사전검증 결과](PREFLIGHT_RETURN_ko_v1.md)에 기록했다.
