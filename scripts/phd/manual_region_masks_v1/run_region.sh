#!/usr/bin/env bash
set -euo pipefail
region="${1:?P2 or P3}"
case "$region" in P2|P3) ;; *) exit 2;; esac
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
artifact_root="$(realpath "$repo/../JointBuildGS-artifacts")"
parent="$artifact_root/phase-payloads/phd/manual_region_masks_v1/PHD-P2P3-MANUAL-REGIONS-v1"
mkdir -p "$parent"
attempt="$(mktemp -d "$parent/annotation.$region.XXXXXXXX")"
mkdir "$attempt/source"
cp -p "$repo/scripts/phd/manual_region_masks_v1/"{generate.py,run_region.sh} "$attempt/source/"
cp -p "$repo/src/phd/manual_region_masks_v1.py" "$attempt/source/"
cp -p "$repo/src/phd/geogs_mvs_pgsr_v1/mvs_depth.py" "$attempt/source/"
cp -p "$repo/configs/phd/manual_region_masks_v1/${region,,}_v1.json" "$attempt/source/config.json"
git -C "$repo" rev-parse HEAD > "$attempt/commit.txt"
printf '%s\n' "$attempt" > "/tmp/jbgs_${region}_mask_annotation.txt"
image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
command=(docker run --rm --runtime runc --network none --cpus 2 --memory 4g
  --user "$(id -u):$(id -g)" --cap-drop ALL --security-opt no-new-privileges
  --read-only --tmpfs /tmp:rw,size=512m -e MPLCONFIGDIR=/tmp/mpl -e PYTHONDONTWRITEBYTECODE=1
  -e OMP_NUM_THREADS=2 -e OPENBLAS_NUM_THREADS=2 -e NVIDIA_VISIBLE_DEVICES=void -e CUDA_VISIBLE_DEVICES=
  -v "$artifact_root/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/inputs/$region:/prior_input:ro"
  -v "$artifact_root/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1/inputs_v2/$region:/mvs_input:ro"
  -v /usr/share/fonts/opentype/noto:/font:ro -v "$attempt:/output:rw"
  --entrypoint python "$image" /output/source/generate.py --config /output/source/config.json
  --output /output/result --commit "$(cat "$attempt/commit.txt")" --runtime-image-id "$image")
printf '%q ' "${command[@]}" > "$attempt/command.sh"
printf '\n' >> "$attempt/command.sh"
printf '%s\n' "$attempt"
"${command[@]}" 2>&1 | tee "$attempt/run.log"
