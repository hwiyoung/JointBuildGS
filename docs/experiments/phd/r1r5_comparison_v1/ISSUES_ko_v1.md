# R1–R5 비교 작업 이슈

`scientific_verdict: null`

## 2026-09-18 — 전체 결과 입력 일치도 분석의 초기 집계 오류

- v1: 개별 거리 통계와 paired 통계에 모두 `n`이 있어 dict 생성에서 TypeError.
  기하 거리 계산 뒤 표 집계가 실패했으며 최초 출력/로그를 보존했다.
  paired 표본 수를 `paired_n`으로 분리하고 실제 row 결합 검사를 추가했다.
- v2: R1 surface 배열의 숫자 Z ID를 polygon 적용 순서로 이름 붙인 것을 검토 중
  발견했다. 거리 및 ALL 집계는 같지만 R1 일부 구역 이름이 틀렸다. 게시하지 않았다.
  v3는 숫자 Z ID로 매핑하고 기존 모든 구역의 MVS/prior 표본 수와 대조한다.
- 최초 HTTP 보조 확인이 `mesh=null`인 Gaussian-center 항목을 포함해 실패했다.
  실제 mesh 항목만 선택한 검사에서 15개/45 buffer 전부 HTTP·길이 PASS.
- 원본 입력, 학습, 결과 mesh 및 진행 중인 R1 matched 실행은 변경하지 않았다.
- 최종 보고서: [전체 결과 1차 분석](RESULT_ANALYSIS_20260918_ko.md).

## 2026-09-18 — Z06 직접 렌더 기여 확인 / R2 분할 렌더 복구 시작

- 문제: R1 prior0에만 보이는 Z06 플로터와 R2 DA3/prior0 CUDA OOM.
- R1 확인 원인: 최종 Gaussian row 1816099의 한 축 scale 168.43m. R1 밖의
  중심에서 Z06 관측에 기여해 expected depth를 앞당긴다. 세 선택 pixel에서
  이 기여만 제외하면 depth가 4.06–7.42m 뒤로 복귀한다. CPU/CUDA 재합산 차이
  최대 0.000312m. 성장 시점과 prior 해제의 영향은 같은 GPU의 대조 실행으로 추적한다.
- R2 조치: 전체 해상도/영상/loss를 유지한 row-strip 렌더와 backward 재계산.
  출력/gradient 수치 동등성 검사 PASS 후 두 실패 조건을 신규 출력에 재실행한다.
  30k 및 TSDF 완료 전에는 복구 완료로 표시하지 않는다.
- 상태: `jbgs-r1r2-causal-recovery-20260918.service`가 기존 큐 종료 후 인계받아
  R2 두 조건 preflight를 실제 시작했다. 이어 R1 유지/해제 대조를 진행한다.
- 증거와 제한: [추적·복구 기록](CAUSAL_RECOVERY_20260918_ko.md).

### 진단 replay v1 principal point 및 checkpoint mmap 경로 오류

첫 ray replay에서 FoV 중심을 가정해 실제 보정 K의 cx/cy를 누락했다.
CUDA depth와 최대 약 22m 불일치하여 v1을 원인 근거에서 제외했고, 실제 adapter와
일치시킨 v2만 사용한다. 별도 checkpoint 감사 첫 실행은 torch 2.1 mmap이
Path 객체를 거부해 실패했고 문자열 경로를 사용한 v2가 PASS했다.
두 최초 실패 로그/출력은 덮어쓰지 않았다.

## 2026-09-18 — R2 OOM 후속 읽기 전용 감사: 공통 의심 카메라 확인

지역 140×75m와 달리 실제 학습은 train 221장의 1400×1013 전체 영상이다.
성공 대조군도 최대 allocated 18.228GiB였다. 세 실패의 연속 camera 기록 전체가
대조군과 일치하며, 그 다음 camera는 모두 `DJI_20241217101311_0008_D`로
추적된다. 실패 render 직전 직접 계측과 구분하는 추론 증거다. 해당 영상의
prior0 해제 mask는 0픽셀이며 실패 직전 Gaussian checkpoint는 없다.
CPU Docker 감사 PASS; 학습·입력·기존 결과 변경 없음.
세부 설정, source 경로와 해석 한계는 [R2 OOM 감사](R2_OOM_CONTEXT_ko.md)에 있다.

