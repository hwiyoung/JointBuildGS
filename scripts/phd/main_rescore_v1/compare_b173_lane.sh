#!/usr/bin/env bash
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
OUT=$(realpath "$REPO/../JointBuildGS-artifacts")/phase-payloads/phd/main_rescore_v1/PHD-MAIN-RESCORE-v1
lane=$1
if [[ "$lane" == A ]]; then
 first=B173nb_b10__LoD2__r8_7000
 keys=(B173nb_b10__ALS__baseline_30000 B173nb_b10__ALS__GeoGS_30000 B173nb_b10__ALS__CDGS_30000 B173nb_b10__ALS__fusion)
else
 first=B173nb_b10__LoD2__baseline_30000
 keys=(B173nb_b10__LoD2__GeoGS_30000 B173nb_b10__LoD2__2DGS_30000 B173nb_b10__LoD2__CDGS_30000 B173nb_b10__LoD2__fusion)
fi
until [[ -f "$OUT/meshes/$first/final.json" ]]; do sleep 20; done
bash "$REPO/scripts/phd/main_rescore_v1/run.sh" "score-$first" score_mesh.py B173nb_b10 LoD2 "$first" "/out/meshes/$first/final.ply"
for key in "${keys[@]}"; do
 until [[ -f "$OUT/jobs/$key.json" && -f "$OUT/renders/$key/receipt.json" ]]; do sleep 20; done
 bash "$REPO/scripts/phd/main_rescore_v1/run_mesh_named.sh" "jobs/$key.json" final
 prior=LoD2;[[ "$key" != *'__ALS__'* ]] || prior=ALS
 bash "$REPO/scripts/phd/main_rescore_v1/run.sh" "score-$key" score_mesh.py B173nb_b10 "$prior" "$key" "/out/meshes/$key/final.ply"
 if [[ "$key" == B173nb_b10__LoD2__2DGS_30000 ]]; then
  bash "$REPO/scripts/phd/main_rescore_v1/run.sh" score-2dgs-als score_mesh.py B173nb_b10 ALS B173nb_b10__ALS__2DGS_30000 "/out/meshes/$key/final.ply"
 fi
done
