#!/usr/bin/env python3
"""A2 projection gate v2 after the configurable zeta fix.

Same measurement family as A1: wide orientation-aware edge alignment, not
gradient-max and not +/-28px STEP. Reports ALS-to-photo (projection/pose) and
LoD2-to-photo (projection+model) in separate columns.

No reconstruction, retraining, or final pass/fail judgment.
"""
from __future__ import annotations

import csv
import json
import math
import platform
import subprocess
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))
from scripts.evidence_and_attributes.review_packages.evidence_cards_v2 import DATA, GEOJSON, IMAGE_DIR, REPO, distort, gml_building, parse_cam_model, parse_cameras, to_cam  # noqa: E402
from src.geospatial.projection_datum import describe_projection_config, projection_geoid_m  # noqa: E402
from scripts.input_and_alignment.datum_and_projection.projection_zeta_ls import (  # noqa: E402
    BUILDINGS,
    RUN_DIR as _A1_RUN_DIR,
    SEARCH,
    STEP,
    als_roof,
    footprints,
    measure_one,
    offset_m,
    orient_align,
    project_points,
    select_views,
    sensitivities,
    silhouette_boundary,
)


RUN_ID = "20260702_A2_projection_gate_v2"
RUN_DIR = REPO / "phases" / "p2-gsjso" / "runs" / RUN_ID
FIG_DIR = REPO / "docs/figs/projection_gate_v2"
OUT_CSV = REPO / "docs/experiments/input-and-alignment/projection_gate/tables/projection_gate_v2.csv"
OUT_MD = REPO / "docs/experiments/input-and-alignment/projection_gate/reports/projection_gate_v2.md"
RESULT_JSON = REPO / "results/tum_transfer/mob/overseg_lever/projection_gate_v2.json"


def git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    except Exception as exc:  # pragma: no cover
        return f"unavailable: {exc}"


def densify_lod2_edges(rings_uv: list[np.ndarray], spacing: float = 4.0):
    pts = []
    tan = []
    for ring in rings_uv:
        r = np.asarray(ring, float)
        if len(r) < 2:
            continue
        for i in range(len(r)):
            a = r[i]
            b = r[(i + 1) % len(r)]
            if not np.isfinite(a).all() or not np.isfinite(b).all():
                continue
            length = float(np.linalg.norm(b - a))
            if length < 1e-6 or length > 2500:
                continue
            tv = (b - a) / length
            for s in np.arange(0, length, spacing):
                pts.append(a + s * tv)
                tan.append(tv)
    if len(pts) < 24:
        return None, None
    return np.asarray(pts, float), np.asarray(tan, float)


def project_lod2_rings(roof: list[np.ndarray], cam, params: np.ndarray, sr: dict, zeta: float):
    rings = []
    for ring in roof:
        uv, front = project_points(np.asarray(ring, float), cam, params, sr, zeta)
        good = front & np.isfinite(uv[:, 0]) & np.isfinite(uv[:, 1])
        if good.sum() >= 3:
            rings.append(uv[good])
    return rings


def align_lod2(roof: list[np.ndarray], cam, params: np.ndarray, sr: dict, zeta: float, image_gray, x0: int, y0: int):
    rings_uv = project_lod2_rings(roof, cam, params, sr, zeta)
    pts, tan = densify_lod2_edges(rings_uv)
    if pts is None:
        return None, rings_uv
    gy, gx = np.gradient(image_gray)
    return orient_align(pts, tan, gx, gy, x0, y0), rings_uv


def align_als(als: np.ndarray, cam, params: np.ndarray, sr: dict, W: int, H: int, zeta: float, image_gray, x0: int, y0: int):
    uv, front = project_points(als, cam, params, sr, zeta)
    inb = front & (uv[:, 0] >= 0) & (uv[:, 0] < W) & (uv[:, 1] >= 0) & (uv[:, 1] < H)
    pts, tan = silhouette_boundary(uv[inb], W, H)
    if pts is None:
        return None, uv[inb], int(inb.sum())
    gy, gx = np.gradient(image_gray)
    return orient_align(pts, tan, gx, gy, x0, y0), uv[inb], int(inb.sum())


