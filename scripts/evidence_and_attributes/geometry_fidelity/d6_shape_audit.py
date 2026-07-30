#!/usr/bin/env python3
"""P2-D6 shape audit — eye+measured verification of the 11 working buildings' roof SHAPE (P0 reuse).

The roof-type labels (flat/curved/composite) were eyeballed, not measured, and the survey showed
they disagree with the reference roofType. This re-checks the 11 with (a) a visual panel per building
[ref LoD2 model | ALS | DIM | GS] x {top, oblique}, height-colored; (b) a MEASURED shape classifier
on ALS roof points (plane RMS, slope, z-levels=stepped, quadric-vs-plane=curved); (c) for 4906969 an
ALS y-slice cross-section to settle round-arch vs stepped-flat. Observation only; verdict=김휘영.

Runs in jointbuildgs-p0-tools:t0 (numpy/laspy/matplotlib; no scipy). EPSG:25832. NO reconstruction.
Out: docs/figs/W_D6_shape/<bid>.png (+ 4906969_yslice.png) + results/.../analysis_pack_d6/shape_audit.csv
"""
import csv, glob, json
from pathlib import Path
import numpy as np, laspy, xml.etree.ElementTree as ET
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from matplotlib.path import Path as MplPath

REPO = Path("/workspace/JointBuildGS")
P0 = REPO / "phases/p0-audit"
EVAL = P0 / "runs/mob_eval"
GMLDIR = P0 / "data/raw/lod2"
GEOJSON = REPO / "results/tum_transfer/analysis/footprints_aoi.geojson"
OUT = REPO / "results/tum_transfer/mob/analysis_pack_d6"
FIG = REPO / "docs/figs/W_D6_shape"

# priority 5 reconstructed first, then 6 R (generation-failure essence)
PRIORITY = ["4906969", "4906972", "42364659", "42364663", "4908023"]
REST = ["4907182", "4907510", "42364609", "4908050", "4908166", "4908176"]
ALLB = PRIORITY + REST
OBS_LABEL = {"4906969": "곡면 curved", "4906972": "평지붕 flat", "42364659": "복합 composite",
             "42364663": "복합 composite", "4908023": "대조 control"}
RT_NAME = {"1000": "Flachdach(평)", "2100": "Pultdach", "3100": "Satteldach(박공)", "3200": "Walmdach(모임)",
           "3500": "Zeltdach", "3900": "Mischform(혼합)", "9999": "Sonstiges(기타)"}


def Lc(t): return t.rsplit("}", 1)[-1]


def gml_building(bid):
    """roofType, roof RoofSurface 3D rings, wall rings, roof z-levels."""
    full = f"DEBY_LOD2_{bid}"
    for g in glob.glob(str(GMLDIR / "*.gml")):
        for _, el in ET.iterparse(g, events=("end",)):
            if Lc(el.tag) != "Building":
                continue
            b = next((v for k, v in el.attrib.items() if Lc(k) == "id"), None)
            if b != full:
                el.clear(); continue
            rts = [e.text.strip() for e in el.iter() if Lc(e.tag) == "roofType" and e.text]
            def rings(kind):
                out = []
                for s in el.iter():
                    if Lc(s.tag) != kind:
                        continue
                    for pl in s.iter():
                        if Lc(pl.tag) == "posList" and pl.text:
                            out.append(np.array([float(x) for x in pl.text.split()]).reshape(-1, 3))
                return out
            roof, wall = rings("RoofSurface"), rings("WallSurface")
            el.clear()
            return (rts[0] if rts else "NONE"), roof, wall
    return "NONE", [], []


def footprint_paths(bid):
    full = f"DEBY_LOD2_{bid}"
    paths = []
    for ft in json.loads(GEOJSON.read_text())["features"]:
        if ft["properties"].get("building_id") != full:
            continue
        geom = ft["geometry"]
        polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        for poly in polys:
            paths.append(MplPath(np.asarray(poly[0])[:, :2]))
    return paths


def read_cloud(arm, bid, paths, roof_only=True):
    f = EVAL / arm / f"DEBY_LOD2_{bid}_orig_classified.las"
    if not f.exists():
        return None
    c = laspy.read(f)
    cl = np.asarray(c.classification)
    P = np.column_stack([np.asarray(c.x), np.asarray(c.y), np.asarray(c.z)]).astype(float)
    P = P[cl == 6] if roof_only else P[(cl == 6) | (cl == 2)]
    if len(P) == 0:
        return P
    m = np.zeros(len(P), bool)
    for p in paths:
        m |= p.contains_points(P[:, :2])
    return P[m]


