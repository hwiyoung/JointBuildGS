#!/usr/bin/env bash
set -euo pipefail
attempt=${1:?absolute attempt path}
config=${2:-configs/phd/mvs_surface_update_v1/experiment.json}
output_name=${3:-prepare_v2}
repo=$(cd "$(dirname "$0")/../../.." && pwd)
art="$repo/../JointBuildGS-artifacts/phase-payloads/phd"
base="$art/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1"
evidence="$art/mvs_evidence_v1/PHD-MVS-EVIDENCE-v1/attempt_20260914T144906Z_OBsE9y/evidence"
mvs="$art/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1/inputs_v2"
test ! -e "$attempt/$output_name"
docker run --rm --network none --cpus 4 --memory 24g --memory-swap 24g \
  --user "$(id -u):$(id -g)" --entrypoint /opt/geogs/bin/python \
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/repo -e MPLCONFIGDIR=/tmp/mpl \
  -e OPENBLAS_NUM_THREADS=1 -e OMP_NUM_THREADS=4 \
  -v "$repo:/repo:ro" -v "$base:/base:ro" -v "$evidence:/evidence:ro" \
  -v "$mvs:/mvs:ro" -v "$attempt:/attempt" \
  sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e \
  /repo/scripts/phd/mvs_surface_update_v1/prepare.py --base /base --inputs /base/inputs \
  --evidence /evidence --mvs /mvs --output "/attempt/$output_name" --config "/repo/$config" \
  2>&1 | tee "$attempt/${output_name}.log"
