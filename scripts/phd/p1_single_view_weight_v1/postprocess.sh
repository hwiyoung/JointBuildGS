#!/usr/bin/env bash
# Native extraction in fresh outputs, followed by CPU-only response measurements.
set -euo pipefail
experiment=""
gpu=1
while [[ $# -gt 0 ]]; do
  case "$1" in
    --experiment-dir) experiment="${2:?}"; shift 2 ;;
    --gpu) gpu="${2:?}"; shift 2 ;;
    *) printf 'Unknown argument: %s\n' "$1" >&2; exit 2 ;;
  esac
done
case "$gpu" in 0|1) ;; *) exit 2 ;; esac
artifact=/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts
experiment="$(realpath -e "${experiment:?--experiment-dir required}")"
[[ "$experiment" == "$artifact/phase-payloads/phd/"* ]]
base="$artifact/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1"
original="$artifact/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1"
source_path="$original/sources/GeoGS-mvs-pgsr-v1"
reference="$artifact/phase-payloads/phd/wu_vallet_regions_v4/PHD-WU-VALLET-REGIONS-EVALUATION-v4/run/P1/reference.npz"
image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
test "$(docker image inspect "$image" --format '{{.Id}}')" = "$image"
test -s "$experiment/config.json"
test -s "$experiment/mask/r1_mask.npz"
test -s "$reference"
exec 9>"$experiment/postprocess.lock"
flock -n 9
output="$experiment/postprocess"
mkdir "$output"
mkdir "$output/snapshot"
cp -p "$experiment/scripts/postprocess.py" "$output/snapshot/postprocess.py"
cp -p "${BASH_SOURCE[0]}" "$output/snapshot/postprocess.sh"
cp -p "$experiment/parent_scripts/finalize.py" "$output/snapshot/finalize.py"
cp -a "$experiment/legacy_scripts" "$output/snapshot/legacy"
sha256sum "$output/snapshot/postprocess.py" "$output/snapshot/postprocess.sh" \
  "$output/snapshot/finalize.py" > "$output/driver_hashes.sha256"
stage=plan
failure() {
  local result=$?
  if [[ "$result" -ne 0 ]]; then
    printf 'FAILED stage=%s exit=%s at=%s\n' "$stage" "$result" "$(date -Is)" > "$output/status.txt"
  fi
}
trap failure EXIT
common=(docker run --rm --network none --cpus 8 --memory 32g --shm-size 4g
  --user "$(id -u):$(id -g)" --env PYTHONDONTWRITEBYTECODE=1
  --env OMP_NUM_THREADS=8 --env OPENBLAS_NUM_THREADS=8
  --env TORCH_HOME=/weights/torch --env MPLCONFIGDIR=/tmp/p1-weight-matplotlib
  --env LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6
  --env PYTORCH_CUDA_ALLOC_CONF=backend:native,max_split_size_mb:128
  --mount "type=bind,src=$output/snapshot,dst=/driver,readonly"
  --mount "type=bind,src=$output/snapshot/legacy,dst=/legacy,readonly"
  --mount "type=bind,src=$source_path,dst=/source,readonly"
  --mount "type=bind,src=$base/inputs/P1,dst=/input,readonly"
  --mount "type=bind,src=$base/runtime/weights,dst=/weights,readonly")
printf 'PLAN\n' > "$output/status.txt"
"${common[@]}" --runtime runc --env NVIDIA_VISIBLE_DEVICES=void --env CUDA_VISIBLE_DEVICES= \
  --mount "type=bind,src=$experiment,dst=/experiment,readonly" \
  --mount "type=bind,src=$output,dst=/output" \
  "$image" python /driver/postprocess.py --stage plan > "$output/plan.log" 2>&1
for alpha in 0 1 4; do
  stage="extract-alpha-$alpha"
  printf '%s\n' "$stage" > "$output/status.txt"
  sha256sum --check --status "$output/driver_hashes.sha256"
  exec 10>"/tmp/jbgs-p1-single-view-gpu-$gpu.lock"
  flock 10
  used="$(nvidia-smi --id="$gpu" --query-gpu=memory.used --format=csv,noheader,nounits)"
  if (( used > 1500 )); then
    printf 'GPU %s is occupied (%s MiB); extraction did not start.\n' "$gpu" "$used" >&2
    exit 3
  fi
  "${common[@]}" --gpus "device=$gpu" \
    --name "jbgs-p1-weight-extract-${alpha}-$(basename "$experiment")" \
    --mount "type=bind,src=$output/extractions/alpha_$alpha,dst=/output" \
    "$image" python /driver/finalize.py --stage extract > "$output/$stage.log" 2>&1
  flock -u 10
  exec 10>&-
done
stage=measure
printf 'MEASURE\n' > "$output/status.txt"
sha256sum --check --status "$output/driver_hashes.sha256"
"${common[@]}" --runtime runc --env NVIDIA_VISIBLE_DEVICES=void --env CUDA_VISIBLE_DEVICES= \
  --mount "type=bind,src=$experiment,dst=/experiment,readonly" \
  --mount "type=bind,src=$original/inputs_v2/P1,dst=/mvs,readonly" \
  --mount "type=bind,src=$reference,dst=/reference/P1/reference.npz,readonly" \
  --mount "type=bind,src=$base/contracts/execution_v1.json,dst=/evaluation_config.json,readonly" \
  --mount "type=bind,src=$output,dst=/output" \
  "$image" python /driver/postprocess.py --stage measure > "$output/measure.log" 2>&1
# Keep the result report at the experiment root; never overwrite a prior report.
test ! -e "$experiment/REPORT.md"
cp -p "$output/REPORT.md" "$experiment/REPORT.md"
printf 'COMPLETE\n' > "$output/status.txt"
printf '%s\n' "$experiment/REPORT.md"
