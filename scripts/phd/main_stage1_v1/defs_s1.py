"""PHD-MAIN-STAGE1-v1 3.3-3.4 and the evaluation definitions of the four sites (jointbuildgs:dev, CPU; pre-training data only;
definitions = configs main_stage1_v1.json 'thinning', 'gate_samples'; the trial's prep_mt.py rules generalised to every site and to
B0's two GT sources, on the v3 GT and regions).

  python defs_s1.py <site> [...]      -> /out/defs/<site>/...
  python defs_s1.py samples           the gate sample counts of 3.3 -> /out/defs/gate_samples.json, .md

defs/<site>/gt_classes.npz   per GT source (uls; B0 also primary): xyz, use (evaluation range, not excluded), vertical-surface
                             points, in a LoD2 footprint, roof (use & footprint & not vertical), wall (use & vertical)
defs/<site>/rows_<prior>.npz ownership rows that count (roof points through roof-like patches, wall points through wall-like
                             patches; the patch's label source): src (0 uls, 1 primary), point, patch, value (GT - prior), kind,
                             code (v3), line direction D, prior-face normal n, slope, tau, s_W (v2 rule), z_MVS at the point,
                             thin (3.4), in_band_v2 / band_adj (roof rows), suspect, premise flags of the patch
defs/<site>/top_raster.npz   highest GT surface per 1 m cell (3 x 3 maximum), the floater reference (uls)
defs/<site>/bsurf.npz        building-surface cells and M3C2 core points (uls), as the trial
defs/<site>/prior_<prior>.npz the registered prior surface as a result (LoD2 without bottom faces; ALS TIN)
defs/<site>/unseen.npz       B173 sites: the B173 unseen wall patches (v3 split)
scientific_verdict: null."""
import json
import sys

import numpy as np
from matplotlib.path import Path as MPath
from shapely.geometry import Point, Polygon as SPoly
from shapely.ops import unary_union
from shapely.prepared import prep

from s1_common import DR, OUT, S0, SCFG1, SITES, Timer, boxes, in_eval_uv, jdump, label_source, log, owner_rows
import s04_gt_v6 as s4
from src.phd.metrics_v3 import band, cloud, thin
from src.phd.metrics_v3.gauss import TopRaster

GT3 = OUT / "v3/box_gt"
EB = dict(radius_m=0.5, height_range_m=0.3, slope_cap_deg=80)          # the fix's edge_band_v2
SRC = {"gt_points": 0, "gt_primary": 1}
TS = SCFG1["thinning"]


def classes(site):
    D = GT3 / site
    g = np.load(D / "gt_points.npz")
    srcs = {"gt_points": (g["xyz"].astype(np.float64), g["multi"])}
    if site.startswith("B0"):
        p = np.load(D / "gt_primary.npz")["xyz"].astype(np.float64)
        srcs["gt_primary"] = (p, np.zeros(len(p), bool))
    ez = np.load(D / "exclusion_cells.npz")["any"]
    Dg, _ = s4.survey_grids()
    grid = s4.Grid(Dg["dtm"].shape)
    bx = boxes()[SITES[site]]
    fp = json.loads((DR / "s02_box" / site / "footprints.json").read_text())["footprints"]
    out = {}
    for name, (X, multi) in srcs.items():
        iy, ix, ok = grid.idx(X[:, 0], X[:, 1])
        excl = ok & ez[iy, ix]
        inev = in_eval_uv(X, bx)
        vert = s4.vertical_points(X) & ~multi
        infp = np.zeros(len(X), bool)
        for r in fp:
            infp |= MPath(np.asarray(r["ring_local"])).contains_points(X[:, :2])
        use = inev & ~excl
        out[name] = dict(xyz=X, use=use, vert=vert, infp=infp, roof=use & infp & ~vert, wall=use & vert, excl=excl, grid=grid, key=None)
    return out, grid, fp


def patch_geometry(site, prior):
    U = np.load(S0 / "s61/box" / site / prior / "units.npz")
    n_p = np.cross(U["loc_t1"], U["loc_t2"])
    n_p /= np.maximum(np.linalg.norm(n_p, axis=1, keepdims=True), 1e-12)
    n_p *= np.where(n_p[:, 2:3] < 0, -1.0, 1.0)
    se = U["surf_ext"][U["loc_surface"]]
    if prior == "LoD2":
        tab = {t["ext"]: t for t in json.loads((DR / "s02_box" / site / "lod2_surfaces.json").read_text())["surfaces"]}
        wl = U["loc_kind"] == 2
        n_p[wl] = np.array([tab[int(e)]["normal"] for e in se[wl]], np.float64)
    Dp = np.where((U["loc_kind"] == 2)[:, None], n_p, np.array([0.0, 0.0, 1.0]))
    return U, n_p, Dp, se


