"""PHD-MAIN-STAGE1-v1 metrics of one result on one judgment unit (jointbuildgs:dev, CPU; module v3; regions v3; definitions =
configs main_stage1_v1.json and the fix's 9.1 table with the six decisions of 2026-10-07).

  python metrics_s1.py <site> <unit_prior> <result> [<result> ...] [--bundles accuracy,spread,completeness,unseen,floating,summary,virtual]

<result>: prop_<prior>_s<k> (the method), imgonly_s<k>, trust_<prior> (always-trust), prop_ALS1x_s0, surface_<prior>, samepath_<prior>.
The unit prior picks the region file and the rows (an image-only result is read on both units). Inputs of the stage-0 trainings of
B173nb_b10 (prop_*_s0/s1 = b1/b2) and the trial's / fix's GPU products are read where they are; every other result from this payload.
Area-ratio metrics on the thinned rows (3.4); geometric accuracy on thinned (judged) and unthinned rows. Writes
/out/metrics/<site>/<result>__<unit>.json and _rows.npz. scientific_verdict: null."""
import argparse
import json
from pathlib import Path

import numpy as np
from matplotlib.path import Path as MPath

from s1_common import DR, MF, MT, OUT, S0, SCFG1, Timer, jdump, log
from src.phd.metrics_v3 import bins, cloud, lines, stats
from src.phd.metrics_v3.gauss import count_near
from src.phd.metrics_v3.readings import roof_reading
from src.phd.metrics_v3.surface import MeshScene

ALL = ["accuracy", "spread", "completeness", "unseen", "floating", "summary", "virtual"]
SLOPES = [0, 5, 17, 30, 45, 90]
STEEP = 17.0
B173NB = "B173nb_b10"
STAGE0 = {"prop_LoD2_s0": "b1_LoD2", "prop_LoD2_s1": "b2_LoD2", "prop_ALS_s0": "b1_ALS", "prop_ALS_s1": "b2_ALS"}


# ------------------------------------------------------------------------------------------------ where a result lives
def result_paths(site, res):
    """paths of a result's products (None where not applicable)."""
    if site == B173NB and res in STAGE0:
        run = STAGE0[res]
        return dict(mesh=S0 / "stage0" / run / "post/mesh_tsdf.ply", dump=S0 / "stage0" / run / "model/dump/iteration_30000/gaussians.npz",
                    floater_mask=MT / "gpu" / run / "floater_mask.npy", floaters=MT / "gpu" / run / "floaters.json",
                    virtual=MF / "virtual/option2" / run / "mesh_virtual.ply", virtual_json=MF / "virtual/option2" / run / "virtual.json",
                    receipt=S0 / "stage0" / run / "receipt.json", post=S0 / "stage0" / run / "post/post.json",
                    quality=OUT / "stage1" / site / res / "post/quality.json", eval_points=MT / "gpu" / run / "eval_points.npz")
    if res.startswith("surface_"):
        return dict(prior_npz=OUT / "defs" / site / f"prior_{res.split('_')[1]}.npz")
    if res.startswith("samepath_"):
        p = (MT / "gpu" / f"samepath_{res.split('_')[1]}" / "mesh.ply") if site == B173NB else (OUT / "stage1" / site / res / "mesh.ply")
        return dict(mesh=p)
    R = OUT / "stage1" / site / res
    return dict(mesh=R / "post/mesh_tsdf.ply", dump=R / "model/dump/iteration_30000/gaussians.npz", floater_mask=R / "gpu/floater_mask.npy",
                floaters=R / "gpu/floaters.json", virtual=R / "gpu/virtual/mesh_virtual.ply", virtual_json=R / "gpu/virtual/virtual.json",
                receipt=R / "receipt.json", post=R / "post/post.json", quality=R / "post/quality.json", eval_points=R / "gpu/eval_points.npz")


def load_result(site, res):
    p = result_paths(site, res)
    if res.startswith("surface_"):
        P = np.load(p["prior_npz"])
        return (lambda: MeshScene(P["V"], P["F"])), None, p
    gs = None
    if p.get("dump") is not None and p["dump"].exists():
        d = np.load(p["dump"])
        gs = dict(xyz=d["xyz"].astype(np.float64), origin=d["origin"] if "origin" in d.files else None, opacity=d["opacity"])
    return (lambda: MeshScene.from_ply(p["mesh"])), gs, p


