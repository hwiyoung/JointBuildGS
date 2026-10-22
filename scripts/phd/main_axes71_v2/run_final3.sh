#!/usr/bin/env bash
# PHD-MAIN-AXES71-v2 차례 4: 일 3 again (R1 MVS 판 나 included), its tables and checks, 일 9 tables, numbers. scientific_verdict: null.
R=$(cd "$(dirname "$0")" && pwd)
run() { CPUS=${CPUS:-16} MEM=${MEM:-32} bash "$R/run_cpu_ax.sh" "$@" || echo "FAIL $1"; }
run f_a3 a3_metrics.py
run f_a3b a3b_criterion.py
run f_a3t a3_tables.py
run f_a3c a3c_checks.py
run f_a9 a9_metrics.py
run f_a9c a9c_checks.py
run f_num ax_numbers.py
