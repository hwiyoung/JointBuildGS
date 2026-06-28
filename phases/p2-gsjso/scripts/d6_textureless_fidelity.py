#!/usr/bin/env python3
"""P2-D6 textureless fidelity — do the 4 GS-assembled textureless buildings MATCH the real roof
(faithful) or are they plausible guesses (flat slab at a guessed height)? P0/D-suite reuse, NO retrain.

Buildings: 42364609, 4908050, 4908166 (Flachdach=flat) + 4907182 (Pultdach 2100=shed, the guess-fill
test: did GS keep the pitch or flatten it?). For each: GS-JSO(D4) roof vs ALS(LiDAR) roof vs reference
LoD2 — height (GS roof-z vs ALS roof-z, ellipsoidal; + ref ortho via per-bldg geoid), shape (roof
top-envelope local slope + planarity RMS), existing RMS→ref / facets / valid / DIM-evidence.

Runs in jointbuildgs-p0-tools:t0 (numpy/laspy/matplotlib; no scipy). EPSG:25832. Observation only.
Out: results/.../analysis_pack_d6/textureless_fidelity.csv + docs/figs/W_D6_textureless/<bid>.png
"""
import csv, glob, json, sys
from pathlib import Path
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, "/workspace/JointBuildGS/phases/p2-gsjso/scripts")
from d6_shape_audit import (footprint_paths, read_cloud, roof_envelope, gml_building,
                            cell_normals, draw_ref)

REPO = Path("/workspace/JointBuildGS")
M = REPO / "results/tum_transfer/mob"
OUT = M / "analysis_pack_d6"
FIG = REPO / "docs/figs/W_D6_textureless"
BLD = [("42364609", "flat"), ("4908050", "flat"), ("4908166", "flat"), ("4907182", "shed(2100)")]


def env_stats(P_all):
    """roof top-envelope: median z (ellipsoidal), local cell-slope median, planarity RMS, n."""
    if P_all is None or len(P_all) < 12:
        return None
    P = roof_envelope(P_all)
    medz = float(np.median(P[:, 2]))
    nrm = cell_normals(P)
    slope = float(np.median(np.degrees(np.arccos(np.clip(np.abs(nrm[:, 2]), 0, 1))))) if len(nrm) else None
    c = P.mean(0); _, _, Vt = np.linalg.svd(P - c, full_matrices=False)
    prms = float(np.sqrt((((P - c) @ Vt[-1]) ** 2).mean()))
    return {"medz": medz, "slope": slope, "prms": prms, "n": len(P)}


def load_refrms():
    out = {}
    for f, arms in [("ref_rms_d4_gssem.csv", {"gs_d4_dense": "GS"}),
                    ("ref_rms_raw.csv", {"raw_lidar": "ALS", "raw_dense": "DIM"})]:
        for r in csv.DictReader(open(REPO / "results/tum_transfer/mob_analysis" / f)):
            if r.get("tag") != "orig":
                continue
            lab = arms.get(r["config"])
            if lab:
                out.setdefault(r["bid"].replace("DEBY_LOD2_", ""), {})[lab] = (r["rms_to_ref_m"], r["dz_m"])
    return out


def gen_status():
    return {r["bid"]: r for r in csv.DictReader(open(OUT / "gen_status.csv"))}


