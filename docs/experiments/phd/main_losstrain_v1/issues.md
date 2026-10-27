# Issues — PHD-MAIN-LOSSTRAIN-v1

LT-001 STOP: original 5 cm patch gate failed for five units. Superseded by the explicit user revision. Original evidence retained.

LT-002 STOP: revised 18 cm centre + 10 cm normal height gate failed for B0 LoD2, R1 LoD2, B173nb ALS. Evidence: tables/patch_join_v2.json. Training never started. Cause of coordinate/grid differences unconfirmed.

LT-003 INCOMPLETE: two r16 B0 GPU initialization probes were interrupted when LT-002 was confirmed. No r16/r17 GPU-equivalence PASS is claimed.

scientific_verdict: null

LT-004 RESOLVED: user 17:00 amendment replaces LT-001/002 linkage gates with direct stage-1 rules. Both new gates PASS.

LT-005 RESOLVED: zero-tangent centroid patches read the exact owning prior surface normals. No GT, nearest-surface imputation or initialization changes. Pixel normal availability PASS.

LT-006 RESOLVED: wing diagnostic first draft had duplicate Python keyword, corrected before data execution. First geometric probe used the fixed figure section outside named tile core; final 6.8 uses the named wing/tile intersection and preserves the preliminary receipt.

LT-007 RESOLVED: report-only CPU process was interrupted to preload NPZ arrays once instead of repeatedly decompressing them. An early relaunch hit the still-stopping container name; rerun after completion succeeded. No training or source data changed.

LT-008 RESOLVED: AXES71 a9 already contains all six nojudge tables. Three redundantly recomputed cases matched every field within 1e-7; their records are preserved under history/recomputed_axes. The B0 ALS duplicate CPU job was intentionally stopped; remaining baseline values are imported from a9. Stage-1 patch scoring remains a new required calculation.

LT-009 OPEN: fixed-gt and dynamic-gt stopped at 3001 because inherited opacity reset clamps free opacities to 0.01. A 100-step reset-specific opacity-check grace was proposed from 24 historical nojudge cycles, not applied. Awaiting user decision under work-order 1.10.

LT-009 RESOLVED BY USER AMENDMENT: actual periodic resets receive opacity-only offsets 1..99 grace; offset 100 resumes threshold and records same-iteration nojudge. Both stopped seed-0 arms restart with attempt_0 retained. No changes to loss, reset, protection, or density logic.

LT-010 RESOLVED: CPU mesh wrapper was edited while a shell waited for Docker and its trailing fragment failed. All 30 completed patch NPZ checksums verified separately; six baseline fate receipts PASS. No recomputation or result overwrite.

LT-011 RESOLVED: approval preparation verification used a nested patch_z path instead of flat filenames. Path corrected and config update made idempotent; no data changed.

LT-012 OPEN: dynamic-gt B173 ALS attempt_1 stopped at 9100, actual periodic reset+100, prior opacity median 0.00798154715448618 < 0.05. Same-iteration nojudge median 0.23826287686824799. No NaN/OOM exception; cause of recovery failure unconfirmed. New trainings blocked; in-flight fixed-gt continues.

LT-012 SUPERSEDED BY USER MONITOR V2: prior opacity is record-only; preserve attempt_1 and restart dynamic GT seed 0. Whole-population opacity after actual reset+100 and legacy-five-view PSNR at 7000/15000/30000 govern new stops. Nojudge is not retrained. Inflight fixed continues, missing birth/time records explicitly unavailable. CPU/GPU observer checks PASS; loss and density source unchanged.

LT-013 OPEN: dynamic GT attempt_2 failed at first loss evaluation, before any backward/optimizer step. New diagnostic lt_cameras list collided with the existing depth-loss camera dictionary. Fix separates lt_diagnostic_cameras; no loss formula or scoring change. All new training paused pending validation and user instruction under the explicitly retained error-stop rule. Fixed arm continues.

LT-014 RECORD-SCHEDULING REPAIR: B0 ALS historical-model photo readout launch was rejected by Docker (exit 125) because the preceding readout still owned the same container name. No project process or optimizer started. The rejection log/receipt are preserved; a per-GPU readout queue now waits before launching, and the rejected launch is retried only after exact no-output checks. This changes recording scheduling only, under the user instruction to resolve such choices without asking.

LT-013 RESOLVED AND RESTART AUTHORIZED: user explicitly approved the validated camera-name fix and fresh seed-0 attempt_3. Future verified recording-code repairs may restart autonomously with loss/scoring/variants/training settings unchanged; changes to those research rules or more than two stops of the same arm require user input. All prior stop records remain.

