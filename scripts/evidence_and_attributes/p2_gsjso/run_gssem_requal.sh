#!/usr/bin/env bash
# P2 — D/D4 gssem RE-QUAL (PART 1). Fix the read-out provenance: eval runs gssem->smrf per arm, so on-disk
# per-building cityjson/las/val3dity ended up SMRF. This regenerates them as GSSEM (thesis canonical read-out),
# preserving the SMRF snapshot for comparison. READ-ONLY w.r.t. training: CPU/docker only, NO GPU, NO retrain.
# *** NEVER touches gs_d5* (D5 training/eval in progress). *** Arms: gs_prior_full_{dense,acmp}, gs_d4_{dense,acmp}.
# Output numbers -> backup dir; comparison doc built separately (gssem_requal_doc.py). EPSG:25832. Observe only.
set -u
cd "$(dirname "$0")/../../.." || exit 1
REPO_HOST="$(pwd -P)"          # host path (tar/find run on host, NOT in container)
WS=/workspace/JointBuildGS     # container path (only for paths passed INTO docker)
OUT=results/tum_transfer/mob; A=results/tum_transfer/mob_analysis
EVALROOT=phases/p0-audit/runs/mob_eval
GEOJSON=results/tum_transfer/analysis/footprints_aoi.geojson
BK=$OUT/gssem_requal_backup; mkdir -p "$BK"
ARMS_D="gs_prior_full_dense gs_prior_full_acmp"
ARMS_D4="gs_d4_dense gs_d4_acmp"
ALL="$ARMS_D $ARMS_D4"
rm -f "$BK/PART1_DONE" "$BK/PART1_FAIL"
echo "[gssem-requal] start $(date '+%F %T'). arms=$ALL  (gs_d5* NOT touched)"

# ---- guard: refuse if any arm name looks like d5 (paranoia) ----
case "$ALL" in *d5*) echo "FATAL: d5 in arm list — abort"; echo fail > "$BK/PART1_FAIL"; exit 9;; esac

# ===== 1) BACKUP smrf (before destructive regen) =====
cp -p "$A/ref_rms_D.csv"  "$A/ref_rms_D_smrf.csv"  || { echo no-D-rms; }
cp -p "$A/ref_rms_d4.csv" "$A/ref_rms_d4_smrf.csv" || { echo no-d4-rms; }
cp -p "$OUT/eval_prior_full_gssem.json" "$BK/eval_prior_full_gssem.pre.json"
cp -p "$OUT/eval_d4_gssem.json"         "$BK/eval_d4_gssem.pre.json"
cp -p "$OUT/eval_prior_full_smrf.json"  "$BK/eval_prior_full_smrf.json"
cp -p "$OUT/eval_d4_smrf.json"          "$BK/eval_d4_smrf.json"
# smrf per-building geometry+validity (cityjson + val3dity; bulky .las excluded = regenerable via --classifier smrf)
( cd "$EVALROOT" && find $ALL \( -name '*.city.jsonl' -o -name '*.city.json' -o -name '*_val3dity.json' -o -name '*_val3dity.log' \) -print0 \
    | tar --null -cf "$REPO_HOST/$BK/perbuilding_smrf.tar" -T - ) 2>"$BK/backup_tar.err"
echo "[backup] perbuilding_smrf.tar = $(du -h "$BK/perbuilding_smrf.tar" 2>/dev/null | cut -f1)"

# snapshot smrf NUMBERS from current (smrf) disk
python3 scripts/evidence_and_attributes/p2_gsjso/gssem_requal_numbers.py smrf "$BK/numbers_smrf.json" || { echo "smrf-snapshot FAIL"; echo fail>"$BK/PART1_FAIL"; exit 2; }

# guard: do not proceed to destructive regen unless backup + snapshot exist
[ -s "$BK/perbuilding_smrf.tar" ] && [ -s "$BK/numbers_smrf.json" ] && [ -s "$A/ref_rms_d4_smrf.csv" ] || {
  echo "FATAL: backup incomplete — abort before regen"; echo fail > "$BK/PART1_FAIL"; exit 3; }