def crop_for_measure(roof: list[np.ndarray], als: np.ndarray, cam, params: np.ndarray, sr: dict, W: int, H: int, zeta: float):
    rings_uv = project_lod2_rings(roof, cam, params, sr, zeta)
    uv_als, front = project_points(als, cam, params, sr, zeta)
    inb = front & (uv_als[:, 0] >= 0) & (uv_als[:, 0] < W) & (uv_als[:, 1] >= 0) & (uv_als[:, 1] < H)
    pts = []
    if rings_uv:
        pts.append(np.vstack(rings_uv))
    if inb.any():
        pts.append(uv_als[inb])
    if not pts:
        return None
    allu = np.vstack(pts)
    pad = SEARCH + 100
    x0 = int(max(0, np.nanmin(allu[:, 0]) - pad))
    y0 = int(max(0, np.nanmin(allu[:, 1]) - pad))
    x1 = int(min(W, np.nanmax(allu[:, 0]) + pad))
    y1 = int(min(H, np.nanmax(allu[:, 1]) + pad))
    if x1 - x0 < 32 or y1 - y0 < 32:
        return None
    img = np.asarray(Image.open(IMAGE_DIR / cam.name).convert("RGB"))[y0:y1, x0:x1]
    gray = img.astype(np.float32) @ np.array([0.299, 0.587, 0.114], float)
    return x0, y0, x1, y1, img, gray


def metric_from_align(al, sens: dict[str, np.ndarray]):
    if al is None:
        return {"px": "", "m": "", "dx": "", "dy": "", "sigma": "", "conf_z": ""}
    return {
        "px": round(float(math.hypot(al["dx"], al["dy"])), 3),
        "m": round(offset_m(float(al["dx"]), float(al["dy"]), sens), 4),
        "dx": round(float(al["dx"]), 3),
        "dy": round(float(al["dy"]), 3),
        "sigma": round(float(al["sigma_px"]), 3),
        "conf_z": round(float(al["z"]), 3),
    }


def render(row, img, x0: int, y0: int, rings_uv: list[np.ndarray], als_uv: np.ndarray, lod2_al, als_al) -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(1, 3, figsize=(18.5, 6.2))
    for a in ax:
        a.imshow(img)
        a.axis("off")
    ax[0].set_title("photo crop", fontsize=8)
    for ring in rings_uv:
        q = np.vstack([ring, ring[:1]])
        ax[1].plot(q[:, 0] - x0, q[:, 1] - y0, "-", c="lime", lw=1.2)
    if len(als_uv):
        u = als_uv[:, 0] - x0
        v = als_uv[:, 1] - y0
        ok = (u >= 0) & (u < img.shape[1]) & (v >= 0) & (v < img.shape[0])
        ax[1].scatter(u[ok], v[ok], s=0.7, c="cyan", alpha=0.45)
    ax[1].set_title("as-projected: clean LoD2 rings + ALS roof pts", fontsize=8)
    for ring in rings_uv:
        q = np.vstack([ring, ring[:1]])
        ax[2].plot(q[:, 0] - x0, q[:, 1] - y0, "-", c="lime", lw=0.6, alpha=0.55)
        if lod2_al:
            ax[2].plot(q[:, 0] - x0 + lod2_al["dx"], q[:, 1] - y0 + lod2_al["dy"], "-", c="orange", lw=1.0)
    if len(als_uv):
        u = als_uv[:, 0] - x0
        v = als_uv[:, 1] - y0
        ok = (u >= 0) & (u < img.shape[1]) & (v >= 0) & (v < img.shape[0])
        ax[2].scatter(u[ok], v[ok], s=0.35, c="cyan", alpha=0.22)
        if als_al:
            ax[2].scatter(u[ok] + als_al["dx"], v[ok] + als_al["dy"], s=0.35, c="yellow", alpha=0.35)
    ax[2].set_title(
        f"shifted-to-edge: ALS {row['als_off_m']}m, LoD2 {row['lod2_off_m']}m",
        fontsize=8,
    )
    fig.suptitle(
        f"{row['building_id']} {row['angle_bin']} nadir={row['view_nadir_deg']} deg | "
        f"ALS off={row['als_off_m']} m (p90 reported in CSV summary), LoD2 off={row['lod2_off_m']} m | {row['view']}",
        fontsize=8.5,
    )
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    out = FIG_DIR / f"{row['building_id'].replace('DEBY_LOD2_', '')}_{row['angle_bin']}.png"
    fig.savefig(out, dpi=115)
    plt.close(fig)


