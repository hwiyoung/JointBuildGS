"""PHD-CH6-SUPPORT-v1 task 3 (background images): true-ortho colour rasters of the four experiment regions from the ULS nadir
points (top point per cell, 0.1 m, in the rotated u-v frame of the boxes) and of the campus overview (0.5 m, resampled from
the real-change survey grid: ULS colour, MVS colour darkened where ULS is absent) (jointbuildgs:dev, CPU).

  python t3_ortho.py

Writes /out/t3/ortho_<box>.npz (rgb uint8 [H, W, 3], u0, v0, res; row 0 = v0) and /out/t3/ortho_overview.npz.
scientific_verdict: null."""
import json
from pathlib import Path

import numpy as np
import scipy.ndimage as ndi

from ch6_common import BOXDEF, OUT, RNGDEF, log, uv_to_xy, xy_to_uv
from common import SHIFT

O = OUT / "t3"; O.mkdir(parents=True, exist_ok=True)
ULS = Path("/art/phase-payloads/p0-audit/data/raw/tum2twin/TUM_Downtown_ULS_20241217_nadir.laz")
SURVEY = Path("/art/phase-payloads/phd/main_design_realchange_survey_v1/PHD-MAIN-DESIGN-REALCHANGE-SURVEY-v1/s1")
REG = {"B0_b10": ("B0", 10.0), "B173nb_b10": ("B173nb", 10.0), "B173_b0": ("B173", 0.0), "R1rep_b10": ("R1rep", 10.0)}
MARGIN, RES = 4.0, 0.1


def rect(bid, band):
    b = BOXDEF[bid]
    return b["eval_u"][0] - band - MARGIN, b["eval_u"][1] + band + MARGIN, b["eval_v"][0] - band - MARGIN, b["eval_v"][1] + band + MARGIN


def fill(rgb, ok, maxd=4):
    d, (iy, ix) = ndi.distance_transform_edt(~ok, return_indices=True)
    out = rgb[iy, ix]
    out[d > maxd] = 255
    return out


def main():
    import laspy
    rects = {k: rect(*v) for k, v in REG.items()}
    xy_lo, xy_hi = np.full(2, np.inf), np.full(2, -np.inf)
    for (u0, u1, v0, v1) in rects.values():
        c = uv_to_xy(np.array([[u0, v0], [u1, v0], [u1, v1], [u0, v1]]))
        xy_lo = np.minimum(xy_lo, c.min(0)); xy_hi = np.maximum(xy_hi, c.max(0))
    acc = {k: [] for k in rects}
    n_all = 0
    with laspy.open(str(ULS)) as f:
        for pts in f.chunk_iterator(15_000_000):
            x = np.asarray(pts.x) - SHIFT[0]; y = np.asarray(pts.y) - SHIFT[1]
            m = (x >= xy_lo[0]) & (x <= xy_hi[0]) & (y >= xy_lo[1]) & (y <= xy_hi[1])
            n_all += len(x)
            if not m.any():
                continue
            uv = xy_to_uv(np.stack([x[m], y[m]], 1))
            z = np.asarray(pts.z)[m] - SHIFT[2]
            col = np.stack([np.asarray(pts.red)[m], np.asarray(pts.green)[m], np.asarray(pts.blue)[m]], 1)
            for k, (u0, u1, v0, v1) in rects.items():
                mm = (uv[:, 0] >= u0) & (uv[:, 0] < u1) & (uv[:, 1] >= v0) & (uv[:, 1] < v1)
                if mm.any():
                    acc[k].append((uv[mm].astype(np.float32), z[mm].astype(np.float32), col[mm]))
    log("ULS points read", n_all)
    for k, (u0, u1, v0, v1) in rects.items():
        uv = np.concatenate([a[0] for a in acc[k]]); z = np.concatenate([a[1] for a in acc[k]]); col = np.concatenate([a[2] for a in acc[k]])
        scale = 256.0 if col.max() > 255 else 1.0
        W, H = int(np.ceil((u1 - u0) / RES)), int(np.ceil((v1 - v0) / RES))
        iu = np.clip(((uv[:, 0] - u0) / RES).astype(np.int64), 0, W - 1); iv = np.clip(((uv[:, 1] - v0) / RES).astype(np.int64), 0, H - 1)
        cell = iv * W + iu
        o = np.lexsort((-z, cell))                 # per cell the highest point first
        cs = cell[o]; first = np.r_[True, cs[1:] != cs[:-1]]
        top = o[first]
        rgb = np.full((H * W, 3), 255, np.uint8); ok = np.zeros(H * W, bool)
        rgb[cell[top]] = np.clip(col[top] / scale, 0, 255).astype(np.uint8); ok[cell[top]] = True
        rgb = fill(rgb.reshape(H, W, 3), ok.reshape(H, W))
        np.savez_compressed(O / f"ortho_{k}.npz", rgb=rgb, u0=u0, v0=v0, res=RES, points=len(z), filled_share=float(1 - ok.mean()))
        log("ortho", k, rgb.shape, "points", len(z), "empty cells filled", round(1 - ok.mean(), 4))
    # overview: resample the survey grid into u-v at 0.5 m
    D = np.load(SURVEY / "rasters_als_mvs_uls.npz")
    g = json.loads((SURVEY / "receipt_s1_als_mvs_uls.json").read_text())["grid"]
    nu = D["uls_n"]; nm = D["mvs_n"]
    rgb_u = np.stack([D["uls_rsum"], D["uls_gsum"], D["uls_bsum"]], -1) / np.maximum(nu, 1)[..., None]
    rgb_m = np.stack([D["mvs_rsum"], D["mvs_gsum"], D["mvs_bsum"]], -1) / np.maximum(nm, 1)[..., None]
    if rgb_u.max() > 255:
        rgb_u = rgb_u / 256.0
    if rgb_m.max() > 255:
        rgb_m = rgb_m / 256.0
    base = np.where((nu > 0)[..., None], rgb_u, np.where((nm > 0)[..., None], 0.6 * rgb_m + 0.4 * 255, 255)).astype(np.float32)
    polys = [xy_to_uv(np.asarray(RNGDEF[r]["polygon_local"], np.float64)) for r in ("R1", "R2", "R3", "R4", "R5", "B0", "SW", "R3E")]
    allp = np.concatenate(polys)
    u0, u1 = allp[:, 0].min() - 25, allp[:, 0].max() + 25; v0, v1 = allp[:, 1].min() - 25, allp[:, 1].max() + 25
    res = 0.5
    W, H = int(np.ceil((u1 - u0) / res)), int(np.ceil((v1 - v0) / res))
    U, V = np.meshgrid(u0 + (np.arange(W) + 0.5) * res, v0 + (np.arange(H) + 0.5) * res)
    xy = uv_to_xy(np.stack([U.ravel(), V.ravel()], 1))
    E = xy[:, 0] + SHIFT[0]; N = xy[:, 1] + SHIFT[1]
    ix = np.floor((E - g["e_min"]) / g["res_m"]).astype(np.int64); iy = np.floor((N - g["n_min"]) / g["res_m"]).astype(np.int64)
    inside = (ix >= 0) & (ix < g["nx"]) & (iy >= 0) & (iy < g["ny"])
    out = np.full((H * W, 3), 255, np.float32)
    out[inside] = base[iy[inside], ix[inside]]
    np.savez_compressed(O / "ortho_overview.npz", rgb=np.clip(out, 0, 255).astype(np.uint8).reshape(H, W, 3), u0=u0, v0=v0, res=res)
    log("overview", (H, W))


if __name__ == "__main__":
    main()
