#!/usr/bin/env bash
# Isolated, persistent static hosting. Only this task's web directory is exposed.
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
TASK_WEB=$(realpath "$REPO/../JointBuildGS-artifacts/phase-payloads/phd/main_uncert_view_v1/PHD-MAIN-UNCERT-VIEW-v1/web")
CONTAINER=jbgs-main-uncert-view-8912
if docker container inspect "$CONTAINER" >/dev/null 2>&1; then
  docker inspect --format '{{.Name}} {{.State.Status}} {{json .NetworkSettings.Ports}}' "$CONTAINER"
  exit 0
fi
exec docker run -d --name "$CONTAINER" --restart unless-stopped --read-only \
  --user "$(id -u):$(id -g)" --cap-drop ALL --security-opt no-new-privileges \
  --cpus 2 --memory 512m --pids-limit 64 \
  -e CUDA_VISIBLE_DEVICES= -e PYTHONDONTWRITEBYTECODE=1 \
  -p 0.0.0.0:8912:8080 -v "$TASK_WEB:/web:ro" -w /web \
  --entrypoint python jointbuildgs:dev -m http.server 8080 --bind 0.0.0.0 --directory /web
