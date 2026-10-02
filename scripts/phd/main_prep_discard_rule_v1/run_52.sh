#!/usr/bin/env bash
# PHD-MAIN-PREP-DISCARD-RULE-v1 5.2 / 5.3 / 5.1 (host driver; every step in Docker; run after the MVS of run_mvs_all.sh).
#   bash run_52.sh [step ...]     steps (default all, in order): ranges gt boxes boxgt b0 forkin
#   ranges  stage 1 of the 7 ranges on their training-only MVS (own registration and tolerance)      -> s52/s03
#   gt      GT of the 7 ranges (v5 rules; height alignment on the new MVS; prep exclusion cells)     -> s52/gt
#   boxes   the 4 boxes on their box MVS with the new fixed values (+ fork maps), and the mask-off runs -> s52/box(_maskoff), s52/export(_maskoff)
#   boxgt   labels of the boxes (prep box GT, new fixed values)                                          -> s52/box_gt
#   b0      the 7 B0 conditions with the new B0 crop values, their labels on the 5.2 B0 GT             -> s53/<cond>, s53_gt/<cond>
#           (B0_NADIR_CONDS limits the nadir-including conditions, e.g. while one waits for a decision)
#   forkin  fork r11 inputs of the 4 boxes                                                               -> fork_inputs/s52
set -uo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd); ART=$(realpath "$REPO/../JointBuildGS-artifacts")
P="$ART/phase-payloads/phd/main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1"; S="$REPO/scripts/phd/main_prep_discard_rule_v1"
cd "$S"
J="$P/logs/jobs_52"; mkdir -p "$J"
declare -A FIX=([B0_b10]=B0 [B173nb_b10]=R2 [B173_b0]=R2 [R1rep_b10]=R1)
steps=("$@"); [ ${#steps[@]} -eq 0 ] && steps=(ranges gt boxes boxgt b0 forkin)
for st in "${steps[@]}"; do
  echo "$(date +%H:%M:%S) 52 step $st start" >> "$P/logs/queue.log"
  case $st in
    ranges) : > "$J/ranges.txt"
            for r in R1 R4; do for p in LoD2 ALS; do echo "s03_stage1.py $r $p --mvs mvs/$r --out-sub s52/s03 --tile" >> "$J/ranges.txt"; done; done
            for r in R2 R3E R5 SW B0; do for p in LoD2 ALS; do echo "s03_stage1.py $r $p --mvs mvs/$r --out-sub s52/s03" >> "$J/ranges.txt"; done; done
            bash run_queue.sh "$J/ranges.txt" 3 10 14 ;;
    gt)     : > "$J/gt.txt"
            for r in R1 R2 R3E R4 R5 SW B0; do echo "s04_gt.py $r --mvs mvs/$r --stage1-sub s52/s03 --out-sub s52/gt --prep-gt-dir /prep/step04/$r --no-depth" >> "$J/gt.txt"; done
            bash run_queue.sh "$J/gt.txt" 3 10 16 ;;
    boxes)  : > "$J/boxes.txt"
            for b in B0_b10 B173nb_b10 B173_b0 R1rep_b10; do for p in LoD2 ALS; do
              c="s03_stage1.py $b $p --views-file /prep/step06/box_views.json --mesh-sub s02_box --mvs /prep/mvs/box_$b --fix-from s52/s03/${FIX[$b]} --fig-views 4"
              echo "$c --out-sub s52/box --export-fork s52/export/$b/$p" >> "$J/boxes.txt"
              echo "$c --out-sub s52/box_maskoff --conf photometric --export-fork s52/export_maskoff/$b/$p" >> "$J/boxes.txt"; done; done
            bash run_queue.sh "$J/boxes.txt" 3 10 14 ;;
    boxgt)  : > "$J/boxgt.txt"
            for b in B0_b10 B173nb_b10 B173_b0 R1rep_b10; do
              echo "s04_gt.py $b --mesh-sub s02_box --stage1-sub s52/box --out-sub s52/box_gt --views-file /prep/step06/box_views.json --mvs /prep/mvs/box_$b --prep-gt-dir /prep/step06/box_gt/$b --no-depth" >> "$J/boxgt.txt"; done
            bash run_queue.sh "$J/boxgt.txt" 2 10 16 ;;
    b0)     : > "$J/b0.txt"
            for c in A15 A9 A3 COVER; do for p in LoD2 ALS; do
              echo "s03_stage1.py B0 $p --views-list /prep/mvs_lists/B0_$c.json --mvs /prep/mvs/B0_$c --fix-from s52/s03/B0 --out-sub s53/$c --fig-views 4" >> "$J/b0.txt"; done; done
            for c in ${B0_NADIR_CONDS:-N13 N8 N2}; do for p in LoD2 ALS; do
              echo "s03_stage1.py B0 $p --views-list mvs_lists/B0_$c.json --mvs mvs/B0_$c --fix-from s52/s03/B0 --out-sub s53/$c --fig-views 4" >> "$J/b0.txt"; done; done
            bash run_queue.sh "$J/b0.txt" 3 8 12
            : > "$J/b0gt.txt"
            for c in A15 A9 A3 COVER ${B0_NADIR_CONDS:-N13 N8 N2}; do echo "s04_gt.py B0 --stage1-sub s53/$c --out-sub s53_gt/$c --gt-from s52/gt/B0 --mvs mvs/B0 --no-depth" >> "$J/b0gt.txt"; done
            bash run_queue.sh "$J/b0gt.txt" 2 8 16 ;;
    forkin) : > "$J/forkin.txt"
            for b in B0_b10 B173nb_b10 B173_b0 R1rep_b10; do
              echo "fork_inputs.py $b --run-sub s52/box --export-sub s52/export --maskoff-run-sub s52/box_maskoff --maskoff-export-sub s52/export_maskoff --out-sub fork_inputs/s52" >> "$J/forkin.txt"; done
            bash run_queue.sh "$J/forkin.txt" 2 8 12 ;;
  esac
  echo "$(date +%H:%M:%S) 52 step $st done" >> "$P/logs/queue.log"
done
