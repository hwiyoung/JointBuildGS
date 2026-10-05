#!/usr/bin/env bash
# Host driver of PHD-STAGE2-PROPAGATION-PREMEASURE-v1 (no training; every step in Docker, receipts in logs/).
#   bash scripts/phd/stage2_propagation_premeasure_v1/run_all.sh [step ...]
# steps (default all, in order): surfaces render measure candidates tables figure
set -uo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
ART=$(realpath "$REPO/../JointBuildGS-artifacts")
OUT="$ART/phase-payloads/phd/stage2_conf_guided_gs_v1/PHD-STAGE2-PROPAGATION-PREMEASURE-v1"
DIAG="$ART/phase-payloads/phd/geogs_roof_bias_v1/GEOGS-ROOF-BIAS-20260921"
DEV=jointbuildgs:dev
GEOGS=jointbuildgs:geogs-official-db40c95-compat-v1        # Open3D 0.19 = the stage-1 face-id renders
WD=/repo/scripts/phd/stage2_propagation_premeasure_v1
FIG_DOC="$REPO/docs/experiments/phd/stage2_conf_guided_gs_v1/figures/propagation_premeasure_summary_v1.png"
mkdir -p "$OUT"/{logs,figures}

run_step() {  # run_step <name> <image> <cpus> [extra docker args...] -- <python args...>
  local name=$1 image=$2 cpus=$3; shift 3
  local extra=(); while [ "$1" != "--" ]; do extra+=("$1"); shift; done; shift
  local log="$OUT/logs/$name.log" start; start=$(date -Iseconds); local t0=$SECONDS
  echo "[$start] START $name" | tee -a "$OUT/logs/driver.log"
  docker run --rm --name "jbgs-premeasure-$name-$$" --network none --user "$(id -u):$(id -g)" --cpus "$cpus" \
    -e PYTHONUNBUFFERED=1 -e OMP_NUM_THREADS="$cpus" -e MPLCONFIGDIR=/tmp/mpl \
    -v "$ART:/artifacts/JointBuildGS:ro" -v "$REPO:/repo:ro" -v "$OUT:/out" "${extra[@]}" -w "$WD" --entrypoint python "$image" "$@" > "$log" 2>&1
  local rc=$?
  python3 - "$name" "$(docker image inspect --format '{{.Id}}' "$image")" "$image" "$start" "$(date -Iseconds)" "$rc" "$((SECONDS-t0))" "$log" "$@" <<'PY'
import json, sys
name, image_id, image, start, end, rc, sec, log = sys.argv[1:9]; cmd = sys.argv[9:]
json.dump({"step": name, "image": image, "image_id": image_id, "command": ["python"] + cmd, "started_at": start, "finished_at": end,
           "seconds": int(sec), "exit_code": int(rc), "status": "PASS" if rc == "0" else "FAILED", "log": log, "scientific_verdict": None},
          open(log[:-4] + ".host_receipt.json", "w"), indent=2)
PY
  echo "[$(date -Iseconds)] END $name rc=$rc ($((SECONDS-t0)) s)" | tee -a "$OUT/logs/driver.log"; return $rc
}

steps=("$@"); [ ${#steps[@]} -eq 0 ] && steps=(surfaces render measure candidates tables figure)
for st in "${steps[@]}"; do
  case $st in
    surfaces)   run_step surfaces "$DEV" 8 -- surfaces.py || exit 1 ;;
    render)     run_step render_ids "$GEOGS" 32 -v "$DIAG/sources/GeoGS:/source:ro" -- render_ids.py || exit 1 ;;
    measure)    pids=(); for S in M_N M_B L_N L_B; do run_step "measure_$S" "$DEV" 16 -- measure.py "$S" & pids+=($!); done
                rc=0; for p in "${pids[@]}"; do wait "$p" || rc=1; done; [ $rc -eq 0 ] || exit 1 ;;
    candidates) run_step candidates "$DEV" 16 -- candidates.py || exit 1 ;;
    tables)     run_step tables "$DEV" 8 -- tables.py || exit 1 ;;
    figure)     run_step figure "$DEV" 8 -v /usr/share/fonts/opentype/noto:/fonts:ro -- figure.py /out/figures/propagation_premeasure_summary_v1.png || exit 1
                cp "$OUT/figures/propagation_premeasure_summary_v1.png" "$FIG_DOC" ;;
    *) echo "unknown step $st"; exit 2 ;;
  esac
done
