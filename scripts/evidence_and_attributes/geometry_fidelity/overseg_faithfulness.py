#!/usr/bin/env python3
"""P2 overseg-faithfulness diag — are GS's extra roof facets a DEFECT (over-seg) or FAITHFUL structure
ALS missed? Phase A showed post-process matches ALS facet COUNT only by collapsing 1.8-3.4m real steps.
Crux: register each GS roof face to the RAW ALS point cloud (not the ALS model) and ask, per face,
"is this height a REAL level the ALS points support, or is it floating?". NO retrain / NO reconstruction.
Observation only; verdict = 김휘영. EPSG:25832. ALS & GS clouds both ELLIPSOIDAL (direct vertical compare).

Per GS roof face: ALS class-6 points whose xy fall inside the face polygon; vertical residual ALS_z −
GS_face_plane(xy). face is ALS-SUPPORTED (real level) if it has enough ALS points AND they sit near its
plane (median|resid| < TOL); else FLOATING/UNSUPPORTED. Plus: GS distinct height-LEVELS via a step-aware
merge (normal-align AND |Δz|<merge_d_tol=0.5m = the cp/g2 grouping tolerance — does NOT cross real steps)
vs ALS levels vs ref levels -> separates "within-level fragmentation (heights right, defect=mergeable)"
from "extra real levels (faithful)" from "floating faces (fabricated)".

Out: results/.../overseg_lever/faithfulness.csv + faithfulness_faces_<bid>.csv + docs/figs/W_faithful/<bid>.png
"""
import csv, glob, json, sys
from collections import defaultdict
from pathlib import Path
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.path import Path as MplPath

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))
from scripts.evidence_and_attributes.geometry_fidelity.d6_shape_audit import footprint_paths, read_cloud, roof_envelope, gml_building
from scripts.evidence_and_attributes.geometry_fidelity.assembly_fidelity import fit_plane
from scripts.evidence_and_attributes.geometry_fidelity.overseg_analysis import parse_solid_roof

REPO = Path("/workspace/JointBuildGS")
LEV = REPO / "results/tum_transfer/mob/overseg_lever"
FIG = REPO / "docs/figs/W_faithful"
BLD = [("4906969", "단차평 stepped-flat"), ("42364659", "단차 stepped"),
       ("4907510", "대조 경사 sloped-ctrl"), ("4906972", "단순 박공 gable-simple")]
TOL = 0.5      # m, ALS-support vertical tolerance (= cp/g2 merge_d_tol)
MIN_ALS = 5    # min ALS pts under a face to judge support
GEOID = 48.165 # ellip - geoid = ortho (for readability)


def z_levels(zvals, sep=0.6, minfrac=0.06):
    """distinct height levels = histogram modes >= minfrac pop, merged within `sep` m."""
    if zvals is None or len(zvals) < 10:
        return []
    z = np.asarray(zvals); span = float(z.max() - z.min())
    nb = max(8, int(span / 0.3))
    hist, edges = np.histogram(z, bins=nb); cen = 0.5 * (edges[:-1] + edges[1:])
    peaks = sorted([(hist[i], cen[i]) for i in range(1, len(hist) - 1)
                    if hist[i] >= minfrac * len(z) and hist[i] >= hist[i - 1] and hist[i] >= hist[i + 1]],
                   key=lambda t: -t[0])
    lv = []
    for _, zc in peaks:
        if not any(abs(zc - l) < sep for l in lv):
            lv.append(zc)
    return sorted(lv)


def step_aware_levels(roof_faces, V, ncos=0.92, dtol=TOL):
    """GS distinct levels = connected components of roof faces under (normal-align AND |Δz_perp|<dtol AND
    xy-overlap). Mirrors the cp/g2 grouping: cannot cross a real step (Δz>dtol)."""
    planes = [fit_plane(V[r]) for r in roof_faces]
    polys = [MplPath(V[r][:, :2]) for r in roof_faces]
    cz = [float(V[r][:, 2].mean()) for r in roof_faces]
    nf = len(roof_faces)
    par = list(range(nf))
    def find(x):
        while par[x] != x:
            par[x] = par[par[x]]; x = par[x]
        return x
    def overlap(i, j):  # xy bbox overlap (cheap adjacency proxy)
        a, b = V[roof_faces[i]][:, :2], V[roof_faces[j]][:, :2]
        return not (a[:, 0].max() < b[:, 0].min() or b[:, 0].max() < a[:, 0].min()
                    or a[:, 1].max() < b[:, 1].min() or b[:, 1].max() < a[:, 1].min())
    for i in range(nf):
        for j in range(i + 1, nf):
            ni, ci = planes[i]; nj, cj = planes[j]
            if abs(float(ni @ nj)) <= ncos:
                continue
            dc = cj - ci; navg = ni + (nj if ni @ nj >= 0 else -nj); navg /= (np.linalg.norm(navg) + 1e-12)
            if abs(float(dc @ navg)) >= dtol:   # different height level -> never merge
                continue
            if overlap(i, j):
                par[find(i)] = find(j)
    comp = defaultdict(list)
    for i in range(nf):
        comp[find(i)].append(i)
    # level z = mean centroid-z per component
    return [float(np.mean([cz[i] for i in cl])) for cl in comp.values()], comp


