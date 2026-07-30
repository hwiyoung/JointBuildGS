#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
ARTIFACT_ROOT="${JBGS_ARTIFACT_ROOT:-${ROOT}/../JointBuildGS-artifacts}"
TOOLS_IMAGE=sha256:87bea02e5598a3d53a119b754191673497d52641bd8ea4106ffee653407579b0
COLMAP_IMAGE=sha256:f3fecec368989ea8d3ba7178416453c07419ff1b310c6df727e1b7efb8a3d4f2
TOOLS_IMAGE_ID="$(docker image inspect "${TOOLS_IMAGE}" --format '{{.Id}}')"
COLMAP_IMAGE_ID="$(docker image inspect "${COLMAP_IMAGE}" --format '{{.Id}}')"
timeout --signal=TERM 60m docker run --rm \
  --user "$(id -u):$(id -g)" \
  -e HOME=/tmp \
  -e FAIR_TOOLS_IMAGE_ID="${TOOLS_IMAGE_ID}" \
  -e FAIR_COLMAP_IMAGE_ID="${COLMAP_IMAGE_ID}" \
  -v "${ROOT}:/workspace/JointBuildGS" \
  -v "${ARTIFACT_ROOT}/fair-pilot:/workspace/JointBuildGS/fair-pilot" \
  -w /workspace/JointBuildGS \
  "${TOOLS_IMAGE}" \
  python3 scripts/experiments/fair_pilot/05_stats_candidates.py "$@"
