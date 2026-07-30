#!/usr/bin/env python3
"""A1 LS estimate of the orthometric->ellipsoidal geoid term zeta.

Uses ALS class-6 roof points as model-independent 3D evidence. For each
building/view, the ALS roof silhouette projected with the current config zeta is
translated over a wide search window to maximize orientation-aware image-edge
energy. The measured 2D residuals are then fit to projection sensitivities:

  residual_uv ~= d(uv)/dZ * delta_zeta
  residual_uv ~= d(uv)/dZ * delta_zeta + d(uv)/dE * dE + d(uv)/dN * dN

No reconstruction, retraining, or pass/fail judgment.
"""
from __future__ import annotations

import csv
import json
import math
import platform
import subprocess
import sys
from pathlib import Path

import laspy
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

sys.path.insert(0, "/workspace/JointBuildGS/phases/p2-gsjso/scripts")
from evidence_cards_v2 import (  # noqa: E402
    ALS_TILES,
    DATA,
    GEOJSON,
    IMAGE_DIR,
    REPO,
    distort,
    gml_building,
    nadir_of,
    parse_cam_model,
    parse_cameras,
    to_cam,
)
from projection_datum import describe_projection_config, load_projection_config, projection_geoid_m  # noqa: E402


RUN_ID = "20260702_A1_zeta_ls"
RUN_DIR = REPO / "phases" / "p2-gsjso" / "runs" / RUN_ID
FIG_DIR = REPO / "docs/figs/projection_zeta_ls"
OUT_CSV = REPO / "docs/experiments/input-and-alignment/projection_zeta_ls/tables/projection_zeta_ls.csv"
OUT_MD = REPO / "docs/experiments/input-and-alignment/projection_zeta_ls/reports/projection_zeta_ls.md"
RESULT_JSON = REPO / "results/tum_transfer/mob/overseg_lever/projection_zeta_ls.json"
CONFIG = REPO / "configs/projection_datum.json"

BUILDINGS = ["4906972", "4907520", "4959327", "4906985", "4959460", "4907184", "4906966", "4906982"]
ANGLE_TARGETS = [
    ("near", 8.0, 0.0, 20.0),
    ("mid", 32.0, 20.0, 45.0),
    ("strong", 55.0, 45.0, 89.0),
]
SEARCH = 300
STEP = 4
MIN_ALS = 25


def git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    except Exception as exc:  # pragma: no cover
        return f"unavailable: {exc}"


def footprints() -> dict[str, np.ndarray]:
    out = {}
    for f in json.load(open(GEOJSON))["features"]:
        bid = f["properties"]["building_id"].replace("DEBY_LOD2_", "")
        g = f["geometry"]
        ring = np.array(
            g["coordinates"][0] if g["type"] == "Polygon" else max((p[0] for p in g["coordinates"]), key=len),
            float,
        )
        if bid not in out or len(ring) > len(out[bid]):
            out[bid] = ring
    return out


def als_roof(ring: np.ndarray, ground_z: float) -> np.ndarray:
    bb = [ring[:, 0].min() - 1, ring[:, 1].min() - 1, ring[:, 0].max() + 1, ring[:, 1].max() + 1]
    chunks = []
    for tile in ALS_TILES:
        with laspy.open(tile) as fh:
            h = fh.header
            if h.x_max < bb[0] or h.x_min > bb[2] or h.y_max < bb[1] or h.y_min > bb[3]:
                continue
        las = laspy.read(tile)
        cl = np.asarray(las.classification)
        x = np.asarray(las.x)
        y = np.asarray(las.y)
        z = np.asarray(las.z)
        m = (cl == 6) & (x >= bb[0]) & (x <= bb[2]) & (y >= bb[1]) & (y <= bb[3]) & (z > ground_z + 2.0)
        if m.any():
            chunks.append(np.column_stack([x[m], y[m], z[m]]))
    return np.vstack(chunks) if chunks else np.zeros((0, 3))


def project_points(points: np.ndarray, cam, params: np.ndarray, sr: dict, geoid_m: float):
    cc = to_cam(points, cam, sr, geoid_m=geoid_m)
    front = cc[:, 2] > 1.0
    uv = np.full((len(points), 2), np.nan)
    if front.any():
        uv[front] = distort(cc[front], params)
    return uv, front


