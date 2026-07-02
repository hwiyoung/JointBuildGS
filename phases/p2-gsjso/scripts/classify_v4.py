#!/usr/bin/env python3
"""population-lock-aux v4 [2] — apply the agreed decomposition rule to the 48 generation-axis buildings
and cross-walk against the old d12 buckets. Observe only; NO labels are authoritative (판정=김휘영). The
rule + thresholds are as agreed (control-success-114 based); B uses roof_lowtex_v4 (tau-validated ruler
from [1]) with threshold = control-114 p90 of that SAME measure. Records every flag multi-hot so Kim can
re-prioritise precedence. Pure stdlib (tools:t0).

Decomposition (precedence A-first, as the rule text orders; all flags also emitted):
  a_cand = frac_views_incidence_le60 < 0.315 AND recon_score_median < 103.6   (control p10)
  veto   = any of {sparse,acmp,gs_sparse,gs_dense,gs_acmp} has_lod22==1   (fact: a method recovered it)
  -> 경계_방법회복 if a_cand AND veto
  -> A1_촬영확실  if a_cand AND recon_score_median < 31.8  (control min)
  -> A2_촬영경계  if a_cand
  -> B_무텍스처   if roof_lowtex_v4 >= B_THR              (control p90 of roof_lowtex_v4)
  -> E_폐색       if occlusion_frac_approx >= 0.667
  -> F_소형       if footprint_area_m2 < 29.8
  -> 미분류       otherwise (C 정반사 merged here; specular flagged separately)
"""
import csv, glob, json
from pathlib import Path
REPO = Path("/workspace/JointBuildGS")
M = REPO / "results/tum_transfer/mob/overseg_lever"
P0 = REPO / "phases/p0-audit/docs"
DOCS = REPO / "docs"

# thresholds (agreed; B_THR + LOWTEX_V4_COL set from [1] result via env-echo below)
INC60_MAX = 0.315
RECON_A_MAX = 103.6
RECON_A1_MAX = 31.8
OCC_MIN = 0.667
AREA_MIN = 29.8
LOWTEX_V4_COL = "roof_lowtex_v4"   # ruler adopted in [1]
B_THR = None                        # control-114 p90 of roof_lowtex_v4 (computed below)


def fnum(v):
    try: return float(v)
    except (TypeError, ValueError): return None


