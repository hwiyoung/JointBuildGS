# SfM 초기화·Anchor 생략 실험 인계

2026-09-10 · 주22k/30k 자원 실패로 종료 / 별도8k 비교 완료 · `scientific_verdict: null`

사용자가 P1/P2/P3에서 SfM 초기 Gaussian으로 Anchor를 생략하고 바로 refinement하여 기존 결과와 비교하도록 요청했다. 실제 세 지역을 실행했고 마지막 재시도까지 모두 CUDA OOM으로 닫혔다. 주22k/30k는 미제공이며, 고정 역사적8k의 실제 학습 상태·공식 렌더·TSDF512·정량/정성 비교는 완료했다. 이 문서는 그 부분 결과와 실패를 인계한다. 원 연구 질문의 확증적 해답이나 전체 학습 성공 보고가 아니다.

계획은 `SFM_NO_ANCHOR_PLAN_ko_v1.md`, 입력 감사는 `SFM_NO_ANCHOR_SUPPORT_DIAGNOSTIC_ko_v1.md`, 실행·실패·복구는 `SFM_NO_ANCHOR_EXECUTION_ko_v1.md`가 소유한다. 재사용 driver는 `scripts/phd/geogs_p1p2p3_v1/no_anchor_v1/`, 설정은 `configs/phd/geogs_p1p2p3_v1/no_anchor_sfm_v1.json`이다.

## 고정 조건

- 실제 고정 COLMAP SfM 점, 지역 train track 2개 이상, 같은 context crop. ALS 초기 점 삽입·기존 checkpoint 복원 없음.
- Stage switch 0, 첫 step부터 refinement, ALS 깊이0.005, 원 DA3 동적 정책·native 보호. 초기 SfM의 ALS 근접 Gaussian만 보호하므로 초기화에 따른 보호 대상 차이가 있다.
- seed0, 새 optimizer·1부터의 일정, 30,000회 연속 실행 중22,000/30,000 snapshot 비교. 전자는 기존 refinement 횟수, 후자는 기존 전체 횟수와 맞춘다.
- 초기화·Anchor 유무·일정을 함께 바꾼 대체 경로 진단이다. 순수 Anchor 단일 요인이나 image-only로 부르지 않는다. 역사적 전체 영상 SfM 계보 때문에 독립 확증 평가도 아니다.
- 같은 원 영상·카메라·ALS·DA3, 원 공식 렌더·TSDF512 raw/post, 같은 UAS 평가 범위·거리 임계값·표본 밀도. UAS는 학습·설정 선택에 사용하지 않는다.

## 현재 종료 상태 — 2026-09-09 21:51 UTC / 09-10 06:51 KST 확인 이후 갱신

아래 과거 진행 기록보다 이 절이 우선한다. **활성 학습은 없다.** 마지막 시도 P1/P2/P3의 native receipt는 모두 FAIL/native1이고 각 독립 supervisor의 exit1을 확인했다. 기존 GPU desktop과 서비스는 유지했다. 추가 fresh 재시도 상한을 소진했으므로 대기하거나 학습을 재시작하지 않는다.

| 지역 | 마지막 실패 |22k/30k 완전 상태 |
|---|---|---|
| P1 |10608회 경계 완료 후10609 backward CUDA OOM | 없음 |
| P2 |22000번째 optimizer 반환 뒤 정기 평가 forward CUDA OOM; 전체 경계21999 | 없음; 마지막 완전 저장15k |
| P3 |8541회 경계 완료 후8542 backward CUDA OOM | 없음 |

P2 native receipt SHA는 `65ed9d68de101e693f5d2f3b3a636085286d61b6a0ef22f541af291ce05ed9af`, driver13,834.020002713893초다. 일반 trace21900과 lifecycle last_completed21999, optimizer22000 반환 후 평가 실패를 구분한다. 평가가 저장보다 먼저라22k complete receipt/PLY가 없고30k는 실행되지 않았다. `queue/P2/status.txt=TRAINING`과 supervisor의 `RUNNING_FIXED_FINAL_RETRY`는 과거 단계 문구이며 종료 receipt/exit1/실제 프로세스 부재를 우선한다.

