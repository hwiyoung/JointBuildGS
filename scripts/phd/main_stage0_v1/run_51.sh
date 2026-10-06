#!/usr/bin/env bash
# PHD-MAIN-STAGE0-v1 5.1 (host driver; every step in Docker): the v6 measurement of the four boxes, their labels and the
# fork r12 inputs.
#   bash run_51.sh [step ...]     steps (default all, in order): boxes boxgt forkin
#   boxes   s03_stage1_v6 per box x prior on the box MVS with the discard task's fixed values (rule auto) -> s61/box, s61/export;
#           the switch site B173nb_b10 also with the confidence mask off -> s61/box_maskoff, s61/export_maskoff
#   boxgt   labels of the boxes with the moved store (GT points / exclusion / alignment of the discard task's s52/box_gt)  -> s61/box_gt
#   forkin  fork r12 inputs of the four boxes                                                                -> fork_inputs/s61
set -uo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd); ART=$(realpath "$REPO/../JointBuildGS-artifacts")
P="$ART/phase-payloads/phd/main_stage0_v1/PHD-MAIN-STAGE0-v1"; S="$REPO/scripts/phd/main_stage0_v1"
cd "$S"
J="$P/logs/jobs_51"; mkdir -p "$J"
declare -A FIX=([B0_b10]=B0 [B173nb_b10]=R2 [B173_b0]=R2 [R1rep_b10]=R1)
SW_SITE=B173nb_b10
steps=("$@"); [ ${#steps[@]} -eq 0 ] && steps=(boxes boxgt forkin)
for st in "${steps[@]}"; do
  echo "$(date +%H:%M:%S) 51 step $st start" >> "$P/logs/queue.log"
  case $st in
    boxes)  : > "$J/boxes.txt"
            for b in B0_b10 B173nb_b10 B173_b0 R1rep_b10; do for p in LoD2 ALS; do
              c="s03_stage1_v6.py $b $p --views-file /prep/step06/box_views.json --mesh-sub /dr/s02_box --mvs /prep/mvs/box_$b --fix-from /dr/s52/s03/${FIX[$b]} --fig-views 4"
              echo "$c --out-sub s61/box --export-fork s61/export/$b/$p" >> "$J/boxes.txt"
              if [ "$b" = "$SW_SITE" ]; then echo "$c --out-sub s61/box_maskoff --conf photometric --export-fork s61/export_maskoff/$b/$p" >> "$J/boxes.txt"; fi
            done; done
            bash run_queue.sh "$J/boxes.txt" 3 10 16 ;;
    boxgt)  : > "$J/boxgt.txt"
            for b in B0_b10 B173nb_b10 B173_b0 R1rep_b10; do
              echo "s04_gt_v6.py $b --mesh-sub /dr/s02_box --stage1-sub s61/box --out-sub s61/box_gt --views-file /prep/step06/box_views.json --mvs /prep/mvs/box_$b --gt-from /dr/s52/box_gt/$b --no-depth" >> "$J/boxgt.txt"; done
            bash run_queue.sh "$J/boxgt.txt" 2 10 20 ;;
    forkin) : > "$J/forkin.txt"
            for b in B0_b10 B173nb_b10 B173_b0 R1rep_b10; do
              mo=""; if [ "$b" = "$SW_SITE" ]; then mo="--maskoff-run-sub s61/box_maskoff --maskoff-export-sub s61/export_maskoff"; fi
              echo "fork_inputs_v6.py $b --run-sub s61/box --export-sub s61/export $mo --out-sub fork_inputs/s61" >> "$J/forkin.txt"; done
            bash run_queue.sh "$J/forkin.txt" 2 8 12 ;;
  esac
  echo "$(date +%H:%M:%S) 51 step $st done" >> "$P/logs/queue.log"
done
