#!/usr/bin/env bash
set -euo pipefail
attempt=${1:?absolute attempt path}
region=${2:?P2 or P3}
case "$region" in P2|P3) ;; *) exit 2;; esac
repo=$(cd "$(dirname "$0")/../../.." && pwd)
base="$repo/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1"
gpu=GPU-4bdfcab8-1464-94b0-0a2f-dd9693ace2a0
free_mib=$(nvidia-smi --id="$gpu" --query-gpu=memory.free --format=csv,noheader,nounits)
[[ "$free_mib" -ge 20000 ]] || { echo 'GPU0 unavailable for isolated screening' >&2; exit 3; }
test -s "$attempt/prepare_screen/receipt.json"
mkdir -p "$attempt/screen"
test ! -e "$attempt/screen/$region"
driver="$attempt/frozen/association_screen.py"
test -s "$driver"
helper_sha=$(sha256sum "$attempt/frozen/gaussian_probe.py")
helper_sha=${helper_sha%% *}
image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
docker run --rm --name "jbgs-surface-screen-$region" --network none \
  --gpus "device=$gpu" --cpus 4 --memory 24g --memory-swap 24g --shm-size 2g \
  --user "$(id -u):$(id -g)" --entrypoint /opt/geogs/bin/python \
  -e JBGS_RUNTIME_IMAGE_ID="$image" -e LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6 \
  -e PYTHONDONTWRITEBYTECODE=1 -e OPENBLAS_NUM_THREADS=1 -e OMP_NUM_THREADS=4 \
  -e PYTORCH_CUDA_ALLOC_CONF=backend:native,max_split_size_mb:128 -e MPLCONFIGDIR=/tmp/mpl \
  -v "$attempt/frozen:/frozen:ro" -v "$attempt/prepare_screen/cases.json:/cases.json:ro" \
  -v "$base/sources/GeoGS-state-camera-v1:/source:ro" \
  -v "$base/runs_allocator_v2/$region/D005_Pnative/model/jbgs_complete/iteration_8000:/anchor:ro" \
  -v "$base/inputs:/inputs:ro" -v "$attempt/screen:/output" \
  "$image" /frozen/association_screen.py --cases /cases.json --region "$region" \
  --source /source --anchor /anchor --inputs /inputs --output "/output/$region" \
  --probe-helper /frozen/gaussian_probe.py --probe-helper-sha256 "$helper_sha" \
  2>&1 | tee "$attempt/screen_${region}.log"
