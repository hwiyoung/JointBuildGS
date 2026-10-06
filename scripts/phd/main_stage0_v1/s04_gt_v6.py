"""PHD-MAIN-STAGE0-v1 s04 v6 (jointbuildgs:dev): ground truth and true labels of a range / box = the discard task's s04_gt.py
(GT rules v5, locked) with the patch store of the v6 stage 1: the units.npz store is the one moved with the registered prior
(frame_shift = the run's registration shift, checked), so a GT point projected onto the registered prior is looked up in the
moved store (v5 used the unmoved store), and the exclusion test uses the moved patch centres (v5: unmoved centre + shift, the
same point). New output: gt_owner_<prefix><prior>.npz = for every GT point that counts in a label, its patch and value (the
quick check of the stage-0 trainings splits GT points by the patches' regions). Options of the discard task:
  --prep-gt-dir <dir>  the evaluation exclusion cells of the prep measure (v1.1) are used unchanged; the ones computed here are
                       only compared with them (configs discard_v1 'ground_truth')
  --gt-from <dir>      labels only: GT points, exclusion cells and alignment of another s04 run (B0 conditions: the 5.2 B0 GT)
  --no-depth           skip the per-view GT depth of the prep case 3 (not used here)

  python s04_gt.py <range_id> [--mesh-sub s02] [--stage1-sub s52/s03] [--out-sub s52/gt] [--views-file /prep/step01/views.json]
         [--views-key train] [--views-list <json>] [--depth-views 40] [--mvs current|<workspace>] [--prep-gt-dir d] [--gt-from d] [--no-depth]

1. ULS nadir points of range + margin; transient returns removed (ULS-only: > 1.5 m above both MVS and ALS 2022 DSM cells;
   points above max + 0.75 m, compared in the DSM frame: config v3 fix)
2. height alignment to the current frame (config v3 = gt_clean method): per-pixel MVS depth minus GT depth on bare-ground
   pixels of up to 40 training views, median, two passes
3. evaluation exclusion cells frozen here, before any case table: trees, transient, prior-side trees (ALS)
4. per judgment unit and prior: GT value (roof-like: vertical lines to the registered prior, top layer within 1.0 m;
   wall-like: projection along the wall normal inside the face, +-2 m), >= 5 points, true label against the range tau
5. per-view GT camera-Z depth for the case-3 views (z-buffer, 9 x 9 leak filter 0.3 m), wall coverage
scientific_verdict: null."""
import argparse
import json
import time
from pathlib import Path

import numpy as np
import scipy.ndimage as ndi

from common import CFG, DENSE, OUT, PREP, SURVEY, GRID_H, GRID_W, Scene, Views, global_to_local, inside_range, jdump, log, range_polygon, read_depth_bin, read_uls, widen
from src.phd.prior_propagation_v6 import locations as locs
from src.phd.prior_propagation_v6 import rule

SV = None
CHUNK = 4_000_000   # points per chunk (memory on the shared host)


def survey_grids():
    D = dict(np.load(SURVEY / "derived.npz"))
    A = dict(np.load(SURVEY / "s1/rasters_als_mvs_uls.npz"))
    g = json.loads((SURVEY / "receipt_s2.json").read_text())
    return D, A


def zbuf(Vw, nme, Xd, dz=0.0, dev="cpu"):
    """GT camera-Z depth of one view: chunked z-buffer of the points (z moved by dz), 9 x 9 leak filter 0.3 m (gt_clean rule)."""
    import torch
    fx, fy, cx, cy = Vw.K
    R = torch.as_tensor(Vw.R(nme), device=dev); tt = torch.as_tensor(Vw.t(nme), device=dev)
    off = torch.as_tensor([0.0, 0.0, dz], dtype=torch.float64, device=dev)
    zb = torch.full((GRID_H * GRID_W,), float("inf"), dtype=torch.float64, device=dev)
    for b0 in range(0, len(Xd), CHUNK):
        Xc = (torch.as_tensor(Xd[b0:b0 + CHUNK], dtype=torch.float64, device=dev) + off) @ R.T + tt
        z = Xc[:, 2]
        u = torch.floor(fx * Xc[:, 0] / z + cx); v = torch.floor(fy * Xc[:, 1] / z + cy)
        ok = (z > 1) & (u >= 0) & (u < GRID_W) & (v >= 0) & (v < GRID_H)
        zb.scatter_reduce_(0, (v[ok] * GRID_W + u[ok]).long(), z[ok], reduce="amin")
        del Xc, z, u, v, ok
    zz = zb.view(GRID_H, GRID_W).cpu().numpy()
    fin = np.isfinite(zz)
    mn = ndi.minimum_filter(np.where(fin, zz, np.inf), size=9)
    leak = fin & (zz > mn + 0.3)
    zz[leak] = np.nan; zz[~fin] = np.nan
    return zz, int(leak.sum())


