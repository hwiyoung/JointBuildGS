#!/usr/bin/env bash
set -euo pipefail
b_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
b_artifacts=$(realpath "$b_repo/../JointBuildGS-artifacts")
b_run=${1:-PHD-P2-AB-V6-B-SURFACE-v2}
b_parent="$b_artifacts/phase-payloads/phd/p2_ab_v6"
b_output="$b_parent/$b_run"
b_cache="$b_parent/PHD-P2-AB-V6-B-RUNTIME-v1"
b_overlay="$b_artifacts/phase-payloads/phd/p2_ab_v2/PHD-P2-AB-V2-B-GEOMETRY-ADAPTER-v2/overlay"
b_oldcache="$b_artifacts/phase-payloads/phd/p2_ab_v4/PHD-P2-AB-V4-B-RUNTIME-v1"
b_image=$(docker image inspect jointbuildgs:dev --format '{{.Id}}')
b_head=$(git -C "$b_repo" rev-parse HEAD)
mkdir -p "$b_parent"
mkdir "$b_output"
if [[ ! -d "$b_cache" ]]; then mkdir "$b_cache"; cp -a "$b_oldcache/." "$b_cache/"; fi
docker run --rm --network none --gpus '"device=1"' --cpus 6 --memory 24g --entrypoint python \
  --mount "type=bind,src=$b_repo,dst=/workspace/JointBuildGS,readonly" \
  --mount "type=bind,src=$b_artifacts,dst=/artifacts/JointBuildGS,readonly" \
  --mount "type=bind,src=$b_output,dst=/output" \
  --mount "type=bind,src=$b_cache,dst=/root/.cache/torch_extensions" \
  --mount "type=bind,src=$b_overlay/rasterize_to_pixels_2dgs_fwd.cu,dst=/opt/conda/lib/python3.11/site-packages/gsplat/cuda/csrc/rasterize_to_pixels_2dgs_fwd.cu,readonly" \
  --mount "type=bind,src=$b_overlay/rasterize_to_pixels_2dgs_bwd.cu,dst=/opt/conda/lib/python3.11/site-packages/gsplat/cuda/csrc/rasterize_to_pixels_2dgs_bwd.cu,readonly" \
  --workdir /workspace/JointBuildGS --env PYTHONDONTWRITEBYTECODE=1 \
  --env OMP_NUM_THREADS=2 --env OPENBLAS_NUM_THREADS=1 --env MAX_JOBS=2 \
  --env JBGS_GSPLAT_MEDIAN_IS_SURFACE_SUM=1 --env JBGS_P2_GEOMETRY_ADAPTER=c4_c8_v1 \
  --env "JBGS_SOURCE_GIT_HEAD=$b_head" --env "JBGS_CONTAINER_IMAGE_ID=$b_image" \
  "$b_image" -m scripts.phd.p2_ab_v6.b_surface_probe --config configs/phd/p2_ab_v6/b_surface_probe_v2.json \
  2>&1 | tee "$b_parent/$b_run.console.log"
