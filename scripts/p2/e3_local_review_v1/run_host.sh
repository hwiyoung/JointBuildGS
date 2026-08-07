#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
artifact_root="${JBGS_ARTIFACT_ROOT:-/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts}"
config="${repo_root}/configs/p2/e3_local_review_v1/building_4906982.json"
task_rel="phase-payloads/p2/e3_local_review_v1/P2-E3-LOCAL-4906982-INPUT-REVIEW-v3"
task_root="${artifact_root}/${task_rel}"
logs_root="${artifact_root}/phase-payloads/p2/e3_local_review_v1/logs"
port="8878"
container_name="jbgs-e3-local-review-8878"
mkdir -p "${logs_root}"

mode="${1:-build}"
if [[ "${mode}" != "build" && "${mode}" != "serve" ]]; then
  echo "usage: $0 [build|serve]" >&2
  exit 2
fi

docker run --rm --network none --shm-size 8g \
  --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -v "${repo_root}:/workspace/JointBuildGS:ro" \
  -v "${artifact_root}:/artifacts/JointBuildGS" \
  -w /workspace/JointBuildGS jointbuildgs:dev \
  python -B scripts/p2/e3_local_review_v1/build_review.py \
    --config /workspace/JointBuildGS/configs/p2/e3_local_review_v1/building_4906982.json \
    --repo-root /workspace/JointBuildGS \
    --artifact-root /artifacts/JointBuildGS \
  >"${logs_root}/build_review.log" 2>&1

tail -n 20 "${logs_root}/build_review.log"

if [[ "${mode}" == "serve" ]]; then
  if docker ps -a --format '{{.Names}}' | rg -Fxq "${container_name}"; then
    docker rm -f "${container_name}" >/dev/null
  fi
  if ss -ltn | rg -q ":${port}[[:space:]]"; then
    echo "port ${port} is already in use" >&2
    exit 1
  fi
  docker run -d --name "${container_name}" --restart unless-stopped \
    -p "${port}:8765" \
    -v "${task_root}/viewer:/viewer:ro" \
    -w /viewer jointbuildgs-p0-tools:t0 \
    python -B -m http.server 8765 --bind 0.0.0.0 --directory /viewer >/dev/null
  echo "viewer=http://127.0.0.1:${port}/"
fi
