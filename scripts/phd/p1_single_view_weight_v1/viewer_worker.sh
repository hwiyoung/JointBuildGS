#!/usr/bin/env bash
# Independent per-condition extraction/display; the frozen training queue is untouched.
set -euo pipefail
output="$(realpath -e "${1:?viewer output}")"
artifact=/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts
experiment="$artifact/phase-payloads/phd/p1_single_view_weight_v1/PHD-P1-SINGLE-VIEW-WEIGHT-v1/attempt.annotated.uOkHWmgi"
base="$artifact/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1"
parent="$artifact/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1"
source_path="$parent/sources/GeoGS-mvs-pgsr-v1"
image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
[[ "$output" == "$parent/viewer_rgb_v1/p1_weights_v1" ]]
exec 8>"$output/worker.lock"
flock -n 8
common=(docker run --rm --network none --cpus 2 --memory 12g --shm-size 512m
  --user "$(id -u):$(id -g)" --env PYTHONDONTWRITEBYTECODE=1
  --env OMP_NUM_THREADS=2 --env OPENBLAS_NUM_THREADS=2
  --env LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6 --env MPLCONFIGDIR=/tmp/weight-viewer
  --mount "type=bind,src=$output/source,dst=/driver,readonly"
  --mount "type=bind,src=$source_path,dst=/source,readonly"
  --mount "type=bind,src=$base/inputs/P1,dst=/input,readonly")
cpu() {
  sha256sum --check --status "$output/source/sha256sums.txt"
  "${common[@]}" --runtime runc --env NVIDIA_VISIBLE_DEVICES=void --env CUDA_VISIBLE_DEVICES= \
    --mount "type=bind,src=$experiment,dst=/experiment,readonly" \
    --mount "type=bind,src=$output,dst=/output" \
    "$image" python /driver/viewer_publish.py "$@"
}
stage=STARTING
trap 'code=$?; if [[ "$code" -ne 0 ]]; then printf "FAIL stage=%s exit=%s\n" "$stage" "$code" > "$output/worker_status.txt"; fi' EXIT
while true; do
  stage=CHECKING_INDIVIDUAL_FINALS
  selected="$(cpu next)"
  case "$selected" in
    COMPLETE) printf 'COMPLETE_ALL_THREE_INDIVIDUALLY_PUBLISHED\n' > "$output/worker_status.txt"; exit 0 ;;
    TRAINING_FAILED|PUBLICATION_FAILED) printf '%s\n' "$selected" > "$output/worker_status.txt"; exit 1 ;;
    WAIT) printf 'WAITING_INDIVIDUAL_FINALS\n' > "$output/worker_status.txt"; sleep 60; continue ;;
    0|1|4) ;;
    *) printf 'Unexpected next result: %s\n' "$selected" >&2; exit 2 ;;
  esac
  alpha="$selected"
  stage="PROCESSING_ALPHA_$alpha"
  printf '%s\n' "$stage" > "$output/worker_status.txt"
  mkdir -p "$output/alpha_$alpha"
  if ! cpu stage --alpha "$alpha" > "$output/alpha_$alpha/stage.log" 2>&1; then
    cpu fail --alpha "$alpha" --error "Final-state verification/staging failed; see alpha_$alpha/stage.log"
    continue
  fi
  # GPU0 becomes free after alpha0. Reserve GPU1 for the already queued alpha4.
  exec 9>/tmp/jbgs-p1-single-view-gpu-0.lock
  flock 9
  while (( $(nvidia-smi --id=0 --query-gpu=memory.used --format=csv,noheader,nounits) > 1500 )); do
    sleep 30
  done
  sha256sum --check --status "$output/source/sha256sums.txt"
  if "${common[@]}" --cpus 8 --memory 32g --shm-size 4g --gpus device=0 \
    --name "jbgs-p1-weight-incremental-alpha-$alpha" \
    --env OMP_NUM_THREADS=8 --env OPENBLAS_NUM_THREADS=8 --env TORCH_HOME=/weights/torch \
    --env PYTORCH_CUDA_ALLOC_CONF=backend:native,max_split_size_mb:128 \
    --mount "type=bind,src=$output/source/legacy,dst=/legacy,readonly" \
    --mount "type=bind,src=$base/runtime/weights,dst=/weights,readonly" \
    --mount "type=bind,src=$output/alpha_$alpha/extraction,dst=/output" \
    "$image" python /driver/finalize.py --stage extract > "$output/alpha_$alpha/extract.log" 2>&1; then
    extracted=true
  else
    extracted=false
  fi
  flock -u 9
  exec 9>&-
  if [[ "$extracted" == false ]]; then
    cpu fail --alpha "$alpha" --error "Native extraction failed; see alpha_$alpha/extract.log"
    continue
  fi
  if ! cpu publish --alpha "$alpha" > "$output/alpha_$alpha/publish.log" 2>&1; then
    cpu fail --alpha "$alpha" --error "Viewer export failed; see alpha_$alpha/publish.log"
    continue
  fi
  printf 'PUBLISHED_ALPHA_%s %s\n' "$alpha" "$(date -Is)" >> "$output/publication_events.log"
done