def cell_normals(P, cell=2.0, minpts=8):
    g = np.floor(P[:, :2] / cell).astype(np.int64)
    key = g[:, 0] * 100003 + g[:, 1]
    o = np.argsort(key, kind="stable"); ks, Ps = key[o], P[o]
    _, cnt = np.unique(ks, return_counts=True)
    nrm = []
    for Q in np.split(Ps, np.cumsum(cnt)[:-1]):
        if len(Q) < minpts:
            continue
        cc = Q.mean(0); _, _, Vt = np.linalg.svd(Q - cc, full_matrices=False)
        n = Vt[-1]; n = n if n[2] >= 0 else -n
        nrm.append(n)
    return np.array(nrm) if nrm else np.empty((0, 3))


def roof_envelope(P, cell=1.0, band=1.5):
    """Top-surface (roof) envelope: per 1m xy cell keep points within `band` of the cell max-z.
    Removes wall/facade points (mob class6 = whole building envelope, not roof-only)."""
    if P is None or len(P) == 0:
        return P
    g = np.floor(P[:, :2] / cell).astype(np.int64); key = g[:, 0] * 100003 + g[:, 1]
    o = np.argsort(key, kind="stable"); ks, Ps = key[o], P[o]
    _, cnt = np.unique(ks, return_counts=True)
    keep = [Q[Q[:, 2] >= Q[:, 2].max() - band] for Q in np.split(Ps, np.cumsum(cnt)[:-1])]
    return np.vstack(keep) if keep else P


def measure_shape(P_all):
    """Measured roof-shape verdict from the ALS ROOF top-envelope (walls removed).
    LOCAL (2m-cell) slope — not one global plane — so multi-height flat sections aren't mistaken
    for a tilted roof; roof-z modes = levels; quadric-vs-plane = smooth curvature (arch)."""
    if P_all is None or len(P_all) < 20:
        return {"verdict": "미산출/희박", "n": 0 if P_all is None else len(P_all)}
    P = roof_envelope(P_all)
    nrm = cell_normals(P)
    if len(nrm) >= 1:
        cell_slope = np.degrees(np.arccos(np.clip(np.abs(nrm[:, 2]), 0, 1)))
        local_slope = float(np.median(cell_slope))
        ndom = nrm.mean(0); ndom /= (np.linalg.norm(ndom) + 1e-12)
        ndisp = float(np.degrees(np.arccos(np.clip(np.abs(nrm @ ndom), 0, 1))).std()) if len(nrm) >= 2 else None
    else:
        local_slope = ndisp = None
    # global plane (for planar_rms = overall non-planarity)
    c = P.mean(0); _, _, Vt = np.linalg.svd(P - c, full_matrices=False)
    nb = Vt[-1]; nb = nb if nb[2] >= 0 else -nb
    gslope = float(np.degrees(np.arccos(np.clip(abs(nb[2]), 0, 1))))
    planar_rms = float(np.sqrt((((P - c) @ Vt[-1]) ** 2).mean()))
    # raw-z levels (modes of z histogram, >=10% pop, merged within 1m)
    z = P[:, 2]; span = float(z.max() - z.min())
    nb_ = max(10, int(span / 0.5))
    hist, edges = np.histogram(z, bins=nb_)
    cen = 0.5 * (edges[:-1] + edges[1:])
    peaks = sorted([(hist[i], cen[i]) for i in range(1, len(hist) - 1)
                    if hist[i] >= 0.10 * len(P) and hist[i] >= hist[i - 1] and hist[i] >= hist[i + 1]],
                   key=lambda t: -t[1])
    levels = []
    for h, zc in peaks:
        if not any(abs(zc - l) < 1.0 for l in levels):
            levels.append(zc)
    nlev = len(levels)
    lvl_sep = (max(levels) - min(levels)) if nlev >= 2 else 0.0
    # quadric fit z ~ ax2+by2+cxy+dx+ey+f (smooth curvature)
    x, y = P[:, 0] - c[0], P[:, 1] - c[1]
    A = np.column_stack([x * x, y * y, x * y, x, y, np.ones_like(x)])
    coef, *_ = np.linalg.lstsq(A, z, rcond=None)
    quad_rms = float(np.sqrt(((A @ coef - z) ** 2).mean()))
    qp = quad_rms / (planar_rms + 1e-9)
    # verdict — local slope drives it
    multilevel = nlev >= 2 and lvl_sep > 1.5
    smooth_curved = planar_rms > 0.4 and qp < 0.55 and (abs(coef[0]) + abs(coef[1])) > 0.01
    if local_slope is None:
        v = "불확실"
    elif local_slope < 12:
        v = "단차/다층 평지붕(stepped/multi-level flat)" if multilevel else (
            "곡면(curved)" if smooth_curved else "평지붕(flat)")
    elif smooth_curved:
        v = "곡면(curved)"
    elif gslope > 70:
        v = "벽 오분류 의심(roof pts ~vertical)"
    elif multilevel:
        v = "다층+경사(multi-level sloped)"
    else:
        v = "경사/박공(sloped/gabled)"
    return {"verdict": v, "n": len(P), "local_slope_deg": round(local_slope, 1) if local_slope is not None else None,
            "global_slope_deg": round(gslope, 1), "planar_rms": round(planar_rms, 3),
            "quad/plane": round(qp, 2), "n_zlevel": nlev, "zlevel_sep_m": round(lvl_sep, 2),
            "nDisp_deg": round(ndisp, 1) if ndisp is not None else None}


