#!/usr/bin/env python3
"""P2 complexity-survey PARTS 2-4 — building complexity mapping + defect↔complexity correlation +
target candidates (no retrain, reference/Roofer reuse only, observe-only; verdict=김휘영).

Confound ③ of B1 was "targets mostly single-level". This maps OBJECTIVE complexity across the
controlled-93 to find genuinely MULTI-LEVEL (stepped) buildings with good coverage, and tests whether
the GS positional defect (±1~2.5m off-level) tracks complexity on the 11 GS buildings.

Complexity signals (all reused, reference-side only — no GS needed for the 93):
  - LoD2 roofType (AdV Dachform) — authoritative but COARSE (mislabels 4906969 stepped-flat as 1000
    Flachdach), so used as context, not the multi-level signal.
  - ALS roof Z-LEVELS = distinct height clusters of the ALS Roofer roof facets (als_default.city.json
    facet mean-z, merged <LEVEL_MERGE) — the MULTI-LEVEL signal for all 93 (the defect is off-LEVEL).
  - ALS roof z-SPAN (facet z range) — multi-storey / stepped magnitude.
  - footprint vertex count (geojson polygon) — footprint complexity.
  - ref/als/dim Roofer facet counts (D6 census) — over-seg context.
For the 11 GS buildings the TRUE raw-ALS z-levels (complexity_metric.csv, PART 1) are used instead of
the cityjson proxy, and merged with PART 1's dz-robust best-fit resid for the correlation.

Reuse: results/.../analysis_pack_d6/survey_per_building.csv (D6 93-census), als_default.city.json
(w3_2b Roofer), footprints_aoi.geojson, complexity_metric.csv (PART 1). EPSG:25832. Run in p0-tools.
Out: results/.../overseg_lever/complexity_survey.csv + complexity_targets.csv + docs/figs/W_complexity/*.png
"""
import csv, glob, json, sys
from collections import defaultdict
from pathlib import Path
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO = Path("/workspace/JointBuildGS")
LEV = REPO / "results/tum_transfer/mob/overseg_lever"
FIG = REPO / "docs/figs/W_complexity"
D6 = REPO / "results/tum_transfer/mob/analysis_pack_d6/survey_per_building.csv"
GEOJSON = REPO / "results/tum_transfer/analysis/footprints_aoi.geojson"
CJ_ALS = sorted(glob.glob(str(REPO / "phases/p0-audit/runs/w3_2b_roofer_repeatability_*/cityjson/run_2/als_default.city.json")))
MOB = ["42364609", "42364659", "42364663", "4907182", "4907510",
       "4908050", "4908166", "4908176", "4906969", "4908023", "4906972"]
LEVEL_MERGE = 0.8   # m, merge facet mean-z within this into one level
RT_NAME = {"1000": "Flachdach", "2100": "Pultdach", "2200": "versetztesPult", "3100": "Satteldach",
           "3200": "Walmdach", "3300": "Krüppelwalm", "3400": "Mansarde", "3500": "Zeltdach",
           "3600": "Sheddach", "3700": "Bogendach", "9999": "Sonstiges"}


def footprint_vertices():
    """{bid: exterior-ring vertex count (closing vertex removed)} from the footprint geojson."""
    d = json.load(open(GEOJSON)); out = {}
    for f in d["features"]:
        bid = str(f["properties"].get("building_id", "")).replace("DEBY_LOD2_", "")
        g = f["geometry"]
        if g["type"] == "Polygon":
            ring = g["coordinates"][0]
        elif g["type"] == "MultiPolygon":
            ring = max((p[0] for p in g["coordinates"]), key=len)
        else:
            continue
        n = len(ring) - 1 if len(ring) > 1 and ring[0] == ring[-1] else len(ring)
        out[bid] = max(out.get(bid, 0), n)   # if multiple parts, take the most complex
    return out


def als_levels_from_cityjson():
    """{bid: (n_levels, z_span, n_roof_facets)} from the ALS Roofer cityjson roof facets."""
    if not CJ_ALS:
        return {}
    d = json.load(open(CJ_ALS[0]))
    tr = d.get("transform", {}); sc = np.array(tr.get("scale", [1, 1, 1])); tl = np.array(tr.get("translate", [0, 0, 0]))
    V = np.array(d["vertices"], float) * sc + tl
    out = {}
    for cid, o in d.get("CityObjects", {}).items():
        bid = cid.replace("DEBY_LOD2_", "").split("-")[0]
        zmeans = []
        for gm in o.get("geometry", []):
            sem = gm.get("semantics", {})
            surfs = sem.get("surfaces", []); vals = sem.get("values", [])
            bnds = gm.get("boundaries", [])
            # Solid: boundaries[shell][face][ring]; values[shell][face]
            for si, shell in enumerate(bnds):
                for fi, face in enumerate(shell):
                    try:
                        ty = surfs[vals[si][fi]].get("type")
                    except Exception:
                        ty = None
                    if ty != "RoofSurface" or not face or not face[0] or len(face[0]) < 3:
                        continue
                    zmeans.append(float(np.mean(V[[int(v) for v in face[0]]][:, 2])))
        if not zmeans:
            continue
        zmeans = sorted(zmeans)
        # merge into levels within LEVEL_MERGE
        levels = [[zmeans[0]]]
        for z in zmeans[1:]:
            if z - levels[-1][-1] < LEVEL_MERGE:
                levels[-1].append(z)
            else:
                levels.append([z])
        span = zmeans[-1] - zmeans[0]
        prev = out.get(bid)
        # if multiple parts map to same bid, keep the one with more facets
        if prev is None or len(zmeans) > prev[2]:
            out[bid] = (len(levels), round(span, 2), len(zmeans))
    return out