def ground_diffs(Vw, nme, gt, mvs_dir, grid, gmask):
    """vertical MVS - GT differences of one view on bare-ground pixels (MVS point inside a ground cell)."""
    dm = read_depth_bin(Path(mvs_dir) / "stereo/depth_maps" / f"{nme}.geometric.bin")
    ok = np.isfinite(gt) & np.isfinite(dm) & (dm > 0)
    Dr = Vw.rays(nme).astype(np.float64); C = Vw.C(nme)
    Xm = C[None, None, :] + np.where(ok, dm, 0)[..., None] * Dr
    iy, ix, ing = grid.idx(Xm[..., 0], Xm[..., 1])
    g = ok & ing & gmask[iy, ix]
    return ((dm - gt) * Dr[..., 2])[g]


def align_px(X, sel, Vw, mvs_dir, grid, g_range, g_wide, passes=2, min_px=5000):
    """gt_clean method: move the GT by the median vertical MVS - GT difference on bare-ground pixels, twice."""
    total = 0.0; out = []
    for it in range(passes):
        dr, dw = [], []
        for nme in sel:
            gt, _ = zbuf(Vw, nme, X, total)
            dr.append(ground_diffs(Vw, nme, gt, mvs_dir, grid, g_range)); dw.append(ground_diffs(Vw, nme, gt, mvs_dir, grid, g_wide))
        d = np.concatenate(dr) if dr else np.zeros(0); src = "range"
        if d.size < min_px:
            d = np.concatenate(dw) if dw else np.zeros(0); src = "range + 20 m"
        med = float(np.median(d)) if d.size else 0.0
        out.append(dict(pass_=it + 1, pixels=int(d.size), source=src, median_mvs_minus_gt_m=med,
                        nmad_m=float(1.4826 * np.median(np.abs(d - med))) if d.size else None))
        total += med
        log("align pass", it + 1, d.size, src, round(med, 4))
    return total, out


def vertical_points(X, vs=0.5, min_n=5, nz_max=0.5):
    """config v4: GT points on vertical surfaces = points of 0.5 m voxels with >= 5 points whose smallest-variance
    direction (PCA) has |n_z| < 0.5 (used for the wall patches only)."""
    key = np.floor(X / vs).astype(np.int64); key -= key.min(0)
    d1 = int(key[:, 1].max()) + 1; d2 = int(key[:, 2].max()) + 1
    kk = (key[:, 0] * d1 + key[:, 1]) * d2 + key[:, 2]; del key
    uk, inv, cnt = np.unique(kk, return_inverse=True, return_counts=True); del kk
    m0 = X.mean(0); nv = len(uk)
    S1 = np.zeros((nv, 3)); C = np.zeros((nv, 3, 3))
    for b0 in range(0, len(X), CHUNK):
        Xc = X[b0:b0 + CHUNK] - m0; ic = inv[b0:b0 + CHUNK]
        for a in range(3):
            S1[:, a] += np.bincount(ic, Xc[:, a], nv)
            for b in range(a, 3):
                C[:, a, b] += np.bincount(ic, Xc[:, a] * Xc[:, b], nv)
    mu = S1 / cnt[:, None]
    for a in range(3):
        for b in range(a, 3):
            C[:, a, b] = C[:, a, b] / cnt - mu[:, a] * mu[:, b]; C[:, b, a] = C[:, a, b]
    w, v = np.linalg.eigh(C)
    vert_vox = (cnt >= min_n) & (np.abs(v[:, 2, 0]) < nz_max)
    return vert_vox[inv]


