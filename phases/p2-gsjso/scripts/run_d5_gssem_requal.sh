#!/usr/bin/env bash
# P2-D5 PART 2 — gssem RE-QUAL for the 6 D5 arms + §5 cp judgment table.
# WAITS for the D5 1-GPU resume to finish (D5_1GPU_DONE), at which point disk per-building = smrf (resume's
# last eval). Then mirrors PART 1 (run_gssem_requal.sh): snapshot smrf -> regenerate gssem -> gssem RMS ->
# snapshot gssem -> build §5 cp table (D5a/b/c vs D4, gssem; smrf alongside) into docs/experiments/joint-optimization/w_d5/reports/W_D5.md.
# CPU/docker only (no GPU, no training, D5 already done). NO outlier-trim / refinement. EPSG:25832. Observe only.
# Launch: setsid nohup bash phases/p2-gsjso/scripts/run_d5_gssem_requal.sh > results/tum_transfer/mob/d5_requal.log 2>&1 < /dev/null &
set -u
cd "$(dirname "$0")/../../.." || exit 1
REPO_HOST="$(pwd -P)"; WS=/workspace/JointBuildGS
OUT=results/tum_transfer/mob; A=results/tum_transfer/mob_analysis
EVALROOT=phases/p0-audit/runs/mob_eval; GEOJSON=results/tum_transfer/analysis/footprints_aoi.geojson
BK=$OUT/gssem_requal_backup; mkdir -p "$BK"
ARMS="gs_d5a_dense gs_d5a_acmp gs_d5b_dense gs_d5b_acmp gs_d5c_dense gs_d5c_acmp"
TOOLS="docker run --rm --user $(id -u):$(id -g) -v $REPO_HOST:/workspace/JointBuildGS -w /workspace/JointBuildGS jointbuildgs-p0-tools:t0"
rm -f "$BK/PART2_DONE" "$BK/PART2_FAIL"

# 0) WAIT for D5 resume to finish
echo "[d5-requal] $(date '+%F %T') waiting for D5_1GPU_DONE ..."
while [ ! -f "$OUT/D5_1GPU_DONE" ]; do sleep 60; done
[ -s "$OUT/eval_d5_gssem.json" ] && [ -s "$OUT/eval_d5_smrf.json" ] || { echo "FATAL: eval_d5_*.json missing"; echo fail>"$BK/PART2_FAIL"; exit 2; }
echo "[d5-requal] $(date '+%F %T') D5 done. disk per-building = smrf (resume last eval)."

# 1) SMRF snapshot (current disk = smrf) BEFORE regen
echo "[$(date '+%T')] RMS smrf (current smrf .las)"
$TOOLS python3 phases/p2-gsjso/scripts/tum_mob_ref_rms.py --arms $ARMS --out "$A/ref_rms_d5_smrf.csv" > "$BK/rms_d5_smrf.log" 2>&1
# backup smrf per-building cityjson+val3dity (bulky .las excluded = regenerable via --classifier smrf)
( cd "$EVALROOT" && find $ARMS \( -name '*.city.jsonl' -o -name '*.city.json' -o -name '*_val3dity.json' \) -print0 \
    | tar --null -cf "$REPO_HOST/$BK/perbuilding_d5_smrf.tar" -T - ) 2>"$BK/backup_d5_tar.err"
cp -p "$OUT/eval_d5_gssem.json" "$BK/eval_d5_gssem.pre.json"
python3 phases/p2-gsjso/scripts/gssem_requal_numbers.py smrf "$BK/numbers_d5_smrf.json" D5 || { echo fail>"$BK/PART2_FAIL"; exit 3; }
[ -s "$BK/perbuilding_d5_smrf.tar" ] && [ -s "$BK/numbers_d5_smrf.json" ] || { echo "FATAL backup incomplete"; echo fail>"$BK/PART2_FAIL"; exit 4; }
echo "[d5-requal] smrf snapshot OK -> regen gssem"

# 2) GSSEM re-eval (regenerate per-building cityjson/las/val3dity as gssem; overwrites eval_d5_gssem.json identically)
CFG=""; for n in $ARMS; do CFG="$CFG $n=$OUT/tsdf_$n.npz"; done
echo "[$(date '+%T')] EVAL gssem (6 D5 arms)"
python3 phases/p2-gsjso/scripts/tum_mob_eval.py --configs $CFG --geojson "$GEOJSON" --classifier gssem --out "$OUT/eval_d5_gssem.json" > "$BK/eval_d5_gssem.log" 2>&1

# 3) GSSEM RMS + snapshot
echo "[$(date '+%T')] RMS gssem (regenerated gssem .las)"
$TOOLS python3 phases/p2-gsjso/scripts/tum_mob_ref_rms.py --arms $ARMS --out "$A/ref_rms_d5_gssem.csv" > "$BK/rms_d5_gssem.log" 2>&1
python3 phases/p2-gsjso/scripts/gssem_requal_numbers.py gssem "$BK/numbers_d5_gssem.json" D5

# 4) verify generation unchanged (gssem pre vs post)
python3 - "$BK" "$OUT" <<'PY'
import json, sys, os
BK, OUT = sys.argv[1], sys.argv[2]
REC = {"42364609","42364659","42364663","4907182","4907510","4908050","4908166","4908176"}
def gen(fn):
    out={}
    for r in json.load(open(fn)):
        if r.get("tag")!="orig" or r["bid"].split("_")[-1] not in REC: continue
        c=r["config"]; out.setdefault(c,[0,0])
        if r.get("roofer_ok") and (r.get("roof_surfaces") or 0)>0: out[c][0]+=1
        if r.get("val3dity_valid") and (r.get("roof_surfaces") or 0)>0: out[c][1]+=1
    return out
a=gen(os.path.join(BK,"eval_d5_gssem.pre.json")); b=gen(os.path.join(OUT,"eval_d5_gssem.json"))
print(f"[verify] D5 gssem generation pre==post: {a==b}")
PY

# 5) §5 cp judgment table -> docs/experiments/joint-optimization/w_d5/reports/W_D5.md
python3 phases/p2-gsjso/scripts/d5_cp_table.py > "$BK/d5_cp_table.log" 2>&1
echo "[d5-requal] DONE $(date '+%F %T')" | tee "$BK/PART2_DONE"