## 2026-09-18 — R1 조건별 표시 높이 불일치: v5 수정·검증 PASS

- 문제: 국소 prior 0의 Z06 플로터는 보이는데 높은 하늘 표면은 사라져 보였다.
- 확인 원인: 기존 R1 exporter는 local Z `[-90, 80]`을 표시한다. 통합 publisher가
  새 R1 DA3/prior0 조건에는 MVS camera-fit bounds의 Z
  `[-81.285965, -1.835385]`를 적용했다. 카메라 맞춤 범위와 geometry crop을
  혼동하여 서로 다른 높이의 geometry를 비교했다.
- 원본 증거: 같은 하늘 402,500픽셀의 최종 렌더 깊이 중앙값은 MVS 68.854m,
  prior0 66.131m, DA3 366.177m다. prior0 원본 메쉬에는 R1 XY 안에서 잘린
  상한보다 높은 정점이 815,473개 남아 있다. 이 정점 모두를 하늘로 의미 분류한
  것은 아니지만, 깊이 표본과 함께 prior0 하늘 제거라는 해석을 반박한다.
- 조치: publisher v5가 R1의 모든 신규 조건에 기존 exporter의 실제 crop을
  적용한다. crop hash가 다른 신규 cache를 만들고 이전 cache와 원본 학습·메쉬는
  보존한다. 카메라 fit bounds와 R2–R5의 표시 범위는 변경하지 않는다.
- 진단: `sky_crop_audit_20260918/receipt.json`.
  게시 검증: `viewer/crop_validation_v5/receipt.json`으로 HTTP geometry bytes,
  hash, 높이 범위 및 기존/신규 Z06 플로터 정점의 동일성을 확인했다(PASS).
  prior0 표시 최대 Z는 72.100m로 복구됐고, 플로터 상자의 3,450개 표시 정점은
  순서 정렬 후 hash가 동일하다. v5 전체 브라우저 시각 검사는 별도 수행하지 않았다.
- 남은 위험: Z06 조각은 두 표시 높이에 모두 포함된다. 이 표시 오류 수정은
  플로터 발생의 학습/추출 원인을 해결하거나 국소 가중치 효과를 증명하지 않는다.

## 2026-09-18 — R2 국소 prior 0도 CUDA OOM: 실패 보존, 나머지 큐 진행

- 마지막 진행 기록: 14,740회, Gaussian 2,340,642개, finite=true.
- `local_prior0_parallel_recovery_20260918T062211Z/process.log`에서
  `_C.rasterize_gaussians` forward의 단일 20.29GiB 요청이 실패했다.
  당시 allocated=4.32GiB, device limit=23.56GiB다. 합계 24.61GiB는 장치
  한도를 넘는다. loss의 NaN 또는 마스크 코드 예외로 종료된 것이 아니다.
- R2 DA3 재시도도 14,860회, Gaussian 3,235,638개에서 실패했지만, 종료 지점은
  SSIM `F.conv2d`다. allocated=22.81GiB, 추가 요청 16.23MiB,
  CUDA free=10.38MiB였다. `da3_resource_recovery_20260918T014542Z/process.log`에
  최초 DA3 OOM 및 allocator-only 재시도와 구분해 보존한다.
- renderer는 Gaussian이 덮는 image tile 수를 합산한 `num_rendered` 크기로
  binning buffer를 만든다. 따라서 Gaussian 총수나 지역 면적만으로 최대 메모리를
  예측할 수 없다. 정확한 실패 영상/primitive의 과도한 화면 footprint는 아직
  계측하지 않았으므로 이번 두 실패의 세부 기하 원인으로 확정하지 않는다.