echo "[gssem-requal] backup OK — proceeding to gssem regen"

# ===== 2) GSSEM re-eval (regenerates per-building cityjson/las/val3dity as gssem; overwrites eval JSONs identically) =====
CFG_D="gs_prior_full_dense=$OUT/tsdf_gs_prior_full_dense.npz gs_prior_full_acmp=$OUT/tsdf_gs_prior_full_acmp.npz"
CFG_D4="gs_d4_dense=$OUT/tsdf_gs_d4_dense.npz gs_d4_acmp=$OUT/tsdf_gs_d4_acmp.npz"
echo "[$(date '+%T')] EVAL gssem D";  python3 scripts/input_and_alignment/p2_gsjso/tum_mob_eval.py --configs $CFG_D  --geojson "$GEOJSON" --classifier gssem --out "$OUT/eval_prior_full_gssem.json" > "$BK/eval_D_gssem.log"  2>&1
echo "[$(date '+%T')] EVAL gssem D4"; python3 scripts/input_and_alignment/p2_gsjso/tum_mob_eval.py --configs $CFG_D4 --geojson "$GEOJSON" --classifier gssem --out "$OUT/eval_d4_gssem.json"         > "$BK/eval_D4_gssem.log" 2>&1

# ===== 3) RMS->ref on gssem .las (p0-tools container: host python3 lacks laspy) =====
TOOLS="docker run --rm --user $(id -u):$(id -g) -v $REPO_HOST:/workspace/JointBuildGS -w /workspace/JointBuildGS jointbuildgs-p0-tools:t0"
echo "[$(date '+%T')] RMS gssem D";  $TOOLS python3 scripts/input_and_alignment/p2_gsjso/tum_mob_ref_rms.py --arms $ARMS_D  --out "$A/ref_rms_D_gssem.csv"  > "$BK/rms_D_gssem.log"  2>&1
echo "[$(date '+%T')] RMS gssem D4"; $TOOLS python3 scripts/input_and_alignment/p2_gsjso/tum_mob_ref_rms.py --arms $ARMS_D4 --out "$A/ref_rms_d4_gssem.csv" > "$BK/rms_D4_gssem.log" 2>&1

# ===== 4) snapshot gssem NUMBERS (disk now = gssem) =====
python3 scripts/evidence_and_attributes/p2_gsjso/gssem_requal_numbers.py gssem "$BK/numbers_gssem.json"

# ===== 5) verify generation (assembled/valid-solid REC) unchanged vs pre =====
python3 - "$BK" <<'PY'
import json, sys
BK = sys.argv[1]
def gen(fn):
    d = json.load(open(fn))
    REC = {"42364609","42364659","42364663","4907182","4907510","4908050","4908166","4908176"}
    out = {}
    for r in d:
        if r.get("tag") != "orig" or r["bid"].split("_")[-1] not in REC:
            continue
        cfg = r["config"]; out.setdefault(cfg, [0,0])
        if r.get("roofer_ok") and (r.get("roof_surfaces") or 0) > 0: out[cfg][0]+=1
        if r.get("val3dity_valid") and (r.get("roof_surfaces") or 0) > 0: out[cfg][1]+=1
    return out
for pre, post in [("eval_prior_full_gssem.pre.json","../eval_prior_full_gssem.json"),
                  ("eval_d4_gssem.pre.json","../eval_d4_gssem.json")]:
    import os
    a = gen(os.path.join(BK, pre)); b = gen(os.path.join(BK, post))
    same = a == b
    print(f"[verify] {pre.replace('.pre.json','')}: pre={a} post={b}  GENERATION {'UNCHANGED' if same else '*** CHANGED ***'}")
PY

echo "[gssem-requal] DONE $(date '+%F %T')" | tee "$BK/PART1_DONE"
