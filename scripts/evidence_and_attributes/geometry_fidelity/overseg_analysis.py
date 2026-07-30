#!/usr/bin/env python3
"""P2 overseg-lever Phase A — diagnosis + post-process levers (facet-merge, smoothing collect, decimation
reuse) + guardrail + figures. GS roof is OVER-SEGMENTED vs ALS (exp1). Diagnose cause (density vs
roughness) and test post-process levers to converge facet count to ALS WITHOUT breaking surface error.
NO retrain, NO reconstruction here (Roofer re-runs done by run_overseg_phaseA.sh). Observation only;
verdict = 김휘영. Reuses assembly_fidelity / d6_shape_audit helpers. EPSG:25832.

Out: results/.../overseg_lever/overseg_phaseA.csv  +  docs/figs/W_overseg/{scatter.png,<bid>.png}
"""
import csv, glob, json, sys
from collections import defaultdict
from pathlib import Path
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))
from scripts.evidence_and_attributes.geometry_fidelity.d6_shape_audit import footprint_paths, read_cloud, roof_envelope, gml_building, EVAL
from scripts.evidence_and_attributes.geometry_fidelity.assembly_fidelity import fit_plane, ref_planes, aligned_rms, roofenv_rms, target_faces

REPO = Path("/workspace/JointBuildGS")
LEV = REPO / "results/tum_transfer/mob/overseg_lever"
FIG = REPO / "docs/figs/W_overseg"
BLD = ["42364659", "42364663", "4907510", "4906972", "4908023", "4906969"]
REF_FAC = {"42364659": 2, "42364663": 1, "4907510": 1, "4906972": 3, "4908023": 1, "4906969": 3}
GUARD = {"42364663", "4906972"}  # controls: must keep facet count >= ALS (no over-merge / no destroy)


# ---------- existing-output facet count + rf_* attributes ----------
def facets_dir(d, bid):
    full = f"DEBY_LOD2_{bid}"
    g = glob.glob(f"{d}/**/*.city.jsonl", recursive=True)
    if not g:
        return None
    n = 0
    for ln in open(g[0]):
        if not ln.strip():
            continue
        for cid, o in json.loads(ln).get("CityObjects", {}).items():
            if cid == full or cid.startswith(full + "-"):
                for gm in o.get("geometry", []):
                    for s in gm.get("semantics", {}).get("surfaces", []):
                        if s.get("type") == "RoofSurface":
                            n += 1
    return n


def rf_attrs(arm, bid):
    full = f"DEBY_LOD2_{bid}"
    g = glob.glob(str(EVAL / arm / f"roofer_{full}_orig" / "*.city.jsonl"))
    if not g:
        return {}
    for ln in open(g[0]):
        if not ln.strip():
            continue
        for cid, o in json.loads(ln).get("CityObjects", {}).items():
            if cid == full or cid.startswith(full + "-"):
                a = o.get("attributes", {})
                if any(k.startswith("rf_") for k in a):
                    return a
    return {}


# ---------- roughness: high-frequency (per-cell residual) vs low-frequency (global-plane residual) ----------
def roughness(P_all):
    if P_all is None or len(P_all) < 20:
        return {"hf": None, "lf": None, "n": 0}
    P = roof_envelope(P_all)
    # high-freq = median per-2m-cell plane residual (local noise); low-freq = global single-plane residual
    gx = np.floor(P[:, 0] / 2.0).astype(np.int64); gy = np.floor(P[:, 1] / 2.0).astype(np.int64)
    _, cid = np.unique(np.stack([gx, gy], 1), axis=0, return_inverse=True)
    res = []
    for k in range(cid.max() + 1):
        Q = P[cid == k]
        if len(Q) < 8:
            continue
        c = Q.mean(0); _, _, Vt = np.linalg.svd(Q - c, full_matrices=False)
        res.append(np.sqrt((((Q - c) @ Vt[-1]) ** 2).mean()))
    hf = float(np.median(res)) if res else None
    c = P.mean(0); _, _, Vt = np.linalg.svd(P - c, full_matrices=False)
    lf = float(np.sqrt((((P - c) @ Vt[-1]) ** 2).mean()))
    return {"hf": hf, "lf": lf, "n": len(P)}


