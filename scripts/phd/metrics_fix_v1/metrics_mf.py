"""PHD-MAIN-METRICS-FIX-v1 metrics v2 of one result at B173nb_b10 (jointbuildgs:dev, CPU; module metrics_v2, region files v2;
definitions = configs metrics_fix_v1.json; pre-training inputs = the trial's defs/ (/mt) and this task's regions_v2/).

  python metrics_mf.py --bundles accuracy,spread,... <result> [<result> ...]
    results: b1_LoD2 b1_ALS b2_LoD2 b2_ALS surface_LoD2 surface_ALS samepath_LoD2 samepath_ALS
    bundles: accuracy (4.3-4.4), spread, completeness, unseen, floating, summary, virtual (4.8); default: all

accuracy    support agreement (code 2, v2): band v2; roof outside the band: faces <= 17 degrees vertical height difference,
            steeper faces normal distance; band and walls normal distance; bias and dispersion per class; removed share by
            slope; remaining points per building
spread      error inflow rate over the points with |W - GT| >= 0.2 m and the indeterminable share; regions 11, 3, 13 (+ records
            12 and the B173 wings); W of code 3 (v2) = the MVS height at the GT point; size bins (10,000-point merging), correction
            rates and boundary; past-shape persistence (patches with |W - GT| > 0.5 m; code 3 counts any origin)
completeness / unseen   missing and invisible agreement (record within one site); inheritance rate and past shape of the unseen
            B173 walls by the inferred label ('inferred')
floating    floating Gaussians 3-20 m and above 20 m (trial GPU floater masks)
summary     Chamfer, precision / completeness / F1, M3C2: definitions unchanged -> copied from the trial result json
virtual     the chosen virtual-view option (4.7): mesh-level inheritance, past shape, wall-plane share
Writes /out/metrics/<result>.json and <result>_rows.npz (merged with earlier bundles). scientific_verdict: null."""
import argparse
import json

import numpy as np
from matplotlib.path import Path as MPath

from mf_common import DR, FCFG, MT, OUT, S0, Timer, jdump, log
from src.phd.metrics_v2 import band, bins, lines, stats
from src.phd.metrics_v2.gauss import count_near
from src.phd.metrics_v2.readings import roof_reading
from src.phd.metrics_v2.surface import MeshScene

SITE = "B173nb_b10"
SLOPES = [0, 5, 17, 30, 45, 91]
ALL = ["accuracy", "spread", "completeness", "unseen", "floating", "summary", "virtual"]


def load_result(name):
    kind, prior = name.split("_")
    if kind in ("b1", "b2"):
        d = np.load(S0 / "stage0" / name / "model/dump/iteration_30000/gaussians.npz")
        return prior, (lambda: MeshScene.from_ply(S0 / "stage0" / name / "post/mesh_tsdf.ply")), dict(xyz=d["xyz"].astype(np.float64), origin=d["origin"], opacity=d["opacity"])
    if kind == "surface":
        P = np.load(MT / "defs" / f"prior_{prior}.npz")
        return prior, (lambda: MeshScene(P["V"], P["F"])), None
    return prior, (lambda: MeshScene.from_ply(MT / "gpu" / f"samepath_{prior}" / "mesh.ply")), None


