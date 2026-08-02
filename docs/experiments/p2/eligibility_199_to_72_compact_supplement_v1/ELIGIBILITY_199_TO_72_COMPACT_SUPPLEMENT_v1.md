# Eligibility 199 to 72 compact supplement v1

## Answer first

The frozen target roster contains exactly **199** unique buildings. Exactly **72**
(36.18%) are quantitative-eligible and **127** (63.82%) are excluded. The eligible
roster is exactly **51 development + 11 validation + 10 held-out = 72**.

This supplement only aggregates already-promoted, Git-bound evidence. It does not
recompute eligibility, open outcome payloads, or read/hash raw UAS, `Images.zip`, or
`OPF.zip`. It also does not change any C1/C2 result or authorize C3-C5 execution.

- scientific_verdict: `null`
- source candidate ledger: `docs/research/preregistration/gate_s0/uas_reference_coverage_r1_v1/candidate_ledger_v1.csv`
- candidate-ledger Git blob: `6e5d6ab0698c0fdf3e67e74cbdd060bf785ea06b`
- source split roster: `docs/research/preregistration/gate_s0/uas_reference_coverage_r1_v1/split_candidate_v1.csv`
- split-roster Git blob: `f6db7b8accdbd7b57b4a221c441acfc5589fb592`
- machine-readable summary: `eligibility_199_to_72_compact_summary_v1.csv`

## One-view reconciliation

| Population | Count | Share of 199 | Share of eligible |
|---|---:|---:|---:|
| `U_target` | 199 | 100.00% | - |
| quantitative-eligible | 72 | 36.18% | 100.00% |
| excluded | 127 | 63.82% | - |
| development | 51 | 25.63% | 70.83% |
| validation | 11 | 5.53% | 15.28% |
| held-out | 10 | 5.03% | 13.89% |

The two identities are exact: `72 + 127 = 199` and `51 + 11 + 10 = 72`.
All 199 `stable_id` values and all 72 split IDs are unique; the split-ID set equals
the quantitative-eligible ID set.

The older explainer's wording “20-cell or larger smooth roof patch” is not a
per-building eligibility threshold. `20` is the minimum size of a segmented patch in
the global reference grid; a building bbox may intersect only part of that patch.
The frozen building-level threshold is at least `4` reference score cells, and the
observed minimum among the 72 eligible buildings is `5`. Therefore this supplement
uses the sealed 72-ID roster and does not repeat the misleading per-building
“at least 20 cells” description.

## Building-primary exclusion reason

`candidate_exclusion_reason` is already one building-level, mutually exclusive field.
This supplement keeps each stored semicolon-delimited combination intact and treats it
as that building's primary exclusion label; it does not invent a new priority order.

| Stored reason combination | Buildings | Share of 199 | Share of 127 excluded |
|---|---:|---:|---:|
| independent UAS reference only | 78 | 39.20% | 61.42% |
| independent UAS reference + MVS | 38 | 19.10% | 29.92% |
| independent UAS reference + MVS + C4 | 9 | 4.52% | 7.09% |
| independent UAS reference + C4 | 2 | 1.01% | 1.57% |
| **subtotal** | **127** | **63.82%** | **100.00%** |

Thus the common first bottleneck across all 127 excluded buildings is insufficient
independent UAS evaluation support. Of those 127, 38 also lack MVS support, 2 also lack
C4 support, and 9 lack both MVS and C4 support. These are eligibility facts, not
performance outcomes.

## Seven fixed cases: reuse only

The exact three passing and four failing cases below are inherited without reselection.
No new cell extraction or image generation was performed.

| Label | Stable ID | Status | Views / MVS / C4 / reference cells | Stored reason |
|---|---|---|---:|---|
| P1 | `DEBY_LOD2_4959324` | ELIGIBLE | 228 / 97 / 87 / 5 | `PASS_ALL_INPUT_SUPPORT_RULES` |
| P2 | `DEBY_LOD2_4959793` | ELIGIBLE | 241 / 282 / 193 / 97 | `PASS_ALL_INPUT_SUPPORT_RULES` |
| P3 | `DEBY_LOD2_4959460` | ELIGIBLE | 399 / 8842 / 6740 / 3543 | `PASS_ALL_INPUT_SUPPORT_RULES` |
| F1 | `DEBY_LOD2_4907184` | EXCLUDED | 186 / 521 / 451 / 3 | `INSUFFICIENT_INDEPENDENT_UAS_REFERENCE_SUPPORT` |
| F2 | `DEBY_LOD2_4907034` | EXCLUDED | 61 / 0 / 574 / 0 | `INSUFFICIENT_INDEPENDENT_UAS_REFERENCE_SUPPORT;INSUFFICIENT_MVS_SUPPORT` |
| F3 | `DEBY_LOD2_4908166` | EXCLUDED | 85 / 40 / 3 / 0 | `INSUFFICIENT_INDEPENDENT_UAS_REFERENCE_SUPPORT;INSUFFICIENT_C4_SUPPORT` |
| F4 | `DEBY_LOD2_4908164` | EXCLUDED | 63 / 0 / 0 / 0 | `INSUFFICIENT_INDEPENDENT_UAS_REFERENCE_SUPPORT;INSUFFICIENT_MVS_SUPPORT;INSUFFICIENT_C4_SUPPORT` |

Existing corrected figure (reused URI):
`artifact://JointBuildGS/phase-payloads/p2-baselines/c1_c2_qualitative_layout_correction_r5_v1/P2-C1-C2-QUALITATIVE-LAYOUT-CORRECTION-R5-v1/eligibility_199_to_72_fixed_cells_layout_corrected_v1.png`

- bytes: `245765`
- SHA-256: `1a1540f380f7fbc1a950e806b879c01ad744cc8cf7e5bcef42cb761923938022`
- fixed-case table: `docs/research/preregistration/gate_s0/uas_eligibility_explainer_v1/uas_eligibility_examples_v1.csv`
- preserved technical binding: `artifacts/manifests/p2_baselines/c1_c2_qualitative_layout_correction_r5_v1/technical_result_manifest_v1.json`

## No-repeat accounting

| Operation | New count |
|---|---:|
| eligibility computations / building reselections | 0 / 0 |
| raw UAS / `Images.zip` / `OPF.zip` reads or hashes | 0 |
| external figure reads or hashes | 0 |
| validation / held-out outcome payload accesses | 0 / 0 |
| C1-C5, MVS, LiDAR, Roofer, reconstruction, or GS runs | 0 |

The only new work is compact arithmetic and consistency validation over the sealed
Git-owned CSV rows. This document is descriptive evidence; `scientific_verdict`
remains `null` for separate human judgment.
