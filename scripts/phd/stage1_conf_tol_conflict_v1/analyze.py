"""Step 6 (jointbuildgs:dev): residuals, statistics, tolerance, coverage, conflict maps,
face/point attributes, tables, stage-2 configs and viewer data for 2 priors x 2 conditions.

All numbers are derived only from this task's inputs; nothing is tuned.  Constants come from
configs/phd/stage1_conf_tol_conflict_v1/experiment.json.
"""
import base64
import csv
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy import ndimage

import common as cm

rc = cm.Receipt("analyze")
K_TOL = cm.C["k_tolerance"]
SIG = cm.C["outlier_sigma"]
views = cm.load_views()
PJ = json.loads((cm.INP / "lod2_polygons.json").read_text())
PZ = np.load(cm.INP / "lod2_polygons.npz")
poly_region_code = PZ["poly_region_code"]
target_polys = [p for p in PJ["polygons"] if p["is_target"]]
context_polys = [p for p in PJ["polygons"] if not p["is_target"]]
tp_index = np.array([p["poly_index"] for p in target_polys], np.int64)
tp_local = np.full(len(poly_region_code), -1, np.int64)
tp_local[tp_index] = np.arange(len(target_polys))
poly_normal = np.zeros((len(poly_region_code), 3), np.float32)
for _p in PJ["polygons"]:
    poly_normal[_p["poly_index"]] = _p["normal"]
NB_F = 1000
F_LO, F_BIN = -5.0, 0.01  # per-face residual histogram (1 cm bins, -5..+5 m)
HR = cm.C["hist_range_m"]
HB = cm.C["hist_bin_m"]
NHB = int(round((HR[1] - HR[0]) / HB))
PNG_RANGE = cm.C["res_png_range_m"]
DEPTH_RANGE = cm.C["depth_png_range_m"]
VLONG = cm.C["viewer_long_side_px"]
RLONG = cm.C["readout_long_side_px"]
EDGE_PX = cm.C["edge_band_px_fullres"]
supplied = cm.ART / cm.CFG["scene"]["supplied_lod2_depth_relative"]
REGION_CODE = {"roof": cm.R_ROOF, "wall": cm.R_WALL, "ground": cm.R_GROUND}
tables = cm.OUT / "tables"
tables.mkdir(parents=True, exist_ok=True)
vpng = cm.OUT / "viewer_png"
vdata = cm.OUT / "viewer_data"
vdata.mkdir(parents=True, exist_ok=True)
als = np.load(cm.INP / "als_points.npz")
als_local = als["xyz_local"]
als_cls = als["classification"]


def prior_paths(prior, cond):
    if prior == "M" and cond == "nominal":
        return supplied, cm.INP / "prior_render/M_nominal_recovered/lod2_prior/raw_normal"
    root = cm.INP / f"prior_render/{prior}_{cond}/lod2_prior"
    return root / "raw_depth", root / "raw_normal"


def load_prior_depth(prior, cond, stem):
    d = np.load(prior_paths(prior, cond)[0] / f"{stem}.npy").astype(np.float32, copy=False)
    ok = np.isfinite(d) & (d > 0) & (d < 1e6)
    return np.where(ok, d, np.nan).astype(np.float32), ok


_cache = {}


def view_static(v):
    """Per-view prior-independent arrays: conf, mvs depth, polygon map, region, dz, edge distance."""
    if v["stem"] in _cache:
        return _cache[v["stem"]]
    conf = np.load(cm.OUT / "conf" / f"{v['stem']}_conf.npy")
    mvs = np.load(cm.INP / "mvs_full" / f"{v['stem']}_depth.npy")
    poly = np.load(cm.INP / "faceid" / f"{v['stem']}.npy")
    region = np.where(poly >= 0, poly_region_code[np.maximum(poly, 0)], cm.R_NONE).astype(np.uint8)
    dx, dy, dzs = cm.ray_dirs_world(v)
    dz = np.abs(dzs)
    # vertical factor: gap between parallel planes with LoD2 normal n along a camera-Z ray d is
    # dz_ray * |n.d| / |n_z|; equals |d_z| for horizontal faces.  Used for the roof vertical residual.
    nrm = poly_normal[np.maximum(poly, 0)]
    nd = np.abs(nrm[..., 0] * dx + nrm[..., 1] * dy + nrm[..., 2] * dzs)
    nz = np.abs(nrm[..., 2])
    vfac = np.where((poly >= 0) & (nz > 1e-6), nd / np.maximum(nz, 1e-6), dz).astype(np.float32)
    del nrm, nd, nz, dx, dy, dzs
    ep = cm.INP / "faceid" / f"{v['stem']}_edgedist.npy"
    if ep.exists():
        edge = np.load(ep)
    else:
        b = np.zeros(poly.shape, bool)
        b[1:, :] |= poly[1:, :] != poly[:-1, :]
        b[:, 1:] |= poly[:, 1:] != poly[:, :-1]
        edge = np.minimum(ndimage.distance_transform_edt(~b), 65535).astype(np.uint16)
        np.save(ep, edge)
    st = {"conf": conf, "mvs": mvs, "poly": poly, "region": region, "dz": dz, "vfac": vfac, "edge": edge}
    _cache.clear()
    _cache[v["stem"]] = st
    return st


def region_map_for(prior, region, prior_ok):
    """L: unbuilt pixels covered by the ALS TIN are 'ground'. M: no ground (LoD2 has no terrain)."""
    if prior == "L":
        r = region.copy()
        r[(region == cm.R_NONE) & prior_ok] = cm.R_GROUND
        return r
    return region


def b64(arr):
    return base64.b64encode(np.ascontiguousarray(arr).tobytes()).decode("ascii")