class Inputs:
    """trial rows + region v2 codes + per-row W offsets of v2 + patch geometry."""

    def __init__(self, prior):
        self.prior = prior
        G = np.load(MT / "defs/gt_classes.npz")
        self.G = G
        self.X = G["xyz"].astype(np.float64)
        r = np.load(MT / "defs" / f"rows_{prior}.npz")
        self.r = r
        R2 = np.load(OUT / "regions_v2" / f"regions_ext_v2_{SITE}_{prior}.npz")
        self.R2 = R2
        U = np.load(S0 / "s61/box" / SITE / prior / "units.npz")
        pt, pa = r["point"], r["patch"].astype(np.int64)
        self.pt, self.pa, self.kind = pt, pa, r["kind"]
        self.code = R2["code_ext_v2"][pa]
        self.code_v1 = r["code"]
        self.tau = r["tau"].astype(np.float64)
        self.D = r["D"].astype(np.float64)
        self.n = r["n"].astype(np.float64)
        self.slope = r["slope"].astype(np.float64)
        self.value = r["value"].astype(np.float64)
        mv = np.load(OUT / "regions_v2" / f"mvs_at_gt_{SITE}.npz")
        zm = np.full(len(self.X), np.nan)
        zm[mv["gt_points_index"]] = mv["gt_points_z_mvs"]
        self.z_mvs = zm
        kept = R2["v1_kept"][pa]
        d = R2["mvs_minus_gt_at_gt"].astype(np.float64)[pa]
        mvs_prior = R2["mvs_minus_prior"].astype(np.float64)[pa]
        sW = np.zeros(len(pt))
        pw = np.isin(self.code, (11, 12, 13, 14))
        sW[pw] = -self.value[pw]
        c3 = self.code == 3
        at_gt = zm[pt] - self.X[pt, 2]
        v2_3 = c3 & ~kept & (self.kind == 1)
        sW[v2_3] = np.where(np.isfinite(at_gt[v2_3]), at_gt[v2_3], d[v2_3])
        k3 = c3 & ~v2_3
        sW[k3] = -self.value[k3] + mvs_prior[k3]
        self.sW = sW
        # W centres per patch of the error regions (v2)
        c2p = R2["code_ext_v2"]
        n_p = np.cross(U["loc_t1"], U["loc_t2"])
        n_p /= np.maximum(np.linalg.norm(n_p, axis=1, keepdims=True), 1e-12)
        n_p *= np.where(n_p[:, 2:3] < 0, -1.0, 1.0)
        if prior == "LoD2":
            tab = {t["ext"]: t for t in json.loads((DR / "s02_box" / SITE / "lod2_surfaces.json").read_text())["surfaces"]}
            se = U["surf_ext"][U["loc_surface"]]
            wl = U["loc_kind"] == 2
            n_p[wl] = np.array([tab[int(e)]["normal"] for e in se[wl]], np.float64)
        Dp = np.where((U["loc_kind"] == 2)[:, None], n_p, np.array([0.0, 0.0, 1.0]))
        wpat = np.nonzero(np.isin(c2p, (3, 11, 12, 13, 14)))[0]
        wc = U["loc_center"][wpat].copy()
        k = c2p[wpat] == 3
        kept_p = R2["v1_kept"][wpat]
        shift = np.where(k & ~kept_p & (U["loc_kind"][wpat] == 1), R2["gt_med"][wpat].astype(np.float64) + np.nan_to_num(R2["mvs_minus_gt_at_gt"][wpat].astype(np.float64)), 0.0)
        shift = np.where(k & (kept_p | (U["loc_kind"][wpat] != 1)), R2["mvs_minus_prior"][wpat].astype(np.float64), shift)
        wc = wc + shift[:, None] * Dp[wpat]
        wdist = np.where(np.isin(c2p[wpat], (11, 12, 13, 14)), np.abs(R2["gt_med"][wpat].astype(np.float64)),
                         np.abs(np.where(kept_p, R2["mvs_minus_prior"][wpat] - R2["gt_med"][wpat], R2["mvs_minus_gt_at_gt"][wpat]).astype(np.float64)))
        self.w_patch, self.w_centre, self.w_code, self.w_dist = wpat, wc, c2p[wpat], wdist


