#!/bin/bash
# Stage 3 order 8 chain (2026-11-20): per scene state + track (CPU), pix (GPU 1), labels, causes; causes waits until the four gtt_s0 extractions are scored.
cd "$(dirname "$0")"; P=../../../../JointBuildGS-artifacts/phase-payloads/phd/main_gttarget_v1/PHD-MAIN-GTTARGET-v1
for s in R1rep_b10__ALS R1rep_b10__LoD2 B0_b10__LoD2 B173nb_b10__ALS B0_b10__ALS; do
  [ -f $P/ca/state_${s}_gtt_s0.npz ] || python3 launch.py cpu g3_ca.py state $s; echo "$(date +%T) state $s $?"
  python3 launch.py cpu g3_ca.py track $s; echo "$(date +%T) track $s $?"
  python3 launch.py gpu 1 g3_ca.py pix $s; echo "$(date +%T) pix $s $?"
  python3 launch.py cpu g3_ca.py labels $s; echo "$(date +%T) labels $s $?"
  until [ -f $P/meshes/${s}__gtt_s0_base/score.json ] && [ -f $P/meshes/${s}__gtt_s0_occl/score.json ] && [ -f $P/meshes/${s}__gtt_s0_median_depth/score.json ] && [ -f $P/meshes/${s}__gtt_s0_occl_median/score.json ]; do sleep 120; done
  python3 launch.py cpu g3_ca.py causes $s; echo "$(date +%T) causes $s $?"
done
echo "$(date +%T) CA_CHAIN_DONE"