LT-015 HOST-OOM RECOVERY: fixed GT completed 30,000 iterations successfully, then TSDF postprocessing was killed (exit 137) by host global OOM at 20:18:55 KST. Docker oom/die events and kernel task cgroup identify this exact process. The model and partial post outputs are preserved. One identical-command post retry waits for at least 56 GiB MemAvailable (48 GiB unchanged container cap plus 8 GiB headroom). No training restart, loss/scoring/post parameters or arm changes. The old runner overwrote shared full_grace_STOP.json; the new post event is preserved separately and the exact old 9,100-stop bytes were restored from its run copy after matching the frozen approval hash. Any further same-arm failure is the third known stop and requires user input.

LT-015 SCHEDULING GUARD: future post entry points wait for both photo-readout locks and 56 GiB host available RAM before loading a model. This serializes only recording/post scheduling; the unchanged stage-1 post/run functions, TSDF parameters and model bytes remain the inputs. Docker event-ring expiry initially rejected the recovery preflight before computation; persistent kernel evidence for the exact container/process now supplies confirmation. No additional model/arm attempt started during that preflight.

LT-015 CPU QUEUE: mesh raycasts, sections, seeded-point fates and AXES CPU readouts now share the TSDF file lock. This prevents this task from allocating a 24 GiB CPU mesh container alongside a 48 GiB TSDF container. Shell wrappers were changed only after their prior invocations exited; arguments and computation are unchanged. Queue seconds are saved beside each CPU log.

LT-015 ADMISSION REVISION: after dynamic GT finished, host available RAM was about 54 GiB. With all large CPU readouts now sharing the TSDF lock, admission was revised from 56 to 52 GiB (unchanged 48 GiB cap plus 4 GiB headroom). The initial wait record is preserved. Only the waiting host helper was terminated and resumed; no training or post computation was interrupted. Fixed post attempt_1 was admitted at 53.644981384277344 GiB available. Both admission boundary checks passed in Docker.

LT-015 THIRD SAME-ARM STOP: fixed GT post attempt_1 also exited 137 at 20:53 KST. Kernel global_oom identifies the exact retry process (anonymous RSS 45,746,032 kB); this does not prove a CUDA OOM or the container limit being exceeded. Fixed training at 30k remains complete. Including the initial 3001 stop, the fixed arm has three known stops, so further retries require the user. Dynamic GT also completed 30k; both saved-model statistics and fates were read independently. No new training or TSDF is active.

LT-016 INTERIM THRESHOLDS: user requested B173 ALS 8.1 thresholds alongside the interim results. Added 21 metric/subset rows with prop_ALS_s0/s1, N, matching pooled spread availability, case spread, 300/N applicability and maximum. Independent recomputation from the two saved patch arrays matched every value exactly. No scoring rule changed.

## LT-017 사용자 승인: 자원 중단 분리와 전체 학습 대기열 재개

2026-10-26: 후처리 자원 부족은 학습 중단 횟수에서 제외한다. 이전 기록은 보존한다. TSDF는 호스트 MemAvailable 64 GiB 이상이 60초 유지된 뒤, 기존 48 GiB 컨테이너 한도로 실행한다. 동일 조건에서 최초 실패 뒤 최대 두 번 재시도하고 그 뒤에는 보고한다. 판 1·2의 완료 모델은 재학습하지 않는다. 판 3·4를 먼저 배정한 뒤 나머지 20회 학습을 두 GPU에 이어 배정하며 채점 완료를 기다리느라 학습을 막지 않는다. 후처리와 큰 CPU 채점은 직렬 실행한다. 앞 네 판 채점 완료 시 중간 보고를 갱신하고 심긴 점의 운명에서 칸 0과 칸 2를 따로 낸다. 손실 식·채점·판·학습 설정은 그대로다.

사진 확인 잔여 조사: 일치하는 프로세스·컨테이너·마운트·RAM 임시 캐시 없음. 결과 파일 삭제 0개. 관련 없는 서비스는 변경하지 않았다. 근거: provenance/photocheck_cleanup.json.

## LT-018 판 3 CUDA OOM 및 실행기의 재시도 누락

판 3 attempt_0은 14,717회 CUDA OOM. 새 대기열 실행기에 원 발주의 동일 설정 1회 재시도가 누락되어 배정이 멈췄다. 누락을 수정하고 제어 흐름과 동일 학습 인자를 검증했다. 원 시도·중단·GPU 메모리 기록을 보존하고 epoch 1에서 판 3 attempt_1 및 남은 20회 배정을 재개한다. 상세: 중단기록_GPU메모리_v1.md. 손실·채점·학습 설정 변경 없음.

## LT-019 B0 LoD2 고정·참값 판 PSNR 기준 중단

