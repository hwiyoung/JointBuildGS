#!/usr/bin/env python3
"""P2 assembly-fidelity — raw MVS FAILED to assemble 3 buildings (42364659, 42364663, 4907510) but
GS-JSO(D4) assembled them. "Assembled != faithful": is the GS model as faithful as ALS(LiDAR) — in
HEIGHT, SHAPE, FACET-count, RMS->ref, CLOSED-ness — or did GS just fill a plausible guess? P0/D-suite
REUSE, NO retrain / NO reconstruction. Observation only; verdict = 김휘영.

Targets (R: DIM-Roofer failed -> GS assembled): 42364659, 42364663, 4907510.
Contrast: 4906972, 4908023 (faithful baseline = DIM also assembled), 4906969 (context).

Per building, all from EXISTING disk artifacts:
  - height : GS vs ALS roof top-envelope, ELLIPSOIDAL. We report BOTH the median AND the p95 RIDGE-top,
             because two of the three targets have BIMODAL footprints (a low + a tall level that the
             ref LoD2 collapses): there the single median lands on whichever cluster has more points,
             so |GS-ALS median| is a metric artifact while the ridge-top (p95) is the like-for-like
             height. ALS-failed-solid building 42364659 also vs ref_ortho + median geoid.
  - shape  : roof top-envelope local cell-slope + z-levels (measure_shape) for GS and ALS, vs ref.
  - facets : GS / ALS / ref target-only RoofSurface count (gen_status, recomputed from current disk).
  - RMS->ref : full class6 (ref_rms_*.csv, orig tag) AND a FACADE-REMOVED roof-envelope RMS recomputed
             here with the SAME 1-DOF dz-aligned point-to-nearest-ref-plane metric (tum_mob_ref_rms).
             The full-cloud RMS is facade-dominated (class6 = whole envelope incl walls) and is NOT a
             clean roof-shape discriminator; the roof-env RMS is, and is reported for EVERY arm/row.
  - closed : TARGET-ONLY (neighbour-removed) closed-2-manifold status on the Roofer Solid shell (every
             edge shared by exactly 2 faces): closed / open / no-solid / no-roofer. clip-level val3dity
             kept as context (gen_status) — it is CLIP-level (incl. neighbours), a different thing.
  - completeness : fraction of 1m footprint cells covered by roof points (GS/ALS/DIM). COVERAGE, NOT
             fidelity — ~1 by construction for any dense cloud; only separates SPARSE clouds.

Runs in jointbuildgs-p0-tools:t0 (numpy/laspy/matplotlib; no scipy). EPSG:25832.
Out: results/.../analysis_pack_d6/assembly_fidelity.csv + docs/figs/W_assembly/<bid>.png
"""
import csv, glob, json, sys
from collections import Counter
from pathlib import Path
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))
from scripts.evidence_and_attributes.geometry_fidelity.d6_shape_audit import (footprint_paths, read_cloud, roof_envelope, gml_building,
                            cell_normals, draw_ref, measure_shape, EVAL)

REPO = Path("/workspace/JointBuildGS")
M = REPO / "results/tum_transfer/mob"
OUT = M / "analysis_pack_d6"
FIG = REPO / "docs/figs/W_assembly"
# (bid, set, note) — R = raw MVS could not assemble but GS-JSO did; Q = contrast
BLD = [("42364659", "R-target", "단차 footprint(저+고), ALS-solid도 실패"),
       ("42364663", "R-target", "DIM 96k점이나 미조립(단봉 ridge)"),
       ("4907510", "R-target", "단차 footprint(주지붕+하부)"),
       ("4906972", "Q-faithful", "충실 기준선 박공(DIM도 조립)"),
       ("4908023", "Q-faithful", "충실 기준선 평(DIM도 조립)"),
       ("4906969", "Q-context", "맥락(단차 평지붕)")]


def env_stats(P_all):
    """roof top-envelope: median z, p95 RIDGE-top z, p05 base z (ellipsoidal), local cell-slope, RMS, n."""
    if P_all is None or len(P_all) < 12:
        return None
    P = roof_envelope(P_all)
    z = P[:, 2]
    nrm = cell_normals(P)
    slope = float(np.median(np.degrees(np.arccos(np.clip(np.abs(nrm[:, 2]), 0, 1))))) if len(nrm) else None
    c = P.mean(0); _, _, Vt = np.linalg.svd(P - c, full_matrices=False)
    prms = float(np.sqrt((((P - c) @ Vt[-1]) ** 2).mean()))
    return {"medz": float(np.median(z)), "ridgez": float(np.percentile(z, 95)),
            "basez": float(np.percentile(z, 5)), "slope": slope, "prms": prms, "n": len(P)}


