#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
artifact_root="${1:?usage: run_c1_c2_oracle_recovery_v2_host.sh ARTIFACT_ROOT PROJECT_IMAGE SOURCE_COMMIT RUN_ID}"
project_image="${2:?missing project image}"
source_commit="${3:?missing source commit}"
run_id="${4:?missing run ID}"
source_rel="phase-payloads/p2/selected10_c1_c4_presentation_v1/P2-SELECTED10-C1-C2-ORACLE-PRESENTATION-v1"
target_rel="phase-payloads/p2/selected10_c1_c4_presentation_v1/P2-SELECTED10-C1-C2-ORACLE-PRESENTATION-RECOVERY-v2"
source_root="${artifact_root}/${source_rel}"
final_root="${artifact_root}/${target_rel}"
partial_root="${final_root}.partial"
expected_image="sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774"

[[ "$(docker image inspect "${project_image}" --format '{{.Id}}')" == "${expected_image}" ]] || { echo "project image identity mismatch" >&2; exit 2; }
[[ "$(git -C "${repo_root}" rev-parse HEAD)" == "${source_commit}" ]] || { echo "HEAD/source mismatch" >&2; exit 2; }
[[ -z "$(git -C "${repo_root}" status --porcelain=v1 --untracked-files=all)" ]] || { echo "clean committed worktree required" >&2; exit 2; }
[[ -d "${source_root}" && ! -L "${source_root}" ]] || { echo "closed v1 source missing" >&2; exit 2; }
[[ ! -e "${final_root}" && ! -e "${partial_root}" ]] || { echo "fresh add-once recovery namespace required" >&2; exit 2; }
mkdir -p "${partial_root}"

project_run() {
  docker run --rm --network none --entrypoint /opt/conda/bin/python \
    --user "$(id -u):$(id -g)" --cpus 8 --memory 32g --pids-limit 2048 \
    -e PYTHONDONTWRITEBYTECODE=1 -e MPLCONFIGDIR=/tmp/jbgs-mpl-cache \
    -v "${repo_root}:/workspace/JointBuildGS:ro" \
    -v "${artifact_root}:/artifacts/JointBuildGS:ro" \
    -v "${source_root}:/source:ro" -v "${partial_root}:/task:rw" \
    -w /workspace/JointBuildGS "${project_image}" \
    scripts/p2/selected10_c1_c4_presentation_v1/c1_c2_oracle.py "$@"
}

project_run inherit-closed-operations --output-root /task --source-root /source
project_run render-finalize --output-root /task --artifact-root /artifacts/JointBuildGS \
  --source-commit "${source_commit}" --run-id "${run_id}"
mv -- "${partial_root}" "${final_root}"
echo "selected10 C1/C2 oracle recovery-v2 complete without Roofer: ${final_root}"
