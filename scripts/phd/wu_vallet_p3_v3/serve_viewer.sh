#!/usr/bin/env bash
set -euo pipefail
wv3_serve_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
wv3_serve_artifacts=$(realpath "$wv3_serve_repo/../JointBuildGS-artifacts")
wv3_serve_run=${1:-PHD-WU-VALLET-P3-VIEWER-v3}
wv3_serve_root="$wv3_serve_artifacts/phase-payloads/phd/wu_vallet_p3_v3/$wv3_serve_run/run"
test -f "$wv3_serve_root/viewer_manifest.json"
if [[ -n $(ss -H -ltn 'sport = :8899') ]]; then
  echo 'Port 8899 is occupied; existing service preserved' >&2
  exit 1
fi
wv3_serve_image=$(docker image inspect jointbuildgs:dev --format '{{.Id}}')
docker run -d --name jbgs-wu-vallet-p3-forensic-viewer-8899 --restart unless-stopped \
  --read-only --cpus 1 --memory 512m -p 127.0.0.1:8899:8080 \
  --mount "type=bind,src=$wv3_serve_root,dst=/srv,readonly" --workdir /srv \
  --entrypoint python "$wv3_serve_image" -m http.server 8080 --bind 0.0.0.0
printf '%s\n' 'http://127.0.0.1:8899/'
