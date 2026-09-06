#!/usr/bin/env bash
set -euo pipefail
a_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
a_artifacts=$(realpath "$a_repo/../JointBuildGS-artifacts")
a_config=${1:-configs/phd/p2_ab_v6/a_observational_envelope_v3.json}
a_run=${2:-PHD-P2-AB-V6-A-OBSERVATIONAL-v3}
a_parent="$a_artifacts/phase-payloads/phd/p2_ab_v6"
a_output="$a_parent/$a_run"
a_image=$(docker image inspect jointbuildgs:dev --format '{{.Id}}')
a_head=$(git -C "$a_repo" rev-parse HEAD)
mkdir -p "$a_parent"
mkdir "$a_output"
docker run --rm --network none --cpus 6 --memory 20g --entrypoint python \
  --mount "type=bind,src=$a_repo,dst=/workspace/JointBuildGS,readonly" \
  --mount "type=bind,src=$a_artifacts,dst=/artifacts/JointBuildGS,readonly" \
  --mount "type=bind,src=$a_output,dst=/output" \
  --workdir /workspace/JointBuildGS \
  --env PYTHONDONTWRITEBYTECODE=1 --env OMP_NUM_THREADS=2 --env OPENBLAS_NUM_THREADS=1 \
  --env "JBGS_SOURCE_GIT_HEAD=$a_head" --env "JBGS_CONTAINER_IMAGE_ID=$a_image" \
  "$a_image" -m scripts.phd.p2_ab_v6.a_observational_envelope_texture --config "$a_config" \
  2>&1 | tee "$a_parent/$a_run.console.log"
