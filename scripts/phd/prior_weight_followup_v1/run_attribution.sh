#!/usr/bin/env bash
set -euo pipefail
JBGS_REPO=$(cd "$(dirname "$0")/../../.." && pwd)
JBGS_ARTIFACTS=$(cd "$JBGS_REPO/../JointBuildGS-artifacts" && pwd)
JBGS_PHDPAYLOAD="$JBGS_ARTIFACTS/phase-payloads/phd"
JBGS_DIAG_PARENT="$JBGS_PHDPAYLOAD/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1/viewer_rgb_v1/mechanism_diagnostic_v1"
mkdir -p "$JBGS_DIAG_PARENT"
JBGS_DIAG_OUT=$(mktemp -d "$JBGS_DIAG_PARENT/attempt.XXXXXXXX")
printf '%s\n' "$JBGS_DIAG_OUT" > /tmp/jbgs_render_attribution.txt
cp "$JBGS_REPO/configs/phd/region_weight_v1/render_attribution_v1.json" "$JBGS_DIAG_OUT/config.json"
cp "$JBGS_REPO/scripts/phd/prior_weight_followup_v1/render_attribution.py" "$JBGS_DIAG_OUT/render_attribution.py"
cp "$0" "$JBGS_DIAG_OUT/run_attribution.sh"
git -C "$JBGS_REPO" rev-parse HEAD > "$JBGS_DIAG_OUT/repository_commit.txt"
printf '%s\n' "$JBGS_DIAG_OUT"
docker run --rm --gpus '"device=1"' --network none --cpus 2 --memory 10g --user "$(id -u):$(id -g)" \
  -e LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6 -e OPENBLAS_NUM_THREADS=2 -e OMP_NUM_THREADS=2 \
  -e PYTHONDONTWRITEBYTECODE=1 -e MPLCONFIGDIR=/tmp/matplotlib \
  -v "$JBGS_PHDPAYLOAD:/payload:ro" -v "$JBGS_ARTIFACTS:/artifacts:ro" -v "$JBGS_REPO:/repo:ro" \
  -v "$JBGS_DIAG_OUT:/out" sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e \
  python /out/render_attribution.py > "$JBGS_DIAG_OUT/run.log" 2>&1
