#!/usr/bin/env bash
set -euo pipefail
wv5_serve_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
wv5_serve_artifacts=$(realpath "$wv5_serve_repo/../JointBuildGS-artifacts")
wv5_serve_run=${1:-PHD-WU-VALLET-MATCHED-VIEWER-v5}
wv5_serve_root="$wv5_serve_artifacts/phase-payloads/phd/wu_vallet_matched_v5/$wv5_serve_run/run"
test -f "$wv5_serve_root/viewer_manifest.json"
if [[ -n $(ss -H -ltn 'sport = :8901') ]]; then
  echo 'Port 8901 is occupied; existing service preserved' >&2
  exit 1
fi
wv5_serve_image=sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774
docker image inspect "$wv5_serve_image" >/dev/null
docker run -d --name jbgs-wu-vallet-matched-comparison-viewer-8901 --restart unless-stopped \
  --read-only --cpus 1 --memory 512m -p 127.0.0.1:8901:8080 \
  --mount "type=bind,src=$wv5_serve_root,dst=/srv,readonly" --workdir /srv \
  --entrypoint python "$wv5_serve_image" -m http.server 8080 --bind 0.0.0.0
printf '%s\n' 'http://127.0.0.1:8901/'