계획했던22k 공식 RGB preview는 필수 상태가 없어 **미실행**이다. 관련 code/config/문서는 개발 기록으로 보존하며 `preview22000_v1/P2` 결과 경로는 만들지 않았다. 부분 정기 평가 PNG는 셔플된 카메라 순서의 일부 출력이므로 갤러리·정량에 쓰지 않았다. 원 결과를 손실 없이 남기기 위한 평가·저장 경계 개선은 후속 운영 질문이고 이번에 다시 실행하지 않았다.

현재 볼 결과는 [실제3지역8k 비교 뷰어](http://127.0.0.1:8902/app/index.html?manifest=/task/evaluation/no_anchor_sfm_prefix8000_v1/profiles/viewer_v1/manifest.json&color=height)다.③ Anchor8k /⑤ SfM no-Anchor8k /④ 기존30k 문맥을 구분한다. 원결과는 [통합 분석](SFM_NO_ANCHOR_RESULTS_ko_v1.md), 사진별 표·민감도·단면·거리 지도는 [8k 분석](SFM_PREFIX8000_RESULTS_ko_v1.md)에 연결한다. 최종22k/30k 실패 profile과 비용·브라우저 종료 검증은 이 문서의 최종 발행 절을 따른다.

## 과거 실행 확인 — 종료 전 진행 기록

이 절이 아래 과거 진행 기록보다 우선한다. 고정한 이전 storage-v2 시도는 세 지역 모두 자원 실패로 닫혔다. P3는 11,271회 완료 뒤 SSIM convolution의 CUDA 할당에서 실패했다(native exit1, driver3221.676865초). 이 실패는 앞선 GPU 중복 진입에 따른 초기화 실패와 별개다.

마지막 자원 재시도는 세 지역 모두 `no_anchor_sfm_gradient_memory_v3_Px/amendment.json`으로 봉인했다. P1은 10,608회 완료 뒤10,609회 backward CUDA OOM으로 종료됐다(native1, driver3254.014911초). P3도8,541회 완료 뒤8,542회 backward CUDA OOM으로 종료됐다(native1, driver2354.341348초). 지역당 추가 fresh 실행1회 상한에 도달했으므로 P1/P3를 다시 학습하지 않는다. P2만 GPU0에서 계속 실행 중이다. 각 root의 `detached_run_v1/` supervisor와 native receipt를 함께 확인한다. 새22k/30k 결과는 아직 없으며 P1/P3는 해당 두 학습량에 대해 실제 자원 실패 상태다.

P2는 마지막 재시도에서15,000회 optimizer와 완전 checkpoint·PLY 저장을 모두 통과했다. 이전 storage-v2의15k 저장 중 host memory 실패와 구별한다. `runs/P2/SFM_noanchor_D005_Pnative/model/jbgs_complete/iteration_15000/receipt.json` SHA는 `4138616987319aa112dfdb2c219bf48a45d5aac043f982604d955aed38ba199f`, checkpoint SHA는 `90635d288d0abdc522bf5b8e2a0314764f287bcb3bf23006f75ff0818749ce0f`, PLY SHA는 `39eb2eb976690c8ee236b8825abdd0f4f42948b9f4e1a75b0d7cd0e5373ed75d`다. 2026-09-09 19:22 UTC 이후의 실제 trace 확인은15,400회, 전체10,334,149개·보호1,437개였다.15k는 I/O 보조 상태이며22k/30k 비교 결과로 대체하지 않는다. 당시 약1.3초/회의 속도로30k까지 수 시간이 더 걸릴 수 있었으나 학습량을 줄이도록 사용자가 답하지 않았으므로 원 계획대로 계속한다.

고정한 역사적8k 보조 진단은 세 지역 모두 완전 상태 검증·공식 RGB·TSDF512 raw/post 추출·기하·사진 평가·요약까지 실제 완료했다. 산출물은 `evaluation/no_anchor_sfm_prefix8000_v1/`에 분리한다. 이8k는 원 실패 시도의 사전 고정 상태이며 마지막 재시도의8k로 교체하지 않는다. 전체 학습의 FAIL과8k 평가 PASS를 구별한다.

8k viewer는 `profiles/viewer_v1/manifest.json`으로 실제 생성했다. `qa/actual_v1/receipt.json`은 `PASS_PREFIX8000_BROWSER_QA`,208검사·9스크린샷이며 새 raw/post 메시6개와 RGB 갤러리3개를 실제 제공한다. 기존 viewer/service/app source는 보존했다. 확인한 주소는 `http://127.0.0.1:8902/app/index.html?manifest=/task/evaluation/no_anchor_sfm_prefix8000_v1/profiles/viewer_v1/manifest.json&color=height`다.③ ALS Anchor8000과⑤ SfM8000이 주 비교이고④ 원 final30000은 다른 학습량의 문맥 결과다.22k/30k 완료 화면과 혼동하지 않는다.

실제3지역 통합 표는 `report_table_v1/comparison.csv`, 사진44쌍의 비교는 같은 폴더 `per_photo_comparison.csv`, 지역별 원자료는 `summary/Px/R8000/`다. 분석은 [8k 결과 문서](SFM_PREFIX8000_RESULTS_ko_v1.md)가 소유한다. 관측참조의 동일 index/XYZ에서 근접도 유지·획득·상실을 비교한 `support_transitions_v1/`은 별도 진단이며 시간적 자산 유효성 정답이 아니다.

[기존30k 해석 보완](RESULTS_CONTEXT_ADDENDUM_ko_v1.md)도 함께 읽는다. P1/P3는 기존 Anchor를 수행한 경로에서도 refinement 후0.5m raw F1이 낮아졌다. Anchor8k 대비 신규8k의 감소 전체를 Anchor 생략의 인과 효과로 귀속하거나, 학습량이 다른 기존30k와의 근접한 값을 동등성으로 해석하지 않는다. 원8k 결과 문서는 작성 시점의 실행 상태를 보존하므로 현재 P3 실패 상태는 이 인계의 현재 절을 우선한다.

P3의8k CPU 상태 검증에서2GiB cgroup memory pressure가 확인되어 그 검증 컨테이너만8GiB로 늘렸다. 편차는 `completed_prefix8000_v1/P3/validation/resource_memory_amendment_v1/`에 보존했다. P1 검증은 변경 전에 이미 PASS로 종료했으므로 P1의 메모리 제한을 늘린 것으로 기록하지 않는다. 학습 GPU·32GiB 제한·원 과학 설정은 이 조치로 변경하지 않았다.

P2의 동일8k 결과는 혼합적이다. raw F1@0.5m은 Anchor0.465087→SfM0.377779로 낮아졌고, F1@1m은0.618817→0.693505로 높아졌다. ROI PSNR은13.739081→14.857164dB다. 더 매끈한 외관을 정밀 형상 개선으로 바꾸어 해석하지 않는다. 표·실제 사진·단면을 함께 읽는다. viewer는 세 지역 평가와 실제 browser 표시 검사 뒤 새 profile로 제공한다.

## Payload와 이전 진행 기록

Task root는 sibling `JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1`이다.

| 지역 | 원 실행 `no_anchor_sfm_v1` | 선택할 자원 복구 root | 이 문서 작성 시점 |
|---|---|---|---|
| P1 | 약10,780회 backward CUDA OOM | `no_anchor_sfm_memory_recovery_v2` | 11,902회 완료 후11,903회 forward CUDA OOM;8k 완전 상태 보존 |
| P2 | 14,400회 직후 backward CUDA OOM | `no_anchor_sfm_memory_recovery_P2_v2` | 15,000회 저장 중32GiB cgroup OOM kill; native−9,8k 완전 상태 보존 |
| P3 | 약8,710회 forward CUDA OOM | `no_anchor_sfm_memory_recovery_P3_v3` | P1 실제 종료 후 GPU0 새 학습 진입; 첫 step PASS |

각 root의 `runs/Px/SFM_noanchor_D005_Pnative/receipt.json`이 닫힌 실행 상태이며, `model/jbgs_trace.jsonl`은 진행 계측이다. `queue/Px/status.txt`는 worker 상태이므로 실패 때 남은 이전 문구보다 receipt와 exit code를 우선한다. 원 실패는 덮어쓰지 않았다. 이 시점에는 새22k/30k 표면·렌더 결과가 없다.

**기존 P1/P2 v2 `queue/.../exit_code.txt=0`을 완료로 사용하면 안 된다.** 15:57:55 UTC에 부모 실행기 종료 표시가 먼저 생겼으나 Docker native 학습은 계속됐고, 도구 세션은 exit143을 반환했다. 신호 발신자는 미확인이다. 이 파일 존재만 확인한 옛 P3 대기부가 GPU0에 조기 진입해 P3 v2는 카메라 CUDA 초기화 중5.029초 만에 실패했다. 이전 `run_region.sh` 부모는 사라졌으므로 후속 export도 자동으로 이어질 수 없었다. 학습을 중단하지 않고 `orchestration_recovery_v1/P1`, `/P2`의 별도 setsid/nohup continuation을 연결했다. 여기의 실제 supervisor PID·status·exit와 native receipt·Docker 프로세스 상태를 함께 확인한다.

P3 v3는 같은 v2 source bytes이며 `prior_initialization_failure`로 조기 실행 실패를 봉인했다. `lane_wait/`의 새 대기부는 P1 native receipt, continuation 종료 및 프로세스 부재, GPU0 compute-process 부재, P1 train/export container 부재를 함께 검사한다. CPU/GPU 자원 편차와 실패는 보존하고 품질 실패로 분류하지 않는다. 상세 기록은 `ISSUES_ko_v1.md`의 SFM-QUEUE-001 및 실행 기록에 있다.

현재 활성 P3 대기부는 **`lane_wait_desktop_v2/`**다. 완전 빈 compute 목록을 요구한 앞선 `lane_wait/`는 기존 원격 데스크톱 daemon도 차단한다는 점을 발견해, 우리 대기 PID만 종료하고 원 기록·stop intent를 남겼다. 새 대기부는 변경하지 않은 기존 daemon(PID72937, proc start ticks60213, `/usr/libexec/gnome-remote-desktop-daemon`, 관측260MiB, 허용상한512MiB)만 예외로 인정하며 다른 compute process는 여전히 차단한다. 기존 desktop 서비스를 중단하거나 GPU를 비우기 위해 조작하지 않는다. `desktop_allowance.json`과 launcher/source snapshot을 보존한다.

복구는 config bytes를 그대로 두고 depth cache와 Adam moments 보관 위치만 CPU로 옮긴다. 원 CUDA loss/optimizer 계산 전에 해당 데이터를 복원한다. 독립 source, `amendment.json`, 작은 CPU/CUDA 동등성 검증을 봉인했다. P2/P3는 동일 runtime의 P1 CUDA fixture 증거를 명시적으로 재사용한다. 복사 비용은 기존 학습 시간과 구분한다.

첫 자원 복구 v1의 P1/P2는 CPU 전송 비용 때문에 오래 걸려, 상태 동일성 검사와 실제 상태 전송 측정(짝지은 cycle 중앙값2.2205배), 별도8-step CUDA runtime fixture를 통과한 후 pinned buffer v2로 교체했다. 학습 전체2.2배 주장은 아니다. 해당 v1 실행의 정확한 native child만 SIGTERM했고 driver는 `native_exit_code=-15` receipt를 남겼다. `replacement_adoption_plan.json`, `stop_intent.json`, `stop_signal_receipt.json`과 모든 로그를 보존했다. 이는 CUDA OOM과 별도인 `RESOURCE_TRANSFER_OPTIMIZATION` 의도 종료이며, 새 amendment의 `prior_resource_attempts`가 비용과 계보를 잇는다. P3 자원 복구 v1은 준비만 되었으며 실행하지 않았다.

v2는 실제 학습 source hash 전체와 CUDA proof를 봉인했다. 추가8k/15k full checkpoint는 진단·복구 근거 보존을 위한 I/O이며 손실·렌더 평가나 학습 스케줄을 변경하지 않는다. 기존 제어와30k/22k 비교는 그대로다. 기존32GiB RAM 제한을 유지하며 pinned cache 성장 시 예산을 검사한다. 전체 trajectory 동일성, 미래 checkpoint 직렬화 최대 메모리 및 학습 완료는 보장하지 않는다. 세 가지 작은 GPU probe가 기존 두 학습과 잠시 겹친 자원 편차와 timing 간섭 가능성도 기록했다.

CUDA fixture v1은 검증 스크립트 장치 index 오류로 실패했다. 원 snapshot과 후속 구조화 failure receipt를 보존했고 v2에서 `cuda:0`로 수정해 통과했다. Runtime 자체는 이 수정으로 바뀌지 않았다.

P1/P2 원 실행 대 복구 prefix 감사에서 초기 PLY·config·카메라·첫 손실과 제어는 일치했다. 이후 loss·densification 수치는 달랐다. 작은 optimizer 동등성 검증을 전체 trajectory의 bitwise 일치로 확대하지 않는다. 증거는 P1 복구 root의 `validation/prefix_audit_v1/attempt_v2/receipt.json`이다.

## 당시 후속 계획 — 아래 자동 실행 대기는 현재 종료됨

1. 활성 P2 마지막 자원 재시도(GPU0)를 보존하며 완료·실패를 확인한다. P1/P3 마지막 재시도는 실제 CUDA OOM으로 닫혔으므로 다시 실행하지 않는다. 기존 서비스 중단 금지. 과거 storage-v2 학습은 이미 모두 종료됐다.
2. Worker는 학습 PASS 뒤22k/30k 공식 렌더·512 추출, seal, geometry, renders, summary를 순서대로 실행한다. 공통 무거운 CPU 작업은 `no_anchor_sfm_v1/locks/heavy_cpu.lock`으로 직렬화한다. 실패를 기존 결과로 대체하지 않는다.
3. 새 평가는 공통 `evaluation/no_anchor_sfm_v1/`에 쓰되 모든 producer는 지역별 복구 root를 명시한다. 준비된 `evaluate.py`는 amendment와 원 실패까지 봉인한다.
4. `build_viewer.py`의 `--region-experiment`를 지역별로 지정하여 새 profile을 만든다. 기존 viewer manifest SHA를 검증하고 기존 viewer는 보존한다. 미완료는 이유를 붙여 pending/failed로 표시하고 F1=0으로 변환하지 않는다.
5. `compare_reference_support.py`, `figures.py`, `summarize_resources.py`로 같은 참조점의 근접도 유지·획득·상실, 고정 단면, 계산 비용을 비교한다. 이 근접도 상태는 유효/낡은 자산의 시간적 정답이 아니다.
6. Docker browser QA에서 실제 메시·RGB와 출처를 검증하고 사람이 비교 그림을 확인한다. 완전 행렬 기본, 부분 결과는 명시적인 `--allow-partial`과 PARTIAL 상태만 사용한다.
7. 실제 표·CSV/NPZ·뷰어·대표 그림을 근거로 분석을 작성하고 이 인계를 완료 상태에 맞춰 갱신한다. 실행 가능성 문제와 최종 품질 문제, 관찰과 인과 추론을 분리한다.

[조건부 동일8k 보조 진단](SFM_PREFIX8000_DIAGNOSTIC_ko_v1.md)은 정책이 지정한 역사적 storage-v2 시도들의 실제 실패로 활성화됐다. 계약은 task의 `contracts/sfm_prefix8000_diagnostic_v1.json` SHA`a312c4999ff590d757116dc0f4a90695020e3ac70130df24fdf6e02a0eb769f0`다. 모든 지역의 고정8k 상태만 별도로 검증·공식추출하고 전체 실패 상태를 보존한다. 실제 보조 평가를 시작했으며 마지막 자원 재시도와 병행한다. 이 진단은 원22k/30k 완료를 대체하지 않는다.

예정 최종 viewer 주소는 `http://127.0.0.1:8902/app/index.html?manifest=/task/evaluation/no_anchor_sfm_v1/profiles/viewer_v1/manifest.json&color=height`이다. 아직 최종 profile을 생성·표시 검증한 주소가 아니므로 결과 링크로 제공하지 않는다. 별도 불변 `profiles/no_anchor_preflight_v1/manifest.json`은 실제 새 메시/RGB0개 상태에서405개 browser 검사와12장 screenshot을 통과했다. 당시 P1/P2 pending·P3 v2 failed를 표시한 기술 검사이므로 새 성능 결과 화면이 아니다.

추가 정책 [마지막 자원 복구 범위](SFM_FINAL_RESOURCE_RETRY_ko_v1.md)를 품질 분석 전에 고정했다. task `contracts/sfm_final_resource_retry_v1.json` SHA`edf3f4312c622059a3506c6ca1c07d2b1c90e234fb672cc592ea3ea7e28f5a9a`에 따라 실패한 지역에 한해 한 번의 fresh SfM 재실행을 적용한다. 변경은 이전 gradient의 forward 전 해제와 동일 bytes의 chunk PLY 저장이다. CPU10/10과 실제 비어 있던 GPU1의 CUDA10/10 검사를 통과했다. CUDA proof는 `no_anchor_sfm_gradient_memory_v3_P1/validation/runtime_cuda_v1/receipt.json` SHA`d547d8ef0aa0e76c65e55f21783319e55a282604194a827ff7e8054324c942c1`이다.

P1은 `no_anchor_sfm_gradient_memory_v3_P1/amendment.json` 봉인 후 `detached_run_v1/`의 독립 supervisor로 GPU1에 진입했다. 첫 step PASS와1,000회 진행을 실제 확인했다. 과거 source/config·실패·비용을 보존하며 resource version3/storage version2를 구별한다. P2의 새 시도는 명시적 커널 cgroup OOM 증거 연결 후 준비하며 P3는 기존 실행을 계속한다. 기존 동일8k 정책과 trajectory는 그대로 보존한다. 이 마지막 재실행까지 실패하면 추가 학습을 반복하지 않는다.

기존 Wu–Vallet/GeoGS 결과·서비스·dirty 연구 문서·canonical E1–E6 계약은 보존한다. Git stage/commit은 하지 않았다.

## 최종 발행·비용·다음 세션 — 실제 종료 결과

`publish_review.sh main_final_partial_v1 partial`에 고정 마지막 P1/P2/P3 root를 명시해 실제 발행했다. 원 command/source snapshot/selection/log/exit0은 `evaluation/no_anchor_sfm_v1/publication/main_final_partial_v1/`에 있다. 세 지역 모두 실패이므로 새22k/30k raw/post12개는 `failed / NOT_ASSESSED_TRAIN_FAILURE / CUDA_OOM`이며 품질값은null이다. 원 baseline과 별도8k를 이 칸에 넣지 않았다.

발행 주소는 [실제 최종 실패 상태 화면](http://127.0.0.1:8902/app/index.html?manifest=/task/evaluation/no_anchor_sfm_v1/profiles/main_final_partial_v1/manifest.json&color=height)이다. manifest SHA`29801067388e913ccd1db995fd8db1f7c7ff9d15f8d310c820f5695ed84c522e`, availability SHA`b9eccf319ab6b1d997ab5f0b721021abe8707bc7e7c96c5facf09e4f9a4dbaa6`를 실제 파일에서 확인했다.

`browser_qa.sh main_final_partial_v1 main_final_partial_v1_actual_v1 8902 --allow-partial`은 `PARTIAL_NO_ANCHOR_BROWSER_QA`,867검사·12스크린샷·exit0이다. QA receipt는 `no_anchor_sfm_v1/validation/browser_qa/main_final_partial_v1_actual_v1/receipt.json` SHA`63f2fb4dcf46f671f5b2e7d29a35b5bede2f30dd8d6cdf16fcadd155e4a5c0a3`다. root도 실제 P2 실패 화면을 열어 기존 표면과 명시적인 새 결과 부재를 확인했다. 새 geometry/RGB가 생성됐다는 검사가 아니다.

새22k/30k의 reference support는144행 모두 미평가 수치null로 보존했다. `support_main_final_partial_v1/receipt.json` SHA`781ee5be7b281f6833ab9f2dd7567ea241db3e1b1a2d6c304fd7c3ad594f3d17`다. 성공한 새 주 표면이 없어 main 합성 그림을 만들지 않았다. 실제8k의 support NPZ·고정 단면·사진·그림은 기존 완료 경로에 있다.

비용은 `resources_main_final_partial_v1/new_phase_resources.csv`와 `new_failed_training_attempts.csv`를 원receipt 경로+SHA로 중복 제거해 `closed_costs_v1/`로 집계했다. 지역별4건씩12건 모두 학습이며 총41,934.821031389292602초(11.648561398시간)의 driver 작업량이다. 달력 경과시간·전 시스템 비용이 아니고 별도8k 추출·평가·준비·viewer 비용은 제외다. `closed_costs_v1/receipt.json` SHA`6fcb2cecdc7d50af7524cd8b7ee8a6535b224247b2ba01c589621f3cb96cadce`; 새 script는 `summarize_closed_costs.py`, config는 `sfm_closed_costs_v1.json`이다.

Docker의 독립 원receipt 합계 대조, 중복 주입의1회 집계, CSV시간 오염·producer SHA변경·거짓 main PASS 거부 등5검사도 PASS했다. 검증 receipt SHA는 `88202557c68ae42f9b1ce8e65d9d350b794d1c72eea53f4c14adc3a42f5e971d`다. 비용 집계는 아래 보조 host-memory flag를 입력으로 쓰거나 출력에 복사하지 않았다.

원 resource v1의 보조 `host_memory_failure_observed_in_log`는 문자열 부분 일치 때문에 CUDA 오류8행에서도 True였다. 해당 열만 수정한 `resource_flag_correction_v1/new_failed_training_attempts.corrected.csv`와 receipt SHA`ed31ed8b06d3f85f380b6199c601fda9494ed2bc2cd5412a2e3dbc4c325dd82f`를 함께 읽는다. 원 `termination_reason`·비용·viewer·품질 결과는 바뀌지 않았다. 원 v1 CSV/발행 snapshot은 보존했고 재사용 `summarize_resources.py`의 해당 감지만 수정했다. 정확한 원인·정정 범위는 [SFM-RESOURCE-FLAG-001](ISSUES_ko_v1.md#sfm-resource-flag-001--cuda-오류-문자열의-보조-host-memory-flag-오탐)에 기록했다.

다음 세션은 [통합 분석](SFM_NO_ANCHOR_RESULTS_ko_v1.md)과 [실제8k 비교](SFM_PREFIX8000_RESULTS_ko_v1.md)부터 읽는다. 활성 학습을 기다리거나 과거 queue status를 근거로 재개하지 않는다. 현재 실패만으로 Anchor의 필요성을 주장하지 않는다. 향후 재실험은 평가·저장 최대 메모리와 상태 보존 순서를 먼저 검토하고, 동일 초기화/동일 단계 비교의 범위를 새로 명시해야 한다. 이번 보존15k와 셔플된 부분 이미지는 현재 주 비교 결과가 아니다. `scientific_verdict: null`.
