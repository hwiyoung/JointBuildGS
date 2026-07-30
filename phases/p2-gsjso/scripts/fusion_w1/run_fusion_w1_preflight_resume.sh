#!/usr/bin/env bash
set -euo pipefail

# Docker-only wrapper for FUS-W1 section-0 resume preflight.
# It launches no training/readout command.  The Docker socket is mounted only
# so the Python preflight can inspect the three locked images and run their
# version probes.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
HOST_REPO="$(realpath "$REPO_ROOT")"
TRAINING_IMAGE="jointbuildgs:dev"
GPU_DEVICE="${FUS_W1_GPU_DEVICE:-1}"
HOST_UID="$(id -u)"
HOST_GID="$(id -g)"
DOCKER_SOCKET_GID="$(stat -c '%g' /var/run/docker.sock)"

docker run --rm \
  --pull=never \
  --gpus "device=${GPU_DEVICE}" \
  --pid=host \
  --user "${HOST_UID}:${HOST_GID}" \
  --group-add "${DOCKER_SOCKET_GID}" \
  --env PYTHONDONTWRITEBYTECODE=1 \
  --env FUS_W1_HOST_REPO="${HOST_REPO}" \
  --volume /var/run/docker.sock:/var/run/docker.sock \
  --volume /usr/bin/docker:/usr/local/bin/docker:ro \
  --volume "${HOST_REPO}:/workspace/JointBuildGS" \
  --volume "${HOST_REPO}:/host-control/JointBuildGS:ro" \
  --workdir /workspace/JointBuildGS \
  --entrypoint python \
  "${TRAINING_IMAGE}" \
  phases/p2-gsjso/scripts/fusion_w1/fusion_w1_preflight_resume.py \
  --config phases/p2-gsjso/configs/fusion_w1/fusion_w1_preflight_resume_v1.json \
  --host-control-root /host-control/JointBuildGS
