#!/usr/bin/env bash
set -euo pipefail
c_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
c_artifacts=$(realpath "$c_repo/../JointBuildGS-artifacts")
c_parent="$c_artifacts/phase-payloads/phd/p2_ab_v1"
c_run=${1:?New run ID required}
shift
if [[ ! "$c_run" =~ ^PHD-P2-AB-C-[A-Za-z0-9_-]+$ ]]; then
  echo 'Invalid evaluation run ID' >&2
  exit 2
fi
test ! -e "$c_parent/$c_run"
c_image='sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774'
c_args=()
for c_b in "$@"; do
  if [[ ! "$c_b" =~ ^PHD-P2-AB-B-[A-Za-z0-9_-]+$ ]]; then
    echo 'Invalid B run ID' >&2
    exit 2
  fi
  c_args+=(--b-root "/artifacts/JointBuildGS/phase-payloads/phd/p2_ab_v1/$c_b")
done
docker run --rm --network none --cpus 4 --memory 6g \
  --user "$(id -u):$(id -g)" --entrypoint python \
  --mount "type=bind,src=$c_repo,dst=/workspace/JointBuildGS,readonly" \
  --mount "type=bind,src=$c_artifacts,dst=/artifacts/JointBuildGS,readonly" \
  --mount "type=bind,src=$c_parent,dst=/new-results" \
  --workdir /workspace/JointBuildGS --env PYTHONDONTWRITEBYTECODE=1 \
  --env OPENBLAS_NUM_THREADS=1 --env OMP_NUM_THREADS=1 \
  "$c_image" -m scripts.phd.p2_ab_v1.c_evaluate \
  --common /artifacts/JointBuildGS/phase-payloads/phd/p2_ab_v1/PHD-P2-AB-COMMON-v2/common \
  --reference /artifacts/JointBuildGS/phase-payloads/phd/p2_ab_v1/PHD-P2-AB-COMMON-v2/evaluation_v2 \
  --a-root /artifacts/JointBuildGS/phase-payloads/phd/p2_ab_v1/PHD-P2-AB-A-v1 \
  --output "/new-results/$c_run" "${c_args[@]}" 2>&1 | tee "$c_parent/$c_run.console.log"
