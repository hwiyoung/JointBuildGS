#!/usr/bin/env bash
set -euo pipefail
REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../../.." && pwd)
TASK="$REPO/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1"
TASK=$(realpath "$TASK")
PREFIX="$TASK/evaluation/no_anchor_sfm_prefix8000_v1"
OUT="$PREFIX/support_transitions_v1"
IMAGE=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
for REGION in P1 P2 P3; do
  test -s "$PREFIX/summary/$REGION/R8000/receipt.json" || {
    echo "Wait for the completed regional summary: $REGION" >&2
    exit 2
  }
done
test ! -e "$OUT" || { echo "Refusing to overwrite $OUT" >&2; exit 2; }
mkdir "$OUT"
mkdir "$OUT/execution" "$OUT/execution/code"
cp "$REPO/scripts/phd/geogs_p1p2p3_v1/no_anchor_v1/prefix8000_v1/compare_support.py" "$OUT/execution/code/"
cp "$REPO/scripts/phd/geogs_p1p2p3_v1/no_anchor_v1/prefix8000_v1/compare_support.sh" "$OUT/execution/code/"
cp "$REPO/scripts/phd/geogs_p1p2p3_v1/no_anchor_v1/compare_reference_support.py" "$OUT/execution/code/"
cp "$REPO/configs/phd/geogs_p1p2p3_v1/prefix8000_support_transitions_v1.json" "$OUT/execution/code/"
COMMAND=(docker run --rm --network none --read-only --cpus 2 --memory 2g --pids-limit 128
  --user "$(id -u):$(id -g)" -e NVIDIA_VISIBLE_DEVICES=void -e MPLCONFIGDIR=/tmp/matplotlib
  -e PYTHONDONTWRITEBYTECODE=1 -e OMP_NUM_THREADS=2 -e OPENBLAS_NUM_THREADS=2
  --tmpfs /tmp:rw,size=128m -v "$TASK:/task:ro" -v "$OUT:/out:rw"
  --entrypoint python "$IMAGE" /out/execution/code/compare_support.py
  --task /task --out /out --config /out/execution/code/prefix8000_support_transitions_v1.json
  --helper /out/execution/code/compare_reference_support.py)
printf '%q ' "${COMMAND[@]}" > "$OUT/execution/command.sh"
printf '\n' >> "$OUT/execution/command.sh"
date -u +%Y-%m-%dT%H:%M:%SZ > "$OUT/execution/started_utc.txt"
set +e
"${COMMAND[@]}" > "$OUT/execution/stdout.log" 2> "$OUT/execution/stderr.log"
STATUS=$?
set -e
printf '%s\n' "$STATUS" > "$OUT/execution/exit_code.txt"
date -u +%Y-%m-%dT%H:%M:%SZ > "$OUT/execution/completed_utc.txt"
(cd "$OUT/execution" && sha256sum code/* command.sh started_utc.txt completed_utc.txt stdout.log stderr.log exit_code.txt > SHA256SUMS)
cat "$OUT/execution/stdout.log"
cat "$OUT/execution/stderr.log" >&2
exit "$STATUS"
