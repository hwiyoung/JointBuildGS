#!/usr/bin/env bash
set -euo pipefail
JBGS_REPO=$(cd "$(dirname "$0")/../../.." && pwd)
JBGS_TASK=$(cd "$JBGS_REPO/../JointBuildGS-artifacts/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1" && pwd)
JBGS_NAME=jbgs-geogs-rgb-viewer-7593-compat
if docker inspect "$JBGS_NAME" >/dev/null 2>&1; then
  test "$(docker inspect "$JBGS_NAME" --format '{{.State.Running}}')" = true
  test "$(docker inspect "$JBGS_NAME" --format '{{index .Config.Labels "jbgs.viewer.alias"}}')" = 8910
else
  docker run -d --name "$JBGS_NAME" --restart unless-stopped --runtime runc \
    --read-only --cpus 1 --memory 512m --user "$(id -u):$(id -g)" \
    --label jbgs.viewer.alias=8910 -e NVIDIA_VISIBLE_DEVICES=void -e PYTHONDONTWRITEBYTECODE=1 \
    -p 127.0.0.1:7593:8080 \
    -v "$JBGS_REPO/src/apps/geogs_rgb_comparison_v1:/app:ro" \
    -v "$JBGS_REPO/src/apps/gs3d_4way_viewer/build/three.module.min.js:/vendor/three.module.min.js:ro" \
    -v "$JBGS_REPO/scripts/phd/geogs_mvs_pgsr_v1/viewer/serve.py:/serve.py:ro" \
    -v "$JBGS_TASK/viewer_rgb_v1:/data:ro" -v "$JBGS_TASK/evaluation:/results/evaluation:ro" \
    sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e python /serve.py
fi