- 두 3090은 별도 조건을 병행하며 VRAM을 합치는 구조가 아니다. R2 두 조건은
  실패로 보류하고 다른 조건은 계속한다. 재시도, 해상도 감소, densification
  제한 또는 원본 artifact 덮어쓰기는 추가하지 않았다.

## 2026-09-18 — R1 mask 해제 전 수치 차이: 인과 해석 보류

사용자의 Z06 플로터 재질문으로 실행 동일성을 추가 확인했다. 첫 active mask는
8,015회지만 8,010회 prior/MVS depth loss 이동평균이 이미 미세하게 달랐다.
Anchor·학습 인수·카메라 순서·TSDF 설정은 같지만 GPU·allocator·driver 경로는
다르다. 시선 교차 사실만으로 플로터를 mask 효과로 확정한 듯한 설명은
불충분하다. [후속 진단](R1_Z06_FLOATER_ko.md)의 Docker 로그 감사에 근거를
남겼으며, 동일 실행 경로의 prior 유지 대조군과 반복성 확인 전 인과 판정은
유보한다. 이 확인 과정에서 새 GPU 실험 또는 기존 결과 변경은 하지 않았다.

## 2026-09-18 15:22 — 병렬 큐 후속 작업 중단 및 GPU 0 대기: 복구 실행

- 문제: R3 DA3 학습은 30k PASS였지만 GPU 1 worker가 기존 큐 종료 명령에서
  중단하여 추출·후속 작업을 맡지 못했다. GPU 0은 R1 prior0·R4 DA3를 완료한 후
  자원 대기를 반복했다.
- 확인 원인: 이 호스트 systemd는 `--kill-who`를 지원하며 코드의
  `--kill-whom`은 지원하지 않는다. 기존 단위 검사는 systemctl을 mock하여
  실제 호스트의 옵션 호환성을 검증하지 못했다. 또한 GPU 0 데스크톱/원격 화면
  사용률 때문에 `utilization <= 5%` 조건이 가용 GPU의 작업도 막았다.
- 조치: 완료 receipt와 실패 상태를 보존한 `parallel_recovery_20260918T062211Z`
  실행. 진행 중 학습 컨테이너가 없음을 확인하고 대기 중인 두 관리 프로세스만
  종료했다. R3는 재학습 없이 추출부터, R2 prior0는 이미 통과한 사전검증에서
  이어간다. 원래 비어 있던 R2 학습 폴더도 보존하고 신규 출력 override를 사용한다.
- 자원 규칙: GPU 0은 확인된 gnome-remote-desktop/rustdesk 프로세스의 화면
  사용률을 허용하되 VRAM 여유 23,000 MiB 및 다른 compute process 부재를
  계속 요구한다. GPU 1·RAM 예약 제한은 유지한다.
- 검증: Docker 검사 5개 PASS, 새 systemd 서비스·R3 추출 GPU 실행 확인.
  관리 오류는 이전 status/failure에 남기며 현재 미해결 실험 실패는 R2 DA3다.
  최초 복구 준비 시 R2 사전검증이 이미 진행하여 사전조건 검사가 중단되었고,
  프로세스 변경 없이 종료했다. 그 완료를 재확인한 뒤 위 인계를 수행했다.

## 2026-09-18 — Z06 플로터 진단의 도구 제한과 수정

- CPU 브라우저의 첫 캡처는 대형 메쉬에서 CDP 15초 제한을 넘겨 실패했다.
  60초 설정의 후속 캡처도 지연되어 해당 진단 컨테이너만 중단했다. 사용자 뷰어와
  학습은 변경하지 않았다. 실패 파일은 `floater_diagnostic_20260918/`에 보존한다.
- 대신 실제 뷰어가 제공하는 hash 검증된 geometry buffer의 동일 XY 단면을
  CPU에서 그려 비교했다. 전체 mask endpoint 검사는 최초부터 같은 결과였다.