def accuracy(I, sc, res, rows):
    A = FCFG["accuracy_v2"]
    acc = I.code == 2
    roof_rows = acc & (I.kind == 1)
    wall_rows = acc & (I.kind == 2)
    ir = np.nonzero(roof_rows)[0]
    inb_v2, _ = band.edge_band_v2(I.X, I.X[I.pt[ir]], I.slope[ir], FCFG["edge_band_v2"]["radius_m"], FCFG["edge_band_v2"]["height_range_m"], 0.1,
                                  FCFG["edge_band_v2"]["slope_cap_deg"])
    inb = np.zeros(len(I.pt), bool)
    inb[ir] = inb_v2
    out_rows = roof_rows & ~inb
    val = np.full(len(I.pt), np.nan)
    steep = np.zeros(len(I.pt), bool)
    v, s = roof_reading(sc, I.X[I.pt[out_rows]], I.n[out_rows], I.slope[out_rows], FCFG["height_range"]["steep_deg"], 2.0)
    val[out_rows] = v
    steep[out_rows] = s
    bandv = np.full(len(I.pt), np.nan)
    for m in (roof_rows & inb, wall_rows):
        if m.any():
            bandv[m] = sc.along(I.X[I.pt[m]], I.n[m], 2.0)
    gentle = out_rows & ~steep
    by_slope = []
    for a, b in zip(SLOPES[:-1], SLOPES[1:]):
        ms = roof_rows & (I.slope >= a) & (I.slope < b)
        by_slope.append(dict(slope_deg=[a, b], roof_points=int(ms.sum()), band_share_v2=round(float(inb[ms].mean()), 4) if ms.any() else None,
                             band_share_v1=round(float(I.G["in_band"][I.pt[ms]].mean()), 4) if ms.any() else None))
    fp = json.loads((DR / "s02_box" / SITE / "footprints.json").read_text())["footprints"]
    by_b = {}
    for f in fp:
        inside = MPath(np.asarray(f["ring_local"])).contains_points(I.X[I.pt, :2])
        by_b[f["building"]] = dict(outside_band_v2=int((inside & out_rows).sum()), outside_band_v1=int((inside & roof_rows & ~I.G["in_band"][I.pt]).sum()),
                                   steep_outside_band_v2=int((inside & out_rows & steep).sum()))
    res["accuracy"] = dict(rule=A["classes"], roof_points=int(roof_rows.sum()), band_share_v2=round(float(inb[roof_rows].mean()), 4) if roof_rows.any() else None,
                           band_share_v1=round(float(I.G["in_band"][I.pt[roof_rows]].mean()), 4) if roof_rows.any() else None,
                           gentle=dict(**stats.bias_dispersion(val[gentle]), no_crossing=int(np.isnan(val[gentle]).sum())),
                           steep=dict(**stats.bias_dispersion(val[out_rows & steep]), no_crossing=int(np.isnan(val[out_rows & steep]).sum())),
                           roof_outside_band=stats.bias_dispersion(val[out_rows]),
                           band=dict(**stats.bias_dispersion(bandv[roof_rows & inb]), no_crossing=int(np.isnan(bandv[roof_rows & inb]).sum())),
                           wall=dict(**stats.bias_dispersion(bandv[wall_rows]), no_crossing=int(np.isnan(bandv[wall_rows]).sum())),
                           by_slope=by_slope, by_building=by_b)
    rows.update(acc_val=val.astype(np.float32), acc_steep=steep, acc_in_band_v2=inb, acc_band_val=bandv.astype(np.float32))


