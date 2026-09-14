#!/usr/bin/env bash
set -euo pipefail
repo=$(cd "$(dirname "$0")/../../.." && pwd)
artifact_root=$(cd "$repo/../JointBuildGS-artifacts" && pwd)
output_root="$artifact_root/phase-payloads/phd/mvs_evidence_v1/PHD-MVS-EVIDENCE-v1"
mkdir -p "$output_root"
attempt=$(mktemp -d "$output_root/attempt_$(date -u +%Y%m%dT%H%M%SZ)_XXXXXX")
image_id=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
printf '%s\n' "$attempt" > "$attempt/host_output.txt"
docker run --rm --network none --cpus 4 --memory 12g --memory-swap 12g \
  --user "$(id -u):$(id -g)" --entrypoint /opt/geogs/bin/python \
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/repo -e MPLCONFIGDIR=/tmp/matplotlib \
  -e OPENBLAS_NUM_THREADS=1 -e OMP_NUM_THREADS=1 -e JBGS_RUNTIME_IMAGE_ID="$image_id" \
  -v "$repo:/repo:ro" \
  -v "$artifact_root/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/inputs:/inputs:ro" \
  -v "$artifact_root/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1/inputs_v2:/mvs:ro" \
  -v "$attempt:/out" -w /repo "$image_id" \
  scripts/phd/mvs_evidence_v1/build.py --config /repo/configs/phd/mvs_evidence_v1/diagnostic.json \
  --inputs /inputs --mvs /mvs --output /out/evidence 2>&1 | tee "$attempt/run.log"
printf '%s\n' "$attempt/evidence"