- 시선-수평면 보조 진단의 최초 roof 참조가 `part=2`(벽)를 사용한 것을 발견해
  `part=1`(지붕)으로 수정했다. 올바른 결과는 `audit_v2/mask_extent.json`이며
  최초 파일은 대체하지 않는다. 학습 mask/구역/판단을 변경한 것은 아니다.

## 2026-09-18 — 단일 GPU 순차 대기: 병렬 실행으로 개선 중

- 문제: 작은 R 영역이어도 남은 정상 8조건의 예상 소요가 11–14시간이었다.
- 확인 원인: 두 RTX 3090 중 하나만 사용하며 조건별 22,000회 전체 영상 학습과
  TSDF 추출을 순차 실행했다. 기존 성공 학습은 조건당 약 64–94분이었다.
- 조치: `parallel_20260918T022117Z`에서 실행 중 R3 DA3를 재시작 없이 인계하고
  GPU 0에 R1 국소 prior 0을 배정했다. 단일 상태 writer와 RAM 예약/FIFO로
  중복 실행 및 추출 간 메모리 경합을 방지한다.
- 해결 범위: 스케줄러 Docker 검사 4개 PASS, 신규 서비스 실행·인계 확인.
  모든 실험의 완료 또는 2배 속도 보증을 뜻하지 않는다. R2 DA3 OOM은 별도로
  보류한다. [병렬화 기록](ACCELERATION_20260918_ko.md)에 상세 근거가 있다.

## 2026-09-18 — R2 DA3 14,740회 이후 CUDA OOM: 자원 복구 진행 중

11:06 KST 후속 확인: allocator 변경 재실행도 마지막 진행 기록 14,860회,
Gaussian 3,235,638개에서 CUDA OOM으로 종료됐다. `Currently allocated: 22.81GiB`
상태에서 추가 할당이 한도를 초과했다. 따라서 **allocator 수정만으로 해결되지
않았다.** 기존 자원 복구의 한 번 재시도 범위를 마쳤고 R2 DA3는 실패 보류한다.
큐는 실패를 보존하고 R3 DA3부터 나머지 독립 조건으로 진행한다. 이 상태에서
전체 15조건의 완료 시각을 약속할 수 없다. 추가 메모리 대응은 별도 작업이다.

- 문제: 카메라 검사 복구 후 R2 DA3 학습이 최종 저장 전 CUDA OOM으로 중단됐다.
  마지막 진행 기록은 14,740회·Gaussian 3,009,165개다.
- 원인: rasterizer가 단일 17.51GiB buffer를 요청했고 당시 free는 17.39GiB,
  PyTorch 미사용 예약 메모리는 약 548MiB였다. 기존 설정은
  `backend:native,max_split_size_mb:128`이었다. allocator 변경으로 끝까지
  수용 가능한지는 아직 확인 전이며 장면 복잡도를 줄이는 수정은 하지 않았다.
- 조치: `cudaMallocAsync` 지원·실제 할당 검사를 통과한 뒤 같은 Anchor와 전체
  영상, 해상도, 가중치, densification, seed를 유지한 신규 R2 출력 경로로 한 번
  재실행한다. 실제 자식 학습 프로세스의 allocator 설정을 invocation에 기록한다.
- 큐: `resource_recovery_20260918T014542Z`. 각 독립 조건이 실패하면 실패 receipt를
  남기고 다음 조건으로 진행하며, 동일 실패 조건을 자동 반복하지 않는다. 최종
  `COMPLETE_WITH_FAILURES`는 성공과 구별한다. R2 재실행 산출물 경로는
  `execution/artifact_overrides.json`과 viewer publisher가 함께 사용한다.
- 보존: 원래 R2 `da3` 실패 폴더와 이전 recovery를 유지했다. GPU 결과 복구 성공은
  30k 학습·추출 receipt가 통과한 이후에만 판정한다.

### 자원 복구 launcher의 bytecode hash 실패: 수정

