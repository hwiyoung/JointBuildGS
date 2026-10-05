#!/usr/bin/env bash
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
task_root=$(realpath "$repo/../JointBuildGS-artifacts/phase-payloads/phd/local_complementary_refinement_v1/PHD-LOCAL-COMPLEMENTARY-REFINEMENT-v1")
sources=${1:-/workspace/configs/phd/local_complementary_refinement_v1/review_sources_v2.json}
mkdir -p "$task_root/main_v2/review_site"
exec docker run --rm --read-only --network none --cpus 1 --memory 1g --memory-swap 1g -w /workspace --user "$(id -u):$(id -g)" -e PYTHONDONTWRITEBYTECODE=1 \
 --mount "type=bind,src=$repo,dst=/workspace,readonly" --mount "type=bind,src=$task_root/main_v2,dst=/task,readonly" \
 --mount "type=bind,src=$task_root/main_v2/review_site,dst=/site" \
 sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e \
 python /workspace/scripts/phd/local_complementary_refinement_v1/build_review_v2.py --task /task --sources "$sources" \
 --app /workspace/src/apps/local_complementary_review_v2 --output /site
