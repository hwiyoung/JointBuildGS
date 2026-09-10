# 국소 상보 depth refinement — main_v2 실행·평가 입구

- task_id: `PHD-LOCAL-COMPLEMENTARY-REFINEMENT-v1`
- 실행 명세: `main_v2`; scientific_verdict: null
- 상태는 [진행 기록](PROGRESS_ko_v2.md)과 실제 phase receipt·queue event로 확인한다.
- 진행 결과의 사진·수치·3D와 에이전트 없는 후속 실행은 [열람·자동화 인계](VIEW_AND_AUTOMATION_ko_v2.md)를 본다.
- “전역 prior 계수만 낮추면 충분한가”의 기존18G·게시11LC·고정 단면띠 재검산은 [전역 prior 감소 검토](PRIOR_REDUCTION_CHECK_ko_v2_1.md)에 있다.
- LC의 추가 기여를 검증13조건·연속 거리·G 세 계수·양방향 보존/수정·사진으로 재검토한 결과는 [기여 면밀 분석 v2.2](CONTRIBUTION_ASSESSMENT_ko_v2_2.md)에 있다. 전역 F1과 국소 형상·연속 거리의 상충 및 제한된 절충 효과를 구분한다.
- 국소 가중 일반의 한계와 현재 설계/구현 문제를 혼용하지 않도록 [설계·구현 재검토 v2.3](DESIGN_IMPLEMENTATION_AUDIT_ko_v2_3.md)에 실제 loss·gradient 경로, 영상 적합과 기하 악화의 공존, source 일치 시 감독 강도 감소를 구분했다.
- [감독 신호·가중 설계 분리 검토 v2.4](SOURCE_AND_WEIGHT_DESIGN_REVIEW_ko_v2_4.md)는 prior 유지 의도, 카메라별 잔차와 다중뷰 일관성의 차이, source 선택·총강도 분리 후보와 DA3/MVS 비교 구조를 정리한다. 새 실행 명세나 검증된 개선안은 아니다.
- [source 신뢰도 근거·픽셀 검증 v2.5](SOURCE_RELIABILITY_AND_PIXEL_VALIDATION_ko_v2_5.md)는 원사진으로 두 후보 표면을 검사하는 선행연구와 적용 한계, P1/P2 실제 target·합성 prediction의 전체 픽셀 가중치 및 gradient 감사 36건 PASS를 기록한다. Gaussian 업데이트와 새 선택기의 성능은 검증 범위에 포함하지 않는다.
- [후속 source 가중 정책·단계 검증 설계 v3](SOURCE_WEIGHT_POLICY_DESIGN_ko_v3.md)는 대칭 patch 비교, 관측 지지/보류, 배분 q와 총강도 s, 지도 판독, source·강도·controller 대조와 G0–G6 검증을 정한다. 수치 보정과 실행 결박 전의 설계이며 기존 main_v2 또는 새 실행 config를 대체하지 않는다.
- [v3.1 변수·MVS 검증 보완](MVS_VALIDATION_AND_NOTATION_ko_v3_1.md)은 생성/판정 사진 분리, MVS 자기검사 한계, 결손·불균일성의 별도 진단과 q/s/관측 지원 판정의 의미를 구체화한다.
- [v3.2 실제 관측 점수 따라보기](OBSERVATION_WALKTHROUGH_ko_v3_2.md)는 기존 입력의8개 위치에서 원사진→투영→패치→mask→밝기 정규화→점수를 제공한다. G/V 분리는 보조 검사로 두며, 실제 가시성·source 정확성·q는 미판정이다.

사용자는 2026-09-10 인계 후 미확정 명세의 구체화부터 새18개 구현·검증·실행·평가 완료까지 승인했다. 아침 종료 제한은 없다. [v1 인계](START_HERE_ko_v1.md)의 미실행 상태와 분위수 probe는 그 이전 준비 이력으로 보존한다. 현재 본 실험의 설정·근거는 아래 v2 문서와 봉인 파일이다.

## 명세와 계보

