#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
ARTIFACT_ROOT="${JBGS_ARTIFACT_ROOT:-${ROOT}/../JointBuildGS-artifacts}"
COLMAP_IMAGE=sha256:f3fecec368989ea8d3ba7178416453c07419ff1b310c6df727e1b7efb8a3d4f2
DEV_IMAGE=sha256:926b2fd5e31d9f22d44db347b703ed1acfe0a98d19c189c80324daec63fd6396
COLMAP_IMAGE_ID="$(docker image inspect "${COLMAP_IMAGE}" --format '{{.Id}}')"
docker_rc=0
timeout --signal=TERM 240m docker run --rm \
  --user "$(id -u):$(id -g)" \
  --gpus '"device=1"' \
  -e HOME=/tmp \
  -v "${ROOT}:/workspace/JointBuildGS" \
  -v "${ARTIFACT_ROOT}/fair-pilot:/workspace/JointBuildGS/fair-pilot" \
  -w /workspace/JointBuildGS \
  "${COLMAP_IMAGE}" \
  bash scripts/fair_pilot/04_colmap_mvs_container.sh "$@" || docker_rc="$?"

docker run --rm \
  --user "$(id -u):$(id -g)" \
  -e HOME=/tmp \
  -e FAIR_COLMAP_IMAGE_ID="${COLMAP_IMAGE_ID}" \
  -v "${ROOT}:/workspace/JointBuildGS" \
  -v "${ARTIFACT_ROOT}/fair-pilot:/workspace/JointBuildGS/fair-pilot" \
  -w /workspace/JointBuildGS \
  "${DEV_IMAGE}" \
  python scripts/fair_pilot/04_finalize_mvs.py "$@"

exit "${docker_rc}"
