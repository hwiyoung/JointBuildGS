#!/usr/bin/env bash
# Detached host dispatcher; every project computation runs in pinned Docker.
set -euo pipefail
attempt=${1:?absolute prepared attempt path}
[[ "$attempt" == /* && -d "$attempt" ]]
frozen="$attempt/source_snapshot"
test -s "$frozen/configs/phd/source_selected_2dgs_v1/experiment.json"
test -s "$attempt/launch_receipt.json"
test ! -e "$attempt/queue_started.txt"
date -Is > "$attempt/queue_started.txt"
image=sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774
gpu=GPU-4bdfcab8-1464-94b0-0a2f-dd9693ace2a0
art=$(realpath -e "$attempt/../../../../..")
parent_queue="$art/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1/queue/attempt.eh1jxGEn"
[[ -d "$parent_queue" ]]
owner_pid=$BASHPID
failure() {
  local code=$?
  [[ "$BASHPID" == "$owner_pid" ]] || return "$code"
  if [[ "$code" != 0 ]]; then
    printf 'FAILED exit=%s at=%s\n' "$code" "$(date -Is)" > "$attempt/status.txt"
    printf 'queue_exit=%s time=%s; partial outputs preserved\n' "$code" "$(date -Is)" >> "$attempt/issues.log"
    notify-send --urgency=normal '소스 판단 + 2DGS 실험 중단' "실패 기록: $attempt/queue.log" || true
  fi
}
trap failure EXIT
cpu() {
  docker run --rm --network none --cpus 4 --memory 16g --memory-swap 16g \
    --user "$(id -u):$(id -g)" --entrypoint python -e PYTHONPATH=/repo \
    -e PYTHONDONTWRITEBYTECODE=1 -e OPENBLAS_NUM_THREADS=1 -e OMP_NUM_THREADS=4 \
    -e MPLCONFIGDIR=/tmp/mpl -v "$frozen:/repo:ro" -v "$attempt:/attempt" \
    -v /usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc:/font.ttc:ro \
    "$image" "$@"
}
integrity() {
  cpu /repo/scripts/phd/source_selected_2dgs_v1/control.py verify --attempt /attempt
}
partial_report() {
  cpu /repo/scripts/phd/source_selected_2dgs_v1/evaluate_and_report.py \
    --attempt /attempt --font /font.ttc --output /attempt/report --partial
}
wait_resources() {
  local stable=0 state available observation free_mib utilization
  while true; do
    state=$(cat "$parent_queue/status.txt")
    case "$state" in
      COMPLETE*|FAILED*|WAITING_FINALIZER_DEFINITION*|EXTRACTION_AND_EVALUATION*) ;;
      *)
        printf 'WAITING_EXISTING_TRAINING %s\n' "$state" > "$attempt/status.txt"
        stable=0
        sleep 30
        continue
        ;;
    esac
    available=$(awk '/MemAvailable:/ {print $2}' /proc/meminfo)
    observation=$(nvidia-smi --id="$gpu" --query-gpu=memory.free,utilization.gpu --format=csv,noheader,nounits)
    IFS=, read -r free_mib utilization <<< "$observation"
    free_mib=${free_mib//[[:space:]]/}; utilization=${utilization//[[:space:]]/}
    [[ "$free_mib" =~ ^[0-9]+$ && "$utilization" =~ ^[0-9]+$ ]]
    printf '%s available_kib=%s free_mib=%s utilization=%s\n' "$(date -Is)" "$available" "$free_mib" "$utilization" >> "$attempt/resource_wait.log"
    if (( available >= 30000000 && free_mib >= 22000 && utilization <= 5 )); then
      stable=$((stable+1))
      if (( stable >= 3 )); then return; fi
    else
      stable=0
    fi
    printf 'WAITING_GPU free_mib=%s utilization=%s stable=%s/3\n' "$free_mib" "$utilization" "$stable" > "$attempt/status.txt"
    sleep 30
  done
}
gpu_job() {
  local region=$1 arm=$2 output=$3
  shift 3
  docker run --rm --name "jbgs-source-selected-${region}-${arm}" --network none \
    --gpus "device=$gpu" --cpus 4 --memory 24g --memory-swap 24g --shm-size 2g \
    --user "$(id -u):$(id -g)" --entrypoint python \
    -e PYTHONPATH=/repo -e PYTHONDONTWRITEBYTECODE=1 -e OPENBLAS_NUM_THREADS=1 \
    -e OMP_NUM_THREADS=4 -e MAX_JOBS=2 -e TORCH_CUDA_ARCH_LIST=8.6 \
    -e TORCH_EXTENSIONS_DIR=/cache -e MPLCONFIGDIR=/tmp/mpl \
    -e JBGS_RUNTIME_IMAGE_ID="$image" \
    -v "$frozen:/repo:ro" -v "$attempt/prepared:/prepared:ro" \
    -v "$attempt/runtime_cache/torch_extensions:/cache" -v "$attempt/training:/training" \
    -v "$attempt/gpu_preflight:/gpu_preflight" "$image" \
    /repo/scripts/phd/source_selected_2dgs_v1/train.py \
    --config /repo/configs/phd/source_selected_2dgs_v1/experiment.json \
    --prepared /prepared --region "$region" --arm "$arm" --output "$output" "$@"
}
integrity
printf 'PREPARED\n' > "$attempt/status.txt"
partial_report
mkdir -p "$attempt/training" "$attempt/gpu_preflight" "$attempt/runtime_cache/torch_extensions"
wait_resources
integrity
printf 'GPU_PREFLIGHT\n' > "$attempt/status.txt"
gpu_job P2 source_selected /gpu_preflight/P2_source_selected --preflight > "$attempt/gpu_preflight.log" 2>&1
cpu /repo/scripts/phd/source_selected_2dgs_v1/control.py gate --attempt /attempt --preflight
for region in P1 P2 P3; do
  for arm in prior_only source_selected; do
    wait_resources
    integrity
    printf 'TRAINING %s %s\n' "$region" "$arm" > "$attempt/status.txt"
    gpu_job "$region" "$arm" "/training/$region/$arm" > "$attempt/train_${region}_${arm}.log" 2>&1
    cpu /repo/scripts/phd/source_selected_2dgs_v1/control.py gate --attempt /attempt --region "$region" --arm "$arm"
    partial_report
  done
done
printf 'EVALUATING\n' > "$attempt/status.txt"
integrity
docker run --rm --network none --cpus 4 --memory 16g --memory-swap 16g \
  --user "$(id -u):$(id -g)" --entrypoint python -e PYTHONPATH=/repo \
  -e PYTHONDONTWRITEBYTECODE=1 -e OPENBLAS_NUM_THREADS=1 -e OMP_NUM_THREADS=4 -e MPLCONFIGDIR=/tmp/mpl \
  -v "$frozen:/repo:ro" -v "$attempt:/attempt" \
  -v "$art/phase-payloads/phd/wu_vallet_regions_v4/PHD-WU-VALLET-REGIONS-EVALUATION-v4/run:/reference:ro" \
  -v /usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc:/font.ttc:ro \
  "$image" /repo/scripts/phd/source_selected_2dgs_v1/evaluate_and_report.py \
  --attempt /attempt --reference-root /reference --font /font.ttc --output /attempt/report \
  > "$attempt/evaluation.log" 2>&1
printf 'VALIDATING_FINAL_REPORT\n' > "$attempt/status.txt"
mkdir "$attempt/qa_final"
docker run --rm --network host --cpus 2 --memory 2g --memory-swap 2g \
  --user "$(id -u):$(id -g)" --entrypoint node \
  -e QA_URL=http://127.0.0.1:8909/report/ -e QA_OUT=/out \
  -v "$frozen:/repo:ro" -v "$attempt/qa_final:/out" \
  sha256:5043f84d76db9d54e64fcf457125aad90ac5423fded88eca6cf487d2b4713a9e \
  /repo/scripts/phd/source_selected_2dgs_v1/browser_qa.mjs > "$attempt/browser_qa_final.log" 2>&1
cpu /repo/scripts/phd/source_selected_2dgs_v1/control.py complete --attempt /attempt
printf 'COMPLETE\n' > "$attempt/status.txt"
date -Is > "$attempt/queue_completed.txt"
notify-send --urgency=normal '소스 판단 + 2DGS 비교 완료' "P1/P2/P3 단계별 결과: $attempt/report" || true
