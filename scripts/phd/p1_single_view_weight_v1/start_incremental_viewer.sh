#!/usr/bin/env bash
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
artifact="$(realpath "$repo/../JointBuildGS-artifacts")"
task="$artifact/phase-payloads/phd/p1_single_view_weight_v1/PHD-P1-SINGLE-VIEW-WEIGHT-v1"
experiment="$task/attempt.annotated.uOkHWmgi"
output="$artifact/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1/viewer_rgb_v1/p1_weights_v1"
base="$artifact/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1"
source_path="$artifact/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1/sources/GeoGS-mvs-pgsr-v1"
image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
unit=jbgs-p1-weight-incremental-viewer
test "$(docker image inspect "$image" --format '{{.Id}}')" = "$image"
test "$(docker inspect jbgs-geogs-rgb-viewer-8910 --format '{{.State.Running}}')" = true
test ! -e "$output"
test "$(systemctl --user is-active "$unit.service" || true)" != active
mkdir "$output"
mkdir -p "$output/source/legacy"
cp -p "$repo/scripts/phd/p1_single_view_weight_v1/"{viewer_publish.py,viewer_worker.sh,start_incremental_viewer.sh} "$output/source/"
cp -p "$experiment/parent_scripts/finalize.py" "$output/source/finalize.py"
cp -p "$experiment/legacy_scripts/parse_extraction.py" "$output/source/legacy/"
cp -p "$repo/scripts/phd/geogs_mvs_pgsr_v1/viewer/export_geometry.py" "$output/source/"
cp -p "$repo/configs/phd/p1_single_view_weight_v1/viewer_v1.json" "$output/source/viewer_config.json"
cp -p "$repo/src/apps/geogs_rgb_comparison_v1/"{p1_weights.html,matched.js,matched.css} "$output/source/"
cp -p "$task/scope_explanation.GGlNGAjv/result/0100_D_current_supervision_scope.png" "$output/scope.png"
git -C "$repo" rev-parse HEAD > "$output/source/operator_head.txt"
sha256sum "$output/source/"*.py "$output/source/"*.sh "$output/source/"*.json \
  "$output/source/"*.html "$output/source/"*.js "$output/source/"*.css \
  "$output/source/legacy/"*.py > "$output/source/sha256sums.txt"
sha256sum "$experiment/scripts/run_queue.sh" "$experiment/scripts/run_phase.sh" \
  "$experiment/scripts/postprocess.sh" "$experiment/scripts/postprocess.py" \
  "$experiment/config.json" "$experiment/mask/r1_mask.npz" > "$output/training_unchanged.sha256"
docker run --rm --runtime runc --network none --cpus 2 --memory 3g --user "$(id -u):$(id -g)" \
  --env NVIDIA_VISIBLE_DEVICES=void --env CUDA_VISIBLE_DEVICES= --env PYTHONDONTWRITEBYTECODE=1 \
  --mount "type=bind,src=$output/source,dst=/driver,readonly" \
  --mount "type=bind,src=$source_path,dst=/source,readonly" \
  --mount "type=bind,src=$base/inputs/P1,dst=/input,readonly" \
  --mount "type=bind,src=$experiment,dst=/experiment,readonly" \
  --mount "type=bind,src=$output,dst=/output" \
  "$image" python /driver/viewer_publish.py refresh > "$output/initialize.log" 2>&1
docker run --rm --runtime runc --network none --cpus 1 --memory 1g --user "$(id -u):$(id -g)" \
  --env NVIDIA_VISIBLE_DEVICES=void --env CUDA_VISIBLE_DEVICES= \
  "$image" python -c 'import json,sys,numpy,PIL,matplotlib; print(json.dumps(dict(python=sys.version,numpy=numpy.__version__,pillow=PIL.__version__,matplotlib=matplotlib.__version__)))' > "$output/runtime.json"
systemd-run --user --unit="$unit" --description='Publish each completed P1 alpha result independently' \
  --property=Type=exec --property=Restart=no \
  --property="StandardOutput=append:$output/worker.log" \
  --property="StandardError=append:$output/worker.log" \
  /usr/bin/bash "$output/source/viewer_worker.sh" "$output"
sha256sum --check --status "$output/training_unchanged.sha256"
printf '%s\n' "$output" 'http://127.0.0.1:8910/app/p1_weights.html'
