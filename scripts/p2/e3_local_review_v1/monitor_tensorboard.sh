#!/usr/bin/env bash
set -Eeuo pipefail

run_root="${1:?run root required}"
while [[ ! -f "${run_root}/ckpt/final.pt" && ! -f "${run_root}/control/operation.json" ]]; do
  python -B scripts/p2/e3_local_review_v1/publish_training_images.py --run-root "${run_root}" >/tmp/publish.log 2>&1 || true
  sleep 30
done
python -B scripts/p2/e3_local_review_v1/publish_training_images.py --run-root "${run_root}"