def prior_mesh(site, prior):
    md = DR / "s02_box" / site
    sh = np.asarray(json.loads((S0 / "s61/box" / site / prior / "summary.json").read_text())["registration"]["shift_applied"], np.float64)
    if prior == "LoD2":
        m = np.load(md / "lod2_mesh.npz")
        return m["V"] + sh, m["F"][m["tri_type"] != 2], sh
    m = np.load(md / "als_mesh.npz")
    return m["V"] + sh, m["F"], sh


def rows_of(site, prior, C):
    R = np.load(OUT / "regions_v3" / f"regions_ext_v3_{site}_{prior}.npz")
    U, n_p, Dp, se = patch_geometry(site, prior)
    assert np.array_equal(R["centre"], U["loc_center"]), "region file and store differ"
    zm_f = np.load(OUT / "regions_v3" / f"mvs_at_gt_{site}.npz")
    parts = []
    for name, pt, pa, va, kd in owner_rows(GT3, site, prior, label_source(GT3, site, prior, len(R["code_ext_v3"]))):
        c = C[name]
        keep = c["use"][pt] & (((kd == 1) & c["roof"][pt]) | ((kd == 2) & c["wall"][pt]))
        pt, pa, va, kd = pt[keep], pa[keep].astype(np.int64), va[keep].astype(np.float64), kd[keep]
        X = c["xyz"]
        zf = np.full(len(X), np.nan)
        if f"{name}_index" in zm_f.files:
            zf[zm_f[f"{name}_index"]] = zm_f[f"{name}_z_mvs"]
        code = R["code_ext_v3"][pa]
        kept = R["v1_kept"][pa]
        d = R["mvs_minus_gt_at_gt"].astype(np.float64)[pa]
        mvs_prior = R["mvs_minus_prior"].astype(np.float64)[pa]
        sW = np.zeros(len(pt))
        pw = np.isin(code, (11, 12, 13, 14))
        sW[pw] = -va[pw]
        c3 = code == 3
        at_gt = zf[pt] - X[pt, 2]
        v2_3 = c3 & ~kept & (kd == 1)
        sW[v2_3] = np.where(np.isfinite(at_gt[v2_3]), at_gt[v2_3], d[v2_3])
        k3 = c3 & ~v2_3
        sW[k3] = -va[k3] + mvs_prior[k3]
        slope = np.degrees(np.arccos(np.clip(np.abs(n_p[pa, 2]), 0, 1)))
        # thinning (3.4): roof rows in horizontal 0.1 m cells, wall rows in 0.1 m cells on the wall plane per LoD2 surface
        th = np.zeros(len(pt), bool)
        r_ = kd == 1
        th[r_] = thin.keep_nearest(X[pt[r_], :2], 0.1)
        w_ = kd == 2
        if w_.any():
            th[w_] = thin.keep_nearest(thin.wall_coords(X[pt[w_]], n_p[pa[w_]]), 0.1, group=se[pa[w_]])
        # band v2 of the roof rows (the source's own points as X_all, as the fix used the box GT of the source)
        inb = np.zeros(len(pt), bool)
        adj = np.full(len(pt), np.nan)
        if r_.any():
            ib, ad = band.edge_band_v2(X, X[pt[r_]], slope[r_], EB["radius_m"], EB["height_range_m"], 0.1, EB["slope_cap_deg"])
            inb[r_], adj[r_] = ib, ad
        parts.append(dict(src=np.full(len(pt), SRC[name], np.int8), point=pt, patch=pa, value=va.astype(np.float32), kind=kd, code=code,
                          D=Dp[pa].astype(np.float32), n=n_p[pa].astype(np.float32), slope=slope.astype(np.float32), tau=R["tau"][pa].astype(np.float32),
                          sW=sW.astype(np.float32), z_mvs=zf[pt].astype(np.float32), thin=th, in_band_v2=inb, band_adj=adj.astype(np.float32),
                          surf_ext=se[pa], suspect=R["gt_suspect"][pa], premise_violation=R["premise_violation"][pa],
                          premise_band=R["premise_band"][pa], obs_within=R["obs_within_threshold"][pa]))
    rows = {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}
    # W centres per patch of the spread regions (v2 rule, as the fix's metrics_mf.Inputs)
    c2p = R["code_ext_v3"]
    wpat = np.nonzero(np.isin(c2p, (3, 11, 12, 13, 14)))[0]
    wc = U["loc_center"][wpat].copy()
    k = c2p[wpat] == 3
    kept_p = R["v1_kept"][wpat]
    shift = np.where(k & ~kept_p & (U["loc_kind"][wpat] == 1), R["gt_med"][wpat].astype(np.float64) + np.nan_to_num(R["mvs_minus_gt_at_gt"][wpat].astype(np.float64)), 0.0)
    shift = np.where(k & (kept_p | (U["loc_kind"][wpat] != 1)), R["mvs_minus_prior"][wpat].astype(np.float64), shift)
    wc = wc + shift[:, None] * Dp[wpat]
    wdist = np.where(np.isin(c2p[wpat], (11, 12, 13, 14)), np.abs(R["gt_med"][wpat].astype(np.float64)),
                     np.abs(np.where(kept_p, R["mvs_minus_prior"][wpat] - R["gt_med"][wpat], R["mvs_minus_gt_at_gt"][wpat]).astype(np.float64)))
    rows.update(w_patch=wpat, w_centre=wc, w_code=c2p[wpat], w_kind=U["loc_kind"][wpat], w_dist=wdist)
    return rows