def visible_fraction(points: np.ndarray, cam, params: np.ndarray, sr: dict, W: int, H: int, geoid_m: float) -> float:
    uv, front = project_points(points, cam, params, sr, geoid_m)
    inb = front & (uv[:, 0] >= 0) & (uv[:, 0] < W) & (uv[:, 1] >= 0) & (uv[:, 1] < H)
    return float(inb.mean())


def select_views(
    roof: list[np.ndarray],
    ring: np.ndarray,
    als: np.ndarray,
    cams,
    params: np.ndarray,
    sr: dict,
    W: int,
    H: int,
    zeta0: float,
):
    allv = np.vstack(roof)
    ctr = np.array([ring[:, 0].mean(), ring[:, 1].mean(), np.median(allv[:, 2])])
    candidates = []
    for cam in cams:
        uv, front = project_points(als, cam, params, sr, zeta0)
        inb = front & (uv[:, 0] >= 0) & (uv[:, 0] < W) & (uv[:, 1] >= 0) & (uv[:, 1] < H)
        if int(inb.sum()) < MIN_ALS:
            continue
        nad = nadir_of(cam, ctr, geoid_m=zeta0)
        cx, cy = params[2], params[3]
        uvi = uv[inb]
        rad = float(np.nanmax(np.sqrt(((uvi[:, 0] - cx) / (0.5 * W)) ** 2 + ((uvi[:, 1] - cy) / (0.5 * H)) ** 2)))
        candidates.append((nad, rad, int(inb.sum()), cam))
    picks = []
    used = set()
    for label, target, lo, hi in ANGLE_TARGETS:
        pool = [c for c in candidates if lo <= c[0] < hi and c[3].name not in used]
        if not pool and label == "strong":
            pool = [c for c in candidates if c[0] >= 40.0 and c[3].name not in used]
        if not pool:
            continue
        pick = min(pool, key=lambda t: abs(t[0] - target) + 3.0 * max(0.0, t[1] - 1.0) - 0.002 * t[2])
        used.add(pick[3].name)
        picks.append((label, pick[0], pick[1], pick[3]))
    return picks, ctr


def silhouette_boundary(uv: np.ndarray, W: int, H: int, cell: int = 2):
    m = np.zeros((H, W), bool)
    ok = np.isfinite(uv[:, 0]) & np.isfinite(uv[:, 1])
    u = np.round(uv[ok, 0]).astype(int)
    v = np.round(uv[ok, 1]).astype(int)
    ok2 = (u >= 0) & (u < W) & (v >= 0) & (v < H)
    u = u[ok2]
    v = v[ok2]
    if len(u) < MIN_ALS:
        return None, None
    for du in range(-cell, cell + 1):
        for dv in range(-cell, cell + 1):
            m[np.clip(v + dv, 0, H - 1), np.clip(u + du, 0, W - 1)] = True
    pts = np.argwhere(m)
    if len(pts) < 30:
        return None, None
    center = pts.mean(0)
    ang = np.arctan2(pts[:, 0] - center[0], pts[:, 1] - center[1])
    rad = np.hypot(pts[:, 0] - center[0], pts[:, 1] - center[1])
    nb = 180
    bins = (((ang + np.pi) / (2 * np.pi)) * nb).astype(int) % nb
    boundary = []
    for bi in range(nb):
        sel = np.where(bins == bi)[0]
        if len(sel):
            boundary.append(pts[sel[np.argmax(rad[sel])]])
    if len(boundary) < 24:
        return None, None
    B = np.array(boundary, float)[:, ::-1]
    tan = np.gradient(B, axis=0)
    tan = tan / np.maximum(np.linalg.norm(tan, axis=1, keepdims=True), 1e-9)
    return B, tan


