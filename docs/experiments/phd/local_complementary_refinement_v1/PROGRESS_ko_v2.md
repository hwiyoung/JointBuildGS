# main_v2 실행 진행 기록

- task_id: PHD-LOCAL-COMPLEMENTARY-REFINEMENT-v1
- scientific_verdict: null
- 사용자 승인: 2026-09-10 전체 새18개 완료까지 구현·검증·실행·평가. 아침 종료 제한 없음.
- 현재 상태: `MAIN_MATRIX_RUNNING`; 2026-09-10 23:12 KST P2 .005 native/release 두 GPU 학습 시작.

본 명세는 [MAIN_SPEC_ko_v2.md](MAIN_SPEC_ko_v2.md)와 [experiment_v2.json](../../../../configs/phd/local_complementary_refinement_v1/experiment_v2.json)이다. config SHA256 `579369916b854f05088ed8427c3b6010e0532343b7b09afb93336ae495c5889e`, source_v2 train SHA256 `297bcf0b357b3e14f617beaffc002ea8322d509356404a90d3b4bc8905c96aca`.

외부 payload root는 기존 resolver의 local task이며, 새 실행 출력은 그 아래 `main_v2/`다. 기존 v1 준비·probe·코드·입력·결과와 서비스는 보존한다. Git stage/commit은 실행하지 않았다.

| 항목 | 상태·근거 |
|---|---|
| 입력 정의·문턱 | 입력 전용292 train view 감사 PASS. 공통 .5/2m 탐색 정책을 새로 채택; correctness calibration 아님. half-pixel convention·포화율·평균 배율 한계 명세 반영 |
| source 준비 | 원 parent source 별도복사 `source_v2/`; 기존파일 변경은 train.py/jbgs_state.py, 새 helper jbgs_local_depth.py. payload/source hash 기록 |
| CPU 검증 | `main_v2/validation/cpu_validation.json`: 48 PASS, 0 failure/error/skip. loss21+evaluation17+runtime10 |
| 평가·보고 보완 후 CPU 통합 | `main_v2/validation/integration_20260910T1454Z/cpu_validation.json`: 109 PASS, 0 failure/error/skip. loss21+runtime10+evaluation33+summary26+maps8+trace11. 실행 당시 코드·테스트 snapshot 보존; 동결 gate의48개 기록은 유지 |
| baseline evaluation 재사용 | `main_v2/evaluation_preflight/attempt_20260910T140234_230545Z/receipt.json`: raw/post42개 PASS, SHA6087242b6898f9286460935c70894750b5d12942db7f19a5c1287e806263de63 |
| 실제 외관 호환 | `main_v2/evaluation_preflight/appearance_20260910T140158_239045Z/receipt.json`: 기존P2 6조건×9카메라×2domain=108행 PASS |
| 학습 결박 | 입력 전파일/Anchor3개/기존18개 final checkpoint+PLY SHA 검증 PASS. `contracts/main_v2/input_binding.json` SHA75b7a3c8d5ca2c0633587af76cd68e86076e4ffc4c7add53cf3462e5821d8a14 |
| 새 GPU probe | P2 .005 native/release 각각8001까지1step PASS. 실제 complete model/optimizer/controller/camera/RNG 즉시 복원 일치. native 보호114521개, release0개 |
| execution_ready | `contracts/main_v2/execution_ready.json` PASS_FROZEN 및 PASS_VERIFIED. source/config/helper/probe/CPU/baseline attestation 결박 |
| 새18개 | 2026-09-11 06:01 KST P1/P2/P3 .005와 P2 .0005 native/release의 train/render/metrics 모두 PASS(8/18). P1 .0005 두 학습 진행 중. 첫6개 및 P2 두 prior 계수4개 부분 평가·수치/원본/지도 QA·시각 검토 완료. 전체 행렬은 미완료 |

모델 큐는 `run_queue_v2.sh`이며 .005→.0005→0, P2→P1→P3, native/release 쌍으로 진행한다. extraction과 training은 겹치지 않는다. host70GiB이면2GPU,38GiB 이상이면 순차 실행한다. `main_v2/queue/events.log`와 개별 phase receipt가 실제 진행 근거다.