def measure_gate_one(bid: str, label: str, nad: float, rad: float, cam, ctr: np.ndarray, gb, als: np.ndarray, params, sr, W, H, zeta: float):
    crop = crop_for_measure(gb["roof"], als, cam, params, sr, W, H, zeta)
    if crop is None:
        return None
    x0, y0, _x1, _y1, img, gray = crop
    sens = sensitivities(ctr, cam, params, sr, zeta)
    if sens is None:
        return None
    als_al, als_uv, n_als = align_als(als, cam, params, sr, W, H, zeta, gray, x0, y0)
    lod2_al, rings_uv = align_lod2(gb["roof"], cam, params, sr, zeta, gray, x0, y0)
    AM = metric_from_align(als_al, sens)
    LM = metric_from_align(lod2_al, sens)
    row = {
        "building_id": f"DEBY_LOD2_{bid}",
        "angle_bin": label,
        "view_nadir_deg": round(float(nad), 3),
        "tan_nadir": round(float(math.tan(math.radians(nad))), 6),
        "frame_r": round(float(rad), 3),
        "view": cam.name,
        "zeta_m": round(float(zeta), 6),
        "n_als_inframe": n_als,
        "als_off_px": AM["px"],
        "als_off_m": AM["m"],
        "als_dx_px": AM["dx"],
        "als_dy_px": AM["dy"],
        "als_sigma_px": AM["sigma"],
        "als_conf_z": AM["conf_z"],
        "lod2_off_px": LM["px"],
        "lod2_off_m": LM["m"],
        "lod2_dx_px": LM["dx"],
        "lod2_dy_px": LM["dy"],
        "lod2_sigma_px": LM["sigma"],
        "lod2_conf_z": LM["conf_z"],
    }
    render(row, img, x0, y0, rings_uv, als_uv, lod2_al, als_al)
    return row


def med_p90(rows: list[dict[str, object]], key: str, filt=None):
    vals = [float(r[key]) for r in rows if r[key] != "" and (filt is None or filt(r))]
    if not vals:
        return None, None, 0
    return float(np.median(vals)), float(np.percentile(vals, 90)), len(vals)


def write_residual_fig(rows: list[dict[str, object]]) -> None:
    fig, ax = plt.subplots(1, 1, figsize=(8.4, 5.8))
    colors = {"near": "#2b8cbe", "mid": "#fdae61", "strong": "#d7191c"}
    for label in ["near", "mid", "strong"]:
        xs = [float(r["tan_nadir"]) for r in rows if r["angle_bin"] == label and r["als_off_m"] != ""]
        ys = [float(r["als_off_m"]) for r in rows if r["angle_bin"] == label and r["als_off_m"] != ""]
        ax.scatter(xs, ys, s=42, c=colors[label], alpha=0.86, label=label)
    med_x, med_y = [], []
    for label in ["near", "mid", "strong"]:
        xs = [float(r["tan_nadir"]) for r in rows if r["angle_bin"] == label and r["als_off_m"] != ""]
        ys = [float(r["als_off_m"]) for r in rows if r["angle_bin"] == label and r["als_off_m"] != ""]
        if xs and ys:
            med_x.append(float(np.median(xs)))
            med_y.append(float(np.median(ys)))
    if med_x:
        order = np.argsort(med_x)
        ax.plot(np.array(med_x)[order], np.array(med_y)[order], "k--", lw=1.2, label="bin medians")
    ax.axhline(0.3, color="#555555", lw=1.0, ls=":", label="0.3 m proposal")
    ax.set_yscale("log")
    ax.set_xlabel("tan(view zenith angle)")
    ax.set_ylabel("ALS-to-photo offset (m, log scale)")
    ax.set_title("A2 ALS offset curve after zeta fix")
    ax.grid(alpha=0.25, which="both")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "als_offset_vs_tan.png", dpi=140)
    plt.close(fig)


