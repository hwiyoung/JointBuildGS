#!/usr/bin/env bash
set -euo pipefail
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
artifact_root=$(realpath "$repo_root/../JointBuildGS-artifacts")
prep_run=${1:?Pass the CPU input preparation attempt directory}
review_run=$(mktemp -d "$prep_run/review_$(date -u +%Y%m%dT%H%M%SZ)_XXXXXXXX")
mkdir -p "$review_run/source"
for relative in scripts/phd/r1_mvs_control_v1 src/phd/region_view_support_v1.py configs/phd/r1_mvs_control_v1 configs/phd/region_view_support_v1/regions_v1.json; do
  mkdir -p "$review_run/source/$(dirname "$relative")"
  cp -a "$repo_root/$relative" "$review_run/source/$relative"
done
command=(docker run --rm --runtime runc --network none --cpus 4 --memory 8g --user "$(id -u):$(id -g)"
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/repo -e OPENBLAS_NUM_THREADS=1 -e OMP_NUM_THREADS=4
  -e NVIDIA_VISIBLE_DEVICES=void -e CUDA_VISIBLE_DEVICES= -e MPLCONFIGDIR=/tmp/mpl
  --mount "type=bind,source=$review_run/source,target=/repo,readonly"
  --mount "type=bind,source=$prep_run/result/input,target=/input,readonly"
  --mount "type=bind,source=$artifact_root/phase-payloads/phd/manual_region_masks_v1/support_audit.rvEKKQ/result/reference_sample_support.npz,target=/p1_source.npz,readonly"
  --mount "type=bind,source=$review_run,target=/output" --entrypoint python
  sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774
  /repo/scripts/phd/r1_mvs_control_v1/review_draft.py --output /output/result)
printf '%q ' "${command[@]}" > "$review_run/command.sh"
printf '\n' >> "$review_run/command.sh"
printf 'REVIEW_RUN=%s\n' "$review_run"
"${command[@]}" 2>&1 | tee "$review_run/run.log"