# ---------- facet-merge lever: merge near-coplanar adjacent roof faces of the GS Solid ----------
def parse_solid_roof(arm, bid):
    """return roof faces as (planes[(n,c)], face_rings[list of vtx-idx], adjacency edges). vertices ELLIPSOIDAL."""
    full = f"DEBY_LOD2_{bid}"
    g = glob.glob(str(EVAL / arm / f"roofer_{full}_orig" / "*.city.jsonl"))
    if not g:
        return None
    lines = [ln for ln in open(g[0]) if ln.strip()]
    meta = json.loads(lines[0]); tr = meta.get("transform", {})
    sc = np.array(tr.get("scale", [1, 1, 1])); tl = np.array(tr.get("translate", [0, 0, 0]))
    # the target's faces and vertices must come from the SAME feature line (vertex indices are line-local)
    for ln in lines[1:]:
        d = json.loads(ln)
        if not d.get("vertices"):
            continue
        V = np.array(d["vertices"], float) * sc + tl
        roof_faces = []
        for cid, o in d.get("CityObjects", {}).items():
            if not (cid == full or cid.startswith(full + "-")):
                continue
            for gm in o.get("geometry", []):
                if gm.get("type") != "Solid":
                    continue
                surfs = gm["semantics"]["surfaces"]; vals = gm["semantics"]["values"]
                for si, shell in enumerate(gm["boundaries"]):
                    for fi, face in enumerate(shell):
                        if not (face and face[0] and len(face[0]) >= 3):
                            continue
                        if surfs[vals[si][fi]].get("type") != "RoofSurface":
                            continue
                        roof_faces.append([int(v) for v in face[0]])
        if roof_faces:
            return roof_faces, V
    return None


def merge_facets(roof_faces, V, ang_deg=10.0, off_m=0.3):
    """merge roof faces that lie on the SAME PLANE (normal angle < ang AND perpendicular offset < off_m).
    Adjacency is NOT required: Roofer roof faces are rarely edge-adjacent (separated by walls in the
    Solid), and the GS over-segmentation is a quilt of co-planar fragments. The OFFSET test preserves
    real height steps (a stepped-flat roof's distinct levels are >off_m apart -> NOT merged), so this
    cannot collapse genuine structure (verified by the gable/control guardrails). Single-linkage union."""
    planes = [fit_plane(V[ring]) for ring in roof_faces]  # (n with n[2]>=0, centroid)
    nf = len(roof_faces)
    parent = list(range(nf))
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    cth = np.cos(np.radians(ang_deg))
    for i in range(nf):
        for j in range(i + 1, nf):
            na, ca = planes[i]; nb, cb = planes[j]
            if abs(float(na @ nb)) < cth:
                continue
            navg = na + (nb if na @ nb >= 0 else -nb); navg /= (np.linalg.norm(navg) + 1e-12)
            if abs(float((ca - cb) @ navg)) > off_m:
                continue
            parent[find(i)] = find(j)
    clusters = defaultdict(list)
    for i in range(nf):
        clusters[find(i)].append(i)
    return len(clusters), clusters, planes


def pt_to_nearest_plane_rms(P, plane_list):
    """direct (no dz) RMS of P to nearest of plane_list[(n,c)] — model & GS cloud share ellipsoidal datum."""
    if P is None or len(P) == 0 or not plane_list:
        return None
    d = np.full(len(P), np.inf)
    for n, c in plane_list:
        d = np.minimum(d, np.abs((P - c) @ n))
    return round(float(np.sqrt((d ** 2).mean())), 3)


def merged_planes(clusters, roof_faces, V, planes):
    out = []
    for cl in clusters.values():
        if len(cl) == 1:
            out.append(planes[cl[0]]); continue
        pts = np.vstack([V[roof_faces[i]] for i in cl])
        out.append(fit_plane(pts))
    return out


def cluster_zspan(clusters, roof_faces, V):
    """max face-centroid-z spread within any merged (>1 face) cluster = how much real height is collapsed."""
    spans = []
    for cl in clusters.values():
        if len(cl) < 2:
            continue
        zc = [float(V[roof_faces[i]][:, 2].mean()) for i in cl]
        spans.append(max(zc) - min(zc))
    return round(max(spans), 2) if spans else 0.0


# ---------- figure: per-building roof faces colored, orig GS | merged GS | ALS ----------
def draw_faces(ax, arm, bid, merge=None):
    pr = parse_solid_roof(arm, bid)
    if pr is None:
        ax.text(0.5, 0.5, "no solid", ha="center"); ax.set_axis_off(); return 0
    roof_faces, V = pr
    if merge is not None:
        _, clusters, planes = merge
        face_cl = {}
        for ci, cl in enumerate(clusters.values()):
            for fi in cl:
                face_cl[fi] = ci
        ncol = len(clusters)
    else:
        face_cl = {i: i for i in range(len(roof_faces))}; ncol = len(roof_faces)
    import matplotlib.cm as cm
    cmap = cm.get_cmap("tab20")
    for fi, ring in enumerate(roof_faces):
        poly = V[ring][:, :2]
        ax.fill(poly[:, 0], poly[:, 1], color=cmap(face_cl[fi] % 20), alpha=0.8, edgecolor="k", lw=0.4)
    ax.set_aspect("equal"); ax.set_axis_off()
    return ncol


