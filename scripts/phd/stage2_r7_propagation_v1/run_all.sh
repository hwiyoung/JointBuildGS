#!/usr/bin/env bash
# Host driver of PHD-STAGE2-R7-PROPAGATION-v1 (no training; every step in Docker, receipts in logs/).
#   bash scripts/phd/stage2_r7_propagation_v1/run_all.sh [step ...]
# steps (default all, in order): unit meshes render tau products inputs fork gputests dry verify premeasure figure
set -uo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
ART=$(realpath "$REPO/../JointBuildGS-artifacts")
P7="$ART/phase-payloads/phd/stage2_conf_guided_gs_v1/PHD-STAGE2-R7-PROPAGATION-v1"
PM1="$ART/phase-payloads/phd/stage2_conf_guided_gs_v1/PHD-STAGE2-PROPAGATION-PREMEASURE-v1"
R6F="$ART/phase-payloads/phd/stage2_conf_guided_gs_v1/PHD-STAGE2-R6-FIX-v1/sources/GeoGS-conf-guided-v1-r6"
DIAG="$ART/phase-payloads/phd/geogs_roof_bias_v1/GEOGS-ROOF-BIAS-20260921"
DEV=jointbuildgs:dev
COMPAT=jointbuildgs:geogs-official-db40c95-compat-v1   # Open3D 0.19 = LoD2Depth renders
TRAIN=jointbuildgs:geogs-conf-guided-v1                # the stage-2 training image
WD=/repo/scripts/phd/stage2_r7_propagation_v1
FIG_DOC="$REPO/docs/experiments/phd/stage2_conf_guided_gs_v1/figures/r7_propagation_summary_v1.png"
mkdir -p "$P7"/{logs,figures}

