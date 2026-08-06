#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
artifact_root="${1:?usage: run_cloudcompare_review10_host.sh ARTIFACT_ROOT}"
task_rel="phase-payloads/p2/c1_c2_shared_footprint_199_v3/P2-C1-C2-ORIGINAL-GLOBAL-v3-CLOUDCOMPARE-REVIEW10-v1"
final_root="${artifact_root}/${task_rel}"
partial_root="${final_root}.partial"
image="jointbuildgs-p0-tools:t0"
expected_image_id="sha256:02b4b7bb2e35e9b88bcc8457678ed8f178cca8f76f22b1b62f02721359e46be8"

[[ "${artifact_root}" == /* && -d "${artifact_root}" ]] || { echo "artifact root must be an existing absolute directory" >&2; exit 2; }
[[ "$(docker image inspect "${image}" --format '{{.Id}}')" == "${expected_image_id}" ]] || { echo "p0-tools image identity mismatch" >&2; exit 2; }
[[ ! -e "${final_root}" && ! -e "${partial_root}" ]] || { echo "fresh add-once review10 namespace required" >&2; exit 2; }
mkdir -p "${partial_root}"

docker run --rm --network none --entrypoint /bin/sh \
  --user "$(id -u):$(id -g)" --cpus 12 --memory 64g --pids-limit 4096 \
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/workspace/JointBuildGS \
  -v "${repo_root}:/workspace/JointBuildGS:ro" \
  -v "${artifact_root}:/artifacts/JointBuildGS:ro" \
  -v "${partial_root}:/output:rw" \
  -w /workspace/JointBuildGS "${image}" -lc \
  "python scripts/p2/c1_c2_shared_footprint_199_v3/build_cloudcompare_review10.py \
    --artifact-root /artifacts/JointBuildGS \
    --output-root /output"

mv -- "${partial_root}" "${final_root}"
echo "frozen v3 CloudCompare review10 complete: ${final_root}"
