#!/usr/bin/env bash
# Host driver of PHD-STAGE2-R10-TWO-FIXES-THREE-CHECKS-v1 (every step in Docker, receipts in logs/).
#   bash scripts/phd/stage2_r10_two_fixes_three_checks_v1/run_all.sh [step ...]
# steps (default all, in order):
#   unit meshes render tau products inputs fork gputests dry verify premeasure train probe statecheck mesh occluders layers cases tables figure
# r9 (PHD-STAGE2-R9-THREE-FIXES-v1) is mounted read-only; nothing of r8 / r9 is changed.
set -uo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
ART=$(realpath "$REPO/../JointBuildGS-artifacts")
P10="$ART/phase-payloads/phd/stage2_conf_guided_gs_v1/PHD-STAGE2-R10-TWO-FIXES-THREE-CHECKS-v1"
P9="$ART/phase-payloads/phd/stage2_conf_guided_gs_v1/PHD-STAGE2-R9-THREE-FIXES-v1"
R8="$ART/phase-payloads/phd/stage2_conf_guided_gs_v1/PHD-STAGE2-R8-FOUR-CASES-v1"
R7="$ART/phase-payloads/phd/stage2_conf_guided_gs_v1/PHD-STAGE2-R7-PROPAGATION-v1"
DIAG="$ART/phase-payloads/phd/geogs_roof_bias_v1/GEOGS-ROOF-BIAS-20260921"
DEV=jointbuildgs:dev
COMPAT=jointbuildgs:geogs-official-db40c95-compat-v1   # Open3D 0.19 = LoD2Depth renders
TRAIN=jointbuildgs:geogs-conf-guided-v1                # the stage-2 training image
WD=/repo/scripts/phd/stage2_r10_two_fixes_three_checks_v1
S=scripts/phd/stage2_r10_two_fixes_three_checks_v1
FIG_DOC="$REPO/docs/experiments/phd/stage2_conf_guided_gs_v1/figures/r10_two_fixes_three_checks_summary_v1.png"
mkdir -p "$P10"/{logs,figures}

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
  local log="$P10/logs/$name.log" start; start=$(date -Iseconds); local t0=$SECONDS
  echo "[$start] START $name" | tee -a "$P10/logs/driver.log"
  docker run --rm --name "jbgs-r10-$name-$$" --network none --user "$(id -u):$(id -g)" --cpus "$cpus" --shm-size 8g \
    -e PYTHONUNBUFFERED=1 -e OMP_NUM_THREADS="$cpus" -e MPLCONFIGDIR=/tmp/mpl -e HOME=/tmp \
    -v "$ART:/artifacts/JointBuildGS:ro" -v "$REPO:/repo:ro" -v "$R7:/r7:ro" -v "$R8:/r8:ro" -v "$P9:/p9:ro" -v "$P10:/p10" -w "$WD" "${extra[@]}" "$image" "$@" > "$log" 2>&1
  local rc=$?
  receipt "$name" "$image" "$start" "$rc" "$((SECONDS-t0))" "$log" "$@"
  echo "[$(date -Iseconds)] END $name rc=$rc ($((SECONDS-t0)) s)" | tee -a "$P10/logs/driver.log"; return $rc
}
steps=("$@"); [ ${#steps[@]} -eq 0 ] && steps=(unit meshes render tau products inputs fork gputests dry verify premeasure train probe statecheck mesh occluders layers cases tables figure)
for st in "${steps[@]}"; do
  t_step=$SECONDS; echo "[$(date -Iseconds)] STEP START $st" >> "$P10/logs/driver.log"
  case $st in
    unit)       run_step unit "$DEV" 4 -w /repo --entrypoint python -- -m unittest tests.phd.test_prior_propagation_v4 || exit 1 ;;
    meshes)     run_step meshes "$DEV" 4 --entrypoint python -- meshes_r10.py || exit 1 ;;
    render)     run_step render "$COMPAT" 32 -v "$DIAG/sources/GeoGS:/source:ro" --entrypoint python -- render_r10.py || exit 1 ;;
    tau)        run_step stage1_tau "$DEV" 16 --entrypoint python -- stage1_products_r10.py tau || exit 1 ;;
    products)   pids=(); for X in M_N M_B; do
                  run_step "stage1_product_$X" "$DEV" 12 --entrypoint python -- stage1_products_r10.py product "$X" & pids+=($!); done
                rc=0; for p in "${pids[@]}"; do wait "$p" || rc=1; done; [ $rc -eq 0 ] || exit 1 ;;
    inputs)     pids=(); for X in M_N M_B; do
                  run_step "prepare_$X" "$DEV" 8 --entrypoint python -- prepare_r10_inputs.py "$X" & pids+=($!); done
                rc=0; for p in "${pids[@]}"; do wait "$p" || rc=1; done; [ $rc -eq 0 ] || exit 1 ;;
    fork)       if [ -d "$P10/sources/GeoGS-conf-guided-v1-r10" ]; then mkdir -p "$P10/sources_superseded"
                  mv "$P10/sources/GeoGS-conf-guided-v1-r10" "$P10/sources_superseded/GeoGS-conf-guided-v1-r10_$(date +%Y%m%dT%H%M%S)"; fi
                mkdir -p "$P10/sources"
                python3 "$REPO/$S/build_fork_r10.py" --parent "$P9/sources/GeoGS-conf-guided-v1-r9" \
                  --out "$P10/sources/GeoGS-conf-guided-v1-r10" --provenance "$P10/provenance" --repo "$REPO" \
                  --repo_commit "$(git -C "$REPO" rev-parse HEAD)" > "$P10/logs/build_fork_r10.log" 2>&1 || exit 1 ;;
    gputests)   docker run --rm --gpus device=0 --network none --user "$(id -u):$(id -g)" -e PYTHONUNBUFFERED=1 -e HOME=/tmp \
                  -v "$P10/sources/GeoGS-conf-guided-v1-r10:/source:ro" -v "$P9/sources/GeoGS-conf-guided-v1-r9:/r9src:ro" \
                  -v "$R8/sources/GeoGS-conf-guided-v1-r8:/r8src:ro" -v "$REPO:/repo:ro" \
                  -w /source --entrypoint python "$TRAIN" "$WD/gpu_tests_r10.py" > "$P10/logs/gpu_tests_r10.log" 2>&1 || exit 1
                grep -q "GPU R10 TESTS PASSED" "$P10/logs/gpu_tests_r10.log" || exit 1 ;;
    dry)        python3 "$REPO/$S/run_r10.py" --gpu 0 --dry M_N L_N L_N_cell > "$P10/logs/dry_gpu0.log" 2>&1 & p0=$!
                python3 "$REPO/$S/run_r10.py" --gpu 1 --dry M_B L_B L_B_cell > "$P10/logs/dry_gpu1.log" 2>&1 & p1=$!
                wait $p0 || exit 1; wait $p1 || exit 1 ;;
    verify)     run_step verify_dry "$DEV" 8 --entrypoint python -- verify_dry_r10.py || exit 1 ;;
    premeasure) run_step premeasure_v5 "$DEV" 4 --entrypoint python -- premeasure_v5.py || exit 1 ;;
    train)      python3 "$REPO/$S/run_r10.py" --gpu 0 M_N M_N_nodepth L_N_vertex L_N_cell_rep L_B_cell > "$P10/logs/train_gpu0.log" 2>&1 & p0=$!
                python3 "$REPO/$S/run_r10.py" --gpu 1 M_N_rep M_B L_N_cell L_B_vertex > "$P10/logs/train_gpu1.log" 2>&1 & p1=$!
                wait $p0 || exit 1; wait $p1 || exit 1 ;;
    probe)      python3 "$REPO/$S/run_r10.py" --gpu 0 --probe M_N > "$P10/logs/probe_gpu0.log" 2>&1 & p0=$!
                python3 "$REPO/$S/run_r10.py" --gpu 1 --probe L_N_vertex > "$P10/logs/probe_gpu1.log" 2>&1 & p1=$!
                wait $p0 || exit 1; wait $p1 || exit 1 ;;
    statecheck) docker run --rm --network none --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$REPO:/repo:ro" -v "$P10:/p10" --entrypoint python "$TRAIN" \
                  "$WD/reset_states_check.py" M_N L_N_vertex > "$P10/logs/reset_states_check.log" 2>&1 || exit 1 ;;
    mesh)       python3 "$REPO/$S/run_mesh_r10.py" --gpu 1 M_N M_N_rep M_N_nodepth M_B L_N_vertex L_N_cell L_N_cell_rep L_B_vertex L_B_cell \
                  > "$P10/logs/mesh_all.log" 2>&1 || exit 1 ;;   # one at a time (host memory)
    occluders)  docker run --rm --gpus device=0 --network none --user "$(id -u):$(id -g)" --cpus 8 -e PYTHONUNBUFFERED=1 -e HOME=/tmp \
                  -v "$ART:/artifacts/JointBuildGS:ro" -v "$ART/phase-payloads/phd/stage2_conf_guided_gs_v1/PHD-STAGE2-CONF-GUIDED-GS-v1:/s2:ro" \
                  -v "$P9:/p9:ro" -v "$P10:/p10" -v "$REPO:/repo:ro" -v "$P10/sources/GeoGS-conf-guided-v1-r10:/source:ro" -w /source --entrypoint python "$TRAIN" \
                  "$WD/occluders_r10.py" M_N M_N_rep M_N_nodepth M_B L_N_vertex L_N_cell L_N_cell_rep L_B_vertex L_B_cell > "$P10/logs/occluders_all.log" 2>&1 || exit 1 ;;
    layers)     run_step reset_layers_r10 "$DEV" 8 --entrypoint python -- reset_layers_r10.py || exit 1 ;;
    cases)      run_step cases_r10 "$DEV" 16 --entrypoint python -- cases_r10.py || exit 1 ;;
    tables)     run_step tables_r10 "$DEV" 2 --entrypoint python -- tables_r10.py || exit 1 ;;
    figure)     run_step figure_r10 "$DEV" 8 -v /usr/share/fonts/opentype/noto:/fonts:ro --entrypoint python -- figure_r10.py /p10/figures/r10_two_fixes_three_checks_summary_v1.png || exit 1
                cp "$P10/figures/r10_two_fixes_three_checks_summary_v1.png" "$FIG_DOC" ;;
    *) echo "unknown step $st"; exit 2 ;;
  esac
  echo "[$(date -Iseconds)] STEP END $st ($((SECONDS-t_step)) s)" >> "$P10/logs/driver.log"
done
