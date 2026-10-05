# P1 필수 산출물 완료 · P2 학습 시작

2026-09-08 08:26 KST의 진행 기록이다. 전체 실험·정량/정성 분석 완료 보고서가 아니다. `scientific_verdict: null`.

`$TASK`는 sibling `JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1`이다. [이전 진행 기록](EXECUTION_STATUS_ko_v4.md)의 고정 source·입력·조건·학습량·allocator·반복·추출 계약과 실행 controller를 그대로 사용한다. 실행 중인 launcher/worker는 수정하지 않았다.

## 실제 확인

원 queue와 `queue_allocator_v2/resource_v3/done` 모두 **6/18개 완료**, 모두 P1이다. 여섯 조건 각각의30,000회 체크포인트, 최종1024 raw/post 표면, 실제 평가 사진 렌더, native metrics 산출물, 필수512 raw/post 표면이 생산 파일 검증을 통과했다. 공통8,000회 anchor512도 확보됐다. 품질 점수와 UAS payload는 아직 분석에 열어 사용하지 않았다.

마지막 두 조건의 실제 native 실행 시간은 다음과 같다. 학습은 같은 P1 anchor8,000회에서 시작한22,000회 구간이며, 완전한0→30,000회 비용으로 부르지 않는다.

| 조건 | 학습 초 | 최종1024 렌더/추출 초 | native metrics 초 | 별도 final512 초 | 선택 final2048 |
|---|---:|---:|---:|---:|---|
| D0005_Prelease | 5,774.8963 | 244.4988 | 40.2614 | 48.9186 | 57.1796초, 확인된 cgroup OOM |
| D0_Prelease | 5,673.7876 | 231.0703 | 25.1633 | 46.7108 | 56.9068초, 확인된 cgroup OOM |

근거는 `runs_allocator_v2/P1/<condition>/{train,render,metrics}_receipt.json` 및 `extraction_resource_v3/primary/P1/<condition>/auxiliary/{mesh_512,mesh_2048}/receipt.json`이다. 두 선택 추출 모두32GiB, native exit−9, `cgroup_oom_kill_delta: 1`이다. P1 여섯 final2048과 공통 anchor1024는 모두 `TECHNICAL_RESOURCE_UNAVAILABLE`로 남는다. 이 상태는 참조 부재나 복원 실패 판정이 아니며, 실패 시도와 부분 파일을 보존한다. 전체 auxiliary 시간에는 대기와 하위 추출 시간이 들어갈 수 있으므로 위 세부 시간을 중복 합산하지 않는다.

P2 `D005_Pnative`는0회부터 시작했고, 이 시점 실제 trace는2,600회다. 새 allocator에서 P2 anchor8,000회가 생성·검증되면 나머지 다섯 조건이 정확히 그 상태에서 분기한다. P3는 아직 시작하지 않았다. 실제 진행 값은 container/trace/queue를 우선한다.

## 남은 완료 조건

연속 실행 기록은 `$TASK/runtime/resource_v3_continuation/attempt.bPR61e/`다. 두 worker가 P2/P3를 포함한 주18개를 마치면, 사전 등록한 같은 anchor·allocator·seed의 바닐라 추가 반복3개를 진행한다. strict finalizer는 총21개 최종 후보와48개 계획 auxiliary의 필수 파일·선택 가용성을 봉인한 뒤에만 UAS 기하 평가, 실제 평가 렌더 점수, 정량표와 사례 그림을 만든다.

현재 진행은 저장소 root에서 `bash scripts/phd/geogs_p1p2p3_v1/runtime/monitor_progress.sh`로 확인할 수 있다. 이 읽기 전용 관찰기는 Docker 상태, iteration/Gaussian/보호 개수, 추출 진행 로그, 완료/실패 queue, anchor gate 상태만 읽는다. UAS와 최종 품질값을 열지 않으며 과학 실행을 시작하거나 변경하지 않는다.

그 후 실제 최종 뷰어 표시/조작 QA, 그림 직접 확인과 개선·유지·악화·판단 불가 사례 해석, 기존6,471개 파일 전체와 서비스/Git 최종 보존 검사, RESULTS와 다음 세션 인계가 필요하다. 자동 산출물 생성이나 P1 실행 완료를 전체 연구 결과 분석 완료로 취급하지 않는다. 반복 재판단은 이번 실험의 구현·측정 대상이 아니다.
