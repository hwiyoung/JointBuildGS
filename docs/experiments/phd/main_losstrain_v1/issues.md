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
