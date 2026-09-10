#!/usr/bin/env bash
set -euo pipefail
photo_audit=${1:?Expected /task/main_v2/photo_target_audit/attempt_*}
evaluation=${2:?Expected /task/main_v2/evaluation/attempt_*}
shift 2
[[ $photo_audit =~ ^/task/main_v2/photo_target_audit/attempt_[A-Za-z0-9_]+$ ]]
[[ $evaluation =~ ^/task/main_v2/evaluation/attempt_[A-Za-z0-9_]+$ ]]
(( $# <= 1 ))
if (( $# )); then [[ $1 == --allow-partial ]]; fi
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
artifact_root=$(realpath "$repo/../JointBuildGS-artifacts")
task_root="$artifact_root/phase-payloads/phd/local_complementary_refinement_v1/PHD-LOCAL-COMPLEMENTARY-REFINEMENT-v1"
parent_root="$artifact_root/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1"
image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
[[ $(docker image inspect jointbuildgs:geogs-official-db40c95-compat-v1 --format '{{.Id}}') == "$image" ]]
mkdir -p "$task_root/main_v2/photo_case_summary"
exec docker run --rm --read-only --network none --cpus 2 --memory 4g --memory-swap 4g \
 --tmpfs /tmp:rw,size=256m --user "$(id -u):$(id -g)" \
 -e PYTHONDONTWRITEBYTECODE=1 -e OMP_NUM_THREADS=2 -e OPENBLAS_NUM_THREADS=2 -e "JBGS_RUNTIME_IMAGE_ID=$image" \
 --mount "type=bind,src=$parent_root/evaluation/geometry,dst=/parent/evaluation/geometry,readonly" \
 --mount "type=bind,src=$task_root/${photo_audit#/task/},dst=$photo_audit,readonly" \
 --mount "type=bind,src=$task_root/${evaluation#/task/},dst=$evaluation,readonly" \
 --mount "type=bind,src=$task_root/contracts/main_v2/experiment_v2.json,dst=/config/experiment_v2.json,readonly" \
 --mount "type=bind,src=$repo/scripts/phd/local_complementary_refinement_v1/summarize_photo_cases_v2.py,dst=/audit/summarize_photo_cases_v2.py,readonly" \
 --mount "type=bind,src=$repo/scripts/phd/local_complementary_refinement_v1/run_photo_case_summary_v2.sh,dst=/audit/run_photo_case_summary_v2.sh,readonly" \
 --mount "type=bind,src=$task_root/main_v2/photo_case_summary,dst=/out" \
 "$image" python /audit/summarize_photo_cases_v2.py --parent /parent --photo-audit "$photo_audit" --evaluation "$evaluation" \
 --config /config/experiment_v2.json --launcher /audit/run_photo_case_summary_v2.sh --output /out "$@"
