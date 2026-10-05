#!/usr/bin/env bash
# Usage: bash .../c_run_docker.sh geometry|appearance|viewer|summary NEW_RUN_ID [CONFIG]
set -euo pipefail
c_stage=${1:?stage required}
c_run=${2:?new run ID required}
c_config=${3:-configs/phd/p2_ab_v2/c_final_v1.json}
[[ "$c_stage" =~ ^(geometry|appearance|viewer|summary)$ ]]
[[ "$c_run" =~ ^PHD-P2-AB-V2-[A-Z0-9-]+-v[0-9]+$ ]]
c_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
c_artifacts=$(realpath "$c_repo/../JointBuildGS-artifacts")
c_output="$c_artifacts/phase-payloads/phd/p2_ab_v2/$c_run"
mkdir -- "$c_output"
docker run --rm --network none --cpus 4 --memory 12g --entrypoint python \
  --mount "type=bind,src=$c_repo,dst=/workspace/JointBuildGS,readonly" \
  --mount "type=bind,src=$c_artifacts,dst=/artifacts/JointBuildGS,readonly" \
  --mount "type=bind,src=$c_output,dst=/output_parent" \
  --workdir /workspace/JointBuildGS --env PYTHONDONTWRITEBYTECODE=1 --env OPENBLAS_NUM_THREADS=1 \
  --env "JBGS_SOURCE_GIT_HEAD=$(git -C "$c_repo" rev-parse HEAD)" \
  --env "JBGS_CONTAINER_IMAGE_ID=$(docker image inspect jointbuildgs:dev --format '{{.Id}}')" \
  jointbuildgs:dev -m scripts.phd.p2_ab_v2.c_pipeline \
  --config "$c_config" --stage "$c_stage" --output "/output_parent/$c_stage" \
  > "$c_output/execution.log" 2>&1
cat "$c_output/execution.log"
