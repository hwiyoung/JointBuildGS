# Codex-to-Work Return — C1/C2 G2 + C3 first-wave recovery R1 v1

- handoff_id: `P2-W2C-C1-C2-G2-C3-FIRST-WAVE-RECOVERY-R1-v1`
- task_id: `P2-C1-C2-G2-C3-FIRST-WAVE-RECOVERY-R1-v1`
- source commit: `8a394899db70494d3f780a7322cff255c1445c68`
- activation commit: `21c8d98a8f7890bb4b3c778a71798d4dc14d9f17`
- offered commit: `195d0b26a4d0ea53e89d9c3945fa7eddc1f6b9f3`
- accepted commit: `5050a212f6465ac759cf9a06d802ec9bb084c085`
- Return / 200-blocked commit: `SELF`
- proposed technical status: `BLOCKED_FOR_BOUNDED_SOURCE_RECOVERY_R2`
- scientific_verdict: `null`

## Answer first

The portability fix passed and real processing began, but three bounded defects stop
C1/C2 closure and C3 training: val3dity exit handling discarded a parseable first-unit
result; every 0.10/0.20/0.40 m dense candidate exceeded the cap without a retained
failure receipt; and original-resolution semantic masks do not align to the
COLMAP-undistorted C3 RGB/depth grid.

No training, validation, held-out, C4, C5, Fusion W1 or `R_ext` work ran. Writer
ownership returns to Work Host for one source-only R2 correction. The exact technical
accounting and recovery contract are in
`docs/experiments/p2/c1_c2_g2_c3_first_wave_recovery_r1_v1/TECHNICAL_INCIDENT_REPORT_v1.md`.

## Preserved reusable outputs

- exact-937 semantic member manifest: 169,696 bytes, SHA-256
  `a1af290af59811632435ccec55e253d99b51ab9931056b93839cd3b18816e528`
- complete receipted GroundedSAM/BERT asset bundle; inference-network access remains off
- 255 original-resolution semantic completion directories, explicitly quarantined and
  ineligible for C3 input
- existing closed 1 m MVS derivative attestation for the R2 initialization adapter

## Non-repeat contract for R2

- do not reopen raw `dim_dense.ply`; adapt the attested 222,044-point 1 m derivative
- do not resume or resize the 255 raw-image semantic masks; use exact undistorted RGB
- rerun only the first G2 unit whose stdout was discarded; the other five are first reads
- persist G2 per-unit and dense terminal-failure telemetry add-once
- keep the development 51, 937 views, seed/loss/schedule, validation/held-out barriers,
  and all scientific roles unchanged

The new R2 packet must first be a DRAFT and must not modify this Return or any earlier
packet/receipt. `scientific_verdict` remains `null`.
