#!/bin/bash
# 2026-11-20 14:30 (user decision): B173 x LoD2 seed-1 run gtt_s1. When its receipt exists and the stage-3 mesh workers
# (g_mesh 293601, g3_mesh_helper) are gone, extract with 2 workers:
#   COMPLETED   -> gtt_s1 iteration 30000, four variants
#   otherwise   -> nothing for gtt_s1 (result absent)
# and in both cases the earlier decision for gtt_s0_rerun1 (stopped twice): iteration 15000 model as a reference row, four variants.
cd "$(dirname "$0")"
P=../../../../JointBuildGS-artifacts/phase-payloads/phd/main_gttarget_v1/PHD-MAIN-GTTARGET-v1; S=B173nb_b10__LoD2
until [ -f $P/runs/$S/gtt_s1/receipt.json ]; do sleep 120; done
st=$(python3 -c "import json;print(json.load(open('$P/runs/$S/gtt_s1/receipt.json'))['status'])"); echo "$(date +%FT%T) gtt_s1 receipt $st"
while [ -d /proc/293601 ] || ps -eo args | grep -q '^python3 g3_mesh_helpe[r]'; do sleep 120; done; echo "$(date +%FT%T) mesh workers gone"
J=()
if [ "$st" = COMPLETED ]; then for v in base occl median_depth occl_median; do J+=("$S:gtt_s1_$v:model:0:/te/runs/$S/gtt_s1/model/point_cloud/iteration_30000/point_cloud.ply:$v"); done; fi
for v in base occl median_depth occl_median; do J+=("$S:gtt_s0_rerun1_it15000_$v:model:0:/te/runs/$S/gtt_s0_rerun1/model/point_cloud/iteration_15000/point_cloud.ply:$v"); done
printf '%s\n' "${J[@]}"
GT_FASTWORK=/home/innopam/jbgs_fastwork_gtt python3 g_mesh.py 2 "${J[@]}"
echo "$(date +%FT%T) WAIT_S1_DONE"
