"""PHD-MAIN-METRICS-FIX-v1 4.5 (part 1): evidence on the observation-error region from pre-training data only (jointbuildgs:dev,
CPU; definitions = configs metrics_fix_v1.json 'observation_error_check').

  python obs_check.py

1. GT appearance, four sites x two priors, roof-like patches of regions v2, observation error (3) vs support agreement (2):
   per 0.25 m cell (the cell of the patch centre; all box GT points) the GT point count and the height range (> 0.3 m = a
   double layer); the share of 0.5 m survey cells within 1 m of the patch centre that hold no GT point or are excluded;
   separately for faces <= 17 and > 17 degrees
2. ULS attributes: the box GT points matched to the raw ULS laz by position (z + the box's height-alignment shift, 0.5 mm):
   intensity, return number, number of returns of the GT points owned by 3 vs 2
3. overlays: the patches drawn on nadir photos (B173nb_b10: the two nadir evaluation views of the stage-0 figures; the other
   sites: the box training view with tilt <= 20 degrees whose projection of the region patches' centroid lies nearest the
   image centre), visible = the camera ray's first crossing with the registered prior within 0.3 m of the patch centre
4. sections: the five observation-error roof-like patches of B173nb_b10 (LoD2, v2) owning the most GT points, each more
   than 2 m from those chosen before -> defs/sections_obs.json (before any training result of this step is read)
Writes /out/obs/obs_check.json, /out/obs/uls_attributes.npz, /out/defs/sections_obs.json, /out/figs/obs_overlay.png.
scientific_verdict: null."""
import json

import cv2
import numpy as np
from matplotlib.lines import Line2D
from scipy.spatial import cKDTree

from mf_common import ART, CFG, DENSE, DR, FCFG, GRID_H, GRID_W, MT, OUT, PRIOR_KO, S0, SITES, Timer, Views, basis, boxes, jdump, log, owner_rows, label_source, setup_fonts, xy_to_uv
import s04_gt_v6 as s4  # noqa: E402  (stage-0 scripts on the path through mf_common)
from src.phd.metrics_v2.surface import MeshScene

plt = setup_fonts()
OC = FCFG["observation_error_check"]
ULS = ART / "phase-payloads/p0-audit/data/raw/tum2twin/TUM_Downtown_ULS_20241217_nadir.laz"
SHIFT = np.array(CFG["frame"]["world_shift_xyz_m"], np.float64)
COLS = {3: "#ffd400", 2: "#2ca02c", 0: "#bdbdbd"}
NAMES = {3: "관측 오류 영역", 2: "지지 일치 영역", 0: "참값 결여 영역"}


def prior_mesh(site, prior):
    md = DR / "s02_box" / site
    sh = np.asarray(json.loads((S0 / "s61/box" / site / prior / "summary.json").read_text())["registration"]["shift_applied"], np.float64)
    m = np.load(md / ("lod2_mesh.npz" if prior == "LoD2" else "als_mesh.npz"))
    F = m["F"][m["tri_type"] != 2] if prior == "LoD2" else m["F"]
    return m["V"] + sh, F


def slopes(site, prior):
    U = np.load(S0 / "s61/box" / site / prior / "units.npz")
    n = np.cross(U["loc_t1"], U["loc_t2"])
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    return np.degrees(np.arccos(np.clip(np.abs(n[:, 2]), 0, 1))), n * np.where(n[:, 2:3] < 0, -1.0, 1.0)


