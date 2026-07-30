#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
HOST_UID="$(id -u)"
HOST_GID="$(id -g)"
IMAGE_REF="${APRIME_DOCKER_IMAGE:-jointbuildgs:dev}"
GPU_INDEX="${APRIME_T2_GPU_INDEX:-1}"
OUTPUT_REL="phases/p2-gsjso/runs/fusion_w1/20260726_fusion_w1_aprime/preflight/T2"
RUNTIME_REL="phases/p2-gsjso/runs/fusion_w1/20260726_fusion_w1_aprime/runtime_env"
IMAGE_ID="$(docker image inspect --format '{{.Id}}' "$IMAGE_REF")"

mkdir -p "$REPO_ROOT/$OUTPUT_REL"
mkdir -p \
  "$REPO_ROOT/$RUNTIME_REL/home" \
  "$REPO_ROOT/$RUNTIME_REL/xdg_cache" \
  "$REPO_ROOT/$RUNTIME_REL/torch_extensions"
LOG_REL="$OUTPUT_REL/t2_tsdf_rehearsal_$(date -u +%Y%m%dT%H%M%S%NZ).log"
docker run --rm --pull=never --network none --gpus all \
  --memory 24g \
  --cpus 12 \
  --user "$HOST_UID:$HOST_GID" \
  -e "HOME=/workspace/JointBuildGS/$RUNTIME_REL/home" \
  -e "XDG_CACHE_HOME=/workspace/JointBuildGS/$RUNTIME_REL/xdg_cache" \
  -e "TORCH_EXTENSIONS_DIR=/workspace/JointBuildGS/$RUNTIME_REL/torch_extensions" \
  -e "MAX_JOBS=2" \
  -e "CUDA_VISIBLE_DEVICES=$GPU_INDEX" \
  -e "APRIME_CONTAINER_IMAGE=$IMAGE_REF" \
  -e "APRIME_CONTAINER_IMAGE_ID=$IMAGE_ID" \
  -v "$REPO_ROOT:/workspace/JointBuildGS" \
  -w /workspace/JointBuildGS \
  "$IMAGE_REF" \
  python phases/p2-gsjso/scripts/fusion_w1/fusion_w1_aprime_tsdf_20260726.py \
  2>&1 | tee "$REPO_ROOT/$LOG_REL"