def write_sidecar(path, key, fields):
    parts = ",".join(f'{k}:"{b64(a)}"' if isinstance(a, np.ndarray) else f"{k}:{json.dumps(a)}" for k, a in fields.items())
    Path(path).write_text(f'window.JBGS_PIX=window.JBGS_PIX||{{}};window.JBGS_PIX[{json.dumps(key)}]={{{parts}}};')


# ----------------------------------------------------------------------------- pass 1
stats_rows, cov_rows, hist = [], [], {}
overall_vals = {}  # (prior,cond) -> region -> list of arrays (ray); 'roof_v' for vertical
static_done = set()
viewer_views = []
for v in views:
    st = view_static(v)
    stem = v["stem"]
    if (vpng / "views" / f"{stem}_mvs.png").exists() and (vdata / f"{stem}_common.js").exists():
        from PIL import Image
        vw, vh = Image.open(vpng / "views" / f"{stem}_image.png").size
        viewer_views.append({"stem": stem, "name": v["name"], "W": v["W"], "H": v["H"], "vw": vw, "vh": vh,
                             "C": np.round(v["C"], 3).tolist(), "image_id": v["image_id"]})
        continue
    # static viewer layers (once)
    from PIL import Image
    im = Image.open(cm.SCENE / "images" / v["name"])
    im.thumbnail((VLONG, VLONG), Image.BOX)
    (vpng / "views").mkdir(parents=True, exist_ok=True)
    im.save(vpng / "views" / f"{stem}_image.png", compress_level=3)
    vw, vh = im.size
    cm.to_png(vpng / "views" / f"{stem}_conf.png", np.repeat((cm.downscale_nearest(st["conf"], VLONG) * 255)[..., None], 3, 2))
    cm.to_png(vpng / "views" / f"{stem}_mvs.png", cm.depth_rgb(cm.downscale_nearest(st["mvs"], VLONG), *DEPTH_RANGE))
    viewer_views.append({"stem": stem, "name": v["name"], "W": v["W"], "H": v["H"], "vw": vw, "vh": vh,
                         "C": np.round(v["C"], 3).tolist(), "image_id": v["image_id"]})
    write_sidecar(vdata / f"{stem}_common.js", f"{stem}|common", {
        "w": cm.downscale_nearest(st["conf"], RLONG).shape[1], "h": cm.downscale_nearest(st["conf"], RLONG).shape[0],
        "conf": cm.downscale_nearest(st["conf"], RLONG).astype(np.uint8),
        "mvs": np.nan_to_num(np.clip(cm.downscale_nearest(st["mvs"], RLONG) * 100, 0, 65535), nan=0).astype(np.uint16)})

for prior in cm.PRIORS:
    for cond in cm.CONDS:
        key = (prior, cond)
        overall_vals[key] = defaultdict(list)
        od = cm.OUT / prior / cond
        od.mkdir(parents=True, exist_ok=True)
        (vpng / prior / cond).mkdir(parents=True, exist_ok=True)
        for v in views:
            st = view_static(v)
            stem = v["stem"]
            pd, pok = load_prior_depth(prior, cond, stem)
            region = region_map_for(prior, st["region"], pok)
            if cond == "nominal":  # region map (with L ground) reused by pass 2
                np.save(od / f"{stem}_region.npy", region)
                cm.to_png(vpng / prior / f"{stem}_region.png", cm.region_rgb(cm.downscale_nearest(region, VLONG)))
            both = (st["conf"] == 1) & pok
            r = np.where(both, st["mvs"] - pd, np.nan).astype(np.float32)
            roofsel = both & (region == cm.R_ROOF)
            resv = np.where(roofsel, r * st["vfac"], np.nan).astype(np.float32)
            overall_vals[key]["roof_vh"].append((r * st["dz"])[roofsel])  # horizontal-plane formula, fact only
            np.save(od / f"{stem}_res.npy", r)
            np.save(od / f"{stem}_resv.npy", resv)
            cm.to_png(od / f"{stem}_res.png", cm.diverging_rgb(r, *PNG_RANGE))
            cm.to_png(vpng / prior / cond / f"{stem}_res.png", cm.diverging_rgb(cm.downscale_nearest(r, VLONG), *PNG_RANGE))
            cm.to_png(vpng / prior / cond / f"{stem}_prior.png", cm.depth_rgb(cm.downscale_nearest(pd, VLONG), *DEPTH_RANGE))
            for reg, code in REGION_CODE.items():
                sel = both & (region == code)
                n_mask = int((pok & (region == code)).sum())
                if prior == "M" and reg == "ground":
                    cov_rows.append([prior, cond, stem, reg, 0, 0, None])
                    continue
                cov_rows.append([prior, cond, stem, reg, n_mask, int(sel.sum()), float(sel.sum() / n_mask) if n_mask else None])
                vals = r[sel]
                overall_vals[key][reg].append(vals)
                s = cm.two_pass(vals)
                stats_rows.append([prior, cond, stem, reg, "ray_depth_camZ", s["n"], s["m"], s["s"], s["m2"], s["s2"], s["out_frac"]])
                if reg == "roof":
                    vv = resv[sel]
                    overall_vals[key]["roof_v"].append(vv)
                    s = cm.two_pass(vv)
                    stats_rows.append([prior, cond, stem, reg, "vertical", s["n"], s["m"], s["s"], s["m2"], s["s2"], s["out_frac"]])
            sel = both & ((region == cm.R_ROOF) | (region == cm.R_WALL))
            n_mask = int((pok & ((region == cm.R_ROOF) | (region == cm.R_WALL))).sum())
            cov_rows.append([prior, cond, stem, "all", n_mask, int(sel.sum()), float(sel.sum() / n_mask) if n_mask else None])
            s = cm.two_pass(r[sel])
            stats_rows.append([prior, cond, stem, "all", "ray_depth_camZ", s["n"], s["m"], s["s"], s["m2"], s["s2"], s["out_frac"]])
            overall_vals[key]["all"].append(r[sel])
            n_other = int((pok & (region == cm.R_OTHER)).sum())
            cov_rows.append([prior, cond, stem, "other", n_other, int((both & (region == cm.R_OTHER)).sum()), None])
            print(prior, cond, stem, "roof n", int((both & (region == cm.R_ROOF)).sum()), flush=True)
        # overall
        vh = np.concatenate(overall_vals[key]["roof_vh"]) if overall_vals[key]["roof_vh"] else np.zeros(0, np.float32)
        overall_vals[key]["roof_vh"] = cm.two_pass(vh)
        for reg in ["roof", "wall", "ground", "all", "roof_v"]:
            if reg not in overall_vals[key]:
                continue
            vals = np.concatenate(overall_vals[key][reg]) if overall_vals[key][reg] else np.zeros(0, np.float32)
            overall_vals[key][reg] = vals
            s = cm.two_pass(vals)
            kind = "vertical" if reg == "roof_v" else "ray_depth_camZ"
            rname = "roof" if reg == "roof_v" else reg
            stats_rows.append([prior, cond, "ALL", rname, kind, s["n"], s["m"], s["s"], s["m2"], s["s2"], s["out_frac"]])
            h, _ = np.histogram(vals[np.isfinite(vals)], bins=NHB, range=HR)
            hist[f"{prior}|{cond}|{rname}|{kind}"] = {"counts": h.tolist(), "under": int((vals < HR[0]).sum()), "over": int((vals > HR[1]).sum()),
                                                      "quantiles": cm.quantiles(vals)}
        for reg in ["roof", "wall", "ground", "all"]:
            if reg in overall_vals[key]:
                nm = sum(row[4] for row in cov_rows if row[:2] == [prior, cond] and row[3] == reg)
                nc = sum(row[5] for row in cov_rows if row[:2] == [prior, cond] and row[3] == reg)
                cov_rows.append([prior, cond, "ALL", reg, nm, nc, float(nc / nm) if nm else None])


