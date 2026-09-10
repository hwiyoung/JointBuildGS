# main_v2 기술 이슈

- task_id: PHD-LOCAL-COMPLEMENTARY-REFINEMENT-v1
- scientific_verdict: null
- 기존 [v1 이슈](ISSUES_ko_v1.md)는 준비 이력으로 보존한다.

## LC-V2-001 — 실행 초안의 계약 연결 누락

문제: v1 launcher는 준비 config/binding을 직접 연결했고, gate revision 경로·queue의 readiness 경로가 일치하지 않았다. queue는 존재하지 않는 run_evaluation.sh를 호출했다. 원 driver는 parent invocation을 읽지만 전체 native flags 동등성을 검증하지 않았다.

원인: 본 실험 전 중단된 미완성 초안. 이 초안으로 main 실험을 실행하지 않았다.

조치: 별도 v2 helpers를 작성하고 contracts/main_v2 identity를 runtime에서 검증한다. v2 queue는 모델 단계 완료만 명시하고 실제 평가 완료와 구분한다. parent native flags는 resume/capture instrumentation을 제외하고 같아야 한다. source payload·complete receipt·trace·render PNG도 생산자 digest로 결박한다.

해결 여부: 동결 시 CPU48개와 P2 native/release GPU1step probe가 통과했고 `execution_ready.json`의 PASS_FROZEN/PASS_VERIFIED를 확인했다. 실제 첫 학습 두 컨테이너에서도 v2 config/binding과 restore 일치가 확인됐다. 전체 모델·평가 완료와는 구분한다.

## LC-V2-002 — depth의 반픽셀 raster 관례 차이

문제: 기존 prior의 Open3D ray는 u+.5/v+.5, DA3 unprojection은 정수u/v이다. 엄밀한 subpixel same-ray 주장은 성립 확인되지 않았다.

원인: 기존 두 source 생성기의 raster 관례 차이. camera-Z 미터라는 공통 depth 정의는 입력 전용 fixture로 확인했다. 큰 불일치의 원인이나 source 정오를 이 차이만으로 확정하지 않는다.

조치: 입력을 보존하고 같은 camera raster index를 대응시키는 실험으로 명세를 한정한다. 기존 G/LC가 같은 입력을 공유하는 비교에서 이 한계를 기록한다.

해결 여부: 운영 정의와 주장 범위에 반영. 반픽셀 재정합은 이번18개 범위가 아니며 수정하지 않았다. 경계 영향과 동일 가시 표면 여부는 남은 한계다.

## LC-V2-003 — 평가 합성 fixture의 voxel 경계

문제: 평가 v2 첫 CPU 검증에서 17개 중1개 fixture가 .3/.1의 부동소수 경계로 두 점을 같은 voxel에 넣어 예상과 달랐다.

조치: 별도 voxel임이 명확한 fixture 좌표로 수정했다. 실제 geometry evaluator는 변경하지 않았다.

해결 여부: 수정 후17개 통과. 실제 reference/cache 일치는 별도 preflight로 검증한다.

## LC-V2-004 — 재사용 검증과 최종 config digest의 불일치

문제: 첫42개 baseline preflight는 검증 PASS였으나, 동시에 정리하던 raster 관례 문구가 최종 config에 반영되어 최종 config SHA와 일치하지 않았다. 최소 attestation 생성기가 `Actual baseline evaluation identity not verified for main specification`으로 거부했다.

조치: 첫 receipt를 보존하고 최종 `contracts/main_v2/experiment_v2.json`에 대해 새 attempt로 identity 검증을 반복한다. 평가 수치나 문턱을 바꾼 것은 아니며 최종 hash에 맞춘 재검증이다. 일치 전 실행 gate를 만들지 않는다.

해결 여부: `attempt_20260910T140234_230545Z/receipt.json`이 최종 config SHA57936991…c5889e에 대해42/42 PASS. 참조 내용이 없는 `contracts/main_v2/baseline_validation.json` 생성도 통과했다.

