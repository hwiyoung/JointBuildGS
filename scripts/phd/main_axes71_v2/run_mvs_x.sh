#!/usr/bin/env bash
# PHD-MAIN-AXES71-v2: the result-side distances of the MVS surfaces made after the site runs (R1 판 가, B173 주변 판 나; R1 판 나 when it exists).
R=$(cd "$(dirname "$0")" && pwd)
CPUS=24 MEM=30 bash "$R/run_cpu_ax.sh" a2x_R1_mvs_a a2x_sample.py R1rep_b10 mvs_a
CPUS=24 MEM=30 bash "$R/run_cpu_ax.sh" a2x_B173nb_mvs_b a2x_sample.py B173nb_b10 mvs_b
while [ ! -f /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_axes71_v2/PHD-MAIN-AXES71-v2/mvs/R1rep_b10/receipt_R1rep_b10.json ] || ! grep -q mesh_mvs_b /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_axes71_v2/PHD-MAIN-AXES71-v2/mvs/R1rep_b10/receipt_R1rep_b10.json 2>/dev/null; do sleep 30; done
CPUS=24 MEM=30 bash "$R/run_cpu_ax.sh" a2x_R1_mvs_b a2x_sample.py R1rep_b10 mvs_b