def appearance(site, X, grid, ez):
    """per-patch cell features of both priors."""
    c25 = OC["cell_m"]
    q = np.floor(X[:, :2] / c25).astype(np.int64)
    key = q[:, 0] * 10_000_000 + q[:, 1]
    o = np.argsort(key)
    ks, zs = key[o], X[o, 2]
    start = np.r_[0, np.nonzero(ks[1:] != ks[:-1])[0] + 1]
    uk = ks[start]
    cnt = np.diff(np.r_[start, len(ks)])
    zmax = np.maximum.reduceat(zs, start)
    zmin = np.minimum.reduceat(zs, start)
    # 0.5 m survey cells: GT count and the exclusion raster
    iy, ix, ok = grid.idx(X[:, 0], X[:, 1])
    g_cnt = np.zeros(ez.shape, np.int64)
    np.add.at(g_cnt, (iy[ok], ix[ok]), 1)
    out = {}
    for prior in ("LoD2", "ALS"):
        R = np.load(OUT / "regions_v2" / f"regions_ext_v2_{site}_{prior}.npz")
        sl, _ = slopes(site, prior)
        c2 = R["code_ext_v2"]
        sel = np.nonzero(np.isin(c2, (2, 3)) & (R["kind"] == 1))[0]
        cc = R["centre"][sel]
        qk = np.floor(cc[:, :2] / c25).astype(np.int64)
        kk = qk[:, 0] * 10_000_000 + qk[:, 1]
        i = np.searchsorted(uk, kk)
        hit = (i < len(uk))
        hit[hit] &= uk[i[hit]] == kk[hit]
        pc = np.zeros(len(sel), np.int64)
        pr = np.full(len(sel), np.nan)
        pc[hit] = cnt[i[hit]]
        pr[hit] = zmax[i[hit]] - zmin[i[hit]]
        # missing ring: 0.5 m cells whose centre is within 1 m of the patch centre
        ring = np.zeros(len(sel))
        py, px, pok = grid.idx(cc[:, 0], cc[:, 1])
        offs = [(dy, dx) for dy in range(-2, 3) for dx in range(-2, 3) if (dy * 0.5) ** 2 + (dx * 0.5) ** 2 <= OC["missing_ring_m"] ** 2]
        for dy, dx in offs:
            yy = np.clip(py + dy, 0, ez.shape[0] - 1)
            xx = np.clip(px + dx, 0, ez.shape[1] - 1)
            ring += ((g_cnt[yy, xx] == 0) | ez[yy, xx]).astype(float)
        ring /= len(offs)
        out[prior] = dict(patch=sel, code=c2[sel], slope=sl[sel], count=pc, range=pr, ring_missing=ring, gt_points=R["gt_points"][sel],
                          d=R["mvs_minus_gt_at_gt"][sel], tau=R["tau"][sel], centre=cc)
    return out


def summarize(a):
    res = {}
    for nm, sm in (("all", np.ones(len(a["code"]), bool)), ("gentle_le17", a["slope"] <= 17), ("steep_gt17", a["slope"] > 17)):
        e = {}
        for c in (2, 3):
            m = sm & (a["code"] == c)
            if not m.any():
                e[str(c)] = dict(patches=0)
                continue
            e[str(c)] = dict(patches=int(m.sum()), count_q=[float(x) for x in np.quantile(a["count"][m], [0.25, 0.5, 0.75])],
                             empty_cell_share=round(float((a["count"][m] == 0).mean()), 4),
                             double_layer_share=round(float(np.nanmean(a["range"][m] > OC["double_layer_m"])), 4),
                             ring_missing_mean=round(float(a["ring_missing"][m].mean()), 4), ring_missing_any=round(float((a["ring_missing"][m] > 0).mean()), 4),
                             d_median=round(float(np.nanmedian(a["d"][m])), 4))
        res[nm] = e
    return res


def uls_attributes(sites_X, sites_need, shifts):
    """intensity, return number, number of returns of the needed box GT points of each site (raw ULS laz, matched by position)."""
    import laspy
    bbs = {s: (X[sites_need[s], :2].min(0) - 1, X[sites_need[s], :2].max(0) + 1) for s, X in sites_X.items()}
    keep = {s: dict(x=[], y=[], z=[], it=[], rn=[], nr=[]) for s in sites_X}
    with laspy.open(str(ULS)) as f:
        for pts in f.chunk_iterator(20_000_000):
            x = np.asarray(pts.x) - SHIFT[0]
            y = np.asarray(pts.y) - SHIFT[1]
            for s, (lo, hi) in bbs.items():
                m = (x >= lo[0]) & (x <= hi[0]) & (y >= lo[1]) & (y <= hi[1])
                if m.any():
                    k = keep[s]
                    k["x"].append(x[m]); k["y"].append(y[m]); k["z"].append(np.asarray(pts.z)[m] - SHIFT[2])
                    k["it"].append(np.asarray(pts.intensity)[m]); k["rn"].append(np.asarray(pts.return_number)[m]); k["nr"].append(np.asarray(pts.number_of_returns)[m])
    out = {}
    for s, X in sites_X.items():
        k = keep[s]
        Q = np.column_stack([np.concatenate(k["x"]), np.concatenate(k["y"]), np.concatenate(k["z"]) + shifts[s]])
        idx = np.nonzero(sites_need[s])[0]
        d, j = cKDTree(Q).query(X[idx], distance_upper_bound=OC["match_tolerance_m"], workers=-1)
        ok = np.isfinite(d)
        it, rn, nr = np.concatenate(k["it"]), np.concatenate(k["rn"]), np.concatenate(k["nr"])
        a_it = np.full(len(X), np.nan, np.float32)
        a_rn = np.full(len(X), -1, np.int8)
        a_nr = np.full(len(X), -1, np.int8)
        a_it[idx[ok]] = it[j[ok]]
        a_rn[idx[ok]] = rn[j[ok]]
        a_nr[idx[ok]] = nr[j[ok]]
        m_all = np.zeros(len(X), bool)
        m_all[idx[ok]] = True
        out[s] = dict(intensity=a_it, return_number=a_rn, number_of_returns=a_nr, matched=m_all, needed=sites_need[s])
        log(s, "ULS matched", int(ok.sum()), "of", len(idx), "raw kept", len(Q))
        del Q
    return out


