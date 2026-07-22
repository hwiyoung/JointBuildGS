# P1W run issues

## 2026-07-22 — 04a inference attempt 1 failed before output publication

- Issue ID: `P1W-MASK-04A-ATTEMPT1-SMALL-CORE`
- Stage reached: all 481 GroundedSAM view inferences completed; failure occurred in
  deterministic vision/footprint fusion.
- Error: `MaskProducerError: projected footprint remains empty after locked 1px core retry`
  from `fuse_vision_roof_mask`.
- Cause classification: at least one nonempty projected selected-building footprint was
  too small to retain a pixel after both the locked 5 px and 1 px erosions. The v1 error
  did not include the view/building ID, so that ID cannot be recovered from the failed
  in-memory attempt.
- Counters: `inference_runs_started=1`, `inference_runs_successful=0`,
  `inference_runs_failed=1`, `learning_runs_started=0`, `optimizer_steps=0`,
  `published_04a_mask_sets=0`.
- GT/GS-result use for the repair: `0`. The repair only adds the original **nonempty**
  projected footprint as the final 0 px core after the locked `5 px -> 1 px` attempts.
  A view with no nonempty projected selected-building footprint still hard-fails.
- Retry accounting: the next 04a command must explicitly pass
  `--prior-inference-runs-started 1`; a successful manifest must therefore report
  cumulative `inference_runs_started=2`, `inference_runs_successful=1`, and
  `inference_runs_failed=1`.

## 2026-07-22 — existing 04b must be regenerated after fusion-only lock revision

- The completed 04b attempt 1 was produced with producer-lock SHA
  `4728402e0ff781d8322c8fbf2f663e473575f872cfac0d7180c1f34627916f16`.
- The small-core rule changes the common producer-lock SHA even though 04b raycasting
  itself is unchanged. Therefore the old 04b cannot be paired with the retried 04a in
  the final controlled pair.
- Preserve it without deletion as
  `plane_masks_04b_attempt1_pre_small_core`, then regenerate 04b under the revised lock.
- The attempt-1 `producer_manifest.json` was created root-owned with mode `0600`, while
  `mask_manifest.json` was mode `0444`; this prevented host-side read-only QA. Revised
  producers publish `producer_manifest.json` as host-readable immutable mode `0444`.
- 04b regeneration remains raycast/evaluation-only:
  `learning_runs_started=0`, `optimizer_steps=0`.
- Asset provenance is not re-signed: the revised lock pins the unchanged receipt bytes
  SHA `ff144c6571713563895a41a67585e4d8b6f3d6f4bdef4a46716a19bd6efab76c`
  and its fetch-time producer-lock SHA
  `4728402e0ff781d8322c8fbf2f663e473575f872cfac0d7180c1f34627916f16`
  separately, with the disclosure
  `fusion-only revision; asset bytes unchanged`.

## 2026-07-22 — mask QA attempt 1 published a root-only directory

- Issue ID: `P1W-MASK-QA-ATTEMPT1-DIR-MODE`
- The first completed read-only pair QA validated all 481 views and wrote `0444`
  files, but Python `mkdtemp` left the containing directory root-owned mode `0700`.
  Host-side review therefore could not read the otherwise complete outputs.
- The inaccessible attempt is preserved without deletion as
  `plane_masks_04a_vs_04b_qa_attempt1_root700`.
- Repair: publish the staging directory as mode `0555` before its atomic rename;
  CSV and manifest remain mode `0444`. The repaired run repeats only evaluation
  arithmetic: `inference_runs_started_by_qa=0`, `learning_runs_started=0`,
  `optimizer_steps=0`, source masks unchanged.

## 2026-07-22 — attempt 4 failed at the first full-state checkpoint

- Issue ID: `P1W-TRAIN-ATTEMPT4-SEED-MASK-CHECKPOINT`.
- Both condition 01 seeds executed 5,000 optimizer updates, then failed before
  publishing a durable checkpoint with
  `CheckpointIntegrityError: surface_seed_mask must be bool with one row per saved Gaussian`.
- Cause: gsplat duplicate/split/remove kept parameter tensors and registered strategy
  state row-aligned, but the model-side `surface_seed_mask` remained at the initial
  1,252,033 rows. At 5k the live populations were about 600k rows.
- The queue was stopped after condition 02 had begun. Its two seeds report cumulative
  `learning_runs_started=1`; their last observed progress displays were 238 and 215,
  with no durable checkpoint.
- No checkpoint payload or SHA sidecar was published by this attempt. The complete
  read-only snapshot, cumulative logs, driver manifest, and SHA receipt are preserved
  under `training/failed_attempts/attempt4_checkpoint_seed_mask/`.
- Repair: register the all-False mask as row-wise strategy state even for condition 01,
  let gsplat transform it during duplicate/split/remove, and synchronize it back to the
  model after every refine/final-prune operation. The checkpoint validator remains
  unchanged.
- Regression coverage executes an actual gsplat duplicate -> split -> remove sequence
  for both all-False and mixed lineage masks, then requires full-state save/load to
  preserve the final live-row mask.