def overall_stat(prior, cond, region, kind="ray_depth_camZ"):
    for row in stats_rows:
        if row[:5] == [prior, cond, "ALL", region, kind]:
            return dict(zip(["n", "m", "s", "m2", "s2", "out_frac"], row[5:]))
    return None


def overall_cov(prior, cond, region):
    for row in cov_rows:
        if row[:4] == [prior, cond, "ALL", region]:
            return row[6]
    return None


# ----------------------------------------------------------------------------- normals (tau_n)
normal_stats = {}
for prior in cm.PRIORS:
    for cond in cm.CONDS:
        vals = defaultdict(list)
        _, npath = prior_paths(prior, cond)
        for v in views:
            st = view_static(v)
            stem = v["stem"]
            nw = np.load(cm.INP / "mvs_native" / f"{stem}_normal_world.npy")
            h, w = nw.shape[:2]
            ok = np.linalg.norm(nw, axis=2) > 0.5
            mr = json.loads((cm.PROV / "mvs_resampling.json").read_text())
            rec = next(x for x in mr["views"] if x["view"] == stem)
            fx, fy, cx, cy = rec["native_K"]
            xs = (np.arange(w) + 0.5 - cx) / fx
            ys = (np.arange(h) + 0.5 - cy) / fy
            uf = np.clip(np.floor(v["K"][0, 0] * xs + v["K"][0, 2]).astype(int), 0, v["W"] - 1)
            vf = np.clip(np.floor(v["K"][1, 1] * ys + v["K"][1, 2]).astype(int), 0, v["H"] - 1)
            pn_full = np.load(npath / f"{stem}.npy", mmap_mode="r")
            pn = np.asarray(pn_full[vf[:, None], uf[None, :]], np.float32)
            region = np.load(cm.OUT / prior / "nominal" / f"{stem}_region.npy")[vf[:, None], uf[None, :]]
            pok = np.linalg.norm(pn, axis=2) > 0.5
            dot = np.abs(np.sum(nw * pn, axis=2)) / np.maximum(np.linalg.norm(nw, axis=2) * np.linalg.norm(pn, axis=2), 1e-9)
            ang = np.degrees(np.arccos(np.clip(dot, 0, 1)))
            for reg, code in REGION_CODE.items():
                sel = ok & pok & (region == code)
                if sel.any():
                    vals[reg].append(ang[sel])
            sel = ok & pok & ((region == cm.R_ROOF) | (region == cm.R_WALL))
            vals["all"].append(ang[sel])
        out = {}
        for reg, lst in vals.items():
            a = np.concatenate(lst)
            s = cm.two_pass(a)
            s["tau_n_deg"] = (s["m2"] + K_TOL * s["s2"]) if s["n"] else None
            s["tau_n_literal_k_s2_deg"] = (K_TOL * s["s2"]) if s["n"] else None
            out[reg] = s
        normal_stats[f"{prior}|{cond}"] = out
        print("normals", prior, cond, {k: (round(x["m2"], 2), round(x["s2"], 2)) for k, x in out.items() if x["n"]}, flush=True)

