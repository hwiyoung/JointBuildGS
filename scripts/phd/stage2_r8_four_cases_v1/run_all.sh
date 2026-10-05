#!/usr/bin/env bash
# Host driver of PHD-STAGE2-R8-FOUR-CASES-v1 (every step in Docker, receipts in logs/).
#   bash scripts/phd/stage2_r8_four_cases_v1/run_all.sh [step ...]
# steps (default all, in order):
#   unit tau products inputs fork gputests dry verify premeasure train mesh cases tables figure
set -uo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
ART=$(realpath "$REPO/../JointBuildGS-artifacts")
P8="$ART/phase-payloads/phd/stage2_conf_guided_gs_v1/PHD-STAGE2-R8-FOUR-CASES-v1"
R7="$ART/phase-payloads/phd/stage2_conf_guided_gs_v1/PHD-STAGE2-R7-PROPAGATION-v1"
DEV=jointbuildgs:dev
TRAIN=jointbuildgs:geogs-conf-guided-v1                # the stage-2 training image
WD=/repo/scripts/phd/stage2_r8_four_cases_v1
FIG_DOC="$REPO/docs/experiments/phd/stage2_conf_guided_gs_v1/figures/r8_four_cases_summary_v1.png"
mkdir -p "$P8"/{logs,figures}

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
  local log="$P8/logs/$name.log" start; start=$(date -Iseconds); local t0=$SECONDS
  echo "[$start] START $name" | tee -a "$P8/logs/driver.log"
  docker run --rm --name "jbgs-r8-$name-$$" --network none --user "$(id -u):$(id -g)" --cpus "$cpus" --shm-size 8g \
    -e PYTHONUNBUFFERED=1 -e OMP_NUM_THREADS="$cpus" -e MPLCONFIGDIR=/tmp/mpl -e HOME=/tmp \
    -v "$ART:/artifacts/JointBuildGS:ro" -v "$REPO:/repo:ro" -v "$R7:/r7:ro" -v "$P8:/p8" -w "$WD" "${extra[@]}" "$image" "$@" > "$log" 2>&1
  local rc=$?
  receipt "$name" "$image" "$start" "$rc" "$((SECONDS-t0))" "$log" "$@"
  echo "[$(date -Iseconds)] END $name rc=$rc ($((SECONDS-t0)) s)" | tee -a "$P8/logs/driver.log"; return $rc
}
steps=("$@"); [ ${#steps[@]} -eq 0 ] && steps=(unit tau products inputs fork gputests dry verify premeasure train mesh cases tables figure)
for st in "${steps[@]}"; do
  t_step=$SECONDS; echo "[$(date -Iseconds)] STEP START $st" >> "$P8/logs/driver.log"
  case $st in
    unit)       run_step unit "$DEV" 4 -w /repo --entrypoint python -- -m unittest tests.phd.test_prior_propagation_v2 || exit 1 ;;
    tau)        run_step stage1_tau "$DEV" 16 --entrypoint python -- stage1_products_r8.py tau || exit 1 ;;
    products)   pids=(); for S in M_N M_B M_C L_N L_B; do
                  run_step "stage1_product_$S" "$DEV" 12 --entrypoint python -- stage1_products_r8.py product "$S" & pids+=($!); done
                rc=0; for p in "${pids[@]}"; do wait "$p" || rc=1; done; [ $rc -eq 0 ] || exit 1 ;;
    inputs)     pids=(); for S in M_N M_B L_N L_B; do
                  run_step "prepare_$S" "$DEV" 8 --entrypoint python -- prepare_r8_inputs.py "$S" & pids+=($!); done
                rc=0; for p in "${pids[@]}"; do wait "$p" || rc=1; done; [ $rc -eq 0 ] || exit 1 ;;
    fork)       if [ -d "$P8/sources/GeoGS-conf-guided-v1-r8" ]; then mkdir -p "$P8/sources_superseded"
                  mv "$P8/sources/GeoGS-conf-guided-v1-r8" "$P8/sources_superseded/GeoGS-conf-guided-v1-r8_$(date +%Y%m%dT%H%M%S)"; fi
                mkdir -p "$P8/sources"
                python3 "$REPO/scripts/phd/stage2_r8_four_cases_v1/build_fork_r8.py" --parent "$R7/sources/GeoGS-conf-guided-v1-r7" \
                  --out "$P8/sources/GeoGS-conf-guided-v1-r8" --provenance "$P8/provenance" --repo "$REPO" \
                  --repo_commit "$(git -C "$REPO" rev-parse HEAD)" > "$P8/logs/build_fork_r8.log" 2>&1 || exit 1 ;;
    gputests)   docker run --rm --gpus device=0 --network none --user "$(id -u):$(id -g)" -e PYTHONUNBUFFERED=1 -e HOME=/tmp \
                  -v "$P8/sources/GeoGS-conf-guided-v1-r8:/source:ro" -v "$R7/sources/GeoGS-conf-guided-v1-r7:/r7src:ro" -v "$REPO:/repo:ro" \
                  -w /source --entrypoint python "$TRAIN" /repo/scripts/phd/stage2_r8_four_cases_v1/gpu_tests_r8.py > "$P8/logs/gpu_tests_r8.log" 2>&1 || exit 1
                grep -q "GPU R8 TESTS PASSED" "$P8/logs/gpu_tests_r8.log" || exit 1 ;;
    dry)        python3 "$REPO/scripts/phd/stage2_r8_four_cases_v1/run_r8.py" --gpu 0 --dry M_N L_N > "$P8/logs/dry_gpu0.log" 2>&1 & p0=$!
                python3 "$REPO/scripts/phd/stage2_r8_four_cases_v1/run_r8.py" --gpu 1 --dry M_B L_B > "$P8/logs/dry_gpu1.log" 2>&1 & p1=$!
                wait $p0 || exit 1; wait $p1 || exit 1 ;;
    verify)     run_step verify_dry "$DEV" 8 --entrypoint python -- verify_dry_r8.py || exit 1 ;;
    premeasure) run_step premeasure_v3 "$DEV" 16 --entrypoint python -- premeasure_v3.py || exit 1 ;;
    train)      python3 "$REPO/scripts/phd/stage2_r8_four_cases_v1/run_r8.py" --gpu 0 M_N M_N_noprior L_N > "$P8/logs/train_gpu0.log" 2>&1 & p0=$!
                python3 "$REPO/scripts/phd/stage2_r8_four_cases_v1/run_r8.py" --gpu 1 M_B L_B > "$P8/logs/train_gpu1.log" 2>&1 & p1=$!
                wait $p0 || exit 1; wait $p1 || exit 1 ;;
    mesh)       python3 "$REPO/scripts/phd/stage2_r8_four_cases_v1/run_mesh.py" --gpu 1 M_N M_N_noprior M_B L_N L_B > "$P8/logs/mesh_all.log" 2>&1 || exit 1 ;;   # one at a time (host memory)
    cases)      run_step four_cases "$DEV" 16 --entrypoint python -- four_cases.py || exit 1 ;;
    tables)     run_step cases_tables "$DEV" 2 --entrypoint python -- cases_tables.py || exit 1 ;;
    figure)     run_step figure_r8 "$DEV" 8 -v /usr/share/fonts/opentype/noto:/fonts:ro --entrypoint python -- figure_r8.py /p8/figures/r8_four_cases_summary_v1.png || exit 1
                cp "$P8/figures/r8_four_cases_summary_v1.png" "$FIG_DOC" ;;
    *) echo "unknown step $st"; exit 2 ;;
  esac
  echo "[$(date -Iseconds)] STEP END $st ($((SECONDS-t_step)) s)" >> "$P8/logs/driver.log"
done
