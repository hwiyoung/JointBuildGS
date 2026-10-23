"""PHD-MAIN-UNCERT-v1 일 1: the places of 5.2 resolved into patch lists (jointbuildgs:dev, CPU), from the region files, the GT planes
(gt_<site>_<set>.npz: has a plane, one layer) and the earlier tasks' place files only -- before any uncertainty value is computed.

  python u1_places.py   -> /out/work/places.json, /out/work/places.npz (patch lists per place and prior)

Rules: config places.list. The other prior's patches = its patches with a centre within 0.25 m (3-D) of a place patch centre.
scientific_verdict: null."""
import json
import sys

import numpy as np
from scipy.ndimage import binary_dilation
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

sys.path.insert(0, "/repo/scripts/phd/main_uncert_v1")
import uc_common as U  # noqa: E402

PL = U.CFG["places"]["list"]


def other(site, prior, idx):
    """patches of the other prior within 0.25 m of the centres idx of `prior`."""
    op = "ALS" if prior == "LoD2" else "LoD2"
    A = U.patches(site, prior)["centre"][idx]
    B = U.patches(site, op)["centre"]
    if not len(idx):
        return op, np.zeros(0, np.int64)
    hits = cKDTree(A).query_ball_point(B, 0.25 + 1e-9, return_length=True)
    return op, np.nonzero(hits > 0)[0]


def area(site, prior, idx):
    return float(U.patches(site, prior)["area"][idx].sum())


def wing(site):
    """configs/phd/main_stage1_vis_v3/vis_v3.json wing_region (scripts/phd/main_stage1_vis_v3/measure_v3.wing_regions)."""
    sites = {s["id"]: s for s in json.loads((U.REPO / "configs/phd/main_prep_discard_rule_v1/sites_v1.json").read_text())["sites"]}
    tab = json.loads((U.DR / "s02_box" / site / "lod2_surfaces.json").read_text())["surfaces"]
    exts = [r["ext"] for r in tab if r["gml"] in sites["B173_wings"]["faces_gml"]]
    Un = np.load(U.S0 / "s61/box" / site / "LoD2/units.npz")
    se = Un["surf_ext"][Un["loc_surface"]]
    wl = np.isin(se, exts)
    R = {p: U.regions(site, p) for p in U.PRIORS}
    out = {"LoD2": np.nonzero(wl & (R["LoD2"]["code_ext_v3"] == 11) & R["LoD2"]["in_eval"])[0]}
    uv = U.xy_to_uv(Un["loc_center"][wl][:, :2])
    lo = np.floor(uv.min(0)) - 1.0
    ij = np.floor((uv - lo) / 0.25).astype(int)
    M = np.zeros(ij.max(0) + 3, bool)
    M[ij[:, 0], ij[:, 1]] = True
    M = binary_dilation(M, iterations=1)
    uva = U.xy_to_uv(R["ALS"]["centre"][:, :2])
    ija = np.floor((uva - lo) / 0.25).astype(int)
    ok = (ija >= 0).all(1) & (ija[:, 0] < M.shape[0]) & (ija[:, 1] < M.shape[1])
    inside = np.zeros(len(uva), bool)
    inside[ok] = M[ija[ok, 0], ija[ok, 1]]
    out["ALS"] = np.nonzero(inside & (R["ALS"]["code_ext_v3"] == 11) & R["ALS"]["in_eval"])[0]
    return out, dict(wing_faces=exts, lod2_wing_units=int(wl.sum()))


def chosen(site, prior, key):
    pt = U.patches(site, prior)
    g = np.load(U.WORK / f"gt_{site}_{prior}.npz")
    m = U.cell_mask(pt["cell"], key) & (g["status"] == 0) & (g["runs"] == 1)
    idx = np.nonzero(m)[0]
    if not len(idx):
        return np.zeros(0, np.int64), dict(candidates=0)
    C = pt["centre"][idx]
    pairs = cKDTree(C).query_pairs(0.36, output_type="ndarray")
    A = coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(len(idx), len(idx)))
    nc, lab = connected_components(A, directed=False)
    ar = np.bincount(lab, weights=pt["area"][idx], minlength=nc)
    big = np.nonzero(ar >= 2.5)[0]
    info = dict(candidates=int(len(idx)), clumps=int(nc), clumps_ge_2_5m2=int(len(big)))
    if not len(big):
        return np.zeros(0, np.int64), dict(info, chosen=None)
    k = int(big[np.argmax(ar[big])])
    sel = idx[lab == k]
    return sel, dict(info, chosen_area_m2=float(ar[k]), chosen_patches=int(len(sel)), second_area_m2=float(np.sort(ar[big])[-2]) if len(big) > 1 else None)


