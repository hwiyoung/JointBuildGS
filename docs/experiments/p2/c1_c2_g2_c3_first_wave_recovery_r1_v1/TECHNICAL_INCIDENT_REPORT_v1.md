# C1/C2 G2 + C3 first-wave recovery R1 technical incident report v1

- handoff_id: `P2-W2C-C1-C2-G2-C3-FIRST-WAVE-RECOVERY-R1-v1`
- accepted commit: `5050a212f6465ac759cf9a06d802ec9bb084c085`
- proposed status: `BLOCKED_FOR_BOUNDED_SOURCE_RECOVERY_R2`
- scientific_verdict: `null`

## Answer first

The cross-host portability recovery passed, but the first real input reads exposed
three bounded execution-contract defects. No performance training started and no
validation or held-out data were opened.

1. val3dity parsed the first C2 unit and returned exit 1. The runner discarded the
   parseable invalid-geometry result because it checked the process code first.
2. The raw dense source was read exactly once. All frozen 0.10/0.20/0.40 m candidates
   exceeded the 3,000,000-point cap, but the producer deleted scratch state without a
   terminal receipt, so exact candidate counts were lost.
3. The semantic contract bound the original 5280x3956 images, while C3 actually trains
   on the COLMAP-undistorted 1400x1013 images. Continuing would produce masks that do
   not share the RGB/depth pixel grid, so the run was stopped.

## Exact stage accounting

| Stage | Completed | Not completed |
|---|---|---|
| C1/C2 G2 | first C2 unit read/hashed once; one val3dity call | receipt absent; remaining five units unread |
| dense seed | raw 659,138,498-byte / 43,942,554-point PLY natural stream read once; every candidate known to exceed cap | exact three counts and output absent because failure receipt was not implemented |
| semantic manifest/assets | exact-937 Git-ledger manifest created; model/source/BERT bundle fetched and receipted once | no final mask manifest |
| semantic inference | 255 original-resolution completions; add-once progress preserved | stopped and quarantined; not C3-eligible because pixel grid differs |
| C3 training | 0 runs / 0 optimizer updates | no checkpoint or model output |

Operational preflights also recorded one zero-read failure from a pre-created final
output directory and one read/hash of the first 1400x1013 COLMAP image that correctly
failed against the original-image ledger. No semantic inference ran in either attempt.

## Recovery decisions

- G2: parse complete stdout before interpreting the exit code. Exit 1 is accepted only
  when metadata and all expected IDs are complete and at least one feature is invalid;
  record `G2=false` and `runtime_exit_anomaly=true`. Persist each unit add-once so a
  later unit cannot erase earlier evidence.
- Dense: do not reopen raw `dim_dense.ply`. Reuse the closed 1 m current-MVS derivative
  `mvs_class26_v1.ply`: 222,044 points (130,155 ground + 91,889 building), 7,327,590
  bytes, SHA-256 `c7d63387d720dc4028c2b00e9cc6abb83d41161d6f033199ee619765fdfaf8dd`.
  Its generation used only current image-derived MVS geometry, not UAS/ALS/LoD1/LoD2
  or evaluation labels. Classification is ignored. A one-read adapter subtracts
  `[690953, 5336071, 604]`, writes GS-local float32 XYZ add-once, and concatenates all
  371,808 SfM points for exactly 593,852 initial Gaussians.
- Semantic: build the manifest from the exact 937 COLMAP-undistorted training RGBs and
  infer on those same 1400x1013 bytes. RGB, geometric depth and semantic labels must
  have identical dimensions before optimizer update 1. The 255 original-resolution
  completions remain isolated and cannot be resized or promoted into C3.
- Telemetry: a future dense cap miss must publish input digest/read count, all candidate
  counts, selected=null and output=null before returning nonzero. A valid terminal
  receipt must prevent another source read.

The 1 m derivative is an initialization-only engineering fallback, not equivalent to
0.4 m raw voxel sampling. It is scientifically preferable here because it is already
attested, outcome-free, and is the exact common current-MVS geometry also consumed by
C2. Sparse-only remains prohibited.

## Prohibited work confirmed

C1/C2 reconstruction, Roofer, R1, `Images.zip`, `OPF.zip`, validation, held-out, C4,
C5, Fusion W1 and `R_ext` were not run or modified. The raw dense source will not be
read again merely to recover discarded counts. `scientific_verdict` remains `null`.
