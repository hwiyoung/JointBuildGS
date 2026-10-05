#!/usr/bin/env bash
set -euo pipefail
bundle="$(realpath "${1:?bundle}")";region="${2:?region}";action="${3:?action}";alpha="${4:-0}";gpu="${5:-0}"
case "$region:$action" in P[23]:refresh|P[23]:publish) ;; *) exit 2;; esac
artifact=/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts
base="$artifact/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1"
parent="$artifact/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1"
viewer="$parent/viewer_rgb_v1/p2p3_weights_v1";output="$viewer/$region";experiment="$bundle/$region"
image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
common=(docker run --rm --network none --user "$(id -u):$(id -g)" -e PYTHONDONTWRITEBYTECODE=1
 -e OMP_NUM_THREADS=2 -e OPENBLAS_NUM_THREADS=2 -e LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6 -e MPLCONFIGDIR=/tmp/mpl
 -v "$bundle/scripts:/driver:ro" -v "$parent/sources/GeoGS-mvs-pgsr-v1:/source:ro" -v "$base/inputs/$region:/input:ro")
# Each region owns only its own publication; the combined manifest uses a lock.
run_cpu() { "${common[@]}" --runtime runc --cpus 2 --memory 12g -e NVIDIA_VISIBLE_DEVICES=void -e CUDA_VISIBLE_DEVICES= \
 -v "$experiment:/experiment:ro" -v "$experiment/viewer_config.json:/viewer_config.json:ro" -v "$output:/output" \
 "$image" python /driver/viewer_publish.py "$@"; }
aggregate() {
 exec 8>"$viewer/aggregate.lock";flock 8
 docker run --rm --runtime runc --network none --cpus 1 --memory 1g --user "$(id -u):$(id -g)" \
 -e NVIDIA_VISIBLE_DEVICES=void -e CUDA_VISIBLE_DEVICES= -e PYTHONDONTWRITEBYTECODE=1 \
 -v "$bundle/scripts:/driver:ro" -v "$viewer:/viewer" "$image" python /driver/aggregate_viewer.py
 flock -u 8;exec 8>&-
}
sha256sum --check --status "$bundle/frozen_files.sha256"
if [[ "$action" == refresh ]]; then run_cpu refresh; [[ -f "$viewer/P2/manifest.json" && -f "$viewer/P3/manifest.json" ]] && aggregate; exit 0; fi
stage=STAGING
on_exit() { code=$?; if [[ "$code" -ne 0 ]]; then run_cpu fail --alpha "$alpha" --error "$stage failed; see $region alpha $alpha display log" || true; aggregate || true; fi; }
trap on_exit EXIT
run_cpu stage --alpha "$alpha"
stage=EXTRACTING
exec 9>"/tmp/jbgs-p1-single-view-gpu-$gpu.lock";flock 9
while (( $(nvidia-smi --id="$gpu" --query-gpu=memory.used --format=csv,noheader,nounits) > 1500 )); do sleep 30; done
"${common[@]}" --gpus "device=$gpu" --cpus 8 --memory 32g --shm-size 4g \
 --name "jbgs-region-weight-extract-$region-a$alpha" -e OMP_NUM_THREADS=8 -e OPENBLAS_NUM_THREADS=8 \
 -e TORCH_HOME=/weights/torch -e PYTORCH_CUDA_ALLOC_CONF=backend:native,max_split_size_mb:128 \
 -v "$bundle/parent_scripts:/finalizer:ro" -v "$bundle/legacy_scripts:/legacy:ro" -v "$base/runtime/weights:/weights:ro" \
 -v "$output/alpha_$alpha/extraction:/output" "$image" python /finalizer/finalize.py --stage extract
flock -u 9;exec 9>&-
stage=PUBLISHING
run_cpu publish --alpha "$alpha"
aggregate
printf 'PUBLISHED %s alpha=%s %s\n' "$region" "$alpha" "$(date -Is)" >> "$viewer/publication_events.log"
