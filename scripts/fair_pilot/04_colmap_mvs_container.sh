#!/usr/bin/env bash
set -u -o pipefail

ROOT=/workspace/JointBuildGS
CONFIG="${ROOT}/configs/fair_pilot/vaihingen_area3.json"
RUN_DIR="${ROOT}/fair-pilot/runs/20260714_vaihingen_area3"
WORKSPACE="${RUN_DIR}/workspace"
LOG="${RUN_DIR}/run.log"
STATUS="${RUN_DIR}/mvs_step_status.tsv"
MVS_DIR="${RUN_DIR}/mvs"

mkdir -p "${MVS_DIR}"
: > "${STATUS}"
date --iso-8601=seconds | tr '\n' '\t' >> "${LOG}"
printf 'stage=colmap_mvs status=started gpu=host1_container0\n' >> "${LOG}"
colmap -h 2>&1 | head -1 > "${RUN_DIR}/colmap_version.txt"

rm -rf "${WORKSPACE}/sparse"
mkdir -p "${WORKSPACE}/sparse"
started="$(date +%s)"
colmap model_converter \
  --input_path "${WORKSPACE}/sparse_text" \
  --output_path "${WORKSPACE}/sparse" \
  --output_type BIN 2>&1 | tee -a "${LOG}"
rc="${PIPESTATUS[0]}"
elapsed="$(( $(date +%s) - started ))"
printf 'model_converter\t%s\t%s\t%s\n' "${rc}" "${elapsed}" "$([ "${rc}" -eq 0 ] && printf ok || printf failed)" >> "${STATUS}"
if [ "${rc}" -ne 0 ]; then
  date --iso-8601=seconds | tr '\n' '\t' >> "${LOG}"
  printf 'stage=colmap_mvs status=partial failed_step=model_converter returncode=%s\n' "${rc}" >> "${LOG}"
  exit 0
fi

# A hand-built dense workspace does not get these directories from
# image_undistorter. Reuse a complete geometric depth cache after a fusion-only
# interruption only when the exact images, poses, configs, and runner match;
# otherwise clear partial maps and run PatchMatch from scratch.
CACHE_LOCK="${WORKSPACE}/stereo/cache_inputs.sha256"
cache_fingerprint="$({
  sha256sum "$0"
  find "${WORKSPACE}/images" "${WORKSPACE}/sparse_text" -type f -print0 | sort -z | xargs -0 sha256sum
  sha256sum "${WORKSPACE}/stereo/patch-match.cfg" "${WORKSPACE}/stereo/fusion.cfg"
} | sha256sum | awk '{print $1}')"
cached_fingerprint="$(cat "${CACHE_LOCK}" 2>/dev/null || true)"
geometric_count="$(find "${WORKSPACE}/stereo/depth_maps" -maxdepth 1 -name '*.geometric.bin' 2>/dev/null | wc -l)"
if [ "${geometric_count}" -eq 10 ] && [ "${cached_fingerprint}" = "${cache_fingerprint}" ]; then
  printf 'patch_match_stereo\t0\t0\treused_complete_geometric_cache\n' >> "${STATUS}"
  date --iso-8601=seconds | tr '\n' '\t' >> "${LOG}"
  printf 'stage=colmap_mvs patch_match=reused geometric_maps=10 cache_fingerprint=%s\n' "${cache_fingerprint}" >> "${LOG}"
  rc=0
