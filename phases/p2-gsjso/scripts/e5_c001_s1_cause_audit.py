#!/usr/bin/env python3
"""E5 C001 S1 cause audit.

Diagnostic-only pass over existing S1 checkpoints, TensorBoard events, readout
outputs, and 8-way tables.  It does not train or change canonical S0/S1
artifacts.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection


REPO = Path(__file__).resolve().parents[3]
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

RUN_ID = "20260708_e5_c001_s1_cause_audit"
RUN_DIR = REPO / "phases/p2-gsjso/runs" / RUN_ID
SNAP_DIR = RUN_DIR / "snapshots"
FIG_DIR = REPO / "docs/figs/e5_c001_s1_audit"
REPORT_PATH = REPO / "docs/experiments/joint-optimization/e5_c001_s1_audit/reports/W_E5_C001_S1원인감사.md"

S1_TRAIN_RUN = REPO / "phases/p2-gsjso/runs/20260708_e5_c001_3b_s1"
S1_RUN_ROOT = REPO / "results/tum_transfer/e5_3b_s1/C001/runs"
S1_P0_RUN = REPO / "phases/p0-audit/runs/e5p_3b_s1_20260708_C001"
S1_READOUT_ROOT = REPO / "results/tum_transfer/e5_3b_s1/C001/readout_ablation"
DATA_ROOT = REPO / "results/tum_transfer/e5_pilot/C001/data_geoidfix_C001_buf20"

LOSS_CSV = REPO / "docs/experiments/joint-optimization/e5_c001_s1_audit/tables/e5_c001_s1_audit_loss.csv"
DENSITY_CSV = REPO / "docs/experiments/joint-optimization/e5_c001_s1_audit/tables/e5_c001_s1_audit_densification.csv"
SERIES_CSV = REPO / "docs/e5_c001_s1_audit_event_series.csv"
A3_CSV = REPO / "docs/experiments/joint-optimization/e5_c001_s1_audit/tables/e5_c001_s1_audit_a3_texture_correlation.csv"
EIGHT_JOINED_CSV = REPO / "docs/experiments/joint-optimization/e5_c001_s1_audit/tables/e5_c001_s1_audit_8way_joined.csv"
ROUTING_CSV = REPO / "docs/experiments/joint-optimization/e5_c001_s1_audit/tables/e5_c001_s1_audit_building_routing.csv"
THRESHOLD_CSV = REPO / "docs/experiments/joint-optimization/e5_c001_s1_audit/tables/e5_c001_s1_audit_threshold_sensitivity.csv"
ISSUES_CSV = REPO / "docs/experiments/joint-optimization/e5_c001_s1_audit/tables/e5_c001_s1_audit_issues.csv"

RECIPE_DOC = REPO / "docs/experiments/joint-optimization/e5_c001_3b_s1/reports/W_③b_레시피설계_레퍼런스기반_20260707.md"
REVIEW_DOC = REPO / "docs/experiments/joint-optimization/e5_c001_3b_s1/reports/W_E5_C001_③b_S1_검수·라우팅_20260708.md"
S1_REPORT = REPO / "docs/experiments/joint-optimization/e5_c001_3b_s1/reports/W_E5_C001_③b_S1_표면복원.md"

S1_RUNS = {
    "sparse": "gs_e5_C001_s1_sparse_r1",
    "dense": "gs_e5_C001_s1_dense_r1",
    "acmp": "gs_e5_C001_s1_acmp_r1",
}
S0_SOURCE_BY_ARM = {"sparse": "gs_sparse_r1", "dense": "gs_dense_r1", "acmp": "gs_acmp_r1"}
S1_SOURCE_BY_ARM = {
    "sparse": "base__gs_e5_C001_s1_sparse_r1",
    "dense": "base__gs_e5_C001_s1_dense_r1",
    "acmp": "base__gs_e5_C001_s1_acmp_r1",
}
LONG_SOURCE_ORDER = [
    "raw_sparse",
    "raw_dense",
    "raw_acmp",
    "gs_s1_sparse",
    "gs_s1_dense",
    "gs_s1_acmp",
    "lidar",
    "reference",
]
PANEL_BUILDINGS = {
    "defect": "DEBY_LOD2_60098",
    "textureless_observed": "DEBY_LOD2_8568391",
    "normal": "DEBY_LOD2_4907184",
}
ROUTING_LABELS = {
    "normal": ["DEBY_LOD2_4907184", "DEBY_LOD2_4908168", "DEBY_LOD2_4907202", "DEBY_LOD2_4907198", "DEBY_LOD2_4907185", "DEBY_LOD2_4908178"],
    "defect": ["DEBY_LOD2_4907188", "DEBY_LOD2_4907194", "DEBY_LOD2_4907195", "DEBY_LOD2_4907186", "DEBY_LOD2_60098"],
    "input_textureless_observed": ["DEBY_LOD2_8568391", "DEBY_LOD2_4907199", "DEBY_LOD2_8568392"],
    "input_low_observed_occluded": ["DEBY_LOD2_108247350", "DEBY_LOD2_108247351"],
    "intrinsic_all_fail": ["DEBY_LOD2_108247349", "DEBY_LOD2_4908179"],
}


def short_id(bid: str) -> str:
    return bid.replace("DEBY_LOD2_", "")


def rel(path: Path | str | None) -> str:
    if path is None:
        return ""
    p = Path(path)
    try:
        return str(p.relative_to(REPO))
    except ValueError:
        return str(p)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def append_issue(rows: list[dict[str, Any]], part: str, severity: str, message: str, path: Path | str | None = None) -> None:
    rows.append({"part": part, "severity": severity, "message": message, "path": rel(path)})


def num(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "na", "null"}:
        return None
    try:
        out = float(text)
    except ValueError:
        return None
    return out if math.isfinite(out) else None


def tf(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def fmt(value: Any, digits: int = 4) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    if isinstance(value, (float, np.floating)):
        v = float(value)
        return f"{v:.{digits}f}" if math.isfinite(v) else ""
    return str(value)


def median(values: list[float]) -> float | None:
    return float(np.median(values)) if values else None


def mean(values: list[float]) -> float | None:
    return float(np.mean(values)) if values else None


def sha256_file(path: Path, block_size: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(block_size), b""):
            h.update(block)
    return h.hexdigest()


def capture(cmd: list[str]) -> str:
    try:
        proc = subprocess.run(cmd, cwd=REPO, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    except FileNotFoundError as exc:
        return f"not_available:{exc.filename}"
    return (proc.stdout or "").strip()


def latest_events(run_dir: Path) -> list[Path]:
    return sorted((run_dir / "tb").glob("events.out.tfevents*"))


def event_stats(args: argparse.Namespace) -> None:
    import torch
    from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

    RUN_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    loss_rows: list[dict[str, Any]] = []
    density_rows: list[dict[str, Any]] = []
    series_rows: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []

    train_fps = {r["run_name"]: r for r in read_csv(S1_TRAIN_RUN / "train_fingerprints.csv")}
    s0_fps = {r["run_name"]: r for r in read_csv(REPO / "phases/p2-gsjso/runs/e5p_train_20260707_C001/train_fingerprints.csv")}
    tags_to_pull = [
        "loss/total",
        "loss/photo",
        "loss/depth",
        "loss/normal",
        "loss/nc",
        "loss/distort",
        "loss/distort_raw",
        "loss_weight/depth",
        "loss_weight/normal",
        "loss_weight/distort",
        "loss/sem",
        "loss/mvc",
        "loss/mutual",
        "loss/structure",
        "stats/n_primitives",
        "stats/elongation_filter_blocked",
        "stats/elongation_axis_ratio_threshold",
        "seed/surviving",
    ]

    for arm, run_name in S1_RUNS.items():
        run_dir = S1_RUN_ROOT / run_name
        event_files = latest_events(run_dir)
        if not event_files:
            append_issue(issues, "A1/A2", "error", "TensorBoard event file missing", run_dir)
            continue
        acc = EventAccumulator(str(run_dir / "tb"), size_guidance={"scalars": 0})
        acc.Reload()
        tags = set(acc.Tags().get("scalars", []))
        scalar: dict[str, list[Any]] = {}
        for tag in tags_to_pull:
            if tag not in tags:
                append_issue(issues, "A1/A2", "warn", f"event scalar tag missing: {tag}", run_dir)
                continue
            scalar[tag] = acc.Scalars(tag)
            for ev in scalar[tag]:
                series_rows.append(
                    {
                        "run_name": run_name,
                        "arm": arm,
                        "tag": tag,
                        "step": ev.step,
                        "value": float(ev.value),
                    }
                )

        def last(tag: str) -> float | None:
            ev = scalar.get(tag, [])
            return float(ev[-1].value) if ev else None

        def med_tail(tag: str, n: int = 100) -> float | None:
            ev = scalar.get(tag, [])
            if not ev:
                return None
            vals = [float(x.value) for x in ev[-n:] if math.isfinite(float(x.value))]
            return median(vals)

        fp = train_fps.get(run_name, {})
        extent = num(fp.get("scene_extent_bbox_m"))
        denom = num(fp.get("distortion_denom"))
        if extent is None and denom is not None:
            extent = math.sqrt(denom)
        w_distort = med_tail("loss_weight/distort") or 100.0
        dist_loss_tail = med_tail("loss/distort")
        dist_raw_tail = med_tail("loss/distort_raw")
        total_tail = med_tail("loss/total")
        weighted_dist_tail = (w_distort * dist_loss_tail) if dist_loss_tail is not None else None
        linear_equiv_weight = (w_distort / extent) if extent and extent > 0 else None
        dist_pct = (100.0 * weighted_dist_tail / total_tail) if weighted_dist_tail is not None and total_tail and total_tail > 0 else None
        depth_weight = med_tail("loss_weight/depth")
        normal_weight = med_tail("loss_weight/normal")
        contrib_depth = (depth_weight * med_tail("loss/depth")) if depth_weight is not None and med_tail("loss/depth") is not None else None
        contrib_normal = (normal_weight * med_tail("loss/normal")) if normal_weight is not None and med_tail("loss/normal") is not None else None
        contrib_nc = 0.05 * med_tail("loss/nc") if med_tail("loss/nc") is not None else None
        contrib_sem = 0.1 * med_tail("loss/sem") if med_tail("loss/sem") is not None else None
        loss_rows.append(
            {
                "run_name": run_name,
                "arm": arm,
                "w_distort": fmt(w_distort),
                "distort_normalization": json.loads((run_dir / "effective_config.json").read_text()).get("distort_normalization", ""),
                "distort_denominator": fmt(denom),
                "scene_extent_bbox_m": fmt(extent),
                "loss_distort_raw_median_tail": fmt(dist_raw_tail, 8),
                "loss_distort_normalized_median_tail": fmt(dist_loss_tail, 10),
                "weighted_distort_median_tail": fmt(weighted_dist_tail, 8),
                "loss_total_median_tail": fmt(total_tail, 8),
                "weighted_distort_pct_of_total_tail": fmt(dist_pct, 6),
                "linear_norm_equiv_weight": fmt(linear_equiv_weight, 6),
                "contrib_photo_tail": fmt(med_tail("loss/photo"), 8),
                "contrib_depth_tail": fmt(contrib_depth, 8),
                "contrib_normal_tail": fmt(contrib_normal, 8),
                "contrib_nc_tail": fmt(contrib_nc, 8),
                "contrib_sem_tail": fmt(contrib_sem, 8),
                "depth_weight_tail": fmt(depth_weight, 6),
                "normal_weight_tail": fmt(normal_weight, 6),
                "event_file_count": len(event_files),
                "event_file_latest": rel(event_files[-1]),
            }
        )

        ckpt = run_dir / "ckpt/final.pt"
        if not ckpt.exists():
            append_issue(issues, "A2", "error", "checkpoint missing", ckpt)
            continue
        payload = torch.load(ckpt, map_location="cpu")
        state = payload.get("state_dict", payload)
        op = torch.sigmoid(state["opacities_raw"].float()).numpy()
        scales = torch.exp(state["log_scales"].float()).numpy()
        inplane = scales[:, :2]
        axis_ratio = np.min(inplane, axis=1) / np.maximum(np.max(inplane, axis=1), 1e-12)
        n_final = int(op.shape[0])
        n_initial = last("stats/n_primitives")
        n_first = None
        if scalar.get("stats/n_primitives"):
            n_first = float(scalar["stats/n_primitives"][0].value)
        density_rows.append(
            {
                "run_name": run_name,
                "arm": arm,
                "n_initial_event": fmt(n_first, 0),
                "n_final_event": fmt(n_initial, 0),
                "n_final_ckpt": n_final,
                "growth_factor_event_first_to_ckpt": fmt((n_final / n_first) if n_first and n_first > 0 else None, 4),
                "s0_r1_final_n": s0_fps.get(f"gs_e5_C001_{arm}_r1", {}).get("final_n", ""),
                "s1_vs_s0_r1_final_n_factor": fmt(
                    (n_final / float(s0_fps[f"gs_e5_C001_{arm}_r1"]["final_n"]))
                    if f"gs_e5_C001_{arm}_r1" in s0_fps and num(s0_fps[f"gs_e5_C001_{arm}_r1"].get("final_n"))
                    else None,
                    4,
                ),
                "opacity_lt_0p005_frac_ckpt": fmt(float(np.mean(op < 0.005)), 6),
                "opacity_lt_0p05_frac_ckpt": fmt(float(np.mean(op < 0.05)), 6),
                "opacity_p05": fmt(float(np.quantile(op, 0.05)), 8),
                "opacity_p50": fmt(float(np.quantile(op, 0.50)), 8),
                "opacity_p95": fmt(float(np.quantile(op, 0.95)), 8),
                "axis_ratio_lt_0p01_frac_ckpt": fmt(float(np.mean(axis_ratio < 0.01)), 6),
                "axis_ratio_lt_0p1_frac_ckpt": fmt(float(np.mean(axis_ratio < 0.1)), 6),
                "axis_ratio_p05": fmt(float(np.quantile(axis_ratio, 0.05)), 8),
                "axis_ratio_p50": fmt(float(np.quantile(axis_ratio, 0.50)), 8),
                "elongation_blocked_median_tail": fmt(med_tail("stats/elongation_filter_blocked"), 1),
                "elongation_blocked_max": fmt(max([float(x.value) for x in scalar.get("stats/elongation_filter_blocked", [])], default=float("nan")), 1),
                "seed_surviving_tail": fmt(med_tail("seed/surviving"), 0),
                "prune_event_count_logged": "",
                "prune_event_count_note": "not logged by current trainer; inferred from final opacity only",
            }
        )
        if "stats/n_pruned" not in tags and "stats/pruned" not in tags:
            append_issue(issues, "A2", "warn", "trainer did not log prune event count; opacity smoking-gun uses final checkpoint", run_dir)

    write_csv(LOSS_CSV, loss_rows)
    write_csv(DENSITY_CSV, density_rows)
    merge_issues(issues)
    plot_loss_and_density(loss_rows, density_rows, series_rows)
    print(json.dumps({"loss": rel(LOSS_CSV), "density": rel(DENSITY_CSV), "event_scalar_rows_read": len(series_rows)}, ensure_ascii=False))


def merge_issues(new_rows: list[dict[str, Any]]) -> None:
    existing = read_csv(ISSUES_CSV) if ISSUES_CSV.exists() and ISSUES_CSV.read_text(encoding="utf-8").strip() else []
    seen = {(r.get("part"), r.get("severity"), r.get("message"), r.get("path")) for r in existing}
    out = list(existing)
    for row in new_rows:
        key = (str(row.get("part", "")), str(row.get("severity", "")), str(row.get("message", "")), str(row.get("path", "")))
        if key not in seen:
            out.append(row)
            seen.add(key)
    write_csv(ISSUES_CSV, out)


def plot_loss_and_density(loss_rows: list[dict[str, Any]], density_rows: list[dict[str, Any]], series_rows: list[dict[str, Any]]) -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    if loss_rows:
        arms = [r["arm"] for r in loss_rows]
        pct = [num(r.get("weighted_distort_pct_of_total_tail")) or 0.0 for r in loss_rows]
        lin = [num(r.get("linear_norm_equiv_weight")) or 0.0 for r in loss_rows]
        fig, axes = plt.subplots(1, 2, figsize=(8.2, 3.2))
        axes[0].bar(arms, pct, color="#3a6ea5")
        axes[0].set_ylabel("weighted distortion / total (%)")
        axes[0].set_title("A1 loss contribution")
        axes[1].bar(arms, lin, color="#9b5de5")
        axes[1].axhline(100, color="0.3", linestyle="--", linewidth=0.8)
        axes[1].set_ylabel("linear-norm equivalent weight")
        axes[1].set_title("100 / scene_extent")
        fig.tight_layout()
        fig.savefig(FIG_DIR / "a1_loss_contribution.png", dpi=180)
        plt.close(fig)
    if density_rows:
        arms = [r["arm"] for r in density_rows]
        growth = [num(r.get("growth_factor_event_first_to_ckpt")) or 0.0 for r in density_rows]
        op05 = [100.0 * (num(r.get("opacity_lt_0p05_frac_ckpt")) or 0.0) for r in density_rows]
        blocked = [num(r.get("elongation_blocked_median_tail")) or 0.0 for r in density_rows]
        fig, axes = plt.subplots(1, 3, figsize=(10.5, 3.2))
        axes[0].bar(arms, growth, color="#2a9d8f")
        axes[0].set_title("N growth")
        axes[0].set_ylabel("final / initial")
        axes[1].bar(arms, op05, color="#e76f51")
        axes[1].set_title("opacity < 0.05")
        axes[1].set_ylabel("% final Gaussians")
        axes[2].bar(arms, blocked, color="#6c757d")
        axes[2].set_title("elongation blocked")
        axes[2].set_ylabel("median tail count")
        fig.tight_layout()
        fig.savefig(FIG_DIR / "a2_gaussian_count_prune.png", dpi=180)
        plt.close(fig)


def render_snaps(args: argparse.Namespace) -> None:
    issues: list[dict[str, Any]] = []
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        import torch
        from PIL import Image
        from src.stage2.dataloader import ColmapDataset
        from src.stage2.renderer import render
        import e5_c001_render_audit as ra
    except Exception as exc:  # noqa: BLE001
        append_issue(issues, "B3", "warn", f"render imports failed: {type(exc).__name__}: {exc}")
        merge_issues(issues)
        return

    device_name = args.device
    if device_name == "cuda" and not torch.cuda.is_available():
        append_issue(issues, "B3", "warn", "CUDA unavailable; GS render snapshots skipped")
        make_render_placeholders()
        merge_issues(issues)
        return
    device = torch.device(device_name)
    try:
        ds = ColmapDataset(root=str(DATA_ROOT), downscale=0.5, load_depth=True, load_normal=True, load_semantic=True)
    except Exception as exc:  # noqa: BLE001
        append_issue(issues, "B3", "warn", f"ColmapDataset load failed: {type(exc).__name__}: {exc}")
        make_render_placeholders()
        merge_issues(issues)
        return

    lowtex = {r["building_id"]: r.get("lowtex_v5_view", "") for r in read_csv(REPO / "docs/experiments/input-and-alignment/lowtex_v5/tables/lowtex_v5.csv")}
    name_to_idx = {fr.name: i for i, fr in enumerate(ds.frames)}
    ckpt = S1_RUN_ROOT / S1_RUNS["dense"] / "ckpt/final.pt"
    try:
        payload = torch.load(ckpt, map_location="cpu")
        model = ra.make_model_from_state(payload["state_dict"], device)
    except Exception as exc:  # noqa: BLE001
        append_issue(issues, "B3", "warn", f"S1 dense checkpoint load failed: {type(exc).__name__}: {exc}", ckpt)
        make_render_placeholders()
        merge_issues(issues)
        return

    for label, bid in PANEL_BUILDINGS.items():
        view_name = lowtex.get(bid, "")
        idx = name_to_idx.get(view_name)
        if idx is None:
            append_issue(issues, "B3", "warn", f"target view not found for {bid}: {view_name}")
            continue
        try:
            batch = ds[idx]
            w2c = batch["w2c"].to(device)
            K = batch["K"].to(device)
            H, W = batch["height"], batch["width"]
            with torch.no_grad():
                out = render(model, w2c, K, W, H, sh_degree=model.active_sh_degree, render_mode="RGB+ED")
            rgb = out["rgb"].detach().cpu().numpy().clip(0, 1)
            depth = out["depth"].detach().cpu().numpy()
            alpha = out["alpha"].detach().cpu().numpy()
            if alpha.ndim == 3:
                alpha = alpha[..., 0]
            rgb_u8 = (rgb * 255).astype(np.uint8)
            if rgb_u8.ndim == 3 and rgb_u8.shape[0] in (3, 4):
                rgb_u8 = np.moveaxis(rgb_u8, 0, -1)
            depth = np.asarray(depth).squeeze()
            valid = np.isfinite(depth) & (depth > 0) & (alpha > 0.5)
            depth_vis = np.zeros(depth.shape, dtype=np.float32)
            if np.any(valid):
                lo, hi = np.quantile(depth[valid], [0.02, 0.98])
                depth_vis = np.clip((depth - lo) / max(hi - lo, 1e-6), 0, 1)
            rgb_path = FIG_DIR / f"render_rgb_{short_id(bid)}.png"
            depth_path = FIG_DIR / f"render_depth_{short_id(bid)}.png"
            Image.fromarray(rgb_u8).save(rgb_path)
            plt.imsave(depth_path, depth_vis, cmap="magma")
        except Exception as exc:  # noqa: BLE001
            append_issue(issues, "B3", "warn", f"render failed for {bid}: {type(exc).__name__}: {exc}")
    make_render_placeholders()
    merge_issues(issues)
    print(json.dumps({"render_dir": rel(FIG_DIR)}, ensure_ascii=False))


def make_render_placeholders() -> None:
    for bid in PANEL_BUILDINGS.values():
        for kind in ["rgb", "depth"]:
            path = FIG_DIR / f"render_{kind}_{short_id(bid)}.png"
            if path.exists():
                continue
            fig, ax = plt.subplots(figsize=(3.2, 2.1))
            ax.text(0.5, 0.5, f"{kind} render\nnot available", ha="center", va="center", fontsize=10)
            ax.set_axis_off()
            fig.tight_layout()
            fig.savefig(path, dpi=160)
            plt.close(fig)


def source_key(row: dict[str, str]) -> str:
    sr = row.get("source_run", "")
    if sr in {"raw_sparse", "raw_dense", "raw_acmp", "lidar", "reference"}:
        return sr
    for arm, s1_sr in S1_SOURCE_BY_ARM.items():
        if sr == s1_sr:
            return f"gs_s1_{arm}"
    return sr


def build_joined_tables() -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    base_rows = read_csv(REPO / "docs/experiments/evaluation/e5_c001_8way/tables/e5_c001_8way_metrics.csv")
    s1_rows = [r for r in read_csv(REPO / "docs/experiments/joint-optimization/e5_c001_3b_s1/tables/e5_c001_3b_s1_metrics.csv") if r.get("setting") == "base"]
    aux = {r["building_id"]: r for r in read_csv(REPO / "docs/experiments/input-and-alignment/population_aux/tables/population_aux_v4.csv")}
    cov_rows = read_csv(REPO / "docs/experiments/joint-optimization/e5_c001_3b_s1/tables/e5_c001_3b_s1_render_readout_coverage.csv")
    cov_by_bid: dict[str, dict[str, list[float]]] = {}
    for row in cov_rows:
        bid = row["building_id"]
        stage = row["stage"]
        cov_by_bid.setdefault(bid, {}).setdefault(stage, []).append(num(row.get("coverage_frac")) or float("nan"))

    source_map = {
        "raw_sparse": ("raw_sparse", "raw sparse"),
        "raw_dense": ("raw_dense", "raw dense"),
        "raw_acmp": ("raw_acmp", "raw acmp"),
        "lidar": ("lidar", "LiDAR"),
        "reference": ("reference", "reference"),
    }
    joined: list[dict[str, Any]] = []
    for row in base_rows + s1_rows:
        key = source_key(row)
        if key not in LONG_SOURCE_ORDER:
            continue
        bid = row["building_id"]
        a = aux.get(bid, {})
        joined.append(
            {
                "building_id": bid,
                "short_id": short_id(bid),
                "source": key,
                "source_run": row.get("source_run", ""),
                "display_label": row.get("display_label", source_map.get(key, ("", key))[1]),
                "has_lod22": row.get("has_lod22", ""),
                "completeness": row.get("completeness", ""),
                "correctness": row.get("correctness", ""),
                "ref_rms_m": row.get("ref_rms_m", ""),
                "roof_planes": row.get("roof_planes", ""),
                "shell_bucket": row.get("shell_bucket", ""),
                "status": row.get("status", ""),
                "texture_lens": row.get("texture_lens", ""),
                "observation_lens": row.get("observation_lens", ""),
                "complexity_lens": row.get("complexity_lens", ""),
                "size_lens": row.get("size_lens", ""),
                "label_lens": row.get("label_lens", ""),
                "n_views_nadir": a.get("n_views_nadir", ""),
                "roof_obs_covered_frac": a.get("roof_obs_covered_frac", ""),
                "roof_lowtex_frac": a.get("roof_lowtex_frac", ""),
                "roof_lowtex_v5": a.get("roof_lowtex_v5", ""),
                "occlusion_frac_approx": a.get("occlusion_frac_approx", ""),
                "recon_score_median": a.get("recon_score_median", ""),
            }
        )
    write_csv(EIGHT_JOINED_CSV, joined)

    rows_by = {(r["building_id"], r["source"]): r for r in joined}
    all_bids = sorted({r["building_id"] for r in joined})
    routing_rows: list[dict[str, Any]] = []
    for bid in all_bids:
        a = aux.get(bid, {})
        category = next((cat for cat, bids in ROUTING_LABELS.items() if bid in bids), "unclassified")
        raw_dense = rows_by.get((bid, "raw_dense"), {})
        raw_acmp = rows_by.get((bid, "raw_acmp"), {})
        lidar = rows_by.get((bid, "lidar"), {})
        s1_vals = [num(rows_by.get((bid, f"gs_s1_{arm}"), {}).get("ref_rms_m")) for arm in ["sparse", "dense", "acmp"]]
        s1_vals = [v for v in s1_vals if v is not None]
        s1_has = [tf(rows_by.get((bid, f"gs_s1_{arm}"), {}).get("has_lod22")) for arm in ["sparse", "dense", "acmp"]]
        raw_dense_rms = num(raw_dense.get("ref_rms_m"))
        raw_acmp_rms = num(raw_acmp.get("ref_rms_m"))
        lidar_rms = num(lidar.get("ref_rms_m"))
        image_doable_3m = (
            (tf(raw_dense.get("has_lod22")) and raw_dense_rms is not None and raw_dense_rms < 3.0)
            or (tf(raw_acmp.get("has_lod22")) and raw_acmp_rms is not None and raw_acmp_rms < 3.0)
        )
        lidar_doable_3m = tf(lidar.get("has_lod22")) and lidar_rms is not None and lidar_rms < 3.0
        render_cov = cov_by_bid.get(bid, {}).get("render_depth_backproj_sample_pre_readout", [])
        post_cov = cov_by_bid.get(bid, {}).get("tsdf_minobs_voxel_post_sor", [])
        routing_rows.append(
            {
                "building_id": bid,
                "short_id": short_id(bid),
                "route_label": category,
                "audit_axis": "quality_diagnostic" if category in {"normal", "defect"} else "generation_limit",
                "raw_dense_rms_m": fmt(raw_dense_rms),
                "raw_acmp_rms_m": fmt(raw_acmp_rms),
                "lidar_rms_m": fmt(lidar_rms),
                "gs_s1_best_rms_m": fmt(min(s1_vals) if s1_vals else None),
                "gs_s1_median_rms_m": fmt(median(s1_vals)),
                "gs_s1_has_lod22_count": sum(s1_has),
                "image_doable_rms_lt_3m": image_doable_3m,
                "lidar_doable_rms_lt_3m": lidar_doable_3m,
                "render_backproj_coverage_median": fmt(median([v for v in render_cov if math.isfinite(v)])),
                "readout_post_sor_coverage_median": fmt(median([v for v in post_cov if math.isfinite(v)])),
                "n_views_nadir": a.get("n_views_nadir", ""),
                "roof_obs_covered_frac": a.get("roof_obs_covered_frac", ""),
                "roof_lowtex_frac": a.get("roof_lowtex_frac", ""),
                "roof_lowtex_v5": a.get("roof_lowtex_v5", ""),
                "occlusion_frac_approx": a.get("occlusion_frac_approx", ""),
                "recon_score_median": a.get("recon_score_median", ""),
            }
        )
    write_csv(ROUTING_CSV, routing_rows)
    threshold_rows = build_threshold_sensitivity(routing_rows)
    write_csv(THRESHOLD_CSV, threshold_rows)
    corr_rows = build_a3_correlation(joined, routing_rows)
    write_csv(A3_CSV, corr_rows)
    return joined, routing_rows, corr_rows


def build_threshold_sensitivity(routing_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for threshold in [2.5, 3.0, 4.0]:
        image_doable_ids = []
        lidar_doable_ids = []
        defect_candidate_ids = []
        for row in routing_rows:
            rd = num(row.get("raw_dense_rms_m"))
            ra = num(row.get("raw_acmp_rms_m"))
            li = num(row.get("lidar_rms_m"))
            gs = num(row.get("gs_s1_best_rms_m"))
            image_doable = (rd is not None and rd < threshold) or (ra is not None and ra < threshold)
            lidar_doable = li is not None and li < threshold
            gs_pass = gs is not None and gs < threshold and int(row.get("gs_s1_has_lod22_count") or 0) > 0
            if image_doable:
                image_doable_ids.append(row["short_id"])
            if lidar_doable:
                lidar_doable_ids.append(row["short_id"])
            if image_doable and not gs_pass:
                defect_candidate_ids.append(row["short_id"])
        out.append(
            {
                "rms_threshold_m": fmt(threshold, 1),
                "image_doable_count": len(image_doable_ids),
                "lidar_doable_count": len(lidar_doable_ids),
                "image_doable_but_gs_s1_not_pass_count": len(defect_candidate_ids),
                "image_doable_ids": ";".join(image_doable_ids),
                "lidar_doable_ids": ";".join(lidar_doable_ids),
                "image_doable_but_gs_s1_not_pass_ids": ";".join(defect_candidate_ids),
            }
        )
    return out


def rankdata(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i + 1
        while j < len(order) and values[order[j]] == values[order[i]]:
            j += 1
        rank = (i + j - 1) / 2.0 + 1.0
        for k in range(i, j):
            ranks[order[k]] = rank
        i = j
    return ranks


def corr(x: list[float], y: list[float], spearman: bool = False) -> float | None:
    if len(x) < 3 or len(y) < 3:
        return None
    xx = rankdata(x) if spearman else x
    yy = rankdata(y) if spearman else y
    a = np.asarray(xx, dtype=float)
    b = np.asarray(yy, dtype=float)
    if float(np.std(a)) <= 1e-12 or float(np.std(b)) <= 1e-12:
        return None
    return float(np.corrcoef(a, b)[0, 1])


def build_a3_correlation(joined: list[dict[str, Any]], routing_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    s0_rows = read_csv(REPO / "docs/experiments/evaluation/e5_c001_8way/tables/e5_c001_8way_metrics.csv")
    s1_rows = [r for r in read_csv(REPO / "docs/experiments/joint-optimization/e5_c001_3b_s1/tables/e5_c001_3b_s1_metrics.csv") if r.get("setting") == "base"]
    aux = {r["building_id"]: r for r in read_csv(REPO / "docs/experiments/input-and-alignment/population_aux/tables/population_aux_v4.csv")}
    cov = {r["building_id"]: r for r in routing_rows}
    rows: list[dict[str, Any]] = []
    for bid in sorted(aux):
        if not bid.startswith("DEBY_LOD2_"):
            continue
        s0 = [
            num(r.get("ref_rms_m"))
            for r in s0_rows
            if r.get("building_id") == bid and r.get("source_run") in set(S0_SOURCE_BY_ARM.values())
        ]
        s1 = [
            num(r.get("ref_rms_m"))
            for r in s1_rows
            if r.get("building_id") == bid and r.get("source_run") in set(S1_SOURCE_BY_ARM.values())
        ]
        s0v = median([v for v in s0 if v is not None])
        s1v = median([v for v in s1 if v is not None])
        if s0v is None or s1v is None:
            continue
        a = aux[bid]
        c = cov.get(bid, {})
        rows.append(
            {
                "building_id": bid,
                "short_id": short_id(bid),
                "delta_rms_s0_minus_s1_m": s0v - s1v,
                "s0_median_gs_r1_rms_m": s0v,
                "s1_median_gs_r1_rms_m": s1v,
                "texture_signal_1_minus_lowtex_frac": (1.0 - (num(a.get("roof_lowtex_frac")) or 0.0)),
                "texture_signal_1_minus_lowtex_v5": (1.0 - (num(a.get("roof_lowtex_v5")) or 0.0)),
                "roof_lowtex_frac": num(a.get("roof_lowtex_frac")),
                "roof_lowtex_v5": num(a.get("roof_lowtex_v5")),
                "roof_obs_covered_frac": num(a.get("roof_obs_covered_frac")),
                "render_backproj_coverage_median": num(c.get("render_backproj_coverage_median")),
                "readout_post_sor_coverage_median": num(c.get("readout_post_sor_coverage_median")),
                "recon_score_median": num(a.get("recon_score_median")),
                "route_label": c.get("route_label", ""),
            }
        )
    proxy_cols = [
        "texture_signal_1_minus_lowtex_frac",
        "texture_signal_1_minus_lowtex_v5",
        "roof_obs_covered_frac",
        "render_backproj_coverage_median",
        "readout_post_sor_coverage_median",
        "recon_score_median",
    ]
    out = []
    for col in proxy_cols:
        pairs = [(num(r.get(col)), num(r.get("delta_rms_s0_minus_s1_m"))) for r in rows]
        pairs = [(x, y) for x, y in pairs if x is not None and y is not None]
        out.append(
            {
                "proxy": col,
                "n": len(pairs),
                "pearson_r": fmt(corr([p[0] for p in pairs], [p[1] for p in pairs], False), 5),
                "spearman_r": fmt(corr([p[0] for p in pairs], [p[1] for p in pairs], True), 5),
                "x_definition": "positive texture/coverage means easier input except lowtex raw columns are inverted",
            }
        )
    write_csv(REPO / "docs/experiments/joint-optimization/e5_c001_s1_audit/tables/e5_c001_s1_audit_a3_building_delta.csv", rows)
    return out


def make_figures(joined: list[dict[str, Any]], routing_rows: list[dict[str, Any]], corr_rows: list[dict[str, Any]]) -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    delta_rows = read_csv(REPO / "docs/experiments/joint-optimization/e5_c001_s1_audit/tables/e5_c001_s1_audit_a3_building_delta.csv")
    if delta_rows:
        x = [num(r.get("texture_signal_1_minus_lowtex_frac")) for r in delta_rows]
        y = [num(r.get("delta_rms_s0_minus_s1_m")) for r in delta_rows]
        c = [num(r.get("render_backproj_coverage_median")) for r in delta_rows]
        fig, ax = plt.subplots(figsize=(6.8, 4.5))
        sc = ax.scatter(
            [v if v is not None else np.nan for v in x],
            [v if v is not None else np.nan for v in y],
            c=[v if v is not None else 0.0 for v in c],
            cmap="viridis",
            s=52,
            edgecolor="k",
            linewidth=0.3,
        )
        for r in delta_rows:
            xv = num(r.get("texture_signal_1_minus_lowtex_frac"))
            yv = num(r.get("delta_rms_s0_minus_s1_m"))
            if xv is None or yv is None:
                continue
            ax.text(xv + 0.006, yv, r["short_id"], fontsize=6)
        ax.axhline(0, color="0.3", linewidth=0.8)
        ax.set_xlabel("texture proxy: 1 - roof_lowtex_frac")
        ax.set_ylabel("Delta RMS S0 - S1 (m)")
        ax.set_title("A3 S1 gain vs texture / render support")
        cb = fig.colorbar(sc, ax=ax)
        cb.set_label("median render coverage")
        fig.tight_layout()
        fig.savefig(FIG_DIR / "a3_delta_rms_texture_scatter.png", dpi=190)
        plt.close(fig)

    by = {(r["building_id"], r["source"]): num(r.get("ref_rms_m")) for r in joined}
    bids = sorted({r["building_id"] for r in joined})
    mat = np.full((len(bids), len(LONG_SOURCE_ORDER)), np.nan)
    for i, bid in enumerate(bids):
        for j, src in enumerate(LONG_SOURCE_ORDER):
            v = by.get((bid, src))
            if v is not None:
                mat[i, j] = min(v, 12.0)
    fig, ax = plt.subplots(figsize=(9.5, 6.2))
    im = ax.imshow(mat, aspect="auto", cmap="magma_r", vmin=0, vmax=12)
    ax.set_xticks(range(len(LONG_SOURCE_ORDER)), LONG_SOURCE_ORDER, rotation=35, ha="right", fontsize=7)
    ax.set_yticks(range(len(bids)), [short_id(b) for b in bids], fontsize=7)
    ax.set_title("B1 8-way ref RMS, S1 GS arms")
    cb = fig.colorbar(im, ax=ax)
    cb.set_label("ref RMS m (clipped at 12)")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "b1_8way_rms_matrix.png", dpi=190)
    plt.close(fig)

    cats = [r["route_label"] for r in routing_rows]
    counts = Counter(cats)
    labels = list(ROUTING_LABELS)
    vals = [counts.get(k, 0) for k in labels]
    fig, ax = plt.subplots(figsize=(8.0, 3.6))
    ax.bar(labels, vals, color=["#4c78a8", "#e45756", "#72b7b2", "#f58518", "#79706e"])
    ax.set_ylabel("buildings")
    ax.set_title("B2 routing cross-tab")
    ax.tick_params(axis="x", rotation=28, labelsize=7)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "b2_routing_crosstab.png", dpi=190)
    plt.close(fig)


def report(args: argparse.Namespace) -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    issues: list[dict[str, Any]] = []
    for required in [RECIPE_DOC, REVIEW_DOC, S1_REPORT]:
        if not required.exists():
            append_issue(issues, "input", "error", "required input doc missing", required)
    joined, routing_rows, corr_rows = build_joined_tables()
    make_figures(joined, routing_rows, corr_rows)
    try:
        make_case_panels()
    except Exception as exc:  # noqa: BLE001
        append_issue(issues, "B3", "warn", f"case panel generation failed: {type(exc).__name__}: {exc}")
    merge_issues(issues)
    snapshot_outputs()
    write_versions()
    write_report()
    print(json.dumps({"report": rel(REPORT_PATH), "fig_dir": rel(FIG_DIR)}, ensure_ascii=False))


def snapshot_outputs() -> None:
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    for path in [LOSS_CSV, DENSITY_CSV, A3_CSV, EIGHT_JOINED_CSV, ROUTING_CSV, THRESHOLD_CSV, ISSUES_CSV, REPO / "docs/experiments/joint-optimization/e5_c001_s1_audit/tables/e5_c001_s1_audit_a3_building_delta.csv"]:
        if path.exists():
            target = SNAP_DIR / path.name
            target.write_bytes(path.read_bytes())


def write_versions() -> None:
    lines = [
        "# E5 C001 S1 cause audit versions",
        f"run_id={RUN_ID}",
        "training=0",
        "canonical_changed=0",
        "verdict=0",
        "figure_root=docs/figs/e5_c001_s1_audit",
        f"git_head={capture(['git', 'rev-parse', 'HEAD'])}",
        f"git_branch={capture(['git', 'branch', '--show-current'])}",
        f"script=phases/p2-gsjso/scripts/e5_c001_s1_cause_audit.py",
    ]
    for path in [RECIPE_DOC, REVIEW_DOC, S1_REPORT, S1_TRAIN_RUN / "train_fingerprints.csv"]:
        lines.append(f"input_sha256 {rel(path)}={sha256_file(path) if path.exists() else 'missing'}")
    for name in S1_RUNS.values():
        ckpt = S1_RUN_ROOT / name / "ckpt/final.pt"
        eff = S1_RUN_ROOT / name / "effective_config.json"
        lines.append(f"ckpt_sha256 {rel(ckpt)}={sha256_file(ckpt) if ckpt.exists() else 'missing'}")
        lines.append(f"effective_config_sha256 {rel(eff)}={sha256_file(eff) if eff.exists() else 'missing'}")
    lines.append(f"docker_images={capture(['docker', 'images', '--format', '{{.Repository}}:{{.Tag}} {{.ID}}'])}")
    (RUN_DIR / "versions.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def md_table(rows: list[dict[str, Any]], fields: list[str], limit: int = 20) -> str:
    if not rows:
        return ""
    view = rows[:limit]
    out = ["|" + "|".join(fields) + "|", "|" + "|".join(["---"] * len(fields)) + "|"]
    for row in view:
        out.append("|" + "|".join(str(row.get(f, "")) for f in fields) + "|")
    if len(rows) > limit:
        out.append("|" + "|".join([f"... {len(rows) - limit} more"] + [""] * (len(fields) - 1)) + "|")
    return "\n".join(out)


def write_report() -> None:
    loss_rows = read_csv(LOSS_CSV) if LOSS_CSV.exists() and LOSS_CSV.read_text(encoding="utf-8").strip() else []
    density_rows = read_csv(DENSITY_CSV) if DENSITY_CSV.exists() and DENSITY_CSV.read_text(encoding="utf-8").strip() else []
    corr_rows = read_csv(A3_CSV) if A3_CSV.exists() and A3_CSV.read_text(encoding="utf-8").strip() else []
    routing_rows = read_csv(ROUTING_CSV) if ROUTING_CSV.exists() and ROUTING_CSV.read_text(encoding="utf-8").strip() else []
    threshold_rows = read_csv(THRESHOLD_CSV) if THRESHOLD_CSV.exists() and THRESHOLD_CSV.read_text(encoding="utf-8").strip() else []
    issues = read_csv(ISSUES_CSV) if ISSUES_CSV.exists() and ISSUES_CSV.read_text(encoding="utf-8").strip() else []

    def minmax(col: str, rows: list[dict[str, str]]) -> str:
        vals = [num(r.get(col)) for r in rows]
        vals = [v for v in vals if v is not None]
        return f"{min(vals):.4g}..{max(vals):.4g}" if vals else ""

    dist_pct = minmax("weighted_distort_pct_of_total_tail", loss_rows)
    linear_w = minmax("linear_norm_equiv_weight", loss_rows)
    op05 = minmax("opacity_lt_0p05_frac_ckpt", density_rows)
    growth = minmax("growth_factor_event_first_to_ckpt", density_rows)
    s1_s0_growth = minmax("s1_vs_s0_r1_final_n_factor", density_rows)
    route_counts = Counter(r.get("route_label", "") for r in routing_rows)
    a3_primary = next((r for r in corr_rows if r.get("proxy") == "texture_signal_1_minus_lowtex_frac"), {})
    lines = [
        "# W_E5_C001 S1 원인 감사",
        "",
        "> 학습 0. 기존 S1 체크포인트, TensorBoard, readout, 8-way 산출 재분석만 수행. 정본 미변경. 판정 0: 아래는 판정이 아니라 관찰 재료다.",
        "",
        "## 입력·경로",
        "",
        f"- 의도 기준: `{rel(RECIPE_DOC)}` §0.5, §2A, §6.",
        f"- 선행 검수: `{rel(REVIEW_DOC)}`.",
        f"- S1 회신: `{rel(S1_REPORT)}`.",
        f"- 그림 root: `{rel(FIG_DIR)}`. 원 발주 표기는 `figs/e5_c001_s1_audit/`였지만, 현재 레포 정리 관례에 맞춰 `docs/figs/` 아래로 고정했다.",
        "",
        "## Part A 판별",
        "",
        "### A1 distortion 적용",
        "",
        f"- 코드식: `src/stage2/train.py`에서 `loss_dist_raw = distort.mean()`, `loss_dist = loss_dist_raw / distort_norm_denominator`, `loss_total += w_distort * loss_dist`.",
        f"- S1 effective config: `scene_extent_sq`, 분모 93252.56728832517 = 305.372833^2, `w_distort=100`.",
        f"- 관찰 한 줄: tail 기준 weighted distortion/total = {dist_pct}%, 선형 정규화 등가 weight = {linear_w}. meter 단위 `rend_dist`라면 현재 제곱분모는 2DGS식 선형 scene-scale 대비 약 305배 약해진 구성으로 해석된다.",
        f"- 표: `{rel(LOSS_CSV)}`. 짝 그림: `{rel(FIG_DIR / 'a1_loss_contribution.png')}`.",
        "",
        md_table(loss_rows, ["arm", "distort_denominator", "loss_distort_raw_median_tail", "weighted_distort_median_tail", "loss_total_median_tail", "weighted_distort_pct_of_total_tail", "linear_norm_equiv_weight"], 8),
        "",
        "### A2 prune·elongation·densification",
        "",
        f"- 로그 확인: `prune_opa=0.05`, seed-protect, elongation filter 메시지는 세 arm 모두 발화. 단 prune event count는 trainer scalar로 기록되지 않아 최종 checkpoint opacity 분포로 폴백했다.",
        f"- 관찰 한 줄: S1/S0(r1) 최종 N = {s1_s0_growth}배, S1 final/initial N = {growth}, 최종 opacity<0.05 비율 = {op05}. `prune_opa=0.05`가 모든 lineage에 강제된 상태라면 0에 가까워야 하므로 seed-protect lineage와 densification 과생성이 prune 효과를 압도했거나 prune audit 계측이 부족한 상태다.",
        f"- 표: `{rel(DENSITY_CSV)}`. 짝 그림: `{rel(FIG_DIR / 'a2_gaussian_count_prune.png')}`.",
        "",
        md_table(density_rows, ["arm", "s0_r1_final_n", "n_final_ckpt", "s1_vs_s0_r1_final_n_factor", "growth_factor_event_first_to_ckpt", "opacity_lt_0p005_frac_ckpt", "opacity_lt_0p05_frac_ckpt", "axis_ratio_lt_0p01_frac_ckpt", "elongation_blocked_median_tail"], 8),
        "",
        "### A3 이득의 texture 의존성",
        "",
        f"- 관찰 한 줄: ΔRMS(S0-S1)와 `1-roof_lowtex_frac`의 Pearson r={a3_primary.get('pearson_r', '')}, Spearman r={a3_primary.get('spearman_r', '')}. per-building MVS roof depth coverage는 건물별 완제품으로 없어서 `population_aux_v4` texture/observation proxy와 render-backprojection coverage로 대체했다.",
        f"- 표: `{rel(A3_CSV)}`, `{rel(REPO / 'docs/experiments/joint-optimization/e5_c001_s1_audit/tables/e5_c001_s1_audit_a3_building_delta.csv')}`. 짝 그림: `{rel(FIG_DIR / 'a3_delta_rms_texture_scatter.png')}`.",
        "",
        md_table(corr_rows, ["proxy", "n", "pearson_r", "spearman_r"], 10),
        "",
        "## Part B 분류-조인 8-way",
        "",
        f"- 전수표: `{rel(EIGHT_JOINED_CSV)}`. 짝 그림: `{rel(FIG_DIR / 'b1_8way_rms_matrix.png')}`.",
        f"- 분류·라우팅표: `{rel(ROUTING_CSV)}`. 짝 그림: `{rel(FIG_DIR / 'b2_routing_crosstab.png')}`.",
        f"- RMS 임계 민감도: `{rel(THRESHOLD_CSV)}`.",
        f"- 라우팅 count: normal={route_counts.get('normal', 0)}, defect={route_counts.get('defect', 0)}, input_textureless_observed={route_counts.get('input_textureless_observed', 0)}, input_low_observed_occluded={route_counts.get('input_low_observed_occluded', 0)}, intrinsic_all_fail={route_counts.get('intrinsic_all_fail', 0)}.",
        "",
        md_table(routing_rows, ["short_id", "route_label", "raw_dense_rms_m", "raw_acmp_rms_m", "lidar_rms_m", "gs_s1_best_rms_m", "gs_s1_has_lod22_count", "render_backproj_coverage_median", "roof_lowtex_v5"], 24),
        "",
        md_table(threshold_rows, ["rms_threshold_m", "image_doable_count", "lidar_doable_count", "image_doable_but_gs_s1_not_pass_count", "image_doable_but_gs_s1_not_pass_ids"], 6),
        "",
        "## B3 정성 패널",
        "",
        f"- DEFECT: `{rel(FIG_DIR / 'panel_defect_60098.png')}`.",
        f"- 입력한계-무텍스처관측됨: `{rel(FIG_DIR / 'panel_textureless_observed_8568391.png')}`.",
        f"- 정상 대조: `{rel(FIG_DIR / 'panel_normal_4907184.png')}`.",
        "",
        "각 패널은 GS-S1 dense의 RGB/depth 렌더, raw_dense | GS-S0 dense | GS-S1 dense | LiDAR | reference 점군/샘플, 그리고 면-거리 색칠 모델을 같은 건물에 대해 나란히 둔다. RGB/depth 렌더를 생성하지 못한 경우 placeholder와 issues에 남긴다.",
        "",
        "## 감사 이슈",
        "",
        md_table(issues, ["part", "severity", "message", "path"], 20),
        "",
        "## 런 지문",
        "",
        f"- versions: `{rel(RUN_DIR / 'versions.txt')}`.",
        f"- snapshots: `{rel(SNAP_DIR)}`.",
        "- 재확인: S1 재학습 0, 정본 미변경, 판정 0.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def make_case_panels() -> None:
    import e5_c001_8way as e
    import e5_c001_3b_s1 as s1
    import pointcloud_attributes_v1 as base

    e.configure_korean_font()
    target_ids = set(PANEL_BUILDINGS.values())
    footprints = base.load_footprints(e.FOOTPRINTS_GPKG, target_ids)
    refs = e.parse_lod2_roofs(e.LOD2_DIR, target_ids)
    base_srcs = {src.source_run: src for src in e.sources()}
    s1_dense = e.Source(
        "gs_s1_dense",
        "gs_s1_dense",
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
        ("gs_s1_dense", s1_dense),
        ("lidar", base_srcs["lidar"]),
        ("reference", base_srcs["reference"]),
    ]
    pred: dict[str, dict[str, list[Any]]] = {}
    for key, src in panel_srcs:
        if key == "reference":
            pred[key] = refs
        else:
            pred[key] = e.parse_cityjson_roofs(src.cityjson_path, target_ids)
    cache = e.PointCloudCache(footprints)

    for label, bid in PANEL_BUILDINGS.items():
        fig = plt.figure(figsize=(13.5, 9.2))
        gs = fig.add_gridspec(3, 5, height_ratios=[1.15, 1.0, 1.15], hspace=0.22, wspace=0.10)
        for col, kind in enumerate(["rgb", "depth"]):
            ax = fig.add_subplot(gs[0, col])
            img = plt.imread(FIG_DIR / f"render_{kind}_{short_id(bid)}.png")
            ax.imshow(img)
            ax.set_title(f"GS-S1 {kind}", fontsize=8)
            ax.set_axis_off()
        ax_note = fig.add_subplot(gs[0, 2:])
        ax_note.text(0.02, 0.75, f"{label}: {short_id(bid)}", fontsize=12, weight="bold")
        ax_note.text(0.02, 0.48, "Rows: render / roof points / facet-distance model", fontsize=9)
        ax_note.text(0.02, 0.26, "Sources: raw_dense | GS-S0 dense | GS-S1 dense | LiDAR | reference", fontsize=9)
        ax_note.set_axis_off()
        for col, (key, src) in enumerate(panel_srcs):
            ax = fig.add_subplot(gs[1, col])
            if key == "reference":
                pts = reference_sample_points(refs.get(bid, []), e)
            else:
                pts = cache.read_roof_points(src, bid)
            e.draw_cloud(ax, pts, footprints[bid], key)
        for col, (key, _src) in enumerate(panel_srcs):
            ax = fig.add_subplot(gs[2, col], projection="3d")
            if key == "reference":
                e.draw_model(ax, refs.get(bid, []), footprints[bid], "reference", f"roof {len(refs.get(bid, []))}")
            else:
                s1.draw_distance_model(ax, pred.get(key, {}).get(bid, []), refs.get(bid, []), footprints[bid], key)
        fig.suptitle(f"S1 audit panel {label} {short_id(bid)}", fontsize=13)
        out = FIG_DIR / f"panel_{label}_{short_id(bid)}.png"
        fig.savefig(out, dpi=180)
        plt.close(fig)


def reference_sample_points(surfaces: list[Any], e_module: Any) -> np.ndarray:
    pts_all = []
    for surf in surfaces:
        pts = e_module.sample_polygon_points(surf.polygon, e_module.SAMPLE_SPACING_M, limit=2500)
        if len(pts) == 0:
            continue
        z = surf.z_at(pts[:, 0], pts[:, 1])
        pts_all.append(np.column_stack([pts[:, 0], pts[:, 1], z]))
    return np.vstack(pts_all) if pts_all else np.empty((0, 3), dtype=float)


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("event-stats")
    r = sub.add_parser("render-snaps")
    r.add_argument("--device", default="cuda")
    p = sub.add_parser("render-placeholders")
    p.add_argument("--message", default="GS render snapshots unavailable in this audit run")
    sub.add_parser("report")
    args = ap.parse_args()
    if args.cmd == "event-stats":
        event_stats(args)
    elif args.cmd == "render-snaps":
        render_snaps(args)
    elif args.cmd == "render-placeholders":
        make_render_placeholders()
        merge_issues([{"part": "B3", "severity": "warn", "message": args.message, "path": ""}])
        print(json.dumps({"render_dir": rel(FIG_DIR), "placeholder": True}, ensure_ascii=False))
    elif args.cmd == "report":
        report(args)


if __name__ == "__main__":
    main()
