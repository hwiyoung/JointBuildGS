#!/usr/bin/env bash
# PHD-MAIN-AXES71-v2 일 1 'MVS 표면', one variant of one site made tile by tile (when the one-piece TSDF does not fit the memory limit):
# mvs_surface.py prep_tiled (the one-piece path's inputs on CPU) -> scripts/phd/main_fill_v1/cdgs/tsdf_tiled.py plan / order / tile k /
# merge (read-only from the repository; the one-piece voxels in every tile core, its triangles and triangle order) -> mvs_surface.py
# receipt_tiled. Each step is one container of run_mvs_surface.sh (CPU only, network off, memory limit), one at a time, stopping at the
# first failure.
#   [TILES=auto:16] [MEM_TILE=32] [MEM_MERGE=32] [CHECK=1] bash run_mvs_tiled.sh <site> <a|b>
# CHECK=1: the validation run on a variant whose one-piece mesh exists -> mesh_mvs_<v>_tiledcheck.ply, tiled_<v>_tiledcheck.json, then
# tsdf_tiled.py compare against mesh_mvs_<v>.ply -> tiledcheck_<v>.json; no receipt entry.
# Work folder AX/mvs/<site>/tiled_<v>_work; result AX/mvs/<site>/mesh_mvs_<v>.ply, tiled_<v>.json and the receipt entry. scientific_verdict: null.
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd); R="$HERE/run_mvs_surface.sh"; T=../main_fill_v1/cdgs/tsdf_tiled.py
site=$1; v=$2; TILES=${TILES:-auto:16}; MEM_TILE=${MEM_TILE:-32}; MEM_MERGE=${MEM_MERGE:-32}
REPO=$(cd "$HERE/../../.." && pwd); ART=$(realpath "$REPO/../JointBuildGS-artifacts"); WDH="$ART/phase-payloads/phd/main_axes71_v2/PHD-MAIN-AXES71-v2/mvs"
SUF=""; [ "${CHECK:-0}" = 1 ] && SUF=_tiledcheck
wd=/w/$site/tiled_${v}${SUF}_work; tag=tl_${site%%_*}_$v$SUF
declare -A S
step() { local name=$1; shift; local t0=$SECONDS; "$@" || { echo "$tag $name failed rc=$?" >&2; exit 1; }; S[$name]=$((SECONDS - t0)); }
step prep  env MEM=12 bash "$R" ${tag}_prep prep_tiled "$site" "$v" "$wd"
step plan  env MEM=12 SCRIPT=$T bash "$R" ${tag}_plan plan "$wd" "$TILES"
step order env MEM=6 SCRIPT=$T bash "$R" ${tag}_order order "$wd"
n=$(python3 -c "import json,sys; print(len(json.load(open(sys.argv[1]))['tiles']))" "$WDH/$site/tiled_${v}${SUF}_work/plan/layout.json") || exit 1
for ((k = 0; k < n; k++)); do
  step tile$k env MEM=$MEM_TILE SCRIPT=$T bash "$R" ${tag}_tile$k tile "$wd" $k
done
step merge env MEM=$MEM_MERGE SCRIPT=$T bash "$R" ${tag}_merge merge "$wd" /w/$site/mesh_mvs_$v$SUF.ply /w/$site/tiled_$v$SUF.json
if [ -n "$SUF" ]; then
  step compare env MEM=24 SCRIPT=$T bash "$R" ${tag}_compare compare /w/$site/mesh_mvs_$v.ply /w/$site/mesh_mvs_$v$SUF.ply /w/$site/tiledcheck_$v.json
  echo "$(date '+%m-%d %H:%M:%S') $tag tiled check done: $n tiles" | tee -a "$WDH/logs/queue.log"; exit 0
fi
js="{$(for k in "${!S[@]}"; do printf '"%s": %s,' "$k" "${S[$k]}"; done | sed 's/,$//')}"
env MEM=12 bash "$R" ${tag}_receipt receipt_tiled "$site" "$v" "$wd" "$js" || exit 1
echo "$(date '+%m-%d %H:%M:%S') $tag tiled done: $n tiles" | tee -a "$WDH/logs/queue.log"
