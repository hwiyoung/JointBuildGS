#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
artifact_root="${1:?usage: run_photo_evidence199_host.sh ARTIFACT_ROOT}"
task_rel="phase-payloads/p2/qualitative_row1_current_raw_v7/P2-QUALITATIVE-ROW1-CURRENT-RAW-v7-PHOTO-EVIDENCE199-v3"
output_root="${artifact_root}/${task_rel}"
image="jointbuildgs:dev"
expected_image_id="sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774"

[[ "${artifact_root}" == /* && -d "${artifact_root}" ]] || { echo "artifact root must be an existing absolute directory" >&2; exit 2; }
[[ "$(docker image inspect "${image}" --format '{{.Id}}')" == "${expected_image_id}" ]] || { echo "runtime image identity mismatch" >&2; exit 2; }
[[ ! -e "${output_root}" && ! -e "${output_root}.partial" ]] || { echo "fresh add-once output namespace required" >&2; exit 2; }

docker run --rm --network none --entrypoint /bin/bash \
  --user "$(id -u):$(id -g)" --cpus 8 --memory 28g --pids-limit 2048 \
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/workspace/JointBuildGS \
  -v "${repo_root}:/workspace/JointBuildGS:ro" \
  -v "${artifact_root}:/artifacts/JointBuildGS:rw" \
  -w /workspace/JointBuildGS "${image}" -lc \
  "python scripts/p2/qualitative_row1_current_raw_v7/build_photo_evidence199.py \
    --config configs/p2/qualitative_row1_current_raw_v7/photo_evidence199_v3.json \
    --artifact-root /artifacts/JointBuildGS \
    --output-root /artifacts/JointBuildGS/${task_rel} \
    --source-commit $(git -C "${repo_root}" rev-parse HEAD) \
    --image-id ${expected_image_id}"

echo "photo evidence199 complete: ${output_root}"
