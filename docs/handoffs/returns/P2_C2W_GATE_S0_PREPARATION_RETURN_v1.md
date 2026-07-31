# Codex-to-Work Return Packet — P2 Gate S0 Preparation v1

## Handoff metadata

- handoff_id: `P2-W2C-GATE-S0-PREP-v1`
- phase: `P2 / pre-result Gate S0 preparation`
- direction: `Codex→Work`
- status: `BLOCKED_FOR_GATE_S0_REVIEW`
- source_commit: `0716c925b43aa401ced47f2311ca28663b290a44`
- approval_commit: `916630cac1225e612405167fcf53686288237d9a`
- offered_commit: `04081d046cf544057c48a8387a6fceb09aadf462`
- accepted_commit: `9197de13725e6caef8b71887096eeeaf8c3f1da8`
- input_commit: `9197de13725e6caef8b71887096eeeaf8c3f1da8`
- output_commit: `SELF` — resolve to the introducing commit with
  `git log -1 --format=%H -- docs/handoffs/returns/P2_C2W_GATE_S0_PREPARATION_RETURN_v1.md`
- run_ids: `P2-GATE-S0-EVIDENCE-20260731`
- completed_at: `2026-07-31T20:12:21+09:00`
- repository_effective_phase: `C1–C5 PROGRAM / P2 ENTRY GATE S0 PREPARATION`
- scientific_verdict: null

## Executive summary

Gate S0 evidence preparation is technically complete and proposes
`BLOCKED_FOR_GATE_S0_REVIEW`. Eleven exact input/reference files totaling
15,743,666,051 bytes were rehashed from the canonical artifact root. All 962
image members were individually hashed. A deterministic ledger resolves the
962/937 discrepancy into 937 included images and 25 explicit
`NO_CALIBRATED_CAMERA_POSE_IN_OPF` exclusions.

Gate S0 is not freeze-ready. Independent LoD1 is `MISSING`; C1/C2/C4 remain
partial; `U_target`, `E_paired`, split membership and defensible cost ceilings
are unknown; common `R_derived`, gravity and writer/toolchain readiness are
incomplete. No substitute LoD1 or result-based population was created.

## Completed tasks

- Verified the complete activation tuple, remote ancestry, approved packet,
  scope and offered receipt before fast-forward.
- Created and remotely validated the immutable accepted event.
- Rehashed 11 exact target files and 962 individual image members.
- Published the deterministic 962-row image/camera ledger.
- Proposed C1 nadir-only from provisional numeric bbox screening in unregistered
  UTM32 frames and retained exact-coverage/class/datum/registration gaps.
- Documented C2 same-base limitations and C4 identity/interface/independence gaps.
- Kept C5 `MISSING`; did not derive LoD1 from LoD2.
- Published outcome-free AOI, funnel, cost and split proposals without assigning
  any building to held-out.
- Audited CityJSON/CityGML/Roofer/validator and G0–G4 writer readiness.

## Required output index

| Output | Path | Status |
|---|---|---|
| Evidence report | `docs/research/preregistration/gate_s0/GATE_S0_EVIDENCE_REPORT_v1.md` | complete |
| Exact input manifest | `docs/research/preregistration/gate_s0/gate_s0_input_manifest_v1.json` | complete; 11 live records |
| Image/camera ledger | `docs/research/preregistration/gate_s0/gate_s0_image_camera_ledger_v1.csv` | complete; 962/937/25 |
| Condition readiness | `docs/research/preregistration/gate_s0/gate_s0_condition_readiness_v1.csv` | complete; field-level status |
| Eligibility funnel | `docs/research/preregistration/gate_s0/gate_s0_eligibility_funnel_v1.csv` | complete; blocked aggregate funnel, no invented IDs |
| Cost evidence | `docs/research/preregistration/gate_s0/gate_s0_cost_bounds_v1.csv` | complete; known input bytes, unknown execution ceilings |
| Split proposal | `docs/research/preregistration/gate_s0/gate_s0_split_proposal_v1.json` | proposal only; not freezeable |
| Issue log | `docs/research/preregistration/gate_s0/issues.md` | complete |
| Return Packet | `docs/handoffs/returns/P2_C2W_GATE_S0_PREPARATION_RETURN_v1.md` | this file |

