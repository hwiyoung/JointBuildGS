#!/usr/bin/env bash
# B2 — reproject TUM2TWIN bundle 32632->25832 + decimate + crop to AOI core, for per-footprint counts.
# Read-only of inputs; CPU; p0-tools (PDAL). Outputs small 25832 LAZ to results/.../b2/ (gitignored).
set -u
REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
TOOLS="jointbuildgs-p0-tools:t0"
OUT="$REPO/results/tum_transfer/mob/b2"; mkdir -p "$OUT"
BOUNDS='([690739,691261],[5335816,5336390])'   # AOI core (25832), covers all 46 footprints

prep(){  # $1=infile $2=outname $3=decimation_step
  cat > "$OUT/$2_pipeline.json" <<JSON
{ "pipeline":[
  "/ws/phases/p0-audit/data/raw/tum2twin/$1",
  {"type":"filters.reprojection","in_srs":"EPSG:32632","out_srs":"EPSG:25832"},
  {"type":"filters.decimation","step":$3},
  {"type":"filters.crop","bounds":"$BOUNDS"},
  {"type":"writers.las","filename":"/ws/results/tum_transfer/mob/b2/$2.laz","a_srs":"EPSG:25832","compression":"lazperf","minor_version":4,"dataformat_id":3}
]}
JSON
  docker run --rm --user "$(id -u):$(id -g)" -v "$REPO":/ws "$TOOLS" \
    pdal pipeline "/ws/results/tum_transfer/mob/b2/$2_pipeline.json" > "$OUT/$2.log" 2>&1
  local n; n=$(docker run --rm -v "$REPO":/ws "$TOOLS" pdal info --summary "/ws/results/tum_transfer/mob/b2/$2.laz" 2>/dev/null | grep -oE '"num_points"[: ]+[0-9]+' | grep -oE '[0-9]+')
  echo "[$2] rc(see log) step=$3 -> ${n:-FAIL} pts ($(tail -1 "$OUT/$2.log"))"
}

prep TUM_Downtown_Photogrammetry_20241217.laz pix4d 15 &
prep TUM_Downtown_ULS_20241217_nadir.laz uls_nadir 15 &
prep TUM_Downtown_ULS_20241217_manual.laz uls_manual 10 &
wait
echo "[b2-prep] all done $(date '+%T')"
