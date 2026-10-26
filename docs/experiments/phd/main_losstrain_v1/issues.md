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
