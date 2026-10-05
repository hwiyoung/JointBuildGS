#!/usr/bin/env bash
set -euo pipefail
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
artifact_root=$(realpath "$repo_root/../JointBuildGS-artifacts")
prep_run=${1:?Pass CPU input preparation attempt directory}
finalize_run=$(mktemp -d "$prep_run/finalize_$(date -u +%Y%m%dT%H%M%SZ)_XXXXXXXX")
mkdir -p "$finalize_run/source"
for relative in scripts/phd/r1_mvs_control_v1 scripts/phd/geogs_p1p2p3_v1/input src/phd/geogs_mvs_pgsr_v1 src/phd/region_view_support_v1.py configs/phd/r1_mvs_control_v1; do
  mkdir -p "$finalize_run/source/$(dirname "$relative")"
  cp -a "$repo_root/$relative" "$finalize_run/source/$relative"
done
command=(docker run --rm --runtime runc --network none --cpus 4 --memory 8g --user "$(id -u):$(id -g)"
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/repo -e OPENBLAS_NUM_THREADS=1 -e OMP_NUM_THREADS=4
  -e NVIDIA_VISIBLE_DEVICES=void -e CUDA_VISIBLE_DEVICES=
  --mount "type=bind,source=$finalize_run/source,target=/repo,readonly"
  --mount "type=bind,source=$prep_run/result/input,target=/input,readonly"
  --mount "type=bind,source=$artifact_root/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/sources/GeoGS-state-camera-v1,target=/anchor_source,readonly"
  --mount "type=bind,source=$artifact_root/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1/sources/GeoGS-mvs-pgsr-v1,target=/refinement_source,readonly"
  --mount "type=bind,source=$finalize_run,target=/output" --entrypoint python
  sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774
  /repo/scripts/phd/r1_mvs_control_v1/finalize_preparation.py --output /output/runtime)
printf '%q ' "${command[@]}" > "$finalize_run/command.sh"
printf '\n' >> "$finalize_run/command.sh"
printf 'FINALIZE_RUN=%s\n' "$finalize_run"
"${command[@]}" 2>&1 | tee "$finalize_run/run.log"
