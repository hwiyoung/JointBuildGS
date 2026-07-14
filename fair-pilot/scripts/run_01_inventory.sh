#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEV_IMAGE=sha256:926b2fd5e31d9f22d44db347b703ed1acfe0a98d19c189c80324daec63fd6396
timeout --signal=TERM 30m docker run --rm \
  --user "$(id -u):$(id -g)" \
  -e HOME=/tmp \
  -v "${ROOT}:/workspace/JointBuildGS" \
  -w /workspace/JointBuildGS \
  "${DEV_IMAGE}" \
  python fair-pilot/scripts/01_inventory.py "$@"