receipt() {  # receipt <name> <image> <start> <rc> <seconds> <log> <command...>
  python3 - "$@" <<'PY'
import json, subprocess, sys
name, image, start, rc, sec, log = sys.argv[1:7]; cmd = sys.argv[7:]
iid = subprocess.run(["docker", "image", "inspect", "--format", "{{.Id}}", image], capture_output=True, text=True).stdout.strip() if image != "host" else "host"
json.dump({"step": name, "image": image, "image_id": iid, "command": cmd, "started_at": start, "seconds": int(sec), "exit_code": int(rc),
           "status": "PASS" if rc == "0" else "FAILED", "log": log, "scientific_verdict": None}, open(log[:-4] + ".host_receipt.json", "w"), indent=2)
PY
}
run_step() {  # run_step <name> <image> <cpus> [extra docker args...] -- <command...>
  local name=$1 image=$2 cpus=$3; shift 3
  local extra=(); while [ "$1" != "--" ]; do extra+=("$1"); shift; done; shift
  local log="$P7/logs/$name.log" start; start=$(date -Iseconds); local t0=$SECONDS
  echo "[$start] START $name" | tee -a "$P7/logs/driver.log"
  docker run --rm --name "jbgs-r7-$name-$$" --network none --user "$(id -u):$(id -g)" --cpus "$cpus" --shm-size 8g \
    -e PYTHONUNBUFFERED=1 -e OMP_NUM_THREADS="$cpus" -e MPLCONFIGDIR=/tmp/mpl -e HOME=/tmp \
    -v "$ART:/artifacts/JointBuildGS:ro" -v "$REPO:/repo:ro" -v "$P7:/p7" -w "$WD" "${extra[@]}" "$image" "$@" > "$log" 2>&1
  local rc=$?
  receipt "$name" "$image" "$start" "$rc" "$((SECONDS-t0))" "$log" "$@"
  echo "[$(date -Iseconds)] END $name rc=$rc ($((SECONDS-t0)) s)" | tee -a "$P7/logs/driver.log"; return $rc
}
steps=("$@"); [ ${#steps[@]} -eq 0 ] && steps=(unit meshes render tau products inputs fork gputests dry verify premeasure figure)
for st in "${steps[@]}"; do
  case $st in
    unit)       run_step unit "$DEV" 4 -w /repo --entrypoint python -- -m unittest tests.phd.test_prior_propagation_v1 || exit 1 ;;
    meshes)     run_step meshes "$DEV" 8 --entrypoint python -- meshes.py || exit 1 ;;
    render)     run_step render "$COMPAT" 32 -v "$DIAG/sources/GeoGS:/source:ro" --entrypoint python -- render.py || exit 1 ;;
    tau)        run_step stage1_tau "$DEV" 16 --entrypoint python -- stage1_products.py tau || exit 1 ;;
    products)   pids=(); for S in M_N M_B M_C L_N L_B; do
                  run_step "stage1_product_$S" "$DEV" 16 --entrypoint python -- stage1_products.py product "$S" & pids+=($!); done
                rc=0; for p in "${pids[@]}"; do wait "$p" || rc=1; done; [ $rc -eq 0 ] || exit 1 ;;
    inputs)     pids=(); for S in M_N M_B L_N L_B; do
                  run_step "prepare_$S" "$DEV" 8 --entrypoint python -- prepare_r7_inputs.py "$S" & pids+=($!); done
                rc=0; for p in "${pids[@]}"; do wait "$p" || rc=1; done; [ $rc -eq 0 ] || exit 1 ;;
    fork)       if [ -d "$P7/sources/GeoGS-conf-guided-v1-r7" ]; then mkdir -p "$P7/sources_superseded"
                  mv "$P7/sources/GeoGS-conf-guided-v1-r7" "$P7/sources_superseded/GeoGS-conf-guided-v1-r7_$(date +%Y%m%dT%H%M%S)"; fi
                mkdir -p "$P7/sources"
                python3 "$REPO/scripts/phd/stage2_r7_propagation_v1/build_fork_r7.py" --parent "$R6F" --out "$P7/sources/GeoGS-conf-guided-v1-r7" \
                  --provenance "$P7/provenance" --repo "$REPO" --repo_commit "$(git -C "$REPO" rev-parse HEAD)" > "$P7/logs/build_fork_r7.log" 2>&1 || exit 1 ;;
    gputests)   docker run --rm --gpus device=0 --network none --user "$(id -u):$(id -g)" -e PYTHONUNBUFFERED=1 -e HOME=/tmp \
                  -v "$P7/sources/GeoGS-conf-guided-v1-r7:/source:ro" -v "$R6F:/r6:ro" -v "$REPO:/repo:ro" -w /source --entrypoint python "$TRAIN" \
                  /repo/scripts/phd/stage2_r7_propagation_v1/gpu_tests_r7.py > "$P7/logs/gpu_tests_r7.log" 2>&1 || exit 1
                grep -q "GPU R7 TESTS PASSED" "$P7/logs/gpu_tests_r7.log" || exit 1 ;;
    dry)        python3 "$REPO/scripts/phd/stage2_r7_propagation_v1/run_r7.py" --gpu 0 M_N:spec M_N:spec_plant M_N:spec_loc M_N:data L_N:spec L_N:spec_plant L_N:data > "$P7/logs/dry_gpu0.log" 2>&1 &
                p0=$!
                python3 "$REPO/scripts/phd/stage2_r7_propagation_v1/run_r7.py" --gpu 1 M_B:spec M_B:spec_plant M_B:data L_B:spec L_B:spec_plant L_B:data > "$P7/logs/dry_gpu1.log" 2>&1 &
                p1=$!; wait $p0 || exit 1; wait $p1 || exit 1 ;;
    verify)     run_step verify_dry "$DEV" 8 --entrypoint python -- verify_dry.py || exit 1 ;;
    premeasure) run_step premeasure_v2 "$DEV" 16 -v "$PM1:/pm1:ro" --entrypoint python -- premeasure_v2.py || exit 1 ;;
    figure)     run_step figure_r7 "$DEV" 8 -v /usr/share/fonts/opentype/noto:/fonts:ro --entrypoint python -- figure_r7.py /p7/figures/r7_propagation_summary_v1.png || exit 1
                cp "$P7/figures/r7_propagation_summary_v1.png" "$FIG_DOC" ;;
    *) echo "unknown step $st"; exit 2 ;;
  esac
done
