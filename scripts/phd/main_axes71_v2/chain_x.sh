#!/usr/bin/env bash
# PHD-MAIN-AXES71-v2: the result-side distances of the three sites one after another (after the normals). scientific_verdict: null.
R=$(cd "$(dirname "$0")" && pwd)
while docker ps --format '{{.Names}}' | grep -q '^jbgs-ax-a1_normals'; do sleep 20; done
for s in R1rep_b10 B0_b10 B173nb_b10; do CPUS=16 MEM=${MEM:-44} bash "$R/run_cpu_ax.sh" "a2x_$s" a2x_sample.py "$s"; done