def write_versions() -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    text = "\n".join(
        [
            f"run_id: {RUN_ID}",
            f"git_head: {git_head()}",
            "command: python3 scripts/input_and_alignment/datum_and_projection/projection_gate_v2.py",
            f"projection_config: {describe_projection_config()}",
            f"python: {platform.python_version()}",
            f"numpy: {np.__version__}",
            "container: jointbuildgs-p0-tools:t0; Docker --user",
            "crs: geo EPSG:25832; OPF/COLMAP EPSG:32632 local with ellipsoidal Z",
            "measurement: wide orientation-aware edge alignment; no +/-28px STEP; no gradient-max",
            "reconstruction_or_retraining: none",
            "",
        ]
    )
    (RUN_DIR / "versions.txt").write_text(text)


def write_report(rows: list[dict[str, object]], criteria: dict[str, object]) -> None:
    lines = [
        "# projection_gate_v2 -- A2 fix+zeta gate",
        "",
        "> Observe only. No reconstruction/retraining. Final 합/불 판정은 김휘영.",
        "",
        "## Method",
        "",
        f"- config: {describe_projection_config()}",
        f"- measurements: {len(rows)} rows = 8 buildings x near/mid/strong 3 views",
        f"- edge alignment: wide {SEARCH}px orientation-aware search, same measurement family as A1; not gradient-max and not +/-28px STEP",
        "- columns split ALS-to-photo (projection/pose) and LoD2-to-photo (projection+model).",
        "- overlays: clean LoD2 roof rings, not jagged silhouettes; each figure caption includes numeric offsets.",
        "",
        "## ALS Gate Summary",
        "",
        "| angle_bin | n | median_m | p90_m | proposed criterion |",
        "|---|---:|---:|---:|---|",
    ]
    for label in ["near", "mid", "strong"]:
        s = criteria["by_bin"][label]
        lines.append(f"| {label} | {s['n']} | {s['median_m']:.4f} | {s['p90_m']:.4f} | median <= 0.3 m |")
    lines.extend(
        [
            f"| overall | {criteria['overall']['n']} | {criteria['overall']['median_m']:.4f} | {criteria['overall']['p90_m']:.4f} | median <= 0.3 m |",
            "",
            f"- criteria_met_for_A3_instruction: **{criteria['criteria_met']}**",
            "",
            "## LoD2 Observation Summary",
            "",
            "| angle_bin | n | median_m | p90_m |",
            "|---|---:|---:|---:|",
        ]
    )
    for label in ["near", "mid", "strong"]:
        med, p90, n = med_p90(rows, "lod2_off_m", lambda r, label=label: r["angle_bin"] == label)
        lines.append(f"| {label} | {n} | {med:.4f} | {p90:.4f} |")
    med, p90, n = med_p90(rows, "lod2_off_m")
    lines.append(f"| overall | {n} | {med:.4f} | {p90:.4f} |")
    lines.extend(
        [
            "",
            "## Files",
            "",
            "- CSV: `docs/experiments/input-and-alignment/projection_gate/tables/projection_gate_v2.csv`",
            "- figures: `docs/figs/projection_gate_v2/*.png`",
            "- residual curve: `docs/figs/projection_gate_v2/als_offset_vs_tan.png`",
            "",
            "## Observation",
            "",
        ]
    )
    if criteria["criteria_met"]:
        lines.append("- ALS median values meet the numeric proposal in all angle bins and overall; final adoption remains 김휘영.")
    else:
        lines.append("- At least one ALS median value does not meet the numeric proposal. Per task instruction, A3 일괄 재계산 is not run from this state.")
        lines.extend(
            [
                "- Cause observation 1: ALS and LoD2 columns are both high in several rows, so the residual is not isolated to LoD2 model error.",
                "- Cause observation 2: strong-oblique rows have the largest ALS median and p90, matching the expected vertical/edge-correspondence sensitivity growth with tan(view zenith).",
                "- Cause observation 3: several rows have large search-derived sigma and far translations, so automated edge correspondence ambiguity remains a candidate source before any downstream recalculation.",
            ]
        )
    lines.extend(
        [
            "",
            "## 판정 필요 지점",
            "",
            "- A2 numeric proposal acceptance/rejection.",
            "- Whether high p90 or low-confidence rows should trigger additional manual correspondence measurement.",
            "- Whether A3 may proceed despite the A2 instruction gate.",
        ]
    )
    OUT_MD.write_text("\n".join(lines) + "\n")