# ------------------------------------------------------------------------------------------------ inputs of a unit
class Inputs:
    def __init__(self, site, prior):
        self.site, self.prior = site, prior
        D = OUT / "defs" / site
        G = np.load(D / "gt_classes.npz")
        self.X = {0: G["xyz_gt_points"].astype(np.float64)}
        if "xyz_gt_primary" in G.files:
            self.X[1] = G["xyz_gt_primary"].astype(np.float64)
        self.G = G
        r = dict(np.load(D / f"rows_{prior}.npz"))
        self.r = r
        self.R = np.load(OUT / "regions_v3" / f"regions_ext_v3_{site}_{prior}.npz")
        self.src, self.pt, self.pa, self.kind = r["src"], r["point"], r["patch"].astype(np.int64), r["kind"]
        self.code, self.tau, self.D, self.n = r["code"], r["tau"].astype(np.float64), r["D"].astype(np.float64), r["n"].astype(np.float64)
        self.slope, self.value, self.sW = r["slope"].astype(np.float64), r["value"].astype(np.float64), r["sW"].astype(np.float64)
        self.thin, self.inb = r["thin"], r["in_band_v2"]
        self.P = np.zeros((len(self.pt), 3))
        for s, X in self.X.items():
            m = self.src == s
            self.P[m] = X[self.pt[m]]
        self.w_patch, self.w_centre, self.w_code, self.w_dist = r["w_patch"], r["w_centre"], r["w_code"], r["w_dist"]


# ------------------------------------------------------------------------------------------------ bundles
def accuracy(I, sc, res, rows):
    acc = I.code == 2
    roof_rows = acc & (I.kind == 1)
    wall_rows = acc & (I.kind == 2)
    out_rows = roof_rows & ~I.inb
    val = np.full(len(I.pt), np.nan)
    steep = np.zeros(len(I.pt), bool)
    if out_rows.any():
        v, s = roof_reading(sc, I.P[out_rows], I.n[out_rows], I.slope[out_rows], STEEP, 2.0)
        val[out_rows] = v
        steep[out_rows] = s
    bandv = np.full(len(I.pt), np.nan)
    for m in (roof_rows & I.inb, wall_rows):
        if m.any():
            bandv[m] = sc.along(I.P[m], I.n[m], 2.0)
    gentle = out_rows & ~steep
    sus = I.r["suspect"]
    out = {}
    for tag, th in (("thinned", I.thin), ("unthinned", np.ones(len(I.pt), bool))):
        out[tag] = dict(gentle=dict(**stats.bias_dispersion(val[gentle & th]), no_crossing=int(np.isnan(val[gentle & th]).sum())),
                        steep=dict(**stats.bias_dispersion(val[out_rows & steep & th]), no_crossing=int(np.isnan(val[out_rows & steep & th]).sum())),
                        band=dict(**stats.bias_dispersion(bandv[roof_rows & I.inb & th]), no_crossing=int(np.isnan(bandv[roof_rows & I.inb & th]).sum())),
                        wall=dict(**stats.bias_dispersion(bandv[wall_rows & th]), no_crossing=int(np.isnan(bandv[wall_rows & th]).sum())),
                        gentle_without_suspect=stats.bias_dispersion(val[gentle & th & ~sus]))
    by_slope = []
    for a, b in zip(SLOPES[:-1], SLOPES[1:]):
        ms = roof_rows & (I.slope >= a) & (I.slope < b) & I.thin
        by_slope.append(dict(slope_deg=[a, b], roof_points=int(ms.sum()), band_share=round(float(I.inb[ms].mean()), 4) if ms.any() else None))
    fp = json.loads((DR / "s02_box" / I.site / "footprints.json").read_text())["footprints"]
    by_b = {}
    for f in fp:
        inside = MPath(np.asarray(f["ring_local"])).contains_points(I.P[:, :2])
        g = inside & gentle & I.thin
        by_b[f["building"]] = dict(gentle_points=int(g.sum()), bias=stats.bias_dispersion(val[g])["bias"], nmad=stats.bias_dispersion(val[g])["nmad"])
    res["accuracy"] = dict(judged="thinned", condition_3_nmad=out["thinned"]["gentle"]["nmad"], condition_3_points=out["thinned"]["gentle"]["n"],
                           **out, by_slope=by_slope, by_building=by_b)
    rows.update(acc_val=val.astype(np.float32), acc_steep=steep, acc_band_val=bandv.astype(np.float32))


