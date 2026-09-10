#!/usr/bin/env bash
# Additive CPU-only full-raster diagnostic. No source/runtime edits or model/GT mounts.
set -euo pipefail
(( $# == 0 ))
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
artifact_root="$(readlink -f "$repo/../JointBuildGS-artifacts")"
task="$artifact_root/phase-payloads/phd/local_complementary_refinement_v1/PHD-LOCAL-COMPLEMENTARY-REFINEMENT-v1"
parent="$artifact_root/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1"
image='sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e'
[[ "$(docker image inspect jointbuildgs:geogs-official-db40c95-compat-v1 --format '{{.Id}}')" == "$image" ]]
output="$task/main_v2/pixel_weight_audit_v2_5"
mkdir -p "$output"
mounts=()
for entry in P1:DJI_20241217084553_0100_D P2:DJI_20241217084505_0076_D; do
  region="${entry%%:*}"; stem="${entry#*:}"
  for relative in input_manifest.json "prior/raw_depth/$stem.npy" "da3/raw_depth/$stem.npy" "scene/images/$stem.JPG"; do
    mounts+=(--mount "type=bind,src=$parent/inputs/$region/$relative,dst=/inputs/$region/$relative,readonly")
  done
  mounts+=(--mount "type=bind,src=$task/main_v2/runs/$region/LC_D005_Pnative/train_invocation.json,dst=/inputs/$region/train_invocation.json,readonly")
done
exec docker run --rm --read-only --network none --cpus 2 --memory 4g --memory-swap 4g \
  --tmpfs /tmp:rw,size=256m --user "$(id -u):$(id -g)" -w /tmp \
  -e PYTHONDONTWRITEBYTECODE=1 -e OMP_NUM_THREADS=2 -e OPENBLAS_NUM_THREADS=2 -e MPLCONFIGDIR=/tmp/mpl \
  -e "JBGS_RUNTIME_IMAGE_ID=$image" "${mounts[@]}" \
  --mount "type=bind,src=$task/contracts/main_v2/experiment_v2.json,dst=/contracts/experiment_v2.json,readonly" \
  --mount "type=bind,src=$task/contracts/main_v2/input_binding.json,dst=/contracts/input_binding.json,readonly" \
  --mount "type=bind,src=$task/source_v2/jbgs_local_depth.py,dst=/frozen/jbgs_local_depth.py,readonly" \
  --mount "type=bind,src=$repo/configs/phd/local_complementary_refinement_v1/pixel_weight_audit_v2_5.json,dst=/audit/config.json,readonly" \
  --mount "type=bind,src=$repo/scripts/phd/local_complementary_refinement_v1/audit_pixel_weights_v2_5.py,dst=/audit/audit_pixel_weights_v2_5.py,readonly" \
  --mount "type=bind,src=$repo/scripts/phd/local_complementary_refinement_v1/run_pixel_weight_audit_v2_5.sh,dst=/audit/run_pixel_weight_audit_v2_5.sh,readonly" \
  --mount "type=bind,src=$output,dst=/output" --entrypoint python "$image" \
  /audit/audit_pixel_weights_v2_5.py --inputs /inputs --config /audit/config.json \
  --main-config /contracts/experiment_v2.json --binding /contracts/input_binding.json \
  --helper /frozen/jbgs_local_depth.py --launcher /audit/run_pixel_weight_audit_v2_5.sh --output /output