# ----------------------------------------------------------------------------- tolerance
tol = {}
for prior in cm.PRIORS:
    tol[prior] = {}
    for cond in cm.CONDS:
        roof = overall_stat(prior, cond, "roof")
        tau_data = K_TOL * roof["s2"] if roof and roof["s2"] is not None else None
        tau_spec = cm.CFG["priors"][prior]["tau_spec_m"]
        tau = max(tau_data, tau_spec) if tau_data is not None else tau_spec
        ns = normal_stats[f"{prior}|{cond}"].get("roof")
        tau_n = ns["tau_n_deg"] if ns and ns["n"] else cm.C["tau_n_default_deg"]
        tol[prior][cond] = {
            "prior": prior, "cond": cond, "tau_region": cm.CFG["tau_region"], "residual_kind": "ray_depth_camZ",
            "tau_data": tau_data, "tau_spec": tau_spec, "tau": tau, "tau_source": "data" if (tau_data is not None and tau_data >= tau_spec) else "spec",
            "tau_data_gt_2x_spec": bool(tau_data is not None and tau_data > 2 * tau_spec),
            "tau_n": tau_n, "tau_n_source": "data" if (ns and ns["n"]) else "default_10deg",
            "tau_n_literal_k_s2": ns["tau_n_literal_k_s2_deg"] if ns and ns["n"] else None,
            "m": roof["m"], "s": roof["s"], "m2": roof["m2"], "s2": roof["s2"], "n": roof["n"], "out_frac": roof["out_frac"],
            "m_v": (overall_stat(prior, cond, "roof", "vertical") or {}).get("m"),
            "m2_v": (overall_stat(prior, cond, "roof", "vertical") or {}).get("m2"),
            "s2_v": (overall_stat(prior, cond, "roof", "vertical") or {}).get("s2"),
            "by_region": {reg: dict(overall_stat(prior, cond, reg) or {}, tau_data=(K_TOL * overall_stat(prior, cond, reg)["s2"]) if overall_stat(prior, cond, reg) and overall_stat(prior, cond, reg)["s2"] is not None else None)
                          for reg in ["roof", "wall", "ground", "all"] if overall_stat(prior, cond, reg)},
            "normal_by_region": normal_stats[f"{prior}|{cond}"],
        }
cm.write_json(cm.OUT / "tolerance.json", tol)

