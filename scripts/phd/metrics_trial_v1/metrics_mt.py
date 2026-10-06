"""PHD-MAIN-METRICS-TRIAL-v1 4.3 metrics of one result (+ 4.4 paths 1-4, 4.5 measures) (jointbuildgs:dev, CPU; definitions =
configs metrics_trial_v1.json, pre-training inputs = defs/ of prep_mt.py).

  python metrics_mt.py <result> [<result> ...]
    b1_LoD2 | b1_ALS | b2_LoD2 | b2_ALS      a stage-0 training: its TSDF mesh (stage0/<run>/post/mesh_tsdf.ply) and Gaussians
    surface_LoD2 | surface_ALS               the registered prior surface itself (defs/prior_<prior>.npz)
    samepath_LoD2 | samepath_ALS             the prior through the same TSDF path (gpu/samepath_<prior>/mesh.ply)
A result is read with the regions of its own prior. Bundles (seconds each):
  spread        four classes along the line per GT row of the prior-wrong (11), image-wrong (3) and unmeasured wrong-prior
                (13) regions, ambiguous share, per size bin of 11 (|s_W| / tau); record only (purpose: the per-patch MVS proxy
                that separates 11 from 12 is doubtful for large offsets): both wrong (12) and the B173 wing points of 11 + 12;
                mechanism layer (trainings): prior-origin Gaussians (opacity >= 0.5) within 0.25 m of each patch's W centre
                (3, 11, 12, 13, 14), image wrong also with any origin
  accuracy      measured agreement (2): roof rows outside the edge band = highest crossing of the vertical line - z_GT; edge
                band and wall rows = signed nearest crossing along the prior-face normal within 2 m; the band share by slope
  completeness  unmeasured agreement (4 missing, 5 invisible): 3-D distance shares <= 0.2 / 0.5 m
  unseen        B173 unseen wall patches: centres and owned GT points within 0.2 / 0.5 m of the mesh; prior-origin (and
                image-origin) Gaussians within 0.25 m of the centres by inferred label (and the 27 true labels)
  floaters      (trainings) the GPU step's floaters (count, pixel share) and their heights over the highest GT surface
  summary       building surface: Chamfer, precision / completeness / F1 at 0.2 / 0.5 m, M3C2 (core points of defs/bsurf)
  paths         (trainings) path 2 at the accuracy roof points: median z of the evaluation-view points in the 0.1 m cell
  virtual       (trainings) the 4.5 measures on gpu/<run>/mesh_virtual.ply, and the same on the training-view mesh
Writes /out/metrics/<result>.json and /out/metrics/<result>_rows.npz. scientific_verdict: null."""
import json
import sys

import numpy as np
from scipy.spatial import cKDTree

from mt_common import MCFG, OUT, S0, SITE, Timer, jdump, log
from src.phd.metrics_v1 import cloud, lines, stats
from src.phd.metrics_v1.cells import CellMedian
from src.phd.metrics_v1.gauss import count_near
from src.phd.metrics_v1.surface import MeshScene

SPREAD = {"prior_wrong": 11, "image_wrong": 3, "unmeasured_wrong_prior_missing": 13, "both_wrong_record": 12}
SLOPES = [0, 5, 17, 30, 45, 91]


def load_result(name):
    kind, prior = name.split("_")
    if kind in ("b1", "b2"):
        sc = MeshScene.from_ply(S0 / "stage0" / name / "post/mesh_tsdf.ply")
        d = np.load(S0 / "stage0" / name / "model/dump" / f"iteration_{30000}" / "gaussians.npz")
        gs = dict(xyz=d["xyz"].astype(np.float64), origin=d["origin"], opacity=d["opacity"])
        return prior, sc, gs, "training"
    if kind == "surface":
        P = np.load(OUT / "defs" / f"prior_{prior}.npz")
        return prior, MeshScene(P["V"], P["F"]), None, "prior surface as-is"
    return prior, MeshScene.from_ply(OUT / "gpu" / f"samepath_{prior}" / "mesh.ply"), None, "prior same-path mesh"