def main():
    v3 = {r["building_id"].replace("DEBY_LOD2_", ""): r for r in csv.DictReader(open(DOCS/"population_aux_v3.csv"))}
    # generation-axis 48 + control-114 from canonical status
    canon = glob.glob(str(REPO/"phases/p0-audit/runs/w2_1_roofer_default_*/building_reconstruction_status.csv"))[0]
    st = {}
    for r in csv.DictReader(open(canon)):
        st.setdefault(r["building_id"].replace("DEBY_LOD2_", ""), {})[r["input"].lower()] = r
    gen48, ctrl114 = [], []
    for b, d in st.items():
        als, dim = d.get("als", {}), d.get("dim", {})
        if als.get("has_lod22") == "True" and dim.get("has_lod22") == "True": ctrl114.append(b)
        if als.get("has_lod22") == "True" and dim.get("has_lod22") != "True" and dim.get("reason") != "missing_lod22_geometry":
            gen48.append(b)
    # B_THR = control-114 p90 of roof_lowtex_v4
    global B_THR
    cvals = sorted(fnum(v3[b].get(LOWTEX_V4_COL)) for b in ctrl114 if fnum(v3[b].get(LOWTEX_V4_COL)) is not None)
    import math
    B_THR = cvals[min(len(cvals)-1, math.ceil(0.90*len(cvals))-1)]
    # arm has_lod22 (veto) from gen_8way
    g8 = {r["bid"]: r for r in csv.DictReader(open(M/"gen_8way.csv"))}
    veto_arms = ["gs_seed_sparse", "gs_seed_dense", "gs_seed_acmp", "raw_sparse", "raw_acmp"]
    # old buckets from d12_buckets
    oldb = {r["bid"]: r["bucket"] for r in csv.DictReader(open(M/"d12_buckets.csv"))}
    # specular flag threshold = control p90 sat
    svals = sorted(fnum(v3[b].get("roof_sat_frac")) for b in ctrl114 if fnum(v3[b].get("roof_sat_frac")) is not None)
    SAT_THR = svals[min(len(svals)-1, math.ceil(0.90*len(svals))-1)]

    rows = []
    for b in sorted(gen48):
        r = v3.get(b, {})
        inc60 = fnum(r.get("frac_views_incidence_le60"))
        recon = fnum(r.get("recon_score_median"))
        ltv4 = fnum(r.get(LOWTEX_V4_COL))
        occ = fnum(r.get("occlusion_frac_approx"))
        area = fnum(r.get("footprint_area_m2"))
        sat = fnum(r.get("roof_sat_frac"))
        g = g8.get(b, {})
        veto = any(g.get(a) == "1" for a in veto_arms)
        recovered = [a for a in veto_arms if g.get(a) == "1"]
        a_cand = (inc60 is not None and inc60 < INC60_MAX) and (recon is not None and recon < RECON_A_MAX)
        f_B = ltv4 is not None and ltv4 >= B_THR
        f_E = occ is not None and occ >= OCC_MIN
        f_F = area is not None and area < AREA_MIN
        f_C = sat is not None and sat >= SAT_THR
        # precedence (rule order): A-first, veto pulls A->method-recovered
        if a_cand and veto: nc = "경계_방법회복"
        elif a_cand and (recon is not None and recon < RECON_A1_MAX): nc = "A1_촬영확실"
        elif a_cand: nc = "A2_촬영경계"
        elif f_B: nc = "B_무텍스처"
        elif f_E: nc = "E_폐색"
        elif f_F: nc = "F_소형"
        else: nc = "미분류"
        rows.append({"building_id": f"DEBY_LOD2_{b}", "old_bucket": oldb.get(b, "?"), "new_class": nc,
                     "a_cand": int(a_cand), "veto_recovered": ";".join(recovered) or "",
                     "flag_A1": int(a_cand and recon is not None and recon < RECON_A1_MAX),
                     "flag_B": int(f_B), "flag_E": int(f_E), "flag_F": int(f_F), "flag_C_specular": int(f_C),
                     "frac_inc60": inc60, "recon_median": recon, "roof_lowtex_v4": ltv4,
                     "occlusion": occ, "area_m2": area, "sat": sat})
    out = M/"bucket_crosswalk.csv"
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    # copy to docs (tracked)
    import shutil; shutil.copy(out, DOCS/"bucket_crosswalk.csv")
    # summary
    from collections import Counter
    print(f"B_THR (control-114 p90 of {LOWTEX_V4_COL}) = {B_THR:.3f} | SAT_THR(p90)={SAT_THR:.4f}")
    print("new_class dist:", dict(Counter(r["new_class"] for r in rows)))
    print("\nold_bucket -> new_class crosstab:")
    cross = Counter((r["old_bucket"], r["new_class"]) for r in rows)
    obs = sorted({r["old_bucket"] for r in rows}); ncs = sorted({r["new_class"] for r in rows})
    print("old_bucket\\new".ljust(22) + "".join(f"{n[:12]:>13}" for n in ncs))
    for ob in obs:
        print(f"{ob:22}" + "".join(f"{cross.get((ob,n),0):>13}" for n in ncs))
    uncls = [r["building_id"].replace("DEBY_LOD2_", "") for r in rows if r["new_class"] == "미분류"]
    print(f"\n미분류 ({len(uncls)}): {' '.join(uncls)}")
    print(f"specular-flagged among 미분류: {[r['building_id'].replace('DEBY_LOD2_','') for r in rows if r['new_class']=='미분류' and r['flag_C_specular']]}")
    json.dump({"unclassified": uncls, "B_THR": B_THR}, open("/tmp/v4_unclassified.json", "w"))


if __name__ == "__main__":
    main()
