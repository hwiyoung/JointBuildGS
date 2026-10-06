#!/usr/bin/env bash
# PHD-MAIN-PREP-DISCARD-RULE-v1 5.2: rebuild the MVS of seven search ranges from their training images only (host driver).
#   bash run_mvs_all.sh            (two GPU queues in parallel; each range: colmap_subset.py then run_colmap.sh)
# Settings = the prep measure (pinned COLMAP 4.0.4 CUDA image, 1024 px, 3 iterations, geometric filter). No network.
set -uo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
ART=$(realpath "$REPO/../JointBuildGS-artifacts")
P="$ART/phase-payloads/phd/main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1"
S="$REPO/scripts/phd/main_prep_discard_rule_v1"
one() {  # one <range> <gpu>
  local r=$1 g=$2 t0=$SECONDS
  docker run --rm --network none --user "$(id -u):$(id -g)" --cpus 8 --memory 16g -v "$ART:/art:ro" -v "$P:/out" -v "$REPO:/repo:ro" \
    -w /repo/scripts/phd/main_prep_discard_rule_v1 --entrypoint python jointbuildgs:dev colmap_subset.py "$r" "mvs_lists/$r.json" > "$P/logs/mvs_subset_$r.log" 2>&1
  local rc=$?
  echo "$(date +%H:%M:%S) mvs_subset_$r rc=$rc $((SECONDS-t0))s" >> "$P/logs/queue.log"
  [ $rc -eq 0 ] || return $rc
  t0=$SECONDS
  bash "$S/run_colmap.sh" "$r" "$g" > "$P/logs/mvs_colmap_$r.log" 2>&1
  rc=$?
  echo "$(date +%H:%M:%S) mvs_colmap_$r rc=$rc $((SECONDS-t0))s" >> "$P/logs/queue.log"
  return $rc
}
q0() { for r in R1 R4 B0; do one "$r" 0; done; }
q1() { for r in R3E R5 SW R2; do one "$r" 1; done; }
echo "$(date +%H:%M:%S) mvs start" >> "$P/logs/queue.log"
q0 & a=$!; q1 & b=$!; wait $a; wait $b
echo "$(date +%H:%M:%S) mvs done" >> "$P/logs/queue.log"
