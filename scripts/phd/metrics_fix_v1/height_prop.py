"""PHD-MAIN-METRICS-FIX-v1 4.6: does the height offset grow with the height above ground? (jointbuildgs:dev, CPU; pre-training
data only; definitions = configs metrics_fix_v1.json 'height_proportional'). Nothing is corrected.

  python height_prop.py

Per site and building (LoD2 footprints of the box): GT roof points (ULS gt_points; ULS ownership rows) of roof-like patches that
are support agreement (regions v2) under both priors, outside the band v2 and on faces <= 17 degrees (slope of the owning
patch of each prior), in the evaluation range; >= 500 points to be fitted. Offsets: z_MVS - z_GT (regions_v2/mvs_at_gt, 0.1 m
cell median), z_LoD2 - z_GT and z_ALS - z_GT (highest crossing of the registered prior surface). Ground: GT points in the
evaluation range, not excluded, outside every footprint buffered by 1 m, within 2-20 m of the building's footprint, z <= DTM
(survey, local = absolute - 604 m) + 0.3 m. Fit per site and offset: offset = a + b x height (buildings + the site's ground point
at height 0 for MVS and ALS), slope in per mille, 95 % intervals (t, n - 2); pooled fit of all sites recorded. Image sets: the
training views of each site (split.json) and their overlaps.
Writes /out/height/height_prop.json, /out/figs/height_prop.png. scientific_verdict: null."""
import json

import numpy as np
from matplotlib.path import Path as MPath
from scipy import stats as sst
from shapely.geometry import Polygon as SPoly
from shapely.ops import unary_union

from mf_common import CFG, DR, FCFG, OUT, S0, SITES, SURVEY, Timer, boxes, in_eval_uv, jdump, log, owner_rows, setup_fonts
import s04_gt_v6 as s4  # noqa: E402
from src.phd.metrics_v2 import band
from src.phd.metrics_v2.surface import MeshScene

plt = setup_fonts()
HP = FCFG["height_proportional"]
ZSHIFT = float(CFG["frame"]["world_shift_xyz_m"][2])
HP_STEEP = 17.0
HP_MIN = 500


def in_geom(geom, xy):
    """vectorised point-in-(multi)polygon with holes."""
    out = np.zeros(len(xy), bool)
    for g in getattr(geom, "geoms", [geom]):
        m = MPath(np.asarray(g.exterior.coords)).contains_points(xy)
        for hole in g.interiors:
            m &= ~MPath(np.asarray(hole.coords)).contains_points(xy)
        out |= m
    return out


def prior_scene(site, prior):
    md = DR / "s02_box" / site
    sh = np.asarray(json.loads((S0 / "s61/box" / site / prior / "summary.json").read_text())["registration"]["shift_applied"], np.float64)
    m = np.load(md / ("lod2_mesh.npz" if prior == "LoD2" else "als_mesh.npz"))
    F = m["F"][m["tri_type"] != 2] if prior == "LoD2" else m["F"]
    return MeshScene(m["V"] + sh, F)


def fit(h, y):
    h, y = np.asarray(h, float), np.asarray(y, float)
    n = len(h)
    if n < 2 or np.ptp(h) == 0:
        return dict(n=n, slope_permille=None, intercept_cm=None)
    r = sst.linregress(h, y)
    out = dict(n=n, slope_permille=round(1000 * r.slope, 3), intercept_cm=round(100 * r.intercept, 2))
    if n > 2:
        t = sst.t.ppf(0.975, n - 2)
        out.update(slope_ci_permille=[round(1000 * (r.slope - t * r.stderr), 3), round(1000 * (r.slope + t * r.stderr), 3)],
                   intercept_ci_cm=[round(100 * (r.intercept - t * r.intercept_stderr), 2), round(100 * (r.intercept + t * r.intercept_stderr), 2)])
    return out


