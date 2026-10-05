#!/usr/bin/env bash
# Additive two-stage CPU diagnostic. Stage 1 fixes centers/neighbors before any RGB read.
set -euo pipefail
(( $# == 0 ))
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
artifact_root="$(readlink -f "$repo/../JointBuildGS-artifacts")"
task="$artifact_root/phase-payloads/phd/local_complementary_refinement_v1/PHD-LOCAL-COMPLEMENTARY-REFINEMENT-v1"
parent="$artifact_root/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1"
image='sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e'
[[ "$(docker image inspect jointbuildgs:geogs-official-db40c95-compat-v1 --format '{{.Id}}')" == "$image" ]]
mkdir -p "$task/main_v2/photometric_walkthrough_v3_2"
output="$(mktemp -d "$task/main_v2/photometric_walkthrough_v3_2/attempt_$(date -u +%Y%m%dT%H%M%SZ)_XXXXXX")"
mounts=()
for entry in P1:DJI_20241217084553_0100_D P2:DJI_20241217084505_0076_D; do
  region="${entry%%:*}"; stem="${entry#*:}"
  for relative in input_manifest.json scene/split_manifest_da3_v2.json "prior/raw_depth/$stem.npy" "da3/raw_depth/$stem.npy"; do
    mounts+=(--mount "type=bind,src=$parent/inputs/$region/$relative,dst=/inputs/$region/$relative,readonly")
  done
  mounts+=(--mount "type=bind,src=$artifact_root/phase-payloads/p0-audit/data/work/mvs/colmap_dense/stereo/depth_maps/$stem.JPG.geometric.bin,dst=/inputs/$region/mvs.geometric.bin,readonly")
done
base=(docker run --rm --read-only --network none --cpus 4 --memory 8g --memory-swap 8g
  --tmpfs /tmp:rw,size=256m --user "$(id -u):$(id -g)" -w /tmp
  -e PYTHONDONTWRITEBYTECODE=1 -e OMP_NUM_THREADS=4 -e OPENBLAS_NUM_THREADS=4 -e MPLCONFIGDIR=/tmp/mpl
  -e "JBGS_RUNTIME_IMAGE_ID=$image"
  --mount "type=bind,src=$task/contracts/main_v2/input_binding.json,dst=/contracts/input_binding.json,readonly"
  --mount "type=bind,src=$repo/configs/phd/local_complementary_refinement_v1/photometric_walkthrough_v3_2.json,dst=/audit/config.json,readonly"
  --mount "type=bind,src=$repo/scripts/phd/local_complementary_refinement_v1/photometric_walkthrough_v3_2.py,dst=/audit/photometric_walkthrough_v3_2.py,readonly"
  --mount "type=bind,src=$repo/scripts/phd/local_complementary_refinement_v1/run_photometric_walkthrough_v3_2.sh,dst=/audit/run_photometric_walkthrough_v3_2.sh,readonly"
  --mount "type=bind,src=$output,dst=/output")
args=(--inputs /inputs --config /audit/config.json --binding /contracts/input_binding.json
  --launcher /audit/run_photometric_walkthrough_v3_2.sh --output /output)
git -C "$repo" rev-parse HEAD > "$output/repository_commit.txt"
printf '%q ' "${base[@]}" "${mounts[@]}" --entrypoint python "$image" /audit/photometric_walkthrough_v3_2.py --stage plan "${args[@]}" > "$output/plan_command.txt"
printf '\n' >> "$output/plan_command.txt"
"${base[@]}" "${mounts[@]}" --entrypoint python "$image" /audit/photometric_walkthrough_v3_2.py --stage plan "${args[@]}" > "$output/plan.log" 2>&1
while IFS=$'\t' read -r region name; do
  [[ "$region" =~ ^P[12]$ && "$name" =~ ^DJI_[0-9_]+_D\.JPG$ ]]
  mounts+=(--mount "type=bind,src=$parent/inputs/$region/scene/images/$name,dst=/inputs/$region/scene/images/$name,readonly")
done < "$output/neighbor_names.tsv"
printf '%q ' "${base[@]}" "${mounts[@]}" --entrypoint python "$image" /audit/photometric_walkthrough_v3_2.py --stage execute "${args[@]}" > "$output/execute_command.txt"
printf '\n' >> "$output/execute_command.txt"
"${base[@]}" "${mounts[@]}" --entrypoint python "$image" /audit/photometric_walkthrough_v3_2.py --stage execute "${args[@]}" > "$output/execute.log" 2>&1
printf 'Photometric diagnostic: %s\n' "$output"
