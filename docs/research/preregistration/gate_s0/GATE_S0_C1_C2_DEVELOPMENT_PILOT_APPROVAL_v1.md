# Gate S0 human decision — C1/C2 development feasibility pilot v1

- decision: `APPROVE_DEVELOPMENT_FEASIBILITY_PILOT_ONLY`
- decision_id: `DEC-P1-013`
- decided_at: `2026-08-02`
- human_reviewer: `김휘영`
- authorized_conditions: `C1_L_upper`, `C2_MVS`
- authorized_split: `development`
- authorized_buildings: `51`
- authorized_groups: `5`
- validation_access: `PROHIBITED`
- held_out_access: `PROHIBITED`
- C3_C4_C5_execution: `PROHIBITED`
- confirmatory_or_population_claim: `PROHIBITED`
- scientific_verdict: `null`

## Decision

The human reviewer authorizes one bounded P2 feasibility pilot on the already-frozen
development split. It may run C1 and C2 only after an exact implementation/config/test
commit, independent review, activated Work-to-Experiment packet and validated
two-host ownership transfer.

The authorized order is:

1. pass a zero-scientific-payload synthetic Roofer smoke with the exact pinned image
   and a new writable task namespace;
2. run C1 and C2 on the exact 51 development buildings only;
3. report quantitative and qualitative development evidence;
4. return writer ownership to the Work Host;
5. use the development evidence to draft, review and separately authorize the first
   C3 training strategy;
6. preserve validation and held-out buildings for later protocol-matched checks.

This is the intended roadmap order: direct C1/C2 baselines establish the common
Stage-3 and image-derived gap before no-external-prior C3 training is designed.

## Interpretation limits

- C1 is `SELF_REFERENCE_UPPER_BASELINE`. It is reported in its own panel and is not
  an independently evaluated accuracy result.
- C2 uses the exact common-base MVS derivative and independent UAS reference for
  score-only evaluation. Reference geometry may not enter reconstruction,
  registration, cropping or roofprint derivation.
- The development group sizes are 47, 1, 1, 1 and 1. Building-level counts and
  residuals must be accompanied by per-group and group-balanced summaries. The 51
  buildings are not treated as 51 independent repetitions.
- G0--G2 may be reported only as provisional technical outcomes under an exact
  precommitted schema. G3, G4 and `PASS_usable` remain null until the later P2
  criterion freeze. LoD1.1 fallback is not counted as LoD2.2 success.
- No p-value, confidence interval, confirmatory conclusion or population/generalized
  claim is authorized from this pilot.
- The LoD2-derived LoD1 remains diagnostic/self-conditioned under `DEC-P1-011` and is
  not an input to this C1/C2 task.

## Exact authorization boundary

The approved scientific unit set is the 51 rows whose `split` is `development` in:

`docs/research/preregistration/gate_s0/uas_reference_coverage_r1_v1/split_candidate_v1.csv`

The implementation must bind its exact Git blob/digest and emit an exact roster
digest before any scientific payload is opened. Validation and held-out output roots
must not be mounted. Membership metadata may be checked only to prove exclusion.

The task packet is:

`docs/handoffs/P2_W2C_C1_C2_FEASIBILITY_PILOT_v1.md`

The DRAFT commit is:

`791b8b032607e7c4899ef7cc627b1003d0a1981b`

An activation revision must name the final reviewed implementation/source commit and
must not broaden the scope above.

## Gate state

```text
gate_decision: APPROVE_DEVELOPMENT_FEASIBILITY_PILOT_ONLY
P2_C1_C2_development: AUTHORIZED_AFTER_ACTIVATED_HANDOFF
P2_validation: PROHIBITED
P4_held_out: PROHIBITED
C3_C4_C5_execution: PROHIBITED
confirmatory_gate: BLOCKED_REFERENCE_COVERAGE_OR_INDEPENDENCE
scientific_verdict: null
```

This human Gate decision is distinct from technical two-host receipts. Every
technical receipt and Return keeps `scientific_verdict: null`.
