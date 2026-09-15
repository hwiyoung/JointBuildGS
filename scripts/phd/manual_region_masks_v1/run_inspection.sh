#!/usr/bin/env bash
set -euo pipefail
region="${1:?P2 or P3}"
case "$region" in P2|P3) ;; *) exit 2;; esac
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
artifacts="$(realpath "$repo/../JointBuildGS-artifacts")"
task="$artifacts/phase-payloads/phd/manual_region_masks_v1/PHD-P2P3-MANUAL-REGIONS-v1"
mkdir -p "$task"
attempt="$(mktemp -d "$task/inspect.$region.XXXXXXXX")"
mkdir "$attempt/source"
cp -p "$repo/scripts/phd/manual_region_masks_v1/"{inspect_regions.py,run_inspection.sh} "$attempt/source/"
cp -p "$repo/src/phd/"{manual_region_masks_v1.py,mvs_evidence_v1.py} "$attempt/source/"
cp -p "$repo/src/phd/geogs_mvs_pgsr_v1/mvs_depth.py" "$attempt/source/"
cp -p "$repo/configs/phd/manual_region_masks_v1/${region,,}_inspection_v1.json" "$attempt/source/config.json"
git -C "$repo" rev-parse HEAD > "$attempt/commit.txt"
printf '%s\n' "$attempt" > "/tmp/jbgs_${region}_mask_inspection.txt"
image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
command=(docker run --rm --runtime runc --network none --cpus 2 --memory 4g
  --user "$(id -u):$(id -g)" --env PYTHONDONTWRITEBYTECODE=1 --env MPLCONFIGDIR=/tmp/mpl
  --env NVIDIA_VISIBLE_DEVICES=void --env CUDA_VISIBLE_DEVICES= --env OMP_NUM_THREADS=2 --env OPENBLAS_NUM_THREADS=2
  --mount "type=bind,src=$artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/inputs/$region,dst=/input,readonly"
  --mount "type=bind,src=$artifacts/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1/inputs_v2/$region,dst=/mvs,readonly"
  --mount "type=bind,src=/usr/share/fonts/opentype/noto,dst=/font,readonly"
  --mount "type=bind,src=$attempt,dst=/output"
  "$image" python /output/source/inspect_regions.py --region "$region" --config /output/source/config.json --output /output/result)
printf '%q ' "${command[@]}" > "$attempt/command.sh"
printf '\n' >> "$attempt/command.sh"
printf '%s\n' "$attempt"
"${command[@]}" 2>&1 | tee "$attempt/run.log"
