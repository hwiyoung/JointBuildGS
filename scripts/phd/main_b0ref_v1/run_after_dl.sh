#!/usr/bin/env bash
# PHD-MAIN-B0REF-v1 일 3·4 queue for the fetched Zenodo files (v1.2.0 manual, v1.1.0 fillparts): crop, select, distances, match, colour,
# tables, figure 3. Each step after wait_mem.sh. scientific_verdict: null.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd)
for s in uls_manual_v120 fill_v110; do
  bash "$H/wait_mem.sh" "crop_$s"; bash "$H/run_cpu.sh" "crop_$s" c1_crop.py "$s" || exit 1
  bash "$H/wait_mem.sh" "sel_$s"; bash "$H/run_cpu.sh" "sel_$s" s2_select.py "$s" || exit 1
done
bash "$H/wait_mem.sh" dist2; bash "$H/run_cpu.sh" dist2 s3_dist.py query uls_manual_v120 uls_nadir+uls_manual_v120 fill_v110 || exit 1
bash "$H/run_cpu.sh" match_man s3b_match.py uls_manual_v120 fill_v110 || exit 1
bash "$H/run_cpu.sh" rgb2 s3_dist.py rgb uls_manual_v120 fill_v110 || exit 1
bash "$H/run_cpu.sh" tab3b s3_dist.py tables || exit 1
bash "$H/run_cpu.sh" counts2 s2_counts.py || exit 1
bash "$H/run_cpu.sh" fig3 s4_figs.py 3 || exit 1
