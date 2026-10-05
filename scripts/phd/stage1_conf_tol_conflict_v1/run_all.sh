#!/usr/bin/env bash
# Host driver for PHD-STAGE1-CONF-TOL-CONFLICT-v1. Every scientific step runs in Docker.
# Usage: run_all.sh <step|all>   steps: geometry mvs render_M_biased render_M_nominal_recovered
#        render_L_nominal render_L_biased faceids analyze report viewer
set -uo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
ART=$(realpath "$REPO/../JointBuildGS-artifacts")
TASK="$ART/phase-payloads/phd/stage1_conf_tol_conflict_v1/PHD-STAGE1-CONF-TOL-CONFLICT-v1"
DIAG="$ART/phase-payloads/phd/geogs_roof_bias_v1/GEOGS-ROOF-BIAS-20260921"
EXAMPLE="$ART/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/native_example/scene"
DEV=jointbuildgs:dev
GEOGS=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
CPUS=${JBGS_CPUS:-24}
SCR=/repo/scripts/phd/stage1_conf_tol_conflict_v1
mkdir -p "$TASK"/{inputs,out,logs,provenance,scripts}
ART_C=/artifacts/JointBuildGS
DIAG_C=$ART_C/phase-payloads/phd/geogs_roof_bias_v1/GEOGS-ROOF-BIAS-20260921
EX_C=$ART_C/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/native_example/scene

common_args() {
  echo --rm --network none --user "$(id -u):$(id -g)" --cpus "$CPUS" --shm-size 8g \
    -e PYTHONUNBUFFERED=1 -e OMP_NUM_THREADS="$CPUS" -e OPENBLAS_NUM_THREADS="$CPUS" -e MPLCONFIGDIR=/tmp/mpl \
    -e JBGS_ARTIFACT_ROOT=$ART_C -e JBGS_TASK_ROOT=/task -e JBGS_REPO_ROOT=/repo \
    -v "$ART:$ART_C:ro" -v "$TASK:/task" -v "$REPO:/repo:ro"
}
run_step() {  # run_step <name> <image> <workdir> <extra docker args...> -- <command...>
  local name=$1 image=$2 wd=$3; shift 3
  local extra=(); while [ "$1" != "--" ]; do extra+=("$1"); shift; done; shift
  local log="$TASK/logs/$name.log" start end rc
  start=$(date -Iseconds); local t0=$SECONDS
  echo "[$(date -Iseconds)] START $name" | tee -a "$TASK/logs/driver.log"
  # shellcheck disable=SC2046
  docker run --name "jbgs-stage1-$name-$$" $(common_args) "${extra[@]}" -w "$wd" --entrypoint "" "$image" "$@" > "$log" 2>&1
  rc=$?; end=$(date -Iseconds)
  python3 - "$name" "$image" "$start" "$end" "$rc" "$((SECONDS-t0))" "$log" "$@" <<'PY'
import json,sys,subprocess
name,image,start,end,rc,sec,log=sys.argv[1:8]; cmd=sys.argv[8:]
iid=subprocess.run(['docker','image','inspect',image,'--format','{{.Id}}'],capture_output=True,text=True).stdout.strip()
commit=subprocess.run(['git','rev-parse','HEAD'],capture_output=True,text=True).stdout.strip()
json.dump({'step':name,'image':image,'image_id':iid,'command':cmd,'started_at':start,'finished_at':end,'seconds':int(sec),'exit_code':int(rc),'status':'PASS' if rc=='0' else 'FAILED','log':log,'operator_commit':commit,'scientific_verdict':None},open(log[:-4]+'.host_receipt.json','w'),indent=2)
PY
  echo "[$(date -Iseconds)] END $name rc=$rc ($((SECONDS-t0)) s)" | tee -a "$TASK/logs/driver.log"
  return $rc
}
render() {  # render <name> <mesh_obj_container_path>
  local name=$1 mesh=$2
  run_step "render_$name" "$GEOGS" /source -v "$DIAG/sources/GeoGS:/source:ro" -- \
    python /source/LoD2Depth/main.py --mesh_path "$mesh" \
    --reference_frame_path "$DIAG_C/provenance/reference_frame.json" \
    --reference_frame_path_building "$DIAG_C/provenance/reference_frame.json" \
    --colmap_dir "$DIAG_C/conditions/B+1.0/scene/sparse_txt" --building_name "$name" --generate_maps \
    --subset_images_dir "$EX_C/images" --output_path "/task/inputs/prior_render/$name/transformed.obj" \
    --output_building_path "/task/inputs/prior_render/$name/transformed_building.obj" \
    --depth_normal_dir "/task/inputs/prior_render/$name/lod2_prior"
}
step() {
  case $1 in
    geometry) run_step geometry "$DEV" $SCR -- python prepare_geometry.py ;;
    mvs) run_step mvs "$DEV" $SCR -- python resample_mvs.py ;;
    render_M_biased) render M_biased "$DIAG_C/conditions/B+1.0/scene/lod2_biased.obj" ;;
    render_M_nominal_recovered) render M_nominal_recovered /task/inputs/lod2_nominal_recovered.obj ;;
    render_L_nominal) render L_nominal /task/inputs/als_tin_nominal.obj ;;
    render_L_biased) render L_biased /task/inputs/als_tin_biased.obj ;;
    faceids) run_step faceids "$GEOGS" $SCR -v "$DIAG/sources/GeoGS:/source:ro" -- python render_faceids.py ;;
    analyze) run_step analyze "$DEV" $SCR -- python analyze.py ;;
    report) run_step report "$DEV" $SCR -- python make_report.py ;;
    viewer) run_step viewer "$DEV" $SCR -- python make_viewer.py ;;
    *) echo "unknown step $1"; return 2 ;;
  esac
}
cp -f "$REPO"/scripts/phd/stage1_conf_tol_conflict_v1/*.py "$REPO"/scripts/phd/stage1_conf_tol_conflict_v1/*.sh "$TASK/scripts/" 2>/dev/null
cp -f "$REPO/configs/phd/stage1_conf_tol_conflict_v1/experiment.json" "$TASK/provenance/experiment.json"
if [ "$1" = all ]; then
  step geometry && step mvs
  step render_M_biased & p1=$!; step render_M_nominal_recovered & p2=$!; step render_L_nominal & p3=$!; step render_L_biased & p4=$!
  wait $p1 $p2 $p3 $p4
  step faceids && step analyze && step report && step viewer
else
  step "$1"
fi