def orient_align(pts: np.ndarray, tan: np.ndarray, gx: np.ndarray, gy: np.ndarray, x0: int, y0: int):
    normal = np.column_stack([-tan[:, 1], tan[:, 0]])
    Hc, Wc = gx.shape
    px = pts[:, 0] - x0
    py = pts[:, 1] - y0
    records = []
    best = (0, 0, -1.0)
    for dy in range(-SEARCH, SEARCH + 1, STEP):
        vy = np.round(py + dy).astype(int)
        for dx in range(-SEARCH, SEARCH + 1, STEP):
            vx = np.round(px + dx).astype(int)
            ok = (vx >= 0) & (vx < Wc) & (vy >= 0) & (vy < Hc)
            if ok.sum() < max(12, len(pts) * 0.45):
                continue
            score = np.abs(normal[ok, 0] * gx[vy[ok], vx[ok]] + normal[ok, 1] * gy[vy[ok], vx[ok]])
            s = float(score.mean())
            records.append((dx, dy, s, int(ok.sum())))
            if s > best[2]:
                best = (dx, dy, s)
    if not records:
        return None
    arr = np.array(records, float)
    scores = arr[:, 2]
    std = float(scores.std() + 1e-9)
    weights = np.exp(np.clip((scores - best[2]) / std, -40, 0))
    weights = weights / weights.sum()
    mx = float(np.sum(weights * arr[:, 0]))
    my = float(np.sum(weights * arr[:, 1]))
    varx = float(np.sum(weights * (arr[:, 0] - mx) ** 2))
    vary = float(np.sum(weights * (arr[:, 1] - my) ** 2))
    sigma = max(float(STEP), math.sqrt(0.5 * (varx + vary)))
    return {
        "dx": float(best[0]),
        "dy": float(best[1]),
        "peak": float(best[2]),
        "z": float((best[2] - scores.mean()) / std),
        "sigma_px": sigma,
        "n_boundary": int(np.median(arr[:, 3])),
        "score_std": std,
    }


def sensitivities(point: np.ndarray, cam, params: np.ndarray, sr: dict, zeta0: float):
    p = point.astype(float)
    uv0, fr0 = project_points(p[None], cam, params, sr, zeta0)
    if not fr0[0] or not np.isfinite(uv0[0]).all():
        return None
    uvz, _ = project_points(p[None], cam, params, sr, zeta0 + 1.0)
    uve, _ = project_points((p + np.array([1.0, 0.0, 0.0]))[None], cam, params, sr, zeta0)
    uvn, _ = project_points((p + np.array([0.0, 1.0, 0.0]))[None], cam, params, sr, zeta0)
    return {
        "uv0": uv0[0],
        "z": uvz[0] - uv0[0],
        "E": uve[0] - uv0[0],
        "N": uvn[0] - uv0[0],
    }


def offset_m(dx: float, dy: float, sens: dict[str, np.ndarray]) -> float:
    J = np.column_stack([sens["E"], sens["N"]])
    if abs(np.linalg.det(J)) < 1e-9:
        return float("nan")
    w = np.linalg.inv(J) @ np.array([dx, dy], float)
    return float(np.hypot(w[0], w[1]))


def measure_one(bid: str, label: str, nad: float, rad: float, cam, ctr: np.ndarray, als: np.ndarray, params, sr, W, H, zeta0: float):
    uv, front = project_points(als, cam, params, sr, zeta0)
    inb = front & (uv[:, 0] >= 0) & (uv[:, 0] < W) & (uv[:, 1] >= 0) & (uv[:, 1] < H)
    if inb.sum() < MIN_ALS:
        return None
    pts, tan = silhouette_boundary(uv[inb], W, H)
    if pts is None:
        return None
    pad = SEARCH + 80
    x0 = int(max(0, pts[:, 0].min() - pad))
    y0 = int(max(0, pts[:, 1].min() - pad))
    x1 = int(min(W, pts[:, 0].max() + pad))
    y1 = int(min(H, pts[:, 1].max() + pad))
    if x1 - x0 < 32 or y1 - y0 < 32:
        return None
    img = np.asarray(Image.open(IMAGE_DIR / cam.name).convert("RGB"))[y0:y1, x0:x1]
    gray = img.astype(np.float32) @ np.array([0.299, 0.587, 0.114], float)
    gy, gx = np.gradient(gray)
    al = orient_align(pts, tan, gx, gy, x0, y0)
    sens = sensitivities(ctr, cam, params, sr, zeta0)
    if al is None or sens is None:
        return None
    off_m = offset_m(al["dx"], al["dy"], sens)
    return {
        "building_id": f"DEBY_LOD2_{bid}",
        "angle_bin": label,
        "view_nadir_deg": round(float(nad), 3),
        "tan_nadir": round(float(math.tan(math.radians(nad))), 6),
        "frame_r": round(float(rad), 3),
        "view": cam.name,
        "n_als_inframe": int(inb.sum()),
        "align_dx_px": round(al["dx"], 3),
        "align_dy_px": round(al["dy"], 3),
        "align_sigma_px": round(al["sigma_px"], 3),
        "align_conf_z": round(al["z"], 3),
        "align_n_boundary": al["n_boundary"],
        "offset_m_at_zeta0": round(off_m, 4) if np.isfinite(off_m) else "",
        "sens_z_u_px_per_m": float(sens["z"][0]),
        "sens_z_v_px_per_m": float(sens["z"][1]),
        "sens_E_u_px_per_m": float(sens["E"][0]),
        "sens_E_v_px_per_m": float(sens["E"][1]),
        "sens_N_u_px_per_m": float(sens["N"][0]),
        "sens_N_v_px_per_m": float(sens["N"][1]),
    }


