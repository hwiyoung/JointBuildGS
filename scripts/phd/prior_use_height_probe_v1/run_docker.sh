#!/usr/bin/env bash
set -euo pipefail

probe_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
probe_artifacts=$(realpath "$probe_repo/../JointBuildGS-artifacts")
probe_parent="$probe_artifacts/phase-payloads/phd/prior_use_height_probe_v1"
probe_output="$probe_parent/PHD-PRIOR-USE-HEIGHT-PROBE-v1"
probe_image='sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774'
probe_head=$(git -C "$probe_repo" rev-parse HEAD)

docker image inspect "$probe_image" >/dev/null
mkdir -p "$probe_parent"
# This must fail if a prior attempt or result already exists.
mkdir "$probe_output"
docker run --rm --network none --cpus 4 --memory 4g \
  --user "$(id -u):$(id -g)" --entrypoint python \
  --mount "type=bind,src=$probe_repo,dst=/workspace/JointBuildGS,readonly" \
  --mount "type=bind,src=$probe_artifacts,dst=/artifacts/JointBuildGS,readonly" \
  --mount "type=bind,src=$probe_output,dst=/output" \
  --workdir /workspace/JointBuildGS \
  --env PYTHONDONTWRITEBYTECODE=1 --env MPLCONFIGDIR=/tmp/probe-matplotlib \
  --env OPENBLAS_NUM_THREADS=1 --env OMP_NUM_THREADS=1 \
  --env "JBGS_SOURCE_GIT_HEAD=$probe_head" --env "JBGS_CONTAINER_IMAGE_ID=$probe_image" \
  "$probe_image" -m scripts.phd.prior_use_height_probe_v1.run \
  --config configs/phd/prior_use_height_probe_v1/p2_v1.json \
  2>&1 | tee "$probe_parent/PHD-PRIOR-USE-HEIGHT-PROBE-v1.console.log"
