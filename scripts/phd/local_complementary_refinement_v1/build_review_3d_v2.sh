#!/usr/bin/env bash
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
task_root=$(realpath "$repo/../JointBuildGS-artifacts/phase-payloads/phd/local_complementary_refinement_v1/PHD-LOCAL-COMPLEMENTARY-REFINEMENT-v1")
parent_root=$(realpath "$repo/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1")
mkdir -p "$task_root/main_v2/review_3d"
exec docker run --rm --read-only --network none --cpus 2 --memory 4g --memory-swap 4g -w /workspace --user "$(id -u):$(id -g)" -e PYTHONDONTWRITEBYTECODE=1 -e OMP_NUM_THREADS=2 -e OPENBLAS_NUM_THREADS=2 --tmpfs /tmp:rw,nosuid,size=128m \
 --mount "type=bind,src=$repo,dst=/workspace,readonly" --mount "type=bind,src=$task_root/main_v2,dst=/task,readonly" \
 --mount "type=bind,src=$parent_root/evaluation,dst=/parent_evaluation,readonly" --mount "type=bind,src=$task_root/main_v2/review_3d,dst=/site" \
 sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e \
 python /workspace/scripts/phd/local_complementary_refinement_v1/build_review_3d_v2.py --task /task --parent-evaluation /parent_evaluation --app /workspace/src/apps/local_complementary_3d_v2 --output /site
