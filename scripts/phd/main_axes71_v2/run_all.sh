#!/usr/bin/env bash
# PHD-MAIN-AXES71-v2: 일 3-8 values, tables and figures one after another (CPU; no training, no GPU). scientific_verdict: null.
R=$(cd "$(dirname "$0")" && pwd)
run() { CPUS=${CPUS:-16} MEM=${MEM:-32} bash "$R/run_cpu_ax.sh" "$@" || echo "FAIL $1"; }
run p_a3 a3_metrics.py
run p_a3b a3b_criterion.py
run p_a3t a3_tables.py
run p_a4 a4_axes.py
run p_a4f a4_fig.py
run p_a5 a5_cdf.py
run p_a6 a6_clumps.py
run p_a6m a6_maps.py
run p_a7b a7_boundary.py
run p_a7m a7_missing.py
run p_a5f a5_fig.py
run p_a8 a8_check.py
run p_a8f a8_figs3.py
