"""Independent reproduction for the stage-1 inspection (PHD-STAGE1-INSPECTION-v1).

Rules: no import of the stage-1 agent modules; every number is recomputed from the raw arrays
(COLMAP geometric depth .bin, LoD2Depth prior depth .npy, delivered face labels) with the
inspection prompt's definitions, and in parallel with the agent's definitions for the 1e-6 match.
Nothing is regenerated (no MVS, no masks); thresholds and pixel sets are not tuned.
Runs in jointbuildgs:dev:  python reproduce.py [--views N]
"""
import argparse
import csv
import json
import math
import struct
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

ART = Path("/artifacts/JointBuildGS")
TASK = ART / "phase-payloads/phd/stage1_conf_tol_conflict_v1/PHD-STAGE1-CONF-TOL-CONFLICT-v1"
OUT = Path("/insp")
DENSE = ART / "phase-payloads/p0-audit/data/work/mvs/colmap_dense"
SCENE = ART / "phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/native_example/scene"
SPARSE_TXT = ART / "phase-payloads/phd/geogs_roof_bias_v1/GEOGS-ROOF-BIAS-20260921/conditions/B+1.0/scene/sparse_txt"
SPEC = {"L": 0.12, "M": 1.0}
K_TOL, SIG, NMAD = 2.5, 3.0, 1.4826
R_ROOF, R_WALL, R_GROUND = 1, 2, 3
ap = argparse.ArgumentParser()
ap.add_argument("--views", type=int, default=0, help="limit number of views (smoke test)")
ap.add_argument("--figview", default="DJI_20241217101305_0005_D")
args = ap.parse_args()
(OUT / "repro").mkdir(parents=True, exist_ok=True)
t_start = time.time()


# ------------------------------------------------------------------ own readers (no agent code)
def qvec2R(q):
    w, x, y, z = q
    return np.array([[1 - 2 * y * y - 2 * z * z, 2 * x * y - 2 * z * w, 2 * x * z + 2 * y * w],
                     [2 * x * y + 2 * z * w, 1 - 2 * x * x - 2 * z * z, 2 * y * z - 2 * x * w],
                     [2 * x * z - 2 * y * w, 2 * y * z + 2 * x * w, 1 - 2 * x * x - 2 * y * y]])


def read_cams_txt(p):
    cams = {}
    for l in Path(p).read_text().splitlines():
        if l.strip() and not l.startswith("#"):
            t = l.split()
            cams[int(t[0])] = dict(model=t[1], W=int(t[2]), H=int(t[3]), p=[float(x) for x in t[4:]])
    return cams


def read_imgs_txt(p):
    imgs = {}
    for l in Path(p).read_text().splitlines():
        t = l.split()
        if len(t) >= 10 and not l.startswith("#"):
            try:
                imgs[t[9]] = dict(q=[float(x) for x in t[1:5]], t=np.array([float(x) for x in t[5:8]]), cam=int(t[8]))
            except ValueError:
                pass
    return imgs


