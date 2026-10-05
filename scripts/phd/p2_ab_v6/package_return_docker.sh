#!/usr/bin/env bash
set -euo pipefail
v6_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
v6_artifacts=$(realpath "$v6_repo/../JointBuildGS-artifacts")
v6_run="$v6_artifacts/phase-payloads/phd/p2_ab_v6/${1:-PHD-P2-AB-V6-RETURN-v1}"
v6_qa=${2:-PHD-P2-AB-V6-BROWSER-QA-v1}
v6_image=$(docker image inspect jointbuildgs:dev --format '{{.Id}}')
v6_head=$(git -C "$v6_repo" rev-parse HEAD)
mkdir "$v6_run"
docker run --rm --network none --cpus 3 --memory 6g --entrypoint python \
  --mount "type=bind,src=$v6_repo,dst=/workspace/JointBuildGS,readonly" \
  --mount "type=bind,src=$v6_artifacts,dst=/artifacts/JointBuildGS,readonly" \
  --mount "type=bind,src=$v6_run,dst=/output" --workdir /workspace/JointBuildGS \
  --env PYTHONDONTWRITEBYTECODE=1 --env "JBGS_SOURCE_GIT_HEAD=$v6_head" \
  --env "JBGS_CONTAINER_IMAGE_ID=$v6_image" "$v6_image" \
  -m scripts.phd.p2_ab_v6.package_return --output /output/return --qa-run "$v6_qa" \
  2>&1 | tee "$v6_run/console.log"
