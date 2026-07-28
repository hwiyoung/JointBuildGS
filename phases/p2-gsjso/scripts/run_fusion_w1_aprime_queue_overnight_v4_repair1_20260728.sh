#!/usr/bin/env bash
# Thin entrypoint for the append-only overnight-v4 readout-HEAD repair.
set -Eeuo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

export APRIME_QUEUE_CONFIG="phases/p2-gsjso/configs/fusion_w1_aprime_queue_overnight_v4_repair1_20260728.json"
export APRIME_QUEUE_DRIVER="phases/p2-gsjso/scripts/fusion_w1_aprime_queue_continuation_v3_20260727.py"
export APRIME_QUEUE_TEST="phases/p2-gsjso/scripts/test_fusion_w1_aprime_queue_overnight_v4_repair1_20260728.py"

exec bash phases/p2-gsjso/scripts/run_fusion_w1_aprime_queue_continuation_v3_20260727.sh "$@"
