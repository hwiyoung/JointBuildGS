#!/usr/bin/env bash
set -euo pipefail

# Host-side orchestration only. All evidence calculations run in the pinned
# jointbuildgs:dev container; the second read-only bind is the VM-staleness
# control view used by pin 5.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "${SCRIPT_DIR}" rev-parse --show-toplevel)"
HOST_REPO="$(realpath "${REPO_ROOT}")"
GPU_DEVICE="${FUS_W1_APRIME_GPU_DEVICE:-1}"
HOST_UID="$(id -u)"
HOST_GID="$(id -g)"
DOCKER_SOCKET_GID="$(stat -c '%g' /var/run/docker.sock)"

docker run --rm \
  --pull=never \
  --network none \
  --gpus "device=${GPU_DEVICE}" \
  --user "${HOST_UID}:${HOST_GID}" \
  --group-add "${DOCKER_SOCKET_GID}" \
  --env PYTHONDONTWRITEBYTECODE=1 \
  --volume /var/run/docker.sock:/var/run/docker.sock \
  --volume /usr/bin/docker:/usr/local/bin/docker:ro \
  --volume "${HOST_REPO}:/workspace/JointBuildGS" \
  --volume "${HOST_REPO}:/host-control/JointBuildGS:ro" \
  --workdir /workspace/JointBuildGS \
  --entrypoint python \
  jointbuildgs:dev \
  phases/p2-gsjso/scripts/fusion_w1/fusion_w1_aprime_preflight_20260726.py \
  --config phases/p2-gsjso/configs/fusion_w1/fusion_w1_aprime_preflight_20260726.json \
  --host-control-root /host-control/JointBuildGS
