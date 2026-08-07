#!/usr/bin/env bash
set -Eeuo pipefail

config="${1:?effective config path required}"
run_root="${2:?run root required}"
log_path="${3:?log path required}"
mkdir -p "${run_root}/control" "$(dirname "${log_path}")"
start_epoch="$(date +%s)"
vram_log="${run_root}/control/vram_used_mib.tsv"
: >"${vram_log}"
python -m src.stage2.train --config "${config}" >"${log_path}" 2>&1 &
training_pid="$!"
while kill -0 "${training_pid}" 2>/dev/null; do
  printf '%s\t' "$(date +%s)" >>"${vram_log}"
  nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -n 1 >>"${vram_log}" || printf '0\n' >>"${vram_log}"
  sleep 2
done
set +e
wait "${training_pid}"
status="$?"
set -e
end_epoch="$(date +%s)"
max_vram="$(awk 'BEGIN{m=0} $2+0>m{m=$2+0} END{print m}' "${vram_log}")"
printf '{"condition":"E3_LOCAL_4906982_2DGS_PARITY","wall_seconds":%d,"gpu_index":0,"max_vram_mib":%d,"exit_code":%d,"scientific_verdict":null}\n' \
  "$((end_epoch-start_epoch))" "${max_vram}" "${status}" >"${run_root}/control/operation.json"
exit "${status}"
