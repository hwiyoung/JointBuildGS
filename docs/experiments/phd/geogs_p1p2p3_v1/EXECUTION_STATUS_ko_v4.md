# 지역 행렬 실행 중 — P1 네 조건 완료

2026-09-08 06:44 KST 시점의 진행 기록이다. 전체 실험 완료·성능 분석 보고서가 아니다. `scientific_verdict: null`.

`$TASK`는 sibling `JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1`이다. 원 source·고정 입력·과학 조건·allocator·반복·추출 계약은 [앞선 연결 기록](EXECUTION_STATUS_ko_v3.md) 그대로다. UAS와 지역 품질값은 아직 분석에 열어 사용하지 않았다.

## 실제 완료와 현재 학습

원 queue와 resource_v3 queue 모두 주 조건 **4/18개 완료**다. 완료는 native train/render/metrics 및 새 auxiliary의 생산 파일 검증을 통과했다는 뜻이다.

| P1 조건 | anchor 이후22,000회 학습 | 실제 후속 단계 |
|---|---:|---|
| D005_Pnative | 6,316.71초 | 최종1024 raw/post·평가 사진 렌더·native metrics 파일·필수512 PASS |
| D0005_Pnative | 6,398.82초 | 같은 필수 단계 PASS |
| D0_Pnative | 5,392.30초 | 같은 필수 단계 PASS; 최종 Gaussian4,769,540개·보호236,015개 |
| D005_Prelease | 6,231.15초 | 같은 필수 단계 PASS; 최종 Gaussian6,154,774개·보호0개 |

공통 anchor512 raw/post도162.92초에 PASS했다. 네 조건의 선택 final2048과 공통 선택 anchor1024는 실제32GiB cgroup OOM으로 `TECHNICAL_RESOURCE_UNAVAILABLE`다. 필수 결과나 참조 부재·복원 실패0점과 혼동하지 않는다. 원 실패 시도·구 auxiliary·예제·Wu 결과는 보존한다.

GPU0는 P1 `D0005_Prelease`, GPU1은 P1 `D0_Prelease`를 같은 원8,000회 anchor에서 학습 중이다. 마지막 확인 iteration은12,500/8,600이며 보호0개다. 두 조건 모두 초기화·anchor prior 이력이 남아 있고 image-only가 아니다. 이 수치는 정적 기록이므로 현재 진행은 실제 container/trace/queue로 확인한다.

## 실제 연속 실행과 다음 단계

연속 실행 기록은 `$TASK/runtime/resource_v3_continuation/attempt.bPR61e/`다. `scripts/phd/geogs_p1p2p3_v1/runtime/continue_resource_v3.sh`와 두 resource worker가 실제 동작 중이다. 실행 중인 launcher·orchestrator·worker는 수정하지 않는다. 도중 실패를 완료로 바꾸거나 기존 경로를 덮어쓰지 않는다.

1. P1 남은2개와 P2/P3 각6개를 이어서 주18개를 완료한다. P2/P3 native는0회부터 새 anchor를 만들고 같은 지역의 나머지 조건은 정확히 그8,000회 상태에서 분기한다.
2. GPU0 P1→P3, GPU1 P2 순서로 사전 등록한 바닐라 추가 반복3개를 진행한다.
3. strict finalizer가21개 final과48개 planned auxiliary의 필수 결과·선택 가용성을 봉인한 뒤, UAS 기하·실제 평가 렌더·정량표·사례 그림을 생성한다. CLI에 세 runtime/repeat/resource 계약을 모두 명시한다.
4. 최종 실제 viewer QA, 그림 직접 검토, 개선·유지·악화·판단 불가 근거를 갖춘 분석, 최종 보존 검사와 인계를 완료해야 한다. 자동 summary 준비 상태를 이 마지막 단계의 완료로 취급하지 않는다.

P1 실측22,000회 학습은 조건당약90–107분이었다. 현재 미완료 학습17개와 P2/P3의 추가 anchor 반복을 같은 속도로 단순 환산하면 두GPU의 학습만약15시간 규모다. 이는 자원 예산 추정이며 다른 지역의 실제 속도·메모리·추출·검증·분석 시간이나 최종 완료 시각을 보장하지 않는다. 학습량을 결과나 소요 시간에 맞춰 줄이지 않았다.

## 검증과 보존

- 결합 CPU 검증은127개 중124 PASS/3 SKIP/실패0, shell 문법7개 PASS다. 명령·소스·테스트 사본과 로그는 `runtime/resource_v3_integration_validation_v1/`에 있다. 생략한3개는 이번 mount 구성에 없는 공식 source/cache가 필요한 metric parity다.
- resource_v3 UI의 실제 **입력 전용** preflight127개 검사가 통과했다. `evaluation/browser_qa/resource_v3_input_preflight_v1/`의9장 screenshot 중 agent는P2, root는P3를 직접 확인했다. 최종 MVS/GeoGS/UAS·512/1024 전환 검증은 아직 아니다.
- 첫 두 resource job의6개 variant trace 재검증에서 필수3 PASS와 선택3 cgroup OOM이 확인됐다. 주기적 host MemAvailable 표본의 최저는약21.32GiB였다. 기록은 `preservation/after_resource_v3_first_jobs_v1/resource_memory_audit.json`이다.
- 같은 시점 기존 서비스62개 식별 정보는 모두 일치했다. 이는 현재 ID·이름·image descriptor·포트·running 비교이며 재시작 이력·데이터 바이트·브라우저 건강의 증명은 아니다. 기존 라이선스 볼륨은 검사하거나 조작하지 않았다.
- 실제 후보 봉인 후 `bash scripts/phd/geogs_p1p2p3_v1/preservation/run_final.sh`로 기존6,471개 파일 전체와 현재 서비스·Git 상태를 새 영수증에 검증한다. 보류3,126개 payload의 전체 hash와 최종 보존 PASS는 아직 완료되지 않았다.

최종 사례 해석은 [평가 검토의11절](EVALUATION_REVIEW_ko_v1.md)을 따른다. 한 방향 거리 감소·높이층·XY 빈 셀을 전체 개선·잘못된 이중면·실제 구멍의 확정 판정으로 바꾸지 않는다. 관측→입력/구현/제어 영향→원문 관계→추가 수정 필요성→후속 질문을 구분한다. 반복 재판단의 효과는 이번 실험에서 측정하지 않았다.
