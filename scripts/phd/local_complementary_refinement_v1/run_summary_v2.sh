#!/usr/bin/env bash
# Only one completed evaluation attempt, its frozen config, and code are readable.
set -euo pipefail
evaluation_container="${1:?Expected /task/main_v2/evaluation/attempt_<id>}"
shift
case "$evaluation_container" in /task/main_v2/evaluation/attempt_*) ;; *) echo 'Unexpected evaluation attempt path' >&2; exit 2 ;; esac
[[ "$evaluation_container" != *'..'* ]] || exit 2
if (( $# > 1 )); then echo 'Only --allow-partial may follow the evaluation path' >&2; exit 2; fi
if (( $# == 1 )); then [[ "$1" == --allow-partial ]] || exit 2; fi
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
task_root="$repo_root/../JointBuildGS-artifacts/phase-payloads/phd/local_complementary_refinement_v1/PHD-LOCAL-COMPLEMENTARY-REFINEMENT-v1"
evaluation_root="$task_root/${evaluation_container#/task/}"
config="$task_root/contracts/main_v2/experiment_v2.json"
output_root="$task_root/main_v2/summary"
image='jointbuildgs:geogs-official-db40c95-compat-v1'
[[ "$(docker image inspect --format '{{.Id}}' "$image")" == sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e ]] || exit 1
test -s "$evaluation_root/receipt.json"
test -s "$config"
mkdir -p "$output_root"
exec docker run --rm --network none --read-only --cpus 2 --memory 16g --memory-swap 16g \
  --user "$(id -u):$(id -g)" --tmpfs /tmp:rw,size=256m \
  -e PYTHONDONTWRITEBYTECODE=1 -e OMP_NUM_THREADS=2 -e OPENBLAS_NUM_THREADS=2 \
  --mount "type=bind,src=$repo_root,dst=/workspace,readonly" \
  --mount "type=bind,src=$evaluation_root,dst=/evaluation,readonly" \
  --mount "type=bind,src=$config,dst=/config/experiment_v2.json,readonly" \
  --mount "type=bind,src=$output_root,dst=/summary" \
  -w /workspace "$image" python scripts/phd/local_complementary_refinement_v1/summarize_results_v2.py \
  --evaluation /evaluation --config /config/experiment_v2.json --output /summary "$@"