else
  rm -rf "${WORKSPACE}/stereo/depth_maps" "${WORKSPACE}/stereo/normal_maps" "${WORKSPACE}/stereo/consistency_graphs"
  mkdir -p "${WORKSPACE}/stereo/depth_maps" "${WORKSPACE}/stereo/normal_maps" "${WORKSPACE}/stereo/consistency_graphs"
  started="$(date +%s)"
  timeout --signal=TERM 240m colmap patch_match_stereo \
  --workspace_path "${WORKSPACE}" \
  --workspace_format COLMAP \
  --config_path "${WORKSPACE}/stereo/patch-match.cfg" \
  --PatchMatchStereo.gpu_index 0 \
  --PatchMatchStereo.depth_min 700 \
  --PatchMatchStereo.depth_max 1100 \
  --PatchMatchStereo.max_image_size -1 \
  --PatchMatchStereo.num_samples 10 \
  --PatchMatchStereo.num_iterations 3 \
  --PatchMatchStereo.geom_consistency 1 \
  --PatchMatchStereo.filter 1 \
  --PatchMatchStereo.filter_min_num_consistent 2 \
    --PatchMatchStereo.cache_size 8 2>&1 | tee -a "${LOG}"
  rc="${PIPESTATUS[0]}"
  elapsed="$(( $(date +%s) - started ))"
  reason="$([ "${rc}" -eq 124 ] && printf timeout || { [ "${rc}" -eq 0 ] && printf ok || printf failed; })"
  printf 'patch_match_stereo\t%s\t%s\t%s\n' "${rc}" "${elapsed}" "${reason}" >> "${STATUS}"
  if [ "${rc}" -eq 0 ]; then
    printf '%s\n' "${cache_fingerprint}" > "${CACHE_LOCK}"
  fi
fi
if [ "${rc}" -ne 0 ]; then
  date --iso-8601=seconds | tr '\n' '\t' >> "${LOG}"
  printf 'stage=colmap_mvs status=partial failed_step=patch_match_stereo returncode=%s\n' "${rc}" >> "${LOG}"
  exit 0
fi

started="$(date +%s)"
timeout --signal=TERM 60m colmap stereo_fusion \
  --workspace_path "${WORKSPACE}" \
  --workspace_format COLMAP \
  --input_type geometric \
  --output_path "${MVS_DIR}/fused_source_epsg32632.ply" \
  --output_type PLY \
  --StereoFusion.max_reproj_error 2 \
  --StereoFusion.min_num_pixels 3 \
  --StereoFusion.max_depth_error 0.02 \
  --StereoFusion.cache_size 8 2>&1 | tee -a "${LOG}"
rc="${PIPESTATUS[0]}"
elapsed="$(( $(date +%s) - started ))"
reason="$([ "${rc}" -eq 124 ] && printf timeout || { [ "${rc}" -eq 0 ] && printf ok || printf failed; })"
printf 'stereo_fusion\t%s\t%s\t%s\n' "${rc}" "${elapsed}" "${reason}" >> "${STATUS}"
if [ "${rc}" -eq 0 ] && grep -a -q '^element vertex 0$' "${MVS_DIR}/fused_source_epsg32632.ply"; then
  date --iso-8601=seconds | tr '\n' '\t' >> "${LOG}"
  printf 'stage=colmap_mvs geometric_fusion=zero_points recovery=photometric_fusion\n' >> "${LOG}"
  started="$(date +%s)"
  timeout --signal=TERM 60m colmap stereo_fusion \
    --workspace_path "${WORKSPACE}" \
    --workspace_format COLMAP \
    --input_type photometric \
    --output_path "${MVS_DIR}/fused_photometric_source_epsg32632.ply" \
    --output_type PLY \
    --StereoFusion.max_reproj_error 2 \
    --StereoFusion.min_num_pixels 3 \
    --StereoFusion.max_depth_error 0.02 \
    --StereoFusion.cache_size 8 2>&1 | tee -a "${LOG}"
  recovery_rc="${PIPESTATUS[0]}"
  recovery_elapsed="$(( $(date +%s) - started ))"
  recovery_reason="$([ "${recovery_rc}" -eq 124 ] && printf timeout || { [ "${recovery_rc}" -eq 0 ] && printf geometric_zero_recovery || printf failed; })"
  printf 'stereo_fusion_photometric\t%s\t%s\t%s\n' "${recovery_rc}" "${recovery_elapsed}" "${recovery_reason}" >> "${STATUS}"
fi
date --iso-8601=seconds | tr '\n' '\t' >> "${LOG}"
printf 'stage=colmap_mvs container_finished returncode=%s\n' "${rc}" >> "${LOG}"
exit 0
