#!/usr/bin/env bash
# PHD-MAIN-B0REF-v1 일 1 queue: GeoGS, then the three LAS crops one at a time, each after wait_mem.sh. scientific_verdict: null.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd)
bash "$H/run_cpu.sh" crop_geogs c1_crop.py geogs
for s in uls_nadir uls_manual photogrammetry; do
  bash "$H/wait_mem.sh" "crop_$s"
  CPUS=8 MEM=8 bash "$H/run_cpu.sh" "crop_$s" c1_crop.py "$s"
done
