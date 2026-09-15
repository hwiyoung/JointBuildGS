#!/usr/bin/env bash
set -euo pipefail
region="${1:?P2 or P3}"
case "$region" in P2|P3) ;; *) exit 2;; esac
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
artifact_root="$(realpath "$repo/../JointBuildGS-artifacts")"
annotation="$(cat "/tmp/jbgs_${region}_mask_annotation.txt")"
[[ -f "$annotation/result/receipt.json" ]]
review="$(mktemp -d "$(dirname "$annotation")/review.$region.XXXXXXXX")"
mkdir "$review/source"
cp -p "$repo/scripts/phd/manual_region_masks_v1/"{review_regions.py,validate_output.py,run_review.sh} "$review/source/"
cp -p "$repo/src/phd/geogs_mvs_pgsr_v1/mvs_depth.py" "$review/source/"
git -C "$repo" rev-parse HEAD > "$review/commit.txt"
printf '%s\n' "$annotation" > "$review/annotation_path.txt"
printf '%s\n' "$review" > "/tmp/jbgs_${region}_mask_review.txt"
image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
command=(docker run --rm --runtime runc --network none --cpus 2 --memory 4g
  --user "$(id -u):$(id -g)" --cap-drop ALL --security-opt no-new-privileges
  --read-only --tmpfs /tmp:rw,size=512m -e MPLCONFIGDIR=/tmp/mpl -e PYTHONDONTWRITEBYTECODE=1
  -e OMP_NUM_THREADS=2 -e OPENBLAS_NUM_THREADS=2 -e NVIDIA_VISIBLE_DEVICES=void -e CUDA_VISIBLE_DEVICES=
  -v "$artifact_root/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/inputs/$region:/prior_input:ro"
  -v "$artifact_root/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1/inputs_v2/$region:/mvs_input:ro"
  -v /usr/share/fonts/opentype/noto:/font:ro -v "$annotation/result:/annotations:ro" -v "$review:/output:rw"
  --entrypoint python "$image")
printf '%q ' "${command[@]}" > "$review/docker_prefix.sh"
printf '\n' >> "$review/docker_prefix.sh"
"${command[@]}" /output/source/validate_output.py --result /annotations --output /output/validation.json > "$review/validation.log" 2>&1
"${command[@]}" /output/source/review_regions.py --annotations /annotations --output /output/result > "$review/review.log" 2>&1
printf '%s\n' "$review"
