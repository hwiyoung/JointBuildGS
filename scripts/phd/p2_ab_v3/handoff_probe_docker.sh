#!/usr/bin/env bash
set -euo pipefail
v3_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
v3_artifacts=$(realpath "$v3_repo/../JointBuildGS-artifacts")
v3_run="$v3_artifacts/phase-payloads/phd/p2_ab_v3/PHD-P2-AB-V3-HANDOFF-v1"
v3_image=$(docker image inspect jointbuildgs:dev --format '{{.Id}}')
v3_head=$(git -C "$v3_repo" rev-parse HEAD)
mkdir -p "$(dirname "$v3_run")"
mkdir "$v3_run"
docker run --rm --network none --cpus 2 --memory 4g --entrypoint python \
  --mount "type=bind,src=$v3_repo,dst=/workspace/JointBuildGS,readonly" \
  --mount "type=bind,src=$v3_artifacts,dst=/artifacts/JointBuildGS,readonly" \
  --mount "type=bind,src=$v3_run,dst=/output" \
  --workdir /workspace/JointBuildGS --env PYTHONDONTWRITEBYTECODE=1 \
  --env "JBGS_SOURCE_GIT_HEAD=$v3_head" --env "JBGS_CONTAINER_IMAGE_ID=$v3_image" \
  "$v3_image" -m scripts.phd.p2_ab_v3.handoff_probe \
  --config configs/phd/p2_ab_v3/handoff_probe_v1.json --output /output/return \
  2>&1 | tee "$v3_run/console.log"