최초 `resource_recovery_20260918T014236Z`가 import로 변경되는
`__pycache__/run_queue.cpython-310.pyc`까지 source hash에 포함하여 GPU 작업 전
중단됐다. 해당 실패를 보존하고 새 snapshot은 bytecode를 제외하며 host launcher도
`PYTHONDONTWRITEBYTECODE=1`을 설정했다. Python source와 입력의 hash 검사는 유지한다.

### 하늘 비교 진단의 최초 MVS 파일 경로 오류: 수정

최초 CPU 진단은 `mvs_rgb` 바로 아래에서 파일을 찾아 실패했다. `raw_depth` 하위의
실제 봉인 입력 경로로 수정한 `sky_comparison_20260918_v2`가 통과했다. 최초 config와
실패 기록은 보존했다. 학습·메쉬는 변경하지 않았다.

## 2026-09-18 — R2 DA3 카메라 반환 정밀도 검사: 수정·복구 큐 실행

- 문제: 07:06 KST R2 DA3 batch 010에서 `DA3 did not preserve input metric
  extrinsics after scale alignment`로 전체 큐 중단. 이 시점에 R1–R5 MVS의
  30k 학습·추출 및 R1 DA3의 30k 학습·추출은 모두 완료했다.
- 원인: pinned DA3 `input_processor.py`는 입력 extrinsics를 float32로 변환하고
  `api.py`는 이 값을 그대로 반환한다. 우리 driver는 float64 원본과 절대 오차
  `1e-5`로 비교했다. R2 batch 010의 정상 변환 오차는 `1.4972931637657894e-5`로,
  이 검사만으로 실패가 재현됐다. 모델의 카메라 추정 변경이 원인은 아니다.
- 조치: 반환값과 **float32로 변환한 원본의 정확한 동일성**을 검사한다. dtype,
  shape, finite 검사도 유지한다. 입력 pose/RGB, 모델, 배치 구성, seed, 깊이,
  학습 설정은 바꾸지 않는다. 원래 source·실패 출력·실패 상태는 보존했다.
- 검증: 완료된 R1 74배치 및 R2 10배치에 새 검사를 적용해 모두 통과했다.
  float32 한 단계의 실제 좌표 변경 및 NaN/dtype/shape 불일치는 거부한다.
  실패했던 R2 batch 010을 별도 추론해 새 검사 PASS를 확인했다.
- 복구: `recovery_20260918T010840Z`의 독립 서비스가 R2 DA3를 신규 출력 폴더에
  다시 생성하고, R2–R5 DA3 및 R1–R5 국소 prior 0의 미완료 단계만 진행한다.
  완료 산출물을 덮어쓰지 않는다. 후속 실패 시 자동 재시도 없이 기록하고 멈춘다.
- 증거: recovery의 `camera_contract_audit/receipt.json`,
  `R2_pose_preflight/result/receipt.json`, `plan.json`, `source_hashes.json`.
- 남은 확인: 전체 R2 추론 및 후속 학습·추출 완료는 별도 실행 receipt가 필요하다.

## 2026-09-17 — 초기 뷰어 nested mount 실패: 해결

- 문제: 신규 8913 서버 컨테이너 생성 시 `/data/r1legacy` mountpoint를 만들 수 없어 시작 실패.
- 원인: 읽기 전용 `/data` bind 아래에 하위 mountpoint가 없었음.
- 조치: 신규 data 디렉터리에 빈 mountpoint를 만들고 생성된 컨테이너를 시작.
  재사용 launcher에도 같은 사전 생성 추가. 기존 R1 8912는 변경하지 않음.
- 증거: 초기 `viewer_command.json`, Docker created container와 이후 서버 상태;
  Chromium v2 HTTP/JS 검사 PASS.

## 2026-09-17 — 리뷰 스크립트 문법 오류: 해결

- 문제: 첫 review worker가 시작 직후 SyntaxError로 중단.
- 원인: metadata dict comprehension 종료 괄호 오타.
- 조치: 새 `review_source_v2` snapshot으로 수정, 전체 Python AST 검사 후 재실행.
  최초 source와 journal `review_source/failure.log` 보존. 수치 작업 시작 전 실패여서
  기존 리뷰/마스크 산출물 덮어쓰기 없음.
