#!/usr/bin/env bash
# PHD-MAIN-AXES71-v2: tables and figures again after the display name of CDGS changed (values the same). scientific_verdict: null.
R=$(cd "$(dirname "$0")" && pwd)
run() { CPUS=${CPUS:-16} MEM=${MEM:-32} bash "$R/run_cpu_ax.sh" "$@" || echo "FAIL $1"; }
run r_a3t a3_tables.py
run r_a3b a3b_criterion.py
run r_a3c a3c_checks.py
run r_a4 a4_axes.py &
run r_a5 a5_cdf.py &
run r_a6 a6_clumps.py &
run r_a7b a7_boundary.py &
wait
run r_a4f a4_fig.py
run r_a7m a7_missing.py
run r_a5f a5_fig.py
run r_a8 a8_check.py
run r_a8f a8_figs3.py
run r_a9 a9_metrics.py
run r_it interim_tables.py
run r_num ax_numbers.py
run r_fin final_report.py
