#!/usr/bin/env bash
set -euo pipefail
(( $# == 1 ))
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
task_root=$(realpath "$repo/../JointBuildGS-artifacts/phase-payloads/phd/local_complementary_refinement_v1/PHD-LOCAL-COMPLEMENTARY-REFINEMENT-v1")
mkdir -p "$task_root/main_v2/normal_photometry_v3_7/browser_qa"
output=$(mktemp -d "$task_root/main_v2/normal_photometry_v3_7/browser_qa/attempt_$(date -u +%Y%m%dT%H%M%SZ)_XXXXXX")
cp "$repo/scripts/phd/local_complementary_refinement_v1/browser_normal_photometry_v3_7.mjs" "${BASH_SOURCE[0]}" "$output/"
git -C "$repo" rev-parse HEAD > "$output/git_commit.txt"
image=sha256:5043f84d76db9d54e64fcf457125aad90ac5423fded88eca6cf487d2b4713a9e
command=(docker run --rm --read-only --network host --cpus 2 --memory 3g --memory-swap 3g -w /tmp --user "$(id -u):$(id -g)" \
 --tmpfs /tmp:rw,exec,size=512m \
 --mount "type=bind,src=$output,dst=/out" \
 --mount "type=bind,src=$task_root/main_v2/review_site,dst=/site,readonly" \
 --entrypoint node "$image" /out/browser_normal_photometry_v3_7.mjs "$1" /out /site)
printf '%q ' "${command[@]}" > "$output/command.sh"
printf '\n' >> "$output/command.sh"
printf '%s\n' "$output"
set +e
"${command[@]}" > "$output/stdout.log" 2> "$output/stderr.log"
code=$?
set -e
printf '%s\n' "$code" > "$output/exit_code.txt"
cat "$output/stdout.log"
if (( code )); then cat "$output/stderr.log" >&2; fi
exit "$code"
