#!/usr/bin/env bash
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
TASK_ROOT=$(realpath "$REPO/../JointBuildGS-artifacts/phase-payloads/phd/main_uncert_view_v1/PHD-MAIN-UNCERT-VIEW-v1")
WEB="$TASK_ROOT/web_mvs_v1_2"
CURRENT=jbgs-main-uncert-view-8912
PREVIOUS=jbgs-main-uncert-view-8912-v11-downloads
CANDIDATE=jbgs-main-uncert-mvs-v12-candidate
test -s "$WEB/downloads/PHD-MAIN-UNCERT-VIEW-v1.2_results.zip"
test "$(docker inspect "$CURRENT" --format '{{range .Mounts}}{{if eq .Destination "/web"}}{{.Source}}{{end}}{{end}}')" = "$TASK_ROOT/web_v1_1"
if docker inspect "$PREVIOUS" >/dev/null 2>&1; then
  echo 'Existing v1.1 rollback container found; preserve it.' >&2
  exit 1
fi
docker create --name "$CANDIDATE" --restart unless-stopped --read-only \
  --user "$(id -u):$(id -g)" --cap-drop ALL --security-opt no-new-privileges \
  --cpus 2 --memory 512m --pids-limit 64 -e CUDA_VISIBLE_DEVICES= \
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONUNBUFFERED=1 \
  -p 0.0.0.0:8912:8080 -v "$WEB:/web:ro" \
  -v "$TASK_ROOT/delivery_server_v1/download_server.py:/server/download_server.py:ro" \
  -w /web --entrypoint python jointbuildgs:dev /server/download_server.py --directory /web
rollback(){
  docker stop --timeout 1 "$CURRENT" >/dev/null 2>&1 || true
  docker rename "$CURRENT" jbgs-main-uncert-mvs-v12-failed >/dev/null 2>&1 || true
  docker rename "$PREVIOUS" "$CURRENT" >/dev/null 2>&1 || true
  docker start "$CURRENT" >/dev/null
  echo 'Previous v1.1 service restored.' >&2
}
docker stop --timeout 3 "$CURRENT" >/dev/null
docker rename "$CURRENT" "$PREVIOUS"
trap rollback ERR
docker rename "$CANDIDATE" "$CURRENT"
docker start "$CURRENT"
for attempt in 1 2 3 4 5; do
  if curl --fail --silent --output /dev/null http://127.0.0.1:8912/geometry_mvs.js; then break; fi
  sleep 1
done
curl --fail --silent --head http://127.0.0.1:8912/downloads/PHD-MAIN-UNCERT-VIEW-v1.2_results.zip | rg -q 'Accept-Ranges: bytes'
trap - ERR
docker inspect "$CURRENT" --format '{{.Name}} {{.State.Status}} {{json .NetworkSettings.Ports}}'
