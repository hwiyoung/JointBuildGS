#!/usr/bin/env bash
set -euo pipefail
JBGS_REPO=$(cd "$(dirname "$0")/../../.." && pwd)
JBGS_ARTIFACTS=$(cd "$JBGS_REPO/../JointBuildGS-artifacts" && pwd)
JBGS_PHDPAYLOAD="$JBGS_ARTIFACTS/phase-payloads/phd"
JBGS_DIAG_PARENT="$JBGS_PHDPAYLOAD/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1/viewer_rgb_v1/depth_evidence_stage2_v1"
mkdir -p "$JBGS_DIAG_PARENT"
JBGS_DIAG_OUT=$(mktemp -d "$JBGS_DIAG_PARENT/attempt.XXXXXXXX")
printf '%s\n' "$JBGS_DIAG_OUT" > /tmp/jbgs_depth_evidence.txt
cp "$JBGS_REPO/configs/phd/region_weight_v1/depth_evidence_stage2_v1.json" "$JBGS_DIAG_OUT/config.json"
cp "$JBGS_REPO/scripts/phd/prior_weight_followup_v1/build_depth_evidence.py" "$JBGS_DIAG_OUT/build_depth_evidence.py"
cp "$0" "$JBGS_DIAG_OUT/run_depth_evidence.sh"
git -C "$JBGS_REPO" rev-parse HEAD > "$JBGS_DIAG_OUT/repository_commit.txt"
printf '%s\n' "$JBGS_DIAG_OUT"
docker run --rm --runtime runc --network none --cpus 2 --memory 6g --user "$(id -u):$(id -g)" \
 -e NVIDIA_VISIBLE_DEVICES=void -e LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6 \
 -e PYTHONDONTWRITEBYTECODE=1 -e OPENBLAS_NUM_THREADS=2 -e OMP_NUM_THREADS=2 -e MPLCONFIGDIR=/tmp/matplotlib \
 -v "$JBGS_PHDPAYLOAD:/payload:ro" -v "$JBGS_REPO:/repo:ro" \
 -v "$JBGS_ARTIFACTS/phase-payloads/p0-audit/data/work/mvs/colmap_dense:/dense:ro" \
 -v "$JBGS_DIAG_OUT:/out" sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e \
 python /out/build_depth_evidence.py > "$JBGS_DIAG_OUT/run.log" 2>&1
