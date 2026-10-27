# R1 LoD2 고정·참값 판의 전체 불투명도 중단

2026-10-27 14:37:27 KST, 씨앗 0의 첫 시도에서 기존 중단 기준이 적용됐다.

| 항목 | 값 |
|---|---|
| 결과 | R1rep_b10 / lt_fixgt_LoD2_s0 / attempt_0 |
| 반복 | 3,100 |
| 마지막 정기 초기화 | 3,000 |
| 초기화 뒤 반복 | 100 |
| 전체 가우시안 수 | 844,047 |
| 전체 불투명도 중앙값 | 0.040125567466020584 |
| 중단 문턱 | 0.05 미만 |
| 상태 | STOPPED_BY_FROZEN_CRITERION |

관측 시점은 최적화·불투명도 바닥 처리 후, 밀도 제어·다음 초기화 전이다. 사전 출신 불투명도는 기록 전용이며 이번 중단 판정에는 사용하지 않았다. 메모리 부족이나 후처리 실패에 의한 종료가 아니다.

원 기록: `JBGS_ARTIFACT_ROOT/phase-payloads/phd/main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/runs/R1rep_b10/lt_fixgt_LoD2_s0/training_health_STOP.json`. 같은 폴더의 시도 로그·health JSONL·모델을 보존한다. 이 판은 학습 정상 완료에 포함하지 않는다. 손실·채점·판·학습·중단 설정을 변경하거나 재학습하지 않았다. 독립 판의 계속 실행은 기존 사용자 승인 범위다.

scientific_verdict: null.
