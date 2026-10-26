#!/usr/bin/env bash
# PHD-MAIN-LOSSTRAIN-v1: bounded CPU checks; historical inputs are read-only.
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
ART=$(realpath "$REPO/../JointBuildGS-artifacts")
PH="$ART/phase-payloads/phd"
OUT="$PH/main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1"
mkdir -p "$OUT/logs" "$REPO/configs/phd/main_losstrain_v1" "$REPO/docs/experiments/phd/main_losstrain_v1"
tag=$1; shift
log="$OUT/logs/${tag}_$(date +%Y%m%dT%H%M%S).log"
case "${1##*/}" in
  mesh_score.py|sections.py|fates.py|split_fate_cells.py|baseline_fates.py|saved_opacity.py)
    # Large mesh/point arrays share host RAM with TSDF. Serialize these readouts.
    queue_started=$SECONDS
    exec 9>"$OUT/checks/tsdf.lock"
    flock -x 9
    printf '%s\n' "$((SECONDS - queue_started))" > "${log%.log}.queue_seconds.txt"
    ;;
esac
set +e
docker run --rm --name "jbgs-lt-${tag,,}" --network none --user "$(id -u):$(id -g)" \
  --cpus 8 --memory 24g --shm-size 2g \
  -e PYTHONUNBUFFERED=1 -e PYTHONDONTWRITEBYTECODE=1 -e HOME=/tmp -e MPLCONFIGDIR=/tmp/mpl \
  -e OMP_NUM_THREADS=8 -e TZ=Asia/Seoul \
  -v "$PH:/ph:ro" -v "$OUT:/out" -v "$REPO:/repo:ro" \
  -v "$REPO/configs/phd/main_losstrain_v1:/config" \
  -v "$REPO/docs/experiments/phd/main_losstrain_v1:/docs" \
  -v /usr/share/fonts/opentype/noto:/fonts:ro \
  -v /home/innopam/.codex/attachments/67413ea0-c89a-42c4-bed6-4c9006b802e5:/attachments:ro \
  -w /repo/scripts/phd/main_losstrain_v1 --entrypoint python jointbuildgs:dev "$@" > "$log" 2>&1
rc=$?
cat "$log"
exit "$rc"
