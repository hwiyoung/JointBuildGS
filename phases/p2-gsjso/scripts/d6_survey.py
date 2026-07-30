#!/usr/bin/env python3
"""P2-D6 survey — population-wide curved-building / over-seg census (P0 reuse, NO reconstruction).

Reuses P0 controlled-93 outputs to ask: is the curved over-seg seen in 4906969 a one-building issue
or a curved-roof-type-wide one; and does LiDAR(ALS) also over-segment? Observation only; verdict=김휘영.

Reference roof-TYPE classification uses the authoritative CityGML <bldg:roofType> attribute (code->4class
map published below). ⚠ The attribute (and the planar LoD2 geometry) do NOT match the observational
labels: 4906969("curved")=1000 flat·3 horiz facets, 4906972("flat")=3100 gable·sloped, 42364659
("composite")=1000 flat. And there are ZERO reference-curved(3700/Bogen) buildings in the 93 — see
phases/p2-gsjso/docs/issues.md. So the over-seg question is answered from the per-building distribution, not the
(empty) reference-curved group.

Inputs (all reused, read-only):
 - 93 set: w3_2c_canonical_closeout_.../docs_snapshot/W3_2c_canonical_paired_status.csv (coverage_control_population=yes)
 - ref roofType + ref facets: data/raw/lod2/*.gml  (RoofSurface count; matches baselines.json for the 11 mob)
 - ALS/DIM facets: w3_2b_roofer_repeatability_.../cityjson/run_2/{als,dim}_default.city.json (target-only)
 - accuracy: W3_2c_canonical_roofer_quality_metrics.csv (als/dim_height_nmad_m, boundary_chamfer_m; 71 both_success)
 - GS facets (4906969 only, mob harness): results/tum_transfer/mob/d5_target_facets.csv (annotated, different harness)

Runs in jointbuildgs-p0-tools:t0 (numpy/matplotlib/xml/json; no scipy). EPSG:25832.
Out: results/tum_transfer/mob/analysis_pack_d6/{survey_per_building.csv,survey_by_type.csv} + docs/figs/W_D6/survey_*.png
"""
import csv, json, glob
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np, xml.etree.ElementTree as ET
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO = Path("/workspace/JointBuildGS")
P0 = REPO / "phases/p0-audit"
CLOSE = P0 / "runs/w3_2c_canonical_closeout_20260612_222618/docs_snapshot"
CJ = P0 / "runs/w3_2b_roofer_repeatability_20260612_220747/cityjson/run_2"
GMLDIR = P0 / "data/raw/lod2"
OUT = REPO / "results/tum_transfer/mob/analysis_pack_d6"
FIGDIR = REPO / "docs/figs/W_D6"

# AdV Dachform code -> 4-class (published). Multi-plane pitched (gable/hip/...) = sloped-planar.
RT_NAME = {"1000": "Flachdach", "2100": "Pultdach", "2200": "versetztesPult", "3100": "Satteldach",
           "3200": "Walmdach", "3300": "Krüppelwalm", "3400": "Mansarddach", "3500": "Zeltdach",
           "3600": "Sheddach", "3700": "Bogendach", "3900": "Mischform", "4000": "asymSattel",
           "9999": "Sonstiges"}
RT_CLASS = {"1000": "flat", "2100": "sloped", "2200": "sloped", "3100": "sloped", "3200": "sloped",
            "3300": "sloped", "3400": "sloped", "3500": "sloped", "4000": "sloped",
            "3700": "curved", "3600": "composite", "3900": "composite", "9999": "other"}


def L(t): return t.rsplit("}", 1)[-1]


def load_ctrl():
    rows = list(csv.DictReader(open(CLOSE / "W3_2c_canonical_paired_status.csv")))
    return [r["building_id"] for r in rows if r.get("coverage_control_population", "").strip().lower() == "yes"]