30,000회 같은 다섯 영상에서 nojudge보다 3.572403 dB 낮아 정해진 기준으로 중단. 판을 완료 처리하거나 삭제하지 않고 로그와 15,000회 모델을 보존한다. 다른 독립 판 18회와 완료 모델의 후처리는 기존 승인 범위에서 계속한다. 상세: 중단기록_B0_LoD2_PSNR_v1.md.

## LT-020 B173 주변 LoD2 고정 판 전체 불투명도 중단과 대기열 분류 오류

2026-10-27 03:20 KST, 3,100회(정기 초기화 +100회)에 전체 불투명도 중앙값 0.0494725853이 0.05 미만으로 내려가 기존 기준대로 중단했다. 이 판을 재실행하거나 완료 처리하지 않는다. 실행 관리 코드가 실제 `whole-population` 중단 문구를 `whole population`으로 검사해 나머지 독립 판까지 막았다. 진행 중이던 판이 끝난 03:34부터 09:38 현황 확인까지 대기열이 정지했다.

분류를 실제 두 건강 기준 문구와 정확히 일치하도록 수정했다. 원 중단·상태 파일은 `checks/resource_resume_v1/history/epoch_2/`에 보존하고 해당 판의 `training_health_STOP.json`에 실제 관측을 연결했다. 보고서 갱신기도 이전 실행의 정지 상태를 읽자마자 종료하던 조건을 제거했다. 실제 3,100회 기록, PSNR 중단, 알 수 없는 오류의 전체 중단 유지, 이전 정지 상태를 지난 보고서 갱신의 네 Docker 검사가 통과했다. 학습 인자·r17 소스·설정 동일성 검증 PASS. 기존 승인 범위로 독립 판 11회를 epoch 3에서 이어간다.

## LT-021 새 메모리 조건에서도 TSDF 컨테이너 한도 초과

B173 주변 ALS 고정 판의 post attempt_2는 01:02 KST에 exit 137로 종료했다. Docker OOM 이벤트와 커널 `CONSTRAINT_MEMCG`가 정확한 컨테이너를 가리킨다. 호스트 64 GiB 이상 60초 입장 조건은 통과했으며, 이번 원인은 48 GiB 컨테이너 한도다. 새 조건의 최초 실패로 기록하고, 사용자 승인대로 같은 조건에서 최대 두 번 재시도한다. 학습 중단 횟수는 늘리지 않으며 모델·부분 후처리·오류 기록을 보존한다.

## LT-022 동일 TSDF의 조각 계산으로 전환

사용자가 반복되는 메모리 문제의 해결을 요청했다. 기존 공간별 TSDF 구현을 승격하고 실제 RGB 보존을 추가했다. 현재 고정 판의 두 실제 영역(203개 훈련 영상)에서 삼각형 좌표·순서·색상과 기존 8.1 채점 배열이 정확히 같았다. 전체 장면의 복셀 저장량은 44.24 GiB, 여섯 조각 가운데 최댓값은 13.19 GiB로 산정됐다. 전체 프로세스 최대 메모리는 별도 실측한다. 손실·채점·학습 설정·판·64 GiB/60초/48 GiB 자원 조건 변경 없음.

post attempt_3은 계산을 시작하지 않은 입장 대기 상태에서 의도적으로 취소했다(빈 로그, `post_attempt_3_CANCELLED.json`). 기존 실행기가 만든 실행 오류 기록도 보존하되 재시도 횟수에서 제외한다. 현재 학습을 종료시키지 않고 완료 후 epoch 4로 전환한다. 과거 64 GiB 입장 기록의 시도 번호를 확인하지 않아 새 후처리 입장 전에 다음 학습이 시작되던 경쟁 조건도 수정했다. Docker 실행 관리 검사 5개 PASS. 상세: 메모리개선_v1.md.

## LT-023 중간 통계 스냅샷 생성의 Git 조회 오류 — 해결

2026-10-27: 저장 통계만 읽는 새 요약 스크립트의 첫 실행은 컨테이너에서 호스트 worktree의 Git 관리 경로를 찾지 못해 종료했다. 원 로그를 보존하고 호스트에서 확인한 커밋을 명시적 인자로 전달하도록 수정했다. Docker 재실행에서 저장 모델 5개, 새 판 PSNR 4개, 칸 0·2 운명 6행 및 완료 학습 11회의 분모·출처 검증이 통과했다. 학습이나 후처리는 재실행·중단하지 않았다. 종료 시간은 실제 학습 소요 시간과 별도로 명시한 후처리 20~40분/판의 계획 가정으로 제시하며 전체 장면 실측 전임을 표시한다.

## LT-024 완료된 앞 네 판의 채점이 신규 학습 배정에 밀릴 수 있음 — 우선순위 수정

