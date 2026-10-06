"""PHD-MAIN-STAGE0-v1 5.4: the quick comparison of the stage-0 results with the ground truth (jointbuildgs:dev, CPU). A check
only, not the main experiment's metrics; definitions = configs stage0_v1.json stage0.quick_gt_check (written before any result).

  python quick_gt.py b1_LoD2 b1_ALS [b2_LoD2 b2_ALS]

GT points: the B173nb_b10 box GT (/dr/s52/box_gt: cleaned, aligned ULS nadir) inside the evaluation range, excluded cells
removed. Wall points = single-return points on vertical surfaces (v4 rule); roof points = the others inside a LoD2 footprint.
Per run (TSDF mesh of the training views, post/mesh_tsdf.ply):
  roof height difference z_result - z_GT (highest mesh hit of the vertical line through the point): median, NMAD
  within: share of GT points whose unsigned distance to the mesh is <= 0.2 m / <= 0.5 m (roof, wall, all)
splits: changed = roof points inside the plan polygons of the two B173 wing roof faces; agreement = points owned (s04 v6 rule,
s61/box_gt gt_owner_<prior>) by patches of the prior's agreement region (5.3 codes 2-5; measured 2, unmeasured 4-5);
unseen = points owned by LoD2 wall patches of DEBY_LOD2_4959326 that are invisible in the v6 LoD2 box run, plus the share of
those patch centres within 0.2 / 0.5 m of the mesh. Writes quick/quick_<run>.json and quick/spread.json. scientific_verdict: null."""
import json
import sys

import numpy as np
import open3d as o3d
from matplotlib.path import Path as MPath
from shapely.geometry import Polygon as SPoly
from shapely.ops import unary_union

from common import DR, OUT, PREP, SCFG, jdump, log, xy_to_uv
import s04_gt_v6 as s4

SITE = SCFG["stage0"]["site"]
NMAD_C = 1.4826
WINGS = ["DEBY_LOD2_4959326_66ac9a84-cf24-4ba6-b5b9-9427d0c20e8b_2", "DEBY_LOD2_4959326_f94b116f-de50-4bff-8e53-0c6a023b9d2f_2"]
B173 = "DEBY_LOD2_4959326"


def stats(dz):
    dz = dz[np.isfinite(dz)]
    if not len(dz):
        return dict(n=0, median=None, nmad=None)
    m = float(np.median(dz))
    return dict(n=int(len(dz)), median=round(m, 4), nmad=round(float(NMAD_C * np.median(np.abs(dz - m))), 4))


def within(d):
    d = d[np.isfinite(d)]
    return dict(n=int(len(d)), le_0_2=round(float((d <= 0.2).mean()), 4) if len(d) else None, le_0_5=round(float((d <= 0.5).mean()), 4) if len(d) else None)


