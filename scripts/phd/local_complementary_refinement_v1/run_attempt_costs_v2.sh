#!/usr/bin/env bash
# Receipt/log/device samples only; no model payload, image or GT is exposed.
set -euo pipefail
(( $# == 0 ))
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
task_root=$(realpath "$repo/../JointBuildGS-artifacts/phase-payloads/phd/local_complementary_refinement_v1/PHD-LOCAL-COMPLEMENTARY-REFINEMENT-v1")
image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
[[ $(docker image inspect jointbuildgs:geogs-official-db40c95-compat-v1 --format '{{.Id}}') == "$image" ]]
test -s "$task_root/main_v2/run_selection_v2.json"
mkdir -p "$task_root/main_v2/attempt_costs"
mounts=(--mount "type=bind,src=$repo/scripts/phd/local_complementary_refinement_v1/attempt_costs_v2.py,dst=/audit/attempt_costs_v2.py,readonly"
 --mount "type=bind,src=$repo/scripts/phd/local_complementary_refinement_v1/run_selection_v2.py,dst=/audit/run_selection_v2.py,readonly"
 --mount "type=bind,src=$task_root/contracts/main_v2/experiment_v2.json,dst=/contracts/experiment_v2.json,readonly"
 --mount "type=bind,src=$task_root/contracts/main_v2/input_binding.json,dst=/contracts/input_binding.json,readonly"
 --mount "type=bind,src=$task_root/main_v2/run_selection_v2.json,dst=/task/main_v2/run_selection_v2.json,readonly"
 --mount "type=bind,src=$task_root/main_v2/attempt_costs,dst=/output")
shopt -s nullglob
for file in "$task_root"/main_v2/runs/P[123]/*/{train_receipt,render_receipt,metrics_receipt}.json \
 "$task_root"/main_v2/runs/P[123]/*/{train,render,metrics}_gpu.csv \
 "$task_root"/main_v2/runs/P[123]/*/train.log \
 "$task_root"/main_v2/retries/*/{train_receipt,render_receipt,metrics_receipt}.json \
 "$task_root"/main_v2/retries/*/{train,render,metrics}_gpu.csv \
 "$task_root"/main_v2/retries/*/train.log; do
 [[ $(readlink -f "$file") == "$file" ]]
 mounts+=(--mount "type=bind,src=$file,dst=/task/${file#"$task_root/"},readonly")
done
exec docker run --rm --read-only --network none --cpus 1 --memory 512m --memory-swap 512m \
 --user "$(id -u):$(id -g)" -e PYTHONDONTWRITEBYTECODE=1 "${mounts[@]}" "$image" \
 python /audit/attempt_costs_v2.py --task /task/main_v2 --config /contracts/experiment_v2.json \
 --binding /contracts/input_binding.json --selection /task/main_v2/run_selection_v2.json --output /output