1. [MAIN_SPEC_ko_v2.md](MAIN_SPEC_ko_v2.md): 입력 전용 문턱 선정, loss reduction, 비교·평가·자원 계약.
2. [experiment_v2.json](../../../../configs/phd/local_complementary_refinement_v1/experiment_v2.json): 실제 실행 설정. SHA256 `579369916b854f05088ed8427c3b6010e0532343b7b09afb93336ae495c5889e`.
3. [v2 artifact resolver](../../../../artifacts/manifests/local_complementary_refinement_v2.yaml): 외부 payload, source, 계약·검증·결과 경로.
4. [진행 기록](PROGRESS_ko_v2.md), [실패·예외 기록](ISSUES_ko_v2.md), [P2 .005 중간 결과](INTERIM_P2_D005_ko_v2.md), [P1 .005 중간 결과](INTERIM_P1_D005_ko_v2.md), [첫6개와 P3 중간 검토](INTERIM_D005_ALL_REGIONS_ko_v2.md), [P2 .0005 중간 검토](INTERIM_P2_D0005_ko_v2.md).

기존 complete Anchor8k 3개와 G 대조18개의 정확한 파일을 재사용한다. 새 LC만 P1/P2/P3 × prior `.005/.0005/0` × 보호 `native/release`로8001–30000 step을 수행한다. 원 GeoGS ALS-adaptation 계보를 보존하며 canonical E1–E6 결과로 바꾸어 부르지 않는다. prior 계수0도 Anchor·가중·보호의 prior 의존성이 있어 image-only가 아니다.

새 `.5/2m`는 입력만 검토한 뒤 선택한 공통 탐색 ramp다. source 정오나 노이즈 경계의 보정값이 아니다. 두 target이 유효하면 `a=clip((abs(DP-DV)-.5)/1.5,0,1)`, prior/visual에 `1-a/a`를 적용하고 각 source의 기존 유효 pixel 수로 나눈다. 단일 유효 source는 배율1이다. 실제 subpixel ray convention 차이와 높은 포화율을 명세에 남겼다.

외부 task root의 `contracts/main_v2/`에는 config, input binding, CPU/probe/baseline 검증과 `execution_ready.json`이 있다. input binding SHA256은 `75b7a3c8d5ca2c0633587af76cd68e86076e4ffc4c7add53cf3462e5821d8a14`, 별도 source_v2의 train.py SHA256은 `297bcf0b357b3e14f617beaffc002ea8322d509356404a90d3b4bc8905c96aca`다. 실행 중인 행렬의 config/source/runtime helper를 바꾸지 않는다. 추가 분석은 새 attempt와 코드 snapshot으로 남긴다.

## 실행 상태와 평가 재현

모든 프로젝트 계산은 Docker다. 현재 queue 소유권과 진행은 다음 읽기 전용 명령으로 확인한다. 이미 실행 중인 queue를 중복 시작하지 않는다.

```bash
bash scripts/phd/local_complementary_refinement_v1/run_monitor_v2.sh
bash scripts/phd/local_complementary_refinement_v1/run_trace_v2.sh
```

monitor는 상태만 읽고 trace 명령은 읽기 전용 trace/receipt를 새 독립 진단 attempt에 snapshot한다. 진행 중 trace는 파일별 관측 시각이 다를 수 있으므로 완결된18개의 분석을 대신하지 않는다. `main_v2/queue/events.log`와 각 run의 train/render/metrics receipt가 모델 단계의 근거다. 모델18개 완료와 전체 평가 완료는 별개다. 전체 평가의 기본값은18개 모두를 요구하며, 부분 평가만 명시적으로 `--region P2 --allow-partial` 같은 옵션을 사용한다.

P3 .0005 native의 원 OOM을 보존하고 별도 경로로 재시도하므로, 최종18개 평가에는 [재시도 계획](RETRY_PLAN_ko_v2.md)의 불변 `run_selection_v2.json`을 먼저 성공 후 생성해야 한다. 아래 최종 명령은 그 manifest가 검증·생성된 뒤 실행한다. 원 경로를 읽는 부분 평가와 과거 receipt의 계보는 유지한다.

