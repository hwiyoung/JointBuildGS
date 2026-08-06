#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
artifact_root="${1:?usage: run_web_review199_exact_rows_host.sh ARTIFACT_ROOT}"
task_rel="phase-payloads/p2/c1_c2_shared_footprint_199_v3/P2-C1-C2-ORIGINAL-GLOBAL-v3-WEB-REVIEW199-EXACT-V6V4-ROWS-COMPACT-FIT-v11"
output_root="${artifact_root}/${task_rel}"
image="jointbuildgs-p0-tools:t0"
expected_image_id="sha256:02b4b7bb2e35e9b88bcc8457678ed8f178cca8f76f22b1b62f02721359e46be8"

[[ "${artifact_root}" == /* && -d "${artifact_root}" ]] || { echo "artifact root must be an existing absolute directory" >&2; exit 2; }
[[ "$(docker image inspect "${image}" --format '{{.Id}}')" == "${expected_image_id}" ]] || { echo "p0-tools image identity mismatch" >&2; exit 2; }
[[ ! -e "${output_root}" && ! -e "${output_root}.partial" ]] || { echo "fresh add-once output namespace required" >&2; exit 2; }

docker run --rm --network none --entrypoint /bin/bash \
  --user "$(id -u):$(id -g)" --cpus 4 --memory 8g --pids-limit 1024 \
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/workspace/JointBuildGS \
  -v "${repo_root}:/workspace/JointBuildGS:ro" \
  -v "${artifact_root}:/artifacts/JointBuildGS:rw" \
  -w /workspace/JointBuildGS "${image}" -lc \
  "python scripts/p2/c1_c2_shared_footprint_199_v3/build_web_review199_exact_rows.py \
    --config configs/p2/c1_c2_shared_footprint_199_v3/web_review199_exact_rows_v5.json \
    --artifact-root /artifacts/JointBuildGS \
    --output-root /artifacts/JointBuildGS/${task_rel} \
    --source-commit $(git -C "${repo_root}" rev-parse HEAD) \
    --image-id ${expected_image_id}"

echo "exact-row web review199 complete: ${output_root}"
