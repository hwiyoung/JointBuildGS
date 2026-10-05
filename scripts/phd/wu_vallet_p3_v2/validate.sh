#!/usr/bin/env bash
set -euo pipefail
wv2_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
for wv2_script in "$wv2_repo"/scripts/phd/wu_vallet_p3_v2/*.sh; do bash -n "$wv2_script"; done
wv2_image=$(docker image inspect jointbuildgs:dev --format '{{.Id}}')
docker run --rm --network none --cpus 2 --memory 4g --entrypoint python \
  --mount "type=bind,src=$wv2_repo,dst=/workspace/JointBuildGS,readonly" \
  --workdir /workspace/JointBuildGS --env PYTHONDONTWRITEBYTECODE=1 \
  --env OMP_NUM_THREADS=2 --env OPENBLAS_NUM_THREADS=1 \
  "$wv2_image" -m unittest -v tests.phd.test_wu_vallet_acquisition_v2 \
  tests.phd.test_wu_vallet_trajectory_v2 tests.phd.test_wu_vallet_ray_runtime_v2