def spread(I, sc, gs, res, rows):
    sel = np.isin(I.code, (11, 3, 13, 12))
    cls = np.full(len(I.pt), -1, np.int8)
    if sel.any():
        c, _ = lines.four_way(sc, I.P[sel], I.D[sel], I.sW[sel], 0.5, 0.5)
        cls[sel] = c
    amb = np.abs(I.sW) < 0.2
    main = ~amb
    th = I.thin
    sus = I.r["suspect"]
    within, viol = I.r["obs_within"], I.r["premise_violation"]
    out = {}
    regions_ = (("prior_error", I.code == 11), ("observation_error_within_threshold", (I.code == 3) & within),
                ("observation_error", I.code == 3), ("premise_violation_interior", (I.code == 3) & viol),
                ("double_error_record", I.code == 12), ("missing_prior_error_record", I.code == 13))
    for nm, m in regions_:
        m = m & th
        e = dict(points=int(m.sum()), patches=int(len(np.unique(I.pa[m]))), main=lines.shares(cls[m & main]),
                 indeterminable_share=round(float(amb[m].mean()), 4) if m.any() else None,
                 roof=lines.shares(cls[m & main & (I.kind == 1)]), wall=lines.shares(cls[m & main & (I.kind == 2)]))
        if nm.startswith("observation_error"):
            e["main_without_suspect"] = lines.shares(cls[m & main & ~sus])
        out[nm] = e
    # unthinned main numbers (to explain the change of 3.5)
    out["unthinned"] = {nm: lines.shares(cls[m & main]) for nm, m in regions_}
    # size bins of the prior-error rows (thinned main points), merged by the 10,000-point rule within the unit
    ratio = np.abs(I.sW) / I.tau
    m11 = (I.code == 11) & main & th
    edges = [1.0, 1.5, 2.0, 3.0, 4.0, 8.0, None]
    counts = [int((m11 & (ratio >= edges[i]) & ((ratio < edges[i + 1]) if edges[i + 1] is not None else True)).sum()) for i in range(6)]
    groups = bins.merge_small(counts, 10_000)
    curve = []
    below = m11 & (ratio < 1.0)
    curve.append(dict(bin=[0.0, 1.0], merged_from=None, points=int(below.sum()), shares=lines.shares(cls[below]),
                      correction_rate=lines.shares(cls[below])["gt_side"], separate=True))
    for g in groups:
        lo, hi = edges[g[0]], edges[g[-1] + 1]
        mb = m11 & (ratio >= lo) & ((ratio < hi) if hi is not None else True)
        sh = lines.shares(cls[mb])
        curve.append(dict(bin=[lo, hi], merged_from=[[edges[i], edges[i + 1]] for i in g], points=int(mb.sum()), patches=int(len(np.unique(I.pa[mb]))),
                          shares=sh, correction_rate=sh["gt_side"]))
    tr = float(np.median(I.tau[(I.code == 11) & (I.kind == 1)])) if ((I.code == 11) & (I.kind == 1)).any() else None
    bnd = bins.boundary([c_["correction_rate"] for c_ in curve[1:]], [c_["bin"][0] for c_ in curve[1:]]) if len(curve) > 1 else None
    out["size_curve"] = dict(bins=curve, raw_counts=counts, groups=groups, boundary_tau=bnd, boundary_roof_m=None if (bnd is None or tr is None) else round(bnd * tr, 3),
                             tau_roof=tr, note="within the unit; pooled over the sites in the tables")
    if gs is not None and gs.get("origin") is not None:
        op, org, gx = gs["opacity"], gs["origin"], gs["xyz"]
        far = I.w_dist > 0.5
        cp = count_near(I.w_centre, gx[(org == 1) & (op >= 0.5)], 0.25)
        ca = count_near(I.w_centre, gx[op >= 0.5], 0.25)
        ps = {}
        for nm, cc, cnt in (("prior_error", 11, cp), ("double_error_record", 12, cp), ("missing_prior_error_record", 13, cp), ("invisible_prior_error_record", 14, cp),
                            ("observation_error_any_origin", 3, ca)):
            mm = (I.w_code == cc) & far
            ps[nm] = dict(patches=int(mm.sum()), patches_all=int((I.w_code == cc).sum()), rate=round(float((cnt[mm] > 0).mean()), 4) if mm.any() else None)
        out["past_shape"] = ps
        rows["w_count_prior"] = cp.astype(np.int32)
        rows["w_count_any"] = ca.astype(np.int32)
    res["spread"] = out
    rows.update(cls=cls)


