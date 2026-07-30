#!/usr/bin/env python3
"""Build corrected-S1 observation material from completed C001 runs.

This script is post-processing only: it reads the already trained corrected-S1
checkpoints/readout/evaluation outputs and writes comparison CSVs, figures, case
panels, and the final observation report. It does not train and does not modify
canonical S0 artifacts.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt


REPO = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

RUN_ID = "20260709_e5_c001_corrected_s1"
RUN_DIR = REPO / "phases/p2-gsjso/runs" / RUN_ID
SNAP_DIR = RUN_DIR / "snapshots"
FIG_DIR = REPO / "docs/figs/e5_c001_corrected_s1"
REPORT = REPO / "docs/experiments/joint-optimization/e5_c001_corrected_s1/reports/W_E5_C001_corrected_S1.md"

S1_P0_RUN = REPO / "phases/p0-audit/runs/e5p_3b_s1_20260708_C001"
CORR_P0_RUN = REPO / "phases/p0-audit/runs/e5p_corrected_s1_20260709_C001"
CORR_RUN_ROOT = REPO / "results/tum_transfer/e5_corrected_s1/C001/runs"
DATA_ROOT = REPO / "results/tum_transfer/e5_pilot/C001/data_geoidfix_C001_buf20"

S0_SOURCE_BY_ARM = {"sparse": "gs_sparse_r1", "dense": "gs_dense_r1", "acmp": "gs_acmp_r1"}
S1_SOURCE_BY_ARM = {
    "sparse": "base__gs_e5_C001_s1_sparse_r1",
    "dense": "base__gs_e5_C001_s1_dense_r1",
    "acmp": "base__gs_e5_C001_s1_acmp_r1",
}
CORR_SOURCE_BY_ARM = {
    "sparse": "base__gs_e5_C001_corrected_s1_sparse_r1",
    "dense": "base__gs_e5_C001_corrected_s1_dense_r1",
    "acmp": "base__gs_e5_C001_corrected_s1_acmp_r1",
}

ROUTING = {
    "normal": ["4907184", "4908168", "4907202", "4907198", "4907185", "4908178"],
    "defect": ["4907186", "4907188", "4907194", "4907195", "60098"],
    "textureless_observed": ["4907199", "8568391", "8568392"],
    "low_observation": ["108247350", "108247351"],
    "hard_all_fail": ["108247349", "4908179"],
}
PANEL_BUILDINGS = {
    "normal": "DEBY_LOD2_4907184",
    "defect": "DEBY_LOD2_60098",
    "textureless_observed": "DEBY_LOD2_8568391",
}


def rel(path: Path | str) -> str:
    p = Path(path)
    try:
        return str(p.relative_to(REPO))
    except ValueError:
        return str(p)


def capture(cmd: list[str]) -> str:
    try:
        return subprocess.check_output(cmd, cwd=REPO, text=True, stderr=subprocess.STDOUT).strip()
    except Exception as exc:  # noqa: BLE001
        return f"not_available:{exc}"


def short_id(bid: str) -> str:
    return bid.replace("DEBY_LOD2_", "")


def full_id(sid: str) -> str:
    return sid if sid.startswith("DEBY_LOD2_") else f"DEBY_LOD2_{sid}"


def fmt(value: Any, digits: int = 3) -> str:
    if value is None:
        return ""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not math.isfinite(v):
        return ""
    return f"{v:.{digits}f}"


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def md_table(rows: list[dict[str, Any]], columns: list[str], max_rows: int | None = None) -> str:
    use = rows if max_rows is None else rows[:max_rows]
    lines = ["| " + " | ".join(columns) + " |", "|" + "|".join("---" for _ in columns) + "|"]
    for row in use:
        lines.append("| " + " | ".join(str(row.get(col, "")) for col in columns) + " |")
    if max_rows is not None and len(rows) > max_rows:
        lines.append("| ... | " + f"{len(rows) - max_rows} rows omitted |" + " | ".join("" for _ in columns[2:]) + " |")
    return "\n".join(lines)


def safe_mean(series: pd.Series) -> float:
    vals = pd.to_numeric(series, errors="coerce")
    return float(vals.mean()) if vals.notna().any() else float("nan")


def safe_median(series: pd.Series) -> float:
    vals = pd.to_numeric(series, errors="coerce")
    return float(vals.median()) if vals.notna().any() else float("nan")


def source_metrics(df: pd.DataFrame, source_run: str) -> dict[str, Any]:
    part = df[df["source_run"] == source_run].copy()
    if part.empty:
        return {
            "completeness": float("nan"),
            "correctness": float("nan"),
            "median_ref_rms_m": float("nan"),
            "mean_ref_rms_m": float("nan"),
            "has_lod22": 0,
            "val3dity_valid": 0,
        }
    return {
        "completeness": safe_mean(part["completeness"]),
        "correctness": safe_mean(part["correctness"]),
        "median_ref_rms_m": safe_median(part["ref_rms_m"]),
        "mean_ref_rms_m": safe_mean(part["ref_rms_m"]),
        "has_lod22": int(part["has_lod22"].astype(bool).sum()),
        "val3dity_valid": int(part["val3dity_valid"].astype(bool).sum()),
    }


def coverage_by_arm(cov: pd.DataFrame, arm: str, setting: str = "base") -> float:
    part = cov[(cov["setting"] == setting) & (cov["arm"] == arm) & (cov["stage"] == "sor_post_clean")]
    return safe_mean(part["coverage_frac"])


def make_comparison_tables() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    s0 = pd.read_csv(REPO / "docs/experiments/evaluation/e5_c001_8way/tables/e5_c001_8way_metrics.csv")
    s1 = pd.read_csv(REPO / "docs/experiments/joint-optimization/e5_c001_3b_s1/tables/e5_c001_3b_s1_metrics.csv")
    corr = pd.read_csv(REPO / "docs/experiments/joint-optimization/e5_c001_corrected_s1/tables/e5_c001_corrected_s1_building_8way.csv")
    s1_delta = pd.read_csv(REPO / "docs/experiments/joint-optimization/e5_c001_3b_s1/tables/e5_c001_3b_s1_delta.csv")
    corr_cov = pd.read_csv(REPO / "docs/experiments/joint-optimization/e5_c001_corrected_s1/tables/e5_c001_corrected_s1_coverage.csv")

    rows: list[dict[str, Any]] = []
    for arm in ["sparse", "dense", "acmp"]:
        prev = s1_delta[s1_delta["arm"] == arm].iloc[0].to_dict()
        cm = source_metrics(corr[corr["setting"] == "base"], CORR_SOURCE_BY_ARM[arm])
        row = {
            "arm": arm,
            "s0_run": prev["s0_run"],
            "s1_run": prev["s1_run"],
            "corrected_run": f"gs_e5_C001_corrected_s1_{arm}_r1",
            "s0_coverage": prev["s0_coverage"],
            "s1_coverage": prev["s1_coverage"],
            "corrected_coverage": coverage_by_arm(corr_cov, arm),
            "s0_completeness": prev["s0_completeness"],
            "s1_completeness": prev["s1_completeness"],
            "corrected_completeness": cm["completeness"],
            "s0_correctness": prev["s0_correctness"],
            "s1_correctness": prev["s1_correctness"],
            "corrected_correctness": cm["correctness"],
            "s0_median_ref_rms_m": prev["s0_median_ref_rms_m"],
            "s1_median_ref_rms_m": prev["s1_median_ref_rms_m"],
            "corrected_median_ref_rms_m": cm["median_ref_rms_m"],
            "s0_has_lod22": prev["s0_has_lod22"],
            "s1_has_lod22": prev["s1_has_lod22"],
            "corrected_has_lod22": cm["has_lod22"],
            "s0_val3dity_valid": prev["s0_val3dity_valid"],
            "s1_val3dity_valid": prev["s1_val3dity_valid"],
            "corrected_val3dity_valid": cm["val3dity_valid"],
        }
        row["delta_corrected_vs_s1_coverage"] = row["corrected_coverage"] - row["s1_coverage"]
        row["delta_corrected_vs_s1_median_ref_rms_m"] = row["corrected_median_ref_rms_m"] - row["s1_median_ref_rms_m"]
        row["delta_corrected_vs_s1_validity"] = row["corrected_val3dity_valid"] - row["s1_val3dity_valid"]
        rows.append(row)

    delta = pd.DataFrame(rows)
    delta.to_csv(REPO / "docs/experiments/joint-optimization/e5_c001_corrected_s1/tables/e5_c001_corrected_s1_delta.csv", index=False)

    breakdown = (
        corr[corr["setting"] == "base"]
        .groupby(["setting", "arm", "status", "status_reason"], dropna=False)
        .size()
        .reset_index(name="n_buildings")
        .sort_values(["arm", "status_reason"])
    )
    breakdown.to_csv(REPO / "docs/experiments/joint-optimization/e5_c001_corrected_s1/tables/e5_c001_corrected_s1_validity_breakdown.csv", index=False)

    target_rows: list[dict[str, Any]] = []
    all_rows = pd.concat([s0, s1, corr], ignore_index=True)
    source_map = {
        "raw_dense": "raw_dense",
        "lidar": "lidar",
        "s0_dense": "gs_dense_r1",
        "s1_dense": S1_SOURCE_BY_ARM["dense"],
        "corrected_dense": CORR_SOURCE_BY_ARM["dense"],
    }
    for route, ids in ROUTING.items():
        for sid in ids:
            bid = full_id(sid)
            row: dict[str, Any] = {"route": route, "building_id": bid}
            for label, source_run in source_map.items():
                part = all_rows[(all_rows["building_id"] == bid) & (all_rows["source_run"] == source_run)]
                if part.empty:
                    row[f"{label}_has_lod22"] = ""
                    row[f"{label}_valid"] = ""
                    row[f"{label}_rms_m"] = ""
                    row[f"{label}_roof_planes"] = ""
                    continue
                r = part.iloc[0]
                row[f"{label}_has_lod22"] = bool(r.get("has_lod22"))
                row[f"{label}_valid"] = bool(r.get("val3dity_valid"))
                row[f"{label}_rms_m"] = r.get("ref_rms_m")
                row[f"{label}_roof_planes"] = r.get("roof_planes")
            target_rows.append(row)
    target = pd.DataFrame(target_rows)
    target.to_csv(REPO / "docs/experiments/joint-optimization/e5_c001_corrected_s1/tables/e5_c001_corrected_s1_target_observations.csv", index=False)
    return delta, breakdown, target


def make_summary_figures(delta: pd.DataFrame, breakdown: pd.DataFrame, target: pd.DataFrame) -> list[Path]:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    arms = delta["arm"].tolist()
    x = np.arange(len(arms))
    fig, axes = plt.subplots(1, 3, figsize=(12.2, 3.7))
    for label, color, offset in [("s0", "#8d99ae", -0.24), ("s1", "#457b9d", 0.0), ("corrected", "#e76f51", 0.24)]:
        axes[0].bar(x + offset, delta[f"{label}_coverage"], width=0.22, color=color, label=label)
        axes[1].bar(x + offset, delta[f"{label}_median_ref_rms_m"], width=0.22, color=color, label=label)
        axes[2].bar(x + offset, delta[f"{label}_val3dity_valid"], width=0.22, color=color, label=label)
    for ax in axes:
        ax.set_xticks(x)
        ax.set_xticklabels(arms)
        ax.grid(axis="y", alpha=0.25)
    axes[0].set_title("coverage post-SOR")
    axes[1].set_title("median reference RMS")
    axes[1].set_ylabel("m")
    axes[2].set_title("val3dity valid count")
    axes[0].legend(loc="upper right", fontsize=8)
    fig.tight_layout()
    out = FIG_DIR / "corrected_s1_delta_summary.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)
    paths.append(out)

    piv = breakdown.pivot_table(index="arm", columns="status_reason", values="n_buildings", aggfunc="sum", fill_value=0)
    fig, ax = plt.subplots(figsize=(7.8, 3.9))
    bottom = np.zeros(len(piv))
    colors = plt.cm.Set2(np.linspace(0, 1, max(1, len(piv.columns))))
    for color, col in zip(colors, piv.columns):
        vals = piv[col].to_numpy(dtype=float)
        ax.bar(piv.index, vals, bottom=bottom, label=col, color=color)
        bottom += vals
    ax.set_ylabel("buildings")
    ax.set_title("corrected-S1 base status reasons")
    ax.legend(fontsize=7, loc="center left", bbox_to_anchor=(1.0, 0.5))
    ax.grid(axis="y", alpha=0.2)
    fig.tight_layout()
    out = FIG_DIR / "corrected_s1_validity_by_arm.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)
    paths.append(out)

    fig, ax = plt.subplots(figsize=(8.4, 3.8))
    route_order = ["normal", "defect", "textureless_observed", "low_observation", "hard_all_fail"]
    plot_rows = []
    for route in route_order:
        part = target[target["route"] == route]
        for label in ["raw_dense", "s1_dense", "corrected_dense", "lidar"]:
            vals = pd.to_numeric(part[f"{label}_rms_m"], errors="coerce")
            plot_rows.append({"route": route, "source": label, "median_rms": vals.median()})
    plot = pd.DataFrame(plot_rows)
    width = 0.18
    rx = np.arange(len(route_order))
    for i, label in enumerate(["raw_dense", "s1_dense", "corrected_dense", "lidar"]):
        vals = [plot[(plot["route"] == r) & (plot["source"] == label)]["median_rms"].iloc[0] for r in route_order]
        ax.bar(rx + (i - 1.5) * width, vals, width=width, label=label)
    ax.set_xticks(rx)
    ax.set_xticklabels(route_order, rotation=20, ha="right")
    ax.set_ylabel("median ref RMS (m)")
    ax.set_title("route-stratified reference RMS")
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    out = FIG_DIR / "corrected_s1_route_ref_rms.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)
    paths.append(out)
    return paths


def append_issue(message: str, path: Path | str = "") -> None:
    issue_path = REPO / "docs/e5_c001_corrected_s1_report_issues.csv"
    exists = issue_path.exists()
    with issue_path.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["part", "severity", "message", "path"], lineterminator="\n")
        if not exists:
            writer.writeheader()
        writer.writerow({"part": "report", "severity": "warn", "message": message, "path": rel(path) if path else ""})


def make_render_placeholders(message: str = "corrected-S1 render snapshot unavailable") -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    for bid in PANEL_BUILDINGS.values():
        for kind in ["rgb", "depth"]:
            path = FIG_DIR / f"render_{kind}_{short_id(bid)}.png"
            if path.exists():
                continue
            fig, ax = plt.subplots(figsize=(3.2, 2.1))
            ax.text(0.5, 0.5, f"{kind} render\n{message}", ha="center", va="center", fontsize=9)
            ax.set_axis_off()
            fig.tight_layout()
            fig.savefig(path, dpi=160)
            plt.close(fig)


def render_snaps(args: argparse.Namespace) -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        import torch
        from PIL import Image
        from src.stage2.dataloader import ColmapDataset
        from src.stage2.renderer import render
        import e5_c001_render_audit as ra
    except Exception as exc:  # noqa: BLE001
        append_issue(f"render imports failed: {type(exc).__name__}: {exc}")
        make_render_placeholders()
        return

    if args.device == "cuda" and not torch.cuda.is_available():
        append_issue("CUDA unavailable; render snapshots written as placeholders")
        make_render_placeholders()
        return

    try:
        ds = ColmapDataset(root=str(DATA_ROOT), downscale=0.5, load_depth=True, load_normal=True, load_semantic=True)
        view_rows = pd.read_csv(REPO / "docs/experiments/input-and-alignment/lowtex_v5/tables/lowtex_v5.csv")
        lowtex = dict(zip(view_rows["building_id"], view_rows["lowtex_v5_view"]))
        name_to_idx = {fr.name: i for i, fr in enumerate(ds.frames)}
        ckpt = CORR_RUN_ROOT / "gs_e5_C001_corrected_s1_dense_r1/ckpt/final.pt"
        payload = torch.load(ckpt, map_location="cpu")
        device = torch.device(args.device)
        model = ra.make_model_from_state(payload["state_dict"], device)
    except Exception as exc:  # noqa: BLE001
        append_issue(f"render setup failed: {type(exc).__name__}: {exc}")
        make_render_placeholders()
        return

    for bid in PANEL_BUILDINGS.values():
        view_name = lowtex.get(bid, "")
        idx = name_to_idx.get(view_name)
        if idx is None:
            append_issue(f"target render view not found for {bid}: {view_name}")
            continue
        try:
            batch = ds[idx]
            w2c = batch["w2c"].to(device)
            K = batch["K"].to(device)
            H, W = batch["height"], batch["width"]
            with torch.no_grad():
                out = render(model, w2c, K, W, H, sh_degree=model.active_sh_degree, render_mode="RGB+ED")
            rgb = out["rgb"].detach().cpu().numpy().clip(0, 1)
            depth = np.asarray(out["depth"].detach().cpu().numpy()).squeeze()
            alpha = np.asarray(out["alpha"].detach().cpu().numpy()).squeeze()
            if rgb.ndim == 3 and rgb.shape[0] in (3, 4):
                rgb = np.moveaxis(rgb, 0, -1)
            Image.fromarray((rgb * 255).astype(np.uint8)).save(FIG_DIR / f"render_rgb_{short_id(bid)}.png")
            valid = np.isfinite(depth) & (depth > 0) & (alpha > 0.5)
            depth_vis = np.zeros(depth.shape, dtype=np.float32)
            if np.any(valid):
                lo, hi = np.quantile(depth[valid], [0.02, 0.98])
                depth_vis = np.clip((depth - lo) / max(hi - lo, 1e-6), 0, 1)
            plt.imsave(FIG_DIR / f"render_depth_{short_id(bid)}.png", depth_vis, cmap="magma")
        except Exception as exc:  # noqa: BLE001
            append_issue(f"render failed for {bid}: {type(exc).__name__}: {exc}")
    make_render_placeholders()


def reference_sample_points(surfaces: list[Any], e_module: Any) -> np.ndarray:
    pts_all = []
    for surf in surfaces:
        pts = e_module.sample_polygon_points(surf.polygon, e_module.SAMPLE_SPACING_M, limit=2500)
        if len(pts) == 0:
            continue
        z = surf.z_at(pts[:, 0], pts[:, 1])
        pts_all.append(np.column_stack([pts[:, 0], pts[:, 1], z]))
    return np.vstack(pts_all) if pts_all else np.empty((0, 3), dtype=float)


def make_case_panels() -> list[Path]:
    import e5_c001_8way as e
    import e5_c001_3b_s1 as s1
    import pointcloud_attributes_v1 as base

    e.configure_korean_font()
    target_ids = set(PANEL_BUILDINGS.values())
    footprints = base.load_footprints(e.FOOTPRINTS_GPKG, target_ids)
    refs = e.parse_lod2_roofs(e.LOD2_DIR, target_ids)
    base_srcs = {src.source_run: src for src in e.sources()}
    corrected_dense = e.Source(
        "gs_corrected_dense",
        CORR_SOURCE_BY_ARM["dense"],
        "GS-corrected-S1 dense",
        "gs",
        CORR_P0_RUN / "base/status/gs_e5_C001_corrected_s1_dense_r1_run_1.csv",
        None,
        CORR_P0_RUN / "base/cityjson/gs_e5_C001_corrected_s1_dense_r1_run_1.city.json",
        None,
        pointcloud_template=str(CORR_P0_RUN / "base/roofer/gs_e5_C001_corrected_s1_dense_r1/run_1/{bid}_run_1_classified.las"),
        pair_raw="raw_dense",
        run_name="gs_e5_C001_corrected_s1_dense_r1",
        seed="dense",
        replicate="r1",
        readout="corrected-S1 base readout",
        z_shift_to_reference_m=e.ELLIP_TO_REF_SHIFT_M,
    )
    s1_dense = e.Source(
        "gs_s1_dense",
        S1_SOURCE_BY_ARM["dense"],
        "GS-S1 dense",
        "gs",
        S1_P0_RUN / "base/status/gs_e5_C001_s1_dense_r1_run_1.csv",
        None,
        S1_P0_RUN / "base/cityjson/gs_e5_C001_s1_dense_r1_run_1.city.json",
        None,
        pointcloud_template=str(S1_P0_RUN / "base/roofer/gs_e5_C001_s1_dense_r1/run_1/{bid}_run_1_classified.las"),
        pair_raw="raw_dense",
        run_name="gs_e5_C001_s1_dense_r1",
        seed="dense",
        replicate="r1",
        readout="S1 base readout",
        z_shift_to_reference_m=e.ELLIP_TO_REF_SHIFT_M,
    )
    panel_srcs = [
        ("raw_dense", base_srcs["raw_dense"]),
        ("gs_s0_dense", base_srcs["gs_dense_r1"]),
        ("gs_corrected_dense", corrected_dense),
        ("lidar", base_srcs["lidar"]),
        ("reference", base_srcs["reference"]),
    ]
    before_after_srcs = [("GS-S1 dense", s1_dense), ("GS-corrected-S1 dense", corrected_dense)]
    pred: dict[str, dict[str, list[Any]]] = {}
    for key, src in panel_srcs:
        if key == "reference":
            pred[key] = refs
        else:
            parsed = e.parse_cityjson_roofs(src.cityjson_path, target_ids)
            pred[key] = {bid: e.shift_surface_z(surfaces, src.z_shift_to_reference_m) for bid, surfaces in parsed.items()}
    cache = e.PointCloudCache(footprints)
    written: list[Path] = []

    for label, bid in PANEL_BUILDINGS.items():
        fig = plt.figure(figsize=(13.6, 9.2))
        gs = fig.add_gridspec(3, 5, height_ratios=[1.05, 1.0, 1.15], hspace=0.23, wspace=0.10)
        for col, kind in enumerate(["rgb", "depth"]):
            ax = fig.add_subplot(gs[0, col])
            ax.imshow(plt.imread(FIG_DIR / f"render_{kind}_{short_id(bid)}.png"))
            ax.set_title(f"corrected-S1 {kind}", fontsize=8)
            ax.set_axis_off()
        ax_note = fig.add_subplot(gs[0, 2:])
        ax_note.text(0.02, 0.76, f"{label}: {short_id(bid)}", fontsize=12, weight="bold")
        ax_note.text(0.02, 0.50, "Rows: corrected render / roof points / facet-distance model", fontsize=9)
        ax_note.text(0.02, 0.29, "Sources: raw_dense | GS-S0 dense | GS-corrected-S1 dense | LiDAR | reference", fontsize=9)
        ax_note.set_axis_off()
        for col, (key, src) in enumerate(panel_srcs):
            ax = fig.add_subplot(gs[1, col])
            pts = reference_sample_points(refs.get(bid, []), e) if key == "reference" else cache.read_roof_points(src, bid)
            e.draw_cloud(ax, pts, footprints[bid], key)
        for col, (key, _src) in enumerate(panel_srcs):
            ax = fig.add_subplot(gs[2, col], projection="3d")
            if key == "reference":
                e.draw_model(ax, refs.get(bid, []), footprints[bid], "reference", f"roof {len(refs.get(bid, []))}")
            else:
                s1.draw_distance_model(ax, pred.get(key, {}).get(bid, []), refs.get(bid, []), footprints[bid], key)
        fig.suptitle(f"corrected-S1 panel {label} {short_id(bid)}", fontsize=13)
        out = FIG_DIR / f"panel_{label}_{short_id(bid)}.png"
        fig.savefig(out, dpi=180)
        plt.close(fig)
        written.append(out)

    fig, axes = plt.subplots(len(PANEL_BUILDINGS), 2, figsize=(6.8, 8.2))
    for row, (label, bid) in enumerate(PANEL_BUILDINGS.items()):
        for col, (src_label, src) in enumerate(before_after_srcs):
            pts = cache.read_roof_points(src, bid)
            e.draw_cloud(axes[row, col], pts, footprints[bid], f"{label} {short_id(bid)}\n{src_label}")
    fig.tight_layout()
    out = FIG_DIR / "corrected_s1_s1_vs_corrected_pointcloud_panel.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)
    written.append(out)
    return written


def build_report(delta: pd.DataFrame, breakdown: pd.DataFrame, target: pd.DataFrame) -> None:
    loss = pd.read_csv(REPO / "docs/experiments/joint-optimization/e5_c001_corrected_s1/tables/e5_c001_corrected_s1_loss.csv")
    density = pd.read_csv(REPO / "docs/experiments/joint-optimization/e5_c001_corrected_s1/tables/e5_c001_corrected_s1_densification.csv")
    summary = pd.read_csv(REPO / "docs/experiments/joint-optimization/e5_c001_corrected_s1/tables/e5_c001_corrected_s1_summary.csv")
    train_fp = pd.read_csv(RUN_DIR / "train_fingerprints.csv")
    issues = pd.read_csv(REPO / "docs/e5_c001_corrected_s1_report_issues.csv") if (REPO / "docs/e5_c001_corrected_s1_report_issues.csv").exists() else pd.DataFrame(columns=["part", "severity", "message", "path"])
    tail = loss[loss["step"] >= 20000].groupby("arm").agg(
        loss_distort_share_median=("loss_distort_share", "median"),
        loss_depth_share_median=("loss_depth_share", "median"),
    ).reset_index()
    density_rows = density.to_dict("records")
    delta_rows = []
    for row in delta.to_dict("records"):
        delta_rows.append({
            "arm": row["arm"],
            "coverage S0/S1/corr": f"{fmt(row['s0_coverage'])}/{fmt(row['s1_coverage'])}/{fmt(row['corrected_coverage'])}",
            "median RMS S0/S1/corr": f"{fmt(row['s0_median_ref_rms_m'])}/{fmt(row['s1_median_ref_rms_m'])}/{fmt(row['corrected_median_ref_rms_m'])}",
            "valid S0/S1/corr": f"{int(row['s0_val3dity_valid'])}/{int(row['s1_val3dity_valid'])}/{int(row['corrected_val3dity_valid'])}",
            "has_lod22 S0/S1/corr": f"{int(row['s0_has_lod22'])}/{int(row['s1_has_lod22'])}/{int(row['corrected_has_lod22'])}",
        })
    base_summary = summary[summary["setting"] == "base"].iloc[0].to_dict()
    voxel_summary = summary[summary["setting"] == "voxel02"].iloc[0].to_dict()

    target_view = []
    for row in target.to_dict("records"):
        if row["route"] not in {"normal", "defect", "textureless_observed"}:
            continue
        target_view.append({
            "route": row["route"],
            "building": short_id(row["building_id"]),
            "raw_dense": fmt(row.get("raw_dense_rms_m")),
            "S1": fmt(row.get("s1_dense_rms_m")),
            "corrected": fmt(row.get("corrected_dense_rms_m")),
            "LiDAR": fmt(row.get("lidar_rms_m")),
        })

    lines = [
        "# E5 C001 corrected-S1 표면 복원 공정 재시험",
        "",
        "> 관찰 자료. 정본 S0 미변경, 판정 0. corrected-S1은 S1의 깨진 표면 모으기 정규화와 prune 작동을 수리한 재학습 3런이다.",
        "",
        "## Step 0 · 표면 모으기 정규화",
        "",
        "- 채택: `distort_normalization=scene_scale_sq`, `distort_norm_denominator=1453.980473`, `w_distort=100`.",
        "- S1 실행본의 `scene_extent_sq` 대비 분모가 93252.6 -> 1453.98로 줄어 distortion 항이 실제 손실에 들어왔다.",
        f"- tail(20k 이후) distortion share 중앙값: {', '.join(f'{r.arm} {r.loss_distort_share_median:.3%}' for r in tail.itertuples())}. 사전 목표 5~15%에는 못 미쳐 `phases/p2-gsjso/docs/issues.md`에 관찰 이슈로 남겼다.",
        f"- 짝 그림: `{rel(FIG_DIR / 'corrected_s1_distort_share.png')}`, `{rel(FIG_DIR / 'corrected_s1_depth_share.png')}`.",
        "",
        "## Step 1 · prune/seed-protect 수리",
        "",
        "- 채택: `seed_protect_until_iter=5000`, `prune_opa=0.05`, `final_prune_opa=0.05`; prune/grow 카운터와 final prune 값을 ckpt/effective config/CSV에 기록.",
        "- 최종 `opacity<0.005` 및 `opacity<0.05`는 세 arm 모두 0으로 떨어졌다. final prune 절대 개수는 sparse 130224, dense 101484, acmp 113040.",
        f"- 짝 그림: `{rel(FIG_DIR / 'corrected_s1_low_opacity_after_final_prune.png')}`, `{rel(FIG_DIR / 'corrected_s1_s1_vs_corrected_pointcloud_panel.png')}`.",
        "",
        md_table(
            [
                {
                    "arm": r["arm"],
                    "final_n": int(r["final_n_gaussians"]),
                    "opacity<0.05": f"{int(r['opacity_lt_005_count'])} ({r['opacity_lt_005_frac']:.3f})",
                    "axis_ratio>10": f"{int(r['axis_ratio_gt10_count'])} ({r['axis_ratio_gt10_frac']:.3f})",
                    "cum_pruned": int(r["cum_pruned"]),
                    "final_pruned": int(r["final_pruned"]),
                }
                for r in density_rows
            ],
            ["arm", "final_n", "opacity<0.05", "axis_ratio>10", "cum_pruned", "final_pruned"],
        ),
        "",
        "## Step 3 · 8-way 관찰",
        "",
        f"- base corrected-S1 요약: has_lod22 {int(base_summary['has_lod22'])}/54, val3dity_valid {int(base_summary['val3dity_valid'])}/54, median ref RMS {base_summary['median_ref_rms_m']:.3f} m, mean post-SOR coverage {base_summary['mean_coverage_post_sor']:.3f}.",
        f"- voxel02 천장 시험: has_lod22 {int(voxel_summary['has_lod22'])}/54, val3dity_valid {int(voxel_summary['val3dity_valid'])}/54, median ref RMS {voxel_summary['median_ref_rms_m']:.3f} m.",
        "- S1 대비 corrected-S1은 저불투명 가우시안은 제거했지만, readout coverage/has_lod22/RMS는 세 arm 모두 퇴행했다. 이는 판정이 아니라 다음 원인 감사 재료다.",
        f"- 짝 그림: `{rel(FIG_DIR / 'corrected_s1_delta_summary.png')}`, `{rel(FIG_DIR / 'corrected_s1_validity_by_arm.png')}`, `{rel(FIG_DIR / 'corrected_s1_route_ref_rms.png')}`, `{rel(FIG_DIR / 'readout/coverage_accuracy_scatter.png')}`.",
        "",
        md_table(delta_rows, ["arm", "coverage S0/S1/corr", "median RMS S0/S1/corr", "valid S0/S1/corr", "has_lod22 S0/S1/corr"]),
        "",
        "## 건물별 표적 관찰",
        "",
        "- 정상/무늬 지붕은 일부 저RMS를 유지하지만 valid-solid와 roof-plane 구성에서 퇴행·무효가 남았다.",
        "- DEFECT 5동은 dense 기준에서 사진측량 수준으로 안정적으로 조여졌다고 보기 어렵다. 60098은 corrected dense 3.557 m로 S1 dense 대비 악화했다.",
        "- 무텍스처-관측 3동은 corrected-S1 성공선에 넣지 않는다. 상태만 기록한다.",
        f"- 짝 그림 패널: `{rel(FIG_DIR / 'panel_normal_4907184.png')}`, `{rel(FIG_DIR / 'panel_defect_60098.png')}`, `{rel(FIG_DIR / 'panel_textureless_observed_8568391.png')}`.",
        "",
        md_table(target_view, ["route", "building", "raw_dense", "S1", "corrected", "LiDAR"], 18),
        "",
        "## CSV 산출",
        "",
        f"- loss: `{rel(REPO / 'docs/experiments/joint-optimization/e5_c001_corrected_s1/tables/e5_c001_corrected_s1_loss.csv')}`",
        f"- densification/prune: `{rel(REPO / 'docs/experiments/joint-optimization/e5_c001_corrected_s1/tables/e5_c001_corrected_s1_densification.csv')}`",
        f"- building 8-way: `{rel(REPO / 'docs/experiments/joint-optimization/e5_c001_corrected_s1/tables/e5_c001_corrected_s1_building_8way.csv')}`",
        f"- validity breakdown: `{rel(REPO / 'docs/experiments/joint-optimization/e5_c001_corrected_s1/tables/e5_c001_corrected_s1_validity_breakdown.csv')}`",
        f"- delta: `{rel(REPO / 'docs/experiments/joint-optimization/e5_c001_corrected_s1/tables/e5_c001_corrected_s1_delta.csv')}`",
        f"- target observations: `{rel(REPO / 'docs/experiments/joint-optimization/e5_c001_corrected_s1/tables/e5_c001_corrected_s1_target_observations.csv')}`",
        "",
        "## 이슈·지문",
        "",
        md_table(issues.to_dict("records"), ["part", "severity", "message", "path"], 20),
        "",
        md_table(
            [
                {
                    "arm": row["arm"],
                    "gpu": row.get("gpu_device", ""),
                    "elapsed_min": row.get("elapsed_min", ""),
                    "seed": row.get("seed", ""),
                    "ckpt_sha256": str(row.get("ckpt_sha256", ""))[:16],
                }
                for row in train_fp.to_dict("records")
            ],
            ["arm", "gpu", "elapsed_min", "seed", "ckpt_sha256"],
        ),
        "",
        f"- train fingerprints: `{rel(RUN_DIR / 'train_fingerprints.csv')}`.",
        f"- readout fingerprints: `{rel(RUN_DIR / 'readout_fingerprints.csv')}`.",
        f"- versions: `{rel(RUN_DIR / 'versions.txt')}`.",
        f"- snapshots: `{rel(SNAP_DIR)}`.",
        "- 재확인: corrected-S1 재학습 3런, 정본 미변경, 판정 0.",
        "",
    ]
    REPORT.write_text("\n".join(lines), encoding="utf-8")


def copy_snapshots(paths: list[Path]) -> None:
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    for path in paths:
        if path.exists() and path.is_file() and path.suffix in {".csv", ".md", ".txt"}:
            (SNAP_DIR / path.name).write_bytes(path.read_bytes())


def run_report(_args: argparse.Namespace) -> None:
    delta, breakdown, target = make_comparison_tables()
    fig_paths = make_summary_figures(delta, breakdown, target)
    panel_paths = make_case_panels()
    build_report(delta, breakdown, target)
    copy_snapshots(
        [
            REPORT,
            REPO / "docs/experiments/joint-optimization/e5_c001_corrected_s1/tables/e5_c001_corrected_s1_delta.csv",
            REPO / "docs/experiments/joint-optimization/e5_c001_corrected_s1/tables/e5_c001_corrected_s1_validity_breakdown.csv",
            REPO / "docs/experiments/joint-optimization/e5_c001_corrected_s1/tables/e5_c001_corrected_s1_target_observations.csv",
            REPO / "docs/e5_c001_corrected_s1_report_issues.csv",
        ]
    )
    print(json.dumps({"report": rel(REPORT), "figures": [rel(p) for p in fig_paths + panel_paths]}, ensure_ascii=False))


def main() -> None:
    os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    render = sub.add_parser("render-snaps")
    render.add_argument("--device", default="cuda")
    sub.add_parser("render-placeholders")
    sub.add_parser("report")
    all_cmd = sub.add_parser("all")
    all_cmd.add_argument("--device", default="cuda")
    args = parser.parse_args()
    if args.cmd == "render-snaps":
        render_snaps(args)
    elif args.cmd == "render-placeholders":
        make_render_placeholders()
        append_issue("render placeholders requested explicitly")
    elif args.cmd == "report":
        run_report(args)
    elif args.cmd == "all":
        render_snaps(args)
        run_report(args)


if __name__ == "__main__":
    main()
