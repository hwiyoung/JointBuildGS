#!/usr/bin/env python3
"""population-verify-aux (B) — per-building RAW MATERIAL for subclass rules (NO labels; rules=김휘영).
Merges EXISTING outputs into population_aux.csv over ALL 199 buildings (reuse only, no reconstruction).
Columns: building_id + coverage(views/angles/area) + texture + occlusion + footprint shape + arm has_lod22.
Where a source only covers the P0-audit subset (T7 79 / T9 8 / T11 71 / W4c 46 / v6 11 / gen_8way 64),
the cell is blank and the coverage gap is reported. Observe only; verdict=김휘영. EPSG:25832.
"""
import csv, glob, json
from collections import defaultdict
from pathlib import Path
REPO = Path("/workspace/JointBuildGS")
P0 = REPO / "phases/p0-audit/docs"
MOB = REPO / "results/tum_transfer/mob"
GEOJSON = REPO / "results/tum_transfer/analysis/footprints_aoi.geojson"


def rd(p):
    return {r["building_id"].replace("DEBY_LOD2_", ""): r for r in csv.DictReader(open(p))} if Path(p).exists() else {}


def f(v):
    try:
        return round(float(v), 4)
    except (TypeError, ValueError):
        return ""


def tf(v):
    return 1 if str(v).strip().lower() in ("true", "1", "yes") else (0 if str(v).strip() != "" else "")


def main():
    # ---- population spine: W3_2c (199, als/dim has_lod22 + footprint_area) ----
    w3 = rd(P0 / "W3_2c_canonical_paired_status.csv")
    # ---- raw canonical status (w2_1) for als/dim has_lod22 (the 114/64/21 source) ----
    w21 = defaultdict(dict)
    cf = glob.glob(str(REPO / "phases/p0-audit/runs/w2_1_roofer_default_*/building_reconstruction_status.csv"))
    if cf:
        for x in csv.DictReader(open(cf[0])):
            w21[x["building_id"].replace("DEBY_LOD2_", "")][x["input"].lower()] = x
    # ---- footprint vertices + area from geojson (199) ----
    fp = {}
    for feat in json.load(open(GEOJSON))["features"]:
        bid = feat["properties"].get("building_id", "").replace("DEBY_LOD2_", "")
        g = feat["geometry"]
        ring = g["coordinates"][0] if g["type"] == "Polygon" else max((p[0] for p in g["coordinates"]), key=len)
        nv = len(ring) - 1 if len(ring) > 1 and ring[0] == ring[-1] else len(ring)
        a = feat["properties"].get("area_m2")
        prev = fp.get(bid)
        if prev is None or nv > prev[0]:
            fp[bid] = (nv, a)
    # ---- coverage/texture/occlusion sources (P0-audit subsets) ----
    t7 = rd(P0 / "W3_failure_diagnosis_building_metrics.csv")            # 79 coverage
    t11 = rd(P0 / "W3_survivor_texture_refine_building_metrics.csv")     # 71 texture+views
    t9 = rd(P0 / "W3_failure_surface_cause_building_metrics.csv")        # 8 failure texture+views
    w4c = rd(P0 / "W4c_no_points_breakdown.csv")                         # 46 no_points views
    # ---- arm has_lod22: v6 table (11) + gen_8way (64) ----
    v6 = defaultdict(dict)
    if (MOB / "table_v6.csv").exists():
        for x in csv.DictReader(open(MOB / "table_v6.csv")):
            if x.get("tag") == "matched":
                v6[x["bid"].replace("DEBY_LOD2_", "")][x["arm"]] = x
    g8 = {r["bid"]: r for r in csv.DictReader(open(MOB / "overseg_lever/gen_8way.csv"))} if (MOB / "overseg_lever/gen_8way.csv").exists() else {}

    def arm_lod22(bid, arm):
        # gen_8way (64 failures): model bool = has_lod22 fact
        if bid in g8 and arm in g8[bid]:
            return tf(g8[bid][arm])
        # v6 table (11): solid True = has_lod22
        vk = {"gs_seed_sparse": "gs_seed_sparse", "gs_seed_dense": "gs_seed_dense", "gs_seed_acmp": "gs_seed_acmp",
              "raw_sparse": "raw_sparse", "raw_acmp": "raw_acmp"}.get(arm)
        if vk and bid in v6 and vk in v6[bid]:
            return tf(v6[bid][vk].get("solid"))
        return ""

    bids = sorted(set(w3) | set(w21) | set(fp))
    rows = []
    for b in bids:
        w = w3.get(b, {}); w2 = w21.get(b, {})
        als = w2.get("als", {}); dim = w2.get("dim", {})
        cov = t7.get(b, {}); tex = t11.get(b) or t9.get(b) or {}; wc = w4c.get(b, {})
        # coverage: prefer T11 (all/near/oblique) else T9 else W4c
        nn = tex.get("near_nadir_view_count") or wc.get("near_nadir")
        no = tex.get("oblique_view_count") or wc.get("oblique")
        nt = tex.get("all_view_count") or cov.get("view_count")
        rows.append({
            "building_id": f"DEBY_LOD2_{b}",
            # has_lod22 (facts; als/dim from raw canonical w2_1 = the 114/64/21 source)
            "als_has_lod22": tf(als.get("has_lod22")) if als else tf(w.get("als_has_lod22")),
            "dim_has_lod22": tf(dim.get("has_lod22")) if dim else tf(w.get("dim_has_lod22")),
            "sparse_has_lod22": arm_lod22(b, "raw_sparse"),
            "acmp_has_lod22": arm_lod22(b, "raw_acmp"),
            "gs_sparse_has_lod22": arm_lod22(b, "gs_seed_sparse"),
            "gs_dense_has_lod22": arm_lod22(b, "gs_seed_dense"),
            "gs_acmp_has_lod22": arm_lod22(b, "gs_seed_acmp"),
            # coverage (angle-aware; subset)
            "n_views_nadir": f(nn), "n_views_oblique": f(no), "n_views_total": f(nt),
            "median_intersection_deg": "",   # pairwise view-intersection NOT in existing outputs -> needs reproject compute
            "median_incidence_deg": f(cov.get("median_incidence_deg") or tex.get("sharp_incidence_deg_median") or wc.get("near_nadir_incid_deg")),
            "roof_area_covered_frac": f(cov.get("median_in_frame_sample_fraction")),   # in-frame sample frac (proxy)
            # texture (T9/T11)
            "roof_lowtex_frac": f(tex.get("sharp_low_texture_pixel_ratio")),
            "roof_grad_p10": f(tex.get("sharp_gradient_p10") or tex.get("near_nadir_texture_gradient_p10") or wc.get("near_texture_grad")),
            # occlusion (T7 approx)
            "occlusion_frac_approx": f(cov.get("occlusion_risk_view_fraction")),
            # footprint shape
            "footprint_area_m2": f(fp.get(b, ("", ""))[1] or w.get("footprint_area_m2")),
            "n_exterior_vertices": fp.get(b, ("", ""))[0],
        })
    keys = list(rows[0].keys())
    out = MOB / "overseg_lever" / "population_aux.csv"
    with open(out, "w", newline="") as fo:
        w = csv.DictWriter(fo, fieldnames=keys); w.writeheader(); w.writerows(rows)
    # coverage-gap report
    def nonblank(k):
        return sum(1 for r in rows if r[k] not in ("", None))
    print(f"[population_aux] {len(rows)} buildings -> {out}")
    print("=== column coverage (non-blank / 199) ===")
    for k in keys[1:]:
        print(f"  {k:26} {nonblank(k)}/{len(rows)}")


if __name__ == "__main__":
    main()