def setup():
    g = np.load(DR / "s52/box_gt" / SITE / "gt_points.npz"); X = g["xyz"].astype(np.float64); multi = g["multi"]
    ez = np.load(DR / "s52/box_gt" / SITE / "exclusion_cells.npz")["any"]
    D, A = s4.survey_grids(); grid = s4.Grid(D["dtm"].shape)
    iy, ix, ok = grid.idx(X[:, 0], X[:, 1])
    excl = ok & ez[iy, ix]
    b = json.loads((PREP / "step06/boxes_v1.json").read_text())["boxes"]["B173nb"]
    uv = xy_to_uv(X[:, :2])
    inev = (uv[:, 0] >= b["eval_u"][0]) & (uv[:, 0] <= b["eval_u"][1]) & (uv[:, 1] >= b["eval_v"][0]) & (uv[:, 1] <= b["eval_v"][1])
    vert = s4.vertical_points(X) & ~multi
    md = DR / "s02_box" / SITE
    fp = json.loads((md / "footprints.json").read_text())["footprints"]
    infp = np.zeros(len(X), bool)
    for r in fp:
        infp |= MPath(np.asarray(r["ring_local"])).contains_points(X[:, :2])
    use = inev & ~excl
    roof = use & infp & ~vert; wall = use & vert
    # wing polygons (plan) of the two B173 wing roof faces
    m = np.load(md / "lod2_mesh.npz"); tab = json.loads((md / "lod2_surfaces.json").read_text())["surfaces"]
    ext = [r["ext"] for r in tab if r["gml"] in WINGS]
    tris = m["F"][np.isin(m["tri_surface"], ext)]
    wing_poly = unary_union([SPoly(m["V"][t][:, :2]) for t in tris]).buffer(0)
    wing = np.zeros(len(X), bool)
    for gpoly in getattr(wing_poly, "geoms", [wing_poly]):
        wing |= MPath(np.asarray(gpoly.exterior.coords)).contains_points(X[:, :2])
    changed = roof & wing
    # agreement regions (5.3) and ownership (s04 v6)
    own, reg = {}, {}
    for pr in ("LoD2", "ALS"):
        o = np.load(OUT / "s61/box_gt" / SITE / f"gt_owner_{pr}.npz"); R = np.load(OUT / "regions" / f"regions_{SITE}_{pr}.npz")
        code = np.full(len(X), -2, np.int8); code[o["point"]] = R["code"][o["patch"]]
        own[pr] = o; reg[pr] = R
        reg[pr + "_point_code"] = code
    # unseen: LoD2 wall patches of B173 invisible in the v6 LoD2 box run
    U = np.load(OUT / "s61/box" / SITE / "LoD2" / "units.npz")
    tabd = {r["ext"]: r for r in tab}
    bld = np.array([tabd[int(e)]["building"] == B173 for e in U["surf_ext"][U["loc_surface"]]])
    unseen_p = bld & (U["loc_kind"] == 2) & (U["state"] == 0) & reg["LoD2"]["in_eval"]
    o = own["LoD2"]; unseen_pts = np.zeros(len(X), bool)
    unseen_pts[o["point"][unseen_p[o["patch"]]]] = True
    unseen_pts &= use
    return dict(X=X, use=use, roof=roof, wall=wall, changed=changed, codes={pr: reg[pr + "_point_code"] for pr in ("LoD2", "ALS")},
                unseen=unseen_pts, unseen_centres=U["loc_center"][unseen_p], n_unseen_patches=int(unseen_p.sum()))


def evaluate(run, S):
    mesh = o3d.io.read_triangle_mesh(str(OUT / "stage0" / run / "post/mesh_tsdf.ply"))
    sc = o3d.t.geometry.RaycastingScene(); sc.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(mesh))
    X = S["X"]; prior = run.split("_")[1]
    d = np.full(len(X), np.nan); idx = np.nonzero(S["use"])[0]
    d[idx] = sc.compute_distance(o3d.core.Tensor(X[idx].astype(np.float32))).numpy()
    dz = np.full(len(X), np.nan); ir = np.nonzero(S["roof"])[0]
    rays = np.concatenate([X[ir, :2], np.full((len(ir), 1), 250.0), np.tile([0, 0, -1.0], (len(ir), 1))], 1).astype(np.float32)
    t = sc.cast_rays(o3d.core.Tensor(rays))["t_hit"].numpy()
    dz[ir] = np.where(np.isfinite(t), 250.0 - t, np.nan) - X[ir, 2]
    code = S["codes"][prior]
    parts = dict(all=S["use"], roof=S["roof"], wall=S["wall"], changed=S["changed"],
                 agreement=S["use"] & np.isin(code, (2, 3, 4, 5)), agreement_measured=S["use"] & (code == 2),
                 agreement_unmeasured=S["use"] & np.isin(code, (4, 5)), unseen=S["unseen"])
    out = dict(run=run, prior=prior, mesh_triangles=len(mesh.triangles), parts={})
    for nm, m in parts.items():
        out["parts"][nm] = dict(points=int(m.sum()), roof_dz=stats(dz[m & S["roof"]]), within=within(d[m]),
                                roof_points_without_mesh_hit=int((m & S["roof"] & ~np.isfinite(dz)).sum()))
    c = S["unseen_centres"]
    dc = sc.compute_distance(o3d.core.Tensor(c.astype(np.float32))).numpy() if len(c) else np.zeros(0)
    out["unseen_patch_centres"] = dict(patches=S["n_unseen_patches"], within=within(dc))
    # added after the first look (purpose: the TSDF of the training views cannot show what no training view sees, so the
    # Gaussians at the unseen patches are counted directly; a record, not a criterion): prior-origin Gaussians of the final
    # dump within 0.25 m of an unseen patch centre
    from scipy.spatial import cKDTree
    dmp = np.load(OUT / "stage0" / run / "model/dump" / f"iteration_{SCFG['stage0']['iterations']}" / "gaussians.npz")
    gx, go, gop = dmp["xyz"].astype(np.float64), dmp["origin"], dmp["opacity"]
    gk = {}
    for nm, m in (("prior_any_opacity", go == 1), ("prior_opacity_ge_0.5", (go == 1) & (gop >= 0.5)), ("image_opacity_ge_0.5", (go == 0) & (gop >= 0.5))):
        if len(c) and m.any():
            cnt = np.array([len(x) for x in cKDTree(gx[m]).query_ball_point(c, 0.25)])
            gk[nm] = dict(share_of_patches_with_one=round(float((cnt > 0).mean()), 4), median_count=float(np.median(cnt)))
    out["unseen_patch_gaussians"] = dict(rule="Gaussians of the final dump within 0.25 m of the unseen patch centres (record only)", **gk)
    np.savez_compressed(OUT / "quick" / f"quick_{run}.npz", d=d.astype(np.float32), dz=dz.astype(np.float32))
    return out


