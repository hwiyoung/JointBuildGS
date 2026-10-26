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