def completeness(I, sc, res, rows):
    dist = np.full(len(I.pt), np.nan, np.float32)
    band = I.r["premise_band"]
    need = (np.isin(I.code, (4, 5)) | band) & I.thin
    if need.any():
        dist[need] = sc.distance(I.P[need])
    comp = {}
    for nm, m in (("missing_agreement", I.code == 4), ("invisible_agreement", I.code == 5), ("premise_band", band)):
        m = m & I.thin
        comp[nm] = dict(all=stats.within(dist[m]), roof=stats.within(dist[m & (I.kind == 1)]), wall=stats.within(dist[m & (I.kind == 2)]),
                        patches=int(len(np.unique(I.pa[m]))))
    comp["condition_4_completeness_0_2"] = comp["premise_band"]["all"]["le_0.2"]
    comp["condition_4_points"] = comp["premise_band"]["all"]["n"]
    res["completeness"] = comp
    rows["dist"] = dist


def unseen(I, sc, gs, res, rows):
    f = OUT / "defs" / I.site / "unseen.npz"          # the B173 unseen wall patches (LoD2 store), read for the results of both units
    if not f.exists():
        return
    un = np.load(f)
    cu, li, lt = un["centre"], un["label_inferred"], un["label_true"]
    groups = {"invisible_agreement_inferred": li == 0, "invisible_error_inferred": li == 1, "ambiguous": li == 2, "true_agreement_label": lt == 0,
              "true_conflict_label": lt == 1}
    dc = sc.distance(cu)
    u = dict(patches=int(len(cu)), mesh_within={k: stats.within(dc[m]) for k, m in groups.items()})
    if gs is not None and gs.get("origin") is not None:
        op, org, gx = gs["opacity"], gs["origin"], gs["xyz"]
        cnt = count_near(cu, gx[(org == 1) & (op >= 0.5)], 0.25)
        u["inheritance_rate_inferred"] = round(float((cnt[groups["invisible_agreement_inferred"]] > 0).mean()), 4)
        u["past_shape_invisible_inferred"] = round(float((cnt[groups["invisible_error_inferred"]] > 0).mean()), 4)
        u["by_group"] = {k: dict(patches=int(m.sum()), share=round(float((cnt[m] > 0).mean()), 4) if m.any() else None) for k, m in groups.items()}
    res["unseen"] = u


def floating(site, p, gs, res):
    if gs is None or not p.get("floater_mask") or not Path(p["floater_mask"]).exists():
        return
    fm = np.load(p["floater_mask"])
    fj = json.loads(Path(p["floaters"]).read_text())
    tr = np.load(OUT / "defs" / site / "top_raster.npz")
    x = gs["xyz"][fm]
    q = np.clip(np.floor((x[:, :2] - tr["lo"]) / float(tr["cell"])).astype(np.int64), 0, np.array(tr["grid"].shape[::-1]) - 1)
    h = x[:, 2] - tr["grid"][q[:, 1], q[:, 0]]
    near = h <= 20
    org = gs["origin"][fm] if gs.get("origin") is not None else np.zeros(len(x), np.int8)
    res["floating"] = dict(near_3_20m=int(near.sum()), near_prior=int((near & (org == 1)).sum()), above_20m=int((~near).sum()),
                           above_20m_prior=int((~near & (org == 1)).sum()), pixel_share_all=round(fj["pixel_share"], 6))


