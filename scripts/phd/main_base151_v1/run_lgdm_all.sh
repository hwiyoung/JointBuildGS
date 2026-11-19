#!/usr/bin/env bash
# PHD-MAIN-BASE151-v1 LGDM chain (configs/phd/main_base151_v1/inputs_LGDM.json): per prior judge -> compose (4 cells) -> patches -> receipt,
# one container at a time (run_lgdm_cpu.sh waits while MemAvailable < 40 GB). Logs: OUT/lgdm/logs/. scientific_verdict: null
#   nohup bash run_lgdm_all.sh [ALS LoD2] &
set -euo pipefail
cd "$(dirname "$0")"
W=$(cd ../../.. && pwd)
L="$(realpath "$W/../JointBuildGS-artifacts")/phase-payloads/phd/main_base151_v1/PHD-MAIN-BASE151-v1/lgdm/logs"
priors=("$@"); [ ${#priors[@]} -eq 0 ] && priors=(ALS LoD2)
for p in "${priors[@]}"; do
  q=$(echo "$p" | tr 'A-Z' 'a-z')
  for step in judge compose patches receipt; do
    case $step in
      judge) args=(judge "$p" --nproc 6); res=(12 22g);;
      compose) args=(compose "$p" all --nproc 8); res=(12 22g);;
      patches) args=(patches "$p"); res=(4 8g);;
      receipt) args=(receipt "$p"); res=(2 4g);;
    esac
    t0=$(date +%s)
    echo "$(date '+%F %T') $p $step start" >> "$L/chain.log"
    if bash run_lgdm_cpu.sh "$step-$q" "${res[@]}" b151_lgdm_detect.py "${args[@]}" > "$L/${step}_$p.log" 2>&1; then
      echo "$(date '+%F %T') $p $step done $(( $(date +%s) - t0 )) s" >> "$L/chain.log"
    else
      rc=$?; echo "$(date '+%F %T') $p $step FAILED rc=$rc $(( $(date +%s) - t0 )) s" >> "$L/chain.log"; exit $rc
    fi
  done
done
echo "$(date '+%F %T') chain end" >> "$L/chain.log"
