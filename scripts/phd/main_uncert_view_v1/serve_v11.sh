#!/usr/bin/env bash
# Switch only this viewer, retaining the stopped v1 container and all v1 bytes.
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
TASK_WEB=$(realpath "$REPO/../JointBuildGS-artifacts/phase-payloads/phd/main_uncert_view_v1/PHD-MAIN-UNCERT-VIEW-v1/web_v1_1")
CURRENT=jbgs-main-uncert-view-8912
PREVIOUS=jbgs-main-uncert-view-8912-v1
CANDIDATE=jbgs-main-uncert-view-v11-candidate
test -s "$TASK_WEB/view_v11.js"
if docker inspect "$CURRENT" --format '{{range .Mounts}}{{.Source}}{{end}}' 2>/dev/null | rg -q '/web_v1_1$'; then
  curl --fail --silent --output /dev/null http://127.0.0.1:8912/view_v11.js
  docker inspect "$CURRENT" --format '{{.Name}} {{.State.Status}}'
  exit 0
fi
docker inspect "$CURRENT" --format '{{range .Mounts}}{{.Source}}{{end}}' | rg -q '/PHD-MAIN-UNCERT-VIEW-v1/web$'
if docker inspect "$PREVIOUS" >/dev/null 2>&1; then
  echo 'Existing rollback container found; preserve it and inspect before switching.' >&2
  exit 1
fi
docker create --name "$CANDIDATE" --restart unless-stopped --read-only \
  --user "$(id -u):$(id -g)" --cap-drop ALL --security-opt no-new-privileges \
  --cpus 2 --memory 512m --pids-limit 64 \
  -e CUDA_VISIBLE_DEVICES= -e PYTHONDONTWRITEBYTECODE=1 \
  -p 0.0.0.0:8912:8080 -v "$TASK_WEB:/web:ro" -w /web \
  --entrypoint python jointbuildgs:dev -m http.server 8080 --bind 0.0.0.0 --directory /web
rollback(){
  docker stop "$CURRENT" >/dev/null 2>&1 || true
  docker rename "$CURRENT" jbgs-main-uncert-view-v11-failed >/dev/null 2>&1 || true
  docker rename "$PREVIOUS" "$CURRENT" >/dev/null 2>&1 || true
  docker start "$CURRENT" >/dev/null
  echo 'v1 restored after failed v1.1 switch' >&2
}
docker stop "$CURRENT" >/dev/null
docker rename "$CURRENT" "$PREVIOUS"
trap rollback ERR
docker rename "$CANDIDATE" "$CURRENT"
docker start "$CURRENT"
for attempt in 1 2 3 4 5; do
  if curl --fail --silent --output /dev/null http://127.0.0.1:8912/view_v11.js; then break; fi
  sleep 1
done
curl --fail --silent --output /dev/null http://127.0.0.1:8912/view_v11.js
trap - ERR
docker inspect "$CURRENT" --format '{{.Name}} {{.State.Status}} {{json .NetworkSettings.Ports}}'
