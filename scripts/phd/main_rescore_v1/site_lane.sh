#!/usr/bin/env bash
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
OUT=$(realpath "$REPO/../JointBuildGS-artifacts")/phase-payloads/phd/main_rescore_v1/PHD-MAIN-RESCORE-v1
site=$1;prior=$2;phase=$3
families=(baseline_30000 GeoGS_30000 CDGS_30000 fusion)
if [[ "$phase" == targets ]]; then families=(judgment_mesh oracle); fi
if [[ "$phase" == comparison && "$prior" == LoD2 ]]; then families+=(2DGS_30000); fi
for family in "${families[@]}"; do
 key="${site}__${prior}__${family}"
 bash "$REPO/scripts/phd/main_rescore_v1/run_mesh_safe.sh" "jobs/$key.json" final
 if [[ ! -f "$OUT/scores/$key/values.json" ]]; then bash "$REPO/scripts/phd/main_rescore_v1/run_score16.sh" "score-$key" score_mesh.py "$site" "$prior" "$key" "/out/meshes/$key/final.ply"; fi
done
if [[ "$phase" == comparison && "$prior" == ALS ]]; then
 source="${site}__LoD2__2DGS_30000";key="${site}__ALS__2DGS_30000"
 until [[ -f "$OUT/meshes/$source/final.json" ]]; do sleep 30; done
 if [[ ! -f "$OUT/scores/$key/values.json" ]]; then bash "$REPO/scripts/phd/main_rescore_v1/run_score16.sh" "score-$key" score_mesh.py "$site" ALS "$key" "/out/meshes/$source/final.ply"; fi
fi
if [[ "$phase" == targets ]]; then bash "$REPO/scripts/phd/main_rescore_v1/run.sh" "quality-$site-$prior" target_quality.py "$site" "$prior" judgment_mesh "${site}__${prior}__judgment_mesh"; fi
