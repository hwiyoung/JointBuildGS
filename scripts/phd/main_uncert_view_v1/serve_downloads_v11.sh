#!/usr/bin/env bash
# Replace only this viewer's transport; retain both previous service snapshots.
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
TASK_ROOT=$(realpath "$REPO/../JointBuildGS-artifacts/phase-payloads/phd/main_uncert_view_v1/PHD-MAIN-UNCERT-VIEW-v1")
CURRENT=jbgs-main-uncert-view-8912
PREVIOUS=jbgs-main-uncert-view-8912-v11-simplehttp
CANDIDATE=jbgs-main-uncert-view-download-candidate
SERVER="$TASK_ROOT/delivery_server_v1/download_server.py"
test -s "$TASK_ROOT/web_v1_1/downloads/PHD-MAIN-UNCERT-VIEW-v1.1_report_and_screens.zip"
mkdir -p "$(dirname "$SERVER")"
if test -e "$SERVER"; then
  cmp "$REPO/scripts/phd/main_uncert_view_v1/download_server.py" "$SERVER"
else
  install -m 444 "$REPO/scripts/phd/main_uncert_view_v1/download_server.py" "$SERVER"
fi
if docker inspect "$CURRENT" --format '{{json .Config.Cmd}}' | rg -q '/server/download_server.py'; then
  curl --fail --silent --head http://127.0.0.1:8912/downloads/PHD-MAIN-UNCERT-VIEW-v1.1_results.zip | rg -q 'Accept-Ranges: bytes'
  exit 0
fi
test "$(docker inspect "$CURRENT" --format '{{range .Mounts}}{{if eq .Destination "/web"}}{{.Source}}{{end}}{{end}}')" = "$TASK_ROOT/web_v1_1"
docker inspect "$CURRENT" --format '{{json .Config.Cmd}}' | rg -q '"http.server"'
if docker inspect "$PREVIOUS" >/dev/null 2>&1; then
  echo 'Existing transport rollback container found; preserve it.' >&2
  exit 1
fi
docker create --name "$CANDIDATE" --restart unless-stopped --read-only \
  --user "$(id -u):$(id -g)" --cap-drop ALL --security-opt no-new-privileges \
  --cpus 2 --memory 512m --pids-limit 64 \
  -e CUDA_VISIBLE_DEVICES= -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONUNBUFFERED=1 \
  -p 0.0.0.0:8912:8080 -v "$TASK_ROOT/web_v1_1:/web:ro" \
  -v "$SERVER:/server/download_server.py:ro" -w /web \
  --entrypoint python jointbuildgs:dev /server/download_server.py --directory /web
rollback(){
  docker stop "$CURRENT" >/dev/null 2>&1 || true
  docker rename "$CURRENT" jbgs-main-uncert-view-download-failed >/dev/null 2>&1 || true
  docker rename "$PREVIOUS" "$CURRENT" >/dev/null 2>&1 || true
  docker start "$CURRENT" >/dev/null
  echo 'Previous v1.1 HTTP service restored after failed switch.' >&2
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
curl --fail --silent --head http://127.0.0.1:8912/downloads/PHD-MAIN-UNCERT-VIEW-v1.1_results.zip | rg -q 'Accept-Ranges: bytes'
trap - ERR
docker inspect "$CURRENT" --format '{{.Name}} {{.State.Status}} {{json .NetworkSettings.Ports}}'