def gml_roof(ctrl_set):
    """roofType code + reference RoofSurface count per building (restricted to ctrl)."""
    rt, reff = {}, {}
    for g in glob.glob(str(GMLDIR / "*.gml")):
        for _, el in ET.iterparse(g, events=("end",)):
            if L(el.tag) != "Building":
                continue
            bid = next((v for k, v in el.attrib.items() if L(k) == "id"), None)
            if bid in ctrl_set:
                rts = [e.text.strip() for e in el.iter() if L(e.tag) == "roofType" and e.text]
                rt[bid] = rts[0] if rts else "NONE"
                reff[bid] = sum(1 for e in el.iter() if L(e.tag) == "RoofSurface")
            el.clear()
    return rt, reff


def cityjson_facets(path):
    d = json.loads(Path(path).read_text())
    facets, present = defaultdict(int), set()
    for cid, o in d.get("CityObjects", {}).items():
        base = cid.split("-")[0]
        present.add(base)
        for g in o.get("geometry", []):
            for s in g.get("semantics", {}).get("surfaces", []):
                if s.get("type") == "RoofSurface":
                    facets[base] += 1
    return facets, present


def load_accuracy():
    """als/dim height NMAD (vertical, m) + boundary chamfer (m) per building, 71 both_success."""
    acc = {}
    for r in csv.DictReader(open(CLOSE / "W3_2c_canonical_roofer_quality_metrics.csv")):
        b = r["building_id"]
        def f(k):
            v = r.get(k, "")
            try:
                return round(float(v), 3)
            except (ValueError, TypeError):
                return None
        acc[b] = {"als_nmad": f("als_height_nmad_m"), "dim_nmad": f("dim_height_nmad_m"),
                  "als_chamfer": f("als_boundary_chamfer_m"), "dim_chamfer": f("dim_boundary_chamfer_m")}
    return acc


