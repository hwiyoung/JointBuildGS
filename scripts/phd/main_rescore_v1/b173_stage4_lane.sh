#!/usr/bin/env bash
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
OUT=$(realpath "$REPO/../JointBuildGS-artifacts")/phase-payloads/phd/main_rescore_v1/PHD-MAIN-RESCORE-v1
prior=$1
for family in judgment_mesh oracle; do
 key="B173nb_b10__${prior}__${family}"
 if [[ ! -f "$OUT/renders/$key/receipt.json" ]]; then bash "$REPO/scripts/phd/main_rescore_v1/run.sh" "patch-$key" render_patches.py B173nb_b10 "$prior" "$family"; fi
 bash "$REPO/scripts/phd/main_rescore_v1/run_mesh_safe.sh" "jobs/$key.json" final
 if [[ ! -f "$OUT/scores/$key/values.json" ]]; then bash "$REPO/scripts/phd/main_rescore_v1/run_score16.sh" "score-$key" score_mesh.py B173nb_b10 "$prior" "$key" "/out/meshes/$key/final.ply"; fi
done
bash "$REPO/scripts/phd/main_rescore_v1/run.sh" "quality-$prior-judgment" target_quality.py B173nb_b10 "$prior" judgment_mesh "B173nb_b10__${prior}__judgment_mesh"
iteration=30000; [[ "$prior" != LoD2 ]] || iteration=7000
bash "$REPO/scripts/phd/main_rescore_v1/run.sh" "quality-$prior-r8" target_quality.py B173nb_b10 "$prior" r8 "B173nb_b10__${prior}__r8_${iteration}"
