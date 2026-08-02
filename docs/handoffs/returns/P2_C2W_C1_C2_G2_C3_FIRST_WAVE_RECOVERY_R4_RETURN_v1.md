# P2 C2W C1/C2 G2 + C3 first-wave recovery R4 Return v1

- handoff_id: `P2-W2C-C1-C2-G2-C3-FIRST-WAVE-RECOVERY-R4-v1`
- task_id: `P2-C1-C2-G2-C3-FIRST-WAVE-RECOVERY-R4-v1`
- writer: Experiment Host
- return direction: Experiment Host to Work Host
- return state: `TECHNICAL_BLOCKED`
- offered commit: `07f59e023aaea603788d4f5204777d3429dbcb17`
- source commit: `b519633b4cce76088fa4ea7530ecd85470c01ba4`
- accepted commit: `1eefefa3a199ae86411b8c4074ca6c93df37f871`
- scientific verdict: `null`

## Return summary

R4 completed the corrected C1/C2 evaluator, exact-937 offline semantic inference,
593,852-point initialization and one seed-0 whole-scene C3 training run through
30,000 updates. The exact final checkpoint contains 406,337 primitives, 812 Stage-2
groups and 319,698 grouped primitives. The required 5k/10k/20k/30k checkpoint
identities are in the technical manifest.

R4 cannot lawfully execute the requested same-development-51 C3 Stage-3 evaluation.
The only common Stage-3 interface has `SYNTHETIC_INTERFACE_SMOKE_ONLY` authority and
performance authority `NONE`; the canonical contracts still leave the final P2
adapter, G3/G4 thresholds and `PASS_usable` criterion unfrozen. No protected-source
surface extraction, building association, real Roofer config or qualitative protocol
exists. Creating one on the Experiment Host would change the protected source/config/
cohort/threshold contract. Completed outputs are preserved and the technical return
therefore closes `BLOCKED_PROTECTED_SOURCE`, not as 51 failed C3 outcomes.

## Returned records

- report:
  `docs/experiments/p2/c1_c2_g2_c3_first_wave_recovery_r4_v1/TECHNICAL_RETURN_REPORT_v1.md`
- compact manifest:
  `artifacts/manifests/p2/c1_c2_g2_c3_first_wave_recovery_r4_v1/technical_result_manifest_v1.json`
- external namespace:
  `artifact://JointBuildGS/phase-payloads/p2/c1_c2_g2_c3_first_wave_recovery_r4_v1/P2-C1-C2-G2-C3-FIRST-WAVE-RECOVERY-R4-v1/`
- C1/C2 result: `c1_c2/development_diagnostics_v1.jsonl`
- semantic manifest:
  `c3/prep/semantic_937_colmap_undistorted_r2/output/manifest.json`
- exact final checkpoint: `c3/train/seed0/ckpt/final.pt`
- training receipt: `c3/train/seed0/technical_receipt_v1.json`
- protected-source gate: `control/c3_development_evaluation_source_gate_v1.json`

## Accounting

- C1/C2 evaluator: one real run, 102 rows, exact development 51 per method
- R3 G2/seed reuse: six-unit receipt plus 222,044 points; no rerun
- semantic: 937/937 offline GPU inferences; native RGB/mask preserved
- C3: one optimizer run, 30,000/30,000 updates, exact final checkpoint sealed
- validation11, heldout10, C4, C5, Fusion W1, R_ext, external priors: unopened
- R4 val3dity, reconstruction, Roofer, MVS adapter: zero invocations
- C3 Stage-3 development evaluation: zero invocations, protected-source blocked
- scientific verdict: `null`

The Experiment Host will publish `200-blocked`, then its direct-child `300-closed`,
returning exclusive writer ownership to the Work Host.