실행 host 자원·기존 컨테이너 목록은 `main_v2/environment/before_gpu/`, 실제 첫 학습 두 컨테이너의 읽기전용 input/Anchor/source/contract와 새 output 전용 쓰기 mount·GPU·CPU·RAM·network는 `main_v2/environment/main_started/actual_training_mounts.jsonl`에 기록했다. 첫 background queue launch는 학습 전 종료되어 `main_v2/queue_launch_attempt_1/`에 보존했고, 같은 코드의 유지되는 실행 세션으로 진행 중이다.

평가 driver는 `run_evaluation_v2.sh evaluate`, 그림은 `run_evaluation_v2.sh figures /task/main_v2/evaluation/attempt_<id>`로 별도 새 attempt에 생성한다. queue의 모델단계 완료를 전체 평가 완료로 부르지 않는다. 최종 원인·방법신규성·검증기여·문제차별성은 각각 기술하고, 평균배율 전역대조/controller replay/반복의 부재를 유지한다.

실패와 수정은 [ISSUES_ko_v2.md](ISSUES_ko_v2.md)에 기록한다.

## 학습 중 진단 — 2026-09-10 23:48 KST

P2 `.005` native/release는 각각 약19,900/20,200 step에 도달했다. 이는 진행 관측이며 최종 학습·추출·평가 완료 수는 아직0/18이다. 실행 중 trace snapshot은 `main_v2/trace_monitor/`의 독립 attempt에 보존한다. `attempt_20260910T142313Z_checkpoint_scope`는 native8100–13800/release8100–13900의 서로 다른 관측 범위를 명시한다.

해당 snapshot의 release에서는11600 step부터 기존 G의 lambdaV=.0475와 LC의 .05가 달랐다. 같은 controller 코드를 사용해도 실제 제어 궤적이 같지는 않다는 관측이며, 이번 비교는 국소 가중과 controller 반응을 함께 포함한다. raw prior residual 증가·DA3 residual 감소는 학습 목적의 상충 관측으로만 기록하고 형상 수정·손상으로 판정하지 않는다.

계산 비용에는 기존 primary1024+RGB export, 기존 auxiliary512의 RGB export 제외, 새512+RGB export, checkpoint 저장 횟수와 학습 시작 iteration, 타이머 범위 차이를 따로 표시한다. 이 상태의 wall/RAM/VRAM 차이를 방법 자체의 효율 이득으로 주장하지 않는다. 평가·보고 코드의 추가 회계/계보 검증은 학습 config/source/helper를 바꾸지 않고 별도 변경 receipt와 Docker 검증으로 남긴다.

`attempt_20260910T144849Z_both20k`의 후속 trace는 native8100–20200/release8100–20500을 보존했다. 실제 같은 카메라 비교는122/122와125/125, lambdaV 불일치는0과90개다. 평균 raw prior loss는 G보다 높고 평균 raw DA3/RGB loss는 낮았지만 개별 표본의 악화도 남는다. 관측 범위가 서로 달라 native/release 평균을 직접 효과 비교로 사용하지 않으며 형상 판정은 최종 평가 전까지 보류한다.

## 첫 모델 쌍 완료 — 2026-09-11 00:35 KST

P2 `.005` native/release의 학습·최종 complete checkpoint/PLY·512 raw/post 표면·원사진 대응 렌더·외관 지표가 모두 PASS다. 학습 driver wall은4740.651/4608.698초, child peak RSS는13,571,104,768/14,352,314,368bytes이다. 저장·검증을 포함하는 현재 driver 범위의 비용이며 과거 G와 타이머 범위가 다르다.

P1 `.005` 두 학습이 시작된 것을 확인한 뒤 P2 부분 평가를 실행한다. 실행 직전 host MemAvailable=64,240,040kB, CPU 평가 cap=4CPU/16GiB다. `main_v2/environment/before_first_p2_evaluation/`에 자원을 기록했다. 이 CPU 평가는 P1 GPU 학습과 겹치므로 관련 시간은 자원이 독점된 비용 비교가 아니다. 학습/추출 사이의 기존 순서는 유지된다. 첫 실제 부분 결과가 나오더라도 전체18개 완료·전체 평가로 부르지 않는다.