def load_d6():
    rows = {}
    for r in csv.DictReader(open(D6)):
        bid = r["building_id"].replace("DEBY_LOD2_", "")
        def i(k):
            v = r.get(k, ""); return int(v) if v not in ("", None) else None
        def fl(k):
            v = r.get(k, ""); return float(v) if v not in ("", None) else None
        rows[bid] = {"roofType": r.get("roofType"), "class4": r.get("class4"),
                     "ref_facets": i("ref_facets"), "als_facets": i("als_facets"), "dim_facets": i("dim_facets"),
                     "als_nmad": fl("als_nmad_m"), "dim_nmad": fl("dim_nmad_m")}
    return rows


def load_part1():
    """{bid: {arm: bestfit_resid}} + als_levels(true) from PART 1."""
    p = LEV / "complexity_metric.csv"
    if not p.exists():
        return {}, {}
    resid = defaultdict(dict); truelv = {}
    for r in csv.DictReader(open(p)):
        resid[r["bid"]][r["arm"]] = float(r["bestfit_resid"])
        truelv[r["bid"]] = (int(r["als_levels"]), float(r["als_span_m"]))
    return resid, truelv


def main():
    LEV.mkdir(parents=True, exist_ok=True); FIG.mkdir(parents=True, exist_ok=True)
    d6 = load_d6(); fpv = footprint_vertices(); alz = als_levels_from_cityjson()
    resid, truelv = load_part1()
    rows = []
    for bid, c in d6.items():
        lv, span, nfac = alz.get(bid, (None, None, None))
        # for the 11 GS buildings prefer the TRUE raw-ALS levels (PART 1)
        if bid in truelv:
            lv_true, span_true = truelv[bid]
        else:
            lv_true, span_true = None, None
        lv_use = lv_true if lv_true is not None else lv
        span_use = span_true if span_true is not None else span
        # raw multi-level flag (NOTE: confounded — a pitched roof's two slope facets differ in mean-z,
        # so Roofer-facet "levels" overcount pitched roofs as multi-level; use roofType to disambiguate).
        complex_flag = bool(lv_use is not None and ((lv_use >= 3) or (lv_use >= 2 and (span_use or 0) >= 3.0)))
        # STEPPED-FLAT = the defect-relevant complexity: a FLAT-roofed (1000) building with multiple real
        # height levels (genuine steps, not pitch). This is where the ±1~2.5m off-level defect lives.
        stepped_flat = bool(c["roofType"] == "1000" and lv_use is not None and lv_use >= 2 and (span_use or 0) >= 3.0)
        rows.append({
            "bid": bid, "roofType": c["roofType"], "roofType_name": RT_NAME.get(c["roofType"], "?"),
            "class4": c["class4"], "fp_vertices": fpv.get(bid),
            "als_levels_cj": lv, "als_span_cj": span, "als_roof_facets_cj": nfac,
            "als_levels_true": lv_true, "als_span_true": span_true,
            "ref_facets": c["ref_facets"], "als_facets": c["als_facets"], "dim_facets": c["dim_facets"],
            "als_nmad": c["als_nmad"],
            "multi_level_complex": complex_flag, "stepped_flat": stepped_flat, "has_GS": bid in MOB,
            "d4_resid": resid.get(bid, {}).get("gs_d4_dense"), "b1_resid": resid.get(bid, {}).get("gs_b1_dense"),
        })
    keys = list(rows[0].keys())
    with open(LEV / "complexity_survey.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys); w.writeheader(); w.writerows(rows)

    # ---- distribution ----
    n = len(rows)
    by_lv = defaultdict(int)
    for r in rows:
        by_lv[r["als_levels_cj"]] += 1
    complex_set = [r for r in rows if r["multi_level_complex"]]
    stepped = [r for r in rows if r["stepped_flat"]]
    print(f"=== complexity distribution (93 control; ALS levels via Roofer cityjson, merge<{LEVEL_MERGE}m) ===")
    print(f"n={n}  raw-multi-level(facet-confounded)={len(complex_set)}  STEPPED-FLAT(1000+≥2lv+span≥3m)={len(stepped)}")
    print("ALS-level count histogram (cityjson):", dict(sorted((k, v) for k, v in by_lv.items() if k is not None)))
    print("roofType dist:", dict(sorted(defaultdict(int, {r['roofType']: sum(1 for x in rows if x['roofType']==r['roofType']) for r in rows}).items())))

    # ---- PART 3: defect↔complexity correlation (11 GS buildings, PART1 best-fit resid) ----
    print("\n=== PART 3: defect↔complexity (11 GS; true ALS levels/span vs dz-robust best-fit resid) ===")
    gs = [r for r in rows if r["has_GS"] and r["als_levels_true"] is not None
          and r["d4_resid"] is not None and r["b1_resid"] is not None]
    print(f"{'bid':9}{'ALSlv':6}{'span':7}{'fpV':5}{'rt':6}{'stepF':6}{'d4_resid':9}{'b1_resid':9}{'b1-d4':7}")
    for r in sorted(gs, key=lambda x: -(x["als_span_true"] or 0)):
        d = round((r["b1_resid"] or 0) - (r["d4_resid"] or 0), 2)
        print(f"{r['bid']:9}{str(r['als_levels_true']):6}{str(r['als_span_true']):7}{str(r['fp_vertices']):5}"
              f"{str(r['roofType']):6}{str(r['stepped_flat']):6}{str(r['d4_resid']):9}{str(r['b1_resid']):9}{str(d):7}")
    if len(gs) >= 4:
        sp = np.array([r["als_span_true"] for r in gs]); d4 = np.array([r["d4_resid"] for r in gs])
        b1 = np.array([r["b1_resid"] for r in gs]); lvv = np.array([r["als_levels_true"] for r in gs])
        def corr(a, b): return round(float(np.corrcoef(a, b)[0, 1]), 2)
        rt_flat = np.array([1.0 if r["roofType"] == "1000" else 0.0 for r in gs])
        print(f"corr(ALS span, d4_resid)={corr(sp,d4)}  corr(ALS levels, d4_resid)={corr(lvv,d4)}  corr(flat-roof, d4_resid)={corr(rt_flat,d4)}")
        print(f"corr(ALS span, b1-d4 delta)={corr(sp, b1-d4)}  corr(d4_resid, b1-d4 delta)={corr(d4, b1-d4)}  (neg => B1 regresses-to-mean: helps high-resid, hurts low)")
        # scatter
        fig, ax = plt.subplots(figsize=(6.5, 4.6))
        ax.scatter(sp, d4, c="tab:blue", label="d4 best-fit resid", s=40)
        ax.scatter(sp, b1, c="tab:orange", label="b1 best-fit resid", s=40)
        for r in gs:
            ax.annotate(r["bid"][-4:], (r["als_span_true"], r["d4_resid"]), fontsize=6)
        ax.set_xlabel("ALS roof z-span (m) — complexity proxy"); ax.set_ylabel("dz-robust best-fit resid (m)")
        ax.set_title("defect vs complexity (11 GS buildings)"); ax.legend(fontsize=8); ax.grid(alpha=0.3)
        fig.tight_layout(); fig.savefig(FIG / "defect_vs_complexity.png", dpi=110); plt.close(fig)

    # ---- PART 4: target candidates (multi-level + coverage) ----
    print("\n=== PART 4: multi-level target candidates (complex AND ALS coverage) ===")
    cands = sorted(complex_set, key=lambda r: -((r["als_span_true"] or r["als_span_cj"] or 0)))
    trows = []
    for r in cands:
        lv = r["als_levels_true"] if r["als_levels_true"] is not None else r["als_levels_cj"]
        span = r["als_span_true"] if r["als_span_true"] is not None else r["als_span_cj"]
        cover = "ALS✓" + ("/DIM✓" if (r["dim_facets"] or 0) > 0 else "/DIM✗")
        status = "GS-exists" if r["has_GS"] else "GS-needed"
        trows.append({"bid": r["bid"], "roofType": r["roofType"], "als_levels": lv, "als_span_m": span,
                      "fp_vertices": r["fp_vertices"], "als_facets": r["als_facets"], "dim_facets": r["dim_facets"],
                      "coverage": cover, "status": status,
                      "d4_resid": r["d4_resid"], "b1_resid": r["b1_resid"]})
        print(f"  {r['bid']:9} rt={r['roofType']:5} ALSlv={lv} span={span}m fpV={r['fp_vertices']} "
              f"alsFac={r['als_facets']} {cover} [{status}] d4_resid={r['d4_resid']}")
    if trows:
        with open(LEV / "complexity_targets.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(trows[0].keys())); w.writeheader(); w.writerows(trows)
    print(f"\n[done] -> {LEV}/complexity_survey.csv (+ _targets.csv) ; figs {FIG}/")


if __name__ == "__main__":
    main()