# ----------------------------------------------------------------------------- pass 2: conflicts, faces, points
conf_rows, facts = [], {"nominal_roof_conflict_facts": {}, "bias_file_check": {}, "supplied_vs_recovered_lod2": {}}
face_attr = {}
als_attr = {}
scatter_rows = []
for prior in cm.PRIORS:
    thr = {code: (tol[prior]["nominal"]["by_region"][reg]["m2"], tol[prior]["nominal"]["by_region"][reg]["s2"])
           for reg, code in REGION_CODE.items() if reg in tol[prior]["nominal"]["by_region"] and tol[prior]["nominal"]["by_region"][reg]["n"]}
    for cond in cm.CONDS:
        od = cm.OUT / prior / cond
        P = len(target_polys)
        fh = np.zeros(P * NB_F, np.int64)
        fcount = np.zeros((P, 4), np.int64)  # n_pix, n_mask, n_conf, n_conflict
        edge_facts = {"n_conflict_roof": 0, "n_edge_band": 0, "n_mvs_nearer": 0, "n_mvs_farther": 0, "n_conf_roof": 0}
        if prior == "L":
            N = len(als_local)
            pv = np.full((N, len(views)), np.nan, np.float32)
            pc = np.zeros((N, 4), np.int64)  # n_vis, n_conf, n_conflict, n_res
        per_view_conf = []
        for vi, v in enumerate(views):
            st = view_static(v)
            stem = v["stem"]
            r = np.load(od / f"{stem}_res.npy")
            region = np.load(cm.OUT / prior / "nominal" / f"{stem}_region.npy")
            pd, pok = load_prior_depth(prior, cond, stem)
            both = np.isfinite(r)
            domain = (region == cm.R_ROOF) | (region == cm.R_WALL) | (region == cm.R_GROUND)
            conflict = np.zeros(r.shape, np.uint8)
            for code, (m2, s2) in thr.items():
                sel = both & (region == code)
                conflict[sel] = (np.abs(r[sel] - m2) > SIG * s2).astype(np.uint8)
            np.save(od / f"{stem}_conflict.npy", conflict)
            cm.to_png(od / f"{stem}_conflict.png", cm.conflict_rgb(conflict, st["conf"], domain))
            cm.to_png(vpng / prior / cond / f"{stem}_conflict.png",
                      cm.conflict_rgb(cm.downscale_nearest(conflict, VLONG), cm.downscale_nearest(st["conf"], VLONG), cm.downscale_nearest(domain, VLONG)))
            # readout sidecar
            rr = cm.downscale_nearest(r, RLONG)
            write_sidecar(vdata / f"{stem}_{prior}_{cond}.js", f"{stem}|{prior}|{cond}", {
                "prior": np.nan_to_num(np.clip(cm.downscale_nearest(pd, RLONG) * 100, 0, 65535), nan=0).astype(np.uint16),
                "res": np.where(np.isfinite(rr), np.clip(np.round(rr * 100), -32767, 32767), -32768).astype(np.int16),
                "code": (cm.downscale_nearest(region, RLONG) | (cm.downscale_nearest(conflict, RLONG) << 4)).astype(np.uint8)})
            for reg, code in REGION_CODE.items():
                sel = both & (region == code)
                if sel.any() or not (prior == "M" and reg == "ground"):
                    conf_rows.append([prior, cond, stem, reg, int(sel.sum()), int(conflict[sel].sum()), float(conflict[sel].mean()) if sel.any() else None])
            sel = both & ((region == cm.R_ROOF) | (region == cm.R_WALL))
            conf_rows.append([prior, cond, stem, "all", int(sel.sum()), int(conflict[sel].sum()), float(conflict[sel].mean()) if sel.any() else None])
            # nominal roof conflict facts: edge band and sign
            if cond == "nominal" and cm.R_ROOF in thr:
                m2 = thr[cm.R_ROOF][0]
                cr = (conflict == 1) & (region == cm.R_ROOF)
                edge_facts["n_conflict_roof"] += int(cr.sum())
                edge_facts["n_edge_band"] += int((cr & (st["edge"] <= EDGE_PX)).sum())
                edge_facts["n_mvs_nearer"] += int((cr & (r < m2)).sum())
                edge_facts["n_mvs_farther"] += int((cr & (r > m2)).sum())
                edge_facts["n_conf_roof"] += int((both & (region == cm.R_ROOF)).sum())
            # per-face accumulation (target polygons)
            tl = tp_local[np.maximum(st["poly"], 0)]
            tl[st["poly"] < 0] = -1
            on = tl >= 0
            fcount[:, 0] += np.bincount(tl[on], minlength=P)
            fcount[:, 1] += np.bincount(tl[on & pok], minlength=P)
            fcount[:, 2] += np.bincount(tl[on & both], minlength=P)
            fcount[:, 3] += np.bincount(tl[on & (conflict == 1)], minlength=P)
            sel = on & both
            bins = np.clip(np.floor((r[sel] - F_LO) / F_BIN), 0, NB_F - 1).astype(np.int64)
            fh += np.bincount(tl[sel] * NB_F + bins, minlength=P * NB_F)
            # ALS points (L only): visibility through the L prior depth of this condition
            if prior == "L":
                u, vv_, z = cm.project(v, als_local + np.array([0, 0, cm.CFG["conditions"][cond]]))
                inside = (u >= 0) & (u < v["W"]) & (vv_ >= 0) & (vv_ < v["H"]) & (z > 0)
                ui, vi_ = np.where(inside, u, 0), np.where(inside, vv_, 0)
                dsurf = pd[vi_, ui]
                vis = inside & np.isfinite(dsurf) & (np.abs(dsurf - z) < cm.C["als_point_visibility_tol_m"])
                cvis = vis & (st["conf"][vi_, ui] == 1)
                rvis = cvis & np.isfinite(r[vi_, ui])
                pc[:, 0] += vis
                pc[:, 1] += cvis
                pc[:, 2] += rvis & (conflict[vi_, ui] == 1)
                pc[:, 3] += rvis
                pv[rvis, vi] = r[vi_, ui][rvis]
            print("pass2", prior, cond, stem, "conflict roof frac", float(conflict[both & (region == cm.R_ROOF)].mean()) if (both & (region == cm.R_ROOF)).any() else None, flush=True)
        for reg in ["roof", "wall", "ground", "all"]:
            rows = [row for row in conf_rows if row[:2] == [prior, cond] and row[3] == reg and row[2] != "ALL"]
            n = sum(row[4] for row in rows)
            k = sum(row[5] for row in rows)
            conf_rows.append([prior, cond, "ALL", reg, n, k, float(k / n) if n else None])
        if cond == "nominal":
            e = edge_facts
            facts["nominal_roof_conflict_facts"][prior] = dict(e, edge_band_px=EDGE_PX, edge_band_fraction=(e["n_edge_band"] / e["n_conflict_roof"]) if e["n_conflict_roof"] else None,
                                                             mvs_nearer_fraction=(e["n_mvs_nearer"] / e["n_conflict_roof"]) if e["n_conflict_roof"] else None,
                                                             note="MVS nearer than prior = structure above the LoD2/ALS roof (dormer, chimney, plant); MVS farther = prior above the observed surface")
        # faces
        cum = np.cumsum(fh.reshape(P, NB_F), axis=1)
        med = np.full(P, np.nan)
        for i in range(P):
            tot = cum[i, -1]
            if tot:
                j = int(np.searchsorted(cum[i], tot / 2.0))
                med[i] = F_LO + (j + 0.5) * F_BIN
        rows = []
        for i, p in enumerate(target_polys):
            n_pix, n_mask, n_conf, n_cfl = [int(x) for x in fcount[i]]
            rows.append({"poly_index": p["poly_index"], "polygon_gml_id": p["polygon_gml_id"], "citygml_type": p["citygml_type"], "region": p["region"],
                         "area_m2": p["area_m2"], "n_pixels": n_pix, "n_prior_mask": n_mask, "n_conf": n_conf, "n_conflict": n_cfl,
                         "conf_frac": (n_conf / n_mask) if n_mask else None, "conflict_frac": (n_cfl / n_conf) if n_conf else None,
                         "res_median": None if np.isnan(med[i]) else float(med[i])})
        face_attr[f"{prior}|{cond}"] = rows
        with (cm.OUT / f"lod2_faces_{prior}_{cond}.csv").open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        # PLY with per-face scalar properties
        tf = PZ["faces"][PZ["target_face_mask"]]
        tpt = PZ["poly_of_tri"][PZ["target_face_mask"]]
        used = np.unique(tf)
        remap = {int(o): i for i, o in enumerate(used)}
        V = PZ["vertices_local"][used]
        with (cm.OUT / f"lod2_faces_{prior}_{cond}.ply").open("w") as f:
            f.write("ply\nformat ascii 1.0\ncomment JointBuildGS stage1 face attributes; local scene frame\n")
            f.write(f"element vertex {len(V)}\nproperty float x\nproperty float y\nproperty float z\n")
            f.write(f"element face {len(tf)}\nproperty list uchar int vertex_indices\nproperty int poly_index\nproperty uchar region_code\nproperty float conf_frac\nproperty float conflict_frac\nproperty float res_median\nend_header\n")
            for x in V:
                f.write(f"{x[0]:.4f} {x[1]:.4f} {x[2]:.4f}\n")
            for tri, pi in zip(tf, tpt):
                row = rows[int(tp_local[pi])]
                f.write(f"3 {remap[int(tri[0])]} {remap[int(tri[1])]} {remap[int(tri[2])]} {pi} {int(poly_region_code[pi])} "
                        f"{-1 if row['conf_frac'] is None else row['conf_frac']:.4f} {-1 if row['conflict_frac'] is None else row['conflict_frac']:.4f} "
                        f"{float('nan') if row['res_median'] is None else row['res_median']:.4f}\n")
        # ALS points
        if prior == "L":
            n_vis, n_conf, n_cfl, n_res = pc.T
            with np.errstate(invalid="ignore"):
                pconf = np.where(n_vis > 0, n_conf / np.maximum(n_vis, 1), np.nan)
                pcfl = np.where(n_res > 0, n_cfl / np.maximum(n_res, 1), np.nan)
                pres = np.nanmedian(pv, axis=1) if pv.shape[1] else np.full(N, np.nan)
            als_attr[cond] = {"conf": pconf, "res": pres, "conflict": pcfl, "n_vis": n_vis}
            with (cm.OUT / f"als_points_{cond}.ply").open("w") as f:
                f.write("ply\nformat ascii 1.0\ncomment Existing ALS class 2/6 crop; local scene frame; z includes the condition bias\n")
                f.write(f"element vertex {N}\nproperty float x\nproperty float y\nproperty float z\nproperty uchar classification\nproperty float conf\nproperty float res\nproperty float conflict\nproperty int n_vis\nend_header\n")
                zb = cm.CFG["conditions"][cond]
                for i in range(N):
                    f.write(f"{als_local[i,0]:.3f} {als_local[i,1]:.3f} {als_local[i,2]+zb:.3f} {int(als_cls[i])} {np.nan_to_num(pconf[i], nan=-1):.4f} {pres[i]:.4f} {np.nan_to_num(pcfl[i], nan=-1):.4f} {int(n_vis[i])}\n")

