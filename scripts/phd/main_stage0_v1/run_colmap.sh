#!/usr/bin/env bash
# PHD-MAIN-STAGE0-v1 (the discard task's run_colmap.sh with this task's payload; thin): patch-match stereo of a subset
# workspace with the pinned CUDA COLMAP image. Same settings as the 937-image MVS: geom_consistency true, max_image_size 1024,
# num_iterations 3, filter true, cache_size 32. No network.
#   bash run_colmap.sh <name> <gpu>
set -uo pipefail
NAME=$1; GPU=${2:-0}
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
ART=$(realpath "$REPO/../JointBuildGS-artifacts")
P="$ART/phase-payloads/phd/main_stage0_v1/PHD-MAIN-STAGE0-v1"
IMG=colmap/colmap@sha256:187ca5ec98e55ed8fbec5f43f9d8f78b7a322b3b7413356634191f7a43c1efcf
WS="$P/mvs/$NAME"
t0=$SECONDS
docker run --rm --name "jbgs-stage0-colmap-$NAME" --gpus "device=$GPU" --network none --user "$(id -u):$(id -g)" \
  -v "$ART:/art:ro" -v "$WS:/ws" -w /ws "$IMG" \
  colmap patch_match_stereo --workspace_path /ws --workspace_format COLMAP \
    --PatchMatchStereo.geom_consistency true --PatchMatchStereo.max_image_size 1024 \
    --PatchMatchStereo.num_iterations 3 --PatchMatchStereo.filter true --PatchMatchStereo.cache_size 32 \
    --PatchMatchStereo.gpu_index 0 > "$WS/patch_match.log" 2>&1
rc=$?
ND=$(ls "$WS/stereo/depth_maps" | grep -c geometric || true)
echo "{\"name\": \"$NAME\", \"image\": \"$IMG\", \"gpu\": $GPU, \"exit_code\": $rc, \"seconds\": $((SECONDS-t0)), \"geometric_depth_maps\": $ND, \"scientific_verdict\": null}" > "$WS/colmap_receipt.json"
echo "colmap $NAME rc=$rc ${ND} maps $((SECONDS-t0)) s"
exit $rc