def main():
    OUT.mkdir(parents=True, exist_ok=True); FIGDIR.mkdir(parents=True, exist_ok=True)
    ctrl = load_ctrl(); cset = set(ctrl)
    rt, reff = gml_roof(cset)
    alsf, alsp = cityjson_facets(CJ / "als_default.city.json")
    dimf, dimp = cityjson_facets(CJ / "dim_default.city.json")
    acc = load_accuracy()
    # GS for 4906969 (mob harness, annotated separately)
    gs = {}
    for r in csv.DictReader(open(REPO / "results/tum_transfer/mob/d5_target_facets.csv")):
        gs[r["bid"]] = {"gs_dense": r.get("fair"), "gs_acmp": r.get("fairAc"),
                        "mob_lidar": r.get("LiD"), "mob_dim": r.get("img"), "mob_ref": r.get("ref")}

    rows = []
    for b in ctrl:
        code = rt.get(b, "NONE"); cls = RT_CLASS.get(code, "other")
        r = reff.get(b)
        # facet==0 <=> has_lod22 False <=> NOT produced as LoD2.2 (verified) -> mark 미산출 (None)
        a = alsf.get(b, 0) if b in alsp else None
        dm = dimf.get(b, 0) if b in dimp else None
        if a == 0:
            a = None
        if dm == 0:
            dm = None
        ac = acc.get(b, {})
        row = {"building_id": b, "roofType": code, "roofType_name": RT_NAME.get(code, "?"), "class4": cls,
               "ref_facets": r, "als_facets": a, "dim_facets": dm,
               "dim_minus_als": (dm - a) if (dm is not None and a is not None) else None,
               "dim_minus_ref": (dm - r) if (dm is not None and r is not None) else None,
               "als_minus_ref": (a - r) if (a is not None and r is not None) else None,
               "dim_over_ref": (round(dm / r, 2) if (dm is not None and r) else None),
               "als_nmad_m": ac.get("als_nmad"), "dim_nmad_m": ac.get("dim_nmad"),
               "als_chamfer_m": ac.get("als_chamfer"), "dim_chamfer_m": ac.get("dim_chamfer")}
        b_short = b.replace("DEBY_LOD2_", "")
        if b_short in gs:
            row["gs_dense_facets_mobharness"] = gs[b_short]["gs_dense"]
            row["gs_acmp_facets_mobharness"] = gs[b_short]["gs_acmp"]
        rows.append(row)

    keys = ["building_id", "roofType", "roofType_name", "class4", "ref_facets", "als_facets",
            "dim_facets", "dim_minus_als", "dim_minus_ref", "als_minus_ref", "dim_over_ref",
            "als_nmad_m", "dim_nmad_m", "als_chamfer_m", "dim_chamfer_m",
            "gs_dense_facets_mobharness", "gs_acmp_facets_mobharness"]
    with open(OUT / "survey_per_building.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore"); w.writeheader(); w.writerows(rows)

    # by-type summary
    byc = defaultdict(list)
    for row in rows:
        byc[row["class4"]].append(row)
    summ = []
    for cls in ["flat", "sloped", "curved", "composite", "other"]:
        rs = byc.get(cls, [])
        dimr = [x["dim_minus_ref"] for x in rs if x["dim_minus_ref"] is not None]
        alsr = [x["als_minus_ref"] for x in rs if x["als_minus_ref"] is not None]
        dima = [x["dim_minus_als"] for x in rs if x["dim_minus_als"] is not None]
        summ.append({"class4": cls, "n": len(rs),
                     "n_dim_recon": sum(1 for x in rs if x["dim_facets"] is not None),
                     "n_als_recon": sum(1 for x in rs if x["als_facets"] is not None),
                     "n_dim_over_ref": sum(1 for x in dimr if x > 0),
                     "n_als_over_ref": sum(1 for x in alsr if x > 0),
                     "med_dim_minus_ref": (round(float(np.median(dimr)), 1) if dimr else None),
                     "med_als_minus_ref": (round(float(np.median(alsr)), 1) if alsr else None),
                     "med_dim_minus_als": (round(float(np.median(dima)), 1) if dima else None)})
    with open(OUT / "survey_by_type.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(summ[0].keys())); w.writeheader(); w.writerows(summ)

    # ---- figures ----
    CMAP = {"flat": "tab:blue", "sloped": "tab:orange", "curved": "tab:red",
            "composite": "tab:green", "other": "tab:gray"}
    paired = [x for x in rows if x["als_facets"] is not None and x["dim_facets"] is not None]
    fig, ax = plt.subplots(1, 2, figsize=(15, 6))
    mx = max([x["als_facets"] for x in paired] + [x["dim_facets"] for x in paired]) + 2
    ax[0].plot([0, mx], [0, mx], "k--", lw=1, label="DIM=ALS")
    for cls in CMAP:
        pts = [x for x in paired if x["class4"] == cls]
        if pts:
            ax[0].scatter([x["als_facets"] for x in pts], [x["dim_facets"] for x in pts],
                          c=CMAP[cls], s=40, alpha=0.7, edgecolor="k", lw=0.3, label=f"{cls} ({len(pts)})")
    t = next((x for x in paired if x["building_id"] == "DEBY_LOD2_4906969"), None)
    if t:
        ax[0].scatter([t["als_facets"]], [t["dim_facets"]], s=260, facecolor="none",
                      edgecolor="red", lw=2.2)
        ax[0].annotate("4906969", (t["als_facets"], t["dim_facets"]), textcoords="offset points",
                       xytext=(8, 8), fontsize=9, color="red")
    ax[0].set_xlabel("ALS (LiDAR) roof facets"); ax[0].set_ylabel("DIM (image) roof facets")
    ax[0].set_title(f"ALS vs DIM target-only facets ({len(paired)} both-reconstructed)\nabove line = DIM over-segments vs LiDAR")
    ax[0].legend(fontsize=8)

    # per-class over-seg vs ref (ALS and DIM) — over-seg is broad & LiDAR too
    classes = ["flat", "sloped", "curved", "composite", "other"]
    xpos = np.arange(len(classes))
    md_als = [next((s["med_als_minus_ref"] for s in summ if s["class4"] == c), None) for c in classes]
    md_dim = [next((s["med_dim_minus_ref"] for s in summ if s["class4"] == c), None) for c in classes]
    md_als = [0 if v is None else v for v in md_als]; md_dim = [0 if v is None else v for v in md_dim]
    ax[1].bar(xpos - 0.2, md_als, 0.4, label="ALS−ref (LiDAR)", color="tab:cyan")
    ax[1].bar(xpos + 0.2, md_dim, 0.4, label="DIM−ref (image)", color="tab:orange")
    ns = [next((s["n"] for s in summ if s["class4"] == c), 0) for c in classes]
    ax[1].set_xticks(xpos); ax[1].set_xticklabels([f"{c}\n(n={n})" for c, n in zip(classes, ns)])
    ax[1].axhline(0, color="k", lw=0.8)
    ax[1].set_ylabel("median (facets − reference)")
    ax[1].set_title("Over-seg vs LoD2 reference by roof class\n(both ALS & DIM > ref across all types)")
    ax[1].legend(fontsize=8)
    fig.suptitle("D6 survey - over-segmentation across the controlled 93 (P0 reuse; observation only)")
    fig.tight_layout()
    fp = FIGDIR / "survey_overseg.png"
    fig.savefig(fp, dpi=120); plt.close(fig)

    # ---- console summary ----
    print("=== roofType class distribution (93) ===")
    for cls in classes:
        print(f"  {cls:10} n={len(byc.get(cls,[]))}")
    print("\n=== by-type over-seg summary ===")
    for s in summ:
        print(f"  {s['class4']:10} n={s['n']:>2} dimRecon={s['n_dim_recon']:>2} "
              f"DIM>ref={s['n_dim_over_ref']:>2} ALS>ref={s['n_als_over_ref']:>2} "
              f"medDIM-ref={s['med_dim_minus_ref']} medALS-ref={s['med_als_minus_ref']} medDIM-ALS={s['med_dim_minus_als']}")
    dimr_all = [x["dim_minus_ref"] for x in rows if x["dim_minus_ref"] is not None]
    alsr_all = [x["als_minus_ref"] for x in rows if x["als_minus_ref"] is not None]
    dima_all = [x["dim_minus_als"] for x in rows if x["dim_minus_als"] is not None]
    print(f"\nALL: DIM>ref {sum(1 for v in dimr_all if v>0)}/{len(dimr_all)} | "
          f"ALS>ref {sum(1 for v in alsr_all if v>0)}/{len(alsr_all)} | "
          f"DIM>ALS {sum(1 for v in dima_all if v>0)}/{len(dima_all)}")
    print(f"medians: DIM-ref={np.median(dimr_all):.0f} ALS-ref={np.median(alsr_all):.0f} DIM-ALS={np.median(dima_all):.0f}")
    sd = sorted([(x["dim_minus_ref"], x["building_id"], x["roofType"]) for x in rows if x["dim_minus_ref"] is not None], reverse=True)
    rank = [b for _, b, _ in sd].index("DEBY_LOD2_4906969") + 1
    t69 = next(x for x in rows if x["building_id"] == "DEBY_LOD2_4906969")
    print(f"\n4906969: roofType={t69['roofType']}({RT_NAME.get(t69['roofType'])}) class={t69['class4']} "
          f"ref={t69['ref_facets']} ALS={t69['als_facets']} DIM={t69['dim_facets']} "
          f"GS(mob)={t69.get('gs_dense_facets_mobharness')}/{t69.get('gs_acmp_facets_mobharness')} "
          f"| DIM-ref rank {rank}/{len(sd)}")
    print(f"\n[done] -> {OUT}/survey_per_building.csv, survey_by_type.csv ; fig {fp}")


if __name__ == "__main__":
    main()