def main():
    T = Timer()
    O = OUT / "obs"
    O.mkdir(parents=True, exist_ok=True)
    (OUT / "defs").mkdir(exist_ok=True)
    Dg, _ = s4.survey_grids()
    grid = s4.Grid(Dg["dtm"].shape)
    res, app_all, Xs, shifts = {}, {}, {}, {}
    for site in SITES:
        D = S0 / "s61/box_gt" / site
        X = np.load(D / "gt_points.npz")["xyz"].astype(np.float64)
        ez = np.load(D / "exclusion_cells.npz")["any"]
        Xs[site] = X
        shifts[site] = json.loads((DR / "s52/box_gt" / site / "gt_summary.json").read_text())["height_alignment"]["shift_m"]
        app = appearance(site, X, grid, ez)
        app_all[site] = app
        res[site] = {p: summarize(a) for p, a in app.items()}
        log(site, "appearance", {p: {k: v["patches"] for k, v in res[site][p]["all"].items()} for p in res[site]}, T.mark(f"app_{site}"))
    # ULS attributes of the GT points owned by roof-like 3 vs 2 patches (ULS label source rows)
    need = {}
    for site in SITES:
        nd = np.zeros(len(Xs[site]), bool)
        for prior in ("LoD2", "ALS"):
            R = np.load(OUT / "regions_v2" / f"regions_ext_v2_{site}_{prior}.npz")
            up = np.ones(len(R["code_ext_v2"]), bool) if site.startswith("B0") else np.zeros(len(R["code_ext_v2"]), bool)
            for name, pt, pa, va, kd in owner_rows(site, prior, up):
                if name == "gt_points":
                    nd[pt[(kd == 1) & np.isin(R["code_ext_v2"][pa], (2, 3))]] = True
        need[site] = nd
    att = uls_attributes(Xs, need, shifts)
    T.mark("uls")
    np.savez_compressed(O / "uls_attributes.npz", **{f"{s}_{k}": v for s, d in att.items() for k, v in d.items()})
    uls_res = {}
    for site in SITES:
        uls_res[site] = {}
        for prior in ("LoD2", "ALS"):
            R = np.load(OUT / "regions_v2" / f"regions_ext_v2_{site}_{prior}.npz")
            uls_patch = np.ones(len(R["code_ext_v2"]), bool) if site.startswith("B0") else np.zeros(len(R["code_ext_v2"]), bool)
            rows = [r_ for r_ in owner_rows(site, prior, uls_patch) if r_[0] == "gt_points"]
            e = {}
            sl, _ = slopes(site, prior)
            for name, pt, pa, va, kd in rows:
                for c in (2, 3):
                    for nm, smask in (("all", np.ones(len(pa), bool)), ("gentle_le17", sl[pa] <= 17), ("steep_gt17", sl[pa] > 17)):
                        m = (kd == 1) & (R["code_ext_v2"][pa] == c) & smask
                        p_ = pt[m]
                        a = att[site]
                        ok = a["matched"][p_]
                        if not ok.any():
                            e[f"{c}_{nm}"] = dict(points=int(m.sum()), matched=0)
                            continue
                        it = a["intensity"][p_][ok]
                        e[f"{c}_{nm}"] = dict(points=int(m.sum()), matched=round(float(ok.mean()), 4), intensity_q=[float(x) for x in np.quantile(it, [0.25, 0.5, 0.75])],
                                              multi_return_share=round(float((a["number_of_returns"][p_][ok] > 1).mean()), 4),
                                              later_return_share=round(float((a["return_number"][p_][ok] > 1).mean()), 4))
            uls_res[site][prior] = e
    T.mark("uls_summary")
    # sections (B173nb_b10, LoD2 v2): five observation-error roof-like patches by owned GT points, > 2 m apart
    R = np.load(OUT / "regions_v2" / "regions_ext_v2_B173nb_b10_LoD2.npz")
    _, nrm = slopes("B173nb_b10", "LoD2")
    cand = np.nonzero((R["code_ext_v2"] == 3) & (R["kind"] == 1) & R["in_eval"])[0]
    cand = cand[np.argsort(-R["gt_points"][cand], kind="stable")]
    chosen = []
    for k in cand:
        c = R["centre"][k]
        if all(np.linalg.norm(c[:2] - R["centre"][j][:2]) > 2.0 for j in chosen):
            chosen.append(int(k))
        if len(chosen) == 5:
            break
    secs = []
    bu = basis()[0]
    for k in chosen:
        n = nrm[k]
        tilt = np.degrees(np.arccos(min(1.0, abs(n[2]))))
        t = n[:2] / np.linalg.norm(n[:2]) if tilt > 5 else bu
        secs.append(dict(patch=k, centre=R["centre"][k].tolist(), t=[float(t[0]), float(t[1])], L=12.0, gt_points=int(R["gt_points"][k]),
                         slope_deg=round(float(tilt), 1), d_mvs_minus_gt=round(float(R["mvs_minus_gt_at_gt"][k]), 3), gt_med=round(float(R["gt_med"][k]), 3)))
    jdump(OUT / "defs/sections_obs.json", dict(rule=OC["sections"], sections=secs, written_before_training_results=True, scientific_verdict=None))
    T.mark("sections")
    # overlays
    V = Views()
    names = {n.rsplit(".", 1)[0]: n for n in V.names}
    shots = [("B173nb_b10", "DJI_20241217091245_0145_D"), ("B173nb_b10", "DJI_20241217091127_0106_D")]
    for site in ("B0_b10", "B173_b0", "R1rep_b10"):
        split = json.loads((S0 / "fork_inputs/s61" / site / "split.json").read_text())["train"]
        R = np.load(OUT / "regions_v2" / f"regions_ext_v2_{site}_LoD2.npz")
        cen = R["centre"][np.isin(R["code_ext_v2"], (2, 3, 0)) & (R["kind"] == 1) & R["in_eval"]].mean(0)
        best, bd = None, 1e9
        for v in split:
            n = names.get(v)
            if n is None or V.tilt(n) > 20:
                continue
            u, vv, z = V.project(n, cen[None, :])
            if z[0] <= 0:
                continue
            dd = np.hypot(u[0] - GRID_W / 2, vv[0] - GRID_H / 2)
            if dd < bd:
                best, bd = v, dd
        shots.append((site, best))
    fig, axs = plt.subplots(len(shots), 2, figsize=(16, 5.9 * len(shots)), constrained_layout=True)
    over = {}
    for i, (site, view) in enumerate(shots):
        n = names[view]
        img = cv2.cvtColor(cv2.resize(cv2.imread(str(DENSE / "images" / n)), (GRID_W, GRID_H), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB)
        C = V.C(n)
        for j, prior in enumerate(("LoD2", "ALS")):
            ax = axs[i, j]
            R = np.load(OUT / "regions_v2" / f"regions_ext_v2_{site}_{prior}.npz")
            m = np.isin(R["code_ext_v2"], (0, 2, 3)) & (R["kind"] == 1) & R["in_eval"]
            P = R["centre"][m]
            code = R["code_ext_v2"][m]
            u, vv, z = V.project(n, P)
            ins = (z > 0) & (u >= 0) & (u < GRID_W) & (vv >= 0) & (vv < GRID_H)
            Vm, Fm = prior_mesh(site, prior)
            sc = MeshScene(Vm, Fm)
            dvec = P - C[None, :]
            dist = np.linalg.norm(dvec, axis=1)
            th = sc.cast(np.broadcast_to(C, P.shape), dvec / dist[:, None])
            vis = ins & (th >= dist - 0.3)
            ax.imshow(img)
            for c in (0, 2, 3):
                mm = vis & (code == c)
                ax.scatter(u[mm], vv[mm], s=0.6, c=COLS[c], linewidths=0, alpha=0.55, rasterized=True)
            if vis.any():
                pad = 30
                ax.set_xlim(max(u[vis].min() - pad, 0), min(u[vis].max() + pad, GRID_W))
                ax.set_ylim(min(vv[vis].max() + pad, GRID_H), max(vv[vis].min() - pad, 0))
            ax.set_xticks([])
            ax.set_yticks([])
            ax.set_title(f"{site} · {PRIOR_KO[prior]} 영역 v2 — {view} (보이는 패치 {int(vis.sum()):,}, 관측 오류 {int((vis & (code == 3)).sum()):,})", fontsize=10)
            over[f"{site}/{prior}/{view}"] = dict(visible=int(vis.sum()), observation_error=int((vis & (code == 3)).sum()))
    fig.legend(handles=[Line2D([], [], marker="s", ls="", color=COLS[c], label=NAMES[c], markersize=9) for c in (3, 2, 0)], loc="lower center", ncol=3, fontsize=11,
               bbox_to_anchor=(0.5, -0.02))
    fig.suptitle("연직 사진 위의 관측 오류 영역(노랑), 지지 일치 영역(초록), 참값 결여 영역(회색) — 지붕류 패치, 영역 v2", fontsize=13, x=0.01, ha="left")
    fig.savefig(OUT / "figs/obs_overlay.png", dpi=80, bbox_inches="tight")
    plt.close(fig)
    T.mark("overlay")
    jdump(O / "obs_check.json", dict(rule=OC, appearance=res, uls=uls_res, overlays=over, shots=shots, height_alignment_shift_m=shifts, seconds=T.marks,
                                    scientific_verdict=None))
    # per-patch features for the rule (pre-training data)
    np.savez_compressed(O / "appearance_patches.npz", **{f"{s}_{p}_{k}": v for s, d in app_all.items() for p, a in d.items() for k, v in a.items()})
    print("obs check done", T.marks)


def sections_steep():
    """added after the first section figure (purpose: the first five, by GT point count, all fell on one flat glass roof; most of
    the region lies on steep sawtooth faces): the same rule restricted to faces steeper than 17 degrees."""
    R = np.load(OUT / "regions_v2" / "regions_ext_v2_B173nb_b10_LoD2.npz")
    sl, nrm = slopes("B173nb_b10", "LoD2")
    cand = np.nonzero((R["code_ext_v2"] == 3) & (R["kind"] == 1) & R["in_eval"] & (sl > 17))[0]
    cand = cand[np.argsort(-R["gt_points"][cand], kind="stable")]
    chosen = []
    for k in cand:
        c = R["centre"][k]
        if all(np.linalg.norm(c[:2] - R["centre"][j][:2]) > 2.0 for j in chosen):
            chosen.append(int(k))
        if len(chosen) == 5:
            break
    secs = []
    for k in chosen:
        n = nrm[k]
        t = n[:2] / np.linalg.norm(n[:2])
        secs.append(dict(patch=k, centre=R["centre"][k].tolist(), t=[float(t[0]), float(t[1])], L=12.0, gt_points=int(R["gt_points"][k]),
                         slope_deg=round(float(sl[k]), 1), d_mvs_minus_gt=round(float(R["mvs_minus_gt_at_gt"][k]), 3), gt_med=round(float(R["gt_med"][k]), 3)))
    jdump(OUT / "defs/sections_obs_steep.json", dict(rule="as sections_obs, restricted to faces steeper than 17 degrees; added after the first section figure (record)",
                                                     sections=secs, scientific_verdict=None))
    print([(s_["patch"], s_["slope_deg"], s_["d_mvs_minus_gt"]) for s_ in secs])


if __name__ == "__main__":
    import sys
    if sys.argv[1:2] == ["--sections-steep"]:
        sections_steep()
    else:
        main()