- 결과: 다섯 영역 마스크 생성 PASS. 이 재시도는 GPU 실험 재시도가 아님.

## 2026-09-17 — 첫 브라우저 QA가 R3 draw 전에 판정: 해결

- 문제: 실제 buffer 로드 성공 뒤 `drawn=false`를 읽어 QA 9번째 검사 실패.
- 원인: `settled`가 다음 animation frame의 draw 대기를 포함하지 않음.
- 조치: 신규 앱의 `settled`에 `!renderRequested` 추가, immutable `app_v2` 게시.
- 결과: Chromium QA v2 14개 PASS. v1 실패 receipt 보존.

## 해석상 제한 — R3/R5 국소 개입이 매우 적음

R3은 82픽셀/5장, R5는 1픽셀/1장만 해제된다. 값은 실제 mask 합계이고 gradient
기여량이 아니다. 같은 결과가 나오더라도 국소 가중치 방법의 유효/무효 판정 근거로
일반화하지 않는다. 표면·구역을 임의로 넓혀 차이를 만들지 않았으며 뷰어에 적용량을 표시한다.

## 2026-09-18 — 보정·보존 후보의 연구질문 대표성: 미해결

- 문제: 보정 후보 입력 거리 표만으로 국소 가중치의 추가 개선 효과 또는 DA3의
  독립적인 기하 정확도를 판정할 수 없다.
- 확인: 동결 함수 재현 PASS. R5 전체 24,552점 중 prior가 앞인 264점 → 건물
  문맥 24점 → 보정 문맥 19점 → 국소 평면성 15점으로 줄며 모두 Z04다.
  R1/R2 실제 해제 픽셀에서도 기본 조건이 이미 MVS에 가까운 것은 별도 확인됐다.
- 원인/범위: 보정 후보는 기본 방법의 실패가 아닌 한 방향의 입력 불일치 가설이다.
  보존 후보는 입력 일치 위주여서 잘못된 MVS와 유효한 prior 사이의 갈등을 충분히
  대표하지 않는다. R3/R5의 비영 마스크도 실질적인 실험 범위 확보를 뜻하지 않는다.
- 조치: 선정 과정과 지표 해석을 `COHORT_SELECTION_AUDIT_20260918_ko.md`에 기록.
  원 후보/마스크/결과는 보존. 새 학습이나 사후 평가 표본 변경 없음.
- 남은 확인: 실제 기본 방법의 보정 실패와 보존 실패 사례, 독립 정확도 평가.
  후보 규칙을 검증했다는 기술 PASS와 이 미해결 연구설계 문제를 구별한다.

## 2026-09-18 — UAS 평가 첫 실행의 CRS header 의존성 오류

- 문제: `uas_evaluation_20260918T124001Z`가 R1 악화 위치 산출 후 원본 LiDAR
  header를 읽는 `parse_crs()`에서 `ModuleNotFoundError: pyproj`로 중단.
- 원인: CPU 이미지에 선택 의존성 pyproj가 없음. 좌표나 입력 자체 오류가 아님.
- 조치: 원본 GeoKeyDirectory VLR을 직접 읽어 EPSG=32632를 확인하는 기존
  프로젝트 방식 적용. 설치·좌표 변환 없음. 새 `_v2` payload에서 재실행.
- 보존/검증: 첫 실패 상태와 완료된 R1 위치 지도 보존. 두 완료 파일은 SHA 확인
  후 재사용하며 새 평가의 진행 상태·예외를 파일에 기록. 완료 여부는 `_v2/receipt.json`.

- 후속 결과: `_v2` LiDAR 기본 평가 327.3초, 15메시·3,874,852 공통 표본 PASS.
  위치별 사례 집계의 최초 드라이버는 모든 셀의 분위수를 계산해 4분 넘게 CPU를
  사용했으므로 해당 진단 컨테이너만 중단(exit 137). 학습/서버/완료 평가에는 영향 없음.
  원 소스·로그 보존 후 동일 셀 계수와 tie 순서를 벡터 집계하고 상위 셀만 분위수를
  계산하는 v2로 완료. `case_retry.json`, `case_command_v2.json`, `case_locations.json`.

