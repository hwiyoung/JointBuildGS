# diff-surfel-rasterization cull3 (PHD-MAIN-STAGE3-v1)

A memory-only patch of the surfel rasterizer that the fork image `jointbuildgs:geogs-conf-guided-v1` builds from
`/opt/geogs-source/submodules/diff-surfel-rasterization`. Used for one training only: `B0n13/prop_LoD2_s0` (stage 3, 연직 포함 13장
본 방법), attempt 3, after the user's decision of 2026-10-15 09:2x. `scientific_verdict: null`.

- **Why.** The training stopped twice on GPU memory with the unpatched rasterizer (2026-10-14 21:34 and 21:56). A few Gaussians beside a
  camera, outside its view, whose 3-sigma disk crosses the camera plane get a diverging screen box from `compute_aabb`
  (d = 9 (T2x^2 + T2y^2) - T2z^2 > 0) and are put in every tile of the image. The sort buffers grow with the (tile, Gaussian) pairs,
  about 40 B each; the run reached 492 million pairs (about 20 GB) when it stopped. A normal render has 3 to 6 million pairs.
- **Patch** (`cull3.patch`, `rasterizer_impl.cu` only; `forward.cu` and `backward.cu` untouched):
  - a kernel of its own, launched after `preprocess`: a Gaussian with d > 0 whose 3.4-sigma sphere lies wholly outside the symmetric
    view frustum (side planes, or before the near plane) and whose screen centre is more than 3 px outside the image gets
    `tiles_touched = 0`. Its radius, depth, centre and the returned `radii` are unchanged (visibility filter, max screen radii,
    densification and pruning see the same values).
  - `duplicateWithKeys`: a Gaussian with no tiles (offset difference 0) writes no key.
  - Why the image is the same: such a Gaussian has alpha < 1/255 at every pixel, so the forward and backward pixel loops already skip it.
- **Earlier forms, not used:** cull1 (the same rule inside the preprocess kernel) and cull2 (a kernel of its own with the frustum rule for
  every Gaussian) changed the forward output; the diagnosis (`scripts/phd/main_stage3_v1/cull_diag_s3.py`) found that the frustum rule
  alone also removed ordinary Gaussians at the lower image edge. cull3 adds the condition d > 0. `rebuild0` (the unpatched source built
  the same way) matches the base image's machine code, so the differences came from the patches, not from the build.
- **Checks** (`scripts/phd/main_stage3_v1/cull1_check_s3.py`; payload `checks/cull1/compare_cull3_*.json`), on B0_b10/prop_LoD2_s0,
  B0n13/imgonly_s0 and B0a9/prop_LoD2_s0, 38 views: forward outputs and radii sha256-equal to the base image. Gradients differ at the
  base image's own run-to-run rounding level (relative 1e-7 to 1e-6) but beyond the pre-set bound (twice one base pair's difference) on
  two of the three results. The bound was not changed; the user decided to use cull3 (asked 01:3x, answered 09:2x).
- **Image** (build context = this directory; the Dockerfile of the second form takes the patch as an argument):

  ```bash
  docker build -f Dockerfile.geogs-conf-guided-v1-cull2 --build-arg PATCH=cull3.patch -t jointbuildgs:geogs-conf-guided-v1-cull3 src/phd/forks/diff-surfel-rasterization-cull3
  ```

  `_C` library sha256 `e88ed6d77b54aaedf2939416415035c2e5b53c65ce8acdbda9cb7b5e006c8e89` (base `5ed584496a1f4f8d7bb8c2fb5d0e849a7d5e76924d89043eeb101dc83c9dd0a8`).
- The fixed GeoGS image (official rasterizer) does not carry this patch.