The machine hash index is
`artifacts/manifests/gate_s0/gate_s0_output_manifest_v1.json`.

## Verification evidence

- Activation tuple/packet/receipt: independent agent review `PASS`
- Offered validator at exact remote commit: `PASS`
- Accepted validator before and after push: `PASS`
- Agent instruction contract: `PASS`
- Repository contract suites: 70/70 `PASS`
- Exact artifact full rehash: 11/11 `PASS`
- Image members: 962/962 individual SHA-256 inventory
- Image/camera ledger: 962 rows, 937 included, 25 excluded; SHA-256
  `8c1e89040869e800c34ebd8a06c2b5185524330fc5d56e594b41686173c465b0`
- Artifact verification level: `artifact_verified`
- Output validator/tests: recorded in the immutable 200 event after the output
  commit is pushed

## Findings

1. C1 nadir-only is an outcome-free provisional bbox-screening proposal, not an
   exact coverage claim; C1 remains blocked by class-2/6, vertical datum,
   transform, residual and per-building coverage.
2. The 937 OPF calibrated IDs are the proposed C2–C5 base. Existing C2 MVS lacks
   exact derivation binding and therefore remains a sensor-processing bundle.
3. Existing ALS is distinct from Current UAS LiDAR by file, year and survey
   regime, but formal independence/registration/overlap remains incomplete.
4. Independent LoD1 is `MISSING`; scored LoD2 was not used as a substitute.
5. The 199 reference intersections are not `U_target` or `E_paired`; no split IDs
   were assigned and held-out remained unopened.
6. Exact input bytes are known, but runtime/memory/output/retention ceilings are
   not defensibly bounded.
7. CityJSON is partial; integrated Roofer, CityGML/cjval, val3dity and G0–G4
   writer readiness is incomplete.

## Changes made

Only the technical accepted receipt and paths allowed by the offered scope were
added. The evidence commit contains Gate S0 manifests, config, generator,
validator/tests, report tables and this Return Packet. No source pipeline,
research canon, protected packet/index, raw input, canonical result, held-out,
Fusion W1 or external `R_ext` path was changed.

## Deviations

The offered receipt's third recorded verification command is descriptive prose
rather than runnable Python. The immutable offered validator still passed. The
accepted receipt records this limitation, does not rely on that command, and
the Experiment Host independently reran an executable tuple check plus the 70
repository contract tests. No other deviation occurred.

## Frozen-decision compliance

- C1–C5 conditions unchanged
- Current UAS LiDAR and Existing ALS kept separate
- C2–C5 common image/camera proposal documented without overstating provenance
- C4/C5 treated as separate rescue-set/failure-mode arms; no synergy claim
- LoD2 kept score-only; no LoD1 synthesis
- `R_derived` retained as primary; external `R_ext` not accessed
- P2/P3 same future development+validation pool; P4 first opens held-out
- No performance run, GS training, prior loss, final adapter or threshold
- `scientific_verdict: null`

## Unresolved blockers

See `docs/research/preregistration/gate_s0/issues.md`. `S0-I01` through
`S0-I11` block Gate S0 freeze or P2 entry. `S0-I12` is a transparent handoff
provenance limitation corrected by independent executable verification.

## Proposed status

`BLOCKED_FOR_GATE_S0_REVIEW`

This is an evidence-package proposal, not a human Gate S0, phase or scientific
decision.

## Recommended next action

After the closed receipt returns writer order, Work Host should fast-forward to
the exact closed commit, cross-review the artifact and output hash indexes, and
prepare a new authorized remediation packet. It should obtain independent LoD1
and provenance/coordinate/coverage evidence, then authorize bounded non-held-out
calibration. It should not begin C1–C5 performance execution from this package.
