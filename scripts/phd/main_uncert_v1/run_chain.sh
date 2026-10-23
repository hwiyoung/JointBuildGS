#!/usr/bin/env bash
# PHD-MAIN-UNCERT-v1 일 2 chain of u2_run.py steps for the given ring radii (one CPU container per step, nice 19).
#   [CPUS=48] [MEM=40] bash run_chain.sh <radii e.g. 1.5 or 1.0,3.0> [data ...]   (default data: mvs_a als mvs_b)
# Order: per data, per site, LoD2 then ALS patch set (als: ALS set only). Stops at the first failing step. scientific_verdict: null.
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
radii=$1; shift
datas=${*:-mvs_a als mvs_b}
CPUS=${CPUS:-48}; MEM=${MEM:-40}
for d in $datas; do
  for s in B0_b10 B173nb_b10 R1rep_b10; do
    for p in LoD2 ALS; do
      [ "$d" = als ] && [ "$p" = LoD2 ] && continue
      CPUS=$CPUS MEM=$MEM bash "$HERE/run_cpu_uc.sh" "u2_${d}_${s%%_*}_${p}_R${radii//,/_}" u2_run.py "$s" "$p" "$d" "$radii" --workers "$CPUS" || exit 1
    done
  done
done
