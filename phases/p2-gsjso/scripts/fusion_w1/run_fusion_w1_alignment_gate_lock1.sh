#!/usr/bin/env bash
# Isolated lock1 launcher; stale v1 writers must not touch this path.
set -euo pipefail

# Docker-only Gate A launcher. It exposes no GPU to the measurement container.
# The Docker socket/client are read-only bind mounts used for host container and
# ephemeral pinned nvidia-smi probes; the runtime guard permits no other child.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
HOST_REPO="$(realpath "$REPO_ROOT")"
TOOLS_REFERENCE="jointbuildgs-p0-tools:t0"
TOOLS_IMAGE_ID="sha256:87bea02e5598a3d53a119b754191673497d52641bd8ea4106ffee653407579b0"
CONFIG_PATH="phases/p2-gsjso/configs/fusion_w1/fusion_w1_alignment_gate_lock1.json"
GUARD_PATH="phases/p2-gsjso/runs/fusion_w1/20260724_fusion_w1/w1_align_execution_guard.json"
LOCK_PATH="phases/p2-gsjso/runs/fusion_w1/20260724_fusion_w1/w1_align_gate.lock"
HOST_UID="$(id -u)"
HOST_GID="$(id -g)"

if [[ ! -S /var/run/docker.sock ]]; then
  echo "[BLOCKED] Docker socket is unavailable" >&2
  exit 2
fi
if [[ ! -x /usr/bin/docker ]]; then
  echo "[BLOCKED] Docker CLI is unavailable at /usr/bin/docker" >&2
  exit 2
fi

OBSERVED_IMAGE_ID="$(docker image inspect --format '{{.Id}}' "$TOOLS_REFERENCE")"
if [[ "$OBSERVED_IMAGE_ID" != "$TOOLS_IMAGE_ID" ]]; then
  echo "[BLOCKED] $TOOLS_REFERENCE image ID drift: $OBSERVED_IMAGE_ID" >&2
  exit 2
fi

for argument in "$@"; do
  case "$argument" in
    --config|--config=*|--execution-guard|--execution-guard=*|--output-dir|--output-dir=*|--targets|--targets=*|--datum-config|--datum-config=*)
      echo "[BLOCKED] wrapper owns reserved Gate option: $argument" >&2
      exit 2
      ;;
  esac
done

# --views is intentionally passed to the runtime guard. It is accepted only
# when view_selection locks both its exact repository path and SHA-256.

DOCKER_SOCKET_GID="$(stat -c '%g' /var/run/docker.sock)"

docker run --rm \
  --pull=never \
  --pid=host \
  --network=none \
  --read-only \
  --memory=24g \
  --memory-swap=24g \
  --cap-drop=ALL \
  --security-opt=no-new-privileges \
  --user "${HOST_UID}:${HOST_GID}" \
  --group-add "$DOCKER_SOCKET_GID" \
  --env PYTHONDONTWRITEBYTECODE=1 \
  --env PYTHONUNBUFFERED=1 \
  --env MPLCONFIGDIR=/tmp/matplotlib \
  --env XDG_CACHE_HOME=/tmp/cache \
  --env CUDA_VISIBLE_DEVICES= \
  --env NVIDIA_VISIBLE_DEVICES=void \
  --tmpfs "/tmp:rw,nosuid,nodev,noexec,size=2g,uid=${HOST_UID},gid=${HOST_GID},mode=1777" \
  --volume /var/run/docker.sock:/var/run/docker.sock:ro \
  --volume /usr/bin/docker:/usr/local/bin/docker:ro \
  --volume "${HOST_REPO}:/workspace/JointBuildGS:rw" \
  --volume "${HOST_REPO}:/host-control/JointBuildGS:ro" \
  --workdir /workspace/JointBuildGS \
  --entrypoint python \
  "$TOOLS_IMAGE_ID" \
  phases/p2-gsjso/scripts/fusion_w1/fusion_w1_alignment_runtime_guard_lock1.py \
  launch \
  --config "$CONFIG_PATH" \
  --guard-receipt "$GUARD_PATH" \
  --lock-file "$LOCK_PATH" \
  --host-control-root /host-control/JointBuildGS \
  -- \
  python \
  phases/p2-gsjso/scripts/fusion_w1/fusion_w1_alignment_gate_lock1.py \
  --config "$CONFIG_PATH" \
  --execution-guard "$GUARD_PATH" \
  "$@"
