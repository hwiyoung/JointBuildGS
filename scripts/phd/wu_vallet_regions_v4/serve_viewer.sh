#!/usr/bin/env bash
set -euo pipefail
wv4_serve_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
wv4_serve_artifacts=$(realpath "$wv4_serve_repo/../JointBuildGS-artifacts")
wv4_serve_run=${1:-PHD-WU-VALLET-REGIONS-VIEWER-v4-r2}
wv4_serve_root="$wv4_serve_artifacts/phase-payloads/phd/wu_vallet_regions_v4/$wv4_serve_run/run"
test -f "$wv4_serve_root/viewer_manifest.json"
if [[ -n $(ss -H -ltn 'sport = :8900') ]]; then
  echo 'Port 8900 is occupied; existing service preserved' >&2
  exit 1
fi
wv4_serve_image=$(docker image inspect jointbuildgs:dev --format '{{.Id}}')
docker run -d --name jbgs-wu-vallet-regions-comparison-viewer-8900 --restart unless-stopped \
  --read-only --cpus 1 --memory 512m -p 127.0.0.1:8900:8080 \
  --mount "type=bind,src=$wv4_serve_root,dst=/srv,readonly" --workdir /srv \
  --entrypoint python "$wv4_serve_image" -m http.server 8080 --bind 0.0.0.0
printf '%s\n' 'http://127.0.0.1:8900/'
