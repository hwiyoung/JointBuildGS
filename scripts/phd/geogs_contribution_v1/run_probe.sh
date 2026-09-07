#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
audit_root="$(cd "$repo_root/../JointBuildGS-artifacts/phase-payloads/phd/geogs_contribution_v1/PHD-GEOGS-CONTRIBUTION-v1" && pwd)"
docker run --rm --network none --read-only --tmpfs /tmp --cpus 2 --memory 4g \
  --user "$(id -u):$(id -g)" --entrypoint python \
  -e MPLCONFIGDIR=/tmp/matplotlib -e OMP_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1 \
  -v "$repo_root:/workspace:ro" -v "$audit_root:/audit:rw" \
  -w /workspace jointbuildgs:dev \
  scripts/phd/geogs_contribution_v1/probe.py \
  --config configs/phd/geogs_contribution_v1/probe_v1.json
