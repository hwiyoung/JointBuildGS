# Work-to-Experiment Task Packet — first-wave execution recovery R4 v1

- handoff_id: `P2-W2C-C1-C2-G2-C3-FIRST-WAVE-RECOVERY-R4-v1`
- task_id: `P2-C1-C2-G2-C3-FIRST-WAVE-RECOVERY-R4-v1`
- status: `DRAFT_NOT_AUTHORIZED`
- parent_handoff_id: `P2-W2C-C1-C2-G2-C3-FIRST-WAVE-RECOVERY-R3-v1`
- source_commit: `SELF`
- scientific_verdict: `null`

## Purpose

Apply only the two source corrections isolated by the real R3 execution, then finish
the already-frozen C1/C2 development diagnostics, exact-937 image semantic masks and
C3 seed-0 whole-scene run. Do not change the cohort, split, images, poses, losses,
schedule, thresholds or evaluation roles.

## Reuse before execution

Reuse the closed R3 six-unit G2 receipt and 222,044-point MVS adapter output exactly.
Do not invoke val3dity, C1/C2 reconstruction, Roofer or the MVS adapter again. Reuse
the exact R3 937-member semantic manifest by its recorded SHA-256 when practical;
regenerating it from the Git crosswalk is allowed only if no RGB, depth or COLMAP
payload is opened. Never rehash the R1 15.7 GB input, `Images.zip` or `OPF.zip`.

Use a fresh R4 external namespace:
`artifact://JointBuildGS/phase-payloads/p2/c1_c2_g2_c3_first_wave_recovery_r4_v1/P2-C1-C2-G2-C3-FIRST-WAVE-RECOVERY-R4-v1/`.
R1, R2 and R3 namespaces are read-only. Record the unavoidable R4 reread of the first
RGB/depth pair that R3 inspected before its pre-inference failure; do not treat it as
a completed semantic inference.

The container keeps the frozen logical path
`/artifacts/JointBuildGS/phase-payloads/p2/c3_first_wave_v2`. Bind its `c3` payload
to the fresh R4 host namespace read-write. Overlay only the closed R3
`membership.json` and `selected_dense_seed.ply` at their configured logical paths as
read-only files. The semantic `work`/`output` and training `train/seed0` directories
therefore resolve to fresh R4 storage, while the C3 `semantic_dir` resolves to the R4
output masks. Do not bind the R3 `work`, semantic `output` or training directory.

## Frozen execution

- 199 target buildings; independent quantitative set 72; development comparison 51
- exact current source 962 / 937 image-pose / 25 excluded
- C1/C2/C3 compare the identical development 51; validation 11 and held-out 10 stay closed
- C3 whole scene: exact 937 views, seed 0, 30,000 updates
- initialization: SfM 371,808 + current-image 1 m MVS 222,044 = 593,852
- loss weights: photo 1.0, depth 0.03, semantic 0.1, intrinsic normal consistency
  0.05, distortion 100.0; external normal and external prior losses remain zero
- native COLMAP depth is read at its stored resolution and aligned by the existing
  dataloader with `cv2.INTER_LINEAR`; RGB and semantic masks remain 1400×1013
- C4, C5, Fusion W1, `R_ext`, UAS/ALS/LoD1/LoD2 training inputs remain prohibited

## Required execution and outputs

1. Run zero-scientific-payload regression preflights for the leading empty
   CityJSONSeq header and native-depth/RGB mismatch contract.
2. Run the C1/C2 evaluator once using the closed R3 G2 receipt; publish 51-building
   same-cohort diagnostics and the 199→72 quantitative/qualitative explanation.
3. Generate all 937 native-RGB semantic masks and a receipt that records native depth
   dimensions plus deterministic training alignment. Do not resize semantic masks.
4. Start C3 only after the exact 937 semantic inventory and 593,852-point
   initialization pass. Publish 5k/10k/20k/30k checkpoints and the technical receipt.
5. Evaluate C3 on the same development 51 and publish stage counts, final outcome
   counts and representative qualitative examples. The 127 outside the independent
   reference set are unscored, not failed.
6. Return writer ownership through a verified/blocked receipt and direct-child
   closure. Keep `scientific_verdict: null`.
