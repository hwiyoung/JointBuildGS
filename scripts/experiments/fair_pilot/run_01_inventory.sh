#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
ARTIFACT_ROOT="${JBGS_ARTIFACT_ROOT:-${ROOT}/../JointBuildGS-artifacts}"
DEV_IMAGE=sha256:926b2fd5e31d9f22d44db347b703ed1acfe0a98d19c189c80324daec63fd6396
timeout --signal=TERM 30m docker run --rm \
  --user "$(id -u):$(id -g)" \
  -e HOME=/tmp \
  -v "${ROOT}:/workspace/JointBuildGS" \
  -v "${ARTIFACT_ROOT}/fair-pilot:/workspace/JointBuildGS/fair-pilot" \
  -v "${ARTIFACT_ROOT}/phase-payloads/p0-audit/data:/workspace/JointBuildGS/phases/p0-audit/data:ro" \
  -w /workspace/JointBuildGS \
  "${DEV_IMAGE}" \
  python scripts/experiments/fair_pilot/01_inventory.py "$@"
