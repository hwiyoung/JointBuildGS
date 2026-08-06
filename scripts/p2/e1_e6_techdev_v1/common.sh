#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
artifact_root="${JBGS_ARTIFACT_ROOT:-/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts}"
task_rel="phase-payloads/p2/e1_e6_techdev_v1/P2-E1-E6-PRIOR-FUSION-TECHDEV-v1"
task_root="${artifact_root}/${task_rel}"
prep_root="${task_root}/prep"
logs_root="${task_root}/logs"
dev_image="jointbuildgs:dev"
tools_image="jointbuildgs-p0-tools:t0"

mkdir -p "${prep_root}" "${logs_root}"

run_tools() {
  docker run --rm --network none \
    --user "$(id -u):$(id -g)" \
    -v "${repo_root}:/workspace/JointBuildGS:ro" \
    -v "${artifact_root}:/artifacts/JointBuildGS" \
    -w /workspace/JointBuildGS "${tools_image}" "$@"
}

run_dev() {
  docker run --rm --network none --shm-size 16g \
    --user "$(id -u):$(id -g)" \
    -e HOME=/tmp \
    -v "${repo_root}:/workspace/JointBuildGS:ro" \
    -v "${artifact_root}:/artifacts/JointBuildGS" \
    -w /workspace/JointBuildGS "${dev_image}" "$@"
}
