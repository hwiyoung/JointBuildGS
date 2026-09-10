#!/usr/bin/env bash
# Additive read-only audit. Argument is the exact sealed host walkthrough attempt.
set -euo pipefail
(( $# == 1 ))
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
audit_artifact="$(readlink -f "$repo/../JointBuildGS-artifacts")"
audit_task="$audit_artifact/phase-payloads/phd/local_complementary_refinement_v1/PHD-LOCAL-COMPLEMENTARY-REFINEMENT-v1"
audit_parent="$audit_artifact/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1"
audit_walkthrough="$(readlink -f "$1")"
[[ "$audit_walkthrough" == "$audit_task/main_v2/photometric_walkthrough_v3_2/attempt_"* ]]
[[ "$(dirname "$audit_walkthrough")" == "$audit_task/main_v2/photometric_walkthrough_v3_2" ]]
audit_image='sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e'
[[ "$(docker image inspect "$audit_image" --format '{{.Id}}')" == "$audit_image" ]]
for item in receipt.json plan.json neighbor_names.tsv; do [[ -f "$audit_walkthrough/$item" ]]; done
mkdir -p "$audit_task/main_v2/photometric_walkthrough_v3_2/camera_audit"
audit_output="$(mktemp -d "$audit_task/main_v2/photometric_walkthrough_v3_2/camera_audit/attempt_$(date -u +%Y%m%dT%H%M%SZ)_XXXXXX")"
cat > "$audit_output/config.json" <<'JSON'
{
  "schema": "jbgs.walkthrough_camera_audit.config.v3.2",
  "observations_per_selected_view": 200,
  "selection": "first_valid_native_observation_entries_without_residual_filter",
  "metadata_atol": 1e-14,
  "axis_atol": 1e-12,
  "image_id": "sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e",
  "gt_geometry_used": false,
  "scientific_verdict": null
}
JSON
audit_mounts=()
for region in P1 P2; do
  for item in input_manifest.json scene/split_manifest_da3_v2.json scene/camera_receipt.json scene/train_sparse_txt/cameras.txt scene/train_sparse_txt/images.txt scene/sparse/0/cameras.bin scene/sparse/0/images.bin; do
    audit_mounts+=(--mount "type=bind,src=$audit_parent/inputs/$region/$item,dst=/inputs/$region/$item,readonly")
  done
done
for item in cameras images points3D; do
  audit_mounts+=(--mount "type=bind,src=$audit_artifact/phase-payloads/p0-audit/data/work/mvs/colmap_dense/sparse/$item.bin,dst=/original/$item.bin,readonly")
done
for item in receipt.json plan.json neighbor_names.tsv; do
  audit_mounts+=(--mount "type=bind,src=$audit_walkthrough/$item,dst=/walkthrough/$item,readonly")
done
audit_command=(docker run --rm --read-only --network none --cpus 2 --memory 2g --memory-swap 2g
  --user "$(id -u):$(id -g)" -e PYTHONDONTWRITEBYTECODE=1 -e OMP_NUM_THREADS=2 -e OPENBLAS_NUM_THREADS=2
  -e "JBGS_RUNTIME_IMAGE_ID=$audit_image" "${audit_mounts[@]}"
  --mount "type=bind,src=$repo/scripts/phd/local_complementary_refinement_v1/audit_walkthrough_camera_v3_2.py,dst=/audit/audit_walkthrough_camera_v3_2.py,readonly"
  --mount "type=bind,src=$repo/scripts/phd/local_complementary_refinement_v1/run_walkthrough_camera_audit_v3_2.sh,dst=/audit/run_walkthrough_camera_audit_v3_2.sh,readonly"
  --mount "type=bind,src=$audit_output/config.json,dst=/audit/config.json,readonly"
  --mount "type=bind,src=$audit_output,dst=/output"
  --entrypoint python "$audit_image" /audit/audit_walkthrough_camera_v3_2.py
  --inputs /inputs --original /original --walkthrough /walkthrough --config /audit/config.json
  --launcher /audit/run_walkthrough_camera_audit_v3_2.sh --output /output)
git -C "$repo" rev-parse HEAD > "$audit_output/repository_commit.txt"
printf '%q ' "${audit_command[@]}" > "$audit_output/execute_command.txt"
printf '\n' >> "$audit_output/execute_command.txt"
set +e
"${audit_command[@]}"
audit_status=$?
set -e
if [[ -f "$audit_output/receipt.json" ]]; then
  (cd "$audit_output" && sha256sum receipt.json > receipt.sha256)
fi
chmod a-w "$audit_output"/* "$audit_output"
printf 'Camera audit status=%s output=%s\n' "$audit_status" "$audit_output"
exit "$audit_status"
