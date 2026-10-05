#!/usr/bin/env bash
# PHD-MAIN-PREP-MEASURE-v1: one case box after the user decision of 23:02 (host driver).
#   bash box_pipeline.sh <box_rid> <gpu> <search_stage1_dir> [skip_mvs]
# 1. MVS from the box's training images only (pinned COLMAP, GPU <gpu>) unless skip_mvs
# 2. stage 1 per prior on that MVS with tolerance and registration fixed from <search_stage1_dir> (e.g. step03/B0)
# 3. GT (labels with the fixed tolerance, height alignment on the box MVS), 4. cases, 5. maps.
set -uo pipefail
RID=$1; GPU=$2; FIX=$3; SKIP=${4:-}
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
ART=$(realpath "$REPO/../JointBuildGS-artifacts")
P="$ART/phase-payloads/phd/main_prep_measure_v1/PHD-MAIN-PREP-MEASURE-v1"
S="$REPO/scripts/phd/main_prep_measure_v1"
dr() { docker run --rm --network none --user "$(id -u):$(id -g)" --cpus 10 --memory 12g -e MPLCONFIGDIR=/tmp/mpl -e OMP_NUM_THREADS=10 \
        -v "$ART:/art:ro" -v "$P:/out" -v "$REPO:/repo:ro" -v /usr/share/fonts/opentype/noto:/fonts:ro -w /repo/scripts/phd/main_prep_measure_v1 \
        --entrypoint python jointbuildgs:dev "$@"; }
log() { echo "$(date +%H:%M:%S) box $RID $*" | tee -a "$P/logs/queue.log"; }
t0=$SECONDS
# one run per box: a second invocation (e.g. a queued chain after the box was started on a free GPU) skips
if ! mkdir "$P/mvs/box_${RID}.lock" 2>/dev/null; then log "already started elsewhere (lock) - skip"; exit 0; fi
if [ -z "$SKIP" ]; then
  python3 -c "import json; v=json.load(open('$P/step06/box_views.json'))['views']['$RID']; json.dump(v['train'], open('$P/mvs_lists/box_$RID.json','w'))"
  dr colmap_subset.py "box_$RID" "mvs_lists/box_$RID.json" > "$P/logs/box_${RID}_subset.log" 2>&1
  bash "$S/run_colmap.sh" "box_$RID" "$GPU" > "$P/logs/box_${RID}_colmap.log" 2>&1; log "colmap rc=$? $((SECONDS-t0))s"
fi
for PR in LoD2 ALS; do
  t1=$SECONDS
  dr step03_stage1.py "$RID" "$PR" --views-file step06/box_views.json --mesh-sub step06/mesh --out-sub step06/box_stage1 --mvs "mvs/box_$RID" \
     --fix-from "$FIX" --fig-views 4 > "$P/logs/box_${RID}_stage1_$PR.log" 2>&1; log "stage1 $PR rc=$? $((SECONDS-t1))s"
done
t1=$SECONDS
dr step04_gt.py "$RID" --mesh-sub step06/mesh --stage1-sub step06/box_stage1 --out-sub step06/box_gt --views-file step06/box_views.json \
   --mvs "mvs/box_$RID" > "$P/logs/box_${RID}_gt.log" 2>&1; log "gt rc=$? $((SECONDS-t1))s"
t1=$SECONDS
dr step05_cases.py "$RID" --stage1-sub step06/box_stage1 --gt-sub step06/box_gt --mesh-sub step06/mesh --out-sub step06/box_cases \
   --mvs "mvs/box_$RID" > "$P/logs/box_${RID}_cases.log" 2>&1; log "cases rc=$? $((SECONDS-t1))s"
dr step09_maps.py "$RID" --stage1-sub step06/box_stage1 --gt-sub step06/box_gt --mesh-sub step06/mesh --out-sub step06/box_maps \
   > "$P/logs/box_${RID}_maps.log" 2>&1; log "maps rc=$? total $((SECONDS-t0))s"