def site_defs(site):
    T = Timer()
    D = OUT / "defs" / site
    D.mkdir(parents=True, exist_ok=True)
    C, grid, fp = classes(site)
    np.savez_compressed(D / "gt_classes.npz", **{f"{k}_{n}": v[k] if k != "xyz" else v[k].astype(np.float32) for n, v in C.items()
                                                 for k in ("xyz", "use", "vert", "infp", "roof", "wall", "excl")})
    log(site, {n: dict(points=len(v["xyz"]), use=int(v["use"].sum()), roof=int(v["roof"].sum()), wall=int(v["wall"].sum())) for n, v in C.items()}, T.mark("classes"))
    for prior in ("LoD2", "ALS"):
        rows = rows_of(site, prior, C)
        np.savez_compressed(D / f"rows_{prior}.npz", **rows)
        log(site, prior, "rows", len(rows["point"]), "thin", int(rows["thin"].sum()), T.mark(f"rows_{prior}"))
        V, F, sh = prior_mesh(site, prior)
        np.savez_compressed(D / f"prior_{prior}.npz", V=V, F=F, shift=sh)
    # top raster (floaters) and the building surface / M3C2 core points: the ULS points (trial rules)
    X = C["gt_points"]["xyz"]
    inev = in_eval_uv(X, boxes()[SITES[site]])
    lo = X[:, :2].min(0) - 5.0
    hi = X[:, :2].max(0) + 5.0
    TR = TopRaster(X, lo, hi, cell=1.0, k=1, fallback=float(X[inev, 2].max()))
    bx = boxes()[SITES[site]]
    np.savez_compressed(D / "top_raster.npz", grid=TR.grid, lo=TR.lo, cell=TR.cell, empty=TR.empty, fallback=TR.fallback,
                        eval_u=np.array(bx["eval_u"]), eval_v=np.array(bx["eval_v"]))
    use = C["gt_points"]["use"]
    iy, ix, ok = grid.idx(X[:, 0], X[:, 1])
    buf = prep(unary_union([SPoly(r["ring_local"]) for r in fp]).buffer(2.0))
    key = iy.astype(np.int64) * grid.nx + ix
    ukeys = np.unique(key[use])
    cy, cx = np.divmod(ukeys, grid.nx)
    ccx = grid.e0 + (cx + 0.5) * grid.res - 690953.0
    ccy = grid.n0 + (cy + 0.5) * grid.res - 5336071.0
    inbuf = np.array([buf.contains(Point(a, b)) for a, b in zip(ccx, ccy)])
    bs_keys = ukeys[inbuf]
    bs = use & np.isin(key, bs_keys)
    Xb = X[bs]
    thin_b = Xb[cloud.voxel_thin(Xb, 0.05)]
    core = Xb[cloud.voxel_thin(Xb, 0.5)]
    nrm_c = cloud.pca_normals(core, thin_b, 0.5, min_n=10)
    ok_n = np.isfinite(nrm_c).all(1)
    up = ok_n & (np.abs(nrm_c[:, 2]) >= 0.5)
    nrm_c[up] *= np.sign(nrm_c[up, 2:3])
    side = ok_n & ~up
    m = np.load(DR / "s02_box" / site / "lod2_mesh.npz")
    tabd = {t["ext"]: t for t in json.loads((DR / "s02_box" / site / "lod2_surfaces.json").read_text())["surfaces"]}
    n_tri = np.zeros((len(m["F"]), 3))
    for e, r in tabd.items():
        n_tri[m["tri_surface"] == e] = r["normal"]
    wtri = np.nonzero((m["tri_type"] != 2) & (np.abs(n_tri[:, 2]) < 0.5))[0]
    if side.any() and len(wtri):
        from src.phd.metrics_v3.surface import MeshScene
        sc = MeshScene(m["V"], m["F"][wtri])
        ans = sc.sc.compute_closest_points(sc.o3d.core.Tensor(core[side].astype(np.float32)))
        prim = ans["primitive_ids"].numpy().astype(np.int64)
        flip = (nrm_c[side] * n_tri[wtri[prim]]).sum(1) < 0
        nrm_c[np.nonzero(side)[0][flip]] *= -1
    np.savez_compressed(D / "bsurf.npz", keys=bs_keys, nx=grid.nx, e0=grid.e0, n0=grid.n0, res=grid.res, gt_thin=thin_b.astype(np.float32),
                        core=core, core_normal=nrm_c, core_ok=ok_n, core_up=up, bs=bs)
    T.mark("bsurf")
    if site in ("B173nb_b10", "B173_b0"):
        R = np.load(OUT / "regions_v3" / f"regions_ext_v3_{site}_LoD2.npz")
        U, n_p, Dp, se = patch_geometry(site, "LoD2")
        un = np.nonzero(R["unseen_label_inferred"] > -2)[0]
        o = np.load(GT3 / site / "gt_owner_LoD2.npz")
        sel = np.isin(o["patch"], un) & use[o["point"]]
        np.savez_compressed(D / "unseen.npz", patch=un, centre=U["loc_center"][un], normal=n_p[un], surf_ext=se[un],
                            label_inferred=R["unseen_label_inferred"][un], label_true=R["label"][un], tau=R["tau"][un],
                            gt_point=o["point"][sel], gt_patch=o["patch"][sel], gt_value=o["value"][sel])
    jdump(D / "defs.json", dict(site=site, sources={n: dict(points=len(v["xyz"]), use=int(v["use"].sum()), roof=int(v["roof"].sum()), wall=int(v["wall"].sum()))
                                                    for n, v in C.items()}, building_surface_cells=len(bs_keys), m3c2_core=len(core),
                                seconds=T.marks, scientific_verdict=None))
    print(site, "defs done", T.marks)