def weighted_lstsq(rows: list[dict[str, object]], cols: list[str]):
    A = []
    b = []
    w = []
    for r in rows:
        sigma = max(float(r["align_sigma_px"]), STEP)
        row_u = []
        row_v = []
        for col in cols:
            if col == "zeta":
                row_u.append(float(r["sens_z_u_px_per_m"]))
                row_v.append(float(r["sens_z_v_px_per_m"]))
            elif col == "E":
                row_u.append(float(r["sens_E_u_px_per_m"]))
                row_v.append(float(r["sens_E_v_px_per_m"]))
            elif col == "N":
                row_u.append(float(r["sens_N_u_px_per_m"]))
                row_v.append(float(r["sens_N_v_px_per_m"]))
        A.extend([row_u, row_v])
        b.extend([float(r["align_dx_px"]), float(r["align_dy_px"])])
        w.extend([1.0 / sigma, 1.0 / sigma])
    A = np.asarray(A, float)
    b = np.asarray(b, float)
    w = np.asarray(w, float)
    Aw = A * w[:, None]
    bw = b * w
    x, *_ = np.linalg.lstsq(Aw, bw, rcond=None)
    pred = A @ x
    resid = b - pred
    dof = max(1, len(b) - len(cols))
    sigma2 = float(np.sum((resid * w) ** 2) / dof)
    cov = sigma2 * np.linalg.inv(Aw.T @ Aw)
    se = np.sqrt(np.diag(cov))
    rms_px = float(np.sqrt(np.mean(resid**2)))
    return {"cols": cols, "x": x, "se": se, "cov": cov, "resid": resid, "pred": pred, "rms_px": rms_px}


def add_residuals(rows: list[dict[str, object]], fit: dict[str, object]) -> None:
    resid = fit["resid"]
    for i, r in enumerate(rows):
        ru = float(resid[2 * i])
        rv = float(resid[2 * i + 1])
        sens_z = np.array([float(r["sens_z_u_px_per_m"]), float(r["sens_z_v_px_per_m"])])
        denom = float(sens_z @ sens_z)
        signed_z_m = float((np.array([ru, rv]) @ sens_z) / denom) if denom > 1e-12 else float("nan")
        r["resid_u_px_zonly"] = round(ru, 3)
        r["resid_v_px_zonly"] = round(rv, 3)
        r["resid_px_zonly"] = round(float(math.hypot(ru, rv)), 3)
        r["resid_signed_z_m_zonly"] = round(signed_z_m, 4) if np.isfinite(signed_z_m) else ""


