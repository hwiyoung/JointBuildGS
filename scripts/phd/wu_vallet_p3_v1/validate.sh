#!/usr/bin/env bash
set -euo pipefail
p3_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
p3_image=$(docker image inspect jointbuildgs:dev --format '{{.Id}}')
for p3_script in "$p3_repo"/scripts/phd/wu_vallet_p3_v1/*.sh; do
  bash -n "$p3_script"
done
docker run --rm --network none --cpus 2 --memory 4g --entrypoint python \
  --mount "type=bind,src=$p3_repo,dst=/workspace/JointBuildGS,readonly" \
  --workdir /workspace/JointBuildGS --env PYTHONDONTWRITEBYTECODE=1 \
  --env OMP_NUM_THREADS=1 --env OPENBLAS_NUM_THREADS=1 \
  "$p3_image" -m unittest -v \
  tests.phd.test_wu_vallet_ray_update \
  tests.phd.test_wu_vallet_sensor_mesh \
  tests.phd.test_wu_vallet_evaluation
