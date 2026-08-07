#!/usr/bin/env bash
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

roofer_image="3dgi/roofer@sha256:dd2c415aaee337502bde0dc1426dfa9c9f88e648f9d2f6340110c49932c251d2"
for baseline in E1 E2; do
  run_dev python scripts/p2/e1_e6_techdev_v1/prepare_roofer.py reuse-baseline \
    --artifact-root /artifacts/JointBuildGS --condition "${baseline}" \
    >"${logs_root}/04_roofer_${baseline}.log" 2>&1
done
for condition in E3 E4 E5 E6; do
  case "${condition}" in
    E3) run_name=E3_GS_IMAGE ;;
    E4) run_name=E4_GS_ALS_UNWEIGHTED ;;
    E5) run_name=E5_GS_ALS_WB ;;
    E6) run_name=E6_GS_LOD2_PLANES_DIAGNOSTIC ;;
  esac
  roofer_root="${task_root}/runs/${run_name}/roofer"
  if [[ -f "${roofer_root}/receipt.json" ]]; then
    grep -q 'c1_c2_shared_footprint_199_v3/run.py::_common_stages' \
      "${roofer_root}/classified_scene_receipt.json" || {
        echo "refusing uncertified Roofer receipt: ${condition}" >&2
        exit 2
      }
    printf 'SKIP Roofer %s\n' "${condition}"
    continue
  fi
  run_tools python scripts/p2/e1_e6_techdev_v1/prepare_roofer.py prepare \
    --artifact-root /artifacts/JointBuildGS --run-name "${run_name}" \
    >"${logs_root}/04_roofer_${condition}_prepare.log" 2>&1
  if [[ ! -f "${roofer_root}/classified_scene.laz" ]]; then
    run_tools pdal pipeline "/artifacts/JointBuildGS/${task_rel}/runs/${run_name}/roofer/classification_pipeline.json" \
      >"${logs_root}/04_roofer_${condition}_classify.log" 2>&1
  fi
  run_tools python scripts/p2/e1_e6_techdev_v1/prepare_roofer.py verify \
    --artifact-root /artifacts/JointBuildGS --run-name "${run_name}" \
    >"${logs_root}/04_roofer_${condition}_verify.log" 2>&1
  mkdir -p "${roofer_root}/output"
  docker run --rm --network none --cpus 12 --memory 64g --pids-limit 4096 \
    --user "$(id -u):$(id -g)" -v "${task_root}:/task:rw" \
    -v "${artifact_root}/phase-payloads/p2/c1_c2_shared_footprint_199_v3/P2-C1-C2-SHARED-FOOTPRINT-199-ORIGINAL-GLOBAL-v3-replay-20260806a/freeze/shared_footprints_199.geojson:/task/shared_footprints_199.geojson:ro" \
    -w /task "${roofer_image}" --id-attribute stable_id --jobs 1 \
    --box 690791.740 5335864.050 691154.650 5336353.850 \
    "runs/${run_name}/roofer/classified_scene.laz" shared_footprints_199.geojson \
    "runs/${run_name}/roofer/output" >"${logs_root}/04_roofer_${condition}.log" 2>&1
  run_dev python scripts/p2/e1_e6_techdev_v1/prepare_roofer.py finalize \
    --artifact-root /artifacts/JointBuildGS --run-name "${run_name}" \
    >"${logs_root}/04_roofer_${condition}_finalize.log" 2>&1
done
printf 'Six Roofer conditions complete.\n'
