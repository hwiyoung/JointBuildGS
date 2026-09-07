#!/usr/bin/env bash
set -euo pipefail
p3_serve_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
p3_serve_artifacts=$(realpath "$p3_serve_repo/../JointBuildGS-artifacts")
p3_serve_version=${1:-PHD-WU-VALLET-P3-VIEWER-v1-r2}
p3_serve_root="$p3_serve_artifacts/phase-payloads/phd/wu_vallet_p3_v1/$p3_serve_version/viewer"
test -f "$p3_serve_root/viewer_manifest.json"
if [[ -n $(ss -H -ltn 'sport = :8897') ]]; then
 echo 'Port 8897 is occupied; existing service preserved' >&2
 exit 1
fi
p3_serve_image=$(docker image inspect jointbuildgs:dev --format '{{.Id}}')
docker run -d --name jbgs-wu-vallet-p3-viewer-8897 --restart unless-stopped \
 --read-only --cpus 1 --memory 512m -p 127.0.0.1:8897:8080 \
 --mount "type=bind,src=$p3_serve_root,dst=/srv,readonly" --workdir /srv \
 --entrypoint python "$p3_serve_image" -m http.server 8080 --bind 0.0.0.0
printf '%s\n' 'http://127.0.0.1:8897/'