def summary(site, res_name, p, res):
    import open3d as o3d
    bsd = np.load(OUT / "defs" / site / "bsurf.npz")
    G = np.load(OUT / "defs" / site / "gt_classes.npz")
    X = G["xyz_gt_points"].astype(np.float64)

    def in_cells(P_):
        ix = np.floor((P_[:, 0] + 690953.0 - float(bsd["e0"])) / float(bsd["res"])).astype(np.int64)
        iy = np.floor((P_[:, 1] + 5336071.0 - float(bsd["n0"])) / float(bsd["res"])).astype(np.int64)
        return np.isin(iy * int(bsd["nx"]) + ix, bsd["keys"])
    if res_name.startswith("surface_"):
        P_ = np.load(p["prior_npz"])
        V, F = P_["V"].astype(np.float64), P_["F"].astype(np.int64)
    else:
        m = o3d.io.read_triangle_mesh(str(p["mesh"]))
        V, F = np.asarray(m.vertices), np.asarray(m.triangles)
    tri_in = np.zeros(len(F), bool)
    for b in range(0, len(F), 4_000_000):
        T3 = V[F[b:b + 4_000_000]]
        tri_in[b:b + 4_000_000] = in_cells(T3.mean(1)) | (0.5 * np.linalg.norm(np.cross(T3[:, 1] - T3[:, 0], T3[:, 2] - T3[:, 0]), axis=1) > 0.01)
        del T3
    smp = cloud.sample_mesh(V, F[tri_in], 400, seed=0)
    smp = smp[in_cells(smp)]
    del V, F
    Gb = X[bsd["bs"]]
    cp_, dRG, dGR = cloud.chamfer_pcf(smp, Gb, ts=(0.2, 0.5))
    cmp_ = smp[cloud.voxel_thin(smp, 0.05)] if len(smp) else smp
    ok = bsd["core_ok"]
    d3, nr_, nc_ = cloud.m3c2(bsd["core"][ok], bsd["core_normal"][ok], bsd["gt_thin"].astype(np.float64), cmp_, radius=0.25, half_len=1.0, min_n=5)
    m3 = stats.robust(d3)
    s = dict(result_points=int(len(smp)), gt_points=int(len(Gb)), **cp_,
             m3c2=dict(core_points=int(ok.sum()), share_with_distance=round(float(np.isfinite(d3).mean()), 4), median=m3["median"], nmad=m3["nmad"]))
    for k in ("receipt", "quality"):
        if p.get(k) is not None and Path(p[k]).exists():
            j = json.loads(Path(p[k]).read_text())
            if k == "receipt":
                s["time_memory"] = dict(wall_seconds=j.get("wall_seconds"), gpu_memory_used_mib=j.get("gpu_memory_used_mib"), status=j.get("status"))
            else:
                s["image_quality"] = j.get("mean")
    res["summary"] = s


def virtual(site, p, res):
    if not p.get("virtual") or not Path(p["virtual"]).exists():
        return
    f = OUT / "defs" / site / "unseen.npz"
    if not f.exists():
        return
    un = np.load(f)
    sc = MeshScene.from_ply(p["virtual"])
    d = sc.distance(un["centre"])
    li = un["label_inferred"]
    vj = json.loads(Path(p["virtual_json"]).read_text()) if Path(p["virtual_json"]).exists() else {}
    res["virtual"] = dict(option="option2", below_roof_within_0_5=round(float((d[li == 0] <= 0.5).mean()), 4) if (li == 0).any() else None,
                          above_roof_within_0_2=round(float((d[li == 1] <= 0.2).mean()), 4) if (li == 1).any() else None,
                          peak_host_gb=vj.get("peak_host_gb"), note="mesh level; read with the inheritance rate (Gaussian level)")


def main(site, unit, results, bundles):
    I = Inputs(site, unit)
    for res_name in results:
        T = Timer()
        mk, gs, p = load_result(site, res_name)
        sc = mk()
        O = OUT / "metrics" / site
        O.mkdir(parents=True, exist_ok=True)
        f = O / f"{res_name}__{unit}.json"
        rf = O / f"{res_name}__{unit}_rows.npz"
        res = json.loads(f.read_text()) if f.exists() else dict(site=site, unit=unit, result=res_name, seconds={})
        rows = dict(np.load(rf)) if rf.exists() else {}
        T.mark("load")
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
                floating(site, p, gs, res)
            elif b == "summary":
                summary(site, res_name, p, res)
            elif b == "virtual":
                virtual(site, p, res)
            T.mark(b)
        res["seconds"].update(T.marks)
        res["scientific_verdict"] = None
        jdump(f, res)
        np.savez_compressed(rf, **rows)
        log(site, unit, res_name, bundles, T.marks)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("site")
    ap.add_argument("unit", choices=["LoD2", "ALS"])
    ap.add_argument("results", nargs="+")
    ap.add_argument("--bundles", default=",".join(ALL))
    a = ap.parse_args()
    main(a.site, a.unit, a.results, a.bundles.split(","))
