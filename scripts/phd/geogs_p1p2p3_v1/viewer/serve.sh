#!/usr/bin/env bash
set -euo pipefail
geogs_view_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../../.." && pwd)
geogs_view_task=$(realpath "$geogs_view_repo/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1")
geogs_view_port=${1:-8902}
geogs_view_manifest=${2:-evaluation/viewer/manifest.json}
geogs_view_name="jbgs-geogs-p1p2p3-viewer-$geogs_view_port"
test -f "$geogs_view_task/$geogs_view_manifest"
if [[ -n $(ss -H -ltn "sport = :$geogs_view_port") ]]; then
  echo "Port $geogs_view_port is occupied; existing service preserved" >&2
  exit 1
fi
geogs_view_image=$(docker image inspect jointbuildgs:geogs-official-db40c95-compat-v1 --format '{{.Id}}')
docker run -d --name "$geogs_view_name" --read-only --cpus 1 --memory 512m \
  --publish "127.0.0.1:$geogs_view_port:8080" \
  --mount "type=bind,src=$geogs_view_repo/src/apps/geogs_p1p2p3_v1,dst=/app,readonly" \
  --mount "type=bind,src=$geogs_view_repo/src/apps/gs3d_4way_viewer/build/three.module.min.js,dst=/three/three.module.min.js,readonly" \
  --mount "type=bind,src=$geogs_view_task,dst=/task,readonly" \
  --mount "type=bind,src=$geogs_view_repo/scripts/phd/geogs_p1p2p3_v1/viewer/serve.py,dst=/serve.py,readonly" \
  --workdir /app --entrypoint /opt/geogs/bin/python "$geogs_view_image" /serve.py
printf '%s\n' "http://127.0.0.1:$geogs_view_port/app/index.html?manifest=/task/$geogs_view_manifest"