def face_support(roof_faces, V, als, dz=0.0):
    """per face: n_ALS under it, median residual (ALS_z - dz) - face_plane(xy), supported bool.
    `dz` removes the known global GS<ALS vertical offset (assembly-fidelity ~1.7m) so the test measures
    RELATIVE structure (is this a real local level) not the absolute height bias."""
    out = []
    for r in roof_faces:
        n, c = fit_plane(V[r])
        poly = MplPath(V[r][:, :2])
        if als is None or len(als) == 0:
            out.append({"n_als": 0, "resid_med": None, "resid_abs": None, "supported": False}); continue
        m = poly.contains_points(als[:, :2])
        Q = als[m]
        if len(Q) < MIN_ALS:
            out.append({"n_als": int(len(Q)), "resid_med": None, "resid_abs": None, "supported": False}); continue
        nz = n[2] if abs(n[2]) > 1e-6 else 1e-6
        zf = (float(n @ c) - n[0] * Q[:, 0] - n[1] * Q[:, 1]) / nz   # face plane z at ALS xy
        resid = (Q[:, 2] - dz) - zf                                  # dz-aligned
        rmed = float(np.median(resid)); rabs = float(np.median(np.abs(resid)))
        out.append({"n_als": int(len(Q)), "resid_med": round(rmed, 2), "resid_abs": round(rabs, 2),
                    "supported": bool(rabs < TOL), "face_z": round(float(V[r][:, 2].mean()), 2)})
    return out


def panel(bid, kind, roof_faces, V, als, lv_gs, lv_als, lv_ref, sup):
    FIG.mkdir(parents=True, exist_ok=True)
    fig = plt.figure(figsize=(15, 5.2))
    cz_all = np.concatenate([V[r][:, 2] for r in roof_faces]) if roof_faces else np.array([0, 1])
    vmin, vmax = float(cz_all.min()), float(cz_all.max())
    # (1) GS faces colored by height (top)
    ax = fig.add_subplot(1, 3, 1)
    import matplotlib.cm as cm; sm = cm.ScalarMappable(cmap="viridis"); sm.set_clim(vmin, vmax)
    for i, r in enumerate(roof_faces):
        poly = V[r][:, :2]; zc = float(V[r][:, 2].mean())
        ax.fill(poly[:, 0], poly[:, 1], color=sm.to_rgba(zc), alpha=0.85,
                edgecolor=("k" if sup[i]["supported"] else "red"), lw=(0.4 if sup[i]["supported"] else 1.4))
    ax.set_aspect("equal"); ax.set_axis_off()
    ax.set_title(f"GS {len(roof_faces)} faces (height-colored; RED edge=ALS-unsupported)", fontsize=8)
    # (2) ALS points colored by height (top)
    ax2 = fig.add_subplot(1, 3, 2)
    if als is not None and len(als):
        E = roof_envelope(als)
        ax2.scatter(E[:, 0], E[:, 1], c=E[:, 2], cmap="viridis", s=6, vmin=vmin, vmax=vmax)
    ax2.set_aspect("equal"); ax2.set_axis_off(); ax2.set_title(f"raw ALS roof pts (n={0 if als is None else len(als)})", fontsize=8)
    # (3) height histogram: ALS pts + GS levels + ref levels
    ax3 = fig.add_subplot(1, 3, 3)
    if als is not None and len(als):
        E = roof_envelope(als)
        ax3.hist(E[:, 2] - GEOID, bins=40, color="lightgray", label="ALS pts z (ortho)")
    for l in lv_gs:
        ax3.axvline(l - GEOID, color="tab:blue", lw=1.6, alpha=0.7)
    for l in lv_ref:                      # ref GML already ortho
        ax3.axvline(l, color="tab:green", ls="--", lw=1.5)
    ax3.plot([], [], color="tab:blue", lw=1.6, label=f"GS levels (n={len(lv_gs)})")
    ax3.plot([], [], color="tab:green", ls="--", label=f"ref levels (n={len(lv_ref)})")
    ax3.set_xlabel("z ortho (m)"); ax3.set_ylabel("ALS pt count"); ax3.legend(fontsize=7)
    ax3.set_title(f"ALS levels n={len(lv_als)} vs GS {len(lv_gs)} vs ref {len(lv_ref)}", fontsize=8)
    k = sum(1 for s in sup if s["supported"]); m = len(sup) - k
    fig.suptitle(f"faithfulness {bid} ({kind})  GS faces ALS-supported k={k} / floating m={m} | "
                 f"levels GS {len(lv_gs)} ALS {len(lv_als)} ref {len(lv_ref)}", fontsize=10)
    fig.tight_layout(rect=[0, 0, 1, 0.95]); fp = FIG / f"{bid}.png"; fig.savefig(fp, dpi=105); plt.close(fig); return fp


