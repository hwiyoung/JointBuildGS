#!/usr/bin/env bash
# CPU-only static maps; immutable evaluation inputs, no parent/GT/model mounts.
set -euo pipefail
evaluation=${1:?Expected /task/main_v2/evaluation/attempt_*}
[[ $evaluation == /task/main_v2/evaluation/attempt_* && $evaluation != *..* ]]
repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
task_root=$(realpath "$repo_root/../JointBuildGS-artifacts/phase-payloads/phd/local_complementary_refinement_v1/PHD-LOCAL-COMPLEMENTARY-REFINEMENT-v1")
evaluation_host=$(realpath "$task_root/${evaluation#/task/}")
[[ $evaluation_host == "$task_root"/main_v2/evaluation/attempt_* ]]
test -s "$evaluation_host/receipt.json"
image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
[[ $(docker image inspect jointbuildgs:geogs-official-db40c95-compat-v1 --format '{{.Id}}') == "$image" ]]
mkdir -p "$task_root/main_v2/maps"
exec docker run --rm --network none --read-only --cpus 2 --memory 4g --memory-swap 4g \
    --tmpfs /tmp:rw,size=512m --user "$(id -u):$(id -g)" \
    -e PYTHONDONTWRITEBYTECODE=1 -e MPLCONFIGDIR=/tmp/mpl -e OMP_NUM_THREADS=2 -e OPENBLAS_NUM_THREADS=2 \
    --mount "type=bind,src=$repo_root/scripts/phd/local_complementary_refinement_v1/evaluation_maps_v2.py,dst=/audit/evaluation_maps_v2.py,readonly" \
    --mount "type=bind,src=$evaluation_host,dst=$evaluation,readonly" \
    --mount "type=bind,src=$task_root/contracts/main_v2/experiment_v2.json,dst=/task/contracts/main_v2/experiment_v2.json,readonly" \
    --mount "type=bind,src=$task_root/main_v2/maps,dst=/task/main_v2/maps" \
    "$image" python /audit/evaluation_maps_v2.py --evaluation "$evaluation" \
      --config /task/contracts/main_v2/experiment_v2.json --output /task/main_v2/maps
