#!/usr/bin/env bash
set -euo pipefail
geogs_v3_gpu="${1:?idle GPU0 or1}"
case "$geogs_v3_gpu" in 0|1) ;; *) exit 2 ;; esac
geogs_v3_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../../.." && pwd)
geogs_v3_task=$(realpath "$geogs_v3_repo/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1")
geogs_v3_exp="$geogs_v3_task/no_anchor_sfm_gradient_memory_v3_P1"
geogs_v3_out="$geogs_v3_exp/validation/runtime_cuda_v1"
test -s "$geogs_v3_exp/source/jbgs_memory_recovery_receipt.json"
test ! -e "$geogs_v3_out"
geogs_v3_processes=$(nvidia-smi -i "$geogs_v3_gpu" --query-compute-apps=pid,process_name,used_memory --format=csv,noheader,nounits)
while IFS= read -r geogs_v3_row; do
  [[ -z "$geogs_v3_row" ]] && continue
  if [[ "$geogs_v3_gpu" == 0 && "$geogs_v3_row" == '72937, /usr/libexec/gnome-remote-desktop-daemon, '* ]]; then
    geogs_v3_mib="${geogs_v3_row##*, }"
    case "$geogs_v3_mib" in *[!0-9]*|'') exit 3 ;; esac
    [[ "$geogs_v3_mib" -le 512 ]]
    [[ "$(awk '{print $22}' /proc/72937/stat)" == 60213 ]]
  else
    printf '%s\n' 'GPU still has a compute job; CUDA fixture was not started.' >&2
    exit 3
  fi
done <<< "$geogs_v3_processes"
mkdir -p -- "$geogs_v3_out"
cp -- "${BASH_SOURCE[0]}" "$geogs_v3_out/launcher.sh"
printf '%s\n' "$geogs_v3_processes" > "$geogs_v3_out/compute_before.csv"
nvidia-smi --query-gpu=index,uuid,memory.used,memory.free,utilization.gpu --format=csv > "$geogs_v3_out/gpus_before.csv"
trap 'geogs_v3_exit=$?; printf "%s\n" "$geogs_v3_exit" > "$geogs_v3_out/exit_code.txt"' EXIT
docker run --rm --network none --gpus "device=$geogs_v3_gpu" --cpus 2 --memory 4g --memory-swap 4g \
  --user "$(id -u):$(id -g)" --env PYTHONDONTWRITEBYTECODE=1 --env OMP_NUM_THREADS=2 --env OPENBLAS_NUM_THREADS=2 \
  --mount "type=bind,src=$geogs_v3_exp/source,dst=/source,readonly" \
  --mount "type=bind,src=$geogs_v3_exp/preparation_runtime,dst=/work,readonly" \
  --mount "type=bind,src=$geogs_v3_out,dst=/out" \
  sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e \
  /opt/geogs/bin/python /work/memory_recovery_v3/verify_runtime.py \
  --prepared-source /source --v1-directory /work/memory_recovery_v1 --v2-directory /work/memory_recovery_v2 \
  --device cuda --receipt /out/receipt.json > "$geogs_v3_out/stdout.log" 2> "$geogs_v3_out/stderr.log"
nvidia-smi --query-gpu=index,uuid,memory.used,memory.free,utilization.gpu --format=csv > "$geogs_v3_out/gpus_after.csv"
cat "$geogs_v3_out/stdout.log"