## LC-V2-005 — CPU 통합 검증 컨테이너 기본 작업 경로

문제: 고정 이미지의 기본 `/workspace/geogs` working directory와 읽기 전용 `/workspace` mount가 충돌하여 Docker가 `mkdir /workspace/geogs: read-only file system`(exit125)로 시작을 거부했다. Python 검증은 실행되지 않았다.

조치: 같은 입력·이미지·검증 코드에서 `-w /workspace`를 명시했다. 프로젝트나 기존 서비스는 수정하지 않았다.

해결 여부: CPU 전체48개 PASS, failure0/error0/skip0. 영수증은 `main_v2/validation/cpu_validation.json`이다.

## LC-V2-006 — 첫 큐 launch 수명 종료

문제: `nohup ... &`로 실행한 첫 host queue는 started.txt만 기록한 뒤 PID2721953이 사라졌다. 이벤트·학습 run·학습 컨테이너가 하나도 생성되지 않은 것을 확인했다. 종료 원인의 세부 신호는 기록되지 않아 확정하지 않는다.

조치: 시작 기록을 같은 파일시스템의 `main_v2/queue_launch_attempt_1/`로 보존하고, 동일 hash의 큐를 유지되는 실행 세션에서 다시 시작했다. source/config/학습량은 변경하지 않았다.

해결 여부: 새 `main_v2/queue/events.log`와 개별 invocation/컨테이너로 실제 시작을 확인한다. 첫 launch를 완료된 또는 실패한 학습1회로 세지 않는다.

## LC-V2-SUMMARY-001 — 보고 이름별 집계와 평가 계약 검사 누락

문제: 보고 초안은 동일 참조점 8bin 합계를 검사했지만, 이름별 수정 손실·손상 회복·추가 손상 count를 독립적으로 신뢰했다. 합성 n=8에서 각각999/888/777도 받아들였다. 평가 전용 사용의 명시적 false와 paired table의 전체 raw/post 문턱도 강제하지 않았다.

원인: 세 방향의 4범주 투영과 이름별 값이 단일 8상태 분할에 모두 결박되지 않았고, 전체 문턱 검사가 geometry table에만 적용되었다.

조치: 보고 revision `v2.2_three_way_accounting`은 생성기 순서 A*4+G*2+LC에서 이름별10개 count를 유도·검사한다. 모든 raw/post·문턱·cohort의 Anchor→G / Anchor→LC / G→LC 투영, 동일 분모와 cell 지지를 검증한다. 명시적 boolean 평가 전용 false 및 각 paired comparison/cohort의 전체 문턱을 요구한다. 변경 범위는 보고 producer와 테스트이며 동결 config·학습 runtime·평가 생성 수치는 변경하지 않았다.

해결 여부: Docker26개 PASS. 변경 전/후 소스·diff·n=8 반례·테스트 로그·영수증은 외부 task의 `main_v2/evaluation_preflight/summary_accounting_audit_20260910T144309794364187Z/`에 보존했다. 첫 테스트의 신규 합성 fixture8개 오류는 exclusive-write helper에 따른 임시 파일 재작성 문제였으며 fixture 수정 후 재검증했다. 최초 오류 로그도 남긴다. 영수증 SHA256은 `3d2e7b2406752a76d9797ce1f547f24dca1fff138839f561247c15b80c9909c4`이다. 이는 보고 회계의 기술 검증이며 실제 효과·재현성 판정이 아니다. scientific_verdict는 null이다.

## LC-V2-EVALUATION-001 — 외관 대응과 평가 실행 계보 검증 보완

문제: 평가 준비 검토에서 과거 appearance CSV의 image/source/ROI 결박과 evaluator runtime/source snapshot 기록이 부족함을 확인했다. 실제 잘못된 수치나 GT 학습 사용이 발견된 것은 아니다.

