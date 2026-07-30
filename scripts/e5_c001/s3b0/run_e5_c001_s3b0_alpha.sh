#!/usr/bin/env bash
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
image="jointbuildgs:dev"
uid_value="$(id -u)"
gid_value="$(id -g)"
run_dir="${repo}/phases/p2-gsjso/runs/e5_c001/20260716_e5_c001_s3b0_measurements/0a_alpha"
mkdir -p "${run_dir}"

docker run --rm -i \
  -v "${repo}:/workspace/JointBuildGS" \
  -w /workspace/JointBuildGS \
  "${image}" \
  bash -lc "mkdir -p results/tum_transfer/e5_s3b0/alpha && chown ${uid_value}:${gid_value} results/tum_transfer/e5_s3b0/alpha"

worker() {
  local shard="$1"
  local gpu="$2"
  docker run --rm -i --gpus all \
    --user "${uid_value}:${gid_value}" \
    -e CUDA_VISIBLE_DEVICES="${gpu}" \
    -e HOME=/tmp/s3b0-home \
    -e XDG_CACHE_HOME=/tmp/s3b0-xdg \
    -e MPLCONFIGDIR=/tmp/matplotlib \
    -e TORCH_EXTENSIONS_DIR=/workspace/JointBuildGS/results/tum_transfer/e5_s3ap_phase2/runtime/torch_extensions \
    -e PYTHONUNBUFFERED=1 \
    -v "${repo}:/workspace/JointBuildGS" \
    -w /workspace/JointBuildGS \
    "${image}" \
    python scripts/e5_c001/s3b0/e5_c001_s3b0_alpha.py worker \
      --shard-index "${shard}" --shard-count 2
}

worker 0 0 >"${run_dir}/launcher_0.log" 2>&1 &
pid0=$!
worker 1 1 >"${run_dir}/launcher_1.log" 2>&1 &
pid1=$!

cleanup() {
  kill "${pid0}" "${pid1}" 2>/dev/null || true
}
trap cleanup INT TERM

rc=0
wait "${pid0}" || rc=1
wait "${pid1}" || rc=1
trap - INT TERM
if [[ "${rc}" -ne 0 ]]; then
  tail -n 80 "${run_dir}/launcher_0.log" || true
  tail -n 80 "${run_dir}/launcher_1.log" || true
  exit "${rc}"
fi

docker run --rm -i \
  --user "${uid_value}:${gid_value}" \
  -e HOME=/tmp/s3b0-home \
  -e XDG_CACHE_HOME=/tmp/s3b0-xdg \
  -e MPLCONFIGDIR=/tmp/matplotlib \
  -v "${repo}:/workspace/JointBuildGS" \
  -w /workspace/JointBuildGS \
  "${image}" \
  python scripts/e5_c001/s3b0/e5_c001_s3b0_alpha.py aggregate
