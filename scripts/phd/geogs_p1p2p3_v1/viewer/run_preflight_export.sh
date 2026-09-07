#!/usr/bin/env bash
set -euo pipefail
geogs_pre_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../../.." && pwd)
geogs_pre_task=$(realpath "$geogs_pre_repo/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1")
geogs_pre_out="$geogs_pre_task/viewer_preflight"
if [[ -e "$geogs_pre_out" ]]; then echo 'Preflight path already exists; preserve it' >&2; exit 1; fi
mkdir -- "$geogs_pre_out"
cp -- "$geogs_pre_repo/scripts/phd/geogs_p1p2p3_v1/viewer/export_preflight.py" "$geogs_pre_out/export_source.py"
cp -- "$geogs_pre_repo/scripts/phd/geogs_p1p2p3_v1/viewer/run_preflight_export.sh" "$geogs_pre_out/export_command.sh"
geogs_pre_image=$(docker image inspect jointbuildgs:geogs-official-db40c95-compat-v1 --format '{{.Id}}')
printf '%s\n' "$geogs_pre_image" > "$geogs_pre_out/image_id.txt"
docker run --rm --read-only --network none --cpus 2 --memory 2g \
  --mount "type=bind,src=$geogs_pre_out/export_source.py,dst=/export.py,readonly" \
  --mount "type=bind,src=$geogs_pre_repo/configs/phd/geogs_p1p2p3_v1/experiment_v1.json,dst=/config.json,readonly" \
  --mount "type=bind,src=$geogs_pre_task/inputs/P1/surface/als_surface.ply,dst=/surfaces/P1.ply,readonly" \
  --mount "type=bind,src=$geogs_pre_task/inputs/P2/surface/als_surface.ply,dst=/surfaces/P2.ply,readonly" \
  --mount "type=bind,src=$geogs_pre_task/inputs/P3/surface/als_surface.ply,dst=/surfaces/P3.ply,readonly" \
  --mount "type=bind,src=$geogs_pre_out,dst=/out" \
  --entrypoint /opt/geogs/bin/python "$geogs_pre_image" /export.py > "$geogs_pre_out/export.log" 2>&1
printf '%s\n' "$geogs_pre_out/manifest.json"
