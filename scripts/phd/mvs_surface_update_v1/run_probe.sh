#!/usr/bin/env bash
set -euo pipefail
attempt=${1:?absolute output attempt containing prepare_v2}
region=${2:?P1 P2 P3}
case "$region" in P1|P2|P3) ;; *) exit 2;; esac
repo=$(cd "$(dirname "$0")/../../.." && pwd)
base="$repo/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1"
source_path="$base/sources/GeoGS-state-camera-v1"
anchor="$base/runs_allocator_v2/$region/D005_Pnative/model/jbgs_complete/iteration_8000"
if [[ "$region" == P1 ]]; then anchor="$base/runs/P1/D005_Pnative/model/jbgs_complete/iteration_8000"; fi
gpu=GPU-4bdfcab8-1464-94b0-0a2f-dd9693ace2a0
free_mib=$(nvidia-smi --id="$gpu" --query-gpu=memory.free --format=csv,noheader,nounits)
[[ "$free_mib" -ge 20000 ]] || { echo 'GPU0 not free for isolated probe' >&2; exit 3; }
test -s "$attempt/prepare_v2/receipt.json"
test -s "$attempt/frozen/gaussian_probe.py"
mkdir -p "$attempt/probe"
test ! -e "$attempt/probe/$region"
image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
docker run --rm --name "jbgs-surface-probe-$region-$(basename "$attempt")" --network none \
  --gpus "device=$gpu" --cpus 4 --memory 24g --memory-swap 24g --shm-size 2g \
  --user "$(id -u):$(id -g)" --entrypoint /opt/geogs/bin/python \
  -e JBGS_RUNTIME_IMAGE_ID="$image" -e LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6 \
  -e PYTHONDONTWRITEBYTECODE=1 -e OPENBLAS_NUM_THREADS=1 -e OMP_NUM_THREADS=4 \
  -e PYTORCH_CUDA_ALLOC_CONF=backend:native,max_split_size_mb:128 \
  -e MPLCONFIGDIR=/tmp/mpl \
  -v "$attempt/frozen:/audit:ro" -v "$attempt/prepare_v2/cases.json:/cases.json:ro" \
  -v "$source_path:/source:ro" -v "$anchor:/anchor:ro" -v "$base/inputs:/inputs:ro" \
  -v "$attempt/probe:/output" "$image" /audit/gaussian_probe.py \
  --cases /cases.json --region "$region" --source /source --anchor /anchor --inputs /inputs --output "/output/$region" \
  2>&1 | tee "$attempt/probe_${region}.log"
