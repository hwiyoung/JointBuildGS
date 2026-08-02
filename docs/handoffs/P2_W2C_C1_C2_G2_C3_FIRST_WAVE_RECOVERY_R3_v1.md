# Work-to-Experiment Task Packet — first-wave execution recovery R3 v1

- handoff_id: `P2-W2C-C1-C2-G2-C3-FIRST-WAVE-RECOVERY-R3-v1`
- task_id: `P2-C1-C2-G2-C3-FIRST-WAVE-RECOVERY-R3-v1`
- status: `DRAFT_NOT_AUTHORIZED`
- parent_handoff_id: `P2-W2C-C1-C2-G2-C3-FIRST-WAVE-RECOVERY-R2-v1`
- source_commit: `SELF`
- scientific_verdict: `null`

## Purpose

Correct only the pinned val3dity 2.6.0 option tokenization isolated by R2, then
execute the already-frozen G2, current-MVS adapter, exact-undistorted semantic and
C3 stages. No cohort, image, pose, loss, schedule, threshold role or split changes.

## Required preflight before scientific reads

Run the exact configured command against a zero-scientific-payload synthetic
CityJSONSeq in the pinned `jointbuildgs-p0-tools:t0` image. It must emit the expected
header and feature verdict lines and parse successfully. If it does not, stop with
captured stdout/stderr and read zero real C2 units.

Publish one add-once preflight receipt containing the synthetic input bytes/SHA-256,
pinned image ID, exact command array, exit code, stdout/stderr identities and parser
result. Its invocation count is exactly one. On restart, verify and reuse that receipt
without invoking val3dity again. Both PASS and failure receipts are terminal evidence;
no real C2 read is allowed before a verified PASS receipt.

## Frozen execution

- 199 target buildings; independent quantitative set 72; development comparison 51
- exact current source 962 / 937 image-pose / 25 excluded
- C1/C2/C3 compare the identical development 51; validation 11 and held-out 10 stay closed
- C3 whole scene: 937 views, seed 0, 30,000 updates
- initialization: SfM 371,808 + current-image 1 m MVS 222,044 = 593,852
- semantic: exact 937 COLMAP-undistorted RGBs; image-derived depth and semantic losses enabled
- C4, C5, Fusion W1, `R_ext`, UAS/ALS/LoD1/LoD2 training inputs remain prohibited

Use a fresh R3 external namespace. Do not reread raw dense MVS, R1 15.7 GB input,
`Images.zip` or `OPF.zip`. Do not rerun C1/C2 reconstruction or Roofer. Record the
historical first-unit repeats caused by R1 exit handling and R2 CLI tokenization;
after the synthetic preflight passes, each R3 real unit is add-once.

## Required results

1. six-unit G2 receipt and C1/C2 development diagnostics;
2. 199→72 quantitative/qualitative explanation, explicitly distinguishing the 127
   unscored buildings from failed buildings;
3. exact 593,852-point C3 initialization audit;
4. exact-937 semantic ledger/masks and shape audit;
5. C3 5k/10k/20k/30k checkpoints and technical receipt;
6. Return, verified/blocked receipt and direct-child closure with
   `scientific_verdict: null`.
