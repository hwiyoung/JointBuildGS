#!/usr/bin/env bash
set -euo pipefail
bundle="$(realpath "${1:?bundle}")";gpu="${2:-0}";recovery="$(realpath "${3:?recovery directory}")"
payload=/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd
base="$payload/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1"
parent="$payload/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1"
viewer="$parent/viewer_rgb_v1"
image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
cpu=(docker run --rm --runtime runc --network none --cpus 2 --memory 12g --user "$(id -u):$(id -g)" -e NVIDIA_VISIBLE_DEVICES=void -e CUDA_VISIBLE_DEVICES= -e PYTHONDONTWRITEBYTECODE=1 -e OMP_NUM_THREADS=2 -e OPENBLAS_NUM_THREADS=2 -e LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6 -e MPLCONFIGDIR=/tmp/mpl)
refresh() {
 exec 8>"$bundle/refresh.lock";flock 8
 "${cpu[@]}" -v "$bundle:/bundle:ro" -v "$viewer:/viewer" "$image" python /bundle/scripts/refresh.py >> "$bundle/refresh.log" 2>&1
 flock -u 8;exec 8>&-
}

region=P1;exp="$bundle/P1";output="$viewer/prior_weights_v1/P1";stage=RECOVERY_CHECK
finish() { code=$?;if [[ "$code" -ne 0 ]];then printf 'FAIL %s exit=%s\n' "$stage" "$code" > "$exp/status.txt";refresh || true;fi; }
trap finish EXIT
test ! -e "$output/alpha_4/extraction"
"${cpu[@]}" -v "$bundle:/bundle:ro" "$image" python /bundle/scripts/verify_bundle.py
 stage=EXTRACTION;printf '%s\n' "$stage" > "$exp/status.txt";refresh
 publish_cpu() {
  "${cpu[@]}" -v "$recovery/driver:/driver:ro" -v "$parent/sources/GeoGS-mvs-pgsr-v1:/source:ro" -v "$base/inputs/$region:/input:ro" \
   -v "$exp:/experiment:ro" -v "$exp/viewer_config.json:/viewer_config.json:ro" -v "$output:/output" "$image" python /driver/viewer_publish.py "$@"
 }
 publish_cpu stage --alpha 4 > "$recovery/display_stage.log" 2>&1
 exec 9>"/tmp/jbgs-p1-single-view-gpu-$gpu.lock";flock 9
 while (( $(nvidia-smi --id="$gpu" --query-gpu=memory.used --format=csv,noheader,nounits) > 1500 ));do sleep 30;done
 docker run --rm --name "jbgs-prior0005-$region-extract" --network none --gpus "device=$gpu" --cpus 8 --memory 32g --shm-size 4g --user "$(id -u):$(id -g)" \
  -e TORCH_HOME=/weights/torch -e MPLCONFIGDIR=/tmp/mpl -e LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6 -e OMP_NUM_THREADS=8 -e OPENBLAS_NUM_THREADS=8 -e PYTHONDONTWRITEBYTECODE=1 -e PYTORCH_CUDA_ALLOC_CONF=backend:native,max_split_size_mb:128 \
  -v "$exp/parent_scripts:/finalizer:ro" -v "$exp/legacy_scripts:/legacy:ro" -v "$parent/sources/GeoGS-mvs-pgsr-v1:/source:ro" \
  -v "$base/inputs/$region:/input:ro" -v "$base/runtime/weights:/weights:ro" -v "$output/alpha_4/extraction:/output" \
  "$image" python /finalizer/finalize.py --stage extract > "$recovery/extraction.log" 2>&1
 flock -u 9;exec 9>&-
 stage=PUBLISHING;printf '%s\n' "$stage" > "$exp/status.txt";refresh
 publish_cpu publish --alpha 4 > "$recovery/publish.log" 2>&1
 printf 'PASS_TRAINED_EXTRACTED_PUBLISHED\n' > "$exp/status.txt";refresh
