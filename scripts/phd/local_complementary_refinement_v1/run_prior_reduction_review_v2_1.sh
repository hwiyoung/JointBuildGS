#!/usr/bin/env bash
# Read-only additional diagnostic; never alters the active frozen orchestration.
set -euo pipefail
(( $# == 0 ))
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
task_root=$(realpath "$repo/../JointBuildGS-artifacts/phase-payloads/phd/local_complementary_refinement_v1/PHD-LOCAL-COMPLEMENTARY-REFINEMENT-v1")
parent_root=$(realpath "$repo/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1")
output="$task_root/main_v2/prior_reduction_review_v2_1"
mkdir -p "$output"
launch=$(mktemp -d "$output/launch_$(date -u +%Y%m%dT%H%M%SZ)_XXXXXX")
cp "$repo/scripts/phd/local_complementary_refinement_v1/compare_prior_reduction_v2_1.py" "${BASH_SOURCE[0]}" "$launch/"
cp "$task_root/main_v2/review_site/current.json" "$launch/review_packet.json"
cp "$task_root/contracts/main_v2/experiment_v2.json" "$launch/experiment_v2.json"
image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
command=(docker run --rm --read-only --network none --cpus 2 --memory 4g --memory-swap 4g -w /tmp \
 --user "$(id -u):$(id -g)" -e PYTHONDONTWRITEBYTECODE=1 -e OMP_NUM_THREADS=2 -e OPENBLAS_NUM_THREADS=2 \
 --mount "type=bind,src=$launch/compare_prior_reduction_v2_1.py,dst=/audit/compare_prior_reduction_v2_1.py,readonly" \
 --mount "type=bind,src=$task_root/main_v2,dst=/task,readonly" \
 --mount "type=bind,src=$launch/review_packet.json,dst=/task/review_site/current.json,readonly" \
 --mount "type=bind,src=$parent_root,dst=/parent,readonly" --mount "type=bind,src=$output,dst=/out" \
 "$image" python /audit/compare_prior_reduction_v2_1.py --task /task --parent /parent --output /out)
printf '%q ' "${command[@]}" > "$launch/command.sh"
printf '\n' >> "$launch/command.sh"
set +e
"${command[@]}" > "$launch/stdout.log" 2> "$launch/stderr.log"
code=$?
set -e
printf '%s\n' "$code" > "$launch/exit_code.txt"
cat "$launch/stdout.log"
if (( code )); then cat "$launch/stderr.log" >&2; fi
exit "$code"
