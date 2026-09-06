#!/usr/bin/env bash
set -euo pipefail
v4_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
v4_artifacts=$(realpath "$v4_repo/../JointBuildGS-artifacts")
v4_run="$v4_artifacts/phase-payloads/phd/p2_ab_v4/PHD-P2-AB-V4-RETURN-v1"
v4_image=$(docker image inspect jointbuildgs:dev --format '{{.Id}}')
v4_head=$(git -C "$v4_repo" rev-parse HEAD)
mkdir -p "$v4_run"
docker run --rm --network none --cpus 2 --memory 4g --entrypoint python \
  --mount "type=bind,src=$v4_repo,dst=/workspace/JointBuildGS,readonly" \
  --mount "type=bind,src=$v4_artifacts,dst=/artifacts/JointBuildGS,readonly" \
  --mount "type=bind,src=$v4_run,dst=/output" --workdir /workspace/JointBuildGS \
  --env PYTHONDONTWRITEBYTECODE=1 --env "JBGS_SOURCE_GIT_HEAD=$v4_head" \
  --env "JBGS_CONTAINER_IMAGE_ID=$v4_image" "$v4_image" \
  scripts/phd/p2_ab_v4/package_return.py --output /output/return