# ----------------------------------------------------------------------------- checks
facts["supplied_vs_recovered_lod2"] = {}
facts["bias_file_check"] = {}
for v in views:
    stem = v["stem"]
    st = view_static(v)
    region = st["region"]
    dz = st["vfac"]
    s_d, s_ok = load_prior_depth("M", "nominal", stem)
    r_d = np.load(cm.INP / "prior_render/M_nominal_recovered/lod2_prior/raw_depth" / f"{stem}.npy")
    r_ok = np.isfinite(r_d)
    b_d = np.load(cm.INP / "prior_render/M_biased/lod2_prior/raw_depth" / f"{stem}.npy")
    b_ok = np.isfinite(b_d)
    roof = region == cm.R_ROOF
    sel = roof & s_ok & r_ok
    facts["supplied_vs_recovered_lod2"][stem] = {"roof_px": int(sel.sum()), "median_vertical_supplied_minus_recovered_m": float(np.median(((s_d - r_d) * dz)[sel])) if sel.any() else None,
                                                 "hit_mask_disagreement_frac_target_roof": float((s_ok != r_ok)[roof].mean())}
    sel = roof & b_ok & r_ok
    facts["bias_file_check"][stem] = {"roof_px": int(sel.sum()), "median_vertical_biased_minus_nominal_recovered_m": float(np.median(((b_d - r_d) * dz)[sel])) if sel.any() else None,
                                      "p05_p95": np.quantile(((b_d - r_d) * dz)[sel], [0.05, 0.95]).tolist() if sel.any() else None}
allv = [x["median_vertical_biased_minus_nominal_recovered_m"] for x in facts["bias_file_check"].values() if x["median_vertical_biased_minus_nominal_recovered_m"] is not None]
facts["bias_file_check"]["summary"] = {"median_over_views_m": float(np.median(allv)) if allv else None, "expected_m": -cm.C["bias_m"],
                                       "note": "prior raised by +1.0 m => prior depth decreases; vertical(biased-nominal) ~ -1.0 m on roofs"}
allv = [x["median_vertical_supplied_minus_recovered_m"] for x in facts["supplied_vs_recovered_lod2"].values() if x["median_vertical_supplied_minus_recovered_m"] is not None]
facts["vertical_conversion"] = {"definition": "roof vertical residual = r * |n.d| / |n_z| (n = LoD2 polygon unit normal of the pixel, d = unnormalised world ray R^T(x,y,1)); equals r*|d_z| for horizontal faces",
                                "horizontal_plane_formula_m2_v": {f"{p}|{c}": overall_vals[(p, c)]["roof_vh"]["m2"] for p in cm.PRIORS for c in cm.CONDS},
                                "note": "r*|d_z| alone underestimates the vertical gap on pitched roofs seen at grazing angles; recorded for comparison only"}
facts["supplied_vs_recovered_lod2"]["summary"] = {"median_over_views_m": float(np.median(allv)) if allv else None,
                                                  "note": "M nominal uses the author-supplied LoD2Depth arrays; M biased is rendered from the recovered CityGML (+1.0 m). This is the mesh-source difference that accompanies the bias."}


def cf(prior, cond, reg):
    for row in conf_rows:
        if row[:4] == [prior, cond, "ALL", reg]:
            return row[6]
    return None


def rel(a, b):
    if a is None or b is None:
        return None
    d = max(abs(a), abs(b))
    return abs(a - b) / d if d > 0 else 0.0


