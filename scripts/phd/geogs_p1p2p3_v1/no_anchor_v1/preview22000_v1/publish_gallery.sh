#!/usr/bin/env bash
set -euo pipefail
preview_gallery_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../../../.." && pwd)
preview_gallery_task=$(realpath "$preview_gallery_repo/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1")
preview_gallery_root="$preview_gallery_task/preview22000_v1/P2"
preview_gallery_code="$preview_gallery_repo/scripts/phd/geogs_p1p2p3_v1/no_anchor_v1/preview22000_v1"
preview_gallery_run="$preview_gallery_root/gallery_build_v1"
test -s "$preview_gallery_root/receipt.json"
test ! -e "$preview_gallery_root/gallery_v1"
test ! -e "$preview_gallery_run"
mkdir -p "$preview_gallery_run/code"
cp -- "$preview_gallery_code/"{gallery.py,gallery.html,publish_gallery.sh,browser_qa.mjs} "$preview_gallery_run/code/"
cp -- "$preview_gallery_repo/configs/phd/geogs_p1p2p3_v1/sfm_prefix22000_gallery_v1.json" "$preview_gallery_run/config.json"
trap 'preview_gallery_exit=$?; printf "%s\n" "$preview_gallery_exit" > "$preview_gallery_run/exit_code.txt"' EXIT
exec 8> "$preview_gallery_task/no_anchor_sfm_v1/locks/heavy_cpu.lock"
flock 8
preview_gallery_command=(docker run --rm --network none --cpus 2 --memory 2g --memory-swap 2g
  --user "$(id -u):$(id -g)" --env PYTHONDONTWRITEBYTECODE=1 --env OMP_NUM_THREADS=2 --env OPENBLAS_NUM_THREADS=2
  --mount "type=bind,src=$preview_gallery_task,dst=/task,readonly"
  --mount "type=bind,src=$preview_gallery_root,dst=/preview"
  --mount "type=bind,src=$preview_gallery_run/code,dst=/code,readonly"
  --mount "type=bind,src=$preview_gallery_run/config.json,dst=/gallery_config.json,readonly"
  sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e python /code/gallery.py)
printf '%q ' "${preview_gallery_command[@]}" > "$preview_gallery_run/command.sh"
printf '\n' >> "$preview_gallery_run/command.sh"
"${preview_gallery_command[@]}" > "$preview_gallery_run/stdout.log" 2> "$preview_gallery_run/stderr.log"
cat "$preview_gallery_run/stdout.log"