조치: image ID·evaluation index·원사진/렌더 hash·정확한 ROI rectangle·pixel count·status를 봉인 기록과 검사한다. 실행 이미지 ID, launcher hash, Python/NumPy/SciPy/Open3D/Pillow 버전, cgroup cap과 실행 코드 snapshot을 평가 attempt에 기록한다. 수치·학습 명세·동결 runtime/queue는 변경하지 않았다.

해결 여부: Docker33개 및 실제 기존 P2 G6×9camera×2domain=108행 검증 PASS. `main_v2/evaluation_preflight/readiness_audit_20260910T144200Z/receipt.json` SHA256 `9d2cf27027ca1d933c0f8466b0e3ce95d3cf4593b3da11ead7b2fb0ec5cb155a`에 전후 코드·diff·검증을 보존했다. 헤더 전용 자원 점검의 첫 Docker 시도는 읽기 전용 기본 working directory 부재로 배열 접근 전 exit125였다. `/audit`를 명시한 재실행은 통과했고 실패 로그도 보존했다. 실제 appearance peak RSS는438,280,192bytes이며 새 geometry peak로 대신 쓰지 않는다. LC geometry의 실제 통합 검증은 최종 출력 후 수행한다.

## LC-V2-MAPS-001 — 첫 실제 P2 PNG의 metadata·제목 겹침

문제: 첫 실제 P2 native/release 지도에서 지지 수를 적은 metadata 문장이 패널 제목과 겹쳤다. 지도 생성의 수치 검사는 PASS였지만 직접 PNG 시각 QA는 실패였다.

원인: metadata y=.865와 세 줄 패널 제목의 고정 위치가 충돌했다.

조치: 문장 y좌표만 .895로 조정하고 render revision `v2.2_header_spacing`을 기록했다. 최초 `main_v2/maps/attempt_20260910T153659_593789Z/`와 중간 `maps/visual_qa_v2_1/attempt_20260910T153659_593789Z/`를 보존했다. 최종 사용 경로는 `main_v2/maps/visual_qa_v2_2/attempt_20260910T153659_593789Z/`다. 두 CSV는 최초와 최종 byte-identical이며 SHA256은 native `da84288c7d4ede89e9d743b026846d5b12bf0516eff6eb82d932b7d07424764f`, release `e55ab6e01fd01b89e29f0d89a0143874ee60ce90643b79fe52d9c7836282fc31`이다. 동결 config·학습·평가 수치는 변경하지 않았다.

해결 여부: 최종 두 PNG를 직접 확인하여 텍스트 겹침 해소. Docker map8개 PASS. 해시로 결박된 Anchor/G/LC 및 paired NPZ의 동일 원본572,214개 ID/XYZ에서6패널의 수정·손상·유한 대응·strict 지지 cell 수를 독립 재계산해 전부 일치했다. 전후 source·diff·재실행 script·테스트·시각/거리 QA는 `main_v2/evaluation_preflight/maps_actual_qa_20260910T153659_593789Z/`에 보존했으며 QA receipt SHA256은 `517d5782bde66b537bd954cd8dd5fcc9bed44fff29c62c3c73a5d93aadfa366e`이다. 점/cell 수는 면적 또는 동일3D패치 대응이 아니다. P2 두 조건의 중간 관측이며 scientific_verdict는 null이다.

## LC-V2-MATRIX-001 — 조건 행렬 그림의 부분/전체 행수별 간격

문제: 새 봉인 요약 그림의 최초 시각 QA에서 실제2행 그림의 범례·축 제목이 겹쳤고, 합성18행 수정/손상 그림의 두 줄 분모 라벨도 겹쳤다. 집계·단위·분모 검사는 통과했으나 이 시각 상태로 전달하지 않았다.