def _sub(P, k=6000):
    if P is None or len(P) <= k:
        return P
    return P[np.random.default_rng(0).choice(len(P), k, replace=False)]


def _emptymsg(ax, msg, title):
    if hasattr(ax, "zaxis"):
        ax.text2D(0.5, 0.5, msg, transform=ax.transAxes, ha="center", va="center")
    else:
        ax.text(0.5, 0.5, msg, ha="center", va="center")
    ax.set_axis_off(); ax.set_title(title, fontsize=8)


def draw_cloud(ax, P, oblique, title):
    if P is None:
        _emptymsg(ax, "미산출\n(no cloud)", title); return
    if len(P) == 0:
        _emptymsg(ax, "0 점 in fp\n(empty)", title); return
    Q = _sub(P); z = Q[:, 2]
    if oblique:
        ax.scatter(Q[:, 0], Q[:, 1], z, c=z, cmap="viridis", s=2)
        ax.view_init(elev=22, azim=-60); ax.set_box_aspect((1, 1, 0.5))
        ax.set_xticks([]); ax.set_yticks([]); ax.set_zticks([])
    else:
        ax.scatter(Q[:, 0], Q[:, 1], c=z, cmap="viridis", s=3); ax.set_aspect("equal"); ax.set_axis_off()
    ax.set_title(f"{title}\n(n={len(P)})", fontsize=8)


def draw_ref(ax, roof, wall, oblique, title):
    allz = np.concatenate([r[:, 2] for r in roof]) if roof else np.array([0, 1])
    import matplotlib.cm as cm
    cmap = cm.get_cmap("tab10")
    if oblique:
        for w in wall:
            ax.add_collection3d(Poly3DCollection([w], facecolor="lightgray", edgecolor="gray", alpha=0.25, linewidths=0.2))
        for i, r in enumerate(roof):
            ax.add_collection3d(Poly3DCollection([r], facecolor=cmap(i % 10), edgecolor="k", alpha=0.85, linewidths=0.4))
        allpts = np.vstack(roof + wall) if (roof or wall) else np.zeros((1, 3))
        for setlim, lo, hi in [(ax.set_xlim, allpts[:, 0].min(), allpts[:, 0].max()),
                               (ax.set_ylim, allpts[:, 1].min(), allpts[:, 1].max()),
                               (ax.set_zlim, allpts[:, 2].min(), allpts[:, 2].max())]:
            setlim(lo, hi)
        ax.view_init(elev=22, azim=-60); ax.set_box_aspect((1, 1, 0.5))
        ax.set_xticks([]); ax.set_yticks([]); ax.set_zticks([])
    else:
        for i, r in enumerate(roof):
            ax.fill(r[:, 0], r[:, 1], color=cmap(i % 10), alpha=0.85, edgecolor="k", lw=0.4)
        ax.set_aspect("equal"); ax.set_axis_off()
    zlv = sorted({round(float(r[:, 2].mean()), 1) for r in roof})
    ax.set_title(f"{title}\nroof z-levels={zlv}", fontsize=8)


