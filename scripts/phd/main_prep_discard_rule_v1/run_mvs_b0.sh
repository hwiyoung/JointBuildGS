#!/usr/bin/env bash
# PHD-MAIN-PREP-DISCARD-RULE-v1 5.3: MVS of the nadir-including B0 conditions (training images only; host driver).
set -uo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd); ART=$(realpath "$REPO/../JointBuildGS-artifacts")
P="$ART/phase-payloads/phd/main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1"; S="$REPO/scripts/phd/main_prep_discard_rule_v1"
GPU=${1:-0}
for c in N13 N8 N2; do
  t0=$SECONDS
  docker run --rm --network none --user "$(id -u):$(id -g)" --cpus 4 --memory 8g -v "$ART:/art:ro" -v "$P:/out" -v "$REPO:/repo:ro" \
    -w /repo/scripts/phd/main_prep_discard_rule_v1 --entrypoint python jointbuildgs:dev colmap_subset.py "B0_$c" "mvs_lists/B0_$c.json" > "$P/logs/mvs_subset_B0_$c.log" 2>&1
  echo "$(date +%H:%M:%S) mvs_subset_B0_$c rc=$? $((SECONDS-t0))s" >> "$P/logs/queue.log"; t0=$SECONDS
  bash "$S/run_colmap.sh" "B0_$c" "$GPU" > "$P/logs/mvs_colmap_B0_$c.log" 2>&1
  echo "$(date +%H:%M:%S) mvs_colmap_B0_$c rc=$? $((SECONDS-t0))s" >> "$P/logs/queue.log"
done