# ---- facade-removed roof RMS->ref (same metric as tum_mob_ref_rms, on roof-envelope only) ----
def fit_plane(ring):
    cc = ring.mean(0); _, _, Vt = np.linalg.svd(ring - cc, full_matrices=False)
    n = Vt[-1]; return n / (np.linalg.norm(n) + 1e-12), cc


def ref_planes(roof):
    pl = []
    for a in roof:
        r = a[:-1] if (len(a) >= 2 and np.allclose(a[0], a[-1])) else a
        if len(r) >= 3:
            pl.append(fit_plane(r))
    return pl


def aligned_rms(P, planes):
    """1-DOF vertical-aligned point-to-nearest-ref-plane RMS (geoid + uniform bias removed)."""
    if P is None or len(P) < 10 or not planes:
        return None
    best = np.inf
    for dz in np.arange(40.0, 56.0, 0.25):
        Q = P.copy(); Q[:, 2] -= dz
        d = np.full(len(Q), np.inf)
        for n, cc in planes:
            d = np.minimum(d, np.abs((Q - cc) @ n))
        best = min(best, float(np.sqrt((d ** 2).mean())))
    return round(best, 3)


def roofenv_rms(P_all, planes):
    if P_all is None or len(P_all) == 0:
        return None
    return aligned_rms(roof_envelope(P_all), planes)


def completeness(P_all, paths, cell=1.0):
    """COVERAGE: fraction of footprint 1m cells with roof points (NOT fidelity; ~1 for dense clouds)."""
    if not paths:
        return None
    xs, ys = [], []
    for p in paths:
        v = p.vertices
        xs += [v[:, 0].min(), v[:, 0].max()]; ys += [v[:, 1].min(), v[:, 1].max()]
    gx = np.arange(np.floor(min(xs) / cell), np.ceil(max(xs) / cell) + 1) * cell + cell / 2
    gy = np.arange(np.floor(min(ys) / cell), np.ceil(max(ys) / cell) + 1) * cell + cell / 2
    XX, YY = np.meshgrid(gx, gy)
    C = np.column_stack([XX.ravel(), YY.ravel()])
    inF = np.zeros(len(C), bool)
    for p in paths:
        inF |= p.contains_points(C)
    Fcells = {(int(np.floor(c[0] / cell)), int(np.floor(c[1] / cell))) for c in C[inF]}
    if not Fcells:
        return None
    if P_all is None or len(P_all) == 0:
        return 0.0
    E = roof_envelope(P_all)
    occ = {(int(np.floor(x / cell)), int(np.floor(y / cell))) for x, y in E[:, :2]}
    return round(len(Fcells & occ) / len(Fcells), 3)


def target_faces(arm, bid):
    """outer-ring vertex-index loops of the TARGET Solid only (neighbour-free). None=no roofer output."""
    full = f"DEBY_LOD2_{bid}"
    g = glob.glob(str(EVAL / arm / f"roofer_{full}_orig" / "*.city.jsonl"))
    if not g:
        return None
    faces = []
    for ln in open(g[0]):
        if not ln.strip():
            continue
        d = json.loads(ln)
        for cid, o in d.get("CityObjects", {}).items():
            if not (cid == full or cid.startswith(full + "-")):
                continue
            for gm in o.get("geometry", []):
                if gm.get("type") != "Solid":
                    continue
                for shell in gm.get("boundaries", []):
                    for face in shell:
                        if face and face[0] and len(face[0]) >= 3:
                            faces.append([int(v) for v in face[0]])
    return faces


def closed_status(faces):
    """target-only shell: closed (2-manifold) / open (non-manifold edges) / no-solid / no-roofer.
    Outer-ring-only (fine for hole-free LoD2 building shells)."""
    if faces is None:
        return {"status": "no-roofer", "n_faces": None, "nonman": None}
    nf = len(faces)
    if nf == 0:
        return {"status": "no-solid", "n_faces": 0, "nonman": None}
    ec = Counter()
    for f in faces:
        m = len(f)
        for i in range(m):
            a, b = f[i], f[(i + 1) % m]
            if a != b:
                ec[(min(a, b), max(a, b))] += 1
    nonman = sum(1 for cnt in ec.values() if cnt != 2)
    return {"status": "closed" if (nf >= 4 and nonman == 0) else "open", "n_faces": nf, "nonman": nonman}


