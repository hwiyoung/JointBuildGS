#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
ARTIFACT_ROOT="${JBGS_ARTIFACT_ROOT:-${ROOT}/../JointBuildGS-artifacts}"
TOOLS_IMAGE=sha256:87bea02e5598a3d53a119b754191673497d52641bd8ea4106ffee653407579b0
timeout --signal=TERM 60m docker run --rm \
  --user "$(id -u):$(id -g)" \
  -e HOME=/tmp \
  -v "${ROOT}:/workspace/JointBuildGS" \
  -v "${ARTIFACT_ROOT}/fair-pilot:/workspace/JointBuildGS/fair-pilot" \
  -v "${ARTIFACT_ROOT}/phase-payloads/p0-audit/data:/workspace/JointBuildGS/phases/p0-audit/data:ro" \
  -w /workspace/JointBuildGS \
  "${TOOLS_IMAGE}" \
  python3 scripts/fair_pilot/03_prepare_area3.py "$@"