첫 두 조건의 실제 관측과 계보는 [INTERIM_P2_D005_ko_v2.md](INTERIM_P2_D005_ko_v2.md)에 정리했다. Raw512/0.5m에서 G 대비 완전성은 −13.70/−9.33%p이고, 같은 참조점 손상은 수정 수보다 많다. 전체9카메라 PSNR 평균은 높지만 선택된 native ROI는 −0.514dB로 악화했다. 사진·단면·지도와 모든 G 대조를 함께 보존한다. 이 중간 관측에 따라 미완료 조건·문턱·학습량을 변경하지 않는다.

## 분석 재현 진입점 — 2026-09-11 01:55 KST

[START_HERE_ko_v2.md](START_HERE_ko_v2.md)에 현재 명세·실행 상태·평가 명령을 연결했다. 이전 v1 인계는 준비 이력으로 보존한다. 새 `run_strata_v2.sh`와 `run_trace_v2.sh`는 기존 분석기를 바꾸지 않고 pinned Docker image, 제한 자원, 필요한 작은 파일의 읽기 전용 mount, 코드·launcher·runtime snapshot을 기록한다.

실제 P2 strata 재실행 `main_v2/strata_diagnostic/attempt_20260910T165137_400728120Z/`의 CSV4개가 기존 진단과 바이트 단위로 일치했다. 증거는 `main_v2/evaluation_preflight/strata_launcher_equality_20260910T165137_400728120Z/receipt.json`이다. trace 재실행 `main_v2/trace_monitor/attempt_20260910T165302Z_VPRARG_trace_v2/`는 완료2/진행2/미시작14의 명시적 부분 snapshot으로, P2의 완결된 각220개 같은 카메라 표본을 재확인했다. P1은 서로 다른 진행 범위의 관측이며 최종 평가를 대신하지 않는다. 학습 config/source/runtime helper는 변경하지 않았다.

## 두 번째 모델 쌍 완료 — 2026-09-11 02:25 KST

P1 `.005` native/release의 train/render/metrics가 모두 PASS했다. 학습 driver wall은6058.524/6165.635초이며, 저장·검증을 포함한 현재 타이머 범위다. `main_v2/environment/first_p1_extraction/`에 자원과 실제 native 렌더 컨테이너 설정을 보존했다. P3 `.005` 두 학습이02:25:20 KST 시작했다.

P3 학습 컨테이너가 실제 시작한 것을 확인한 뒤 P1 부분 평가를 시작했다. 실행 직전 MemAvailable=73,261,952kB, CPU 평가 cap=4CPU/16GiB이며 `main_v2/environment/before_first_p1_evaluation/`에 기록했다. CPU 평가와 P3 학습은 겹치며, 전체18개 완료나 자원 독점 비용 비교를 뜻하지 않는다.

P1의 실제 부분 평가·같은 점/셀 전이·source 층·완료 trace·사진/단면 검토는 [INTERIM_P1_D005_ko_v2.md](INTERIM_P1_D005_ko_v2.md)에 남겼다. 대응 G 대비 완전성−20.46/−19.83%p와15카메라 ROI PSNR 평균+3.743/+4.101dB가 함께 나타났다. 고정 선택 ROI는−1.265/−.996dB로 악화했다. 독립 원본 pixel/crop/PSNR 검증 PASS와 실제10개 PNG 시각 검토를 보존했다. Raw/post·모든 G 조건·미지원 참조점과 국소 수정·손상을 함께 보고하고, 미완료 조건이나 동결 학습 정책은 바꾸지 않았다.

## 첫 prior 계수의6개 모델 완료 — 2026-09-11 04:40 KST

P3 `.005` native/release의 train/render/metrics가 모두 PASS하여 첫6개 모델 단계가 완료됐다. 학습 driver wall은6100.877/7501.454초, child peak RSS는18,526,359,552/22,940,512,256bytes다. `main_v2/environment/p3_first_pair_training/`의 실제 두 컨테이너 mount는 입력·Anchor·source·계약 읽기 전용 및 새 output만 쓰기 가능이고, 평가 GT mount가 없음을 확인했다. CPU8/RAM32GiB/GPU1 및 network none도 실제 설정으로 확인했다. `main_v2/environment/first_p3_extraction/`에는 실제 native 렌더 컨테이너와 자원 기록을 남겼다.

