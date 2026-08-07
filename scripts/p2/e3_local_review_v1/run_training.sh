#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
artifact_root="${JBGS_ARTIFACT_ROOT:-/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts}"
task_name="${E3_TASK_NAME:-P2-E3-LOCAL-4906982-2DGS-PARITY-v5-dist0-resetoff-pilot7k}"
run_name="${E3_RUN_NAME:-E3_LOCAL_4906982_2DGS_PARITY_V5_DIST0_RESETOFF_PILOT7K}"
max_iter="${E3_MAX_ITER:-7000}"
w_distort="${E3_W_DISTORT:-0}"
reset_every="${E3_RESET_EVERY:-100000}"
task_root="${artifact_root}/phase-payloads/p2/e3_local_4906982_v1/${task_name}"
run_root="${artifact_root}/phase-payloads/p2/e1_e6_techdev_v1/P2-E1-E6-PRIOR-FUSION-TECHDEV-v1/runs/${run_name}/seed0"
config="${task_root}/config/effective.yaml"
container_name="jbgs-e3-local-4906982-train"
source_commit="$(git -C "${repo_root}" rev-parse HEAD)"
clean_source="${task_root}/control/source_${source_commit}"
mode="${1:-start}"

if [[ "${mode}" == "status" ]]; then
  docker ps -a --filter "name=^/${container_name}$" --format '{{.Names}} {{.Status}}'
  test ! -f "${run_root}/progress.json" || tail -n 20 "${run_root}/progress.json"
  test ! -f "${task_root}/logs/train.log" || tail -n 20 "${task_root}/logs/train.log"
  exit 0
fi
if [[ "${mode}" != "start" ]]; then
  echo "usage: $0 [start|status]" >&2
  exit 2
fi
if docker ps -a --format '{{.Names}}' | rg -Fxq "${container_name}"; then
  echo "${container_name} already exists; use status" >&2
  exit 0
fi
if [[ -f "${run_root}/ckpt/final.pt" ]]; then
  echo "final checkpoint already exists: ${run_root}/ckpt/final.pt"
  exit 0
fi
if ! git -C "${repo_root}" diff --quiet -- src/stage2 scripts/p2/e1_e6_techdev_v1/materialize_config.py configs/p2/e1_e6_techdev_v1/common_gs.yaml; then
  echo "tracked training engine/config differs from HEAD" >&2
  exit 2
fi
docker run --rm --network none --shm-size 8g --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -v "${repo_root}:/workspace/JointBuildGS:ro" -v "${artifact_root}:/artifacts/JointBuildGS" \
  -w /workspace/JointBuildGS jointbuildgs:dev python -B scripts/p2/e3_local_review_v1/prepare_training.py \
  --repo-root /workspace/JointBuildGS --artifact-root /artifacts/JointBuildGS --source-commit "${source_commit}" \
  --task-name "${task_name}" --run-name "${run_name}" --max-iter "${max_iter}" \
  --w-distort "${w_distort}" --reset-every "${reset_every}"
mkdir -p "${clean_source}"
if [[ ! -f "${clean_source}/src/stage2/train.py" ]]; then
  git -C "${repo_root}" archive "${source_commit}" | tar -x -C "${clean_source}"
fi
mkdir -p "${task_root}/logs" "${run_root}"
docker run -d --name "${container_name}" --network none --shm-size 16g \
  --gpus 'device=0' --user "$(id -u):$(id -g)" \
  -e CUDA_VISIBLE_DEVICES=0 -e HOME=/tmp \
  -e XDG_CACHE_HOME="/artifacts/JointBuildGS/phase-payloads/p2/e3_local_4906982_v1/${task_name}/control/cache" \
  -e TORCH_EXTENSIONS_DIR=/artifacts/JointBuildGS/phase-payloads/p2/e3_local_4906982_v1/P2-E3-LOCAL-4906982-2DGS-PARITY-v2/control/torch_extensions \
  -v "${clean_source}:/workspace/JointBuildGS:ro" \
  -v "${repo_root}/scripts/p2/e3_local_review_v1/container_train.sh:/runner/container_train.sh:ro" \
  -v "${artifact_root}:/artifacts/JointBuildGS" \
  -w /workspace/JointBuildGS jointbuildgs:dev \
  bash /runner/container_train.sh \
  "/artifacts/JointBuildGS/phase-payloads/p2/e3_local_4906982_v1/${task_name}/config/effective.yaml" \
  "/artifacts/JointBuildGS/phase-payloads/p2/e1_e6_techdev_v1/P2-E1-E6-PRIOR-FUSION-TECHDEV-v1/runs/${run_name}/seed0" \
  "/artifacts/JointBuildGS/phase-payloads/p2/e3_local_4906982_v1/${task_name}/logs/train.log"
echo "started ${container_name}"
