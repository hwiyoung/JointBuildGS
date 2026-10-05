# 실행 중 인계 지점 — 추출 자원 계약 추가

2026-09-08 · 진행 중 기록이며 완료 보고서가 아니다. `scientific_verdict: null`.

`$TASK`는 sibling 외부 저장소의 `phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1`이다. 공식 source·원 과학 설정·봉인 입력·allocator_v2·반복 계약과 정확한 P1 anchor는 [앞선 인계](EXECUTION_STATUS_ko_v2.md) 그대로다.

## 실제 완료·실행 상태

- 공식 예제는30,000회 학습·실제 렌더·raw/post mesh·native metric 파일을 완료했다. 세 지역 결과와 분리한다.
- P1 `D005_Pnative`, `D0005_Pnative`는 `runs_allocator_v2/P1/`에서30,000회 학습·최종1024 raw/post mesh·독립 평가 사진 렌더·native metric 파일 생성을 완료했다. 지역 품질값은 아직 설정 선택이나 분석에 읽어 사용하지 않았다.
- 학습 직후 발생한 launcher EOF는 실행 중 shell 변경이 강하게 지지되는 원인이다. 마지막 Docker 호출을 exec로 바꿨고, 완료 train 해시 검증 뒤 후속 단계만 재개했다. 원 queue/log와 복구 기록은 `queue_allocator_v2/recovery/`에 있다.
- 그 뒤 P1 바닐라 anchor1024와 가중치0.0005 final2048이32GiB MEMCG OOM으로 실패했다. 성공한 가중치0.0005 final512와 모든 원 실패 파일은 기존 경로에 남아 있다.
- 새48GiB anchor1024 단독 시험도 실패했다. 새32GiB anchor512 단독 시험은 실제 렌더와 raw/post 유효 표면까지 PASS했다. 두 probe와 stopped container는 보존한다. 경로는 `runtime/host_memory_recovery_v1/`이다.
- P1 `D0_Pnative`는 같은 기존8,000회 anchor에서30,000회까지 실제 학습을 완료했다. train receipt의 native/validated exit0, wall5,392.298482초이며 최종 Gaussian4,769,540개·보호236,015개다. GPU1 P1 `D005_Prelease`는 같은 anchor에서 학습 중이다. 두 train-only 시작 명령은 각각 `runtime/train_pending_extraction_review.sh`, `runtime/train_registered_condition_only.sh P1 D005_Prelease 1`이었다. 이 두 job은 후속 render/metrics/새 auxiliary가 아직 필요하며 새 worker가 producer 검증 후 이어간다. 진행 중인 GPU1 학습을 중복 실행하지 않는다.
- 실제 trace에서 D0native는 `lod_weight=0`, 보호236,015개를 유지한다. D005Prelease는 보호0개다. 초기화·anchor prior는 양쪽 모두 남아 있으므로 image-only가 아니다.

## 새 고정 계약과 남은 연결 작업

[추출 자원 보완](EXTRACTION_RESOURCE_AMENDMENT_ko_v3.md)을 읽는다. `contracts/extraction_resource_v3.json` SHA256은 `804f371b9db70b089daccdba2052df8c71b54b5d20acba2ea2f5c6d3d7eb7efa`다. 필수 최종1024·512, 지역 공통 anchor512, 원래 선택 anchor1024/final2048의 성공 또는 확인된 MEMCG 실패를 모두 기록한다. 주 정량은1024, anchor 전후는 양쪽512를 비교한다.

새 산출물은 `extraction_resource_v3/{primary|native_repeat_1}/{region}/{condition}/`에 둔다. 기존 run·auxiliary·영수증·로그를 이동하거나 덮어쓰지 않는다. source/학습 계약을 변경하지 않는다. 선택 실패는 `TECHNICAL_RESOURCE_UNAVAILABLE`와 null metric으로 별도 표시하고 참조 부재나 복원 실패0점으로 바꾸지 않는다.

새 runtime driver/worker/repeat/finalizer 및 evaluation/sealer/summary/cases/viewer 연결과 독립 통합 검토를 완료했다. 세 지역의21개 final과48개 planned auxiliary variant, 공통 anchor 소유권, 선택 OOM의 cgroup 증거, producer 해시, 봉인 상태·CLI 연결을 확인했다. 반복 runner에도 train24GiB/render40GiB의 host MemAvailable 사전 대기를 적용했고, 로그 프로세스가 GPU flock을 붙잡는 문제는 Docker 재현 검사 후 수정했다. 과학 설정·입력·분기 조건은 그대로다.

