#!/usr/bin/env bash
# PHD-MAIN-BASE151-v1: DA3 depth of one cell's training views with the unchanged FIX geogs_da3_fix.py (--rule consec12 --save),
# jointbuildgs:geogs-da3-3d835ec-v1, GPU 1 only, network off; the FIX mounts with /scene = the GeoGS LoD2 cell scene (images, sparse/0),
# /split.json = the cell split, /out = OUT/da3 (-> OUT/da3/geogs/cell<k>/da3_prior_consec12).
#   bash run_da3.sh <cell>       (the caller holds the queue: control/HOLD_GPU)
# scientific_verdict: null
set -uo pipefail
W=$(cd "$(dirname "$0")/../../.." && pwd); ART=$(realpath "$W/../JointBuildGS-artifacts"); PH="$ART/phase-payloads/phd"
EXP=$(realpath "$W/../JointBuildGS-exp"); OUT="$PH/main_base151_v1/PHD-MAIN-BASE151-v1"; T="$PH/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1"
k=$1; mkdir -p "$OUT/da3"
docker run --rm --name "jbgs-b151-da3-cell$k" --gpus device=1 --network none --user "$(id -u):$(id -g)" --cpus 8 --memory 32g --shm-size 2g \
  -e PYTHONUNBUFFERED=1 -e PYTHONDONTWRITEBYTECODE=1 -e HOME=/tmp -e HF_HUB_OFFLINE=1 \
  -v "$T/sources/DA3NESTED-GIANT-LARGE:/model:ro" -v "$T/sources/GeoGS/preprocessing/get_da3_depth_with_colmap.py:/official.py:ro" \
  -v "$OUT/scenes/GeoGS_LoD2/cell$k:/scene:ro" -v "$OUT/scenes/GeoGS_LoD2/cell$k/split.json:/split.json:ro" -v "$OUT/da3:/out" \
  -v "$EXP/scripts/phd/main_fix_v1:/fixs:ro" -w /fixs --entrypoint python jointbuildgs:geogs-da3-3d835ec-v1 \
  geogs_da3_fix.py "cell$k" --rule consec12 --save --mem_fraction 0.95 > "$OUT/logs/da3_cell$k.log" 2>&1
echo "$(date '+%F %T') da3 cell$k rc=$?" | tee -a "$OUT/logs/da3.log"
