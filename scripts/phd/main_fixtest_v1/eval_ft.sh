#!/usr/bin/env bash
# PHD-MAIN-FIXTEST-v1 일 5 driver (host; every step in Docker through run_step_ft.sh): the new distance metric of this task's results that have
# their post steps done (dm_ft d2 per site, d2b for B0), the d3 blocks, the place tables, the mechanisms of fix A (band_w) and fix B (mech_b).
#   bash eval_ft.sh [site ...]        (default: the three sites; a site's d2 counts only results not counted yet)
# One heavy step at a time (the training queue's CPU slot lock logs/slot0.lock is taken for d2, so the post steps and d2 do not overlap).
# scientific_verdict: null.
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd); REPO=$(cd "$HERE/../../.." && pwd); ART=$(realpath "$REPO/../JointBuildGS-artifacts")
FT="$ART/phase-payloads/phd/main_fixtest_v1/PHD-MAIN-FIXTEST-v1"
sites=("$@"); [ ${#sites[@]} -eq 0 ] && sites=(B0_b10 B173nb_b10 R1rep_b10)
todo() {   # this task's PASS results of a site whose post steps are done and whose dist file is missing
  local s=$1
  for d in "$FT"/runs/"$s"/fix*_s0; do
    [ -d "$d" ] || continue; r=$(basename "$d")
    [ -f "$d/receipt.json" ] && grep -q '"status": "PASS"' "$d/receipt.json" || continue
    [ -f "$FT/metrics/$s/${r}__LoD2.json" ] || [ -f "$FT/metrics/$s/${r}__ALS.json" ] || continue
    p=LoD2; [[ $r == *_ALS_* ]] && p=ALS
    [ -f "$FT/dist/${s}_${p}__${r}.npz" ] || echo "$r"
  done
}
for s in "${sites[@]}"; do
  res=$(todo "$s" | tr '\n' ' ')
  [ -n "${res// }" ] || continue
  ( exec 9>>"$FT/logs/slot0.lock"; flock 9; CPUS=16 MEM=40 bash "$HERE/run_step_ft.sh" "dm_d2_${s}_$(date +%H%M)" dm_ft.py d2 "$s" $res )
  if [ "$s" = B0_b10 ]; then ( exec 9>>"$FT/logs/slot0.lock"; flock 9; CPUS=16 MEM=40 bash "$HERE/run_step_ft.sh" "dm_d2b_$(date +%H%M)" dm_ft.py d2b $res ); fi
done
CPUS=8 MEM=24 bash "$HERE/run_step_ft.sh" "dm_d3_$(date +%H%M)" dm_ft.py d3
CPUS=4 MEM=16 bash "$HERE/run_step_ft.sh" "tables_$(date +%H%M)" tables_ft.py
CPUS=8 MEM=24 bash "$HERE/run_step_ft.sh" "mechb_$(date +%H%M)" mech_b.py
echo "eval_ft done $(date '+%m-%d %H:%M:%S')"
