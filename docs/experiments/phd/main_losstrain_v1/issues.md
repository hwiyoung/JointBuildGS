# Issues — PHD-MAIN-LOSSTRAIN-v1

LT-001 STOP: original 5 cm patch gate failed for five units. Superseded by the explicit user revision. Original evidence retained.

LT-002 STOP: revised 18 cm centre + 10 cm normal height gate failed for B0 LoD2, R1 LoD2, B173nb ALS. Evidence: tables/patch_join_v2.json. Training never started. Cause of coordinate/grid differences unconfirmed.

LT-003 INCOMPLETE: two r16 B0 GPU initialization probes were interrupted when LT-002 was confirmed. No r16/r17 GPU-equivalence PASS is claimed.

scientific_verdict: null

LT-004 RESOLVED: user 17:00 amendment replaces LT-001/002 linkage gates with direct stage-1 rules. Both new gates PASS.

LT-005 RESOLVED: zero-tangent centroid patches read the exact owning prior surface normals. No GT, nearest-surface imputation or initialization changes. Pixel normal availability PASS.

LT-006 RESOLVED: wing diagnostic first draft had duplicate Python keyword, corrected before data execution. First geometric probe used the fixed figure section outside named tile core; final 6.8 uses the named wing/tile intersection and preserves the preliminary receipt.

LT-007 RESOLVED: report-only CPU process was interrupted to preload NPZ arrays once instead of repeatedly decompressing them. An early relaunch hit the still-stopping container name; rerun after completion succeeded. No training or source data changed.