def panel(bid, rt, roof, wall, clouds, facets, rms, shape):
    FIG.mkdir(parents=True, exist_ok=True)
    fig = plt.figure(figsize=(17, 8.5))
    cols = [("ref", None), ("ALS", clouds["ALS"]), ("DIM", clouds["DIM"]), ("GS", clouds["GS"])]
    for ci, (name, P) in enumerate(cols):
        ax_t = fig.add_subplot(2, 4, ci + 1)
        ax_o = fig.add_subplot(2, 4, ci + 5, projection="3d")
        if name == "ref":
            draw_ref(ax_t, roof, wall, False, "ref LoD2 (roof colored)")
            draw_ref(ax_o, roof, wall, True, "ref LoD2 oblique")
        else:
            fa = facets.get(name, "–"); rm = rms.get(name, "–")
            draw_cloud(ax_t, P, False, f"{name} top  facets={fa} RMS→ref={rm}")
            draw_cloud(ax_o, P, True, f"{name} oblique")
    obs = OBS_LABEL.get(bid, "(R: 생성표적)")
    fig.suptitle(f"D6 shape audit {bid} | 관측라벨={obs} | 참조 roofType={rt}({RT_NAME.get(rt,'?')}) "
                 f"| ref면={facets.get('ref')} | 측정형상={shape['verdict']} "
                 f"(local-slope {shape.get('local_slope_deg')}°, planeRMS {shape.get('planar_rms')}, "
                 f"quad/plane {shape.get('quad/plane')}, z-levels {shape.get('n_zlevel')}@sep {shape.get('zlevel_sep_m')}m)",
                 fontsize=9)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fp = FIG / f"{bid}.png"
    fig.savefig(fp, dpi=95); plt.close(fig)
    return fp


def _kmeans1d(v, k, iters=50):
    """Tiny 1D k-means -> (labels, centers). Deterministic init at quantiles."""
    k = min(k, len(np.unique(np.round(v, 1))))
    if k < 1:
        return np.zeros(len(v), int), np.array([v.mean()])
    cen = np.quantile(v, np.linspace(0.1, 0.9, k))
    for _ in range(iters):
        lab = np.argmin(np.abs(v[:, None] - cen[None, :]), axis=1)
        new = np.array([v[lab == j].mean() if (lab == j).any() else cen[j] for j in range(k)])
        if np.allclose(new, cen):
            break
        cen = new
    return lab, cen


def yslice_4906969(als, roof):
    """ALS y-slice: round arch vs stepped-flat — on the ROOF TOP-PROFILE, in the cloud's own datum.
    Compares parabola(arch, 3 DOF) vs piecewise-constant 3-level(step, 3 DOF) RMS to the top profile."""
    if als is None or len(als) < 20:
        return None
    ymid = float(np.median(als[:, 1]))
    sl = als[np.abs(als[:, 1] - ymid) < 1.5]
    if len(sl) < 12:
        return None
    x0 = als[:, 0].min(); xs = sl[:, 0] - x0; zs = sl[:, 2]
    # roof top-profile: per 0.5m x-bin, take max z (roof top, drops walls)
    order = np.argsort(xs); xs_s, zs_s = xs[order], zs[order]
    edges = np.arange(xs_s.min(), xs_s.max() + 0.5, 0.5)
    px, pz = [], []
    for i in range(len(edges) - 1):
        m = (xs_s >= edges[i]) & (xs_s < edges[i + 1])
        if m.any():
            px.append(0.5 * (edges[i] + edges[i + 1])); pz.append(zs_s[m].max())
    px, pz = np.array(px), np.array(pz)
    pc = np.polyfit(px, pz, 2); arch_rms = float(np.sqrt(((np.polyval(pc, px) - pz) ** 2).mean()))
    lab, cen = _kmeans1d(pz, 3); step_pred = cen[lab]
    step_rms = float(np.sqrt(((step_pred - pz) ** 2).mean()))
    fig, ax = plt.subplots(figsize=(10, 5.2))
    ax.scatter(xs, zs, s=6, c="lightgray", label=f"ALS y-slice all (n={len(sl)})")
    ax.scatter(px, pz, s=22, c="tab:blue", label="roof top-profile (per-0.5m max-z)")
    xx = np.linspace(px.min(), px.max(), 200)
    ax.plot(xx, np.polyval(pc, xx), "tab:orange", lw=2, label=f"parabola (arch) RMS={arch_rms:.2f} m")
    for c in cen:
        ax.axhline(c, color="tab:red", ls="--", lw=1, alpha=0.7)
    ax.plot([], [], "tab:red", ls="--", label=f"3-level steps RMS={step_rms:.2f} m")
    verdict = "둥근 호(arch)" if arch_rms < 0.7 * step_rms else ("단차 평지붕(stepped-flat)" if step_rms < 0.7 * arch_rms else "혼재/불명확")
    ax.set_title(f"4906969 ALS y-slice (roof top-profile) — arch RMS {arch_rms:.2f} vs 3-step RMS {step_rms:.2f} → {verdict}\n"
                 f"(ellipsoidal z; ref ortho roof-levels +~49m geoid)")
    ax.set_xlabel("x - x0 (m)"); ax.set_ylabel("z (m)"); ax.legend(fontsize=8)
    fig.tight_layout(); fp = FIG / "4906969_yslice.png"; fig.savefig(fp, dpi=120); plt.close(fig)
    return fp, arch_rms, step_rms, verdict


