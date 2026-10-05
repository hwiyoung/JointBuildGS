# 공식 GeoGS P1·P2·P3 진단

`PHD-GEOGS-P1P2P3-v1` · 비확증 개발 실험 · `scientific_verdict: null`

2026-09-10 추가 작업: [SfM 초기화·Anchor 생략 비교 계획](SFM_NO_ANCHOR_PLAN_ko_v1.md), [실제 실행·메모리 실패와 복구 기록](SFM_NO_ANCHOR_EXECUTION_ko_v1.md), [이어가기](SFM_NO_ANCHOR_HANDOFF_ko_v1.md). 기존 ALS 초기화·Anchor 결과와 분리한 새 실험이며, 아래 원 실험의 완료 결과를 새 조건의 결과로 재사용하지 않는다.

기존 세 공간 crop에서 공식 GeoGS의 prior 깊이 요구와 구조 보호를 구분해 비교한다. 원 ALS·현재 영상·MVS의 생산 계보를 보존하고, 같은8,000회 anchor에서6조건을30,000회까지 비교한다. 신규 판단 알고리즘이나 반복 재판단은 구현하지 않는다.

[실제 결과 뷰어 바로 열기](http://127.0.0.1:8902/app/index.html?manifest=/task/evaluation/viewer/manifest_preview_v1.json&color=height) · [사용법과 현재 표시 범위](VIEWER_AVAILABLE_ko_v1.md). 2026-09-08 22:15 KST의 닫힌 산출물 목록이며 P3 일부 평가/최종 분석은 진행 중이다.

- [실험계획](EXPERIMENT_PLAN_ko_v1.md), [봉인 입력](INPUT_SEAL_ko_v1.md), [완전 상태 검증](STATE_VALIDATION_ko_v1.md)
- [실제 결과 분석 노트](ANALYSIS_NOTES_ko_v1.md): 완료된 실제 P1 입력·바닐라 표면의 정량·단면 관찰부터 기록 중이며, 세 지역 전체 최종 분석은 아직 아니다.
- [P1 실제 기하·렌더 검토](P1_REVIEW_ko_v1.md): 기하29개·렌더7개 완료 후 여섯 조건, 동일512 anchor, 거리 민감도, 실제 사진을 검토했다. P2/P3 및 최종 viewer 완료와 구분한다.
- [P2 실제 기하·렌더 검토](P2_REVIEW_ko_v1.md): 기하29개·렌더7개 완료 후 원설정의 큰 prior 오류 완화, 깊이 약화의 렌더 개선과 기하·세부 손실, 해결되지 않은 실제 사진을 함께 기록했다.
- [원문 감사](PAPER_AUDIT_ko_v1.md), [평가 검토](EVALUATION_REVIEW_ko_v1.md), [실행 편차](PREFLIGHT_DEVIATIONS_ko_v1.md), [이슈](ISSUES_ko_v1.md)
- [DA3 cubic 깊이 감사](DA3_DEPTH_VALIDITY_AUDIT_ko_v1.md), [DA3 축척 처리 감사](DA3_SCALE_CONVENTION_AUDIT_ko_v1.md)
- [공식 TSDF 깊이 범위 입력 감사](EXTRACTION_DOMAIN_AUDIT_ko_v1.md): 고정 카메라만으로 절단값과 평가 prism을 대조한 결과이며 추출 설정은 유지한다.
- [입력 뷰어 표시 검증](VIEWER_PREFLIGHT_ko_v1.md)
- [실제 삼각면·표시 계보 보완 검증](DISPLAY_VALIDATION_ko_v1.md): 합성 검증 완료; 최종 지역 화면·그림 검토는 후보 봉인 이후 필요.
- [깊이·보호 요인 대비표](FACTOR_CONTRASTS_ko_v1.md): 합성28개 검사 통과. all21 봉인과 summary 생성 후 `bash scripts/phd/geogs_p1p2p3_v1/analysis/run_factor_contrasts.sh`를 별도로 실행하여 같은 조건끼리의 직접 대비와 차이의 차이를 기록한다.
- [실현 제어 궤적](CONTROL_TRAJECTORIES_ko_v1.md): 주18개 실제 기록4,120행과 지역별 PNG/PDF 생성·수동 표시 검토를 완료했다. `evaluation/control_trajectories_v1/attempt.M6kKT8`에 명령·소스·영수증을 보존하며, 보조 반복0개와 실패·미실행 상태를 별도 기록했다.
- [자원 표의 측정 범위와 실제 시간 집계](RESOURCE_MEASUREMENTS_ko_v1.md): phase/trace/variant의 측정 범위를 구분한다. 주18개 네 단계 driver 합30.427750시간과 별도 반복 실패 비용을 닫힌 영수증에서 확인했으며, 전체 달력 경과 시간과는 구분한다.
- [allocator 복구 조건과 한계](ALLOCATOR_RECOVERY_ko_v2.md), [중간 보존 점검](PRESERVATION_INTERIM_ko_v2.md)
- [봉인 후 전체 보존 검사와 신규 경로 검토](PRESERVATION_FINAL_ko_v1.md): 기존6471개 파일bytes·기존62개 서비스시점identity 일치. 범위 밖 신규74개 경로 때문에 원exit1/검토필요 상태를 보존하고 작성주체미확정·무변경조치를 기록했다.
- [P2 여섯 조건 완료 후 보존 감사](PRESERVATION_AFTER_P2_ko_v1.md): 14개 보조 추출 기록, 닫힌 증거 파일 해시24건, 12:56:25 KST의 기존 서비스62개 식별 정보를 확인했다. 전체 최종 보존 감사는 all21 봉인 이후 별도로 수행한다.
- [P3 여섯 조건 완료 후 보존 감사](PRESERVATION_AFTER_P3_ko_v1.md): 14개 보조 추출의 연결과 닫힌 증거33건,18:57:41 KST의 기존 서비스62개 식별 정보를 확인했다. root도 정본/원자원/서비스/닫힌증거 영수증의 네 해시를 재확인했다.
- [추출 자원 보완 계약](EXTRACTION_RESOURCE_AMENDMENT_ko_v3.md): 주 최종1024 유지, 동일512 anchor/최종 비교, 선택 고해상도의 확인된 메모리 불가 별도 기록.
- [현재 실행 중 인계 지점](EXECUTION_STATUS_ko_v8.md), [P3 완료 과정](EXECUTION_STATUS_ko_v7.md), [P3 진입 시점](EXECUTION_STATUS_ko_v6.md), [P1 완료 시점](EXECUTION_STATUS_ko_v5.md), [P1 앞선 진행](EXECUTION_STATUS_ko_v4.md), [추출 연결 기록](EXECUTION_STATUS_ko_v3.md), [앞선 allocator 인계](EXECUTION_STATUS_ko_v2.md), [추가 바닐라 반복 계약](../../../../configs/phd/geogs_p1p2p3_v1/supplemental_repeat_v1.json)
- 외부 payload resolver: `artifacts/manifests/geogs_p1p2p3_v1.yaml`

2026-09-08 20:07:49 KST에 주 조건18/18개의 결과78개와 관련 파일1,849개를 봉인했고, [실행 상태 v9](EXECUTION_STATUS_ko_v9.md)의 별도 launcher로 실제 평가에 진입했다. 추가 바닐라 반복은 P1/P2 CUDA OOM 실패, P3 미실행이다. [평가 시작 조건 변경](EVALUATION_COMPLETION_AMENDMENT_ko_v2.md)에 따라 실패 경로를 보존하고 추가 진단·재시도 없이 주18개를 분석한다. 주 조건과 평가법은 유지하며 보조 반복의 실제 품질 변동은 미측정으로 남긴다.

현재 값은 `bash scripts/phd/geogs_p1p2p3_v1/runtime/monitor_progress.sh`와 최신 인계 문서로 확인한다. 주18개 완료와 반복/최종 분석 미완료를 구분한다. 입력·문헌·예제·합성 브라우저 검사를 세 지역의 최종 성능 결과로 취급하지 않는다. 주18개 후보와 보조 실패·미실행 상태를 결합한 봉인 이후 최종 정량표·실제 사례 그림·비교 화면·분석·인계가 모두 필요하다. 위의 all21 참조들은 변경 전 구현·검증 기록이며, 현재 완료 범위는 평가 시작 조건 변경 문서가 규정한다.

현재 실행 경로는 [runtime_layout_allocator_v2.json](../../../../configs/phd/geogs_p1p2p3_v1/runtime_layout_allocator_v2.json)과 외부 `contracts/runtime_layout_allocator_v2.json`으로 고정한다. 새 비교는 `runs_allocator_v2/`, 상태 검증은 `parity_allocator_v2/`, 작업 기록은 `queue_allocator_v2/`에 남긴다. `runs/P1/D005_Pnative/`와 `runs/P1/D0005_Pnative/`의 두 CUDA OOM 시도는 그대로 보존한다. 이 실패 시도와 새 allocator 조건을 주 비교표에 혼합하지 않는다.

P1은 기존 `runs/P1/D005_Pnative/model/jbgs_complete/iteration_8000/`의 같은 anchor를 사용하며 새 원설정 조건도 여기서 재개한다. P2/P3의 anchor와 후속 조건은 새 allocator에서 시작한다. 과학 설정·봉인 입력·영상 해상도·학습량·제어 조건은 그대로다. P1의 첫 두 조건은 최종 학습·1024 표면·렌더를 완료했지만 보조 추출에서 별도 CPU 메모리 한계를 확인했다. 새 `extraction_resource_v3/`는 실패한 기존 보조 산출물을 덮어쓰지 않고 필수512·선택 추출을 기록한다. 전체 실행이나 모든 메모리 문제가 해결됐다는 선언은 아니다.

UAS 평가 전에 각 지역의 동일 allocator·동일 anchor 바닐라 반복을 한 번씩 추가하는 계획을 고정했다. 첫 P1/P2 반복 실패와 P3 미실행 이후 원 계약을 보존하면서 `evaluation_completion_v2.json`을 추가했다. 평가에는 원 runtime layout·supplemental repeat·추출 자원 계약과 새 완료 범위를 모두 결합한다. 주18개 필수 표면과 선택 추출 상태, 보조 반복의 실패·미실행 상태를 봉인한 뒤 참조를 연다. 향후 반복 결과는 별도로 연결하며 여섯 조건이나 주18개 결과를 대체하지 않는다.

재현 진입점은 `scripts/phd/geogs_p1p2p3_v1/`이다. 원 source/고정 Docker image/봉인 입력을 이용하며 출력이 이미 존재하면 덮어쓰지 않는다. 실행별 실제 명령·입력/코드 hash·로그·GPU/메모리·실패 영수증을 외부 task 경로에 남긴다. 기존 source·Wu–Vallet 결과·서비스와 canonical E1–E6 계약은 별도다.
