#!/usr/bin/env bash
set -euo pipefail
b_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
b_artifacts=$(realpath "$b_repo/../JointBuildGS-artifacts")
b_config=${1:-configs/phd/p2_ab_v1/b_prior_v1.json}
b_run=${2:-PHD-P2-AB-B-PRIOR-v1}
b_parent="$b_artifacts/phase-payloads/phd/p2_ab_v1"
b_output="$b_parent/$b_run"
b_cache="$b_parent/PHD-P2-AB-B-RUNTIME-v1"
b_image=$(docker image inspect jointbuildgs:dev --format '{{.Id}}')
b_head=$(git -C "$b_repo" rev-parse HEAD)
mkdir -p "$b_parent"
mkdir "$b_output"
if [[ ! -d "$b_cache" ]]; then
  mkdir "$b_cache"
  cp -a "$b_artifacts/phase-payloads/p2/e4_local_4906982_55v_als_prior_v1/P2-E4-LOCAL-4906982-55V-ALS-PRIOR-v1/cache/torch_extensions/." "$b_cache/"
fi
docker run --rm --network none --gpus '"device=1"' --cpus 4 --memory 12g \
  --entrypoint python \
  --mount "type=bind,src=$b_repo,dst=/workspace/JointBuildGS,readonly" \
  --mount "type=bind,src=$b_artifacts,dst=/artifacts/JointBuildGS,readonly" \
  --mount "type=bind,src=$b_output,dst=/output" \
  --mount "type=bind,src=$b_cache,dst=/root/.cache/torch_extensions" \
  --workdir /workspace/JointBuildGS \
  --env PYTHONDONTWRITEBYTECODE=1 --env OMP_NUM_THREADS=2 --env OPENBLAS_NUM_THREADS=1 \
  --env MAX_JOBS=2 --env "JBGS_SOURCE_GIT_HEAD=$b_head" --env "JBGS_CONTAINER_IMAGE_ID=$b_image" \
  "$b_image" -m scripts.phd.p2_ab_v1.b_run --config "$b_config" \
  2>&1 | tee "$b_parent/$b_run.console.log"
