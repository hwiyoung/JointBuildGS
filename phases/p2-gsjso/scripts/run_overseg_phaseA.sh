#!/usr/bin/env bash
# P2 overseg-lever Phase A — Step 0 (reproducibility + ceil-density test) + smoothing-lever Roofer runs.
# Reuses the canonical mob Roofer call: 3dgi/roofer v1.0.0, --id-attribute building_id, per-building box,
# footprints_scene_aoi.gpkg, DEFAULTS (ceil-point-density 20). NO retrain. Observation only. EPSG:25832.
set -uo pipefail
REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
ROOFER="3dgi/roofer@sha256:dd2c415aaee337502bde0dc1426dfa9c9f88e648f9d2f6340110c49932c251d2"
TOOLS="jointbuildgs-p0-tools:t0"
GPKG="phases/p0-audit/data/work/w2/footprints_scene_aoi.gpkg"
EVAL="phases/p0-audit/runs/mob_eval/gs_d4_dense"
BASE="$REPO/results/tum_transfer/mob/overseg_lever"
U="$(id -u):$(id -g)"
mkdir -p "$BASE/smoothed"

# building boxes (baselines.json bbox_utm)
declare -A BOX=(
 [42364659]="691087.35 5336287.94 691096.70 5336301.27"
 [42364663]="690916.96 5336090.73 690928.80 5336117.97"
 [4907510]="690833.80 5335893.30 690847.43 5335910.84"
 [4906972]="690933.23 5335923.58 690964.54 5335948.06"
 [4908023]="690906.29 5336108.24 690911.89 5336115.25"
 [4906969]="690916.69 5336008.57 690935.67 5336025.35"
)
BLD=(42364659 42364663 4907510 4906972 4908023 4906969)

roofer() { # $1=in_las(repo-rel) $2=outdir(repo-rel) $3="box" $4=extra(optional)
  local extra="${4:-}"
  rm -rf "$REPO/$2"; mkdir -p "$REPO/$2"
  # shellcheck disable=SC2086
  docker run --rm --user "$U" -v "$REPO":/workspace/JointBuildGS -w /workspace/JointBuildGS "$ROOFER" \
    --id-attribute building_id --srs EPSG:25832 --box $3 $extra \
    "/workspace/JointBuildGS/$1" "/workspace/JointBuildGS/$GPKG" "/workspace/JointBuildGS/$2" \
    > "$REPO/$2/roofer.log" 2>&1 || { echo "  [roofer FAIL] $2"; tail -4 "$REPO/$2/roofer.log"; }
}
smooth() { # $1=in $2=out $3=cell $4=win $5=npass(optional)
  docker run --rm --user "$U" -v "$REPO":/workspace/JointBuildGS -w /workspace/JointBuildGS "$TOOLS" \
    python3 phases/p2-gsjso/scripts/overseg_smooth.py --in "/workspace/JointBuildGS/$1" --out "/workspace/JointBuildGS/$2" --cell "$3" --win "$4" --npass "${5:-1}"
}

echo "########## STEP 0.3  reproducibility: orig GS x3 (4906969, 4906972) ##########"
for bid in 4906969 4906972; do
  las="$EVAL/DEBY_LOD2_${bid}_orig_classified.las"
  for r in 1 2 3; do roofer "$las" "results/tum_transfer/mob/overseg_lever/repro/${bid}_r${r}" "${BOX[$bid]}"; done
done

echo "########## STEP 0  ceil-point-density enforcement test (4906969: default 20 vs 200 vs 5) ##########"
las="$EVAL/DEBY_LOD2_4906969_orig_classified.las"
roofer "$las" "results/tum_transfer/mob/overseg_lever/ceil/4906969_d20"  "${BOX[4906969]}" ""
roofer "$las" "results/tum_transfer/mob/overseg_lever/ceil/4906969_d200" "${BOX[4906969]}" "--ceil-point-density 200"
roofer "$las" "results/tum_transfer/mob/overseg_lever/ceil/4906969_d5"   "${BOX[4906969]}" "--ceil-point-density 5"

echo "########## STEP 0  baseline re-run (orig GS, my harness) for all 6 ##########"
for bid in "${BLD[@]}"; do
  roofer "$EVAL/DEBY_LOD2_${bid}_orig_classified.las" "results/tum_transfer/mob/overseg_lever/base/${bid}" "${BOX[$bid]}"
done

echo "########## TASK 2  SMOOTHING lever (MLS-on-grid roof-top, overlapping windows): light/med/strong ##########"
# strength label -> "cell win npass" (support = (2*win+1)*cell m); strong = fairness probe (~7m support, 2 passes)
declare -A SM=( [light]="0.4 1 1" [med]="0.5 2 1" [strong]="1.0 3 2" )
for bid in "${BLD[@]}"; do
  src="$EVAL/DEBY_LOD2_${bid}_orig_classified.las"
  for s in light med strong; do
    read -r cell win npass <<< "${SM[$s]}"
    out="results/tum_transfer/mob/overseg_lever/smoothed/${bid}_${s}.las"
    smooth "$src" "$out" "$cell" "$win" "$npass"
    roofer "$out" "results/tum_transfer/mob/overseg_lever/smooth_${s}/${bid}" "${BOX[$bid]}"
  done
done
echo "[done] outputs under $BASE/"
