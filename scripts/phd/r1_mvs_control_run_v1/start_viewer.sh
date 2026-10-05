#!/usr/bin/env bash
set -euo pipefail
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
artifact_root=$(realpath "$repo_root/../JointBuildGS-artifacts")
attempt=${1:?absolute active run attempt}
test -s "$attempt/authorization.txt"
test -z "$(ss -H -ltn 'sport = :8912')"
viewer="$attempt/viewer"
mkdir "$viewer"
mkdir "$viewer/source" "$viewer/data"
cp "$repo_root/scripts/phd/r1_mvs_control_run_v1/publish.py" "$viewer/source/"
cp "$repo_root/scripts/phd/geogs_mvs_pgsr_v1/viewer/export_geometry.py" "$repo_root/scripts/phd/geogs_mvs_pgsr_v1/viewer/serve.py" "$viewer/source/"
cp -a "$repo_root/src/apps/r1_mvs_control_v1" "$viewer/source/app"
cp "$repo_root/src/apps/gs3d_4way_viewer/build/three.module.min.js" "$viewer/source/three.module.min.js"
cp "$0" "$viewer/source/start_viewer.sh"
judgment="$artifact_root/phase-payloads/phd/r1_area_judgment_v1/PHD-R1-AREA-JUDGMENT-v1/attempt_20260916T134132Z_9keJVvIo"
image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
common=(--runtime runc --read-only --cap-drop ALL --security-opt no-new-privileges --user "$(id -u):$(id -g)"
 -e PYTHONDONTWRITEBYTECODE=1 -e NVIDIA_VISIBLE_DEVICES=void -e LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6
 -e OPENBLAS_NUM_THREADS=2 -e OMP_NUM_THREADS=2 --tmpfs /tmp:rw,nosuid,size=256m)
docker run -d --name jbgs-r1-control-publisher-8912 --restart unless-stopped "${common[@]}" --network none --cpus 2 --memory 12g \
 --mount "type=bind,source=$viewer/source,target=/driver,readonly" \
 --mount "type=bind,source=$attempt,target=/run,readonly" \
 --mount "type=bind,source=$judgment/result,target=/evidence,readonly" \
 --mount "type=bind,source=$judgment/review_20260916T140058Z_pvyQNrYK/result,target=/review,readonly" \
 --mount "type=bind,source=$viewer/data,target=/out" "$image" python /driver/publish.py > "$viewer/publisher_container.txt"
docker run -d --name jbgs-r1-control-viewer-8912 --restart unless-stopped "${common[@]}" --cpus 1 --memory 512m --publish 127.0.0.1:8912:8080 \
 --mount "type=bind,source=$viewer/source/serve.py,target=/serve.py,readonly" \
 --mount "type=bind,source=$viewer/source/app,target=/app,readonly" \
 --mount "type=bind,source=$viewer/source/three.module.min.js,target=/vendor/three.module.min.js,readonly" \
 --mount "type=bind,source=$viewer/data,target=/data,readonly" "$image" python /serve.py > "$viewer/server_container.txt"
printf 'http://127.0.0.1:8912/\n'