W = cm.C["bias_check_window_m"]
checks = {"per_prior": {}, "cross_prior": {}}
for prior in cm.PRIORS:
    tn, tb = tol[prior]["nominal"], tol[prior]["biased"]
    reg_ok = bool(tn["m2"] is not None and abs(tn["m2"]) < tn["s2"])
    bias_ok = bool(tb["m2_v"] is not None and W[0] <= tb["m2_v"] <= W[1])
    dmv = (tb["m2_v"] - tn["m2_v"]) if (tb["m2_v"] is not None and tn["m2_v"] is not None) else None
    checks["per_prior"][prior] = {
        "R1_registration_ok": reg_ok, "R1_values": {"m2_roof": tn["m2"], "s2_roof": tn["s2"], "m_roof_first_pass": tn["m"], "s_roof_first_pass": tn["s"]},
        "registration_warning": (not reg_ok), "registration_warning_text": None if reg_ok else f"정상 조건 지붕 |m2|={abs(tn['m2']):.3f} m ≥ s2={tn['s2']:.3f} m: 계통 편차",
        "R2_bias_verified": bias_ok, "R2_values": {"m2_v_biased": tb["m2_v"], "m2_v_nominal": tn["m2_v"], "delta_m2_v": dmv, "window": W,
                                                     "deviation_from_1m": None if tb["m2_v"] is None else abs(tb["m2_v"] - cm.C["bias_m"])},
        "R3_tolerance_source": tn["tau_source"], "R3_tau_data_gt_2x_spec": tn["tau_data_gt_2x_spec"],
        "R3_note": "MVS 품질 점검 기록 필요(τ_data > 2τ_spec); τ는 τ_data 유지" if tn["tau_data_gt_2x_spec"] else None,
        "R4_roof_coverage": overall_cov(prior, "nominal", "roof"), "R4_undetermined_upper": None if overall_cov(prior, "nominal", "roof") is None else 1 - overall_cov(prior, "nominal", "roof"),
        "R6_conflict_sane": bool(cf(prior, "biased", "roof") is not None and cf(prior, "nominal", "roof") is not None and cf(prior, "biased", "roof") > cf(prior, "nominal", "roof")),
        "R6_values": {"roof_conflict_biased": cf(prior, "biased", "roof"), "roof_conflict_nominal": cf(prior, "nominal", "roof")},
        "wall_conflict_similar": bool(cf(prior, "biased", "wall") is not None and cf(prior, "nominal", "wall") is not None and abs(cf(prior, "biased", "wall") - cf(prior, "nominal", "wall")) <= 0.10),
        "wall_conflict_values": {"nominal": cf(prior, "nominal", "wall"), "biased": cf(prior, "biased", "wall"), "rule": "abs difference <= 0.10"},
    }
tL, tM = tol["L"]["nominal"], tol["M"]["nominal"]
rel_tau = rel(tL["tau"], tM["tau"])
rel_cf = {c: rel(cf("L", c, "roof"), cf("M", c, "roof")) for c in cm.CONDS}
run_both = bool((rel_tau is not None and rel_tau >= cm.C["run_both_priors_rel_diff"]) or any(x is not None and x >= cm.C["run_both_priors_rel_diff"] for x in rel_cf.values()))
covL, covM = overall_cov("L", "nominal", "roof"), overall_cov("M", "nominal", "roof")
checks["cross_prior"] = {
    "R5_run_both_priors": run_both, "R5_values": {"tau_L": tL["tau"], "tau_M": tM["tau"], "rel_diff_tau": rel_tau, "rel_diff_roof_conflict": rel_cf},
    "s_L_lt_s_M": bool(tL["s2"] is not None and tM["s2"] is not None and tL["s2"] < tM["s2"]), "s_values": {"s2_L": tL["s2"], "s2_M": tM["s2"]},
    "coverage_within_5pp": bool(covL is not None and covM is not None and abs(covL - covM) <= 0.05), "coverage_values": {"roof_L": covL, "roof_M": covM,
                                                                                                                          "wall_L": overall_cov("L", "nominal", "wall"), "wall_M": overall_cov("M", "nominal", "wall")},
}
checks["all_green"] = bool(all(checks["per_prior"][p]["R1_registration_ok"] and checks["per_prior"][p]["R2_bias_verified"] and checks["per_prior"][p]["R6_conflict_sane"] for p in cm.PRIORS))
cm.write_json(cm.OUT / "checks.json", checks)