## 2026-09-18 — 실패 위치 확대 뷰어의 초기 브라우저 QA 대기 실패

- 문제: 신규 failure inspector의 QA 1·2회가 Viewer did not settle로 종료.
- 원인: 첫 회는 디렉터리 URL의 404(index.html 명시 필요), 둘째는 QA 상태의
  settled getter가 non-enumerable이라 CDP 직렬화에서 빠짐.
- 조치: index.html URL 사용, getter를 enumerable로 수정한 app_v2와 qa_v3 분리.
  원 QA receipt·소스는 failure_inspector_20260918T133424Z/qa, qa_v2에 보존.
- 범위: 표시·검사 상태만 수정. 원본 메시·LiDAR·거리·학습에는 변경 없음.
- 재검증 결과: 같은 payload의 qa_v3/receipt.json.

- QA v3: 기하·표본·카메라·전체 지도·모바일 14개 검사 통과 후, 기본 favicon.ico
  요청의 404가 마지막 HTTP 검사에서 발견됨. 신규 페이지에 빈 data favicon을
  지정한 app_v3로 수정. 최종 결과는 qa_v4/receipt.json에 기록한다.

- 최종 해결: app_v3 / qa_v4의 15개 검사 PASS, HTTP exact bytes PASS.

## 2026-09-18 — failure inspector 브라우저 연결 주소 오류

- 문제: 사용자가 새 확대 뷰어가 보이지 않는다고 보고(표시 주소 localhost:3111).
- 원인: 앞선 open_in_codex 호출에 실제 원격 서버 포트 8913 대신 이전 UI의
  임시 연결 포트 4035를 전달함. 서버 호스트의 4035/3111에는 listener가 없음.
- 조치: 실제 서버 http://127.0.0.1:8913/data/failure_inspector_20260918_v1/index.html
  로 다시 open 요청. 기존 서버·실험·기하 데이터는 변경하지 않음.
- 검증: 컨테이너 running, HTML/JS/CSS/case/census/지도 HTTP 200, 네 메시의
  XYZ/index buffer 크기 확인 PASS. 앱 open 결과 queued로 사용자 화면 표출은
  도구 응답만으로 확정하지 않음.

## 2026-09-18 — 큰 참조 거리 후보의 표면 대응 문제와 Z07 재검토

- 문제: 거리 순위만으로 고른 R1 Z03 세 곳과 R5 Z04 한 곳은 아래층·가림
  가능성이 있는 UAS 표본을 비교하고 있었다. GS 외부 지붕 실패로 확정할 수 없다.
- 확인: 원영상 두 시점, 원본 메시 단면, 0.5m XY 열의 상단 참조와 비교했다.
  네 곳은 선택 표본의 상단 근접 비율이 0%. 기존 R1 Z07의 155점도 이 비율은
  80/155(51.6%)로, 경계·다층 대응을 더 확인해야 한다. 거리를 계산한 오류는 아니다.
- 조치: 다섯 사례를 보류 목록으로 이동. Z07 기존 페이지에 해석 보완 표시.
  원래 기하·수치·첫 후보 목록·이전 검토 기록은 보존했다.
- 결과: 외부 지붕 사진과 상단 참조 대응이 확인되는 새 다섯 곳(C03–C07)을
  별도 개선 검토 목록으로 공개. 같은 표본의 prior/MVS/DA3 기하와 입력 depth를 제공.
- 한계: 상단 대응 검사는 완전한 가시성 보증이 아니다. 가중치로 회복되는지,
  편향의 원인이 입력·최적화·TSDF 중 무엇인지는 미확정. 학습 변경 없음.
  상세: `IMPROVEMENT_SITES_20260918_ko.md`, `scientific_verdict: null`.
