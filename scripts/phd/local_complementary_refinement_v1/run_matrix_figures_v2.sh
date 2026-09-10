#!/usr/bin/env bash
# Sealed summary CSV -> static figures; no reference, model, parent or GPU mounts.
set -euo pipefail
summary=${1:?Expected /task/main_v2/summary/attempt_*}
[[ $summary == /task/main_v2/summary/attempt_* && $summary != *..* ]]
repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
task_root=$(realpath "$repo_root/../JointBuildGS-artifacts/phase-payloads/phd/local_complementary_refinement_v1/PHD-LOCAL-COMPLEMENTARY-REFINEMENT-v1")
summary_host=$(realpath "$task_root/${summary#/task/}")
[[ $summary_host == "$task_root"/main_v2/summary/attempt_* ]]
image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
[[ $(docker image inspect jointbuildgs:geogs-official-db40c95-compat-v1 --format '{{.Id}}') == "$image" ]]
test -s "$summary_host/receipt.json"
test -s "$summary_host/paired_summary.csv"
mkdir -p "$task_root/main_v2/matrix_figures"
exec docker run --rm --network none --read-only --cpus 2 --memory 4g --memory-swap 4g \
 --tmpfs /tmp:rw,size=512m --user "$(id -u):$(id -g)" \
 -e PYTHONDONTWRITEBYTECODE=1 -e MPLCONFIGDIR=/tmp/mpl -e OMP_NUM_THREADS=2 -e OPENBLAS_NUM_THREADS=2 \
 --mount "type=bind,src=$repo_root/scripts/phd/local_complementary_refinement_v1/visualize_matrix_v2.py,dst=/audit/visualize_matrix_v2.py,readonly" \
 --mount "type=bind,src=$summary_host/receipt.json,dst=$summary/receipt.json,readonly" \
 --mount "type=bind,src=$summary_host/paired_summary.csv,dst=$summary/paired_summary.csv,readonly" \
 --mount "type=bind,src=$task_root/contracts/main_v2/experiment_v2.json,dst=/config/experiment_v2.json,readonly" \
 --mount "type=bind,src=$task_root/main_v2/matrix_figures,dst=/task/main_v2/matrix_figures" \
 "$image" python /audit/visualize_matrix_v2.py --summary "$summary" --config /config/experiment_v2.json \
 --output /task/main_v2/matrix_figures