def main():
    runs = sys.argv[1:]
    (OUT / "quick").mkdir(exist_ok=True)
    S = setup()
    log("GT points in range", int(S["use"].sum()), "roof", int(S["roof"].sum()), "wall", int(S["wall"].sum()), "changed", int(S["changed"].sum()),
        "unseen", int(S["unseen"].sum()), "unseen patches", S["n_unseen_patches"])
    res = {}
    for r in runs:
        res[r] = evaluate(r, S)
        jdump(OUT / "quick" / f"quick_{r}.json", dict(rule=SCFG["stage0"]["quick_gt_check"], **res[r], scientific_verdict=None))
        log(r, {k: (v["roof_dz"]["median"], v["within"]["le_0_2"]) for k, v in res[r]["parts"].items()})
    if all(f"b{b}_{p}" in res for b in (1, 2) for p in ("LoD2", "ALS")):
        spread = {}
        for p in ("LoD2", "ALS"):
            a_, b_ = res[f"b1_{p}"], res[f"b2_{p}"]
            spread[p] = {nm: dict(roof_dz_median=None if a_["parts"][nm]["roof_dz"]["median"] is None else round(b_["parts"][nm]["roof_dz"]["median"] - a_["parts"][nm]["roof_dz"]["median"], 4),
                                  roof_dz_nmad=None if a_["parts"][nm]["roof_dz"]["nmad"] is None else round(b_["parts"][nm]["roof_dz"]["nmad"] - a_["parts"][nm]["roof_dz"]["nmad"], 4),
                                  le_0_2=None if a_["parts"][nm]["within"]["le_0_2"] is None else round(b_["parts"][nm]["within"]["le_0_2"] - a_["parts"][nm]["within"]["le_0_2"], 4),
                                  le_0_5=None if a_["parts"][nm]["within"]["le_0_5"] is None else round(b_["parts"][nm]["within"]["le_0_5"] - a_["parts"][nm]["within"]["le_0_5"], 4))
                        for nm in a_["parts"]}
            spread[p]["unseen_patch_centres_le_0_5"] = round(b_["unseen_patch_centres"]["within"]["le_0_5"] - a_["unseen_patch_centres"]["within"]["le_0_5"], 4) \
                if a_["unseen_patch_centres"]["within"]["le_0_5"] is not None else None
        jdump(OUT / "quick" / "spread.json", dict(rule="seed 1 (batch 2) minus seed 0 (batch 1), per prior", spread=spread, scientific_verdict=None))


if __name__ == "__main__":
    main()
