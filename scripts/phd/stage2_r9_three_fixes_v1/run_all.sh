#!/usr/bin/env bash
# Host driver of PHD-STAGE2-R9-THREE-FIXES-v1 (every step in Docker, receipts in logs/).
#   bash scripts/phd/stage2_r9_three_fixes_v1/run_all.sh [step ...]
# steps (default all, in order):
#   unit meshes render tau products inputs fork gputests dry verify premeasure train r8rot mesh extra views cases tables figure
# (mesh also builds M_N and L_N with r8's virtual cameras: mesh/<run>_r8cams)
set -uo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
ART=$(realpath "$REPO/../JointBuildGS-artifacts")
P9="$ART/phase-payloads/phd/stage2_conf_guided_gs_v1/PHD-STAGE2-R9-THREE-FIXES-v1"
R8="$ART/phase-payloads/phd/stage2_conf_guided_gs_v1/PHD-STAGE2-R8-FOUR-CASES-v1"
R7="$ART/phase-payloads/phd/stage2_conf_guided_gs_v1/PHD-STAGE2-R7-PROPAGATION-v1"
S2="$ART/phase-payloads/phd/stage2_conf_guided_gs_v1/PHD-STAGE2-CONF-GUIDED-GS-v1"
DIAG="$ART/phase-payloads/phd/geogs_roof_bias_v1/GEOGS-ROOF-BIAS-20260921"
DEV=jointbuildgs:dev
COMPAT=jointbuildgs:geogs-official-db40c95-compat-v1   # Open3D 0.19 = LoD2Depth renders
TRAIN=jointbuildgs:geogs-conf-guided-v1                # the stage-2 training image
WD=/repo/scripts/phd/stage2_r9_three_fixes_v1
FIG_DOC="$REPO/docs/experiments/phd/stage2_conf_guided_gs_v1/figures/r9_three_fixes_summary_v1.png"
mkdir -p "$P9"/{logs,figures}

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
  local log="$P9/logs/$name.log" start; start=$(date -Iseconds); local t0=$SECONDS
  echo "[$start] START $name" | tee -a "$P9/logs/driver.log"
  docker run --rm --name "jbgs-r9-$name-$$" --network none --user "$(id -u):$(id -g)" --cpus "$cpus" --shm-size 8g \
    -e PYTHONUNBUFFERED=1 -e OMP_NUM_THREADS="$cpus" -e MPLCONFIGDIR=/tmp/mpl -e HOME=/tmp \
    -v "$ART:/artifacts/JointBuildGS:ro" -v "$REPO:/repo:ro" -v "$R7:/r7:ro" -v "$R8:/r8:ro" -v "$P9:/p9" -w "$WD" "${extra[@]}" "$image" "$@" > "$log" 2>&1
  local rc=$?
  receipt "$name" "$image" "$start" "$rc" "$((SECONDS-t0))" "$log" "$@"
  echo "[$(date -Iseconds)] END $name rc=$rc ($((SECONDS-t0)) s)" | tee -a "$P9/logs/driver.log"; return $rc
}
steps=("$@"); [ ${#steps[@]} -eq 0 ] && steps=(unit meshes render tau products inputs fork gputests dry verify premeasure train r8rot mesh extra views cases tables figure)
for st in "${steps[@]}"; do
  t_step=$SECONDS; echo "[$(date -Iseconds)] STEP START $st" >> "$P9/logs/driver.log"
  case $st in
    unit)       run_step unit "$DEV" 4 -w /repo --entrypoint python -- -m unittest tests.phd.test_prior_propagation_v2 tests.phd.test_prior_propagation_v3 || exit 1 ;;
    meshes)     run_step meshes "$DEV" 4 --entrypoint python -- meshes_r9.py || exit 1 ;;
    render)     run_step render "$COMPAT" 32 -v "$DIAG/sources/GeoGS:/source:ro" --entrypoint python -- render_r9.py || exit 1 ;;
    tau)        run_step stage1_tau "$DEV" 16 --entrypoint python -- stage1_products_r9.py tau || exit 1 ;;
    products)   pids=(); for S in M_N M_B L_N L_B; do
                  run_step "stage1_product_$S" "$DEV" 12 --entrypoint python -- stage1_products_r9.py product "$S" & pids+=($!); done
                rc=0; for p in "${pids[@]}"; do wait "$p" || rc=1; done; [ $rc -eq 0 ] || exit 1 ;;
    inputs)     pids=(); for S in M_N M_B L_N L_B; do
                  run_step "prepare_$S" "$DEV" 8 --entrypoint python -- prepare_r9_inputs.py "$S" & pids+=($!); done
                rc=0; for p in "${pids[@]}"; do wait "$p" || rc=1; done; [ $rc -eq 0 ] || exit 1 ;;
    fork)       if [ -d "$P9/sources/GeoGS-conf-guided-v1-r9" ]; then mkdir -p "$P9/sources_superseded"
                  mv "$P9/sources/GeoGS-conf-guided-v1-r9" "$P9/sources_superseded/GeoGS-conf-guided-v1-r9_$(date +%Y%m%dT%H%M%S)"; fi
                mkdir -p "$P9/sources"
                python3 "$REPO/scripts/phd/stage2_r9_three_fixes_v1/build_fork_r9.py" --parent "$R8/sources/GeoGS-conf-guided-v1-r8" \
                  --out "$P9/sources/GeoGS-conf-guided-v1-r9" --provenance "$P9/provenance" --repo "$REPO" \
                  --repo_commit "$(git -C "$REPO" rev-parse HEAD)" > "$P9/logs/build_fork_r9.log" 2>&1 || exit 1 ;;
    gputests)   docker run --rm --gpus device=0 --network none --user "$(id -u):$(id -g)" -e PYTHONUNBUFFERED=1 -e HOME=/tmp \
                  -v "$P9/sources/GeoGS-conf-guided-v1-r9:/source:ro" -v "$R8/sources/GeoGS-conf-guided-v1-r8:/r8src:ro" -v "$REPO:/repo:ro" \
                  -w /source --entrypoint python "$TRAIN" /repo/scripts/phd/stage2_r9_three_fixes_v1/gpu_tests_r9.py > "$P9/logs/gpu_tests_r9.log" 2>&1 || exit 1
                grep -q "GPU R9 TESTS PASSED" "$P9/logs/gpu_tests_r9.log" || exit 1 ;;
    dry)        python3 "$REPO/scripts/phd/stage2_r9_three_fixes_v1/run_r9.py" --gpu 0 --dry M_N L_N > "$P9/logs/dry_gpu0.log" 2>&1 & p0=$!
                python3 "$REPO/scripts/phd/stage2_r9_three_fixes_v1/run_r9.py" --gpu 1 --dry M_B L_B > "$P9/logs/dry_gpu1.log" 2>&1 & p1=$!
                wait $p0 || exit 1; wait $p1 || exit 1 ;;
    verify)     run_step verify_dry "$DEV" 8 --entrypoint python -- verify_dry_r9.py || exit 1 ;;
    premeasure) run_step premeasure_v4 "$DEV" 16 --entrypoint python -- premeasure_v4.py || exit 1 ;;
    train)      python3 "$REPO/scripts/phd/stage2_r9_three_fixes_v1/run_r9.py" --gpu 0 M_N M_N_noprior L_N > "$P9/logs/train_gpu0.log" 2>&1 & p0=$!
                python3 "$REPO/scripts/phd/stage2_r9_three_fixes_v1/run_r9.py" --gpu 1 ctrl_M_N_r8 M_B L_B > "$P9/logs/train_gpu1.log" 2>&1 & p1=$!
                wait $p0 || exit 1; wait $p1 || exit 1 ;;
    r8rot)      t0=$SECONDS; docker run --rm --gpus device=0 --network none --user "$(id -u):$(id -g)" -e PYTHONUNBUFFERED=1 -e HOME=/tmp \
                  -v "$R8/sources/GeoGS-conf-guided-v1-r8:/source:ro" -v "$R8:/r8:ro" -v "$P9:/p9" -v "$REPO:/repo:ro" -w /source \
                  --entrypoint python "$TRAIN" /repo/scripts/phd/stage2_r9_three_fixes_v1/r8_initial_rotations.py > "$P9/logs/r8_initial_rotations.log" 2>&1 || exit 1
                echo "[$(date -Iseconds)] END r8rot ($((SECONDS-t0)) s)" >> "$P9/logs/driver.log" ;;
    mesh)       python3 "$REPO/scripts/phd/stage2_r9_three_fixes_v1/run_mesh.py" --gpu 1 M_N M_N_noprior M_B L_N L_B > "$P9/logs/mesh_all.log" 2>&1 || exit 1   # one at a time (host memory)
                python3 "$REPO/scripts/phd/stage2_r9_three_fixes_v1/run_mesh.py" --gpu 1 --variant r8cams M_N L_N > "$P9/logs/mesh_r8cams.log" 2>&1 || exit 1 ;;
    extra)      python3 "$REPO/scripts/phd/stage2_r9_three_fixes_v1/run_r9.py" --gpu 0 r8rep_M_N M_N_noorient > "$P9/logs/extra_gpu0.log" 2>&1 & p0=$!
                python3 "$REPO/scripts/phd/stage2_r9_three_fixes_v1/run_r9.py" --gpu 1 r8rep_L_N L_N_noorient > "$P9/logs/extra_gpu1.log" 2>&1 & p1=$!
                wait $p0 || exit 1; wait $p1 || exit 1
                python3 "$REPO/scripts/phd/stage2_r9_three_fixes_v1/run_mesh.py" --gpu 1 r8rep_M_N M_N_noorient > "$P9/logs/mesh_extra.log" 2>&1 || exit 1 ;;
    views)      t0=$SECONDS; docker run --rm --name "jbgs-r9-views-$$" --gpus device=0 --network none --user "$(id -u):$(id -g)" -e PYTHONUNBUFFERED=1 -e HOME=/tmp \
                  -v "$ART:/artifacts/JointBuildGS:ro" -v "$S2:/s2:ro" -v "$R8:/r8:ro" -v "$P9:/p9" -v "$REPO:/repo:ro" \
                  -v "$P9/sources/GeoGS-conf-guided-v1-r9:/source:ro" -w /source --entrypoint python "$TRAIN" \
                  /repo/scripts/phd/stage2_r9_three_fixes_v1/views_r9.py M_N > "$P9/logs/views_r9.log" 2>&1 || exit 1
                echo "[$(date -Iseconds)] END views ($((SECONDS-t0)) s)" >> "$P9/logs/driver.log" ;;
    cases)      run_step cases_r9 "$DEV" 16 --entrypoint python -- cases_r9.py || exit 1
                run_step reset_layers_r9 "$DEV" 8 --entrypoint python -- reset_layers_r9.py || exit 1
                run_step cases_extra "$DEV" 16 -e R9_EXTRA=1 --entrypoint python -- cases_r9.py || exit 1 ;;
    tables)     run_step tables_r9 "$DEV" 2 --entrypoint python -- tables_r9.py || exit 1 ;;
    figure)     run_step figure_r9 "$DEV" 8 -v /usr/share/fonts/opentype/noto:/fonts:ro --entrypoint python -- figure_r9.py /p9/figures/r9_three_fixes_summary_v1.png || exit 1
                cp "$P9/figures/r9_three_fixes_summary_v1.png" "$FIG_DOC" ;;
    *) echo "unknown step $st"; exit 2 ;;
  esac
  echo "[$(date -Iseconds)] STEP END $st ($((SECONDS-t_step)) s)" >> "$P9/logs/driver.log"
done
