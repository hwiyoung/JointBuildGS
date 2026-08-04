#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
artifact_root="${JBGS_ARTIFACT_ROOT:-/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts}"
relative_root="phase-payloads/p2/c1_c2_c3_consolidated_results_v1/P2-C1-C2-C3-CONSOLIDATED-RESULTS-v2"
final_root="${artifact_root}/${relative_root}"
partial_root="${final_root}.partial"
project_image="sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774"

[[ ! -e "${final_root}" && ! -e "${partial_root}" ]] || { echo "add-once v2 output namespace exists" >&2; exit 2; }
source_base_commit="$(git -C "${repo_root}" rev-parse HEAD)"
docker run --rm --network none -v "${artifact_root}:/artifacts/JointBuildGS:rw" "${project_image}" \
  sh -lc "install -d -o $(id -u) -g $(id -g) -m 0755 '/artifacts/JointBuildGS/${relative_root}.partial'"
docker run --rm --network none --cpus 4 --memory 32g --pids-limit 1024 \
  --entrypoint /opt/conda/bin/python --user "$(id -u):$(id -g)" -e HOME=/tmp -e MPLCONFIGDIR=/tmp/mpl -e PYTHONDONTWRITEBYTECODE=1 \
  -v "${repo_root}:/workspace/JointBuildGS:ro" -v "${artifact_root}:/artifacts/JointBuildGS:rw" \
  -w /workspace/JointBuildGS "${project_image}" -B \
  scripts/p2/c1_c2_c3_consolidated_results_v1/compose_v2.py \
  --output-root "/artifacts/JointBuildGS/${relative_root}.partial" \
  --artifact-root /artifacts/JointBuildGS --source-base-commit "${source_base_commit}"
docker run --rm --network none -v "${artifact_root}:/artifacts/JointBuildGS:rw" "${project_image}" \
  sh -lc "mv -- '/artifacts/JointBuildGS/${relative_root}.partial' '/artifacts/JointBuildGS/${relative_root}'"
echo "completed: ${final_root}"
