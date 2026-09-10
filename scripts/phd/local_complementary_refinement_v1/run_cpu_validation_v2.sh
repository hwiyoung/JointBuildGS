#!/usr/bin/env bash
# Additive integration validation; the frozen readiness receipt remains intact.
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
task_root=$(realpath "$repo/../JointBuildGS-artifacts/phase-payloads/phd/local_complementary_refinement_v1/PHD-LOCAL-COMPLEMENTARY-REFINEMENT-v1")
parent_root=$(realpath "$repo/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1")
label=${1:?unique validation label}
[[ $label =~ ^[a-zA-Z0-9_-]+$ ]]
output="$task_root/main_v2/validation/$label"
[[ ! -e $output ]]
image_id='sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e'
[[ $(docker image inspect jointbuildgs:geogs-official-db40c95-compat-v1 --format '{{.Id}}') == "$image_id" ]]
mkdir "$output"
cp -- "${BASH_SOURCE[0]}" "$output/launcher_snapshot.sh"
cp -a -- "$repo/scripts/phd/local_complementary_refinement_v1" "$output/helper_snapshots"
cp -a -- "$repo/tests/phd/local_complementary_refinement_v1" "$output/test_snapshots"
exec docker run --rm --network none --read-only --cpus 2 --memory 4g --memory-swap 4g \
  --tmpfs /tmp:rw,exec,size=512m --user "$(id -u):$(id -g)" \
  -e PYTHONDONTWRITEBYTECODE=1 -e OMP_NUM_THREADS=2 -e OPENBLAS_NUM_THREADS=2 \
  -e MPLCONFIGDIR=/tmp/mpl -e LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6 \
  -e "JBGS_RUNTIME_IMAGE_ID=$image_id" -e "JBGS_REPOSITORY_COMMIT=$(git -C "$repo" rev-parse HEAD)" \
  --mount "type=bind,src=$repo,dst=/workspace,readonly" \
  --mount "type=bind,src=$parent_root/sources/GeoGS-state-camera-v1,dst=/parent_source,readonly" \
  --mount "type=bind,src=$task_root/contracts/main_v2/experiment_v2.json,dst=/config.json,readonly" \
  --mount "type=bind,src=$output,dst=/validation" -w /workspace "$image_id" \
  python /workspace/scripts/phd/local_complementary_refinement_v1/validate_cpu_v2.py
