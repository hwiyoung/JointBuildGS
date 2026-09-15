#!/usr/bin/env bash
set -euo pipefail
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
artifact_root=$(realpath "$repo_root/../JointBuildGS-artifacts")
audit_run=${1:?Pass completed whole-R1 audit attempt}
review_run=$(mktemp -d "$audit_run/review_$(date -u +%Y%m%dT%H%M%SZ)_XXXXXXXX")
mkdir -p "$review_run/source"
for relative in scripts/phd/r1_area_judgment_v1 configs/phd/r1_area_judgment_v1 src/phd/region_view_support_v1.py artifacts/manifests/gate_s0/freeze_recovery_v1/technical_freeze_manifest_v1.json; do
  mkdir -p "$review_run/source/$(dirname "$relative")"
  cp -a "$repo_root/$relative" "$review_run/source/$relative"
done
command=(docker run --rm --runtime runc --network none --cpus 4 --memory 8g --user "$(id -u):$(id -g)"
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/repo -e OPENBLAS_NUM_THREADS=1 -e OMP_NUM_THREADS=4
  -e NVIDIA_VISIBLE_DEVICES=void -e CUDA_VISIBLE_DEVICES= -e MPLCONFIGDIR=/tmp/mpl
  --mount "type=bind,source=$review_run/source,target=/repo,readonly"
  --mount "type=bind,source=$artifact_root/phase-payloads/phd/r1_mvs_control_v1/PHD-R1-MVS-CONTROL-PREP-v1/attempt_20260916T130151Z_jm4gu7vc/result/input,target=/input,readonly"
  --mount "type=bind,source=$audit_run/result,target=/evidence,readonly"
  --mount "type=bind,source=$audit_run/overview,target=/overview,readonly"
  --mount "type=bind,source=$artifact_root/phase-payloads/phd/manual_region_masks_v1/support_audit.rvEKKQ/result/reference_sample_support.npz,target=/p1_source.npz,readonly"
  --mount "type=bind,source=$repo_root/configs/phd/manual_region_masks_v1/p1_v1.json,target=/p1_config.json,readonly"
  --mount "type=bind,source=/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc,target=/font.ttf,readonly"
  --mount "type=bind,source=$review_run,target=/output" --entrypoint python
  sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774
  /repo/scripts/phd/r1_area_judgment_v1/review.py --output /output/result)
printf '%q ' "${command[@]}" > "$review_run/command.sh"
printf '\n' >> "$review_run/command.sh"
printf 'REVIEW_RUN=%s\n' "$review_run"
"${command[@]}" 2>&1 | tee "$review_run/run.log"
