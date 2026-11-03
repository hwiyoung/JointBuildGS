#!/usr/bin/env bash
# Models exist, but JA cells and frozen reference normals do not exist for this scope.
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
OUT=$(realpath "$REPO/../JointBuildGS-artifacts")/phase-payloads/phd/main_rescore_v1/PHD-MAIN-RESCORE-v1
cd "$REPO";site=B173_b0
bash scripts/phd/main_rescore_v1/run.sh "setup-$site" setup_site.py "$site"
if [[ ! -f "$OUT/views/$site.json" ]]; then bash scripts/phd/main_rescore_v1/run_gpu.sh "jobs/${site}__views.json" freeze_views.py; fi
for prior in ALS LoD2; do for family in GeoGS CDGS 2DGS; do
 if [[ "$family" == 2DGS && "$prior" == ALS ]]; then continue; fi
 key="${site}__${prior}__${family}_30000"
 if [[ ! -f "$OUT/renders/$key/receipt.json" ]]; then bash scripts/phd/main_rescore_v1/run_gpu.sh "jobs/$key.json"; fi
 bash scripts/phd/main_rescore_v1/run_mesh_safe.sh "jobs/$key.json" final
done; done
bash scripts/phd/main_rescore_v1/run.sh reuse-B173-only reused_meshes.py "$site"
if [[ ! -f "$OUT/reference/normals_${site}.npz" ]]; then bash scripts/phd/main_rescore_v1/run.sh reference-B173-only scene_reference.py; fi
for prior in ALS LoD2; do for family in prior GeoGS_30000 CDGS_30000 2DGS_30000; do
 key="${site}__${prior}__${family}";mesh="/out/meshes/$key/final.ply"
 if [[ "$family" == prior ]]; then mesh="/art/phase-payloads/phd/main_stage1_v1/PHD-MAIN-STAGE1-v1/defs/$site/prior_$prior.npz"; fi
 if [[ "$family" == 2DGS_30000 ]]; then mesh="/out/meshes/${site}__LoD2__2DGS_30000/final.ply"; fi
 if [[ ! -f "$OUT/scores/$key/values.json" ]]; then bash scripts/phd/main_rescore_v1/run_score16.sh "scene-$key" score_scene_only.py "$prior" "$key" "$mesh"; fi
done; done
bash scripts/phd/main_rescore_v1/run.sh record-unavailable record_unavailable.py
