#!/usr/bin/env bash
set -euo pipefail
b_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
b_artifacts=$(realpath "$b_repo/../JointBuildGS-artifacts")
b_parent="$b_artifacts/phase-payloads/phd/p2_ab_v2"
b_output="$b_parent/PHD-P2-AB-V2-B-GRADIENT-AUDIT-v1"
b_overlay="$b_artifacts/phase-payloads/p2/e3_local_4906982_surface_intersection_diag_v1/P2-E3-LOCAL-4906982-SURFACE-INTERSECTION-DIAG-v1/control/surface_python_overlay/gsplat/cuda/csrc"
mkdir "$b_output"
docker run --rm --network none --gpus '"device=1"' --entrypoint python \
 --mount "type=bind,src=$b_repo,dst=/workspace/JointBuildGS,readonly" \
 --mount "type=bind,src=$b_artifacts,dst=/artifacts/JointBuildGS,readonly" \
 --mount "type=bind,src=$b_output,dst=/output" \
 --mount "type=bind,src=$b_parent/PHD-P2-AB-V2-B-RUNTIME-v1,dst=/root/.cache/torch_extensions" \
 --mount "type=bind,src=$b_overlay/rasterize_to_pixels_2dgs_fwd.cu,dst=/opt/conda/lib/python3.11/site-packages/gsplat/cuda/csrc/rasterize_to_pixels_2dgs_fwd.cu,readonly" \
 --mount "type=bind,src=$b_overlay/rasterize_to_pixels_2dgs_bwd.cu,dst=/opt/conda/lib/python3.11/site-packages/gsplat/cuda/csrc/rasterize_to_pixels_2dgs_bwd.cu,readonly" \
 --workdir /workspace/JointBuildGS --env PYTHONDONTWRITEBYTECODE=1 --env OMP_NUM_THREADS=2 \
 --env OPENBLAS_NUM_THREADS=1 --env MAX_JOBS=2 --env JBGS_GSPLAT_MEDIAN_IS_SURFACE_SUM=1 \
 jointbuildgs:dev -m scripts.phd.p2_ab_v2.b_gradient_audit --config configs/phd/p2_ab_v2/b_gradient_audit_v1.json
