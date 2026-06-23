#!/usr/bin/env bash
# P2 make-or-break v6 — RAW baseline arm (NO GS training): sparse/dense/ACMP/LiDAR raw clouds
# -> P_utm npz (ellipsoidal) -> SAME tum_mob_eval harness as the GS arm (classify->Roofer->
# val3dity->facet count + plane_rms roughness). RMS-to-reference is a separate Phase-4 step.
# Idempotent (skips existing npz). CPU only -> safe to run while the GS arm trains on the GPU.
# Launch: setsid nohup bash phases/p2-gsjso/scripts/run_mob_v6_raw.sh > results/tum_transfer/mob/v6_raw.log 2>&1 &
# Observation only. EPSG:25832. Docker-based.
set -u
cd "$(dirname "$0")/../../.." || exit 1
REPO="$(pwd)"
OUT=results/tum_transfer/mob
RAW="$OUT/raw"; mkdir -p "$RAW"
TOOLS="jointbuildgs-p0-tools:t0"
echo "[$(date '+%F %T')] ===== MOB v6 RAW arm start ====="

# 1) convert each raw cloud -> ellipsoidal P_utm npz (p0-tools: laspy + numpy)
for c in sparse dense acmp lidar; do
  if [ -f "$RAW/raw_$c.npz" ]; then echo "[$(date '+%F %T')] SKIP convert $c"; continue; fi
  echo "[$(date '+%F %T')] CONVERT $c"
  docker run --rm --user "$(id -u):$(id -g)" -v "$REPO":/workspace/JointBuildGS -w /workspace/JointBuildGS "$TOOLS" \
    python3 phases/p2-gsjso/scripts/tum_mob_raw_to_npz.py --cloud "$c" \
      --out "/workspace/JointBuildGS/$RAW/raw_$c.npz" --voxel 0.10 > "$OUT/raw_convert_$c.log" 2>&1
  echo "[$(date '+%F %T')] CONVERT $c rc=$? -> $(tail -1 "$OUT/raw_convert_$c.log")"
done

# versions
COMMIT=$(git rev-parse HEAD 2>/dev/null || echo UNKNOWN)
{
  echo "run=raw_arm  stamped=$(date '+%F %T')  git_commit=$COMMIT"
  echo "datum: ellipsoidal UTM (GS-LOCAL+[690953,5336071,604]); acmp/lidar +48 geoid (ortho->ellip)"
  for c in sparse dense acmp lidar; do echo "  raw_$c: $(tail -1 "$OUT/raw_convert_$c.log" 2>/dev/null)"; done
  echo "harness=tum_mob_eval.py (same as GS arm)  roofer=3dgi/roofer@sha256:dd2c415a... tools=$TOOLS"
} > "$RAW/versions.txt"

# 2) EVAL the 4 raw arms through the SAME harness (orig + ALS-density-matched)
echo "[$(date '+%F %T')] EVAL raw 4-way"
python3 phases/p2-gsjso/scripts/tum_mob_eval.py \
  --configs raw_sparse="$RAW/raw_sparse.npz" raw_dense="$RAW/raw_dense.npz" \
            raw_acmp="$RAW/raw_acmp.npz" raw_lidar="$RAW/raw_lidar.npz" \
  --out "$OUT/eval_v6_raw.json" > "$OUT/eval_v6_raw.log" 2>&1
echo "$?" > "$OUT/eval_v6_raw.done"
touch "$OUT/V6_RAW_DONE"
echo "[$(date '+%F %T')] ===== V6 RAW DONE (eval rc=$(cat "$OUT/eval_v6_raw.done")) ====="
