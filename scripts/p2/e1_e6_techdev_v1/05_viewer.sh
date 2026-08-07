#!/usr/bin/env bash
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
mvs_mesh_root="${prep_root}/viewer_surface_meshes"
mvs_mesh="${mvs_mesh_root}/E2_openmvs_mesh.ply"
mkdir -p "${mvs_mesh_root}"
if [[ ! -f "${mvs_mesh}" ]]; then
  mvs_source="${artifact_root}/phase-payloads/p2/mvs_native_textured_mesh_preflight_v1/P2-MVS-NATIVE-DENSE-SCENE-RECOVERY-v2/work/mvs/openmvs"
  p0_data="${artifact_root}/phase-payloads/p0-audit/data"
  docker run --rm --network none --cpus 24 --memory 100g --pids-limit 4096 \
    --user "$(id -u):$(id -g)" -e HOME=/tmp \
    -v "${mvs_source}:/source:ro" -v "${p0_data}:/workspace/data:ro" \
    -v "${mvs_mesh_root}:/output:rw" \
    -w /output --entrypoint /usr/local/bin/OpenMVS/ReconstructMesh \
    jointbuildgs-p0-openmvs:t0 \
    -i /source/dim_dense.mvs -o /output/E2_openmvs_mesh.ply \
    --max-threads 24 --min-point-distance 2.5 --decimate 0.25 \
    --remove-spurious 20 --remove-spikes 1 --close-holes 30 --smooth 2 \
    >"${logs_root}/05_E2_openmvs_reconstruct_mesh.log" 2>&1
fi
run_dev python scripts/p2/e1_e6_techdev_v1/prepare_viewer_surface_meshes.py \
  --task-root "/artifacts/JointBuildGS/${task_rel}" \
  >"${logs_root}/05_viewer_surface_meshes.log" 2>&1
run_dev python scripts/p2/e1_e6_techdev_v1/extract_real_change_candidates.py \
  --artifact-root /artifacts/JointBuildGS \
  --task-root "/artifacts/JointBuildGS/${task_rel}" \
  >"${logs_root}/05_real_change_candidates.log" 2>&1
run_dev python scripts/p2/e1_e6_techdev_v1/prepare_viewer_pointclouds.py \
  --artifact-root /artifacts/JointBuildGS \
  --task-root "/artifacts/JointBuildGS/${task_rel}" \
  >"${logs_root}/05_viewer_pointclouds.log" 2>&1
run_dev python scripts/p2/e1_e6_techdev_v1/build_viewer.py \
  --repository-root /workspace/JointBuildGS --artifact-root /artifacts/JointBuildGS \
  >"${logs_root}/05_viewer.log" 2>&1
printf 'Viewer ready: %s/viewer/index.html\n' "${task_root}"
