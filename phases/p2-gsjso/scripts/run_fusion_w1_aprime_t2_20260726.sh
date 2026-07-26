#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
HOST_UID="$(id -u)"
HOST_GID="$(id -g)"
IMAGE_REF="${APRIME_DOCKER_IMAGE:-jointbuildgs:dev}"
GPU_INDEX="${APRIME_T2_GPU_INDEX:-1}"
OUTPUT_REL="phases/p2-gsjso/runs/20260726_fusion_w1_aprime/preflight/T2"
IMAGE_ID="$(docker image inspect --format '{{.Id}}' "$IMAGE_REF")"

mkdir -p "$REPO_ROOT/$OUTPUT_REL"
LOG_REL="$OUTPUT_REL/t2_tsdf_rehearsal_$(date -u +%Y%m%dT%H%M%S%NZ).log"
docker run --rm --pull=never --network none --gpus all \
  --memory 24g \
  --cpus 12 \
  --user "$HOST_UID:$HOST_GID" \
  -e "HOME=/tmp/aprime-t2-home" \
  -e "XDG_CACHE_HOME=/tmp/aprime-t2-cache" \
  -e "TORCH_EXTENSIONS_DIR=/tmp/aprime-t2-torch-extensions" \
  -e "CUDA_VISIBLE_DEVICES=$GPU_INDEX" \
  -e "APRIME_CONTAINER_IMAGE=$IMAGE_REF" \
  -e "APRIME_CONTAINER_IMAGE_ID=$IMAGE_ID" \
  -v "$REPO_ROOT:/workspace/JointBuildGS" \
  -w /workspace/JointBuildGS \
  "$IMAGE_REF" \
  python phases/p2-gsjso/scripts/fusion_w1_aprime_tsdf_20260726.py \
  2>&1 | tee "$REPO_ROOT/$LOG_REL"
