#!/usr/bin/env bash
# Host orchestration only. Processing and validation are performed in Docker.
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
OUT=$(realpath "$REPO/../JointBuildGS-artifacts/phase-payloads/phd/main_meshpatch_v1/PHD-MAIN-MESHPATCH-v1")
cd "$REPO"
while [[ ! -f "$OUT/status/delivery_handover.json" ]]; do
  state=$(docker inspect --format '{{.State.Status}}' jbgs-meshpatch-queue)
  if [[ "$state" != running ]]; then
    printf '%s queue stopped before full handover; no final commit\n' "$(date -Is)" > "$OUT/logs/finalize_failure.txt"
    exit 1
  fi
  sleep 30
done
cd "$OUT/deliveries"
sha256sum --check PHD-MAIN-MESHPATCH-v1_handover.zip.sha256
cd "$REPO"
bash scripts/phd/main_meshpatch_v1/commit_delivery.sh mesh > "$OUT/logs/final_commit.log" 2>&1
date -Is > "$OUT/status/final_git_delivery.txt"