# ----------------------------------------------------------------------------- tables
with (cm.OUT / "stats.csv").open("w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["prior", "cond", "view", "region", "residual_kind", "n", "m", "s", "m2", "s2", "out_frac"])
    w.writerows(stats_rows)
with (cm.OUT / "coverage.csv").open("w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["prior", "cond", "view", "region", "n_prior_mask", "n_conf", "coverage"])
    w.writerows(cov_rows)
with (cm.OUT / "conflict.csv").open("w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["prior", "cond", "view", "region", "n_conf_mask", "n_conflict", "conflict_frac"])
    w.writerows(conf_rows)
diag = json.loads((cm.ART / cm.CFG["scene"]["diagnostic_nominal_summary_relative"]).read_text())
diagN = {"roof_median_m": diag["surfaces"]["roof"]["median_m"], "roof_nmad_m": diag["surfaces"]["roof"]["nmad_m"],
         "wall_median_m": diag["surfaces"]["wall"]["median_m"], "wall_nmad_m": diag["surfaces"]["wall"]["nmad_m"],
         "definition": "GeoGS N output vs GT UAV LiDAR signed nearest-distance error (diagnostic GEOGS-ROOF-BIAS-20260921 table B); not the same quantity as MVS-prior residuals"}
cmp_rows = []


def add(metric, fn, diag_val=None):
    cmp_rows.append([metric] + [fn(p, c) for p in cm.PRIORS for c in cm.CONDS] + [diag_val])


for key in ["tau_data", "tau_spec", "tau", "tau_source", "tau_n", "m", "s", "m2", "s2", "out_frac", "n", "m_v", "m2_v", "s2_v"]:
    add(f"{key}(roof)" if key not in ("tau_spec", "tau_source") else key, lambda p, c, k=key: tol[p][c][k])
for reg in ["roof", "wall", "ground", "all"]:
    add(f"coverage_{reg}", lambda p, c, r=reg: overall_cov(p, c, r))
    add(f"conflict_frac_{reg}", lambda p, c, r=reg: cf(p, c, r))
    if reg != "all":
        add(f"m2_{reg}(ray)", lambda p, c, r=reg: (overall_stat(p, c, r) or {}).get("m2"))
        add(f"s2_{reg}(ray)", lambda p, c, r=reg: (overall_stat(p, c, r) or {}).get("s2"))
for q in ["p05", "p25", "p50", "p75", "p95"]:
    add(f"roof_residual_{q}(ray)", lambda p, c, q=q: hist[f"{p}|{c}|roof|ray_depth_camZ"]["quantiles"][q])
    add(f"roof_residual_{q}(vertical)", lambda p, c, q=q: hist[f"{p}|{c}|roof|vertical"]["quantiles"][q])
cmp_rows.append(["diagN_roof_signed_error_median_vs_GT", None, None, None, None, diagN["roof_median_m"]])
cmp_rows.append(["diagN_roof_signed_error_nmad_vs_GT", None, None, None, None, diagN["roof_nmad_m"]])
cmp_rows.append(["diagN_wall_signed_error_median_vs_GT", None, None, None, None, diagN["wall_median_m"]])
cmp_rows.append(["diagN_wall_signed_error_nmad_vs_GT", None, None, None, None, diagN["wall_nmad_m"]])
with (cm.OUT / "compare_L_vs_M.csv").open("w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["metric", "L_nominal", "L_biased", "M_nominal", "M_biased", "diag_N_GeoGS_vs_GT"])
    w.writerows(cmp_rows)

# ----------------------------------------------------------------------------- stage-2 configs
stage2 = {}
for prior in cm.PRIORS:
    tn, tb = tol[prior]["nominal"], tol[prior]["biased"]
    pp = checks["per_prior"][prior]
    cfg = {"prior": prior, "conf_dir": "conf", "conf_files": "{view}_conf.npy (uint8 0/1, 4082x5644), shared by all priors/conditions",
           "tau": tn["tau"], "tau_spec": tn["tau_spec"], "tau_data": tn["tau_data"], "tau_n": tn["tau_n"],
           "cap": None if tn["tau"] is None else 3 * tn["tau"], "seed_distance": tn["tau"], "conf_threshold_E": 0.5, "lr_scale_low": 0.01,
           "opacity_floor": 0.5, "E_refresh_iters": 500,
           "expected": {"roof_coverage": pp["R4_roof_coverage"], "undetermined_upper": pp["R4_undetermined_upper"],
                        "roof_conflict_frac_nominal": cf(prior, "nominal", "roof"), "roof_conflict_frac_biased": cf(prior, "biased", "roof"),
                        "m_v_biased": tb["m2_v"]},
           "flags": {"registration_ok": pp["R1_registration_ok"], "bias_verified": pp["R2_bias_verified"], "tolerance_source": pp["R3_tolerance_source"],
                     "run_both_priors": checks["cross_prior"]["R5_run_both_priors"], "conflict_sane": pp["R6_conflict_sane"]},
           "provenance": {"task_id": cm.CFG["task_id"], "tau_region": "roof", "tau_definition": "max(k*s2_roof_nominal, tau_spec), k=2.5, two-pass NMAD of MVS-prior camera-Z residual",
                          "tau_n_definition": cm.CFG["tau_n_definition"], "residual_kind": "ray_depth_camZ (camera-Z metres, same as LoD2Depth and COLMAP)",
                          "m_v_definition": "roof vertical residual = r * |n.d| / |n_z| with n = LoD2 polygon normal, d = unnormalised world ray R^T(x,y,1) (= r*|d_z| for horizontal faces); two-pass median",
                          "null_reason": None, "scientific_verdict": None}}
    nulls = [k for k in ["tau", "tau_n"] if cfg[k] is None]
    if nulls:
        cfg["provenance"]["null_reason"] = f"{nulls}: no roof residual samples in this experiment"
    stage2[prior] = cfg
    cm.write_json(cm.OUT / f"stage2_config_{prior}.json", cfg)

# ----------------------------------------------------------------------------- results bundle
als_stride = cm.C["als_viewer_point_stride"]
idx = np.arange(0, len(als_local), als_stride)
viewer_als = {}
for cond, a in als_attr.items():
    viewer_als[cond] = {"x": np.round(als_local[idx, 0], 2).tolist(), "y": np.round(als_local[idx, 1], 2).tolist(),
                        "cls": als_cls[idx].astype(int).tolist(),
                        "conf": [None if not np.isfinite(x) else round(float(x), 3) for x in a["conf"][idx]],
                        "res": [None if not np.isfinite(x) else round(float(x), 3) for x in a["res"][idx]],
                        "conflict": [None if not np.isfinite(x) else round(float(x), 3) for x in a["conflict"][idx]]}
results = {"task_id": cm.CFG["task_id"], "scientific_verdict": None, "generated_at": cm.now_iso(), "config": cm.CFG,
           "views": viewer_views, "tolerance": tol, "checks": checks, "facts": facts, "diagN": diagN,
           "stats_rows": stats_rows, "coverage_rows": cov_rows, "conflict_rows": conf_rows, "compare_rows": cmp_rows,
           "hist": hist, "hist_meta": {"range": HR, "bin": HB, "nbins": NHB},
           "faces": {"target": [{k: p[k] for k in ["poly_index", "polygon_gml_id", "citygml_type", "region", "area_m2", "ring_local_xy", "z_local_mean", "normal"]} for p in target_polys],
                     "context": [{k: p[k] for k in ["poly_index", "building_id", "region", "ring_local_xy"]} for p in context_polys if p["region"] == "roof"],
                     "attributes": face_attr, "bbox_local": PJ["target_bbox_local"], "crop_local_xy": PJ["als_crop_local_xy"]},
           "als_points": viewer_als, "stage2": stage2,
           "provenance": {k: json.loads((cm.PROV / f"{k}.json").read_text()) for k in ["geometry", "mvs_resampling", "faceid_render"] if (cm.PROV / f"{k}.json").exists()}}
cm.write_json(cm.OUT / "results.json", results)
print("checks", json.dumps(checks, indent=1, default=str)[:4000])
rc.write()