```bash
bash scripts/phd/local_complementary_refinement_v1/run_evaluation_v2.sh evaluate --run-selection /task/main_v2/run_selection_v2.json
bash scripts/phd/local_complementary_refinement_v1/run_summary_v2.sh /task/main_v2/evaluation/attempt_ID
bash scripts/phd/local_complementary_refinement_v1/run_evaluation_v2.sh figures /task/main_v2/evaluation/attempt_ID
bash scripts/phd/local_complementary_refinement_v1/run_maps_v2.sh /task/main_v2/evaluation/attempt_ID
bash scripts/phd/local_complementary_refinement_v1/run_strata_v2.sh /task/main_v2/evaluation/attempt_ID
bash scripts/phd/local_complementary_refinement_v1/run_matrix_figures_v2.sh /task/main_v2/summary/attempt_ID
bash scripts/phd/local_complementary_refinement_v1/run_figure_review_v2.sh /task/main_v2/evaluation/attempt_ID /task/main_v2/figures/attempt_ID
bash scripts/phd/local_complementary_refinement_v1/run_map_review_v2.sh /task/main_v2/evaluation/attempt_ID /task/main_v2/maps/attempt_ID
bash scripts/phd/local_complementary_refinement_v1/run_trace_v2.sh --selection /task/main_v2/run_selection_v2.json
bash scripts/phd/local_complementary_refinement_v1/run_attempt_costs_v2.sh
```

`attempt_ID`는 각 앞 단계가 생성한 실제 receipt 경로로 치환한다. 각 명령은 독립 출력에 생성하며 기존 attempt를 덮어쓰지 않는다. 부분 평가를 요약하거나 그림 QA할 때는 summary, figure_review, map_review에도 `--allow-partial`이 필요하다. figure_review는 원본 pixel/crop, 선택 카메라 PSNR, 단면 표본 수를 독립 대조한다. map_review는 Anchor/G/LC 원 거리 배열에서 모든 표시 cell의 수정·손상·지원 수와 범주를 다시 확인한다. 실제 PNG의 시각 검토는 별도로 남긴다. 원본 참조점 ID/XYZ 일치와 봉인 출력 hash 검증을 통과한 결과를 사용한다.

## 해석과 완료 기준

[원사진·DA3 target A–F 사례 검토](PHOTO_TARGET_CASE_REVIEW_ko_v2.md)는 실제 보이는 표면, 원 target 편차와 같은 참조점의 기존 성공·LC 손상을 연결한다. 사진 진단은6사례 완료, 모델 사례 표는첫 .0056개 부분 비교다. 전체 평가 뒤 같은 사진/ID로 `run_photo_case_summary_v2.sh /task/main_v2/photo_target_audit/attempt_20260910T232336_211760Z /task/main_v2/evaluation/attempt_ID`를 실행하여 전체18개 사례 표를 남긴다. 원사진 진단은모델 결과를 읽지 않으며 새 학습 정책이 아니다.

2026-09-11 08:15 KST의 후속 부분 기록은 [P1 .0005 보고](INTERIM_P1_D0005_ko_v2.md)다. 모델10/18개 완료와 P1만 선택한4조건 부분 평가를 구분한다. P3 .0005 두 조건은 진행 중이며 남은 모델·전체 평가를 계속한다.

Raw TSDF512를 주평가, 동일 post512를 별도 평가한다. 모든 G 대조와 Anchor를 남기고, 같은 참조점·XY cell에서 수정과 손상, G의 수정 유지·소실, 추가 손상을 함께 보고한다. 고정 사진·ROI·단면과 평균 외관 지표를 연결하되 일부 사진 악화를 숨기지 않는다. 계산 비용은 과거/현재의 checkpoint·렌더 범위와 타이머 차이를 명시한다.

박사학위 논의는 네 항목을 구분한다. **문제 차별성**은 불완전한 기존 자산과 현재 관측의 보완 범위이며, **원인 설명**은 관측된 충돌·최적화 반응의 근거와 식별 한계다. **방법 신규성**은 이번 국소 배분 규칙이 선행 방식과 구별되는 범위이고, **검증 기여**는 대응 부위의 기존 성공과 새 악화를 함께 추적한 통제·계보·측정이다. 개발18개의 결과만으로 네 항목이 모두 입증되었다고 판정하지 않는다.

평균 배율 전역 대조, controller replay와 반복이 없다. 따라서 공간 배분 고유 효과, DA3 단독 인과, 작은 차이의 재현성·모집단 일반화를 확정하지 않는다. source별 근접도·strict target 오차 층은 평가 proxy이며 정오·시점 변화의 진실값이 아니다. GT는 평가 전용이고 인간의 과학적 판정은 별도다.

완료는 새18개 phase PASS, 전체18개 평가·요약, 실제 시각/회계 검토와 자원·실패·한계 기록까지 포함한다. 기존 입력·결과·서비스·준비 이력·사용자 작업은 보존하며 Git stage/commit은 별도 요청 없이 수행하지 않는다.