def read_cams_bin(p):
    with open(p, "rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        out = {}
        for _ in range(n):
            cid, model, w, h = struct.unpack("<iiQQ", f.read(24))
            npar = {0: 3, 1: 4, 2: 4, 3: 5, 4: 8, 5: 8, 6: 12, 7: 5, 8: 4, 9: 5, 10: 12}[model]
            out[cid] = dict(model=model, W=w, H=h, p=struct.unpack("<" + "d" * npar, f.read(8 * npar)))
    return out


def read_colmap_bin(p):
    with open(p, "rb") as f:
        head = b""
        while head.count(b"&") < 3:
            head += f.read(1)
        w, h, c = [int(x) for x in head.decode().split("&")[:3]]
        a = np.fromfile(f, np.float32)
    return np.transpose(a.reshape((w, h, c), order="F"), (1, 0, 2)).squeeze()


def median_nmad(x):
    x = np.asarray(x, dtype=np.float64)
    m = float(np.median(x))
    return m, float(NMAD * np.median(np.abs(x - m)))


def two_pass(x):
    # statistics in float64 (the agent's convention); float32 medians differ at the 1e-6 level
    x = np.asarray(x, dtype=np.float64)
    x = x[np.isfinite(x)]
    if x.size == 0:
        return dict(n=0, m=None, s=None, n2=0, m2=None, s2=None, out_frac=None)
    m, s = median_nmad(x)
    keep = np.abs(x - m) <= SIG * s if s > 0 else np.ones(x.size, bool)
    m2, s2 = median_nmad(x[keep])
    return dict(n=int(x.size), m=m, s=s, n2=int(keep.sum()), m2=m2, s2=s2, out_frac=float(1 - keep.mean()))


cams = read_cams_txt(SPARSE_TXT / "cameras.txt")
imgs = read_imgs_txt(SPARSE_TXT / "images.txt")
dense_cam = read_cams_bin(DENSE / "sparse/cameras.bin")[1]
stems = sorted(Path(n).stem for n in (SCENE / "images").iterdir() if n.suffix.lower() == ".jpg")
if args.views:
    stems = stems[: args.views]
PJ = json.loads((TASK / "inputs/lod2_polygons.json").read_text())
n_poly = PJ["n_polygons_total"]
poly_normal = np.zeros((n_poly, 3), np.float32)
target_polys = {}
for p in PJ["polygons"]:
    poly_normal[p["poly_index"]] = p["normal"]
    if p["is_target"]:
        target_polys[p["poly_index"]] = p["region"]
supplied = SCENE / "lod2_prior/raw_depth"


def prior_path(prior, cond):
    if prior == "M" and cond == "nominal":
        return supplied
    if prior == "M" and cond == "nominal_recovered":
        return TASK / "inputs/prior_render/M_nominal_recovered/lod2_prior/raw_depth"
    return TASK / f"inputs/prior_render/{prior}_{cond}/lod2_prior/raw_depth"


def load_prior(prior, cond, stem):
    d = np.load(prior_path(prior, cond) / f"{stem}.npy").astype(np.float32)
    ok = np.isfinite(d) & (d > 0) & (d < 1e6)
    return np.where(ok, d, np.nan).astype(np.float32), ok


# ------------------------------------------------------------------ per-view loop
POOLS = {"roof": (R_ROOF,), "bldg": (R_ROOF, R_WALL), "wall": (R_WALL,), "ground": (R_GROUND,)}
samples = defaultdict(list)  # key (prior,cond,pool,axis) -> list of arrays
per_view = []  # rows for reproduction_stats (per view)
identity = []
coverage_rows = []
injection = []
fig_arrays = {}
face_any_yes = defaultdict(bool)
face_yes_counts = defaultdict(lambda: [0, 0])  # poly -> [n_yes, n_prior_valid]
for vi, stem in enumerate(stems):
    t0 = time.time()
    im = imgs[stem + ".JPG"]
    cam = cams[im["cam"]]
    fx, fy, cx, cy = cam["p"]
    W, H = cam["W"], cam["H"]
    R = qvec2R(im["q"])
    # ---- observation confidence map A and MVS depth, recomputed from the raw COLMAP arrays
    d = read_colmap_bin(DENSE / "stereo/depth_maps" / f"{stem}.JPG.geometric.bin")
    h, w = d.shape
    valid = (d > 0) & np.isfinite(d)
    fx0, fy0, cx0, cy0 = dense_cam["p"]
    fxn, fyn, cxn, cyn = fx0 * w / dense_cam["W"], fy0 * h / dense_cam["H"], cx0 * w / dense_cam["W"], cy0 * h / dense_cam["H"]
    xn = (np.arange(W) + 0.5 - cx) / fx
    yn = (np.arange(H) + 0.5 - cy) / fy
    gu = fxn * xn + cxn - 0.5
    gv = fyn * yn + cyn - 0.5
    iu = np.clip(np.rint(gu).astype(int), 0, w - 1)
    iv = np.clip(np.rint(gv).astype(int), 0, h - 1)
    A = valid[iv[:, None], iu[None, :]].astype(np.uint8)
    u0 = np.clip(np.floor(gu).astype(int), 0, w - 1)
    v0 = np.clip(np.floor(gv).astype(int), 0, h - 1)
    u1 = np.clip(u0 + 1, 0, w - 1)
    v1 = np.clip(v0 + 1, 0, h - 1)
    au = np.clip(gu - u0, 0, 1).astype(np.float32)
    av = np.clip(gv - v0, 0, 1).astype(np.float32)
    dv = np.where(valid, d, 0).astype(np.float32)
    vf = valid.astype(np.float32)
    num = np.zeros((H, W), np.float32)
    den = np.zeros((H, W), np.float32)
    for (vy, ux, wy, wx) in ((v0, u0, 1 - av, 1 - au), (v0, u1, 1 - av, au), (v1, u0, av, 1 - au), (v1, u1, av, au)):
        wgt = wy[:, None] * wx[None, :]
        num += wgt * dv[vy[:, None], ux[None, :]]
        den += wgt * vf[vy[:, None], ux[None, :]]
    mvs = np.where((A == 1) & (den > 0), num / np.maximum(den, 1e-12), np.nan).astype(np.float32)
    A_agent = np.load(TASK / "out/conf" / f"{stem}_conf.npy")
    mvs_agent = np.load(TASK / "inputs/mvs_full" / f"{stem}_depth.npy")
    both_fin = np.isfinite(mvs) & np.isfinite(mvs_agent)
    identity.append(dict(view=stem, A_shape=list(A.shape), image_wh=[W, H], A_mismatch_px=int((A != A_agent).sum()),
                         A_yes_fraction=float(A.mean()), native_valid_fraction=float(valid.mean()),
                         mvs_full_max_abs_diff=float(np.abs(mvs[both_fin] - mvs_agent[both_fin]).max()) if both_fin.any() else None,
                         mvs_full_nan_mask_mismatch=int((np.isfinite(mvs) != np.isfinite(mvs_agent)).sum())))
    # ---- delivered labels (used as given; not regenerated)
    poly = np.load(TASK / "inputs/faceid" / f"{stem}.npy")
    regions = {p: np.load(TASK / f"out/{p}/nominal/{stem}_region.npy") for p in "LM"}
    # ---- vertical factor for roof pixels: |n.d| / |n_z| with d = R^T (x, y, 1) (own implementation)
    dxw = (R[0, 0] * xn[None, :] + R[1, 0] * yn[:, None] + R[2, 0]).astype(np.float32)
    dyw = (R[0, 1] * xn[None, :] + R[1, 1] * yn[:, None] + R[2, 1]).astype(np.float32)
    dzw = (R[0, 2] * xn[None, :] + R[1, 2] * yn[:, None] + R[2, 2]).astype(np.float32)
    nrm = poly_normal[np.maximum(poly, 0)]
    nd = np.abs(nrm[..., 0] * dxw + nrm[..., 1] * dyw + nrm[..., 2] * dzw)
    nz = np.abs(nrm[..., 2])
    vfac = np.where((poly >= 0) & (nz > 1e-6), nd / np.maximum(nz, 1e-6), np.abs(dzw)).astype(np.float32)
    del nrm, nd, nz, dxw, dyw
    obliquity = float(np.median(vfac[regions["L"] == R_ROOF])) if (regions["L"] == R_ROOF).any() else None
    # ---- face capability (any-view yes) on target polygons, from delivered face ids
    for pi in np.unique(poly[poly >= 0]):
        if int(pi) in target_polys:
            sel = poly == pi
            face_yes_counts[int(pi)][0] += int((A[sel] == 1).sum())
            face_yes_counts[int(pi)][1] += int(sel.sum())
    # ---- residuals per prior / condition
    r_store = {}
    for prior in "LM":
        region = regions[prior]
        for cond in (["nominal", "biased", "nominal_recovered"] if prior == "M" else ["nominal", "biased"]):
            pd, pok = load_prior(prior, cond, stem)
            yes = (A == 1) & pok
            r = np.where(yes, mvs - pd, np.nan).astype(np.float32)
            r_store[(prior, cond)] = (r, pok)
            if cond == "nominal_recovered":
                continue
            rv = np.where(yes & (region == R_ROOF), r * vfac, np.nan).astype(np.float32)
            for pool, codes in POOLS.items():
                if prior == "M" and pool == "ground":
                    continue
                sel = yes & np.isin(region, codes)
                vals = r[sel]
                samples[(prior, cond, pool, "camz")].append(vals)
                st = two_pass(vals)
                per_view.append(dict(prior=prior, cond=cond, pool=pool, axis="camz", view=stem, **st))
                n_mask = int((pok & np.isin(region, codes)).sum())
                coverage_rows.append(dict(prior=prior, cond=cond, view=stem, pool=pool, n_prior_mask=n_mask, n_yes=int(sel.sum()),
                                          coverage=(int(sel.sum()) / n_mask) if n_mask else None))
                if pool == "roof":
                    vv = rv[sel]
                    samples[(prior, cond, pool, "vert")].append(vv)
                    st = two_pass(vv)
                    per_view.append(dict(prior=prior, cond=cond, pool=pool, axis="vert", view=stem, **st))
            if stem == args.figview:
                fig_arrays[f"{prior}_{cond}_r"] = r.astype(np.float16)
                fig_arrays[f"{prior}_{cond}_rv"] = rv.astype(np.float16)
                fig_arrays[f"{prior}_{cond}_priorok"] = pok
        # ---- §5 injection check (nominal vs biased prior arrays)
        pairs = [("nominal", "biased")] + ([("nominal_recovered", "biased")] if prior == "M" else [])
        for a, b in pairs:
            ra, oka = r_store[(prior, a)]
            rb, okb = r_store[(prior, b)]
            pa, _ = load_prior(prior, a, stem)
            pb, _ = load_prior(prior, b, stem)
            bothok = oka & okb
            differ = bothok & (np.abs(pa - pb) > 1e-4)
            roof = (region == R_ROOF) & np.isfinite(ra) & np.isfinite(rb)
            shift_c = (rb - ra)[roof]
            shift_v = ((rb - ra) * vfac)[roof]
            if a == "nominal":
                # aligned samples for the effective-injection analysis: biased residual and the prior's own
                # camera-Z shift on roof yes-pixels of the biased scene (both priors valid)
                sel_e = (region == R_ROOF) & np.isfinite(rb) & bothok
                samples[(prior, "biased_aligned", "roof", "camz")].append(rb[sel_e])
                samples[(prior, "shift", "roof", "camz")].append((pa - pb)[sel_e])
                samples[(prior, "shift", "roof", "vert")].append(((pa - pb) * vfac)[sel_e])
            injection.append(dict(prior=prior, pair=f"{a}->{b}", view=stem, n_both_valid=int(bothok.sum()), n_differ=int(differ.sum()),
                                  differ_fraction=float(differ.sum() / max(bothok.sum(), 1)),
                                  prior_valid_mismatch_px=int((oka != okb).sum()),
                                  roof_n=int(roof.sum()), roof_median_shift_camz=float(np.median(shift_c)) if roof.any() else None,
                                  roof_median_shift_vertical=float(np.median(shift_v)) if roof.any() else None,
                                  roof_p05_p95_shift_camz=[float(x) for x in np.quantile(shift_c, [0.05, 0.95])] if roof.any() else None,
                                  roof_median_vertical_factor=float(np.median(vfac[roof])) if roof.any() else None))
    if stem == args.figview:
        fig_arrays["A"] = A
        fig_arrays["region_L"] = regions["L"]
        fig_arrays["region_M"] = regions["M"]
        fig_arrays["vfac"] = vfac.astype(np.float32)
        fig_arrays["poly"] = poly
    print(f"[{vi+1}/{len(stems)}] {stem} A mismatch {identity[-1]['A_mismatch_px']} px, mvs max diff {identity[-1]['mvs_full_max_abs_diff']:.2e}, "
          f"roof obliquity factor median {obliquity}", f"{time.time()-t0:.1f}s", flush=True)

# ------------------------------------------------------------------ overall statistics and widths
overall = {}
for key, lst in list(samples.items()):
    vals = np.concatenate(lst) if lst else np.zeros(0, np.float32)
    samples[key] = vals
    if key[1] in ("shift", "biased_aligned"):
        continue
    overall[key] = two_pass(vals)
    prior = key[0]
    st = overall[key]
    st["tau_data"] = K_TOL * st["s2"] if st["s2"] is not None else None
    st["tau_spec"] = SPEC[prior]
    st["tau"] = max(st["tau_data"], SPEC[prior]) if st["tau_data"] is not None else SPEC[prior]
    st["tau_source"] = "data" if (st["tau_data"] is not None and st["tau_data"] >= SPEC[prior]) else "spec"
    st["quantiles"] = {f"p{int(q*100):02d}": float(v) for q, v in zip([0.05, 0.25, 0.5, 0.75, 0.95], np.quantile(vals, [0.05, 0.25, 0.5, 0.75, 0.95]))} if vals.size else {}


def out_fractions(prior, cond, ref_pool, axis):
    """Roof yes-pixels of `cond` scene outside the width defined from the nominal scene of `ref_pool`/axis."""
    ref = overall[(prior, "nominal", ref_pool, axis)]
    x = samples[(prior, cond, "roof", axis)]
    x = x[np.isfinite(x)]
    if x.size == 0 or ref["m2"] is None:
        return None
    dev = np.abs(x - ref["m2"])
    return dict(n_yes=int(x.size), ref_pool=ref_pool, axis=axis, m_ref=ref["m2"], s_ref=ref["s2"], tau_ref=ref["tau"],
                frac_out_tau=float((dev > ref["tau"]).mean()), frac_out_3s=float((dev > SIG * ref["s2"]).mean()),
                frac_out_4tau=float((dev > 4 * ref["tau"]).mean()), frac_out_tau_data=float((dev > ref["tau_data"]).mean()))


checks = {"width_out_fractions": {}, "scene_consistency": {}, "center": {}, "pixel_pool": {}, "size": {}}
for prior in "LM":
    for cond in ["nominal", "biased"]:
        for ref_pool in ["roof", "bldg"]:
            for axis in (["camz", "vert"] if ref_pool == "roof" else ["camz"]):
                checks["width_out_fractions"][f"{prior}|{cond}|ref={ref_pool}|{axis}"] = out_fractions(prior, cond, ref_pool, axis)
    for pool in ["roof", "bldg"]:
        for axis in (["camz", "vert"] if pool == "roof" else ["camz"]):
            n_, b_ = overall[(prior, "nominal", pool, axis)], overall[(prior, "biased", pool, axis)]
            checks["scene_consistency"][f"{prior}|{pool}|{axis}"] = dict(
                tau_nominal=n_["tau"], tau_biased=b_["tau"], rel_diff_tau=abs(n_["tau"] - b_["tau"]) / max(n_["tau"], b_["tau"]),
                tau_data_nominal=n_["tau_data"], tau_data_biased=b_["tau_data"],
                rel_diff_tau_data=abs(n_["tau_data"] - b_["tau_data"]) / max(n_["tau_data"], b_["tau_data"]) if n_["tau_data"] and b_["tau_data"] else None,
                within_10pct=bool(abs(n_["tau"] - b_["tau"]) / max(n_["tau"], b_["tau"]) <= 0.10),
                injected_fraction_of_pool="1.0 (entire prior raised; no partial injection region exists)")
            checks["center"][f"{prior}|{pool}|{axis}"] = dict(m2=n_["m2"], s2=n_["s2"], abs_m_lt_s=bool(abs(n_["m2"]) < n_["s2"]),
                                                            m_over_tau=abs(n_["m2"]) / n_["tau"] if n_["tau"] else None)
    for pool in ["roof", "bldg"]:
        n_ = overall[(prior, "nominal", pool, "camz")]
        checks["size"][f"{prior}|{pool}|camz"] = dict(s2=n_["s2"], two_five_s2=n_["tau_data"], spec=SPEC[prior], spec_is_floor=bool(n_["tau_data"] < SPEC[prior]))
    # non-building pixels must be zero in the width pool: count ground/other/none pixels inside the pool by construction
    checks["pixel_pool"][prior] = dict(pool_definition="A==1 & prior valid & region in pool; region labels delivered per view",
                                       n_ground_in_bldg_pool=0, n_none_in_bldg_pool=0, note="pool is selected by region code, so non-building codes cannot enter")

# ---- capability (§3) per view coverage and face-level any-view yes
cap = {}
for prior in "LM":
    for pool in ["roof", "wall"]:
        vals = [r["coverage"] for r in coverage_rows if r["prior"] == prior and r["cond"] == "nominal" and r["pool"] == pool and r["coverage"] is not None]
        cap[f"{prior}|{pool}"] = dict(per_view_median=float(np.median(vals)), per_view_min=float(np.min(vals)), per_view_max=float(np.max(vals)),
                                     pooled=float(sum(r["n_yes"] for r in coverage_rows if r["prior"] == prior and r["cond"] == "nominal" and r["pool"] == pool)
                                                  / max(sum(r["n_prior_mask"] for r in coverage_rows if r["prior"] == prior and r["cond"] == "nominal" and r["pool"] == pool), 1)))
faces = {reg: [pi for pi, r in target_polys.items() if r == reg] for reg in ["roof", "wall"]}
cap["faces_any_view_yes"] = {reg: dict(n_faces=len(faces[reg]), n_faces_seen=sum(1 for pi in faces[reg] if face_yes_counts[pi][1] > 0),
                                       n_faces_any_yes=sum(1 for pi in faces[reg] if face_yes_counts[pi][0] > 0),
                                       fraction_of_seen=(sum(1 for pi in faces[reg] if face_yes_counts[pi][0] > 0) / max(sum(1 for pi in faces[reg] if face_yes_counts[pi][1] > 0), 1)),
                                       fraction_of_all=(sum(1 for pi in faces[reg] if face_yes_counts[pi][0] > 0) / max(len(faces[reg]), 1)))
                             for reg in ["roof", "wall"]}
cap["hold_upper_bound"] = {p: dict(pooled_pixels=1 - cap[f"{p}|roof"]["pooled"], per_view_median=1 - cap[f"{p}|roof"]["per_view_median"],
                                   per_view_worst=1 - cap[f"{p}|roof"]["per_view_min"], faces=1 - cap["faces_any_view_yes"]["roof"]["fraction_of_all"]) for p in "LM"}

# ---- sensitivity / right-scene (§3) using the prompt's width (ref pool bldg, camz) and the roof pool, both axes
sens = {}
for prior in "LM":
    for ref_pool, axis in [("bldg", "camz"), ("roof", "camz"), ("roof", "vert")]:
        wb = checks["width_out_fractions"][f"{prior}|biased|ref={ref_pool}|{axis}"]
        wn = checks["width_out_fractions"][f"{prior}|nominal|ref={ref_pool}|{axis}"]
        sens[f"{prior}|ref={ref_pool}|{axis}"] = dict(sensitivity_tau=wb["frac_out_tau"], sensitivity_3s=wb["frac_out_3s"], sensitivity_pass_0p9=bool(wb["frac_out_tau"] >= 0.9),
                                                       nominal_out_tau=wn["frac_out_tau"], nominal_out_3s=wn["frac_out_3s"], nominal_out_4tau=wn["frac_out_4tau"],
                                                       tau_ref=wb["tau_ref"], one_m_over_tau=1.0 / wb["tau_ref"])
# effective injection: roof yes-pixels of the biased scene whose prior shift itself exceeds the width
eff = {}
for prior in "LM":
    rb_ = samples[(prior, "biased_aligned", "roof", "camz")]
    sh_ = samples[(prior, "shift", "roof", "camz")]
    shv = samples[(prior, "shift", "roof", "vert")]
    for ref_pool in ["bldg", "roof"]:
        ref = overall[(prior, "nominal", ref_pool, "camz")]
        out = np.abs(rb_ - ref["m2"]) > ref["tau"]
        strong = sh_ > ref["tau"]
        eff[f"{prior}|ref={ref_pool}|camz"] = dict(
            n=int(rb_.size), tau_ref=ref["tau"], frac_shift_le_tau=float((~strong).mean()),
            shift_quantiles_camz={f"p{int(q*100):02d}": float(v) for q, v in zip([0.01, 0.05, 0.10, 0.25, 0.5], np.quantile(sh_, [0.01, 0.05, 0.10, 0.25, 0.5]))},
            shift_quantiles_vert={f"p{int(q*100):02d}": float(v) for q, v in zip([0.01, 0.05, 0.10, 0.25, 0.5], np.quantile(shv, [0.01, 0.05, 0.10, 0.25, 0.5]))},
            sensitivity_all=float(out.mean()), sensitivity_on_effective=float(out[strong].mean()) if strong.any() else None,
            attainable_upper_bound=float(strong.mean()),
            note="pixels with shift <= tau cannot leave the width for any A (eave band: the raised wall enters the ray; steep faces facing the camera)")
checks["effective_injection"] = eff
checks["sensitivity"] = sens
checks["capability"] = cap
checks["limitations"] = {
    "pixel_pool": "pool membership is by prior-face label; occluders in front of faces (trees, vehicles) that project onto roof/wall labels remain in the pool; the count of non-building codes is zero by construction",
    "A_identity": "the bilinear/nearest resampling path mirrors the agent's documented method; independent evidence is the re-derivation of the depth-grid intrinsics from the dense cameras.bin and A_yes ~ native valid fraction",
    "ground_rows": "L biased 'ground' rows deviate from the agent's stats/coverage tables because the agent's first pass labelled ground with the biased TIN coverage while its second pass and the delivered label files use the nominal coverage; the reproduction uses the delivered (nominal) labels for both scenes",
    "capability_denominator": "coverage denominators are prior-valid AND region (stage-1 order definition); the prompt's 'roof pixels' differs by <=2e4 px (<1e-4)",
}
checks["identity"] = identity
checks["injection"] = injection

# ------------------------------------------------------------------ reproduction match vs agent tables
agent_stats = list(csv.DictReader((TASK / "out/stats.csv").open()))
agent_cov = list(csv.DictReader((TASK / "out/coverage.csv").open()))
agent_cfl = list(csv.DictReader((TASK / "out/conflict.csv").open()))
agent_tol = json.loads((TASK / "out/tolerance.json").read_text())
match = []


def add_match(name, a, r, exact=False):
    a = None if a in (None, "") else float(a)
    r = None if r is None else float(r)
    if a is None or r is None:
        match.append(dict(metric=name, agent=a, repro=r, abs_diff=None, rel_diff=None, ok=(a is None and r is None)))
        return
    diff = abs(a - r)
    rel = diff / max(abs(a), abs(r), 1e-12)
    ok = (diff == 0) if exact else (rel <= 1e-6 or diff <= 1e-9)
    match.append(dict(metric=name, agent=a, repro=r, abs_diff=diff, rel_diff=rel, ok=bool(ok)))


AGENT_POOL = {"roof": "roof", "wall": "wall", "ground": "ground", "bldg": "all"}
AGENT_AXIS = {"camz": "ray_depth_camZ", "vert": "vertical"}
for (prior, cond, pool, axis), st in overall.items():
    row = next((r for r in agent_stats if r["prior"] == prior and r["cond"] == cond and r["view"] == "ALL" and r["region"] == AGENT_POOL[pool] and r["residual_kind"] == AGENT_AXIS[axis]), None)
    if row is None:
        continue
    for k, ak in [("n", "n"), ("m", "m"), ("s", "s"), ("m2", "m2"), ("s2", "s2"), ("out_frac", "out_frac")]:
        add_match(f"stats|{prior}|{cond}|{AGENT_POOL[pool]}|{AGENT_AXIS[axis]}|{k}", row[ak], st[k], exact=(k == "n"))
if not args.views:
    for prior in "LM":
        for cond in ["nominal", "biased"]:
            t = agent_tol[prior][cond]
            st = overall[(prior, cond, "roof", "camz")]
            for k in ["tau_data", "tau", "m2", "s2"]:
                add_match(f"tolerance|{prior}|{cond}|{k}", t[k], st[k])
            add_match(f"tolerance|{prior}|{cond}|m2_v", t["m2_v"], overall[(prior, cond, "roof", "vert")]["m2"])
            for pool, ap_ in [("roof", "roof"), ("wall", "wall"), ("bldg", "all"), ("ground", "ground")]:
                if prior == "M" and pool == "ground":
                    continue
                row = next((r for r in agent_cov if r["prior"] == prior and r["cond"] == cond and r["view"] == "ALL" and r["region"] == ap_), None)
                if row:
                    n_mask = sum(r["n_prior_mask"] for r in coverage_rows if r["prior"] == prior and r["cond"] == cond and r["pool"] == pool)
                    n_yes = sum(r["n_yes"] for r in coverage_rows if r["prior"] == prior and r["cond"] == cond and r["pool"] == pool)
                    add_match(f"coverage|{prior}|{cond}|{ap_}|n_prior_mask", row["n_prior_mask"], n_mask, exact=True)
                    add_match(f"coverage|{prior}|{cond}|{ap_}|n_conf", row["n_conf"], n_yes, exact=True)
                    add_match(f"coverage|{prior}|{cond}|{ap_}|coverage", row["coverage"], n_yes / n_mask if n_mask else None)
            # agent conflict fraction on roof = out_3s with roof-pool nominal reference
            row = next((r for r in agent_cfl if r["prior"] == prior and r["cond"] == cond and r["view"] == "ALL" and r["region"] == "roof"), None)
            if row:
                add_match(f"conflict|{prior}|{cond}|roof|conflict_frac(3s2_roof_nominal)", row["conflict_frac"], checks["width_out_fractions"][f"{prior}|{cond}|ref=roof|camz"]["frac_out_3s"])
# per-view match (roof, camz + vert)
for pv in per_view:
    if pv["pool"] not in ("roof", "bldg"):
        continue
    row = next((r for r in agent_stats if r["prior"] == pv["prior"] and r["cond"] == pv["cond"] and r["view"] == pv["view"] and r["region"] == AGENT_POOL[pv["pool"]] and r["residual_kind"] == AGENT_AXIS[pv["axis"]]), None)
    if row:
        for k in ["n", "m2", "s2"]:
            add_match(f"stats|{pv['prior']}|{pv['cond']}|{AGENT_POOL[pv['pool']]}|{AGENT_AXIS[pv['axis']]}|{pv['view']}|{k}", row[k], pv[k], exact=(k == "n"))

# ------------------------------------------------------------------ write outputs
with (OUT / "repro/reproduction_stats.csv").open("w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["prior", "cond", "pool", "axis", "view", "n", "m", "s", "n2", "m2", "s2", "out_frac", "tau_data", "tau_spec", "tau", "tau_source"])
    for (prior, cond, pool, axis), st in sorted(overall.items()):
        w.writerow([prior, cond, pool, axis, "ALL", st["n"], st["m"], st["s"], st["n2"], st["m2"], st["s2"], st["out_frac"], st["tau_data"], st["tau_spec"], st["tau"], st["tau_source"]])
    for pv in per_view:
        w.writerow([pv["prior"], pv["cond"], pv["pool"], pv["axis"], pv["view"], pv["n"], pv["m"], pv["s"], pv["n2"], pv["m2"], pv["s2"], pv["out_frac"], "", "", "", ""])
with (OUT / "repro/reproduction_match.csv").open("w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["metric", "agent", "repro", "abs_diff", "rel_diff", "ok"])
    w.writeheader()
    w.writerows(match)
with (OUT / "repro/coverage_per_view.csv").open("w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(coverage_rows[0].keys()))
    w.writeheader()
    w.writerows(coverage_rows)
hist = {}
for (prior, cond, pool, axis), vals in samples.items():
    if pool in ("roof", "bldg", "wall") and cond not in ("shift", "biased_aligned"):
        h, edges = np.histogram(vals[np.isfinite(vals)], bins=300, range=(-3, 3))
        hist[f"{prior}|{cond}|{pool}|{axis}"] = dict(counts=h.tolist(), under=int((vals < -3).sum()), over=int((vals > 3).sum()))
checks["overall"] = {f"{k[0]}|{k[1]}|{k[2]}|{k[3]}": v for k, v in overall.items()}
checks["hist"] = hist
checks["hist_edges"] = np.linspace(-3, 3, 301).tolist()
checks["match_summary"] = dict(n=len(match), n_ok=sum(1 for m in match if m["ok"]), failures=[m for m in match if not m["ok"]][:50])
checks["runtime_s"] = time.time() - t_start
checks["views"] = stems
checks["spec"] = SPEC
checks["constants"] = dict(k=K_TOL, sigma=SIG, nmad=NMAD)
(OUT / "repro/checks.json").write_text(json.dumps(checks, indent=1, default=lambda o: None if isinstance(o, float) and not np.isfinite(o) else (o.item() if hasattr(o, "item") else str(o))))
np.savez_compressed(OUT / "repro/fig_arrays.npz", **fig_arrays)
print("match", checks["match_summary"]["n_ok"], "/", checks["match_summary"]["n"], "runtime", round(checks["runtime_s"]), "s")
print(json.dumps({k: v for k, v in checks["sensitivity"].items()}, indent=0)[:1500])
