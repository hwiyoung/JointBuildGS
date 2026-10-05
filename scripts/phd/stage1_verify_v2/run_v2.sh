#!/usr/bin/env bash
# Host driver for PHD-STAGE1-VERIFY-v2 (all scientific steps in Docker).
# steps: prepare | render_<L|M>_<nominal|biased_small|biased_main> | renders (all six, parallel) | faceid | verify
set -uo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
ART=$(realpath "$REPO/../JointBuildGS-artifacts")
V2="$ART/phase-payloads/phd/stage1_conf_tol_conflict_v1/PHD-STAGE1-VERIFY-v2"
DIAG="$ART/phase-payloads/phd/geogs_roof_bias_v1/GEOGS-ROOF-BIAS-20260921"
DEV=jointbuildgs:dev
GEOGS=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
CPUS=${JBGS_CPUS:-24}
ART_C=/artifacts/JointBuildGS
DIAG_C=$ART_C/phase-payloads/phd/geogs_roof_bias_v1/GEOGS-ROOF-BIAS-20260921
EX_C=$ART_C/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/native_example/scene
mkdir -p "$V2"/{inputs_v2,out_v2,logs}
run_step() {  # run_step <name> <image> <workdir> <entrypoint> [extra docker args...] -- <args...>
  local name=$1 image=$2 wd=$3 ep=$4; shift 4
  local extra=(); while [ "$1" != "--" ]; do extra+=("$1"); shift; done; shift
  local log="$V2/logs/$name.log" start; start=$(date -Iseconds); local t0=$SECONDS
  echo "[$start] START $name" | tee -a "$V2/logs/driver.log"
  docker run --rm --name "jbgs-v2-$name-$$" --network none --user "$(id -u):$(id -g)" --cpus "$CPUS" --shm-size 8g \
    -e PYTHONUNBUFFERED=1 -e OMP_NUM_THREADS="$CPUS" -e MPLCONFIGDIR=/tmp/mpl \
    -v "$ART:$ART_C:ro" -v "$V2:/v2" -v "$REPO:/repo:ro" "${extra[@]}" -w "$wd" --entrypoint "$ep" "$image" "$@" > "$log" 2>&1
  local rc=$?
  python3 - "$name" "$image" "$start" "$(date -Iseconds)" "$rc" "$((SECONDS-t0))" "$log" "$ep" "$@" <<'PY'
import json,sys
name,image,start,end,rc,sec,log=sys.argv[1:8]; cmd=sys.argv[8:]
json.dump({'step':name,'image':image,'command':cmd,'started_at':start,'finished_at':end,'seconds':int(sec),'exit_code':int(rc),'status':'PASS' if rc=='0' else 'FAILED','log':log,'scientific_verdict':None},open(log[:-4]+'.host_receipt.json','w'),indent=2)
PY
  echo "[$(date -Iseconds)] END $name rc=$rc ($((SECONDS-t0)) s)" | tee -a "$V2/logs/driver.log"; return $rc
}
render() {  # render <name> <obj basename>
  run_step "render_$1" "$GEOGS" /source python -v "$DIAG/sources/GeoGS:/source:ro" -- /source/LoD2Depth/main.py --mesh_path "/v2/inputs_v2/$2" \
    --reference_frame_path "$DIAG_C/provenance/reference_frame.json" --reference_frame_path_building "$DIAG_C/provenance/reference_frame.json" \
    --colmap_dir "$DIAG_C/conditions/B+1.0/scene/sparse_txt" --building_name "$1" --generate_maps --subset_images_dir "$EX_C/images" \
    --output_path "/v2/inputs_v2/prior_render/$1/transformed.obj" --output_building_path "/v2/inputs_v2/prior_render/$1/transformed_building.obj" \
    --depth_normal_dir "/v2/inputs_v2/prior_render/$1/lod2_prior"
}
case $1 in
  prepare) run_step prepare "$DEV" /repo/scripts/phd/stage1_verify_v2 python -- prepare_v2.py ;;
  renders) render L_nominal als_v2_nominal.obj & render L_biased_small als_v2_biased_small.obj & render L_biased_main als_v2_biased_main.obj &
           render M_nominal lod2_v2_nominal.obj & render M_biased_small lod2_v2_biased_small.obj & render M_biased_main lod2_v2_biased_main.obj & wait ;;
  faceid) run_step faceid "$GEOGS" /repo/scripts/phd/stage1_verify_v2 python -v "$DIAG/sources/GeoGS:/source:ro" -- faceid_v2.py ;;
  verify) run_step verify "$DEV" /repo/scripts/phd/stage1_verify_v2 python -v /usr/share/fonts/opentype/noto:/fonts:ro -- verify_v2.py ;;
  *) echo "unknown step $1"; exit 2 ;;
esac
