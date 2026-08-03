# P2 C1/C2/C3 U_target=199 technical census v1

- task_id: `P2-C1-C2-C3-UTARGET199-v1`
- handoff_id: `P2-W2C-C1-C2-C3-UTARGET199-v1`
- status: `APPROVED_FOR_EXECUTION`
- approval_basis: `direct human instruction in the Experiment Host task on 2026-08-04`
- target: exact `U_target=199`, with no 72/10 display cohort split
- random seed: `0` paired across C3-1/C3-2
- scientific_verdict: `null`

## Technical objective

Complete the 199-building C1/C2 technical census and then run two paired C3 development
conditions without human intervention:

1. `C3-1 = 2DGS + image-derived semantic pseudo-label loss`;
2. `C3-2 = C3-1 + image-derived MVS depth loss`.

`C3-2` is preregistered here as the image-only base that future C4/C5 conditions must
share. C4/C5 are not authorized by this packet.

## Common C3 seed

Both conditions start from byte-identical `all SfM sparse + sampled common-MVS dense`:

- retain all exact 371,808 SfM sparse points;
- read the exact 43,942,554-point common dense MVS once;
- crop only the frozen common AOI/Z range;
- use deterministic EPSG:25832 3D voxel-center-nearest representatives;
- test fixed nested voxel sizes `0.5/1.0/2.0/4.0 m` and publish the finest candidate
  with at most 220,000 dense representatives;
- perform no classification, footprint, building-ID, semantic, UAS, ALS, LoD1 or LoD2
  filtering;
- enforce at most 591,808 initial Gaussians and an 800,000 live-Gaussian cap.

The former 222,044-point 1 m class-2/6 derivative and the former 406,337-primitive
checkpoint remain immutable legacy diagnostics and are not an input to this task.

## Paired loss contract

The two configs are byte-equivalent except for `load_depth`, `w_depth`, and `out_dir`.
Both use the same exact 937 RGBs, semantic masks, seed 0, 30,000 updates, photometric
loss, semantic CE, normal consistency and normalized 2DGS distortion. Structural,
mutual, MVC, external normal, external prior and semantic-geometry auxiliary losses are
zero. C3-2 alone activates the existing image-derived MVS depth L1 with the frozen
5k-to-10k ramp to `0.03`.

## GPU and unattended execution

- use physical GPU 0 only and never interrupt or share GPU 1;
- require at least 22,000 MiB free before seed0 C3-1 and again before seed0 C3-2;
- run the pair sequentially;
- fail closed before training if the neutral dense seed exceeds 220,000 points;
- retain any failed add-once namespace for diagnosis; never delete or overwrite it;
- produce exact 5k/10k/15k/20k/25k/final checkpoints and logs;
- report a single-paired-seed development boundary; do not claim seed variance.

## C1/C2 and evaluation boundary

- every one of the 199 stable IDs remains in the qualitative/index/result surface;
- legacy 72/10 reference labels are not visible cohorts;
- raw reference-cell/patch/group provenance may remain in machine-readable audit rows;
- missing independent current reference remains explicit and is not replaced by 2022
  LoD2;
- 2022 LoD2 roofline is evaluation-only historical context;
- official G3/G4/`PASS_usable` and `scientific_verdict` remain `null`.

## Prohibited

- C4/C5/Fusion W1 execution or result access;
- GT RoofSurface, roof type, semantic label or final LoD2 model in C1/C2/C3 geometry;
- external roofprint in Stage 3;
- deletion, overwrite or relabeling of any prior partial/final payload;
- selecting a better C3 checkpoint or seed after viewing outcomes.
