# Official DA3 preprocessing for the GeoGS diagnostic

Task: `PHD-GEOGS-P1P2P3-v1`; `scientific_verdict: null`.

This wrapper uses the unchanged official GeoGS `read_colmap_data` helper and its
DA3 inference arguments. The DA3 API, network and weights are official. The
intentional input adaptation is train-only balanced consecutive batches of at most8
views, ordered by filename. Revision2 uses K=ceil(N/8) and array_split intoK
groups; all current groups contain7 or8 views. Every batch must have at least3
noncollinear camera centers (SVD rank>=2) for official pose-scale alignment.
It is not a claim to reproduce full-collection DA3 inference.

Pinned sources:

- [Official DA3 repository](https://github.com/ByteDance-Seed/Depth-Anything-3/tree/3d835ec1a5802d64a8b8b15f817a1ab54809bfe4),
  commit `3d835ec1a5802d64a8b8b15f817a1ab54809bfe4`, installed package version0.0.0.
- [Original DA3NESTED-GIANT-LARGE weights](https://huggingface.co/depth-anything/DA3NESTED-GIANT-LARGE/tree/8615eefb62f2db4f8d6ebaa59160086981672829),
  revision `8615eefb62f2db4f8d6ebaa59160086981672829`.
- Weight SHA256 `8899faf998dedbc230261ab736fa57015280727399429122d44d4f9e7aac2ddd`,
  6,759,558,100 bytes, verified against publisher LFS metadata.
- Official GeoGS preprocessing SHA256
  `97703618afba7563b7f6f8ef2671219b525925e1474140871609db2fc2c7c2ea`.
- Dedicated image `jointbuildgs:geogs-da3-3d835ec-v1`, image ID
  `sha256:4130d2597c2c3c2804a7cacb8302be948314bc37ba81a1a21383e1c8b7fbba73`.
  Base torch2.4.1+cu121, torchvision0.19.1+cu121, numpy1.26.4 are preserved.
  Optional DA3 UI/GS/training packages are not needed for depth inference.

External task-relative owners:

- `sources/Depth-Anything-3`: unmodified official source.
- `sources/DA3NESTED-GIANT-LARGE`: model, config, model card and hashes.
- `runtime/da3`: acquisition/build logs, image inspect, package freeze, commands.
- `da3/P1|P2|P3/NEW_RUN_TAG`: actual generated depths and receipts.

From repository root, acquire and build once into new task storage:

```bash
bash scripts/phd/geogs_p1p2p3_v1/da3/acquire.sh
bash scripts/phd/geogs_p1p2p3_v1/da3/build.sh
```

Acquisition rejects an existing final receipt; it does not overwrite earlier
results. Build must be coordinated with other Docker builds and preserves all
existing images. Weights remain outside the image and Docker filesystem.

Run a fixed batch preflight or a full region using an unoccupied GPU:

```bash
JBGS_DA3_GPU_INDEX=0 bash scripts/phd/geogs_p1p2p3_v1/da3/run.sh P1 balanced_preflight_v2 0
JBGS_DA3_GPU_INDEX=0 bash scripts/phd/geogs_p1p2p3_v1/da3/run.sh P1 balanced_v2
```

The launcher accepts P1/P2/P3 and a new output tag. GPU0 preprocessing alongside
GPU1 native training is a resource-only scheduling revision approved in the active
task. The PyTorch allocator is limited to80% of the visible GPU to preserve desktop
headroom. The launcher checks free memory and active utilization before starting;
it never stops a service or process. CUDA OOM is recorded without silently reducing
the840 resolution,8-view maximum, or model size. Processing may be scheduled only
after the parent task coordinates GPU ownership.

The inference container is network-disabled and does not mount the full artifact
root, full RGB scene directory, UAS, or evaluation RGB. Its RGB input is the
self-contained train-only `da3_batches` directory. Split metadata lists exclusions
so the driver can assert no evaluation image appears. Source image SHA, camera
poses, intrinsics, model SHA, official script SHA and installed DA3 source bytes are
checked before inference.

`raw_depth_upsampled/*.npy` is the official-style cubic upsampled depth used by
GeoGS. `raw_depth/`, confidence arrays, per-batch NPZ/JSON and run receipts retain
the inference output and its identity. The wrapper records invalid-depth fractions
without modifying values to improve an evaluation score. Each run writes into a
new empty directory; a failed run and completed earlier batches remain available.
No GeoGS training is performed by these scripts.

After a complete region succeeds, create the new immutable input package:

```bash
bash scripts/phd/geogs_p1p2p3_v1/da3/consolidate.sh P1 balanced_v2
```

This writes `inputs/P1/da3/raw_depth/<stem>.npy` at original resolution, retains
inference-resolution arrays separately, and verifies exact source hashes and full
train-only membership. It rejects an existing target and any partial/failed run.
P2/P3 use their corresponding region argument and successful run tag.

Runtime attempts are preserved. The first wrapper preflight stopped before model
inference because DA3 is a namespace package; its integrity check now resolves the
installed path through `depth_anything_3.api`. The next8-view preflight succeeded.
The first whole-region attempt then ran out of allocator memory on batch1 after
batch0 succeeded. The retry deletes completed prediction temporaries, calls
`gc.collect()` and releases only unused CUDA cache after every batch, recording
allocated/reserved bytes before and after. It retains the exact model, input
partition,840 resolution, seed and80% allocator cap. No expandable-segment or
smaller-input policy is silently enabled.

The cache-managed P1 attempt passed its first12 batches but failed the last2-view
batch because official evo Umeyama alignment rejects covariance rank<2. This
input-contract failure motivates the common balanced revision2, with unchanged
image train/evaluation membership, model,840 resolution, seed and allocatorcap.
Old batches, manifests and partial results remain intact. New data use
`split_manifest_da3_v2.json` and `da3_batches_v2`; the separate
`da3_batch_revision_v2.json` is hashed alongside the exact base config bytes.
All three regions are rerun under this one policy; no reference score selects it.
