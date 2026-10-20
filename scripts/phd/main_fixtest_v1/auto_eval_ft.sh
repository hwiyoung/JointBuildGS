#!/usr/bin/env bash
# PHD-MAIN-FIXTEST-v1 일 5 (host driver; every step in Docker): while the training queue runs, evaluate each finished result once its post
# steps are done, so that the final evaluation only has to remake the tables:
#   - eval_ft.sh <site> when a PASS result of the site has its metrics json but no dist file (the new distance metric, d2b for B0, then
#     d3, the place tables and the fix-B mechanism; d2 waits for the queue's CPU slot lock, so it never runs beside a post step)
#   - band_w.py for fix-A results (fixA_ reading L, fixAT_ reading T, fixAB_ reading L) whose 30,000 dump exists and whose band file has no
#     entry for them yet (the method's seeds are already in the band files)
# Ends when logs/QUEUE_DONE.json exists and nothing is left. Log: logs/auto_eval.log.
#   bash auto_eval_ft.sh
# scientific_verdict: null.
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd); REPO=$(cd "$HERE/../../.." && pwd); ART=$(realpath "$REPO/../JointBuildGS-artifacts")
FT="$ART/phase-payloads/phd/main_fixtest_v1/PHD-MAIN-FIXTEST-v1"
LOG="$FT/logs/auto_eval.log"
say() { echo "$(date '+%m-%d %H:%M:%S') $*" | tee -a "$LOG"; }
need_dist() {   # PASS results of a site with metrics and without a dist file
  local s=$1
  for d in "$FT"/runs/"$s"/fix*_s0; do
    [ -d "$d" ] || continue; r=$(basename "$d")
    [ -f "$d/receipt.json" ] && grep -q '"status": "PASS"' "$d/receipt.json" || continue
    p=LoD2; [[ $r == *_ALS_* ]] && p=ALS
    [ -f "$FT/metrics/$s/${r}__$p.json" ] || continue
    [ -f "$FT/dist/${s}_${p}__${r}.npz" ] || echo "$r"
  done
}
need_band() {   # "site prior reading result" of fix-A results with a dump and no band entry
  for d in "$FT"/runs/*/fixA*_s0; do
    [ -d "$d" ] || continue; r=$(basename "$d"); s=$(basename "$(dirname "$d")")
    [ -f "$d/receipt.json" ] && grep -q '"status": "PASS"' "$d/receipt.json" || continue
    [ -d "$d/model/dump/iteration_30000" ] || continue
    p=LoD2; [[ $r == *_ALS_* ]] && p=ALS
    rd=L; [[ $r == fixAT_* ]] && rd=T
    f="$FT/mech/bands_${s}_${p}_${rd}.json"
    [ -f "$f" ] && grep -q "\"$r\"" "$f" && continue
    echo "$s $p $rd $r"
  done
}
declare -A TRIES
say "auto_eval start"
while true; do
  did=0
  while read -r s p rd r; do
    [ -n "${r:-}" ] || continue
    k="band:$s:$p:$rd:$r"; TRIES[$k]=$(( ${TRIES[$k]:-0} + 1 ))
    [ "${TRIES[$k]}" -gt 2 ] && continue
    say "band_w $s $p $rd $r"
    CPUS=4 MEM=16 bash "$HERE/run_step_ft.sh" "bandw_${s}_${p}_${rd}_${r}" band_w.py "$s" "$p" "$rd" "$r" > /dev/null
    say "band_w $r rc=$?"; did=1
  done < <(need_band)
  for s in B0_b10 B173nb_b10 R1rep_b10; do
    res=$(need_dist "$s" | tr '\n' ' ')
    [ -n "${res// }" ] || continue
    k="$s:$res"; TRIES[$k]=$(( ${TRIES[$k]:-0} + 1 ))
    if [ "${TRIES[$k]}" -gt 2 ]; then
      [ "${TRIES[$k]}" -eq 3 ] && say "eval $s: $res — the distance files were not made in two tries; left for the final evaluation (see logs/dm_d2_*)"
      continue
    fi
    say "eval $s: $res"
    bash "$HERE/eval_ft.sh" "$s" >> "$LOG" 2>&1
    say "eval $s rc=$?"; did=1
  done
  if [ -f "$FT/logs/QUEUE_DONE.json" ] && [ $did -eq 0 ]; then
    say "auto_eval done (left: bands [$(need_band | tr '\n' ';')] dist [$(for s in B0_b10 B173nb_b10 R1rep_b10; do need_dist "$s"; done | tr '\n' ' ')])"; break
  fi
  sleep 300
done
