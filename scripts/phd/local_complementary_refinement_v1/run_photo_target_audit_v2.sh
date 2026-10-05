#!/usr/bin/env bash
# Additive CPU evaluation of already selected input/reference cases; no models.
set -euo pipefail
(( $# == 0 ))
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
artifact_root=$(realpath "$repo/../JointBuildGS-artifacts")
task_root="$artifact_root/phase-payloads/phd/local_complementary_refinement_v1/PHD-LOCAL-COMPLEMENTARY-REFINEMENT-v1"
parent_root="$artifact_root/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1"
image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
[[ $(docker image inspect jointbuildgs:geogs-official-db40c95-compat-v1 --format '{{.Id}}') == "$image" ]]
mkdir -p "$task_root/main_v2/photo_target_audit"
exec docker run --rm --read-only --network none --cpus 2 --memory 4g --memory-swap 4g \
 --tmpfs /tmp:rw,size=256m --user "$(id -u):$(id -g)" \
 -e PYTHONDONTWRITEBYTECODE=1 -e OMP_NUM_THREADS=2 -e OPENBLAS_NUM_THREADS=2 \
 -e MPLCONFIGDIR=/tmp/mpl -e "JBGS_RUNTIME_IMAGE_ID=$image" \
 --mount "type=bind,src=$parent_root/inputs,dst=/parent/inputs,readonly" \
 --mount "type=bind,src=$parent_root/evaluation/da3_refinement_spatial_v1,dst=/parent/evaluation/da3_refinement_spatial_v1,readonly" \
 --mount "type=bind,src=$task_root/contracts/main_v2/input_binding.json,dst=/binding.json,readonly" \
 --mount "type=bind,src=$repo/configs/phd/local_complementary_refinement_v1/photo_target_diagnostic_v2.json,dst=/audit/photo_target_diagnostic_v2.json,readonly" \
 --mount "type=bind,src=$repo/scripts/phd/local_complementary_refinement_v1/audit_photo_targets_v2.py,dst=/audit/audit_photo_targets_v2.py,readonly" \
 --mount "type=bind,src=$repo/scripts/phd/local_complementary_refinement_v1/run_photo_target_audit_v2.sh,dst=/audit/run_photo_target_audit_v2.sh,readonly" \
 --mount "type=bind,src=$task_root/main_v2/photo_target_audit,dst=/out" \
 "$image" python /audit/audit_photo_targets_v2.py --parent /parent --binding /binding.json \
 --config /audit/photo_target_diagnostic_v2.json --launcher /audit/run_photo_target_audit_v2.sh --output /out