def panel(bid, kind, gs, als, roof):
    FIG.mkdir(parents=True, exist_ok=True)
    fig = plt.figure(figsize=(14, 8))
    cols = [("GS-JSO(D4)", gs), ("ALS(LiDAR)", als), ("ref LoD2", None)]
    for ci, (name, P) in enumerate(cols):
        axt = fig.add_subplot(2, 3, ci + 1)
        axo = fig.add_subplot(2, 3, ci + 4, projection="3d")
        if name == "ref LoD2":
            draw_ref(axt, roof, [], False, "ref roof (colored)")
            draw_ref(axo, roof, [], True, "ref oblique")
        else:
            E = roof_envelope(P) if P is not None and len(P) else P
            for ax, ob in [(axt, False), (axo, True)]:
                if E is None or len(E) == 0:
                    ax.text(0.5, 0.5, "0", ha="center"); ax.set_axis_off(); continue
                if ob:
                    ax.scatter(E[:, 0], E[:, 1], E[:, 2], c=E[:, 2], cmap="viridis", s=4)
                    ax.set_box_aspect((1, 1, 0.4)); ax.view_init(22, -60)
                    ax.set_xticks([]); ax.set_yticks([]); ax.set_zticks([])
                else:
                    ax.scatter(E[:, 0], E[:, 1], c=E[:, 2], cmap="viridis", s=8); ax.set_aspect("equal"); ax.set_axis_off()
            axt.set_title(f"{name} roof-env top (n={len(E)})", fontsize=8)
            axo.set_title(f"{name} oblique", fontsize=8)
    fig.suptitle(f"D6 textureless fidelity {bid} ({kind})", fontsize=10)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fp = FIG / f"{bid}.png"; fig.savefig(fp, dpi=100); plt.close(fig); return fp


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rr = load_refrms(); gs_stat = gen_status()
    rows = []
    for bid, kind in BLD:
        paths = footprint_paths(bid)
        gs = read_cloud("gs_d4_dense", bid, paths)
        als = read_cloud("raw_lidar", bid, paths)
        rt, roof, wall = gml_building(bid)
        es_gs, es_als = env_stats(gs), env_stats(als)
        ref_z = float(np.mean([r[:, 2].mean() for r in roof])) if roof else None
        # height: GS vs ALS roof-env median z (both ellipsoidal -> direct diff). geoid = ALS_ellip - ref_ortho.
        h_gs = es_gs["medz"] if es_gs else None
        h_als = es_als["medz"] if es_als else None
        geoid = (h_als - ref_z) if (h_als is not None and ref_z is not None) else None
        gs_minus_als = (h_gs - h_als) if (h_gs is not None and h_als is not None) else None
        g = gs_stat.get(bid, {})
        rrb = rr.get(bid, {})
        row = {"bid": bid, "kind": kind, "roofType": rt, "ref_z_ortho": round(ref_z, 2) if ref_z else None,
               "GS_roofz_ellip": round(h_gs, 2) if h_gs else None,
               "ALS_roofz_ellip": round(h_als, 2) if h_als else None,
               "GS_minus_ALS_z_m": round(gs_minus_als, 2) if gs_minus_als is not None else None,
               "geoid_m(ALS-ref)": round(geoid, 2) if geoid else None,
               "GS_localslope_deg": round(es_gs["slope"], 1) if es_gs and es_gs["slope"] is not None else None,
               "ALS_localslope_deg": round(es_als["slope"], 1) if es_als and es_als["slope"] is not None else None,
               "GS_planeRMS": round(es_gs["prms"], 3) if es_gs else None,
               "ALS_planeRMS": round(es_als["prms"], 3) if es_als else None,
               "GS_rms_to_ref": rrb.get("GS", (None,))[0], "ALS_rms_to_ref": rrb.get("ALS", (None,))[0],
               "GS_facets": g.get("GS_facets"), "ALS_facets": g.get("ALS_facets"), "ref_facets": g.get("ref_facets"),
               "GS_valid": g.get("GS_valid"), "ALS_valid": g.get("ALS_valid"),
               "DIM_class6_pts": g.get("DIM_class6_pts")}
        fp = panel(bid, kind, gs, als, roof)
        rows.append(row)
        print(f"{bid} {kind:10} rt={rt} | GS_z {row['GS_roofz_ellip']} ALS_z {row['ALS_roofz_ellip']} "
              f"GS-ALS {row['GS_minus_ALS_z_m']}m | slope GS {row['GS_localslope_deg']} ALS {row['ALS_localslope_deg']} "
              f"| planeRMS GS {row['GS_planeRMS']} ALS {row['ALS_planeRMS']} | rms2ref GS {row['GS_rms_to_ref']} ALS {row['ALS_rms_to_ref']} "
              f"| facets GS {row['GS_facets']}/ALS {row['ALS_facets']}/ref {row['ref_facets']} | DIM {row['DIM_class6_pts']} -> {fp.name}")
    with open(OUT / "textureless_fidelity.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    print(f"\n[done] -> {OUT}/textureless_fidelity.csv ; figs {FIG}/")


if __name__ == "__main__":
    main()