def main():
    LEV.mkdir(parents=True, exist_ok=True)
    rows = []
    for bid, kind in BLD:
        paths = footprint_paths(bid)
        als = read_cloud("raw_lidar", bid, paths)
        rt, roof, wall = gml_building(bid)
        pr = parse_solid_roof("gs_d4_dense", bid)
        if pr is None:
            continue
        roof_faces, V = pr
        gs_cloud = read_cloud("gs_d4_dense", bid, paths)   # dense GS surface (not sparse model verts)
        als_env = roof_envelope(als) if als is not None and len(als) else None
        gs_env = roof_envelope(gs_cloud) if gs_cloud is not None and len(gs_cloud) else None
        # global GS<ALS vertical offset (ellipsoidal, dense-surface medians): ALS sits dz above GS.
        # best-fit dz that minimises per-face |resid| (robust to bimodal medians) over a +/-3m search.
        if als_env is not None and gs_env is not None:
            dz0 = float(np.median(als_env[:, 2]) - np.median(gs_env[:, 2]))
            # fairest test: pick the global offset (GS sits at/below ALS, dz>=0) that MAXIMISES the number
            # of faces sitting on ALS within TOL; tie-break by min total residual. "At the best possible
            # single offset, how many GS faces are on the real surface?"
            cand = [z for z in (round(dz0 + d, 2) for d in np.arange(-3, 3.01, 0.25)) if z >= 0]
            def score(z):
                ss = face_support(roof_faces, V, als, z)
                k = sum(1 for s in ss if s["supported"])
                tot = sum(s["resid_abs"] for s in ss if s["resid_abs"] is not None)
                return (-k, tot)
            dz = min(cand, key=score) if cand else max(0.0, dz0)
        else:
            dz = 0.0
        sup = face_support(roof_faces, V, als, dz=dz)
        lv_gs, comp = step_aware_levels(roof_faces, V)
        lv_als = z_levels(als_env[:, 2] if als_env is not None else None)
        lv_ref = sorted({round(float(r[:, 2].mean()), 1) for r in roof}) if roof else []  # ref GML = ORTHO already
        k = sum(1 for s in sup if s["supported"]); m = len(sup) - k
        als_min = float(als_env[:, 2].min() - GEOID) if als_env is not None else None
        als_max = float(als_env[:, 2].max() - GEOID) if als_env is not None else None
        fp = panel(bid, kind.split()[-1], roof_faces, V, als, lv_gs, lv_als, lv_ref, sup)
        # per-face csv
        with open(LEV / f"faithfulness_faces_{bid}.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["face", "face_z_ortho", "n_als", "resid_med", "resid_abs", "supported"])
            w.writeheader()
            for i, s in enumerate(sup):
                w.writerow({"face": i, "face_z_ortho": round(float(V[roof_faces[i]][:, 2].mean()) - GEOID, 2),
                            "n_als": s["n_als"], "resid_med": s["resid_med"], "resid_abs": s["resid_abs"],
                            "supported": s["supported"]})
        row = {"bid": bid, "kind": kind, "GS_dz_below_ALS_m": round(dz, 2), "GS_faces": len(roof_faces),
               "GS_supported_k": k, "GS_floating_m": m,
               "GS_levels_stepaware": len(lv_gs), "ALS_levels": len(lv_als), "ref_levels": len(lv_ref),
               "GS_levels_z_ortho": sorted(round(x - GEOID, 1) for x in lv_gs),
               "ALS_levels_z_ortho": sorted(round(x - GEOID, 1) for x in lv_als),
               "ref_levels_z_ortho": lv_ref, "ALS_z_min_ortho": round(als_min, 1) if als_min else None,
               "ALS_z_max_ortho": round(als_max, 1) if als_max else None}
        rows.append(row)
        print(f"{bid} {kind:22} | dz(GS<ALS) {dz:.2f}m | GS {len(roof_faces)} faces: ALS-supported k={k} floating m={m} | "
              f"levels GS(stepaware)={len(lv_gs)}{sorted(round(x-GEOID,1) for x in lv_gs)} "
              f"ALS={len(lv_als)}{sorted(round(x-GEOID,1) for x in lv_als)} ref={len(lv_ref)}{lv_ref} -> {fp.name}")
    with open(LEV / "faithfulness.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    print(f"\n[done] -> {LEV}/faithfulness.csv + per-face csvs ; figs {FIG}/")


if __name__ == "__main__":
    main()
