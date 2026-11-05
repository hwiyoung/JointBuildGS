#!/usr/bin/env bash
set -euo pipefail
for site in B173nb_b10 B0_b10 R1rep_b10; do
  for prior in ALS LoD2; do
    bash scripts/phd/main_recount_v1/run_cpu.sh "${site}_${prior}" recount.py "$site" "$prior"
  done
done
