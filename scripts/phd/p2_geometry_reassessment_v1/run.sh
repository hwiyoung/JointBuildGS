#!/usr/bin/env bash
set -euo pipefail
repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
source_root="$repo_root/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/geometry/P2"
report_root="$repo_root/docs/experiments/phd/p2_geometry_reassessment_v1"
image_tag=jointbuildgs:geogs-official-db40c95-compat-v1
image_id=$(docker image inspect "$image_tag" --format '{{.Id}}')
git_commit=$(git -C "$repo_root" rev-parse HEAD)
mkdir -p "$report_root"
test ! -e "$report_root/analysis"
docker run --rm --read-only --network none --cpus 4 --memory 4g \
  --tmpfs /tmp:rw,size=256m -w /tmp --user "$(id -u):$(id -g)" \
  -e OPENBLAS_NUM_THREADS=1 -e OMP_NUM_THREADS=4 -e MPLCONFIGDIR=/tmp/mpl \
  -v "$repo_root:/workspace:ro" -v "$source_root:/source:ro" -v "$report_root:/output:rw" \
  --entrypoint python "$image_tag" \
  /workspace/scripts/phd/p2_geometry_reassessment_v1/analyze.py \
  --config /workspace/configs/phd/p2_geometry_reassessment_v1/analysis.json \
  --source /source --output /output/analysis --git-commit "$git_commit" --image-id "$image_id"
docker run --rm --read-only --network none --cpus 2 --memory 2g \
  --tmpfs /tmp:rw,size=128m -w /tmp --user "$(id -u):$(id -g)" \
  -e OPENBLAS_NUM_THREADS=1 -e MPLCONFIGDIR=/tmp/mpl \
  -v "$repo_root:/workspace:ro" -v "$report_root:/output:rw" \
  --entrypoint python "$image_tag" \
  /workspace/scripts/phd/p2_geometry_reassessment_v1/validate_and_present.py \
  --analysis /output/analysis --output /output/figures
