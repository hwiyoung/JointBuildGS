#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 || $# -gt 3 ]]; then
  echo "Usage: bash scripts/phd/geogs_p1p2p3_v1/da3/run.sh P1|P2|P3 NEW_RUN_TAG [BATCH_ID]" >&2
  exit 2
fi
region="$1"
run_tag="$2"
[[ "$region" =~ ^P[123]$ && "$run_tag" =~ ^[a-zA-Z0-9_-]+$ ]] || exit 2
if [[ $# -eq 3 ]]; then [[ "$3" =~ ^[0-9]+$ ]] || exit 2; fi
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
task_root="$repo_root/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1"
scene_root="$task_root/inputs/$region/scene"
output_root="$task_root/da3/$region/$run_tag"
gpu_index="${JBGS_DA3_GPU_INDEX:-1}"
[[ "$gpu_index" =~ ^[01]$ ]] || exit 2
image="sha256:4130d2597c2c3c2804a7cacb8302be948314bc37ba81a1a21383e1c8b7fbba73"
test -f "$scene_root/split_manifest_da3_v2.json"
test -f "$repo_root/configs/phd/geogs_p1p2p3_v1/da3_batch_revision_v2.json"
test -f "$task_root/runtime/da3/acquisition.json"
test ! -e "$output_root"
free_mb="$(nvidia-smi -i "$gpu_index" --query-gpu=memory.free --format=csv,noheader,nounits)"
util_percent="$(nvidia-smi -i "$gpu_index" --query-gpu=utilization.gpu --format=csv,noheader,nounits)"
if [[ "$free_mb" -lt 20000 || "$util_percent" -gt 0 ]]; then
  echo "Selected GPU is occupied or has <20GB free; preserve active work and retry after it finishes." >&2
  exit 3
fi
mkdir -p "$(dirname "$output_root")"
mkdir "$output_root"
log="$task_root/runtime/da3/${region}_${run_tag}.log"
test ! -e "$log"
cmd=(docker run --rm --name "jbgs-geogs-da3-${region}-${run_tag}"
  --network none --read-only --gpus "device=$gpu_index" --cpus 8 --memory 32g --shm-size 2g
  --tmpfs /tmp:rw,nosuid,size=1g -e HF_HOME=/tmp/hf -e MPLCONFIGDIR=/tmp/matplotlib
  -v "$repo_root/scripts/phd/geogs_p1p2p3_v1/da3:/drivers:ro"
  -v "$repo_root/configs/phd/geogs_p1p2p3_v1/experiment_v1.json:/config.json:ro"
  -v "$repo_root/configs/phd/geogs_p1p2p3_v1/da3_batch_revision_v2.json:/batch_policy.json:ro"
  -v "$scene_root/split_manifest_da3_v2.json:/split.json:ro"
  -v "$scene_root/da3_batches_v2:/batches:ro"
  -v "$task_root/sources/DA3NESTED-GIANT-LARGE:/model:ro"
  -v "$task_root/sources/GeoGS/preprocessing/get_da3_depth_with_colmap.py:/official.py:ro"
  -v "$task_root/runtime/da3/acquisition.json:/acquisition.json:ro"
  -v "$output_root:/out" "$image" /drivers/infer.py)
if [[ $# -eq 3 ]]; then cmd+=(--batch-id "$3"); fi
printf '%q ' "${cmd[@]}" > "$task_root/runtime/da3/${region}_${run_tag}.command.txt"
printf '\n' >> "$task_root/runtime/da3/${region}_${run_tag}.command.txt"
"${cmd[@]}" > "$log" 2>&1
echo "$output_root"
