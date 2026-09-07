#!/usr/bin/env bash
# Kill-condition diagnostics for PHD-GEOGS-P1P2P3-v1 (evaluation-only use of the frozen UAS reference; no training).
# Usage: bash scripts/phd/geogs_p1p2p3_v1/analysis/killtest_v1/run_killtest.sh <artifact_root> <out_dir>
set -euo pipefail
A=${1:?artifact root (host path to JointBuildGS-artifacts)}; OUT=${2:?output dir}
T=/a/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1
FP=/a/phase-payloads/p0-audit/data/work/footprints/lod2_ground_plan.geojson
REFD=/a/phase-payloads/phd/wu_vallet_regions_v4/PHD-WU-VALLET-REGIONS-EVALUATION-v4/run
HERE=$(cd "$(dirname "$0")" && pwd); mkdir -p "$OUT"
run() { docker run --rm --entrypoint python -v "$A:/a:ro" -v "$HERE:/s:ro" -v "$OUT:/out" -w /s -e OMP_NUM_THREADS=4 --memory=20g jointbuildgs:dev "$@"; }
for R in P1 P2 P3; do
  run zone_f1.py $R $T $FP /out
  run depth_triplet.py $R $T $REFD/$R/reference.npz /out
  run da3_audit.py $R $T $REFD/$R/reference.npz $FP /out
done
run ground_candidate.py P1 $T $FP /out; run ground_candidate.py P2 $T $FP /out
run kb_good_views.py P2 $T $REFD/P2/reference.npz $FP /out 0,1
run kb_good_views.py P3 $T $REFD/P3/reference.npz $FP /out 0,16