def main():
    T = Timer()
    O = OUT / "height"
    O.mkdir(parents=True, exist_ok=True)
    Dg, _ = s4.survey_grids()
    grid = s4.Grid(Dg["dtm"].shape)
    dtm = Dg["dtm"].astype(np.float64) - ZSHIFT
    bx = boxes()
    res, pooled = {}, {"MVS": ([], []), "LoD2": ([], []), "ALS": ([], [])}
    for site in SITES:
        b = bx[SITES[site]]
        D = S0 / "s61/box_gt" / site
        X = np.load(D / "gt_points.npz")["xyz"].astype(np.float64)
        ez = np.load(D / "exclusion_cells.npz")["any"]
        iy, ix, ok = grid.idx(X[:, 0], X[:, 1])
        use = in_eval_uv(X, b) & ~(ok & ez[iy, ix])
        mv = np.load(OUT / "regions_v2" / f"mvs_at_gt_{site}.npz")
        zm = np.full(len(X), np.nan)
        zm[mv["gt_points_index"]] = mv["gt_points_z_mvs"]
        # common gentle support-agreement roof points (both priors)
        good = {}
        for prior in ("LoD2", "ALS"):
            R = np.load(OUT / "regions_v2" / f"regions_ext_v2_{site}_{prior}.npz")
            U = np.load(S0 / "s61/box" / site / prior / "units.npz")
            nrm = np.cross(U["loc_t1"], U["loc_t2"])
            nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-12)
            sl = np.degrees(np.arccos(np.clip(np.abs(nrm[:, 2]), 0, 1)))
            up = np.ones(len(R["code_ext_v2"]), bool) if site.startswith("B0") else np.zeros(len(R["code_ext_v2"]), bool)
            g = np.zeros(len(X), bool)
            for name, pt, pa, va, kd in owner_rows(site, prior, up):
                if name != "gt_points":
                    continue
                m = (kd == 1) & (R["code_ext_v2"][pa] == 2) & (sl[pa] <= HP_STEEP) & use[pt]
                p_, s_ = pt[m], sl[pa[m]]
                inb, _ = band.edge_band_v2(X, X[p_], s_, 0.5, 0.3, 0.1, 80.0)
                g[p_[~inb]] = True
            good[prior] = g
        roof = good["LoD2"] & good["ALS"]
        scL, scA = prior_scene(site, "LoD2"), prior_scene(site, "ALS")
        fp = json.loads((DR / "s02_box" / site / "footprints.json").read_text())["footprints"]
        allfp = unary_union([SPoly(f["ring_local"]) for f in fp]).buffer(1.0)
        # ground candidates: use, outside footprints + 1 m, z <= DTM + 0.3
        gcand = use & ok & (X[:, 2] <= dtm[iy, ix] + 0.3)
        gi = np.nonzero(gcand)[0]
        gi = gi[~in_geom(allfp, X[gi, :2])]
        site_res = dict(buildings={}, image_views=None)
        rings = []
        for f in fp:
            poly = SPoly(f["ring_local"])
            inside = MPath(np.asarray(f["ring_local"])).contains_points(X[:, :2]) & roof
            ring = poly.buffer(HP["ring_m"][1]).difference(poly.buffer(HP["ring_m"][0]))
            gin = gi[in_geom(ring, X[gi, :2])] if len(gi) else gi
            rings.append(gin)
            ri = np.nonzero(inside)[0]
            e = dict(roof_points=int(len(ri)), ground_points=int(len(gin)))
            if len(ri) and len(gin):
                zr, zg = np.median(X[ri, 2]), np.median(X[gin, 2])
                e["height_m"] = round(float(zr - zg), 2)
                e["mvs_minus_gt_cm"] = round(100 * float(np.nanmedian(zm[ri] - X[ri, 2])), 2)
                e["lod2_minus_gt_cm"] = round(100 * float(np.nanmedian(scL.highest_z(X[ri, :2]) - X[ri, 2])), 2)
                e["als_minus_gt_cm"] = round(100 * float(np.nanmedian(scA.highest_z(X[ri, :2]) - X[ri, 2])), 2)
                e["ground_mvs_minus_gt_cm"] = round(100 * float(np.nanmedian(zm[gin] - X[gin, 2])), 2)
                e["ground_als_minus_gt_cm"] = round(100 * float(np.nanmedian(scA.highest_z(X[gin, :2]) - X[gin, 2])), 2)
                e["fitted"] = len(ri) >= HP_MIN
            site_res["buildings"][f["building"]] = e
        # site ground reference: all ground points of the rings together
        gall = np.unique(np.concatenate(rings)) if rings else gi
        site_res["ground"] = dict(points=int(len(gall)), mvs_minus_gt_cm=round(100 * float(np.nanmedian(zm[gall] - X[gall, 2])), 2) if len(gall) else None,
                                  als_minus_gt_cm=round(100 * float(np.nanmedian(scA.highest_z(X[gall, :2]) - X[gall, 2])), 2) if len(gall) else None)
        fits = {}
        for key, col, gkey in (("MVS", "mvs_minus_gt_cm", "mvs_minus_gt_cm"), ("LoD2", "lod2_minus_gt_cm", None), ("ALS", "als_minus_gt_cm", "als_minus_gt_cm")):
            hs, ys = [], []
            for bname, e in site_res["buildings"].items():
                if e.get("fitted"):
                    hs.append(e["height_m"])
                    ys.append(e[col] / 100)
            if gkey and site_res["ground"][gkey] is not None:
                hs.append(0.0)
                ys.append(site_res["ground"][gkey] / 100)
            fits[key] = fit(hs, ys)
            pooled[key][0].extend(hs)
            pooled[key][1].extend(ys)
        site_res["fits"] = fits
        site_res["height_alignment_shift_m"] = json.loads((DR / "s52/box_gt" / site / "gt_summary.json").read_text())["height_alignment"]["shift_m"]
        res[site] = site_res
        log(site, {k: (v.get("height_m"), v.get("mvs_minus_gt_cm"), v.get("lod2_minus_gt_cm"), v.get("als_minus_gt_cm"), v.get("roof_points")) for k, v in site_res["buildings"].items()},
            "ground", site_res["ground"], "fits", fits, T.mark(site))
    # image sets
    views = {s: set(json.loads((S0 / "fork_inputs/s61" / s / "split.json").read_text())["train"]) for s in SITES}
    ov = {f"{a}|{b}": dict(shared=len(views[a] & views[b]), jaccard=round(len(views[a] & views[b]) / max(len(views[a] | views[b]), 1), 3)) for i, a in enumerate(SITES) for b in list(SITES)[i + 1:]}
    img = dict(train_views={s: len(v) for s, v in views.items()}, overlaps=ov, sfm="one SfM of 937 posed images (common to every site)")
    pooled_fit = {k: fit(*v) for k, v in pooled.items()}
    jdump(O / "height_prop.json", dict(rule=HP, sites=res, pooled=pooled_fit, image_sets=img, seconds=T.marks, scientific_verdict=None))
    # figure
    fig, axs = plt.subplots(1, 3, figsize=(19, 6), constrained_layout=True)
    marks = {"B0_b10": "o", "B173nb_b10": "s", "B173_b0": "^", "R1rep_b10": "D"}
    cols = {"MVS": "#2ca02c", "LoD2": "#d62728", "ALS": "#1f77b4"}
    ko = {"MVS": "MVS − 참값", "LoD2": "LoD2 − 참값", "ALS": "항공 LiDAR − 참값"}
    for ax, key, col in zip(axs, ("MVS", "LoD2", "ALS"), ("mvs_minus_gt_cm", "lod2_minus_gt_cm", "als_minus_gt_cm")):
        for site, sr in res.items():
            hs = [e["height_m"] for e in sr["buildings"].values() if e.get("fitted")]
            ys = [e[col] for e in sr["buildings"].values() if e.get("fitted")]
            gk = {"MVS": "mvs_minus_gt_cm", "ALS": "als_minus_gt_cm"}.get(key)
            if gk and sr["ground"][gk] is not None:
                hs = [0.0] + hs
                ys = [sr["ground"][gk]] + ys
            ax.scatter(hs, ys, marker=marks[site], s=60, c=cols[key], edgecolors="k", linewidths=0.5, label=site)
            f = sr["fits"][key]
            if f.get("slope_permille") is not None:
                xx = np.array([0, max(hs) if hs else 1])
                ax.plot(xx, f["intercept_cm"] + f["slope_permille"] / 10 * xx, "-", color=cols[key], lw=0.8, alpha=0.7)
        pf = pooled_fit[key]
        if pf.get("slope_permille") is not None:
            xx = np.array([0, max(pooled[key][0])])
            ax.plot(xx, pf["intercept_cm"] + pf["slope_permille"] / 10 * xx, "k--", lw=1.2, label=f"네 지역 함께: {pf['slope_permille']:+.2f} ‰")
        ax.axhline(0, color="#888", lw=0.6)
        ax.set_xlabel("지면 위 높이 (m)")
        ax.set_ylabel(f"{ko[key]} (cm)")
        ax.set_title(f"{ko[key]}: 건물마다 점 하나(높이 0 = 지면)", fontsize=11)
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8)
    fig.suptitle("지지 일치 영역의 완만한 지붕(두 사전 정보 모두, 새 띠 밖, 17° 이하)에서 건물마다 높이 어긋남의 중앙값과 지면 위 높이", fontsize=12, x=0.01, ha="left")
    fig.savefig(OUT / "figs/height_prop.png", dpi=95)
    plt.close(fig)
    print("height done", T.marks)


if __name__ == "__main__":
    main()
