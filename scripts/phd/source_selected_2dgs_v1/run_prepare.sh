#!/usr/bin/env bash
set -euo pipefail
attempt=${1:?absolute new attempt path}
repo=$(cd "$(dirname "$0")/../../.." && pwd)
art=$(realpath -e "$repo/../JointBuildGS-artifacts")
parent="$art/phase-payloads/phd/mvs_surface_update_v1/PHD-MVS-SURFACE-UPDATE-v1/attempt_20260914T162810Z_5j6JQY"
evidence="$art/phase-payloads/phd/mvs_evidence_v1/PHD-MVS-EVIDENCE-v1/attempt_20260914T144906Z_OBsE9y/evidence"
base="$art/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1"
mvs="$art/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1/inputs_v2"
test ! -e "$attempt/prepared"
printf 'PREPARING_INPUTS\n' > "$attempt/status.txt"
docker run --rm --network none --cpus 4 --memory 16g --memory-swap 16g \
  --user "$(id -u):$(id -g)" --entrypoint python -e PYTHONPATH=/repo \
  -e PYTHONDONTWRITEBYTECODE=1 -e OPENBLAS_NUM_THREADS=1 -e OMP_NUM_THREADS=4 -e MPLCONFIGDIR=/tmp/mpl \
  -v "$repo:/repo:ro" -v "$parent:/parent:ro" -v "$evidence:/evidence:ro" \
  -v "$base/inputs:/inputs:ro" -v "$mvs:/mvs:ro" -v "$base/contracts/execution_v1.json:/base_config.json:ro" \
  -v "$attempt:/attempt" \
  sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774 \
  /repo/scripts/phd/source_selected_2dgs_v1/prepare.py \
  --config /repo/configs/phd/source_selected_2dgs_v1/experiment.json \
  --primary /parent/prepare_v2 --screen /parent/prepare_screen --evidence /evidence \
  --inputs /inputs --mvs /mvs --base-config /base_config.json --output /attempt/prepared \
  2>&1 | tee "$attempt/preparation.log"
printf 'PREPARED\n' > "$attempt/status.txt"
