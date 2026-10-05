#!/usr/bin/env bash
# Read-only exact point-distance to displayed-cell QA; no GT use in training.
set -euo pipefail
evaluation=${1:?Expected /task/main_v2/evaluation/attempt_*}
maps=${2:?Expected /task/main_v2/maps/attempt_*}
shift 2
[[ $evaluation =~ ^/task/main_v2/evaluation/attempt_[A-Za-z0-9_]+$ ]]
[[ $maps =~ ^/task/main_v2/maps/attempt_[A-Za-z0-9_]+$ ]]
(( $# <= 1 ))
if (( $# )); then [[ $1 == --allow-partial ]]; fi
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
artifact_root=$(realpath "$repo/../JointBuildGS-artifacts")
task_root="$artifact_root/phase-payloads/phd/local_complementary_refinement_v1/PHD-LOCAL-COMPLEMENTARY-REFINEMENT-v1"
parent_root="$artifact_root/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1"
image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
[[ $(docker image inspect jointbuildgs:geogs-official-db40c95-compat-v1 --format '{{.Id}}') == "$image" ]]
test -s "$task_root/${evaluation#/task/}/receipt.json"
test -s "$task_root/${maps#/task/}/receipt.json"
mkdir -p "$task_root/main_v2/maps_review"
exec docker run --rm --read-only --network none --cpus 2 --memory 4g --memory-swap 4g \
 --tmpfs /tmp:rw,size=256m --user "$(id -u):$(id -g)" \
 -e PYTHONDONTWRITEBYTECODE=1 -e OMP_NUM_THREADS=2 -e OPENBLAS_NUM_THREADS=2 -e "JBGS_RUNTIME_IMAGE_ID=$image" \
 --mount "type=bind,src=$task_root,dst=/task,readonly" \
 --mount "type=bind,src=$parent_root,dst=/parent,readonly" \
 --mount "type=bind,src=$repo/scripts/phd/local_complementary_refinement_v1/review_maps_v2.py,dst=/audit/review_maps_v2.py,readonly" \
 --mount "type=bind,src=$task_root/main_v2/maps_review,dst=/task/main_v2/maps_review" \
 "$image" python /audit/review_maps_v2.py --evaluation "$evaluation" --maps "$maps" \
 --parent /parent --config /task/contracts/main_v2/experiment_v2.json --output /task/main_v2/maps_review "$@"
