#!/usr/bin/env bash
set -euo pipefail
audit_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
audit_source="$audit_repo/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1"
audit_output="$audit_repo/docs/experiments/phd/geogs_causal_followup_v1"
audit_image=jointbuildgs:geogs-official-db40c95-compat-v1
audit_image_id=$(docker image inspect "$audit_image" --format '{{.Id}}')
mkdir -p "$audit_output"
test ! -e "$audit_output/analysis/control_audit"
docker run --rm --read-only --network none --cpus 1 --memory 256m -w /tmp \
  --tmpfs /tmp:rw,size=16m --user "$(id -u):$(id -g)" \
  -v "$audit_repo:/workspace:ro" -v "$audit_source:/source:ro" -v "$audit_output:/output:rw" \
  --entrypoint python "$audit_image" /workspace/scripts/phd/geogs_causal_followup_v1/control_audit.py \
  --source /source --output /output/analysis/control_audit \
  --config /workspace/configs/phd/geogs_causal_followup_v1/control_audit.json --image-id "$audit_image_id"
