#!/usr/bin/env bash
set -euo pipefail
a_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
a_artifacts=$(realpath "$a_repo/../JointBuildGS-artifacts")
a_parent="$a_artifacts/phase-payloads/phd/p2_ab_v1"
a_output="$a_parent/PHD-P2-AB-A-v1"
a_image='sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774'
a_head=$(git -C "$a_repo" rev-parse HEAD)
docker image inspect "$a_image" >/dev/null
mkdir -p "$a_parent"
mkdir "$a_output"
docker run --rm --network none --cpus 4 --memory 6g --user "$(id -u):$(id -g)" --entrypoint python \
  --mount "type=bind,src=$a_repo,dst=/workspace/JointBuildGS,readonly" \
  --mount "type=bind,src=$a_artifacts,dst=/artifacts/JointBuildGS,readonly" \
  --mount "type=bind,src=$a_output,dst=/output" --workdir /workspace/JointBuildGS \
  --env PYTHONDONTWRITEBYTECODE=1 --env OPENBLAS_NUM_THREADS=1 --env OMP_NUM_THREADS=1 \
  --env "JBGS_SOURCE_GIT_HEAD=$a_head" --env "JBGS_CONTAINER_IMAGE_ID=$a_image" \
  "$a_image" -m scripts.phd.p2_ab_v1.a_run --config configs/phd/p2_ab_v1/a_p2_v1.json \
  2>&1 | tee "$a_parent/PHD-P2-AB-A-v1.console.log"