def load_refrms():
    """full-class6 rms_to_ref_m for GS / ALS / DIM (orig tag), per bid."""
    out = {}
    for f, arms in [("ref_rms_d4_gssem.csv", {"gs_d4_dense": "GS"}),
                    ("ref_rms_raw.csv", {"raw_lidar": "ALS", "raw_dense": "DIM"})]:
        for r in csv.DictReader(open(REPO / "results/tum_transfer/mob_analysis" / f)):
            if r.get("tag") != "orig":
                continue
            lab = arms.get(r["config"])
            if lab:
                out.setdefault(r["bid"].replace("DEBY_LOD2_", ""), {})[lab] = r["rms_to_ref_m"]
    return out


def gen_status():
    return {r["bid"]: r for r in csv.DictReader(open(OUT / "gen_status.csv"))}


def panel(bid, tag, gs, als, roof, cap):
    FIG.mkdir(parents=True, exist_ok=True)
    fig = plt.figure(figsize=(14, 8.4))
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
    fig.suptitle(f"assembly fidelity {bid} ({tag})\n{cap}", fontsize=9)
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    fp = FIG / f"{bid}.png"; fig.savefig(fp, dpi=100); plt.close(fig); return fp


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rr = load_refrms(); gs_stat = gen_status()
    cache = {}
    for bid, tag, note in BLD:
        paths = footprint_paths(bid)
        gs = read_cloud("gs_d4_dense", bid, paths)
        als = read_cloud("raw_lidar", bid, paths)
        dim = read_cloud("raw_dense", bid, paths)
        rt, roof, wall = gml_building(bid)
        cache[bid] = dict(paths=paths, gs=gs, als=als, dim=dim, rt=rt, roof=roof,
                          es_gs=env_stats(gs), es_als=env_stats(als),
                          ref_z=(float(np.mean([r[:, 2].mean() for r in roof])) if roof else None),
                          planes=ref_planes(roof),
                          als_n=(0 if als is None else len(als)))  # pre-envelope class6-in-fp roof count
    # geoid = ALS_envz - ref_ortho, median over buildings with >=600 pre-envelope ALS roof pts
    geoids = [cache[b]["es_als"]["medz"] - cache[b]["ref_z"] for b in cache
              if cache[b]["es_als"] and cache[b]["ref_z"] is not None and cache[b]["als_n"] >= 600]
    geoid_med = float(np.median(geoids)) if geoids else None
    print(f"[geoid] per-bldg(ALS-ref) over >=600-pt ALS: {[round(g,2) for g in geoids]} median={geoid_med}")

    rows = []
    for bid, tag, note in BLD:
        c = cache[bid]
        es_gs, es_als, ref_z = c["es_gs"], c["es_als"], c["ref_z"]
        h_gs = es_gs["medz"] if es_gs else None
        h_als = es_als["medz"] if es_als else None
        r_gs = es_gs["ridgez"] if es_gs else None
        r_als = es_als["ridgez"] if es_als else None
        gs_minus_als = (h_gs - h_als) if (h_gs is not None and h_als is not None) else None
        ridge_diff = (r_gs - r_als) if (r_gs is not None and r_als is not None) else None
        geoid = (h_als - ref_z) if (h_als is not None and ref_z is not None) else None
        gs_vs_refgeoid = (h_gs - (ref_z + geoid_med)) if (h_gs is not None and ref_z is not None
                                                          and geoid_med is not None) else None
        sh_gs = measure_shape(c["gs"]); sh_als = measure_shape(c["als"])
        cl_gs = closed_status(target_faces("gs_d4_dense", bid))
        cl_als = closed_status(target_faces("raw_lidar", bid))
        cl_dim = closed_status(target_faces("raw_dense", bid))
        rmse_gs = roofenv_rms(c["gs"], c["planes"]); rmse_als = roofenv_rms(c["als"], c["planes"])
        rmse_dim = roofenv_rms(c["dim"], c["planes"])
        g = gs_stat.get(bid, {}); rrb = rr.get(bid, {})
        # bimodal-artifact flag: single-median height vs ridge-top height tell materially different
        # stories (multi-level footprint -> the median lands on whichever cluster has more points).
        bim = (gs_minus_als is not None and ridge_diff is not None
               and abs(gs_minus_als - ridge_diff) > 2.0)
        row = {"bid": bid, "set": tag, "note": note, "roofType": c["rt"],
               "ref_z_ortho": round(ref_z, 2) if ref_z else None,
               "GS_medz_ellip": round(h_gs, 2) if h_gs is not None else None,
               "ALS_medz_ellip": round(h_als, 2) if h_als is not None else None,
               "GS_minus_ALS_med_m": round(gs_minus_als, 2) if gs_minus_als is not None else None,
               "GS_ridgez_ellip": round(r_gs, 2) if r_gs is not None else None,
               "ALS_ridgez_ellip": round(r_als, 2) if r_als is not None else None,
               "GS_minus_ALS_ridge_m": round(ridge_diff, 2) if ridge_diff is not None else None,
               "bimodal_med_artifact": bim,
               "GS_vs_ref+geoidMed_m": round(gs_vs_refgeoid, 2) if gs_vs_refgeoid is not None else None,
               "geoid_m(ALS-ref)": round(geoid, 2) if geoid is not None else None,
               "GS_slope_deg": sh_gs.get("local_slope_deg"), "ALS_slope_deg": sh_als.get("local_slope_deg"),
               "GS_zlevels": sh_gs.get("n_zlevel"), "ALS_zlevels": sh_als.get("n_zlevel"),
               "GS_shape": sh_gs.get("verdict"), "ALS_shape": sh_als.get("verdict"),
               "GS_rms2ref_full": rrb.get("GS"), "ALS_rms2ref_full": rrb.get("ALS"), "DIM_rms2ref_full": rrb.get("DIM"),
               "GS_roofenvRMS": rmse_gs, "ALS_roofenvRMS": rmse_als, "DIM_roofenvRMS": rmse_dim,
               "GS_facets": g.get("GS_facets"), "ALS_facets": g.get("ALS_facets"), "ref_facets": g.get("ref_facets"),
               "GS_closed_tgt": cl_gs["status"], "ALS_closed_tgt": cl_als["status"], "DIM_closed_tgt": cl_dim["status"],
               "GS_nfaces": cl_gs["n_faces"], "ALS_nfaces": cl_als["n_faces"],
               "GS_valid_clip": g.get("GS_valid"), "ALS_valid_clip": g.get("ALS_valid"), "DIM_valid_clip": g.get("DIM_valid"),
               "GS_complete": completeness(c["gs"], c["paths"]), "ALS_complete": completeness(c["als"], c["paths"]),
               "DIM_complete": completeness(c["dim"], c["paths"]),
               "DIM_class6_pts": g.get("DIM_class6_pts")}
        cap = (f"med G-A {row['GS_minus_ALS_med_m']}m / ridge G-A {row['GS_minus_ALS_ridge_m']}m"
               f"{' [bimodal med-artifact]' if bim else ''} | facets G{row['GS_facets']}/A{row['ALS_facets']}/ref{row['ref_facets']} | "
               f"closed(tgt) G:{cl_gs['status']}/A:{cl_als['status']} | roofRMS->ref G{rmse_gs}/A{rmse_als} (full G{row['GS_rms2ref_full']}/A{row['ALS_rms2ref_full']})")
        fp = panel(bid, tag, c["gs"], c["als"], c["roof"], cap)
        rows.append(row)
        print(f"{bid} {tag:11} rt={c['rt']} | medz G{row['GS_medz_ellip']}/A{row['ALS_medz_ellip']} "
              f"med-d {row['GS_minus_ALS_med_m']} | ridge G{row['GS_ridgez_ellip']}/A{row['ALS_ridgez_ellip']} "
              f"ridge-d {row['GS_minus_ALS_ridge_m']}{' BIMODAL' if bim else ''} | "
              f"slope G{row['GS_slope_deg']}/A{row['ALS_slope_deg']} zlv G{row['GS_zlevels']}/A{row['ALS_zlevels']} | "
              f"fac G{row['GS_facets']}/A{row['ALS_facets']}/r{row['ref_facets']} | "
              f"closed G:{cl_gs['status']}({cl_gs['n_faces']}f)/A:{cl_als['status']} | "
              f"roofRMS G{rmse_gs}/A{rmse_als}/D{rmse_dim} (full G{row['GS_rms2ref_full']}/A{row['ALS_rms2ref_full']}) | "
              f"compl G{row['GS_complete']}/A{row['ALS_complete']} | DIMpts {row['DIM_class6_pts']} -> {fp.name}")
    with open(OUT / "assembly_fidelity.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    print(f"\n[done] -> {OUT}/assembly_fidelity.csv ; figs {FIG}/ ; geoid_med={geoid_med}")


if __name__ == "__main__":
    main()