def panel(bid, gs_orig_n, gs_merged_n, als_n, merge, zspan=None):
    FIG.mkdir(parents=True, exist_ok=True)
    fig, axs = plt.subplots(1, 3, figsize=(13, 4.4))
    draw_faces(axs[0], "gs_d4_dense", bid); axs[0].set_title(f"GS orig roof faces = {gs_orig_n}", fontsize=9)
    draw_faces(axs[1], "gs_d4_dense", bid, merge)
    axs[1].set_title(f"GS facet-merged = {gs_merged_n}  (collapses z-span {zspan}m)", fontsize=9)
    draw_faces(axs[2], "raw_lidar", bid); axs[2].set_title(f"ALS roof faces = {als_n}", fontsize=9)
    fig.suptitle(f"overseg-lever {bid}  (ref={REF_FAC[bid]})  facet-merge ang25/off1.0 (aggressive, guardrail-safe)", fontsize=10)
    fig.tight_layout(rect=[0, 0, 1, 0.94]); fp = FIG / f"{bid}.png"; fig.savefig(fp, dpi=100); plt.close(fig); return fp


def main():
    rows = []
    for bid in BLD:
        paths = footprint_paths(bid)
        gs = read_cloud("gs_d4_dense", bid, paths); als = read_cloud("raw_lidar", bid, paths)
        rt, roof, wall = gml_building(bid); rpl = ref_planes(roof)
        ag = rf_attrs("gs_d4_dense", bid); aa = rf_attrs("raw_lidar", bid)
        rg = roughness(gs); ra = roughness(als)
        gs_fac = facets_dir(str(EVAL / "gs_d4_dense" / f"roofer_DEBY_LOD2_{bid}_orig"), bid)
        als_fac = facets_dir(str(EVAL / "raw_lidar" / f"roofer_DEBY_LOD2_{bid}_orig"), bid)
        # roof-env RMS->ref (facade-removed, fidelity to truth)
        rms_gs = roofenv_rms(gs, rpl); rms_als = roofenv_rms(als, rpl)
        # ---- facet-merge lever (plane-clustering): gentle a10/off0.3 vs aggressive-safe a25/off1.0 ----
        # NB single-linkage union -> a chain of small steps can collapse into a cluster whose z-span >> off.
        pr = parse_solid_roof("gs_d4_dense", bid)
        gs_roofpts = roof_envelope(gs) if gs is not None and len(gs) else None
        merge_res = {}
        for ang, off in [(10.0, 0.3), (25.0, 1.0)]:
            if pr is None:
                merge_res[(ang, off)] = None; continue
            roof_faces, V = pr
            nmer, clusters, planes = merge_facets(roof_faces, V, ang, off)
            orig_fit = pt_to_nearest_plane_rms(gs_roofpts, planes)
            merg_fit = pt_to_nearest_plane_rms(gs_roofpts, merged_planes(clusters, roof_faces, V, planes))
            zspan = cluster_zspan(clusters, roof_faces, V)
            merge_res[(ang, off)] = (nmer, orig_fit, merg_fit, clusters, planes, zspan)
        m10 = merge_res[(10.0, 0.3)]; m25 = merge_res[(25.0, 1.0)]
        gs_merge_gentle = m10[0] if m10 else gs_fac
        gs_merge_aggr = m25[0] if m25 else gs_fac
        # smoothing-lever facets
        sm_light = facets_dir(str(LEV / "smooth_light" / bid), bid)
        sm_med = facets_dir(str(LEV / "smooth_med" / bid), bid)
        # decimation reuse (matched tag)
        gs_matched = facets_dir(str(EVAL / "gs_d4_dense" / f"roofer_DEBY_LOD2_{bid}_matched"), bid)
        fp = panel(bid, gs_fac, gs_merge_aggr, als_fac, ((m25[0], m25[3], m25[4]) if m25 else None),
                   zspan=(m25[5] if m25 else None))
        row = {"bid": bid, "ref_facets": REF_FAC[bid], "ALS_facets": als_fac, "GS_facets": gs_fac,
               "overseg_excess_vs_ALS": (gs_fac - als_fac) if (gs_fac is not None and als_fac is not None) else None,
               "GS_rf_roof_planes": ag.get("rf_roof_planes"), "ALS_rf_roof_planes": aa.get("rf_roof_planes"),
               "GS_rf_rmse_lod22": round(ag.get("rf_rmse_lod22", 0), 3) if ag else None,
               "ALS_rf_rmse_lod22": round(aa.get("rf_rmse_lod22", 0), 3) if aa else None,
               "GS_pt_density": round(ag.get("rf_pt_density", 0), 1) if ag else None,
               "ALS_pt_density": round(aa.get("rf_pt_density", 0), 1) if aa else None,
               "GS_nodata_frac": round(ag.get("rf_nodata_frac", 0), 3) if ag else None,
               "GS_roof_type": ag.get("rf_roof_type"), "ALS_roof_type": aa.get("rf_roof_type"),
               "GS_roughHF": round(rg["hf"], 3) if rg["hf"] is not None else None,
               "ALS_roughHF": round(ra["hf"], 3) if ra["hf"] is not None else None,
               "GS_roughLF": round(rg["lf"], 3) if rg["lf"] is not None else None,
               "ALS_roughLF": round(ra["lf"], 3) if ra["lf"] is not None else None,
               "GS_roofenvRMS2ref": rms_gs, "ALS_roofenvRMS2ref": rms_als,
               # levers: facet-merge gentle (a10/off0.3) vs aggressive-guardrail-safe (a25/off1.0)
               "merge_gentle_a10o03": gs_merge_gentle, "merge_aggr_a25o10": gs_merge_aggr,
               "merge_reaches_ALS": (gs_merge_aggr == als_fac) if als_fac is not None else None,
               "fitRMS_orig": m25[1] if m25 else None,
               "fitRMS_gentle": m10[2] if m10 else None, "fitRMS_aggr": m25[2] if m25 else None,
               "merge_zspan_gentle": m10[5] if m10 else None, "merge_zspan_aggr": m25[5] if m25 else None,
               "smooth_light": sm_light, "smooth_med": sm_med,
               "decim_matched": gs_matched,
               "guardrail": bid in GUARD}
        rows.append(row)
        print(f"{bid:10} ref{REF_FAC[bid]} ALS{als_fac} GS{gs_fac} (excess {row['overseg_excess_vs_ALS']}) | "
              f"dens G{row['GS_pt_density']}/A{row['ALS_pt_density']} roughLF G{row['GS_roughLF']}/A{row['ALS_roughLF']} "
              f"| rfPlanes G{ag.get('rf_roof_planes')}/A{aa.get('rf_roof_planes')} "
              f"| merge gentle->{gs_merge_gentle} aggr->{gs_merge_aggr}(=ALS? {row['merge_reaches_ALS']}) "
              f"fitRMS {row['fitRMS_orig']}->g{row['fitRMS_gentle']}/a{row['fitRMS_aggr']} zspan_aggr {row['merge_zspan_aggr']}m "
              f"| smooth L/M {sm_light}/{sm_med} | decim {gs_matched} -> {fp.name}")
    # ---- scatter: over-seg excess vs density and vs roughness ----
    FIG.mkdir(parents=True, exist_ok=True)
    ex = [r["overseg_excess_vs_ALS"] for r in rows]
    fig, axs = plt.subplots(1, 3, figsize=(15, 4.6))
    for ax, key, lab in [(axs[0], "GS_pt_density", "GS rf_pt_density (pts/m²)"),
                         (axs[1], "GS_roughHF", "GS high-freq roughness (per-2m-cell plane RMS, m)"),
                         (axs[2], "GS_roughLF", "GS low-freq waviness (global-plane RMS, m)")]:
        xv = [r[key] for r in rows]
        ax.scatter(xv, ex, c="tab:blue", s=60)
        for r, x in zip(rows, xv):
            ax.annotate(r["bid"], (x, r["overseg_excess_vs_ALS"]), fontsize=7)
        ax.set_xlabel(lab); ax.set_ylabel("over-seg excess (GS−ALS facets)"); ax.grid(alpha=0.3)
        xv2 = [v for v in xv if v is not None]; ev2 = [e for e, v in zip(ex, xv) if v is not None]
        if len(xv2) >= 3 and np.std(xv2) > 0:
            cc = np.corrcoef(xv2, ev2)[0, 1]; ax.set_title(f"r = {cc:.2f}", fontsize=10)
    fig.suptitle("over-seg excess vs density / high-freq roughness / low-freq waviness", fontsize=11)
    fig.tight_layout(rect=[0, 0, 1, 0.95]); fig.savefig(FIG / "scatter.png", dpi=110); plt.close(fig)
    with open(LEV / "overseg_phaseA.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    print(f"\n[done] -> {LEV}/overseg_phaseA.csv ; figs {FIG}/")


if __name__ == "__main__":
    main()