조치: 조건행은 같은 순서로 유지하면서 물리적 inch 여백과 한 줄N 라벨을 적용했다. 작은 nonzero delta가 정확한0처럼 표기되지 않게 지수 표기도 지원한다. 최초 실제 `main_v2/matrix_figures/attempt_20260910T163452_936054Z/`와 중간 `attempt_20260910T163642_216915Z/`, 합성/로그/코드 snapshot은 보존했다. 최종 실제 경로는 `main_v2/matrix_figures/attempt_20260910T163843_120697Z/`다. 최초·최종 `chart_data.csv`는 byte-identical이며 SHA256은 `607c887b59eb02ee4e5ae63d9aaab0a95a01258da9e5d610b42c55816295178c`이다. 데이터·동결 config·학습/평가 runtime은 변경하지 않았다.

해결 여부: Docker11개 PASS, shell syntax PASS. 실제2행/합성18행 최종 그림 두 종류의 시각 QA 완료. 최종 PNG는 직접 확인한 간격 수정본과 byte-identical이다. 최종 실제 그림은2/18 관측과 미표시16개를 명시하고, 합성18행은 제목에 SYNTHETIC QA를 표시한다. 전후 source/diff/테스트/원본 보존·수치 검증은 `main_v2/evaluation_preflight/matrix_figures_cpu_qa_v2_20260910/receipt.json` SHA256 `df8603d9dc3f9c5b79f8b0fe33bbf481f0b739961b71e5127892bc6347762682`에 기록했다. 조건마다1회이며 CI·우월성·재현성·공간 배분 인과 판정을 만들지 않았다. scientific_verdict는 null이다.

## LC-V2-P1-REVIEW-001 — 보고용 trace 조회의 중첩 필드

문제·원인: P1 시각/표 QA는 PASS했지만, 별도 읽기 전용 terminal 조회가 trace JSON의 condition 필드를 평탄한 구조로 가정해 `KeyError: 'region'`로 종료했다. 실제 필드는 각 항목의 `summary` 아래 있다. 이후 issue 기록의 첫 결합 patch도 존재하지 않는 문맥 `#` 때문에 적용 전에 거부됐다.

조치·해결: 실제 JSON 구조를 읽고 `condition['summary']`로 조회한 독립 Docker 검사는 PASS했다. 첫 조회 오류와 patch 거부는 `main_v2/figures_review/review_P1_D005_v2_20260910T1730Z/trace_inspection_attempt_1.txt`, 수정된 조회 script·봉인 trace SHA·결과는 같은 디렉터리의 `inspect_trace_summary.py`와 `trace_inspection.json`에 남겼다. 학습·분석기·설정·입력·기존 결과 변경은 없으며 main matrix 또는 평가 실패가 아니다. scientific_verdict는 null이다.

## LC-V2-FIGURE-QA-001 — Anchor 전체 패널 독립 대조 범위 보완

문제·원인: 새 범용 figure QA는4개 ROI가 각 전체 패널의 정확한 crop인지 검사했지만, 전체 패널→봉인 원 렌더의 독립 pixel 대조는 원사진/G/LC3개에 적용했다. Anchor는 그림 생성기의 봉인 source/카메라 검사에 의존했다. 실제 잘못된 Anchor 패널이 발견된 것은 아니다.

조치·해결: QA revision `v2.1_all_four_native_panel_sources`에서 정확한 `D005_Pnative / anchor_512 / raw` render candidate와 사진명·image ID·camera ID·evaluation index·원 렌더 SHA를 독립 조회하고 Anchor 전체 pixel도 비교한다. 첫6개 실제 Docker 검증은 모두 PASS했다. 이전 QA source·receipt는 `main_v2/figures_review/attempt_20260910T195401_933515Z/`에 남고, 보완 source·receipt는 `main_v2/figures_review/attempt_20260910T203212_627796Z/`에 있다. 그림·평가 수치·학습 config/source/runtime은 변경하지 않았다. scientific_verdict는 null이다.

## LC-V2-LOOKUP-001 — 읽기 전용 경로 조회 오류