def spread(I, sc, gs, res, rows):
    SP = FCFG["accepted_proposals"]
    sel = np.isin(I.code, (11, 3, 13, 12))
    cls = np.full(len(I.pt), -1, np.int8)
    c, _ = lines.four_way(sc, I.X[I.pt[sel]], I.D[sel], I.sW[sel], 0.5, 0.5)
    cls[sel] = c
    amb = np.abs(I.sW) < 0.2
    main = ~amb
    changed = I.G["changed"][I.pt]
    out = {}
    for nm, m in (("prior_error", I.code == 11), ("observation_error", I.code == 3), ("missing_prior_error", I.code == 13),
                  ("double_error_record", I.code == 12), ("wings_11_12_record", np.isin(I.code, (11, 12)) & changed)):
        out[nm] = dict(points=int(m.sum()), patches=int(len(np.unique(I.pa[m]))), main=lines.shares(cls[m & main]),
                       indeterminable_share=round(float(amb[m].mean()), 4) if m.any() else None, all_points=lines.shares(cls[m]),
                       roof=lines.shares(cls[m & main & (I.kind == 1)]), wall=lines.shares(cls[m & main & (I.kind == 2)]))
    # size bins of the prior-error rows (main points), merged by the 10,000-point rule
    ratio = np.abs(I.sW) / I.tau
    m11 = (I.code == 11) & main
    edges = [1.0, 1.5, 2.0, 3.0, 4.0, 8.0, None]
    counts = [int((m11 & (ratio >= edges[i]) & ((ratio < edges[i + 1]) if edges[i + 1] is not None else True)).sum()) for i in range(6)]
    groups = bins.merge_small(counts, 10_000)
    curve = []
    below = m11 & (ratio < 1.0)
    curve.append(dict(bin=[0.0, 1.0], merged_from=None, points=int(below.sum()), patches=int(len(np.unique(I.pa[below]))), shares=lines.shares(cls[below]),
                      correction_rate=lines.shares(cls[below])["gt_side"], separate=True))
    for g in groups:
        lo, hi = edges[g[0]], edges[g[-1] + 1]
        mb = m11 & (ratio >= lo) & ((ratio < hi) if hi is not None else True)
        sh = lines.shares(cls[mb])
        curve.append(dict(bin=[lo, hi], merged_from=[[edges[i], edges[i + 1]] for i in g], points=int(mb.sum()), patches=int(len(np.unique(I.pa[mb]))),
                          shares=sh, correction_rate=sh["gt_side"], indeterminable_share=round(float(amb[(I.code == 11) & (ratio >= lo) & ((ratio < hi) if hi is not None else True)].mean()), 4)))
    tr = float(np.median(I.tau[(I.code == 11) & (I.kind == 1)])) if ((I.code == 11) & (I.kind == 1)).any() else None
    bnd = bins.boundary([c_["correction_rate"] for c_ in curve[1:]], [c_["bin"][0] for c_ in curve[1:]])
    out["size_curve"] = dict(bins=curve, raw_counts=counts, groups=groups, boundary_tau=bnd, boundary_roof_m=None if (bnd is None or tr is None) else round(bnd * tr, 3), tau_roof=tr)
    # past-shape persistence
    if gs is not None:
        op, org, gx = gs["opacity"], gs["origin"], gs["xyz"]
        far = I.w_dist > 0.5
        cp = count_near(I.w_centre, gx[(org == 1) & (op >= 0.5)], 0.25)
        ca = count_near(I.w_centre, gx[op >= 0.5], 0.25)
        ps = {}
        for nm, cc, cnt in (("prior_error", 11, cp), ("double_error_record", 12, cp), ("missing_prior_error", 13, cp), ("invisible_prior_error", 14, cp),
                            ("observation_error_any_origin", 3, ca)):
            mm = (I.w_code == cc) & far
            ps[nm] = dict(patches=int(mm.sum()), patches_all=int((I.w_code == cc).sum()), rate=round(float((cnt[mm] > 0).mean()), 4) if mm.any() else None)
        out["past_shape"] = ps
        rows["w_count_prior"] = cp.astype(np.int32)
        rows["w_count_any"] = ca.astype(np.int32)
    res["spread"] = out
    rows.update(cls=cls, sW=I.sW.astype(np.float32), code_v2=I.code)


def completeness(I, sc, res, rows):
    dist = np.full(len(I.pt), np.nan, np.float32)
    comp = {}
    for nm, cc in (("missing_agreement", 4), ("invisible_agreement", 5)):
        m = I.code == cc
        if m.any():
            dist[m] = sc.distance(I.X[I.pt[m]])
        comp[nm] = dict(all=stats.within(dist[m]), roof=stats.within(dist[m & (I.kind == 1)]), wall=stats.within(dist[m & (I.kind == 2)]),
                        patches=int(len(np.unique(I.pa[m]))), note="record within one site (stage 1 reads it pooled over the sites)")
    res["completeness"] = comp
    rows["dist"] = dist