P2 `.0005` native/release는04:40:21 KST에 같은 지역의 원 complete Anchor8k에서 새로 시작했다. 두 컨테이너의 실행과 첫 iteration 전진을 확인한 뒤 첫6개 통합 부분 평가를 실행했다. 직전 MemAvailable=70,023,856kB, CPU 평가 cap=4CPU/16GiB이며 `main_v2/environment/before_first6_evaluation/`에 기록했다. 이 CPU 평가도 새 P2 학습과 겹친다. 첫6개 평가에는 명시적 `--allow-partial`을 사용하며, 전체18개 평가 완료로 부르지 않는다.

## 첫6개 평가·시각 검토 완료 — 2026-09-11 05:06 KST

[첫6개와 P3 보고](INTERIM_D005_ALL_REGIONS_ko_v2.md)에 전체 대조·수정과 손상·source 층·사진/단면·controller·비용을 정리했다. P3의 대응 G 대비 F1은+.04541/+.05877이나 완전성은−4.23/−3.46%p다. 기존 P3 약한 prior 전역 대조가 이미 비슷하거나 더 높은 지표를 내는 점을 함께 보고한다. 선택 사진 ROI PSNR은−.03526/−.28687dB이며, 전체 ROI 평균 상승과 구분했다.

첫6개 평가 receipt SHA256은 `3e19a441629f5a49f6a5413c4a8f4c5b3a7c60d6708fefd79ce91fdc48bfc08b`다. `run_figure_review_v2.sh`의 독립 원본 pixel/crop·PSNR·단면 수 QA6개는 PASS했고 실제 P3 사진/단면6개·지도2개·부분 행렬2개를 열어 검토했다. 앞선 P1/P2 별도 평가와 통합 평가 사이14개 CSV의 해당 행,8개 NPZ,12개 사진/단면 PNG,8개 map CSV/PNG가 정확히 일치했다. 이42개 동등성 검사는 분석 재계산 검증이며 독립 학습 반복이 아니다. 증거는 `main_v2/evaluation_preflight/first6_parity_v2/receipt.json`이다.

P2 .0005는같은 시각 native17,400/release17,800 step까지 전진 중이었다. 이 부분 관측에 따라 동결 config·source·runtime helper 또는 남은 조건을 바꾸지 않았다.

05:12 KST, 새 독립 `run_map_review_v2.sh`도 실제 첫6개에서 PASS했다. 원 Anchor/G/LC 거리 배열의 정확한 참조점 ID·XYZ로18개 panel의 모든 격자 수정·손상·유한 거리 쌍·strict 지원·표시 범주를 재계산했다. `main_v2/maps_review/attempt_20260910T201112_205568Z/receipt.json`에 입력 hash·코드 snapshot·명령·Docker runtime/비용을 보존했다. 이전 지도·평가와 학습 코드는 변경하지 않았다.

05:33 KST, figure QA의 Anchor 전체 패널 독립 원 렌더 대조를 보완한 revision `v2.1_all_four_native_panel_sources`도 실제 첫6개에서 PASS했다. 결과는 `main_v2/figures_review/attempt_20260910T203212_627796Z/receipt.json`이다. 네 패널의 원본 pixel·카메라 identity와 각 ROI crop, 선택 PSNR, 단면 수가 모두 일치했다. 이전 source/receipt를 보존했고 검사 범위 보완을 issue에 남겼다. P2 .0005는24,100/25,200 step까지 진행했다.

## 네 번째 모델 쌍 완료 — 2026-09-11 06:01 KST

P2 `.0005` native/release의 train/render/metrics가 모두 PASS하여8/18개 모델 단계가 완료됐다. 학습 driver wall은4599.872/4293.920초, child peak RSS는12,295,966,720/12,097,687,552bytes다. 최종 Gaussian 수는2,937,027/2,886,557이며 기록된 최종 lambdaV는.05/.0475다. 이는 현재 driver·조건의 관측이고 순수 방법 비용 이득을 뜻하지 않는다.