후속 P1 .0005 보고 조회에서도 존재하지 않는 `matched_changes.csv`와 `cohort_transition_summary.csv`를 추정한 두 `head`가 exit1을 반환했다. 실제 산출물 목록에서 `paired_summary.csv`와 `primary_source_strata.csv`를 확인한 뒤 올바른 CSV와 JSON 중첩 필드를 Docker로 읽었다. 첫 임시 필터의 빈 목록도 결과0건으로 사용하지 않고 실제 `candidate` 필드로 재조회했다. 학습/평가 데이터 변경·모델 실패는 없고 보고 수치는 실제 파일에서 확인했다.

2026-09-11 P1 Anchor 계보 재확인에서 `REUSE*`라는 부정확한 문서 glob과 존재하지 않는 `bind_inputs_v2.py`를 지정한 두 `rg` 조회가 exit2를 반환했다. 실제 재사용 문서는 `RESOURCE_AND_REUSE_REVIEW_ko_v1.md`이며 이 문서와 기존 `runs_allocator_v2/P1/D005_Pnative/train_invocation.json`을 직접 읽어 P1의 원 `runs/` Anchor 예외 경로와 `--jbgs_resume_full /anchor/checkpoint.pth`, `training_start_iteration: 8000` 계보를 확인했다. 입력 부재나 Anchor 불일치가 아니며, 이 조회는 어떤 학습·분석·입력 파일도 변경하지 않았다. 모델/평가 실패 수에 포함하지 않는다. scientific_verdict는 null이다.

## LC-V2-PHOTO-CASE-001 — 보조 사례 집계 옵션 표기

2026-09-11 08:28 KST 첫 `run_photo_case_summary_v2.sh` 호출이 `--photo-audit`를 전달했지만 Python 파서가 `--photo_audit`를 요구하여 계산 시작 전 exit2로 종료했다. 초기 source·launcher·오류는 `main_v2/photo_case_summary/launch_attempt_1_argparse/`에 보존했다. 파서의 공개 옵션을 하이픈 표기로 맞췄다. 새 `attempt_20260910T232835_852311Z` 실제 첫6개 비교는24행의 전체 case/선택 사진 subset에서 원본 ID/XYZ와 수정−손상=근접점 수 변화 검증을 통과했다. 학습·기존 평가·입력 변경은 없고 모델 실패가 아니다. scientific_verdict는 null이다.

## LC-V2-RUN-001 — P3 .0005 native CUDA OOM

문제: 첫 train이2026-09-11 08:25:53 KST exit1로 실패했다. 마지막 trace14900, 진행표시14950, Gaussian6,563,992이며30000 완료가 아니다. 원 경로 `main_v2/runs/P3/LC_D0005_Pnative/`에 train log/receipt/invocation/GPU sample과 trace를 보존한다.

원인: rasterizer backward의1.17GiB 요청 시 GPU0 여유1.07GiB로 CUDA OOM. PyTorch allocated21.04GiB 및 unallocated reserve666.07MiB, 별도 desktop process260MiB가 exception에 기록됐다. CPU 평가와의 인과나 host RAM 부족은 확인되지 않았다.

조치·해결 여부: [별도 재시도 계획](RETRY_PLAN_ko_v2.md)을 작성했다. 현재 queue 완료 후 동일 정책·같은 Anchor로 GPU1 새 output에 재시도하며 현재는미해결이다. `main_v2/environment/p3_0005_native_oom_observed/`에 관측 당시 자원을 보존했다. 기존 서비스·입력·완료 결과를 변경하지 않는다. scientific_verdict는 null이다.

## LC-V2-SELECTION-QA-001 — 분석 resolver 통합 검증의 임시 공간