def unseen(I, sc, gs, res, rows):
    un = np.load(MT / "defs/unseen.npz")
    cu, li, lt = un["centre"], un["label_inferred"], un["label_true"]
    groups = {"invisible_agreement_inferred": li == 0, "invisible_error_inferred": li == 1, "ambiguous": li == 2, "true_agreement_label": lt == 0,
              "true_conflict_label": lt == 1}
    dc = sc.distance(cu)
    u = dict(patches=int(len(cu)), mesh_within={k: stats.within(dc[m]) for k, m in groups.items()})
    if gs is not None:
        op, org, gx = gs["opacity"], gs["origin"], gs["xyz"]
        cnt = count_near(cu, gx[(org == 1) & (op >= 0.5)], 0.25)
        u["inheritance_rate_inferred"] = round(float((cnt[groups["invisible_agreement_inferred"]] > 0).mean()), 4)
        u["past_shape_invisible_inferred"] = round(float((cnt[groups["invisible_error_inferred"]] > 0).mean()), 4)
        u["by_group"] = {k: dict(patches=int(m.sum()), share=round(float((cnt[m] > 0).mean()), 4) if m.any() else None) for k, m in groups.items()}
        rows["unseen_count_prior"] = cnt.astype(np.int32)
    res["unseen"] = u


def floating(name, gs, res):
    if gs is None:
        return
    fm = np.load(MT / "gpu" / name / "floater_mask.npy")
    fj = json.loads((MT / "gpu" / name / "floaters.json").read_text())
    tr = np.load(MT / "defs/top_raster.npz")
    x = gs["xyz"][fm]
    q = np.floor((x[:, :2] - tr["lo"]) / float(tr["cell"])).astype(np.int64)
    h = x[:, 2] - tr["grid"][q[:, 1], q[:, 0]]
    near = h <= 20
    org = gs["origin"][fm]
    res["floating"] = dict(near_3_20m=int(near.sum()), near_prior=int((near & (org == 1)).sum()), above_20m=int((~near).sum()), above_20m_prior=int((~near & (org == 1)).sum()),
                           pixel_share_all=round(fj["pixel_share"], 6), note="3-20 m read with the past-shape persistence rate; the pixel share is for both bands together")


def summary(name, res):
    t = json.loads((MT / "metrics" / f"{name}.json").read_text())
    res["summary"] = dict(**t["summary"], source="copied from the trial (definitions unchanged)")


def virtual(name, I, gs, res, rows):
    vj = OUT / "virtual" / "chosen.json"
    if gs is None or not vj.exists():
        return
    ch = json.loads(vj.read_text())
    p = OUT / "virtual" / ch["option"] / name / "mesh_virtual.ply"
    if not p.exists():
        return
    un = np.load(MT / "defs/unseen.npz")
    cu, li = un["centre"], un["label_inferred"]
    sc = MeshScene.from_ply(p)
    dc = sc.distance(cu)
    res["virtual"] = dict(option=ch["option"], below_roof_within_0_5=round(float((dc[li == 0] <= 0.5).mean()), 4), above_roof_within_0_2=round(float((dc[li == 1] <= 0.2).mean()), 4),
                          note="mesh level; read with the inheritance rate (Gaussian level)")


def main(names, bundles):
    for name in names:
        T = Timer()
        prior, mk_scene, gs = load_result(name)
        I = Inputs(prior)
        T.mark("inputs")
        need_scene = any(b in bundles for b in ("accuracy", "spread", "completeness", "unseen"))
        sc = mk_scene() if need_scene else None
        T.mark("load")
        f = OUT / "metrics" / f"{name}.json"
        res = json.loads(f.read_text()) if f.exists() else dict(result=name, prior=prior, site=SITE, seconds={})
        rf = OUT / "metrics" / f"{name}_rows.npz"
        rows = dict(np.load(rf)) if rf.exists() else {}
        for b in bundles:
            if b == "accuracy":
                accuracy(I, sc, res, rows)
            elif b == "spread":
                spread(I, sc, gs, res, rows)
            elif b == "completeness":
                completeness(I, sc, res, rows)
            elif b == "unseen":
                unseen(I, sc, gs, res, rows)
            elif b == "floating":
                floating(name, gs, res)
            elif b == "summary":
                summary(name, res)
            elif b == "virtual":
                virtual(name, I, gs, res, rows)
            T.mark(b)
        res["seconds"].update(T.marks)
        res["scientific_verdict"] = None
        (OUT / "metrics").mkdir(exist_ok=True)
        jdump(f, res)
        np.savez_compressed(rf, **rows)
        log(name, bundles, T.marks)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundles", default=",".join(ALL))
    ap.add_argument("names", nargs="+")
    a = ap.parse_args()
    main(a.names, a.bundles.split(","))