class Grid:
    e0, n0, res = 690700.0, 5335820.0, 0.5

    def __init__(self, shape):
        self.ny, self.nx = shape

    def idx(self, x, y):
        E = x + 690953.0; N = y + 5336071.0
        ix = np.floor((E - self.e0) / self.res).astype(np.int64); iy = np.floor((N - self.n0) / self.res).astype(np.int64)
        ok = (ix >= 0) & (ix < self.nx) & (iy >= 0) & (iy < self.ny)
        return np.clip(iy, 0, self.ny - 1), np.clip(ix, 0, self.nx - 1), ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("range_id"); ap.add_argument("--mesh-sub", default="s02"); ap.add_argument("--stage1-sub", default="s52/s03")
    ap.add_argument("--out-sub", default="s52/gt"); ap.add_argument("--views-file", default="/prep/step01/views.json")
    ap.add_argument("--prep-gt-dir", default=None); ap.add_argument("--gt-from", default=None); ap.add_argument("--no-depth", action="store_true")
    ap.add_argument("--views-key", default="train"); ap.add_argument("--views-list", default=None); ap.add_argument("--depth-views", type=int, default=40)
    ap.add_argument("--mvs", default="current", help="MVS workspace for the height alignment (current or a workspace under /out)")
    a = ap.parse_args()
    P_ = lambda p: Path(p) if str(p).startswith("/") else OUT / p
    t0 = time.time()
    rid = a.range_id
    mesh_dir = P_(a.mesh_sub) / rid
    rng = json.loads((mesh_dir / "range.json").read_text())
    D = OUT / a.out_sub / rid; D.mkdir(parents=True, exist_ok=True)
    G, A = survey_grids(); grid = Grid(G["dtm"].shape)
    wide = widen(rng, CFG["ranges"]["prior_margin_m"]) if rng["kind"] != "polygon" else rng
    Pw = range_polygon(wide) if rng["kind"] != "polygon" else np.asarray(rng["polygon_local"])
    lo, hi = Pw.min(0), Pw.max(0)
    if a.gt_from:   # labels only (this task: B0 conditions read the 5.2 B0 GT)
        z_ = np.load(P_(a.gt_from) / "gt_points.npz"); X, multi = z_["xyz"].astype(np.float64), z_["multi"]
        log(rid, "GT points from", a.gt_from, len(X))
    else:
        X, multi = read_uls(lo, hi)
        log(rid, "ULS points", len(X))
    iy, ix, ing = grid.idx(X[:, 0], X[:, 1])
    rec = dict(range=rid, uls_points=int(len(X)), uls_points_outside_survey_grid=int((~ing).sum()), config=CFG["version"][:3])
    dtm = G["dtm"].astype(float); uls = G["uls"].astype(float); mvs = G["mvs"].astype(float); als = G["als"].astype(float)   # absolute heights
    rough = A["uls_zmax"] - A["uls_zmin"]
    umulti = np.where(A["uls_n"] > 0, A["uls_n_multi"] / np.maximum(A["uls_n"], 1), 1.0)
    ground = (A["als_n_c2"] >= 2) & (rough < 0.25) & (G["fid"] < 0) & (G["veg"] < 0.05) & np.isfinite(uls) & np.isfinite(mvs) & (np.abs(uls - dtm) < 1.0) & (umulti < 0.05)
    EE, NN = np.meshgrid(grid.e0 + (np.arange(grid.nx) + 0.5) * grid.res, grid.n0 + (np.arange(grid.ny) + 0.5) * grid.res)
    cxy = np.stack([EE.ravel() - 690953.0, NN.ravel() - 5336071.0], 1)
    inr_cells = inside_range(cxy, rng).reshape(EE.shape) if rng["kind"] != "polygon" else np.zeros(EE.shape, bool)
    wide_cells = inside_range(cxy, wide).reshape(EE.shape) if rng["kind"] != "polygon" else np.ones(EE.shape, bool)
    # 1. transient returns (v3: the point test in the frame of the survey DSM = local z + 604 m)
    trans_cell = (uls > np.fmax(mvs, als) + 1.5) & np.isfinite(mvs) & np.isfinite(uls)
    zmax_ok = np.fmax(mvs, als)[iy, ix] - 604.0 + 0.75
    transient = ing & trans_cell[iy, ix] & (X[:, 2] > zmax_ok)
    if a.gt_from:
        transient[:] = False          # the points of the other run are already cleaned
    rec["transient"] = dict(points_removed=int(transient.sum()), cells=int((trans_cell & inr_cells).sum()) if inr_cells.any() else int(trans_cell.sum()),
                            rule=CFG["ground_truth"]["transient_rule"], fix_v3=CFG["ground_truth"]["revision_v3"]["transient_rule"])
    X = X[~transient]; multi = multi[~transient]
    del iy, ix, ing, zmax_ok, transient
    # 2. height alignment to the current frame (v3: gt_clean method, per-pixel MVS depth on bare ground, two passes)
    gsel = ground & (inr_cells if inr_cells.any() else np.ones_like(ground))
    shift_v2 = float(np.median((mvs - uls)[gsel])) if gsel.sum() >= 50 else None
    views = json.loads(P_(a.views_list).read_text()) if a.views_list else json.loads(P_(a.views_file).read_text())["views"][rid][a.views_key]
    views = views if isinstance(views, list) else views["train"]
    mvs_dir = DENSE if a.mvs == "current" else P_(a.mvs)
    views = [n for n in views if (Path(mvs_dir) / "stereo/depth_maps" / f"{n}.geometric.bin").exists()]   # views COLMAP skipped are left out
    sel = [views[int(i)] for i in np.unique(np.linspace(0, len(views) - 1, min(a.depth_views, len(views))).round().astype(int))]
    Vw = Views()
    if a.gt_from:
        gs_ = json.loads((P_(a.gt_from) / "gt_summary.json").read_text())
        shift, arec = 0.0, dict(from_run=str(a.gt_from), shift_applied_there=gs_["height_alignment"]["shift_m"])
    else:
        shift, arec = align_px(X, sel, Vw, mvs_dir, grid, ground & inr_cells, ground & wide_cells)
    rec["height_alignment"] = dict(shift_m=shift, passes=arec, views=len(sel), mvs=str(mvs_dir), rule=CFG["ground_truth"]["height_alignment"],
                                   v2_survey_cell_shift_m=shift_v2, note="v2 survey-cell value recorded for comparison only")
    X[:, 2] += shift
    iy, ix, ing = grid.idx(X[:, 0], X[:, 1])
    # 3. exclusion cells (frozen here)
    als_multi = np.where(A["als_n"] > 0, A["als_n_multi"] / np.maximum(A["als_n"], 1), np.nan)
    als_c20 = np.where(A["als_n"] > 0, A["als_n_c20"] / np.maximum(A["als_n"], 1), np.nan)
    trees = (G["veg"] > 0.3) | ((als_c20 > 0.5) & (als_multi > 0.5))
    prior_trees = (A["als_n_c6"] > 0) & (als_multi > 0.5)
    excl = trees | trans_cell
    src_ex = P_(a.gt_from) if a.gt_from else (P_(a.prep_gt_dir) if a.prep_gt_dir else None)
    if src_ex is not None:   # this task: the frozen exclusion cells are reused unchanged; the recomputed ones only compared
        ez = np.load(src_ex / "exclusion_cells.npz")
        rec["exclusion_cells_reused"] = dict(source=str(src_ex), equal_to_recomputed={k: bool(np.array_equal(ez[k], v)) for k, v in
                                                                                        (("trees", trees), ("transient", trans_cell), ("prior_side_trees", prior_trees), ("any", excl))})
        trees, trans_cell, prior_trees, excl = ez["trees"], ez["transient"], ez["prior_side_trees"], ez["any"]
    np.savez_compressed(D / "exclusion_cells.npz", trees=trees, transient=trans_cell, prior_side_trees=prior_trees, any=excl)
    rec["exclusion_cells_in_range"] = dict(trees=int((trees & inr_cells).sum()), transient=int((trans_cell & inr_cells).sum()),
                                           prior_side_trees=int((prior_trees & inr_cells).sum()), cell_m=0.5) if inr_cells.any() else None
    np.savez_compressed(D / "gt_points.npz", xyz=X.astype(np.float32), multi=multi)
    def unit_labels(X, prefix, vert=None):
        labels = {}
        for prior in ("LoD2", "ALS"):
            S1 = P_(a.stage1_sub) / rid / prior
            if not (S1 / "units.npz").exists():
                continue
            U = locs.load_store(S1 / "units.npz")
            summ = json.loads((S1 / "summary.json").read_text())
            sh = np.asarray(summ["registration"]["shift_applied"], np.float64)
            if not np.allclose(locs.frame_shift(U), sh, atol=0, rtol=0):      # v6: the store moved with the registered prior
                raise RuntimeError(f"{S1}: store frame_shift {locs.frame_shift(U).tolist()} != registration shift {sh.tolist()}")
            tau = {1: summ["tolerance"]["roof"]["tau"], 2: summ["tolerance"]["wall"]["tau"]}
            if prior == "LoD2":
                m = dict(np.load(mesh_dir / "lod2_mesh.npz", allow_pickle=False))
                V = m["V"] + sh; F = m["F"]; ts = m["tri_surface"]; ttype = m["tri_type"]
                tab = {r["ext"]: r for r in json.loads((mesh_dir / "lod2_surfaces.json").read_text())["surfaces"]}
                n_tri = np.zeros((len(F), 3))
                for e, r in tab.items():
                    n_tri[ts == e] = r["normal"]
                unit_ok = ttype != 2
            else:
                m = dict(np.load(mesh_dir / "als_mesh.npz", allow_pickle=False))
                V = m["V"] + sh; F = m["F"]; ts = m["tri_surface"]; n_tri = m["tri_normal"]; unit_ok = ts >= 0
            ci_of_tri = np.full(len(F), -1, np.int64)
            okt = unit_ok & (ts >= 0)
            ci_of_tri[okt] = locs.compact_index(U, ts[okt])
            Lc = len(U["loc_area"])
            vals, owners, pidx = [], [], []
            # roof-like: vertical lines; chunked (memory: 84 M points in R1, a global OOM on the shared host at 22:03 with
            # whole-array temporaries); same definitions: top layer = points within 1.0 m below the highest point of the unit
            sc = Scene(V, F)
            rl, rz, rd, ri = [], [], [], []
            for b0 in range(0, len(X), CHUNK):
                Xc = X[b0:b0 + CHUNK]
                t, tri = sc.cast_points(np.column_stack([Xc[:, 0], Xc[:, 1], np.full(len(Xc), 250.0)]), np.tile([0, 0, -1.0], (len(Xc), 1)))
                hit = (tri >= 0)
                hit[hit] &= (np.abs(n_tri[tri[hit], 2]) >= 0.5) & (ci_of_tri[tri[hit]] >= 0)
                zh = 250.0 - t[hit]
                loc = locs.locate(U, ci_of_tri[tri[hit]], np.column_stack([Xc[hit, 0], Xc[hit, 1], zh]))
                rm = (loc >= 0) & (U["loc_kind"][np.maximum(loc, 0)] == 1)
                rl.append(loc[rm].astype(np.int32)); rz.append(Xc[hit, 2][rm].astype(np.float32)); rd.append((Xc[hit, 2] - zh)[rm].astype(np.float32))
                ri.append((b0 + np.nonzero(hit)[0][rm]).astype(np.int64))
                del Xc, t, tri, hit, zh, loc, rm
            lr = np.concatenate(rl); zr = np.concatenate(rz); dr = np.concatenate(rd); ir = np.concatenate(ri); del rl, rz, rd, ri
            topz = np.full(Lc, -np.inf, np.float32)
            np.maximum.at(topz, lr, zr)
            keep = zr >= topz[lr] - 1.0
            vals.append(dr[keep]); owners.append(lr[keep]); pidx.append(ir[keep]); del lr, zr, dr, keep, ir
            # wall-like (LoD2): projection along the normal inside the face, within 2 m
            if prior == "LoD2":
                wall_tri = np.nonzero(okt & (np.abs(n_tri[:, 2]) < 0.5))[0]
                if len(wall_tri):
                    scw = Scene(V, F[wall_tri])
                    Xw_all = X if vert is None else X[vert]          # config v4: wall patches use points on vertical surfaces only
                    iw_all = np.arange(len(X)) if vert is None else np.nonzero(vert)[0]
                    for b0 in range(0, len(Xw_all), CHUNK):
                        Xc = Xw_all[b0:b0 + CHUNK]
                        cp, prim = scw.closest(Xc)
                        tri_w = wall_tri[prim]
                        v = Xc - cp.astype(np.float64)
                        dist = np.linalg.norm(v, axis=1)
                        nn = n_tri[tri_w]
                        along = np.abs((v * nn).sum(1))
                        inside_face = (dist <= 2.0) & (along >= 0.999 * dist - 1e-4)
                        lw = np.full(len(Xc), -1, np.int64)
                        lw[inside_face] = locs.locate(U, ci_of_tri[tri_w[inside_face]], cp[inside_face].astype(np.float64))
                        okw = inside_face & (lw >= 0)
                        okw &= U["loc_kind"][np.maximum(lw, 0)] == 2
                        vals.append((v[okw] * nn[okw]).sum(1).astype(np.float32)); owners.append(lw[okw].astype(np.int32))
                        pidx.append(iw_all[b0:b0 + CHUNK][okw].astype(np.int64))
                        del Xc, cp, prim, tri_w, v, dist, nn, along, inside_face, lw, okw
            vv = np.concatenate(vals); oo = np.concatenate(owners); pp_ = np.concatenate(pidx); del vals, owners, pidx
            np.savez_compressed(D / f"gt_owner_{prefix}{prior}.npz", point=pp_, patch=oo.astype(np.int32), value=vv.astype(np.float32),
                                kind=U["loc_kind"][oo].astype(np.int8))
            order = np.argsort(oo, kind="stable"); vv, oo = vv[order], oo[order]
            cnt = np.bincount(oo, minlength=Lc)
            med = np.full(Lc, np.nan)
            if len(oo):
                starts = np.r_[0, np.cumsum(cnt)[:-1]]
                has = cnt > 0
                # median per unit via sorting values within groups
                o2 = np.lexsort((vv, oo)); vs = vv[o2]
                mid_lo = starts[has] + (cnt[has] - 1) // 2; mid_hi = starts[has] + cnt[has] // 2
                med[has] = 0.5 * (vs[mid_lo] + vs[mid_hi])
            kind = U["loc_kind"]
            tau_u = np.where(kind == 2, tau[2], tau[1])
            lab = np.full(Lc, -1, np.int8)
            enough = cnt >= 5
            lab[enough & (np.abs(med) <= tau_u)] = 0
            lab[enough & (np.abs(med) > tau_u)] = 1
            # exclusion of units by cell (centre XY of the registered unit = the moved store's centre)
            cxy = U["loc_center"][:, :2]
            cy_, cx_, cok = grid.idx(cxy[:, 0], cxy[:, 1])
            ex_any = np.where(cok, excl[cy_, cx_], False)
            ex_prior_tree = np.where(cok, prior_trees[cy_, cx_], False) if prior == "ALS" else np.zeros(Lc, bool)
            excluded = ex_any | ex_prior_tree
            np.savez_compressed(D / f"labels_{prefix}{prior}.npz", gt_n=cnt.astype(np.int32), gt_med=med.astype(np.float32), label=lab, tau=tau_u.astype(np.float32),
                                excluded=excluded, excluded_trees_transient=ex_any, excluded_prior_trees=ex_prior_tree)
            inr = U["loc_in_range"]
            def share(msk):
                return dict(units=int(msk.sum()), with_gt=int((msk & enough).sum()), true_agree=int((msk & (lab == 0)).sum()),
                            true_conflict=int((msk & (lab == 1)).sum()), excluded=int((msk & excluded).sum()))
            labels[prior] = dict(roof=share(inr & (kind == 1)), wall=share(inr & (kind == 2)) if prior == "LoD2" else None, tau=tau, shift=sh.tolist(),
                                 wall_coverage=float(((inr & (kind == 2) & enough).sum()) / max((inr & (kind == 2)).sum(), 1)) if prior == "LoD2" else None)
            log(rid, prefix or "GT", prior, "labels", json.dumps(labels[prior])[:300])
        return labels

    if rid.startswith("B0"):
        # order: B0 uses gt_clean = the GeoGS evaluation cloud (r1_b1_sub002) in the common frame: author frame + [2, -29, 0]
        # (step01 pose check), z - 0.0746 m (the stage-2 gt_clean ground alignment; author z = H - 604)
        from plyfile import PlyData  # noqa: F401
        pth = Path("/art/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/native_example/evaluation_reference/r1_b1_sub002_transformed.ply")
        with open(pth, "rb") as f:
            hdr = b""
            while b"end_header" not in hdr:
                hdr += f.readline()
            off = len(hdr)
        nn_ = int([l for l in hdr.decode().splitlines() if l.startswith("element vertex")][0].split()[-1])
        mm = np.memmap(pth, dtype=np.dtype([("x", "<f8"), ("y", "<f8"), ("z", "<f8"), ("r", "u1"), ("g", "u1"), ("b", "u1")]), mode="r", offset=off, shape=(nn_,))
        Xg = np.stack([np.asarray(mm["x"]) + 2.0, np.asarray(mm["y"]) - 29.0, np.asarray(mm["z"]) - 0.0746], 1)
        rec["gt_primary"] = dict(source=str(pth), points=int(len(Xg)), transform="author + [2, -29, 0]; z - 0.0746 (gt_clean)", note="covers the target building only")
        vg = vertical_points(Xg); vu = vertical_points(X) & ~multi          # v5: single-return points for the ULS wall labels
        rec["vertical_surface_points"] = dict(gt_primary_share=float(vg.mean()), uls_share=float(vu.mean()), rule=CFG["ground_truth"]["patch_value"])
        labels = unit_labels(Xg, "", vg)
        rec["labels_uls_supplement"] = unit_labels(X, "uls_", vu)
        X_depth = Xg
        np.savez_compressed(D / "gt_primary.npz", xyz=Xg.astype(np.float32))
    else:
        rec["gt_primary"] = dict(source="TUM2TWIN ULS nadir 2024-12-17 (cleaned here)")
        vu = vertical_points(X) & ~multi                                    # v5: single-return points on vertical surfaces
        rec["vertical_surface_points"] = dict(share=float(vu.mean()), rule=CFG["ground_truth"]["patch_value"])
        labels = unit_labels(X, "", vu)
        X_depth = X
        np.savez_compressed(D / "gt_primary.npz", xyz=X.astype(np.float32))
    rec["labels"] = labels
    if a.no_depth:
        rec["seconds"] = round(time.time() - t0, 1)
        jdump(D / "gt_summary.json", rec)
        log(rid, "GT done (no depth)", rec["seconds"], "s shift", round(shift, 4))
        return
    # 5. per-view GT depth for case 3 (the alignment views) and the alignment check on the same maps
    (D / "gt_depth").mkdir(exist_ok=True)
    chk_g, chk_b = [], []
    for nme in sel:
        zz, nleak = zbuf(Vw, nme, X_depth)
        np.savez_compressed(D / "gt_depth" / f"{nme}.npz", depth=zz.astype(np.float32), leak_dropped=nleak)
        chk_g.append(ground_diffs(Vw, nme, zz, mvs_dir, grid, ground & (inr_cells if inr_cells.any() else wide_cells)))
        bmask = (G["fid"] >= 0) & ((G["mvs"] - G["dtm"]) > 3.0)
        chk_b.append(ground_diffs(Vw, nme, zz, mvs_dir, grid, bmask))
    cg = np.concatenate(chk_g) if chk_g else np.zeros(0); cb = np.concatenate(chk_b) if chk_b else np.zeros(0)
    rec["alignment_check_on_depth_maps"] = dict(gt=("gt_clean (B0 primary)" if rid.startswith("B0") else "aligned ULS"),
                                                ground_pixels=int(cg.size), ground_median_mvs_minus_gt_m=float(np.median(cg)) if cg.size else None,
                                                building_pixels=int(cb.size), building_median_mvs_minus_gt_m=float(np.median(cb)) if cb.size else None,
                                                note="building pixels: MVS point in a LoD2 footprint cell more than 3 m above the DTM (check only)")
    rec["gt_depth_views"] = sel
    rec["seconds"] = round(time.time() - t0, 1)
    jdump(D / "gt_summary.json", rec)
    log(rid, "GT done", rec["seconds"], "s shift", round(shift, 4), "transient", rec["transient"]["points_removed"])


if __name__ == "__main__":
    main()