2026-09-11 09시경 분석 run-selection 보완의 첫 전체 테스트 호출은138개 중 모의 queue 테스트1개가 `/tmp`의 가짜 `nvidia-smi` 실행 Permission denied로 실패했다. Docker tmpfs의 기본 실행 금지가 직접 원인이며 실 GPU 호출·학습 실패가 아니다. 부모 source가 이 호출에 마운트되지 않아 source 대조4개도 skip이었다. 첫 receipt/log/source snapshot은 `main_v2/analysis_revisions/run_selection_v2_1/validation/`에 보존했다. 테스트 재호출에는 `/tmp:rw,exec`와 읽기 전용 부모 source를 명시하고 `validation_retry_exec_tmp/`에 별도 기록한다. 학습 container/설정/source는 변경하지 않는다. 최초 단위 검증의 run-selection14개와 평가33개는 통과했다. scientific_verdict는 null이다.

동일 작업의 읽기 전용 issue 조회에서 `ISSUES_v2.md`라는 부정확한 이름을 사용한 `tail`이 exit1을 반환했다. 실제 `ISSUES_ko_v2.md`를 파일 목록에서 확인해 읽었으며 산출물 부재나 모델 실패가 아니다.

재호출 `validation_retry_exec_tmp/receipt.json`은138개 모두 PASS이고 skip은없다. 실행용 tmpfs와 부모 source mount가 원인이었음을 실제 통과로 확인했다. 신규학습의 자원 설정은변경하지 않았다.

## LC-V2-EVALUATION-002 — 후속 receipt 결손과 알려진 학습 실패 구분

P3 .0005 native 실패를 검토하며 평가의 phase 파일 존재 검사에서 한 receipt라도 없으면 일괄 `PENDING_OR_MISSING_PHASE`로 분류하는 초안 경로를 발견했다. 이미 train FAIL이 있고 metrics가 없는 경우도 같은 분류가 될 수 있다. 완료 조건의 거리/외관 계산 문제는 아니며, 해당 실패가 포함된 새 부분 평가 전에 보완했다.

`run_phase_presence`는 기존 receipt를 해시로 결박하고 `FAILED_PHASE`, `INVALID_PHASE_RECEIPT`, `INVALID_PHASE_STATUS`, `PENDING_OR_MISSING_PHASE`, `ALL_PHASE_RECEIPTS_PASS`를 구분한다. 평가 실패·미완료 행에는 `quality_metrics:null`과 `reference_absence:false`를 남긴다. 새4개를 포함한 평가37개와 run-selection14개(합51개)가 PASS했고, 실제 원 OOM receipt SHA256 `478de7467958edd5033b8d171db0c6edb4e8b7fada06c4e228d45c2847782ed3`도 train FAIL/render MISSING/metrics MISSING으로 정확히 분류했다. `main_v2/analysis_revisions/failed_phase_presence_v2_1/receipt.json`에 source snapshot·검증을 보존했다. 학습/원 receipt/완료 지표 계산식은변경하지 않았다. scientific_verdict는 null이다.
# 진행 결과 뷰어·무인 후속 작업 검증 — 2026-09-11

- 실제 systemd 시작 시 Codex 제공 `rg`가 PATH에 없어 source 목록의 두 process substitution이127을 반환했으나 parent는 평가를 계속했다. 학습·평가를 중단하지 않고 원 감시 목록/127 marker/로그를 보존한 뒤, 기존71개 hash 불변과 누락234개를 검증하여305개 목록으로 원자적 복구했다. 추가 coverage는 복구 시점부터이며 소급 주장하지 않는다. `main_v2/automation_v2/source_guard_repair_v2_1/receipt.json`이 근거다. 실행 중인 코드는 그대로이며, 다음 launcher는 별도v2.1에서 해당 unit에만 PATH를 명시한다.
- 3D 최초 Chromium QA도 writable XDG 기본 경로 때문에 시작에 실패했다. 독립 임시 config/cache/data 경로로 고쳐306개 실제 조건/raw/post/표시/카메라 검사가 PASS했다. 처음 실패와 뒤의 성공을 모두 `main_v2/review_3d/browser_qa/`에 보존했다.

