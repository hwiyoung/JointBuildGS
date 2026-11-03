#!/usr/bin/env bash
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
for prior in ALS LoD2; do
 for family in prior mvs; do
  bash "$REPO/scripts/phd/main_rescore_v1/run.sh" "input-$prior-$family" score_inputs.py B173nb_b10 "$prior" "$family"
 done
done
