#!/usr/bin/env bash
set -euo pipefail
audit_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
audit_source="$audit_repo/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1"
audit_output="$audit_repo/docs/experiments/phd/geogs_expectation_audit_v1"
audit_image=jointbuildgs:geogs-official-db40c95-compat-v1
audit_image_id=$(docker image inspect "$audit_image" --format '{{.Id}}')
audit_commit=$(git -C "$audit_repo" rev-parse HEAD)
mkdir -p "$audit_output"
test ! -e "$audit_output/analysis"
docker run --rm --read-only --network none --cpus 2 --memory 2g -w /tmp \
  --tmpfs /tmp:rw,size=64m --user "$(id -u):$(id -g)" -e OPENBLAS_NUM_THREADS=1 \
  -v "$audit_repo:/workspace:ro" -v "$audit_source:/source:ro" -v "$audit_output:/output:rw" \
  --entrypoint python "$audit_image" /workspace/scripts/phd/geogs_expectation_audit_v1/audit.py \
  --source /source --output /output/analysis --config /workspace/configs/phd/geogs_expectation_audit_v1/audit.json \
  --image-id "$audit_image_id" --git-commit "$audit_commit"
