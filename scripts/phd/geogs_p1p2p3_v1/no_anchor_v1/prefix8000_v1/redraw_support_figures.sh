#!/usr/bin/env bash
set -euo pipefail
REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../../.." && pwd)
TASK=$(realpath "$REPO/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1")
PREFIX="$TASK/evaluation/no_anchor_sfm_prefix8000_v1"
SOURCE="$PREFIX/support_transitions_v1"
OUT="$PREFIX/support_transitions_figures_v2"
test -s "$SOURCE/receipt.json"
test ! -e "$OUT"
mkdir "$OUT"
mkdir "$OUT/execution"
cp "$REPO/scripts/phd/geogs_p1p2p3_v1/no_anchor_v1/prefix8000_v1/redraw_support_figures.py" "$OUT/execution/"
cp "$REPO/scripts/phd/geogs_p1p2p3_v1/no_anchor_v1/prefix8000_v1/redraw_support_figures.sh" "$OUT/execution/"
COMMAND=(docker run --rm --network none --read-only --cpus 2 --memory 2g --pids-limit 128
  --user "$(id -u):$(id -g)" -e NVIDIA_VISIBLE_DEVICES=void -e PYTHONDONTWRITEBYTECODE=1
  -e OMP_NUM_THREADS=2 -e OPENBLAS_NUM_THREADS=2 -e MPLCONFIGDIR=/tmp/matplotlib
  --tmpfs /tmp:rw,size=128m -v "$TASK:/task:ro" -v "$SOURCE:/source:ro" -v "$OUT:/out:rw"
  --entrypoint python sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
  /out/execution/redraw_support_figures.py --source /source --out /out)
printf '%q ' "${COMMAND[@]}" > "$OUT/execution/command.sh"
printf '\n' >> "$OUT/execution/command.sh"
date -u +%Y-%m-%dT%H:%M:%SZ > "$OUT/execution/started_utc.txt"
set +e
"${COMMAND[@]}" > "$OUT/execution/stdout.log" 2> "$OUT/execution/stderr.log"
STATUS=$?
set -e
printf '%s\n' "$STATUS" > "$OUT/execution/exit_code.txt"
date -u +%Y-%m-%dT%H:%M:%SZ > "$OUT/execution/completed_utc.txt"
(cd "$OUT/execution" && sha256sum *.py *.sh *.txt *.log > SHA256SUMS)
cat "$OUT/execution/stdout.log"
cat "$OUT/execution/stderr.log" >&2
exit "$STATUS"
