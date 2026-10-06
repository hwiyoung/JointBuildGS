"""PHD-MAIN-METRICS-TRIAL-v1 4.3 preparation (jointbuildgs:dev, CPU): everything the metrics read that does not depend on a
training result, fixed before any metric (definitions = configs metrics_trial_v1.json). Site = B173nb_b10.

  python prep_mt.py

defs/gt_classes.npz   GT points of the box: use (evaluation range, not excluded), roof, wall, edge band and its height range
                      (roof points), building surface, changed (B173 wings, stage 0) -- the stage-0 quick-check rules
defs/rows_<prior>.npz GT ownership rows that count (roof points through roof-like patches, wall points through wall-like
                      patches): point, patch, value (GT - prior along the line), kind, extended region code, line direction D,
                      offset of the wrong data s_W, tau, prior-face normal n (roof-like up, wall-like outward), face slope;
                      and per patch of the spread regions (3, 11, 12, 13, 14): the W centre and its line direction
defs/unseen.npz       B173 unseen wall patches (LoD2 store): index, centre, outward normal, inferred and true labels, owned GT
                      points (use)
defs/top_raster.npz   highest GT surface per 1 m cell (3 x 3 maximum), the floater reference
defs/bsurf.npz        building-surface cells (0.5 m survey grid) and the M3C2 core points with their normals; the GT cloud of
                      the building surface thinned to 0.05 m
defs/sections.json    representative section per prior and size bin
defs/prior_<prior>.npz  the registered prior surface put in place of the result (LoD2 without bottom faces; ALS TIN)
scientific_verdict: null."""
import json

import numpy as np
from matplotlib.path import Path as MPath
from shapely.geometry import Point, Polygon as SPoly
from shapely.ops import unary_union
from shapely.prepared import prep

from mt_common import DR, MCFG, OUT, S0, SITE, B173, Timer, basis_u, boxes, in_eval_uv, jdump, log  # sets the paths first
import s04_gt_v6 as s4  # noqa: E402
from src.phd.metrics_v1 import band, cloud
from src.phd.metrics_v1.gauss import TopRaster
from src.phd.metrics_v1.surface import MeshScene

WINGS = ["DEBY_LOD2_4959326_66ac9a84-cf24-4ba6-b5b9-9427d0c20e8b_2", "DEBY_LOD2_4959326_f94b116f-de50-4bff-8e53-0c6a023b9d2f_2"]
SPREAD_CODES = (3, 11, 12, 13, 14)


def prior_mesh(prior):
    md = DR / "s02_box" / SITE
    sh = np.asarray(json.loads((S0 / "s61/box" / SITE / prior / "summary.json").read_text())["registration"]["shift_applied"], np.float64)
    if prior == "LoD2":
        m = np.load(md / "lod2_mesh.npz")
        F = m["F"][m["tri_type"] != 2]
        return m["V"] + sh, F, sh
    m = np.load(md / "als_mesh.npz")
    return m["V"] + sh, m["F"], sh