def recompute_facets(arm, bid):
    full = f"DEBY_LOD2_{bid}"
    g = glob.glob(str(EVAL / arm / f"roofer_{full}_orig" / "*.city.jsonl"))
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


def load_rms():
    rms = {}
    for f, cfgs in [("ref_rms_raw.csv", {"raw_dense": "DIM", "raw_lidar": "ALS"}),
                    ("ref_rms_d4_gssem.csv", {"gs_d4_dense": "GS"})]:
        p = REPO / "results/tum_transfer/mob_analysis" / f
        if not p.exists():
            continue
        for r in csv.DictReader(open(p)):
            if r.get("tag") != "orig":
                continue
            arm = r["config"]; lab = cfgs.get(arm)
            if lab:
                rms.setdefault(r["bid"].replace("DEBY_LOD2_", ""), {})[lab] = r.get("rms_to_ref_m")
    return rms


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rmsdb = load_rms()
    rows = []
    for bid in ALLB:
        rt, roof, wall = gml_building(bid)
        paths = footprint_paths(bid)
        clouds = {"ALS": read_cloud("raw_lidar", bid, paths), "DIM": read_cloud("raw_dense", bid, paths),
                  "GS": read_cloud("gs_d4_dense", bid, paths)}
        facets = {"ref": len(roof), "ALS": recompute_facets("raw_lidar", bid),
                  "DIM": recompute_facets("raw_dense", bid), "GS": recompute_facets("gs_d4_dense", bid)}
        rms = rmsdb.get(bid, {})
        shape = measure_shape(clouds["ALS"])
        fp = panel(bid, rt, roof, wall, clouds, facets, rms, shape)
        zlv = sorted({round(float(r[:, 2].mean()), 2) for r in roof})
        rows.append({"bid": bid, "obs_label": OBS_LABEL.get(bid, "R(생성표적)"), "ref_roofType": rt,
                     "ref_roofType_name": RT_NAME.get(rt, "?"), "ref_facets": len(roof), "ref_zlevels": zlv,
                     "measured_shape": shape["verdict"], "local_slope_deg": shape.get("local_slope_deg"),
                     "global_slope_deg": shape.get("global_slope_deg"),
                     "planar_rms": shape.get("planar_rms"), "quad_over_plane": shape.get("quad/plane"),
                     "n_zlevel": shape.get("n_zlevel"), "zlevel_sep_m": shape.get("zlevel_sep_m"),
                     "nDisp_deg": shape.get("nDisp_deg"), "ALS_facets": facets["ALS"],
                     "DIM_facets": facets["DIM"], "GS_facets": facets["GS"],
                     "ALS_n": len(clouds["ALS"]) if clouds["ALS"] is not None else 0,
                     "DIM_n": len(clouds["DIM"]) if clouds["DIM"] is not None else 0})
        print(f"{bid:9} obs={OBS_LABEL.get(bid,'R'):14} rt={rt}({RT_NAME.get(rt,'?'):14}) "
              f"ref={len(roof)} zlv={zlv} -> measured={shape['verdict']:34} "
              f"(loc-slope {shape.get('local_slope_deg')}° planeRMS {shape.get('planar_rms')} "
              f"q/p {shape.get('quad/plane')} zlev {shape.get('n_zlevel')}@{shape.get('zlevel_sep_m')}m) -> {fp.name}")
    ys = yslice_4906969(read_cloud("raw_lidar", "4906969", footprint_paths("4906969")), gml_building("4906969")[1])
    if ys:
        print(f"\n[4906969 y-slice] arch RMS={ys[1]:.2f} vs 3-step RMS={ys[2]:.2f} -> {ys[3]} ({ys[0].name})")
    keys = list(rows[0].keys())
    with open(OUT / "shape_audit.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys); w.writeheader(); w.writerows(rows)
    print(f"\n[done] {len(rows)} panels -> {FIG}/ ; table -> {OUT}/shape_audit.csv")


if __name__ == "__main__":
    main()
