#!/usr/bin/env bash
# Caller owns its task GPU lock; the driver owns the shared extraction lock.
set -euo pipefail
region="${1:?P1 P2 P3}"
condition="${2:?Condition ID}"
gpu="${3:?0 or 1}"
family="${4:-primary}"
case "$region" in P1|P2|P3) ;; *) exit 2 ;; esac
case "$condition" in D005_Pnative|D0005_Pnative|D0_Pnative|D005_Prelease|D0005_Prelease|D0_Prelease) ;; *) exit 2 ;; esac
case "$gpu" in 0|1) ;; *) exit 2 ;; esac
case "$family" in primary) ;; native_repeat_1) test "$condition" = D005_Pnative ;; *) exit 2 ;; esac
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
task_root="$repo_root/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1"
output="$task_root/extraction_resource_v3/$family/$region/$condition"
image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
test "$(docker image inspect jointbuildgs:geogs-official-db40c95-compat-v1 --format '{{.Id}}')" = "$image"
test ! -e "$output"
mkdir -p "$output"
cp -p -- "${BASH_SOURCE[0]}" "$output/launcher_snapshot.sh"
repeat_env=()
if [[ "$family" == native_repeat_1 ]]; then
  repeat_env=(--env JBGS_REPEAT_ID=native_repeat_1 --env JBGS_REPEAT_CONTRACT_SHA256=3c62494f13de96dba33b1c36cbadf58e555305fee01ce641dd41f560bdfacafc)
fi
exec docker run --rm --name "jbgs-geogs-${region}-${condition}-auxiliary-resource-v3-${family}" --cidfile "$output/container_id.txt" \
  --network none --gpus "device=$gpu" --cpus 8 --memory 32g --shm-size 4g --user "$(id -u):$(id -g)" \
  --env JBGS_RUNTIME_IMAGE_ID="$image" --env JBGS_RUNTIME_REVISION=allocator_v2 \
  --env PYTORCH_CUDA_ALLOC_CONF=backend:native,max_split_size_mb:128 --env PYTHONDONTWRITEBYTECODE=1 \
  --env LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6 --env TORCH_HOME=/weights/torch --env MPLCONFIGDIR=/tmp/geogs-matplotlib \
  --env OMP_NUM_THREADS=8 --env OPENBLAS_NUM_THREADS=8 "${repeat_env[@]}" \
  --mount "type=bind,src=$task_root,dst=/task,readonly" \
  --mount "type=bind,src=$repo_root/scripts/phd/geogs_p1p2p3_v1,dst=/audit,readonly" \
  --mount "type=bind,src=$task_root/sources/GeoGS-state-camera-v1,dst=/source,readonly" \
  --mount "type=bind,src=$task_root/inputs/$region,dst=/input,readonly" \
  --mount "type=bind,src=$task_root/runtime/weights,dst=/weights,readonly" \
  --mount "type=bind,src=$output,dst=/output" "$image" python /audit/run_auxiliary_resource_v3.py \
  --region "$region" --condition "$condition" --run-family "$family"
