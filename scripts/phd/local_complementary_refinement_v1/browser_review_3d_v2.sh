#!/usr/bin/env bash
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
task_root=$(realpath "$repo/../JointBuildGS-artifacts/phase-payloads/phd/local_complementary_refinement_v1/PHD-LOCAL-COMPLEMENTARY-REFINEMENT-v1")
out="$task_root/main_v2/review_3d/browser_qa/attempt_$(date -u +%Y%m%dT%H%M%S)_$RANDOM"
mkdir -p "$out"
cp "$repo/scripts/phd/local_complementary_refinement_v1/browser_review_3d_v2.mjs" "$repo/scripts/phd/local_complementary_refinement_v1/browser_review_3d_v2.sh" "$out/"
docker run --rm --read-only --network host --cpus 2 --memory 3g --memory-swap 3g --tmpfs /tmp:rw,nosuid,size=1g --shm-size 512m \
 --mount "type=bind,src=$repo/scripts/phd/local_complementary_refinement_v1/browser_review_3d_v2.mjs,dst=/qa/qa.mjs,readonly" --mount "type=bind,src=$out,dst=/out" \
 sha256:5043f84d76db9d54e64fcf457125aad90ac5423fded88eca6cf487d2b4713a9e /qa/qa.mjs "${1:-http://127.0.0.1:8906}" /out
printf '%s\n' "$out/receipt.json"