P1 `.0005` 두 학습은06:01:09 KST에 시작했고 두 실제 컨테이너 및 iteration 전진을 확인했다. 이어 P2의 `.005/.0005` 네 조건만 명시적으로 `--region P2 --allow-partial` 평가를 시작했다. 직전 MemAvailable=66,875,836kB이며 `main_v2/environment/before_p2_0005_evaluation/`에 자원을 기록했다. CPU4/RAM16GiB 부분 평가와 P1 학습이 겹치므로 자원 독점 비용 비교가 아니다. 모델8개 완료를 전체18개 평가 완료로 집계하지 않는다.

P2 네 조건의 부분 평가·요약·source 층·사진/단면·지도와 독립4개 원본 패널/PSNR/단면·원 거리→모든 cell QA가 완료됐다. 새 `.0005` 사진/단면6개·지도2개·부분 행렬2개를 실제 열어 검토했고, [P2 .0005 보고](INTERIM_P2_D0005_ko_v2.md)에 기록했다. 해당 평가 receipt SHA256은 `2cd606390cb3bc70a6077e292bb194a9bef9be6d2720fe98c4eaeb7fd626aa25`다. 이 attempt는P2 네 조건만 선택했으므로4/18 표시와 지역 내 미완료2개를 전체 모델8/18 상태와 구분한다.

P2 .0005의 대응 G 대비 정확도는−2.9543/−3.2899%p, 완전성은−2.8398/−2.0071%p, F1은−.030058/−.024955다. 같은 점의 수정14,822/16,374개와 손상31,072/27,859개, 기존 수정 소실17,423/10,638개를 함께 기록했다. 전체 PSNR 평균도−.251626/−.090938dB, 선택 ROI는−.99769/−.59827dB다. Release의 both-far 평가 층처럼 수정이 손상보다 많은 부분도 포함했다. 이 값은 단일 실행의 제한된 관측이며 문턱·미완료 조건 또는 scientific_verdict를 바꾸지 않는다.

## 다섯 번째 모델 쌍과 부분 평가 완료 — 2026-09-11 08:15 KST

08:33 KST 실패 확인: P3 .0005 native의 첫 train이08:25:53 KST CUDA OOM으로 종료됐다. 원 run은 보존하고 release 및 나머지 queue는 계속한다. 현재 성공10/18, 실패1, 진행1이다. [재시도 계획](RETRY_PLAN_ko_v2.md)에 직접 원인·실패 비용·GPU1 동일 정책 새 attempt와 평가 선택 계보의 보완을 기록했다. 전체18조건에서 제외하지 않는다.

08:30 KST 후속 보조 검토: [A–F 원사진/target 사례](PHOTO_TARGET_CASE_REVIEW_ko_v2.md)를 추가했다. 과거 max-cohort-count 타일·원본 ID·카메라·원 depth의 재계산 및 native crop이6개 모두 PASS했고 실제 figure/crop12개를 열어 검토했다. P1 A/B에서는보이는 포장면과2.4–2.7m 높은 DA3 목표를 구분했고, E는식생 가림 불확실성을 유지했다. 첫6개 결과의 case/subset24행에서 기존 성공·LC 손상을 연결했으며 전체18개 후 같은 사례 표를 추가한다. 학습과무관한 CPU 평가·별도 config이며 main config/source/runtime은변경하지 않았다.

P1 `.0005` 두 조건은08:04:59 KST에 train/render/metrics가 모두 PASS하여 모델10/18개 완료다. 학습 driver wall6994.688/5807.409초와 child peak RSS24,218,574,848/22,405,742,592bytes를 기록했다. `main_v2/environment/p1_0005_mid_training/`, `p1_0005_extraction/`에 자원과 실제 native 렌더 설정을 보존했다. 평가 GT 없이 입력·Anchor·source·계약 읽기 전용, 새 output만 쓰기 가능하며 GPU1/CPU8/RAM32GiB/no swap/network none을 확인했다.