- 정적 packet builder 첫 시도는 Docker image의 기본 working directory와 읽기 전용 repo mount가 충돌하여 exit125였다. 명시적 `/workspace` 작업 경로로 수정한 뒤 게시 PASS했다. 학습·평가 원본은 변경되지 않았다.
- 실제 Chromium QA의 초기 실패는 image의 Node entrypoint 중복, 읽기 불가 XDG 기본 경로, extension background target 선택이었다. 명시적 entrypoint, 독립 writable XDG, `type=page/about:blank` 선택으로 고쳤다. 실패 attempt를 보존했으며 최종 실제10조건230검사 PASS와 desktop/photo/mobile 화면 확인을 남겼다. 모델 실패나 품질 결과로 분류하지 않는다.
- `current.json`을 바꿀 때 기존 페이지의 수치와 새 PNG가 섞일 수 있는 경로를 발견했다. root를 불변 packet 주소로 redirect하고 운영 상태만 별도로 읽는다. 새 검증 묶음의 이동 링크를 표시한다.
- 무인 후속 초안의 단순 PASS 종료 코드로는 전체 trace 완료를 보장하지 않고, source snapshot만 기록하면 실행 중 코드 변경을 차단하지 못했다. 최종 완료에 각 필수 receipt의 전체18개 상태·동일 evaluation/selection/게시 hash를 요구하고, 실행 source SHA를 각 단계 전에 확인하도록 보완한다. 완료 표식 없는 main/retry 프로세스 종료도 liveness 검사로 드러낸다. 동결 학습 tuple과 실행 조건을 변경하는 조치가 아니다.

## LC-V2.2-REPORT-001 — 기여 분석의 가까운 점 라벨 겹침

13조건 기여 분석의 첫 양방향 연속 평균 거리 scatter에서 P2의 가까운 G/LC 점 라벨이 겹쳤다. 수치·봉인 입력·단면 계산 오류는 아니다. 첫 `packet_contribution_v2_2_20260911T025441_538040Z`를 보존하고, 계수별 라벨 위치와 연결선을 분리한 `packet_contribution_v2_2_r2_20260911T025441_538040Z`를 새로 생성했다. 기존 review/3D current pointer나 서비스를 변경하지 않았다. r2 원본 PNG를 실제 열어 구분을 확인했다. 가까운 값의 정확한 차이는 동일 보고서의 전체13조건 표·원 CSV에서 제공한다.

추가 분석 자체는 원 NPZ에 대한 독립138검사 PASS다. 빈 재구성/비유한 거리를 만나면 조용히 제외하지 않고 중단하는 구현이며, 현재13조건에는 해당 결손이 없다. 향후 분석 config의 .1m 변화 구간이나 .5m 폭을 바꿀 경우 CSV 열 이름·그림 문구도 함께 버전 변경해야 한다. 현재 실행 config와 명칭은 일치한다. 기존 자동 실행 source305개 해시 검사도 PASS이며, 이 추가 분석을 공간 배분 고유 효과나 독립 학습 반복의 검증으로 부르지 않는다.

## LC-V2.3-AUDIT-001 — 추가 합성 gradient 감사의 fixture dtype 불일치

설계/구현 재검토의 첫 CPU 합성 fixture가 depth float64와 RGB float32를 혼합해 dtype equality assertion에서 실패했다. 실제 동결 학습 코드의 오류를 발견한 것이 아니다. 원 attempt를 보존하고 fixture dtype만 맞춘 `main_v2/implementation_audit/attempt_20260911T042717Z_dtypealigned_retry`에서 기존16테스트와 동결 loss/renderer AST의 gradient 기대값 검사가 PASS했다. CUDA kernel 전체를 새로 실행한 검증은 아니며 실제 형상 악화의 단독 원인은 미확정이다. 상세 범위는 `DESIGN_IMPLEMENTATION_AUDIT_ko_v2_3.md`에 남겼다. 같은 조회 중 부정확한 두 파일 경로가 exit2를 반환한 이력도 그 문서에 기록했다. 동결 source·입력·계수·기존 결과는 수정하지 않았다.
