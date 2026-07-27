#!/usr/bin/env bash
# Host-only user-systemd control plane. Scientific commands remain Docker-only
# through the locked continuation-v3 queue wrapper.
set -Eeuo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"
export PYTHONDONTWRITEBYTECODE=1

CONTROLLER="phases/p2-gsjso/scripts/fusion_w1_aprime_continuation_v3_service_20260727.py"
CONFIG="phases/p2-gsjso/configs/fusion_w1_aprime_continuation_v3_service_20260727.json"

exec /usr/bin/python3 "$CONTROLLER" --config "$CONFIG" "$@"
