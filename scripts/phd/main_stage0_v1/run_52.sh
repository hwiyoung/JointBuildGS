#!/usr/bin/env bash
# PHD-MAIN-STAGE0-v1 5.2 (host driver; every step in Docker): the nadir-including B0 conditions re-selected (config v2 rule),
# their MVS, and stage 1 + labels of all seven conditions with module v6 (B0 crop fixed values).
#   bash run_52.sh [step ...]     steps (default all): select mvs stage1 labels
#   select  b0_select_v2.py                                                  -> mvs_lists/B0_N13|N8|N2.json, b0_conditions_v2.json
#   mvs     the discard task's colmap_subset.py (unchanged; /out = this payload) and run_colmap.sh, GPU $GPU   -> mvs/B0_<N>
#   stage1  s03_stage1_v6 for N13 N8 N2 (new MVS) and A15 A9 A3 COVER (prep MVS) x LoD2 / ALS, fixed = /dr/s52/s03/B0 -> s62/<c>
#   labels  s04_gt_v6 on the discard task's B0 GT (/dr/s52/gt/B0)                                        -> s62_gt/<c>
set -uo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd); ART=$(realpath "$REPO/../JointBuildGS-artifacts")
P="$ART/phase-payloads/phd/main_stage0_v1/PHD-MAIN-STAGE0-v1"; S="$REPO/scripts/phd/main_stage0_v1"; D="$REPO/scripts/phd/main_prep_discard_rule_v1"
PREP="$ART/phase-payloads/phd/main_prep_measure_v1/PHD-MAIN-PREP-MEASURE-v1"; DR="$ART/phase-payloads/phd/main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1"
GPU=${GPU:-0}
cd "$S"
J="$P/logs/jobs_52"; mkdir -p "$J"
NEW="N13 N8 N2"
steps=("$@"); [ ${#steps[@]} -eq 0 ] && steps=(select mvs stage1 labels)
for st in "${steps[@]}"; do
  echo "$(date +%H:%M:%S) 52 step $st start" >> "$P/logs/queue.log"
  case $st in
    select) echo "b0_select_v2.py" > "$J/select.txt"; bash run_queue.sh "$J/select.txt" 1 4 8 ;;
    mvs)    for c in $NEW; do
              t0=$SECONDS
              docker run --rm --network none --user "$(id -u):$(id -g)" --cpus 4 --memory 8g -e MPLCONFIGDIR=/tmp/mpl -v "$ART:/art:ro" -v "$P:/out" -v "$REPO:/repo:ro" \
                -w /repo/scripts/phd/main_prep_discard_rule_v1 --entrypoint python jointbuildgs:dev colmap_subset.py "B0_$c" "mvs_lists/B0_$c.json" > "$P/logs/mvs_subset_B0_$c.log" 2>&1
              echo "$(date +%H:%M:%S) mvs_subset_B0_$c rc=$? $((SECONDS-t0))s" >> "$P/logs/queue.log"; t0=$SECONDS
              bash run_colmap.sh "B0_$c" "$GPU" > "$P/logs/mvs_colmap_B0_$c.log" 2>&1
              echo "$(date +%H:%M:%S) mvs_colmap_B0_$c rc=$? $((SECONDS-t0))s" >> "$P/logs/queue.log"
            done ;;
    stage1) : > "$J/stage1.txt"
            for c in A15 A9 A3 COVER; do for p in LoD2 ALS; do
              echo "s03_stage1_v6.py B0 $p --views-list /prep/mvs_lists/B0_$c.json --mesh-sub /dr/s02 --mvs /prep/mvs/B0_$c --fix-from /dr/s52/s03/B0 --out-sub s62/$c --fig-views 4" >> "$J/stage1.txt"; done; done
            for c in $NEW; do for p in LoD2 ALS; do
              echo "s03_stage1_v6.py B0 $p --views-list mvs_lists/B0_$c.json --mesh-sub /dr/s02 --mvs mvs/B0_$c --fix-from /dr/s52/s03/B0 --out-sub s62/$c --fig-views 4" >> "$J/stage1.txt"; done; done
            bash run_queue.sh "$J/stage1.txt" 3 8 12 ;;
    labels) : > "$J/labels.txt"
            for c in A15 A9 A3 COVER $NEW; do echo "s04_gt_v6.py B0 --mesh-sub /dr/s02 --stage1-sub s62/$c --out-sub s62_gt/$c --gt-from /dr/s52/gt/B0 --mvs /dr/mvs/B0 --no-depth" >> "$J/labels.txt"; done
            bash run_queue.sh "$J/labels.txt" 2 8 16 ;;
  esac
  echo "$(date +%H:%M:%S) 52 step $st done" >> "$P/logs/queue.log"
done
