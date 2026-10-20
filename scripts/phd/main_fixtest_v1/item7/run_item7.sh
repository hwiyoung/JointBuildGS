#!/usr/bin/env bash
# PHD-MAIN-FIXTEST-v1 일 7 (곁일, 그림 unseen_1의 듬성듬성한 칸): thin runner of one CPU step in jointbuildgs:dev, network off.
#   [CPUS=8] [MEM=24] bash run_item7.sh <tag> <script.py> [args ...]
# Mounts: /ph = phase-payloads/phd (ro; the fill task's payload SL is read only), /repo (ro), /fonts (Noto CJK, ro);
# read-write only: /item7 = PH/main_fixtest_v1/PHD-MAIN-FIXTEST-v1/item7, /fig = docs/.../main_fixtest_v1/figures/item7,
# /tab = docs/.../main_fixtest_v1/tables. Log: /item7/logs/<tag>.log (an existing log is renamed first); queue.log line with seconds.
# scientific_verdict: null.
set -uo pipefail
REPO=$(cd "$(dirname "$0")/../../../.." && pwd); ART=$(realpath "$REPO/../JointBuildGS-artifacts"); PH="$ART/phase-payloads/phd"
OUT="$PH/main_fixtest_v1/PHD-MAIN-FIXTEST-v1/item7"
FIG="$REPO/docs/experiments/phd/main_fixtest_v1/figures/item7"; TAB="$REPO/docs/experiments/phd/main_fixtest_v1/tables"
tag=$1; shift; script=$1; shift
mkdir -p "$OUT/logs" "$FIG" "$TAB"
[ -f "$OUT/logs/$tag.log" ] && mv "$OUT/logs/$tag.log" "$OUT/logs/$tag.$(date +%H%M%S).log"
t0=$SECONDS
docker run --rm --name "jbgs-fx-item7-${tag,,}" --network none --user "$(id -u):$(id -g)" --cpus "${CPUS:-8}" --memory "${MEM:-24}g" \
  -e PYTHONUNBUFFERED=1 -e PYTHONDONTWRITEBYTECODE=1 -e HOME=/tmp -e MPLCONFIGDIR=/tmp/mpl -e OMP_NUM_THREADS="${CPUS:-8}" -e TZ=Asia/Seoul \
  -v "$PH:/ph:ro" -v "$OUT:/item7" -v "$REPO:/repo:ro" -v "$FIG:/fig" -v "$TAB:/tab" -v /usr/share/fonts/opentype/noto:/fonts:ro \
  -w /repo/scripts/phd/main_fixtest_v1/item7 --entrypoint python jointbuildgs:dev "$script" "$@" > "$OUT/logs/$tag.log" 2>&1
rc=$?; echo "$(date +%H:%M:%S) $tag rc=$rc $((SECONDS-t0))s" | tee -a "$OUT/logs/queue.log"
exit $rc