def regression_residual_vs_tan(rows: list[dict[str, object]]):
    x = np.array([float(r["tan_nadir"]) for r in rows if r["resid_signed_z_m_zonly"] != ""], float)
    y = np.array([float(r["resid_signed_z_m_zonly"]) for r in rows if r["resid_signed_z_m_zonly"] != ""], float)
    if len(x) < 2:
        return None
    A = np.column_stack([x, np.ones_like(x)])
    coef, *_ = np.linalg.lstsq(A, y, rcond=None)
    pred = A @ coef
    ss_res = float(np.sum((y - pred) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 1e-12 else 0.0
    return {"slope": float(coef[0]), "intercept": float(coef[1]), "r2": r2, "x": x, "y": y, "pred": pred}


def write_fig(rows: list[dict[str, object]], reg: dict[str, object] | None) -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(1, 1, figsize=(8.6, 5.8))
    colors = {"near": "#2b8cbe", "mid": "#fdae61", "strong": "#d7191c"}
    for label in ["near", "mid", "strong"]:
        xs = [float(r["tan_nadir"]) for r in rows if r["angle_bin"] == label and r["resid_signed_z_m_zonly"] != ""]
        ys = [float(r["resid_signed_z_m_zonly"]) for r in rows if r["angle_bin"] == label and r["resid_signed_z_m_zonly"] != ""]
        ax.scatter(xs, ys, s=36, c=colors[label], label=label, alpha=0.85)
    if reg is not None:
        xx = np.linspace(0, max(reg["x"]) * 1.05, 100)
        yy = reg["slope"] * xx + reg["intercept"]
        ax.plot(xx, yy, "k--", lw=1.2, label=f"fit slope={reg['slope']:.3f} m/tan intercept={reg['intercept']:.3f} m")
        ax.set_title(f"Z-only residual vs tan(view zenith); R2={reg['r2']:.3f}")
    else:
        ax.set_title("Z-only residual vs tan(view zenith)")
    ax.axhline(0, color="#777777", lw=0.8)
    ax.set_xlabel("tan(view zenith angle)")
    ax.set_ylabel("signed residual along Z sensitivity (m)")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "residual_vs_tan.png", dpi=140)
    plt.close(fig)


def update_config(zeta_hat: float, ci_half: float) -> None:
    cfg = load_projection_config(CONFIG)
    cfg["orthometric_geoid_m"] = round(float(zeta_hat), 6)
    cfg["a1_zeta_ls"] = {
        "run_id": RUN_ID,
        "zeta_hat_m": round(float(zeta_hat), 6),
        "ci95_half_width_m": round(float(ci_half), 6),
        "updated_by": "phases/p2-gsjso/scripts/projection_zeta_ls.py --update-config",
    }
    with open(CONFIG, "w") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
        f.write("\n")


def write_versions(zeta0: float) -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    text = "\n".join(
        [
            f"run_id: {RUN_ID}",
            f"git_head: {git_head()}",
            "command: python3 phases/p2-gsjso/scripts/projection_zeta_ls.py --zeta0 48.0 --update-config",
            f"projection_config_before_fit: {describe_projection_config()}",
            f"zeta0_m: {zeta0:.6f}",
            f"python: {platform.python_version()}",
            f"numpy: {np.__version__}",
            "container: jointbuildgs-p0-tools:t0; Docker --user",
            "crs: geo EPSG:25832; OPF/COLMAP EPSG:32632 local with ellipsoidal Z",
            "reconstruction_or_retraining: none",
            "",
        ]
    )
    (RUN_DIR / "versions.txt").write_text(text)


def write_report(rows: list[dict[str, object]], zeta0: float, zfit: dict, xyzfit: dict, reg: dict | None):
    zeta_hat = zeta0 + float(zfit["x"][0])
    zeta_se = float(zfit["se"][0])
    ci_half = 1.96 * zeta_se
    xyz = xyzfit["x"]
    cov = xyzfit["cov"]
    corr_ze = float(cov[0, 1] / math.sqrt(cov[0, 0] * cov[1, 1])) if cov.shape[0] > 1 else float("nan")
    corr_zn = float(cov[0, 2] / math.sqrt(cov[0, 0] * cov[2, 2])) if cov.shape[0] > 2 else float("nan")
    med_by_bin = {}
    for label in ["near", "mid", "strong"]:
        vals = [float(r["offset_m_at_zeta0"]) for r in rows if r["angle_bin"] == label and r["offset_m_at_zeta0"] != ""]
        med_by_bin[label] = float(np.median(vals)) if vals else float("nan")
    lines = [
        "# projection_zeta_ls -- A1 LS zeta alignment",
        "",
        "> Observe only. No reconstruction/retraining. ALS class-6 roof points are the independent 3D evidence; final adoption is 김휘영.",
        "",
        "## Measurement",
        "",
        f"- buildings: {len(set(r['building_id'] for r in rows))} texture-clear success buildings",
        f"- measurements: {len(rows)} views (`near` <20 deg, `mid` 20-45 deg, `strong` >45 deg)",
        f"- method: ALS roof silhouette -> wide {SEARCH}px orientation-aware edge search, not gradient-max and not +/-28px STEP",
        f"- starting config zeta0: {zeta0:.3f} m",
        "",
        "## LS Result",
        "",
        f"- zeta-only: zeta_hat = **{zeta_hat:.3f} m**; 95% CI half-width = **{ci_half:.3f} m**; residual RMS = {zfit['rms_px']:.2f} px",
        f"- zeta+XY: zeta_hat = **{zeta0 + float(xyz[0]):.3f} m**, dE={float(xyz[1]):+.3f} m, dN={float(xyz[2]):+.3f} m; residual RMS = {xyzfit['rms_px']:.2f} px",
        f"- zeta/XY correlation: corr(zeta,dE)={corr_ze:+.3f}, corr(zeta,dN)={corr_zn:+.3f}; RMS improvement = {zfit['rms_px'] - xyzfit['rms_px']:.2f} px",
        "",
        "## Residual vs tan(view zenith)",
        "",
    ]
    if reg is not None:
        lines.append(
            f"- signed-Z residual regression: slope={reg['slope']:+.4f} m/tan, intercept={reg['intercept']:+.4f} m, R2={reg['r2']:.3f}"
        )
    lines.append("- figure: `docs/figs/projection_zeta_ls/residual_vs_tan.png`")
    lines.extend(
        [
            "",
            "## zeta comparison",
            "",
            "| source | zeta_m | delta_vs_LS_m | note |",
            "|---|---:|---:|---|",
            f"| LS A1 | {zeta_hat:.3f} | +0.000 | ALS-to-photo edge fit |",
            f"| GCG2016 sampled value from root-cause note | 45.700 | {45.7 - zeta_hat:+.3f} | official quasigeoid comparison value |",
            f"| pipeline prior | 48.000 | {48.0 - zeta_hat:+.3f} | existing GS-local/seed convention |",
            "",
            "## Angle-bin observation at zeta0",
            "",
            "| bin | median ALS offset at zeta0 (m) |",
            "|---|---:|",
        ]
    )
    for label in ["near", "mid", "strong"]:
        lines.append(f"| {label} | {med_by_bin[label]:.4f} |")
    lines.extend(
        [
            "",
            "## Recommendation",
            "",
            f"- 권고: A2 재게이트에는 LS zeta_hat {zeta_hat:.3f} m를 기본 config로 사용하고, 45.7/48.0은 sensitivity comparison 값으로만 병기한다. 채택 판정은 김휘영.",
            "",
            "## Caveats",
            "",
            "- This is an automated edge-silhouette alignment, so low-confidence or repeated roof texture can inflate uncertainty.",
            "- LoD2 is not used in the LS fit; building-level scatter here is ALS/photo/pose/edge-pick scatter, while LoD2 model error remains for A2's separate LoD2 column.",
            "",
            "## 판정 필요 지점",
            "",
            "- LS zeta_hat 채택 여부.",
            "- zeta+XY 개선량을 포즈/XY 보정 신호로 볼지 여부.",
            "- residual_vs_tan 기울기를 추가 수직 잔량으로 볼지 여부.",
        ]
    )
    OUT_MD.write_text("\n".join(lines) + "\n")


def main() -> None:
    update = "--update-config" in sys.argv
    zeta0 = projection_geoid_m()
    if "--zeta0" in sys.argv:
        zeta0 = float(sys.argv[sys.argv.index("--zeta0") + 1])
    sr = json.load(open(DATA / "work/opf/opf/scene_reference_frame.json"))["base_to_canonical"]
    W, H, params = parse_cam_model(DATA / "work/colmap/sparse/0/cameras.txt")
    cams = parse_cameras(DATA / "work/colmap/sparse/0/images.txt", sr)
    fp = footprints()
    rows = []
    for bid in BUILDINGS:
        gb = gml_building(bid)
        ring = fp.get(bid)
        if not gb or not gb["roof"] or ring is None:
            print(f"{bid} skip: missing roof/footprint")
            continue
        ground_z = float(np.vstack(gb["roof"] + gb["wall"])[:, 2].min())
        als = als_roof(ring, ground_z)
        if len(als) < MIN_ALS:
            print(f"{bid} skip: ALS roof pts {len(als)}")
            continue
        views, ctr = select_views(gb["roof"], ring, als, cams, params, sr, W, H, zeta0)
        seen_bins = []
        for label, nad, rad, cam in views:
            row = measure_one(bid, label, nad, rad, cam, ctr, als, params, sr, W, H, zeta0)
            if row is None:
                print(f"{bid} {label} nad={nad:.1f} no measurement")
                continue
            rows.append(row)
            seen_bins.append(label)
            print(
                f"{bid} {label:6} nad={nad:5.1f} dx={row['align_dx_px']:7.1f} dy={row['align_dy_px']:7.1f} "
                f"sigma={row['align_sigma_px']:6.1f} z={row['align_conf_z']:4.1f}"
            )
        missing = sorted(set(["near", "mid", "strong"]) - set(seen_bins))
        if missing:
            print(f"{bid} missing bins: {','.join(missing)}")
    if len(rows) < 8:
        raise RuntimeError(f"too few measurements: {len(rows)}")
    zfit = weighted_lstsq(rows, ["zeta"])
    xyzfit = weighted_lstsq(rows, ["zeta", "E", "N"])
    add_residuals(rows, zfit)
    reg = regression_residual_vs_tan(rows)
    write_fig(rows, reg)
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    cols = [
        "building_id",
        "angle_bin",
        "view_nadir_deg",
        "tan_nadir",
        "frame_r",
        "view",
        "n_als_inframe",
        "align_dx_px",
        "align_dy_px",
        "align_sigma_px",
        "align_conf_z",
        "align_n_boundary",
        "offset_m_at_zeta0",
        "resid_u_px_zonly",
        "resid_v_px_zonly",
        "resid_px_zonly",
        "resid_signed_z_m_zonly",
        "sens_z_u_px_per_m",
        "sens_z_v_px_per_m",
        "sens_E_u_px_per_m",
        "sens_E_v_px_per_m",
        "sens_N_u_px_per_m",
        "sens_N_v_px_per_m",
    ]
    with open(OUT_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    RESULT_JSON.parent.mkdir(parents=True, exist_ok=True)
    zeta_hat = zeta0 + float(zfit["x"][0])
    ci_half = 1.96 * float(zfit["se"][0])
    json.dump(
        {
            "run_id": RUN_ID,
            "zeta0_m": zeta0,
            "zeta_only": {
                "zeta_hat_m": zeta_hat,
                "ci95_half_width_m": ci_half,
                "delta_zeta_m": float(zfit["x"][0]),
                "se_delta_zeta_m": float(zfit["se"][0]),
                "rms_px": zfit["rms_px"],
            },
            "zeta_xy": {
                "zeta_hat_m": zeta0 + float(xyzfit["x"][0]),
                "dE_m": float(xyzfit["x"][1]),
                "dN_m": float(xyzfit["x"][2]),
                "rms_px": xyzfit["rms_px"],
            },
            "residual_vs_tan": None
            if reg is None
            else {"slope_m_per_tan": reg["slope"], "intercept_m": reg["intercept"], "r2": reg["r2"]},
            "n_measurements": len(rows),
            "n_buildings": len(set(r["building_id"] for r in rows)),
        },
        open(RESULT_JSON, "w"),
        ensure_ascii=False,
        indent=2,
    )
    write_report(rows, zeta0, zfit, xyzfit, reg)
    write_versions(zeta0)
    if update:
        update_config(zeta_hat, ci_half)
    print(f"[summary] zeta_hat={zeta_hat:.3f} +/- {ci_half:.3f} m (95% CI), n={len(rows)}")
    print(f"[summary] zeta+XY rms={xyzfit['rms_px']:.2f}px vs zeta-only rms={zfit['rms_px']:.2f}px")
    print(f"[done] {OUT_CSV}")
    print(f"[done] {OUT_MD}")
    print(f"[done] {FIG_DIR / 'residual_vs_tan.png'}")
    if update:
        print(f"[done] updated {CONFIG}")


if __name__ == "__main__":
    main()
