#!/usr/bin/env bash
set -euo pipefail
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
artifact_root=$(realpath "$repo_root/../JointBuildGS-artifacts")
audit_run=${1:?Pass completed whole-R1 audit attempt}
review_run=${2:?Pass completed whole-R1 review attempt}
validation_run=$(mktemp -d "$review_run/validation_$(date -u +%Y%m%dT%H%M%SZ)_XXXXXXXX")
mkdir "$validation_run/source"
cp "$repo_root/scripts/phd/r1_area_judgment_v1/validate.py" "$validation_run/source/validate.py"
command=(docker run --rm --runtime runc --network none --cpus 2 --memory 4g --user "$(id -u):$(id -g)"
  -e PYTHONDONTWRITEBYTECODE=1 -e OPENBLAS_NUM_THREADS=1 -e OMP_NUM_THREADS=2
  -e NVIDIA_VISIBLE_DEVICES=void -e CUDA_VISIBLE_DEVICES=
  --mount "type=bind,source=$review_run/source,target=/repo,readonly"
  --mount "type=bind,source=$validation_run/source,target=/driver,readonly"
  --mount "type=bind,source=$audit_run/result,target=/audit,readonly"
  --mount "type=bind,source=$review_run/result,target=/review,readonly"
  --mount "type=bind,source=$artifact_root/phase-payloads/phd/region_view_support_v1/PHD-R1R5-VIEW-SUPPORT-v1/attempt_20260915T130845Z_TkeMtl/result,target=/old,readonly"
  --mount "type=bind,source=$validation_run,target=/output" --entrypoint python
  sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774
  /driver/validate.py --output /output/result)
printf '%q ' "${command[@]}" > "$validation_run/command.sh"
printf '\n' >> "$validation_run/command.sh"
printf 'VALIDATION_RUN=%s\n' "$validation_run"
"${command[@]}" 2>&1 | tee "$validation_run/run.log"