2026-10-27: 사용자가 전체 학습을 기다리지 않고 완료 모델에서 판단 자료를 확보할 수 있는지 물었다. 첫 후처리 입장만 우선하는 정책은 이후 신규 학습이 RAM을 차지해 다음 후처리의 64 GiB 입장을 늦출 수 있었다. 완료된 B173 ALS 네 판의 후처리·채점과 날개 단면 보고 생성까지 신규 학습 배정만 보류하도록 수정했다. 진행 중 학습과 연구 설정은 그대로이며, 중간 보고 생성 기록으로 보류를 자동 해제한다. Docker 검사 8개 PASS. 기존 실패 기록과 중단 판을 보존한다. 상세: 중간채점_우선순위_v1.md.

## LT-025 마지막 판의 메모리 입장 대기로 중간 보고 예상 시간 초과

2026-10-27 13:16 KST 확인: 앞 세 판은 후처리·채점 완료, 판 4는 post attempt_0 실행 중이다. 이 시도의 입장 기록은 대기 3704.9169초(약 61.7분), 입장 당시 MemAvailable 64.4565 GiB, 60.2052초 안정 조건 통과다. 이는 실행 중 OOM이나 학습 중단이 아니다. 12:30~13:00 예상보다 늦었음을 보고하며 메모리 조건은 변경하지 않았다. 실제 삼각형 생성 작업이 시작됐고, 이후 추가 후처리·채점·단면 생성·그림 검수가 남아 있다. 단면 미생성 안내가 완료된 세 판의 메시와 채점까지 없다고 표현하던 문장을 현재 완료 수와 그림 생성 대기로 바로잡았다.

## LT-026 중간 지표가 독립적인 추가 후처리까지 기다리는 실행 의존성 — 분리

2026-10-27 13:33 KST: 판 4의 실제 시점 메시 추출은 13:24에 완료됐으나 가상 시점·부유점용 run 단계는 호스트 MemAvailable 약 62.7 GiB로 입장 대기 중이었다. 8.1·8.2·8.5와 날개 단면에는 run 단계 출력이 필요하지 않으므로, 기존 Docker CPU 스크립트를 그대로 호출하는 requested_interim_readout.py로 먼저 계산한다. 24 GiB CPU 한도와 TSDF 공유 잠금은 유지한다. 계산 결과는 나중의 measure_run이 재사용하며, 미완료 추가 지표를 measure_PASS로 표시하지 않는다. 보고서도 핵심 패치 채점 완료와 전체 채점 완료를 분리한다. 손실·채점 규칙·판·학습·메모리 입장 조건 변경 없음.

13:42 KST: 네 판의 8.1·8.2, 21행 문턱, 칸 0·2 운명, 날개 단면 생성과 화면 검수를 완료했다. Docker 검증은 단면과 채점의 메시 SHA-256 일치까지 PASS다. 요청한 중간 보고의 준비 완료 기록으로 신규 학습의 임시 배정 보류를 해제한다. 판 4의 가상 시점·부유점·8.3 전체 채점은 별도 대기 상태로 보존하며, 전체 24회 완료로 표시하지 않는다.

## LT-027 중간 전달 포장 중 컨테이너 Git 경로 조회 — 수정

2026-10-27: 중간 ZIP 포장 첫 실행은 호스트 worktree 관리 경로가 컨테이너에 없어 커밋 조회에서 종료했다. ZIP 생성 전이었고 학습·채점에는 영향이 없다. 호스트에서 확인한 커밋을 명시적 인자로 전달하도록 수정했다. 원 실행 로그와 첫 시도의 빈 전달 디렉터리는 보존하고 새 revision으로 포장한다. 이번 변경은 진행 중 상태·24판 목록·한 번 고정한 공통 파일을 두 ZIP에 넣는 전달 절차에 한정한다. 과학 설정 변경 없음. 재실행의 CRC·파일별 SHA-256·공통 파일 동일성 결과는 해당 delivery receipt에 기록한다.

## LT-028 R1 LoD2 고정·참값 판의 기존 전체 불투명도 기준 중단

2026-10-27 14:37:27 KST: R1 LoD2 판 1은 3,100회, 정기 초기화 +100회에서 전체 가우시안 844,047개의 불투명도 중앙값 0.040125567466020584로 기존 0.05 기준에 걸렸다. 사전 출신만의 기준이 아니라 전체 집단의 기준이다. `runs/R1rep_b10/lt_fixgt_LoD2_s0/training_health_STOP.json`과 원 관측·시도 모델을 보존하고 정상 완료에서 제외한다. 손실·채점·판·학습 설정을 바꾸거나 이 판을 재시작하지 않았으며 독립 판은 기존 승인 범위에서 계속한다. 상세: 중단기록_R1_LoD2_전체불투명도_v1.md.
