#!/usr/bin/env bash
# PHD-MAIN-WIDEN0-v2: only authorized GPU operation, exact inherited COLMAP settings.
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
ART=$(realpath "$REPO/../JointBuildGS-artifacts")
OUT="$ART/phase-payloads/phd/main_widen0_v2/PHD-MAIN-WIDEN0-v2"
WS="$OUT/mvs/full"
IMG=colmap/colmap@sha256:187ca5ec98e55ed8fbec5f43f9d8f78b7a322b3b7413356634191f7a43c1efcf
GPU=${1:-1}
test -f "$REPO/docs/experiments/phd/main_widen0_v2/중간보고_v1.md"
test -f "$WS/subset.json"
test -f "$OUT/gates/input_pass.json"
test ! -f "$WS/colmap_receipt.json"
mkdir -p "$WS/cache" "$WS/tmp"
wait_start=$SECONDS
while true; do
  # The desktop encoder on GPU 0 is an active desktop service, not a research job.
  # Every research compute process on either GPU still causes a wait; the chosen
  # GPU must also have no compute process of any kind.
  busy=$(nvidia-smi --query-compute-apps=process_name --format=csv,noheader,nounits | awk '$0 != "/usr/libexec/gnome-remote-desktop-daemon"')
  target_busy=$(nvidia-smi -i "$GPU" --query-compute-apps=pid --format=csv,noheader,nounits)
  if [ -z "$busy" ] && [ -z "$target_busy" ]; then break; fi
  sleep 30
done
wait_s=$((SECONDS-wait_start))
if [ -f "$OUT/gpu_wait_initial_seconds.txt" ]; then
  read -r initial_wait < "$OUT/gpu_wait_initial_seconds.txt"
  wait_s=$((wait_s+initial_wait))
fi
start_utc=$(date -u +%FT%TZ)
start=$SECONDS
set +e
nice -n 19 docker run --rm --name jbgs-main-widen0-v2-mvs --read-only --network none \
  --gpus "device=$GPU" --user "$(id -u):$(id -g)" --memory 32g --memory-swap 32g --cpus 8 \
  -e XDG_CACHE_HOME=/ws/cache -e CUDA_CACHE_PATH=/ws/cache/cuda -e TMPDIR=/ws/tmp \
  -v "$ART:/art:ro" -v "$WS:/ws:rw" -v "$WS/tmp:/tmp:rw" -w /ws \
  --entrypoint nice "$IMG" -n 19 colmap patch_match_stereo --workspace_path /ws --workspace_format COLMAP \
  --PatchMatchStereo.geom_consistency true --PatchMatchStereo.max_image_size 1024 \
  --PatchMatchStereo.num_iterations 3 --PatchMatchStereo.filter true --PatchMatchStereo.cache_size 32 \
  --PatchMatchStereo.gpu_index 0 > "$WS/patch_match.log" 2>&1
rc=$?
set -e
elapsed=$((SECONDS-start))
count=$(find "$WS/stereo/depth_maps" -maxdepth 1 -type f -name '*.geometric.bin' | wc -l)
cat > "$WS/colmap_receipt.json" <<EOF
{
  "task_id": "PHD-MAIN-WIDEN0-v2",
  "started_at_utc": "$start_utc",
  "image": "$IMG",
  "gpu": $GPU,
  "gpu_wait_seconds": $wait_s,
  "desktop_service": "GPU 0 gnome-remote-desktop preserved; selected GPU 1 empty before launch",
  "seconds": $elapsed,
  "exit_code": $rc,
  "geometric_depth_maps": $count,
  "training": false,
  "scientific_verdict": null
}
EOF
exit "$rc"