def main() -> None:
    zeta = projection_geoid_m()
    sr = json.load(open(DATA / "work/opf/opf/scene_reference_frame.json"))["base_to_canonical"]
    W, H, params = parse_cam_model(DATA / "work/colmap/sparse/0/cameras.txt")
    cams = parse_cameras(DATA / "work/colmap/sparse/0/images.txt", sr)
    fp = footprints()
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for bid in BUILDINGS:
        gb = gml_building(bid)
        ring = fp.get(bid)
        if not gb or not gb["roof"] or ring is None:
            print(f"{bid} skip: missing roof/fp")
            continue
        ground_z = float(np.vstack(gb["roof"] + gb["wall"])[:, 2].min())
        als = als_roof(ring, ground_z)
        views, ctr = select_views(gb["roof"], ring, als, cams, params, sr, W, H, zeta)
        for label, nad, rad, cam in views:
            row = measure_gate_one(bid, label, nad, rad, cam, ctr, gb, als, params, sr, W, H, zeta)
            if row is None:
                print(f"{bid} {label} no measurement")
                continue
            rows.append(row)
            print(
                f"{bid} {label:6} nad={nad:5.1f} ALS={row['als_off_m']}m LoD2={row['lod2_off_m']}m "
                f"view={cam.name}"
            )
    if len(rows) < 24:
        print(f"[warn] expected 24 rows, got {len(rows)}")
    cols = [
        "building_id",
        "angle_bin",
        "view_nadir_deg",
        "tan_nadir",
        "frame_r",
        "view",
        "zeta_m",
        "n_als_inframe",
        "als_off_px",
        "als_off_m",
        "als_dx_px",
        "als_dy_px",
        "als_sigma_px",
        "als_conf_z",
        "lod2_off_px",
        "lod2_off_m",
        "lod2_dx_px",
        "lod2_dy_px",
        "lod2_sigma_px",
        "lod2_conf_z",
    ]
    with open(OUT_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    by_bin = {}
    criteria_met = True
    for label in ["near", "mid", "strong"]:
        med, p90, n = med_p90(rows, "als_off_m", lambda r, label=label: r["angle_bin"] == label)
        by_bin[label] = {"median_m": med, "p90_m": p90, "n": n}
        criteria_met = criteria_met and med is not None and med <= 0.3
    med, p90, n = med_p90(rows, "als_off_m")
    overall = {"median_m": med, "p90_m": p90, "n": n}
    criteria_met = criteria_met and med is not None and med <= 0.3
    criteria = {"by_bin": by_bin, "overall": overall, "criteria_met": bool(criteria_met)}
    write_residual_fig(rows)
    RESULT_JSON.parent.mkdir(parents=True, exist_ok=True)
    json.dump({"run_id": RUN_ID, "criteria": criteria, "n_rows": len(rows)}, open(RESULT_JSON, "w"), ensure_ascii=False, indent=2)
    write_report(rows, criteria)
    write_versions()
    print(f"[summary] ALS medians: near={by_bin['near']['median_m']:.4f}, mid={by_bin['mid']['median_m']:.4f}, strong={by_bin['strong']['median_m']:.4f}, overall={overall['median_m']:.4f}")
    print(f"[summary] criteria_met_for_A3_instruction={criteria_met}")
    print(f"[done] {OUT_CSV}")
    print(f"[done] {OUT_MD}")
    print(f"[done] {FIG_DIR}")


if __name__ == "__main__":
    main()