def main():
    T = U.Timer()
    out, arrs = {}, {}

    def put(name, site, prior, idx, info):
        idx = np.asarray(sorted(set(np.asarray(idx, np.int64).tolist())), np.int64)
        op, oidx = other(site, prior, idx)
        pt = U.patches(site, prior)
        g = np.load(U.WORK / f"gt_{site}_{prior}.npz")
        rec = dict(site=site, prior=prior, patches=int(len(idx)), area_m2=area(site, prior, idx),
                   in_eval=int(pt["in_eval"][idx].sum()), roof_like=int(pt["roof_like"][idx].sum()),
                   gt_plane=int((g["status"][idx] == 0).sum()), gt_multi_layer=int((g["runs"][idx] >= 2).sum()),
                   other=dict(prior=op, patches=int(len(oidx)), area_m2=area(site, op, oidx)), **info)
        out[name] = rec
        arrs[f"{name}__{prior}"] = idx
        arrs[f"{name}__{op}"] = oidx
    v4 = json.loads((U.V4 / "prep/places.json").read_text())
    s = "B173nb_b10"
    put("glass_strip", s, "ALS", v4["V6"]["glass"] + v4["V6"]["ring_missing"], dict(ko=PL["glass_strip"]["ko"], glass=len(v4["V6"]["glass"]),
                                                                                     ring_missing=len(v4["V6"]["ring_missing"]), source=PL["glass_strip"]["source"]))
    put("glass_dome", s, "ALS", v4["V5"]["place"], dict(ko=PL["glass_dome"]["ko"], source=PL["glass_dome"]["source"]))
    fr = np.load(U.FT / "prep/figpos_fig1_rows.npz")
    rw = np.load(U.S1 / "defs" / s / "rows_ALS.npz")
    fpatch = rw["patch"][fr["rows"]]
    gtx = np.load(U.S1 / "defs" / s / "gt_classes.npz")["xyz_gt_points"]
    same_xyz = bool(np.allclose(gtx[rw["point"][fr["rows"]]].astype(np.float64), fr["xyz_gt"], atol=1e-4)) if "point" in rw.files else None
    v3 = np.asarray(v4["V3"]["place"], np.int64)
    up = np.unique(fpatch)
    put("flat_roof", s, "ALS", up, dict(ko=PL["flat_roof"]["ko"], source=PL["flat_roof"]["source"], rows=int(len(fr["rows"])),
                                        rows_point_xyz_equal=same_xyz, v4_V3_patches=int(len(v3)), overlap_with_V3=int(np.isin(up, v3).sum())))
    wm, winfo = wing(s)
    for p in U.PRIORS:
        idx = wm[p]
        pt = U.patches(s, p)
        g = np.load(U.WORK / f"gt_{s}_{p}.npz")
        out[f"b173_wing__{p}"] = dict(ko=PL["b173_wing"]["ko"], site=s, prior=p, patches=int(len(idx)), area_m2=area(s, p, idx),
                                      gt_plane=int((g["status"][idx] == 0).sum()), gt_multi_layer=int((g["runs"][idx] >= 2).sum()),
                                      roof_like=int(pt["roof_like"][idx].sum()), source=PL["b173_wing"]["source"], **winfo)
        arrs[f"b173_wing__{p}"] = idx
    put("r1_step_roof", "R1rep_b10", "LoD2", v4["V1"]["place"], dict(ko=PL["r1_step_roof"]["ko"], source=PL["r1_step_roof"]["source"]))
    out["r1_low_flat"] = dict(ko=PL["r1_low_flat"]["ko"], status="확인 불가", why=PL["r1_low_flat"]["source"])
    for site, prior in U.CASES:
        for key in ("s_corr", "s_keep"):
            sel, info = chosen(site, prior, key)
            nm = f"chosen_{site}_{prior}_{key}"
            if len(sel):
                put(nm, site, prior, sel, dict(ko=f"{U.SITE_KO[site]} {U.PRIOR_KO[prior]} {U.KEY_KO[key]}", rule=PL["chosen"]["rule"], **info))
            else:
                out[nm] = dict(ko=f"{U.SITE_KO[site]} {U.PRIOR_KO[prior]} {U.KEY_KO[key]}", status="없음", **info)
    np.savez(U.WORK / "places.npz", **arrs)
    U.jdump(U.WORK / "places.json", dict(rule=__doc__, made=U.now(), env=U.env(), places=out, arrays=sorted(arrs), seconds=T.mark("all"),
                                         scientific_verdict=None))
    for k, v in out.items():
        U.log(k, {kk: vv for kk, vv in v.items() if kk in ("patches", "area_m2", "gt_multi_layer", "status", "other")})


if __name__ == "__main__":
    main()