def main():
    T = Timer()
    D = OUT / "defs"
    D.mkdir(parents=True, exist_ok=True)
    bx = boxes()["B173nb"]
    md = DR / "s02_box" / SITE
    # ---------------------------------------------------------------- GT classes (stage-0 quick check rules)
    g = np.load(S0 / "s61/box_gt" / SITE / "gt_points.npz")
    X = g["xyz"].astype(np.float64)
    multi = g["multi"]
    ez = np.load(S0 / "s61/box_gt" / SITE / "exclusion_cells.npz")["any"]
    Dg, _ = s4.survey_grids()
    grid = s4.Grid(Dg["dtm"].shape)
    iy, ix, ok = grid.idx(X[:, 0], X[:, 1])
    excl = ok & ez[iy, ix]
    inev = in_eval_uv(X, bx)
    vert = s4.vertical_points(X) & ~multi
    fp = json.loads((md / "footprints.json").read_text())["footprints"]
    infp = np.zeros(len(X), bool)
    for r in fp:
        infp |= MPath(np.asarray(r["ring_local"])).contains_points(X[:, :2])
    use = inev & ~excl
    roof = use & infp & ~vert
    wall = use & vert
    m = np.load(md / "lod2_mesh.npz")
    tab = json.loads((md / "lod2_surfaces.json").read_text())["surfaces"]
    tabd = {r["ext"]: r for r in tab}
    ext = [r["ext"] for r in tab if r["gml"] in WINGS]
    tris = m["F"][np.isin(m["tri_surface"], ext)]
    wing_poly = unary_union([SPoly(m["V"][t][:, :2]) for t in tris]).buffer(0)
    wing = np.zeros(len(X), bool)
    for gp in getattr(wing_poly, "geoms", [wing_poly]):
        wing |= MPath(np.asarray(gp.exterior.coords)).contains_points(X[:, :2])
    changed = roof & wing
    log("GT", len(X), "use", int(use.sum()), "roof", int(roof.sum()), "wall", int(wall.sum()), "changed", int(changed.sum()))
    # edge band of the roof points: range of the heights of all box GT points within 0.5 m
    eb = MCFG["edge_band"]
    ir = np.nonzero(roof)[0]
    inb, rng = band.edge_band(X, X[ir], eb["radius_m"], eb["height_range_m"], eb["raster_cell_m"])
    in_band = np.zeros(len(X), bool)
    in_band[ir] = inb
    band_range = np.full(len(X), np.nan, np.float32)
    band_range[ir] = rng
    log("edge band", int(inb.sum()), "of", len(ir), T.mark("band"))
    # building surface: 0.5 m survey cells within 2 m of a footprint, holding a 'use' point
    buf = prep(unary_union([SPoly(r["ring_local"]) for r in fp]).buffer(2.0))
    key = iy.astype(np.int64) * grid.nx + ix
    ukeys = np.unique(key[use])
    cy, cx = np.divmod(ukeys, grid.nx)
    # cell centre, local frame (Grid: E = x + 690953, N = y + 5336071, e0 690700, n0 5335820, 0.5 m)
    ccx = grid.e0 + (cx + 0.5) * grid.res - 690953.0
    ccy = grid.n0 + (cy + 0.5) * grid.res - 5336071.0
    inbuf = np.array([buf.contains(Point(a, b)) for a, b in zip(ccx, ccy)])
    bs_keys = ukeys[inbuf]
    bs = use & np.isin(key, bs_keys)
    log("building surface cells", len(bs_keys), "GT points", int(bs.sum()), T.mark("bsurf"))
    np.savez_compressed(D / "gt_classes.npz", xyz=X.astype(np.float32), use=use, roof=roof, wall=wall, infp=infp, in_band=in_band,
                        band_range=band_range, bs=bs, changed=changed, excl=excl)
    # ---------------------------------------------------------------- top raster (floaters)
    lo = X[:, :2].min(0) - 5.0
    hi = X[:, :2].max(0) + 5.0
    fl = MCFG["floaters"]
    TR = TopRaster(X, lo, hi, cell=fl["cell_m"], k=1, fallback=float(X[inev, 2].max()))
    np.savez_compressed(D / "top_raster.npz", grid=TR.grid, lo=TR.lo, cell=TR.cell, empty=TR.empty, fallback=TR.fallback,
                        eval_u=np.array(bx["eval_u"]), eval_v=np.array(bx["eval_v"]))
    # ---------------------------------------------------------------- rows and W centres per prior
    secs = {}
    for prior in ("LoD2", "ALS"):
        R = np.load(OUT / "regions_ext" / f"regions_ext_{SITE}_{prior}.npz")
        U = np.load(S0 / "s61/box" / SITE / prior / "units.npz")
        assert np.array_equal(R["centre"], U["loc_center"]), "region file and store differ"
        o = np.load(S0 / "s61/box_gt" / SITE / f"gt_owner_{prior}.npz")
        pt, pa, va, kd = o["point"], o["patch"].astype(np.int64), o["value"].astype(np.float64), o["kind"]
        keep = use[pt] & (((kd == 1) & roof[pt]) | ((kd == 2) & wall[pt]))
        pt, pa, va, kd = pt[keep], pa[keep], va[keep], kd[keep]
        code = R["code_ext"][pa]
        # patch normals: roof-like = cross(t1, t2) up (equals the face normal of LoD2 faces); wall-like = LoD2 outward normal
        n_p = np.cross(U["loc_t1"], U["loc_t2"])
        n_p /= np.maximum(np.linalg.norm(n_p, axis=1, keepdims=True), 1e-12)
        n_p *= np.where(n_p[:, 2:3] < 0, -1.0, 1.0)
        if prior == "LoD2":
            se = U["surf_ext"][U["loc_surface"]]
            wl = U["loc_kind"] == 2
            n_p[wl] = np.array([tabd[int(e)]["normal"] for e in se[wl]], np.float64)
        Dp = np.where((U["loc_kind"] == 2)[:, None], n_p, np.array([0.0, 0.0, 1.0]))
        mvs = R["mvs_minus_prior"].astype(np.float64)
        sW = np.where(np.isin(code, (11, 12, 13, 14)), -va, 0.0)
        sW = np.where(code == 3, -va + mvs[pa], sW)
        tau = R["tau"][pa]
        slope = np.degrees(np.arccos(np.clip(np.abs(n_p[pa, 2]), 0, 1))).astype(np.float32)
        pw = np.nonzero(np.isin(R["code_ext"], SPREAD_CODES))[0]
        Wc = U["loc_center"][pw] + np.where(R["code_ext"][pw] == 3, mvs[pw], 0.0)[:, None] * Dp[pw]
        np.savez_compressed(D / f"rows_{prior}.npz", point=pt, patch=pa, value=va.astype(np.float32), kind=kd, code=code,
                            D=Dp[pa].astype(np.float32), sW=sW.astype(np.float32), tau=tau.astype(np.float32), n=n_p[pa].astype(np.float32),
                            slope=slope, w_patch=pw, w_centre=Wc, w_code=R["code_ext"][pw], w_kind=U["loc_kind"][pw],
                            w_gt_med=R["gt_med"][pw], w_tau=R["tau"][pw])
        log(prior, "rows", len(pt), {int(c): int((code == c).sum()) for c in np.unique(code)})
        # representative sections: per bin, the prior-wrong roof-like patch owning the most GT points (|gt_med| / tau in the bin)
        bins = MCFG["size_curve"]["bins_tau"]
        cand = (R["code_ext"] == 11)
        ratio = np.abs(R["gt_med"].astype(np.float64)) / R["tau"].astype(np.float64)
        gp = R["gt_points"]
        sec = {}
        for lo_b, hi_b in bins:
            name = f"{lo_b:g}-{'' if hi_b is None else f'{hi_b:g}'}"
            inbin = cand & (ratio >= lo_b) & ((ratio < hi_b) if hi_b is not None else True)
            for kv in (1, 2):
                mm = inbin & (U["loc_kind"] == kv)
                if mm.any():
                    k = int(np.nonzero(mm)[0][np.argmax(gp[mm])])
                    nn = n_p[k]
                    if kv == 1:
                        tilt = np.degrees(np.arccos(min(1.0, abs(nn[2]))))
                        t = nn[:2] / np.linalg.norm(nn[:2]) if tilt > 5.0 else basis_u()
                    else:
                        t = nn[:2] / np.linalg.norm(nn[:2])
                    sec[name] = dict(patch=k, kind=int(kv), centre=U["loc_center"][k].tolist(), t=[float(t[0]), float(t[1])], L=12.0,
                                     ratio=round(float(ratio[k]), 3), gt_med=round(float(R["gt_med"][k]), 3), gt_points=int(gp[k]),
                                     patches_in_bin=int(inbin.sum()))
                    break
            else:
                sec[name] = None
        secs[prior] = sec
        # the registered prior surface as a result
        V, F, sh = prior_mesh(prior)
        np.savez_compressed(D / f"prior_{prior}.npz", V=V, F=F, shift=sh)
    jdump(D / "sections.json", dict(rule=MCFG["size_curve"]["representative_sections"], sections=secs, written_before_metrics=True,
                                    scientific_verdict=None))
    # ---------------------------------------------------------------- unseen B173 wall patches
    R = np.load(OUT / "regions_ext" / f"regions_ext_{SITE}_LoD2.npz")
    U = np.load(S0 / "s61/box" / SITE / "LoD2" / "units.npz")
    un = np.nonzero(R["unseen_label_inferred"] > -2)[0]
    se = U["surf_ext"][U["loc_surface"]][un]
    nrm = np.array([tabd[int(e)]["normal"] for e in se], np.float64)
    o = np.load(S0 / "s61/box_gt" / SITE / "gt_owner_LoD2.npz")
    sel = np.isin(o["patch"], un) & use[o["point"]]
    np.savez_compressed(D / "unseen.npz", patch=un, centre=U["loc_center"][un], normal=nrm, surf_ext=se,
                        label_inferred=R["unseen_label_inferred"][un], label_true=R["label"][un], tau=R["tau"][un],
                        gt_point=o["point"][sel], gt_patch=o["patch"][sel], gt_value=o["value"][sel])
    log("unseen patches", len(un), "GT rows (use)", int(sel.sum()), "points", len(np.unique(o["point"][sel])))
    # ---------------------------------------------------------------- building surface: thinned GT, M3C2 core points and normals
    sm = MCFG["summary_numbers"]["m3c2"]
    Xb = X[bs]
    thin = Xb[cloud.voxel_thin(Xb, 0.05)]
    core = Xb[cloud.voxel_thin(Xb, 0.5)]
    nrm_c = cloud.pca_normals(core, thin, sm["normal_scale_m"] / 2.0, min_n=10)
    ok_n = np.isfinite(nrm_c).all(1)
    up = ok_n & (np.abs(nrm_c[:, 2]) >= 0.5)
    nrm_c[up] *= np.sign(nrm_c[up, 2:3])
    side = ok_n & ~up
    Vl, Fl = m["V"], m["F"]
    wtri = np.nonzero(m["tri_type"] != 2)[0]
    n_tri = np.zeros((len(Fl), 3))
    for e, r in tabd.items():
        n_tri[m["tri_surface"] == e] = r["normal"]
    wtri = wtri[np.abs(n_tri[wtri, 2]) < 0.5]
    if side.any() and len(wtri):
        sc = MeshScene(Vl, Fl[wtri])
        ans = sc.sc.compute_closest_points(sc.o3d.core.Tensor(core[side].astype(np.float32)))
        prim = ans["primitive_ids"].numpy().astype(np.int64)
        on = n_tri[wtri[prim]]
        flip = (nrm_c[side] * on).sum(1) < 0
        nrm_c[np.nonzero(side)[0][flip]] *= -1
    np.savez_compressed(D / "bsurf.npz", keys=bs_keys, nx=grid.nx, e0=grid.e0, n0=grid.n0, res=grid.res, gt_thin=thin.astype(np.float32),
                        core=core, core_normal=nrm_c, core_ok=ok_n, core_up=up)
    log("bsurf GT", len(Xb), "thin", len(thin), "core", len(core), "normals ok", int(ok_n.sum()), "up", int(up.sum()), T.mark("m3c2_core"))
    jdump(D / "defs.json", dict(site=SITE, gt_points=len(X), use=int(use.sum()), roof=int(roof.sum()), wall=int(wall.sum()), changed=int(changed.sum()),
                                edge_band_roof_points=int(in_band.sum()), building_surface_cells=len(bs_keys), building_surface_points=int(bs.sum()),
                                m3c2_core=len(core), seconds=T.marks, config_sha256_note="see progress.md", scientific_verdict=None))
    print("prep done", T.mark("all"))


if __name__ == "__main__":
    main()
