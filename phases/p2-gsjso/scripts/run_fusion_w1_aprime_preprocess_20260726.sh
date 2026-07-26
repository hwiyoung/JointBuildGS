#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "${SCRIPT_DIR}" rev-parse --show-toplevel)"
HOST_REPO="$(realpath "${REPO_ROOT}")"
HOST_UID="$(id -u)"
HOST_GID="$(id -g)"

if [[ "$#" -eq 0 ]]; then
  echo "usage: $0 --building-id ID | --all-aprime" >&2
  exit 2
fi

docker run --rm \
  --pull=never \
  --network none \
  --memory 24g \
  --cpus 12 \
  --user "${HOST_UID}:${HOST_GID}" \
  --env PYTHONDONTWRITEBYTECODE=1 \
  --env MPLCONFIGDIR=/tmp/matplotlib \
  --env XDG_CACHE_HOME=/tmp \
  --volume "${HOST_REPO}:/workspace/JointBuildGS" \
  --workdir /workspace/JointBuildGS \
  --entrypoint python \
  jointbuildgs-p0-tools:t0 \
  phases/p2-gsjso/scripts/fusion_w1_aprime_preprocess_20260726.py \
  --config phases/p2-gsjso/configs/fusion_w1_aprime_preprocess_20260726.json \
  "$@"