def mesh_arrays(name):
    import open3d as o3d
    kind, prior = name.split("_")
    if kind == "surface":
        P = np.load(OUT / "defs" / f"prior_{prior}.npz")
        return P["V"].astype(np.float64), P["F"].astype(np.int64)
    p = S0 / "stage0" / name / "post/mesh_tsdf.ply" if kind in ("b1", "b2") else OUT / "gpu" / f"samepath_{prior}" / "mesh.ply"
    m = o3d.io.read_triangle_mesh(str(p))
    return np.asarray(m.vertices), np.asarray(m.triangles)


def share_by(cnt, groups):
    return {k: (dict(patches=int(m.sum()), share_with_one=round(float((cnt[m] > 0).mean()), 4)) if m.any() else dict(patches=0, share_with_one=None))
            for k, m in groups.items()}


def main(name):
    T = Timer()
    prior, sc, gs, what = load_result(name)
    T.mark("load")
    G = np.load(OUT / "defs/gt_classes.npz")
    X = G["xyz"].astype(np.float64)
    r = np.load(OUT / "defs" / f"rows_{prior}.npz")
    pt, code, kind, D, sW, tau, nrm, slope = r["point"], r["code"], r["kind"], r["D"].astype(np.float64), r["sW"].astype(np.float64), \
        r["tau"].astype(np.float64), r["n"].astype(np.float64), r["slope"]
    n_rows = len(pt)
    res = dict(result=name, prior=prior, what=what, mesh_triangles=sc.n_tri, site=SITE)
    rows = dict()
    T.mark("inputs")
    # ------------------------------------------------------------------------------------------------ spread
    SP = MCFG["spread"]
    sel = np.isin(code, list(SPREAD.values()))
    cls = np.full(n_rows, -1, np.int8)
    tt = np.full(n_rows, np.nan, np.float32)
    c, t = lines.four_way(sc, X[pt[sel]], D[sel], sW[sel], SP["t_max_m"], SP["t_fraction"])
    cls[sel] = c
    tt[sel] = t
    amb = np.abs(sW) < SP["ambiguous_m"]
    out = {}
    changed = G["changed"][pt]
    for nm, cc in list(SPREAD.items()) + [("wings_11_12_record", None)]:
        m = (code == cc) if cc is not None else (np.isin(code, (11, 12)) & changed)
        e = dict(points=int(m.sum()), patches=int(len(np.unique(r["patch"][m]))), all=lines.shares(cls[m]),
                 ambiguous_share=round(float(amb[m].mean()), 4) if m.any() else None, non_ambiguous=lines.shares(cls[m & ~amb]),
                 roof=lines.shares(cls[m & (kind == 1)]), wall=lines.shares(cls[m & (kind == 2)]))
        out[nm] = e
    # size bins of the prior-wrong rows (per point |s_W| / tau)
    ratio = np.abs(sW) / tau
    m11 = code == 11
    bins = [[0.0, 1.0]] + MCFG["size_curve"]["bins_tau"]
    curve = []
    for lo_b, hi_b in bins:
        mb = m11 & (ratio >= lo_b) & ((ratio < hi_b) if hi_b is not None else True)
        tr = float(np.median(tau[m11 & (kind == 1)])) if (m11 & (kind == 1)).any() else None
        tw = float(np.median(tau[m11 & (kind == 2)])) if (m11 & (kind == 2)).any() else None
        curve.append(dict(bin=[lo_b, hi_b], roof_m=[None if tr is None else round(lo_b * tr, 3), None if (tr is None or hi_b is None) else round(hi_b * tr, 3)],
                          wall_m=[None if tw is None else round(lo_b * tw, 3), None if (tw is None or hi_b is None) else round(hi_b * tw, 3)],
                          all=lines.shares(cls[mb]), roof=lines.shares(cls[mb & (kind == 1)]), wall=lines.shares(cls[mb & (kind == 2)]),
                          ambiguous_share=round(float(amb[mb].mean()), 4) if mb.any() else None))
    out["size_curve_prior_wrong"] = curve
    # mechanism layer
    if gs is not None:
        op, org, gx = gs["opacity"], gs["origin"], gs["xyz"]
        mo = MCFG["spread"]["mechanism_opacity"]
        rad = MCFG["spread"]["mechanism_radius_m"]
        cp = count_near(r["w_centre"], gx[(org == 1) & (op >= mo)], rad)
        mech = {}
        for nm, cc in [("prior_wrong", 11), ("image_wrong", 3), ("unmeasured_wrong_prior_missing", 13), ("unmeasured_wrong_prior_invisible", 14), ("both_wrong_record", 12)]:
            mm = r["w_code"] == cc
            mech[nm] = dict(patches=int(mm.sum()), prior_origin_share=round(float((cp[mm] > 0).mean()), 4) if mm.any() else None)
        m3 = r["w_code"] == 3
        ca = count_near(r["w_centre"][m3], gx[op >= mo], rad)
        mech["image_wrong"]["any_origin_share_record"] = round(float((ca > 0).mean()), 4) if m3.any() else None
        out["mechanism"] = mech
        rows["w_count_prior"] = cp.astype(np.int32)
    res["spread"] = out
    rows.update(cls=cls, t=tt)
    T.mark("spread")
    # ------------------------------------------------------------------------------------------------ accuracy
    acc = code == 2
    inb = G["in_band"][pt]
    rr = acc & (kind == 1) & ~inb
    br = acc & (kind == 1) & inb
    wr = acc & (kind == 2)
    dz = np.full(n_rows, np.nan, np.float32)
    z = sc.highest_z(X[pt[rr], :2])
    dz[rr] = z - X[pt[rr], 2]
    ua = np.full(n_rows, np.nan, np.float32)
    sm = MCFG["accuracy"]["search_m"]
    for m in (br, wr):
        if m.any():
            ua[m] = sc.along(X[pt[m]], nrm[m], sm)
    roof_all = acc & (kind == 1)
    by_slope = []
    for a, b in zip(SLOPES[:-1], SLOPES[1:]):
        ms = roof_all & (slope >= a) & (slope < b)
        by_slope.append(dict(slope_deg=[a, b], roof_points=int(ms.sum()), band_share=round(float(inb[ms].mean()), 4) if ms.any() else None))
    res["accuracy"] = dict(roof=dict(points_all=int(roof_all.sum()), edge_band_removed=int(br.sum()),
                                     edge_band_share=round(float(br.sum() / max(roof_all.sum(), 1)), 4), **stats.robust(dz[rr]),
                                     no_crossing=int(np.isnan(dz[rr]).sum())),
                           edge_band=dict(**stats.robust(ua[br]), no_crossing_within_2m=int(np.isnan(ua[br]).sum()), points=int(br.sum())),
                           wall=dict(**stats.robust(ua[wr]), no_crossing_within_2m=int(np.isnan(ua[wr]).sum()), points=int(wr.sum())),
                           band_by_slope=by_slope)
    rows.update(dz=dz, u_along=ua)
    T.mark("accuracy")
    # ------------------------------------------------------------------------------------------------ completeness
    dist = np.full(n_rows, np.nan, np.float32)
    comp = {}
    for nm, cc in (("unmeasured_agreement_missing", 4), ("unmeasured_agreement_invisible", 5)):
        m = code == cc
        if m.any():
            dist[m] = sc.distance(X[pt[m]])
        comp[nm] = dict(all=stats.within(dist[m]), roof=stats.within(dist[m & (kind == 1)]), wall=stats.within(dist[m & (kind == 2)]),
                        patches=int(len(np.unique(r["patch"][m]))))
    res["completeness"] = comp
    rows["dist"] = dist
    T.mark("completeness")
    # ------------------------------------------------------------------------------------------------ unseen B173 walls
    un = np.load(OUT / "defs/unseen.npz")
    cu = un["centre"]
    li, lt = un["label_inferred"], un["label_true"]
    groups = {"below_current_roof (inferred agreement)": li == 0, "above_current_roof (inferred conflict)": li == 1, "ambiguous": li == 2,
              "true agreement (label)": lt == 0, "true conflict (label)": lt == 1, "all": np.ones(len(cu), bool)}
    dc = sc.distance(cu)
    gpt = np.unique(un["gt_point"])
    dg = sc.distance(X[gpt])
    ures = dict(patches=int(len(cu)), centres_within={k: stats.within(dc[m]) for k, m in groups.items()}, gt_points=stats.within(dg))
    if gs is not None:
        op, org, gx = gs["opacity"], gs["origin"], gs["xyz"]
        cpu_ = count_near(cu, gx[(org == 1) & (op >= 0.5)], 0.25)
        ciu = count_near(cu, gx[(org == 0) & (op >= 0.5)], 0.25)
        ures["prior_origin_gaussians"] = share_by(cpu_, groups)
        ures["image_origin_gaussians_record"] = share_by(ciu, groups)
        rows["unseen_count_prior"] = cpu_.astype(np.int32)
    res["unseen"] = ures
    rows["unseen_dist_train_mesh"] = dc
    T.mark("unseen")
    # ------------------------------------------------------------------------------------------------ floaters
    if gs is not None:
        fj = OUT / "gpu" / name / "floaters.json"
        f = json.loads(fj.read_text()) if fj.exists() else None
        fm = np.load(OUT / "gpu" / name / "floater_mask.npy") if (OUT / "gpu" / name / "floater_mask.npy").exists() else None
        tr = np.load(OUT / "defs/top_raster.npz")
        hgt = None
        if fm is not None and fm.any():
            q = np.floor((gs["xyz"][fm, :2] - tr["lo"]) / float(tr["cell"])).astype(np.int64)
            hgt = gs["xyz"][fm, 2] - tr["grid"][q[:, 1], q[:, 0]]
        res["floaters"] = dict(count=None if f is None else f["floaters"], prior_origin=None if f is None else f["floaters_prior_origin"],
                               pixel_share=None if f is None else round(f["pixel_share"], 6), floater_pixels=None if f is None else f["floater_pixels"],
                               height_over_top_m=None if hgt is None else dict(p50=round(float(np.median(hgt)), 2), p95=round(float(np.quantile(hgt, 0.95)), 2),
                                                                                max=round(float(hgt.max()), 2)))
    T.mark("floaters")
    # ------------------------------------------------------------------------------------------------ summary numbers
    bsd = np.load(OUT / "defs/bsurf.npz")

    def in_cells(P):
        ix = np.floor((P[:, 0] + 690953.0 - float(bsd["e0"])) / float(bsd["res"])).astype(np.int64)
        iy = np.floor((P[:, 1] + 5336071.0 - float(bsd["n0"])) / float(bsd["res"])).astype(np.int64)
        return np.isin(iy * int(bsd["nx"]) + ix, bsd["keys"])
    V, F = mesh_arrays(name)
    # triangles drawn from: centroid in a building-surface cell, or larger than 0.01 m2 (a prior polygon can reach into a
    # cell with its centroid outside); the samples are then kept by their own cell
    tri_in = np.zeros(len(F), bool)
    for b in range(0, len(F), 4_000_000):
        T3 = V[F[b:b + 4_000_000]]
        tri_in[b:b + 4_000_000] = in_cells(T3.mean(1)) | (0.5 * np.linalg.norm(np.cross(T3[:, 1] - T3[:, 0], T3[:, 2] - T3[:, 0]), axis=1) > 0.01)
        del T3
    smp = cloud.sample_mesh(V, F[tri_in], MCFG["summary_numbers"]["sample_density_per_m2"], seed=0)
    smp = smp[in_cells(smp)]
    del V, F
    T.mark("summary_sample")
    Gb = X[G["bs"]]
    cp_, dRG, dGR = cloud.chamfer_pcf(smp, Gb, ts=(0.2, 0.5))
    T.mark("summary_chamfer")
    M = MCFG["summary_numbers"]["m3c2"]
    cmp_ = smp[cloud.voxel_thin(smp, 0.05)] if len(smp) else smp
    ok = bsd["core_ok"]
    d3, nr_, nc_ = cloud.m3c2(bsd["core"][ok], bsd["core_normal"][ok], bsd["gt_thin"].astype(np.float64), cmp_,
                              radius=M["projection_diameter_m"] / 2.0, half_len=M["max_depth_m"], min_n=5)
    m3 = stats.robust(d3)
    res["summary"] = dict(result_points=int(len(smp)), gt_points=int(len(Gb)), triangles_in_cells=int(tri_in.sum()), **cp_,
                          m3c2=dict(core_points=int(ok.sum()), share_with_distance=round(float(np.isfinite(d3).mean()), 4), median=m3["median"], nmad=m3["nmad"]))
    rows["m3c2"] = d3.astype(np.float32)
    del smp, Gb, dRG, dGR, cmp_
    T.mark("summary")
    # ------------------------------------------------------------------------------------------------ path 2 (trainings)
    if gs is not None and (OUT / "gpu" / name / "eval_points.npz").exists():
        ep = np.load(OUT / "gpu" / name / "eval_points.npz")["xyz"]
        cm = CellMedian(X[pt[rr], :2], MCFG["bias_paths"]["cell_m"])
        cm.add(ep)
        z2, n2 = cm.medians(MCFG["bias_paths"]["min_points"])
        p2 = np.full(n_rows, np.nan, np.float32)
        p2[rr] = z2 - X[pt[rr], 2]
        rows["path2"] = p2
        res["path2"] = dict(**stats.robust(p2[rr]), eval_points=int(len(ep)))
    T.mark("paths")
    # ------------------------------------------------------------------------------------------------ virtual-view mesh (trainings)
    vp = OUT / "gpu" / name / "mesh_virtual.ply"
    if gs is not None and vp.exists():
        vres = {}
        for tag, scn in (("virtual", MeshScene.from_ply(vp)), ("training", sc)):
            dcv = scn.distance(cu)
            dgv = scn.distance(X[gpt])
            vres[tag] = dict(centres_within={k: stats.within(dcv[m]) for k, m in groups.items()}, gt_points=stats.within(dgv))
            if tag == "virtual":
                rows["unseen_dist_virtual_mesh"] = dcv
        # mesh vertices at the unseen walls: signed distance to the LoD2 wall plane
        import open3d as o3d
        mv = o3d.io.read_triangle_mesh(str(vp))
        Vv = np.asarray(mv.vertices)
        for tag, VV in (("virtual", Vv), ("training", None)):
            if VV is None:
                VV = np.asarray(o3d.io.read_triangle_mesh(str(S0 / "stage0" / name / "post/mesh_tsdf.ply")).vertices)
            tree = cKDTree(cu)
            dd, k = tree.query(VV, distance_upper_bound=2.5, workers=-1)
            okk = np.isfinite(dd)
            vv = VV[okk] - cu[k[okk]]
            nn = un["normal"][k[okk]]
            sd = (vv * nn).sum(1)
            inpl = np.linalg.norm(vv - sd[:, None] * nn, axis=1)
            mm = (inpl <= 0.2) & (np.abs(sd) <= 2.0)
            sdm = sd[mm]
            lab = li[k[okk]][mm]
            hist = np.histogram(sdm, bins=np.arange(-2.0, 2.01, 0.1))[0].tolist()
            vres[tag]["vertices_at_unseen_walls"] = dict(n=int(len(sdm)), q=[round(float(x), 3) for x in np.quantile(sdm, [0.05, 0.25, 0.5, 0.75, 0.95])] if len(sdm) else None,
                                                          share_within_0_2=round(float((np.abs(sdm) <= 0.2).mean()), 4) if len(sdm) else None,
                                                          n_below_roof=int((lab == 0).sum()), n_above_roof=int((lab == 1).sum()), hist_m=hist)
            if tag == "virtual":
                np.savez_compressed(OUT / "metrics" / f"{name}_virtual_vertices.npz", sd=sdm.astype(np.float32), lab=lab, xyz=VV[okk][mm].astype(np.float32))
        vj = json.loads((OUT / "gpu" / name / "virtual.json").read_text())
        gpts_lab = np.isin(np.arange(len(cu)), np.searchsorted(un["patch"], np.unique(un["gt_patch"])))
        vres["gt_cover"] = {k: dict(patches=int(m.sum()), with_owned_gt_point=round(float(gpts_lab[m].mean()), 4) if m.any() else None,
                                    with_label=round(float((lt[m] >= 0).mean()), 4) if m.any() else None) for k, m in groups.items()}
        vres["gpu"] = dict(voxel_m=vj["voxel_m"], seconds=vj["seconds"], peak_host_gb=vj["peak_host_gb"], triangles=vj["triangles"],
                           seen_per_view=[(v["view"], v["seen"], v["seen_below_roof"], v["seen_above_roof"]) for v in vj["virtual"]])
        res["virtual"] = vres
    T.mark("virtual")
    res["seconds"] = T.marks
    res["scientific_verdict"] = None
    (OUT / "metrics").mkdir(exist_ok=True)
    jdump(OUT / "metrics" / f"{name}.json", res)
    np.savez_compressed(OUT / "metrics" / f"{name}_rows.npz", **rows)
    log(name, "done", T.marks)


if __name__ == "__main__":
    for nm in sys.argv[1:]:
        main(nm)
