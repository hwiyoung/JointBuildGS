#!/usr/bin/env bash
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
artifact_root="$(realpath "$repo/../JointBuildGS-artifacts")"
p2="$(cat /tmp/jbgs_P2_mask_review.txt)"
p3="$(cat /tmp/jbgs_P3_mask_review.txt)"
[[ -f "$p2/result/review.json" && -f "$p3/result/review.json" ]]
output="$artifact_root/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1/viewer_rgb_v1/p2p3_manual_regions_v1"
mkdir "$output"
mkdir "$output/source"
cp -p "$repo/scripts/phd/manual_region_masks_v1/"{publish_review.py,run_publish.sh} "$output/source/"
cp -p "$repo/src/apps/geogs_rgb_comparison_v1/"{manual_regions.html,manual_regions.js} "$output/source/"
printf '%s\n%s\n' "$p2" "$p3" > "$output/source/review_paths.txt"
git -C "$repo" rev-parse HEAD > "$output/source/commit.txt"
image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
command=(docker run --rm --runtime runc --network none --cpus 2 --memory 2g
 --user "$(id -u):$(id -g)" --env PYTHONDONTWRITEBYTECODE=1 --env NVIDIA_VISIBLE_DEVICES=void --env CUDA_VISIBLE_DEVICES=
 -v "$p2:/P2:ro" -v "$p3:/P3:ro" -v "$output:/output:rw" --entrypoint python "$image" /output/source/publish_review.py)
printf '%q ' "${command[@]}" > "$output/source/command.sh"
printf '\n' >> "$output/source/command.sh"
"${command[@]}" > "$output/publish.log" 2>&1
printf '%s\n' "$output"
