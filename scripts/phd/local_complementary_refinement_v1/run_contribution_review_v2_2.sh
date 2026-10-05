#!/usr/bin/env bash
# Independent additive diagnosis. Does not modify frozen training or automation.
set -euo pipefail
(( $# == 0 ))
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
task_root=$(realpath "$repo/../JointBuildGS-artifacts/phase-payloads/phd/local_complementary_refinement_v1/PHD-LOCAL-COMPLEMENTARY-REFINEMENT-v1")
parent_root=$(realpath "$repo/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1")
output="$task_root/main_v2/contribution_review_v2_2"
mkdir -p "$output"
launch=$(mktemp -d "$output/launch_$(date -u +%Y%m%dT%H%M%SZ)_XXXXXX")
cp "$repo/scripts/phd/local_complementary_refinement_v1/analyze_contribution_v2_2.py" "${BASH_SOURCE[0]}" "$launch/"
cp "$repo/configs/phd/local_complementary_refinement_v1/contribution_review_v2_2.json" "$launch/"
git -C "$repo" rev-parse HEAD > "$launch/git_commit.txt"
image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
command=(docker run --rm --read-only --network none --cpus 2 --memory 4g --memory-swap 4g -w /tmp \
 --user "$(id -u):$(id -g)" -e PYTHONDONTWRITEBYTECODE=1 -e OMP_NUM_THREADS=2 -e OPENBLAS_NUM_THREADS=2 -e MPLCONFIGDIR=/tmp/mpl \
 --tmpfs /tmp:rw,nosuid,size=128m \
 --mount "type=bind,src=$launch,dst=/audit,readonly" \
 --mount "type=bind,src=$task_root/main_v2,dst=/task,readonly" \
 --mount "type=bind,src=$parent_root,dst=/parent,readonly" --mount "type=bind,src=$output,dst=/out" \
 "$image" python /audit/analyze_contribution_v2_2.py --task /task --parent /parent --config /audit/contribution_review_v2_2.json --output /out)
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