P3 `.0005` 두 학습은08:04:59 KST에 시작했다. 실제 실행과 iteration 전진을 확인한 뒤 P1 `.005/.0005` 네 조건 부분 평가를 진행했다. 직전 MemAvailable=63,973,096kB를 `main_v2/environment/before_p1_0005_evaluation/`에 남겼다. CPU4/RAM16GiB 평가와 P3 학습이 겹치며 비독점 비용이다.

[P1 .0005 보고](INTERIM_P1_D0005_ko_v2.md)에 네 조건 평가·요약·source 층·trace·사진/단면·지도와 실제 새10개 PNG 검토를 남겼다. 평가 receipt SHA256은 `c9fbc91a8d9f8bdb6eef3713af97dd9834b3a7f05a1183397c8e066990e79cd0`다. 네 원본 패널/PSNR/단면과 원 거리→모든 cell 독립 QA는4개 모두 PASS했다. Native 완전성+1.2433%p에도 정확도−4.7191%p와 기존 수정 소실7,925개가 함께 발생했다. Release 완전성은−1.0072%p, F1은두 조건 모두 낮아졌다. 고정 선택 ROI PSNR도−.29541/−.24373dB다. 남은8개 모델·전체 평가와 과학적 해석 제한을 유지한다.

## 재시도 선택을 위한 분석 검증 — 2026-09-11 08:56 KST

모델 단계는성공10/18·실패1·진행1·미시작6이다. P3 .0005 native의 GPU1 같은 정책 재시도는 main queue lock을 기다린다. [재시도 계획](RETRY_PLAN_ko_v2.md)에 성공 시도를 명시적으로 선택하는 분석 resolver와 최종 명령을 추가했다. 동결 학습 config/binding hash는 그대로다. 추가 분석 검증은138개 전체 PASS, 기존6조건 그림18PNG exact hash parity, 독립 원본4패널/PSNR/단면6조건 PASS다. 원본 조회 trace 분석도10/1/1/6 상태를 구분했다. 과거 평가와그림은 보존했으며 실제 retry 성공 후 전체18개 선택 및 평가 검증은 아직 남아 있다.
# 진행 결과 3D·정성정량 열람과 독립 후속 작업 — 2026-09-11 10:20 KST

10:20:33 KST 첫 실제 자동 연쇄가 끝나 게시 결과도11조건으로 늘었다. P3 `.0005` release를 포함한3조건 부분 평가를 기존 P1/P2 묶음과 결합했다. 새 정적/3D packet 및 실제336개 브라우저 PASS 경로는 [열람·무인 후속 인계](VIEW_AND_AUTOMATION_ko_v2.md)에 남겼다. 아래10개는 최초 게시 시점의 기록이다. 자동화는 active/running이며 다음 완료를 기다린다. 전체18개 완료와 수동 해석은 별개다.

[열람·무인 후속 인계](VIEW_AND_AUTOMATION_ko_v2.md)에 현재10개 검증 결과의 정적8905·3D8906 화면을 연결했다. 정적 실제 브라우저230개, 3D306개 검사는 PASS이며 원 사진·원 거리·raw/post512 실제 삼각형 계보와 대조 G 조건을 결박했다. 이전 viewer와 서비스를 보존했다.

모델은11개 완료했고 P2 prior0 두 학습이 계속한다. 원 P3 .0005 native CUDA OOM과 이미 등록된 동일 정책 GPU1 retry는 그대로 보존한다. 새 systemd 단위가 기존 main queue의 완료 event를 읽어 부분 평가·게시를 시작했으며, 전체18개 후속 평가·비용·사례·3D 실제 브라우저 검증도 스크립트로 연결했다. 모델11개 완료와 화면10개 검증 완료를 구분한다. 에이전트의 주기적 감시나 예약 LLM 호출은 사용하지 않는다.

추가 완료 판정17개 Docker 검사와 실제 부분 묶음의 전체완료 거부 검사가 PASS했다. 최초 systemd PATH의 `rg` 결손으로 source 감시 목록 일부가 빠진 문제는 실행 코드를 바꾸지 않고 guard305개로 보완했다. 초기 guard/오류와 복구 시점을 별도 receipt에 남겼다. 전체18개 완료·인간의 새 그림 해석·과학적 판정은 아직 이뤄졌다고 보고하지 않는다. `scientific_verdict: null`이다.
