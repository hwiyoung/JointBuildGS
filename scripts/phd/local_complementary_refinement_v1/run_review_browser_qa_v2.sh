#!/usr/bin/env bash
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
task_root=$(realpath "$repo/../JointBuildGS-artifacts/phase-payloads/phd/local_complementary_refinement_v1/PHD-LOCAL-COMPLEMENTARY-REFINEMENT-v1")
output="$task_root/main_v2/review_browser_qa/attempt_$(date -u +%Y%m%dT%H%M%SZ)_${RANDOM}"
mkdir -p "$output"
printf '%s\n' "$output"
exec docker run --rm --read-only --network host --cpus 2 --memory 2g --memory-swap 2g -w /tmp --user "$(id -u):$(id -g)" \
 --tmpfs /tmp:rw,exec,size=512m \
 --mount "type=bind,src=$repo/scripts/phd/local_complementary_refinement_v1/review_browser_qa_v2.mjs,dst=/qa.mjs,readonly" \
 --mount "type=bind,src=$output,dst=/out" --entrypoint node \
 sha256:5043f84d76db9d54e64fcf457125aad90ac5423fded88eca6cf487d2b4713a9e \
 /qa.mjs "${1:-http://127.0.0.1:8905}" /out