`runtime/continue_resource_v3.sh`를 실제 시작했다. 운영 기록은 `$TASK/runtime/resource_v3_continuation/attempt.bPR61e/`다. 기존 train-only GPU 잠금이 풀리면 새 worker0/1이 완료 producer를 검증하여 재사용하고 남은 단계만 실행한다. GPU0는 `D0_Pnative` 학습 종료 후 `P1_D005_Pnative`의 기존 완료 단계 검증을 시작했으며 새 claim은 `queue_allocator_v2/resource_v3/claims/P1_D005_Pnative/attempt.V2R62l/`이다. 주18개 완료 뒤 GPU0에서 P1→P3 반복, GPU1에서 P2 반복을 진행한다. 모든21개 성공 뒤 strict finalizer가 봉인→UAS/렌더 평가→표→실제 사례 그림 순서로 실행한다. 실패는 완료로 넘기지 않는다. 최종 브라우저 QA·그림 직접 확인·관찰 근거를 갖춘 분석·보존 검증은 이후 별도로 필요하다. 실행 중인 launcher/orchestrator를 수정하지 않는다.

기존 두 global queue 실패는 새 계약의 job 완료 영수증을 검증한 뒤 원 기록을 보존하며 처리한다. 구 auxiliary FAIL 파일 자체는 이동하거나 덮어쓰지 않는다.

평가의 네 entrypoint에는 `--runtime-layout`, `--repeat-contract`와 새 `--resource-contract /task/contracts/extraction_resource_v3.json`을 함께 사용한다. 추가 반복은 primary18개가 새 계약을 만족한 뒤 시작한다. 공통 anchor는 primary 바닐라가 지역별 한 번 생성하여 반복에서도 공유한다.

분석 보고 방향 열은 `reference_to_prior_relation`으로 명확히 했다. 모든 고정 거리 문턱에 면적 균등 표본 기반 `A×(1−precision)`을 추가해 관측 참조에서 먼 표면 면적을 추정한다. 이를 잘못된 잔존 구조의 확정 면적으로 부르지 않는다. 이 출력 보완은 UAS·지역 품질 접근 전에 완료했고 formula/null/aggregation을 포함한 Docker 합성 검증62개가 통과했다. 사례 선택은 원래 main1024 규칙을 유지한다. 자동 거리 관계·XY 결손·높이층은 의미 판정을 대신하지 않으며 실제 사진·단면과 함께 개선·유지·악화·판단 불가 근거를 작성해야 한다.

최종 연결 코드의 결합 CPU 검증은127개 중124개 PASS,3개 SKIP, 실패·오류0이며 shell 문법7개도 PASS했다. 생략은 공식 source/cache mount가 필요한 metric parity3개로, 이번 CPU-only 검사에서 해당 mount를 제공하지 않았다. 정확한 명령·image·코드/테스트 사본·해시·로그·영수증은 `$TASK/runtime/resource_v3_integration_validation_v1/`에 보존했다. 실제 GPU 실험 결과나 최종 정량 검증을 대신하지 않는다.

## 참조·뷰어·보존

UAS payload는 아직 열지 않았다. 모든 주18개+반복3개와 선택 추출의 가용성 inventory를 봉인한 뒤 실제 UAS 기하·평가 사진 지표·표·단면·사례·최종 viewer QA를 수행해야 한다. 현재 서비스8902는 입력 preflight 화면이다. 실제 결과의1024 및 공통512 표시·브라우저 검증·사용자용 분석·최종 인계는 아직 완료되지 않았다.

메모리 종료 뒤 기존 running 서비스62개의 ID·이름·image 표기·포트·running 상태를 다시 확인하여62개 모두 일치했다. `preservation/after_memcg_oom_v1/receipt.json`을 참조한다. 참조 가능3,126개 파일의 최종 byte 검사는 여전히 candidate seal 뒤로 보류한다. 기존 사용자 dirty 파일·Wu 결과·canonical 계약·서비스·라이선스 볼륨은 건드리지 않는다.

봉인 이후 최종 보존 명령은 `bash scripts/phd/geogs_p1p2p3_v1/preservation/run_final.sh`다. 실제 candidate seal과 모든 producer 해시를 먼저 검증한 뒤, 기존6,471개 파일 전체를 예외 없이 해시한다. 기존 dirty patch·HEAD·누락 symlink·출처 미상 새 문서의 관측 메타데이터·서비스62개를 구분해 기록한다. 새 출력은 `$TASK/preservation/final_v1/attempt.XXXXXX/`이며 아직 실제 최종 검사는 실행하지 않았다. 합성 변조·누락·봉인 차단6개 검사는 통과했다.
