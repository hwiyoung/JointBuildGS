# Work-to-Experiment Task Packet — C1/C2 G2 + C3 first-wave recovery R2 v1

- handoff_id: `P2-W2C-C1-C2-G2-C3-FIRST-WAVE-RECOVERY-R2-v1`
- task_id: `P2-C1-C2-G2-C3-FIRST-WAVE-RECOVERY-R2-v1`
- status: `APPROVED_FOR_EXECUTION`
- user_approval: `GRANTED_IN_WORK_HOST_SESSION_2026-08-02`
- parent_handoff_id: `P2-W2C-C1-C2-G2-C3-FIRST-WAVE-RECOVERY-R1-v1`
- source_commit: `38cb686a633ca568410302f88a0f5c92e593b946`
- scientific_verdict: `null`

## Purpose

Apply only the three bounded corrections identified by the closed R1 incident and
resume the already-approved C1/C2 development closure and C3 first wave. The cohort,
937-view scene, seed, losses, schedule, criteria roles, and split barriers do not
change.

## Frozen scope

- 199 target buildings; 72 independent-evaluation eligible; development 51 only
- common source: 962 images / 937 exact image-pose members / 25 exclusions
- C1/C2/C3 comparison: identical development 51
- C3: one whole-scene model, seed 0, 30,000 completed optimizer updates
- validation 11 and held-out 10: unopened and prohibited
- C4, C5, Fusion W1, `R_ext`, UAS/ALS/LoD1/LoD2 training inputs: prohibited

## Exact corrections

1. **G2 result preservation.** Parse exact val3dity CityJSONSeq stdout before exit
   interpretation. Accept exit 1 only with complete expected IDs/metadata and at
   least one invalid feature; record `G2=false` and the runtime anomaly. Persist each
   unit add-once and resume verified units.
2. **C3 current-MVS initialization.** Do not reopen raw `dim_dense.ply`. Reuse the
   closed 1 m current-MVS derivative `mvs_class26_v1.ply` (222,044 points; 7,327,590
   bytes; SHA-256 `c7d63387d720dc4028c2b00e9cc6abb83d41161d6f033199ee619765fdfaf8dd`).
   Ignore classification, subtract `[690953,5336071,604]`, and add-once write local
   float32 XYZ. Concatenate all 371,808 SfM points: exact initial total 593,852.
3. **Semantic pixel alignment.** Use the exact 937 COLMAP-undistorted training RGBs,
   not the original 5280x3956 files. A membership-only Git manifest causes zero RGB
   pre-read; each natural inference read computes the RGB identity and verifies its
   dimensions against COLMAP camera metadata and the corresponding geometric depth
   map before inference. The final manifest becomes the exact undistorted RGB ledger.

The 255 original-resolution R1 completion directories are quarantined and must not be
resumed, resized, copied, or promoted into C3.

The 1 m spacing is an evidence-reuse and resource-bounded engineering choice, not a
claim that the literature prescribes 1 m or 0.4 m. No universal 0.4 m initialization
rule is assumed. Sparse-only initialization is prohibited because it both omits the
frozen current-image MVS support shared with C2 and contradicts the reviewer's prior
poor sparse-only observation. This R2 run therefore tests the already-frozen C3
recipe with current-image MVS plus SfM; it is not an initialization ablation.

## Reuse and no-repeat contract

- raw dense source reads/hashes: 0
- R1, `Images.zip`, `OPF.zip` full hashes: 0
- C1/C2 reconstruction and Roofer reruns: 0
- first G2 unit: one documented repeat because R1 discarded its stdout; other five:
  first and only validation read
- exact undistorted RGB: one natural verification/inference read per image
- R1 receipted GroundedSAM/BERT bundle: read-only reuse; no network fetch
- new outputs use a fresh R2 external namespace; no R1 artifact is modified

## Required outputs

- complete six-unit G2 receipt and 102-row C1/C2 development diagnostics
- actual G0--G2 C1/C2 counts, clearly labelled diagnostic G3/G4 candidate counts,
  and the existing 199→72 quantitative and fixed qualitative pass/fail explanation
  in one human-readable result report; do not relabel a diagnostic candidate as a
  frozen final `PASS_usable`
- 1 m MVS adapter output/receipt and exact 593,852-initial-point audit
- exact-937 undistorted semantic completions, final masks/manifest, and RGB-depth-mask
  shape audit
- C3 5k/10k/20k/30k full-state checkpoints, training log and technical receipt
- Return plus 200-verified or visible blocked receipt and direct-child 300-closed

## Done when

All authorized stages complete once or fail with reusable add-once evidence; no
prohibited split/input is read; writer ownership returns to Work Host; and
`scientific_verdict` remains `null`.