def samples():
    GS = SCFG1["gate_samples"]
    out, md = {}, []
    for site in SITES:
        for prior in ("LoD2", "ALS"):
            r = np.load(OUT / "defs" / site / f"rows_{prior}.npz")
            th = r["thin"]
            code = r["code"]
            big = np.abs(r["sW"]) >= 0.2
            c = {
                "1": int((th & (code == 11) & big).sum()),
                "2": int((th & (code == 3) & r["obs_within"] & big).sum()),
                "3": int((th & (code == 2) & (r["kind"] == 1) & ~r["in_band_v2"] & (r["slope"] <= 17.0)).sum()) if prior == "LoD2" else None,
                "4": int((th & r["premise_band"]).sum()),
            }
            unthin = {"1": int(((code == 11) & big).sum()), "2": int(((code == 3) & r["obs_within"] & big).sum()), "4": int(r["premise_band"].sum())}
            out[f"{site}/{prior}"] = dict(thinned=c, unthinned=unthin, gate_unit=site != "B173_b0",
                                         planned_undecidable=[k for k, v in c.items() if v is not None and v < GS["minimum"]])
    jdump(OUT / "defs" / "gate_samples.json", dict(rule=GS, units=out, scientific_verdict=None))
    md.append("| 지역 · 사전 정보 | 조건 1 사전 정보 오류 | 조건 2 관측 오류 문턱 이내 | 조건 3 지지 일치 완만한 지붕 | 조건 4 전제 위배 둘레 |")
    md.append("|---|---|---|---|---|")
    for k, v in out.items():
        cells = [("—" if v["thinned"][c] is None else (f"{v['thinned'][c]:,}" + (" (판별 불가 예정)" if c in v["planned_undecidable"] else ""))) for c in ("1", "2", "3", "4")]
        md.append(f"| {k.replace('/', ' · ')}{'' if v['gate_unit'] else ' (보고만)'} | " + " | ".join(cells) + " |")
    (OUT / "defs" / "gate_samples.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    if sys.argv[1] == "samples":
        samples()
    else:
        for s in sys.argv[1:]:
            site_defs(s)
