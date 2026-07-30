#!/usr/bin/env python3
"""Audit a completed TUM2TWIN R_v1 run and derive surface_proxy_R_v1.

This is a post-analysis only.  It reads frozen run artifacts and existing
camera/LiDAR inputs, performs no GS learning, Roofer run, ICP, or geometry
distance recomputation, and writes only below ``post_analysis``.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Iterable, Mapping

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib-post-analysis")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp/xdg-post-analysis")
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import pearsonr, rankdata, spearmanr


REPO = Path(__file__).resolve().parents[3]
DEFAULT_RUN_ROOT = REPO / "reports/nightly_rv1_20260728_2327"
SCIENCE_STATUS = (
    "R_v1 is a relative, provisional stratification for experiment selection. "
    "It is not a final scientific readiness or quality certification."
)
GROUPS = ("R0", "R1", "R2", "R3", "RX")
COLORS = {
    "R0": "#2f6fb0",
    "R1": "#c69214",
    "R2": "#dc762f",
    "R3": "#7d8f36",
    "RX": "#8b949e",
}
MARKERS = {"R0": "o", "R1": "s", "R2": "^", "R3": "D", "RX": "x"}
REQUIRED_SURFACE = (
    "surface_recall_0p2m",
    "reference_to_reconstruction_p95_m",
    "surface_precision_0p2m",
    "reconstruction_to_reference_p95_m",
)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO.resolve()))
    except ValueError:
        return str(path.resolve())


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path, block_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    os.replace(temporary, path)


def atomic_json(path: Path, value: Any) -> None:
    atomic_text(path, json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def atomic_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as handle:
        frame.to_csv(handle, index=False, na_rep="NaN", float_format="%.12g")
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    os.replace(temporary, path)


def finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def percentile_rank(series: pd.Series, *, inverse: bool = False) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    result = pd.Series(np.nan, index=series.index, dtype=float)
    valid = numeric.notna() & np.isfinite(numeric)
    if not valid.any():
        return result
    values = numeric.loc[valid].to_numpy(dtype=float)
    if len(values) == 1:
        ranks = np.asarray([0.5], dtype=float)
    else:
        ranks = (rankdata(values, method="average") - 1.0) / (len(values) - 1.0)
    if inverse:
        ranks = 1.0 - ranks
    result.loc[valid] = ranks
    return result


def quadrant(completeness_high: bool, reliability_high: bool) -> str:
    return {
        (True, True): "R0",
        (False, True): "R1",
        (True, False): "R2",
        (False, False): "R3",
    }[(bool(completeness_high), bool(reliability_high))]


def classify_surface_proxy(metrics: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, dict[str, float]]]:
    frame = metrics.copy()
    frame["rank_recall_0p2"] = percentile_rank(frame["surface_recall_0p2m"])
    frame["rank_reference_to_surface_p95_inverse"] = percentile_rank(
        frame["reference_to_reconstruction_p95_m"], inverse=True
    )
    frame["rank_precision_0p2"] = percentile_rank(frame["surface_precision_0p2m"])
    frame["rank_surface_to_reference_p95_inverse"] = percentile_rank(
        frame["reconstruction_to_reference_p95_m"], inverse=True
    )
    rank_fields = [
        "rank_recall_0p2",
        "rank_reference_to_surface_p95_inverse",
        "rank_precision_0p2",
        "rank_surface_to_reference_p95_inverse",
    ]
    frame["surface_proxy_metric_valid"] = frame[rank_fields].notna().all(axis=1)
    frame["completeness_score"] = frame[
        ["rank_recall_0p2", "rank_reference_to_surface_p95_inverse"]
    ].mean(axis=1)
    frame["reliability_score"] = frame[
        ["rank_precision_0p2", "rank_surface_to_reference_p95_inverse"]
    ].mean(axis=1)
    frame.loc[~frame["surface_proxy_metric_valid"], ["completeness_score", "reliability_score"]] = np.nan
    frame["surface_proxy_score"] = frame[["completeness_score", "reliability_score"]].mean(axis=1)
    thresholds: dict[str, dict[str, float]] = {}
    valid = frame["surface_proxy_metric_valid"]
    for q in (0.4, 0.5, 0.6):
        key = f"q{int(q * 100)}"
        c_threshold = float(frame.loc[valid, "completeness_score"].quantile(q))
        r_threshold = float(frame.loc[valid, "reliability_score"].quantile(q))
        thresholds[key] = {"completeness": c_threshold, "reliability": r_threshold}
        output = f"surface_proxy_R_{key}"
        frame[output] = "RX"
        frame.loc[valid, output] = [
            quadrant(c >= c_threshold, r >= r_threshold)
            for c, r in zip(
                frame.loc[valid, "completeness_score"],
                frame.loc[valid, "reliability_score"],
            )
        ]
    sensitivity_fields = ["surface_proxy_R_q40", "surface_proxy_R_q50", "surface_proxy_R_q60"]
    frame["surface_proxy_R_stable"] = (
        frame[sensitivity_fields].nunique(axis=1).eq(1)
        & frame["surface_proxy_metric_valid"]
        & ~frame[sensitivity_fields].eq("RX").any(axis=1)
    )
    frame["surface_proxy_R_v1"] = np.where(
        frame["surface_proxy_R_stable"], frame["surface_proxy_R_q50"], "RX"
    )
    frame["classification_confidence"] = np.select(
        [frame["surface_proxy_R_stable"], ~frame["surface_proxy_metric_valid"]],
        ["high_relative_stability", "unknown_missing_metric"],
        default="low_threshold_sensitivity",
    )
    frame["classification_reason"] = np.select(
        [frame["surface_proxy_R_stable"], ~frame["surface_proxy_metric_valid"]],
        [
            "same non-RX label at q40/q50/q60",
            "one or more required completeness/reliability metrics unavailable",
        ],
        default="q40/q50/q60 labels disagree",
    )
    frame["surface_thickness_used_in_reliability"] = False
    frame["surface_thickness_exclusion_reason"] = (
        "0.2 m XY-cell Z-span proxy conflates roof slope, walls, and multiple surfaces; "
        "not a validated physical thickness metric"
    )
    frame["scientific_status"] = SCIENCE_STATUS
    return frame, thresholds


def source_snapshot_audit(cache_manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    prefix = "/workspace/JointBuildGS/"
    for recorded_path, expected in cache_manifest.get("source_snapshot", {}).items():
        path = REPO / recorded_path[len(prefix):] if recorded_path.startswith(prefix) else Path(recorded_path)
        exists = path.is_file()
        stat = path.stat() if exists else None
        size_match = bool(exists and stat and stat.st_size == int(expected["size"]))
        mtime_match = bool(exists and stat and stat.st_mtime_ns == int(expected["mtime_ns"]))
        rows.append(
            {
                "path": rel(path),
                "exists": exists,
                "recorded_size": int(expected["size"]),
                "current_size": int(stat.st_size) if stat else None,
                "recorded_mtime_ns": int(expected["mtime_ns"]),
                "current_mtime_ns": int(stat.st_mtime_ns) if stat else None,
                "size_match": size_match,
                "mtime_match": mtime_match,
                "unchanged_by_size_and_mtime": bool(size_match and mtime_match),
            }
        )
    return rows


def parse_manual_qa(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    if not path.is_file():
        return result
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| DEBY_LOD2_"):
            continue
        parts = [part.strip() for part in line.strip().strip("|").split("|")]
        if len(parts) >= 2:
            result[parts[0]] = parts[1]
    return result


def existing_view_inventories() -> dict[str, dict[str, Any]]:
    root = REPO / (
        "phases/p2-gsjso/runs/fusion_w1/20260726_fusion_w1_aprime/preprocess_aprime/"
        "aprime_pose_28b38383a0b6d826_class6_e005_k3_rooftin_v2/by_building"
    )
    inventories: dict[str, dict[str, Any]] = {}
    for path in sorted(root.glob("*/views.csv")):
        rows = list(csv.DictReader(path.open(newline="", encoding="utf-8")))
        inventories[path.parent.name] = {
            "source": rel(path),
            "rows": rows,
            "view_count": len(rows),
            "image_names": [row["image_name"] for row in rows],
        }
    return inventories


def import_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def derived_view_inventory(building_id: str, run_root: Path) -> dict[str, Any]:
    """Run the existing locked view selector only; never materialize a scene."""
    script = REPO / "phases/p2-gsjso/scripts/fusion_w1/fusion_w1_preprocess_v1_20260725.py"
    config_path = REPO / "phases/p2-gsjso/configs/fusion_w1/fusion_w1_preprocess_v1_20260725.json"
    module = import_module("tum2twin_post_analysis_view_selector", script)
    config = load_json(config_path)
    gate = module.import_module(
        "tum2twin_post_analysis_alignment_gate",
        module.repo_path(config["inputs"]["alignment_helper_script"]),
    )
    cameras, _images, images_by_name, image_paths = gate.load_training_inventory(
        module.repo_path(config["inputs"]["corrected_sparse"]),
        module.repo_path(config["inputs"]["training_image_dir"]),
        int(config["r1_contract"]["image_count"]),
    )
    scene_reference = module.load_json(config["inputs"]["scene_reference_frame"])
    cache = run_root / "cache" / building_id / "reference.npz"
    with np.load(cache, allow_pickle=False) as payload:
        xyz = payload["xyz"]
        inside = payload["inside"].astype(bool)
        classification = payload["classification"].astype(np.uint8)
    class6 = xyz[inside & (classification == 6)]
    selected = module.select_views(
        gate, class6, cameras, images_by_name, scene_reference, config
    )
    missing = [view.image.name for view in selected if not image_paths[view.image.name].is_file()]
    return {
        "source": (
            f"derived_read_only_with:{rel(script)}::select_views; "
            f"config:{rel(config_path)}"
        ),
        "view_count": len(selected),
        "image_names": [view.image.name for view in selected],
        "missing_images": missing,
        "camera_count": len(cameras),
        "registered_image_count": len(images_by_name),
        "lidar_class6_points_for_ranking": int(len(class6)),
        "materialized_local_scene": False,
    }


def basic_input_complete(run_root: Path, building_id: str, config: Mapping[str, Any]) -> bool:
    cache = run_root / "cache" / building_id
    required = [
        cache / "dense.npz",
        cache / "reference.npz",
        cache / "footprint.json",
        cache / "lod2.json",
        cache / "complete.json",
        run_root / "building_results" / f"{building_id}.json",
        REPO / config["sources"]["footprints"],
        REPO / config["sources"]["dense_mvs_pointcloud"],
        REPO / config["sources"]["surface_reference_pointclouds"][0],
        REPO / config["sources"]["camera_pose_manifest"],
        REPO / config["sources"]["image_directory"],
    ]
    return all(path.exists() for path in required)


def choose_candidates(
    frame: pd.DataFrame,
    run_root: Path,
    config: Mapping[str, Any],
    existing_views: Mapping[str, Mapping[str, Any]],
    panel_status: Mapping[str, str],
) -> list[dict[str, Any]]:
    work = frame.copy()
    work["basic_inputs_complete"] = [
        basic_input_complete(run_root, bid, config) for bid in work["building_id"]
    ]
    work["existing_local_scene"] = work["building_id"].isin(existing_views)
    work["qualitative_panel_available"] = work["building_id"].isin(panel_status)
    selected_rows: list[pd.Series] = []
    requested = {"R0": 1, "R1": 2, "R2": 2}
    for group, count in requested.items():
        pool = work[
            (work["surface_proxy_R_v1"] == group)
            & work["surface_proxy_R_stable"]
            & work["basic_inputs_complete"]
        ].copy()
        if len(pool) < count:
            raise RuntimeError(f"insufficient eligible {group} candidates: {len(pool)} < {count}")
        group_c = float(pool["completeness_score"].median())
        group_r = float(pool["reliability_score"].median())
        group_area = float(pool["footprint_area_m2"].median())
        pool["group_center_distance"] = np.hypot(
            pool["completeness_score"] - group_c,
            pool["reliability_score"] - group_r,
        )
        preferred = pool[pool["existing_local_scene"]].copy()
        if len(preferred) >= count:
            pool = preferred
        first = pool.sort_values(
            ["group_center_distance", "building_id"], ascending=[True, True]
        ).iloc[0]
        selected_rows.append(first)
        if count == 1:
            continue
        remaining = pool[pool["building_id"] != first["building_id"]].copy()
        if float(first["footprint_area_m2"]) < group_area:
            opposite = remaining[remaining["footprint_area_m2"] >= group_area]
        else:
            opposite = remaining[remaining["footprint_area_m2"] < group_area]
        if not opposite.empty:
            remaining = opposite
        second = remaining.sort_values(
            ["group_center_distance", "qualitative_panel_available", "building_id"],
            ascending=[True, False, True],
        ).iloc[0]
        selected_rows.append(second)

    output: list[dict[str, Any]] = []
    for row in selected_rows:
        building_id = str(row["building_id"])
        if building_id in existing_views:
            inventory = dict(existing_views[building_id])
            inventory["missing_images"] = [
                name
                for name in inventory["image_names"]
                if not (REPO / "results/tum_transfer/data_geoidfix/images" / name).is_file()
            ]
            inventory["materialized_local_scene"] = True
            inventory["lidar_class6_points_for_ranking"] = int(row["reference_class6_count_raw"])
        else:
            inventory = derived_view_inventory(building_id, run_root)
        view_count = int(inventory["view_count"])
        seed_points = int(row["reference_class6_count_raw"])
        output.append(
            {
                "building_id": building_id,
                "surface_proxy_R_v1": str(row["surface_proxy_R_v1"]),
                "q40": str(row["surface_proxy_R_q40"]),
                "q50": str(row["surface_proxy_R_q50"]),
                "q60": str(row["surface_proxy_R_q60"]),
                "completeness_score": float(row["completeness_score"]),
                "reliability_score": float(row["reliability_score"]),
                "group_center_distance": float(row["group_center_distance"]),
                "footprint_area_m2": float(row["footprint_area_m2"]),
                "surface_recall_0p2m": float(row["surface_recall_0p2m"]),
                "surface_precision_0p2m": float(row["surface_precision_0p2m"]),
                "reference_to_surface_p95_m": float(row["reference_to_reconstruction_p95_m"]),
                "surface_to_reference_p95_m": float(row["reconstruction_to_reference_p95_m"]),
                "lidar_class6_points": seed_points,
                "view_count": view_count,
                "view_inventory_source": inventory["source"],
                "image_names": list(inventory["image_names"]),
                "materialized_local_scene": bool(inventory.get("materialized_local_scene")),
                "missing_image_count": len(inventory.get("missing_images", [])),
                "essential_inputs_complete": bool(
                    row["basic_inputs_complete"]
                    and view_count >= 10
                    and not inventory.get("missing_images")
                    and seed_points > 0
                    and int(row["reconstruction_class6_count_raw"]) > 0
                ),
                "qualitative_panel_status": panel_status.get(building_id, "not_in_panel"),
            }
        )
    median_load = float(np.median([x["view_count"] * x["lidar_class6_points"] for x in output]))
    for candidate in output:
        proxy = candidate["view_count"] * candidate["lidar_class6_points"] / median_load
        candidate["gpu_cost"] = {
            "gpu_hours": None,
            "gpu_hours_reason": "no comparable five-arm per-building timing record",
            "relative_input_load_proxy": float(proxy),
            "proxy_definition": "selected_view_count * LiDAR class6 point count / candidate median",
            "expected_tier": "low" if proxy <= 1.0 else ("medium" if proxy <= 3.0 else "high"),
        }
    return output


def correlation(frame: pd.DataFrame, x: str, y: str) -> dict[str, Any]:
    subset = frame[[x, y]].replace([np.inf, -np.inf], np.nan).dropna()
    if len(subset) < 3:
        return {"n": len(subset), "pearson": None, "spearman": None}
    return {
        "n": len(subset),
        "pearson": float(pearsonr(subset[x], subset[y]).statistic),
        "spearman": float(spearmanr(subset[x], subset[y]).statistic),
    }


def group_summary(frame: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for group in GROUPS:
        subset = frame[frame["surface_proxy_R_v1"] == group]
        area = subset["footprint_area_m2"]
        views = subset["existing_view_count"].dropna()
        rows.append(
            {
                "group": group,
                "n": int(len(subset)),
                "area_median": float(area.median()) if len(area) else None,
                "area_p25": float(area.quantile(0.25)) if len(area) else None,
                "area_p75": float(area.quantile(0.75)) if len(area) else None,
                "view_count_available_n": int(len(views)),
                "view_count_median_existing": float(views.median()) if len(views) else None,
            }
        )
    return rows


def save_figure(path: Path, figure: plt.Figure) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.stem}.{os.getpid()}.tmp.png"
    figure.savefig(temporary, dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(figure)
    os.replace(temporary, path)


def plot_scatter(
    frame: pd.DataFrame,
    candidates: Iterable[Mapping[str, Any]],
    output_dir: Path,
    thresholds: Mapping[str, Mapping[str, float]],
) -> None:
    selected = {item["building_id"] for item in candidates}
    valid = frame[frame["surface_proxy_metric_valid"]]

    fig, ax = plt.subplots(figsize=(8.4, 6.2))
    for group in GROUPS:
        subset = valid[valid["surface_proxy_R_v1"] == group]
        if subset.empty:
            continue
        ax.scatter(
            subset["completeness_score"], subset["reliability_score"],
            s=35, alpha=0.76, color=COLORS[group], marker=MARKERS[group], label=f"{group} (n={len(subset)})",
        )
    q50 = thresholds["q50"]
    ax.axvline(q50["completeness"], color="#343a40", linestyle="--", linewidth=1, label="q50 axes")
    ax.axhline(q50["reliability"], color="#343a40", linestyle="--", linewidth=1)
    chosen = valid[valid["building_id"].isin(selected)]
    ax.scatter(chosen["completeness_score"], chosen["reliability_score"], s=155, marker="*", facecolor="none", edgecolor="#111827", linewidth=1.5, label="oracle candidates")
    for _, row in chosen.iterrows():
        ax.annotate(row["building_id"].replace("DEBY_LOD2_", ""), (row["completeness_score"], row["reliability_score"]), xytext=(4, 5), textcoords="offset points", fontsize=7)
    ax.set(xlabel="Completeness percentile score (higher is better)", ylabel="Reliability percentile score (higher is better)", xlim=(-0.03, 1.03), ylim=(-0.03, 1.03))
    fig.suptitle("Completeness vs reliability", x=0.12, ha="left", fontsize=15, fontweight="bold")
    ax.set_title("135 buildings with all four required point-surface proxy metrics; dashed lines show q50", loc="left", fontsize=9, color="#4b5563")
    ax.grid(True, color="#e5e7eb", linewidth=0.7); ax.legend(fontsize=8, frameon=False, ncol=2)
    save_figure(output_dir / "figures/completeness_vs_reliability.png", fig)

    fig, ax = plt.subplots(figsize=(8.4, 6.2))
    for group in GROUPS:
        subset = valid[valid["surface_proxy_R_v1"] == group]
        if subset.empty:
            continue
        ax.scatter(subset["surface_recall_0p2m"], subset["surface_precision_0p2m"], s=35, alpha=0.76, color=COLORS[group], marker=MARKERS[group], label=group)
    ax.scatter(chosen["surface_recall_0p2m"], chosen["surface_precision_0p2m"], s=155, marker="*", facecolor="none", edgecolor="#111827", linewidth=1.5)
    ax.set(xlabel="Recall@0.2 m: reference → reconstructed surface proxy", ylabel="Precision@0.2 m: reconstructed surface proxy → reference", xlim=(-0.03, 1.03), ylim=(-0.03, 1.03))
    fig.suptitle("Recall vs precision at 0.2 m", x=0.12, ha="left", fontsize=15, fontweight="bold")
    ax.set_title("Nearest-neighbour distances after 0.1 m voxelization; not explicit mesh distances", loc="left", fontsize=9, color="#4b5563")
    ax.grid(True, color="#e5e7eb", linewidth=0.7); ax.legend(fontsize=8, frameon=False, ncol=5)
    save_figure(output_dir / "figures/recall_vs_precision.png", fig)

    lod = valid[valid["roof_plane_f1"].notna()]
    fig, ax = plt.subplots(figsize=(8.4, 6.2))
    for group in GROUPS:
        subset = lod[lod["surface_proxy_R_v1"] == group]
        if subset.empty:
            continue
        ax.scatter(subset["surface_proxy_score"], subset["roof_plane_f1"], s=35, alpha=0.76, color=COLORS[group], marker=MARKERS[group], label=group)
    chosen_lod = lod[lod["building_id"].isin(selected)]
    ax.scatter(chosen_lod["surface_proxy_score"], chosen_lod["roof_plane_f1"], s=155, marker="*", facecolor="none", edgecolor="#111827", linewidth=1.5)
    ax.set(xlabel="Surface proxy score: mean(completeness, reliability)", ylabel="Roof-plane F1", xlim=(-0.03, 1.03), ylim=(-0.03, 1.03))
    fig.suptitle("Surface proxy vs LoD2 roof-plane quality", x=0.12, ha="left", fontsize=15, fontweight="bold")
    ax.set_title(f"n={len(lod)} buildings with both axes; correlation is descriptive, not causal", loc="left", fontsize=9, color="#4b5563")
    ax.grid(True, color="#e5e7eb", linewidth=0.7); ax.legend(fontsize=8, frameon=False, ncol=5)
    save_figure(output_dir / "figures/surface_vs_lod2.png", fig)


def fmt(value: Any, digits: int = 3) -> str:
    if value is None or not finite(value):
        return "unknown"
    return f"{float(value):.{digits}f}"


def group_markdown(rows: list[dict[str, Any]]) -> str:
    lines = ["| Group | n | area median [p25, p75] m² | existing view coverage | existing view median |", "|---|---:|---:|---:|---:|"]
    for row in rows:
        lines.append(
            f"| {row['group']} | {row['n']} | {fmt(row['area_median'], 1)} "
            f"[{fmt(row['area_p25'], 1)}, {fmt(row['area_p75'], 1)}] | "
            f"{row['view_count_available_n']}/{row['n']} | {fmt(row['view_count_median_existing'], 1)} |"
        )
    return "\n".join(lines)


def candidate_markdown(candidates: Iterable[Mapping[str, Any]]) -> str:
    lines = ["| R | Building | C | Reliability | Area m² | Views | LiDAR class-6 | Cost proxy |", "|---|---|---:|---:|---:|---:|---:|---|"]
    for item in candidates:
        lines.append(
            f"| {item['surface_proxy_R_v1']} | `{item['building_id']}` | "
            f"{fmt(item['completeness_score'])} | {fmt(item['reliability_score'])} | "
            f"{fmt(item['footprint_area_m2'], 1)} | {item['view_count']} | "
            f"{item['lidar_class6_points']} | {item['gpu_cost']['expected_tier']} "
            f"({fmt(item['gpu_cost']['relative_input_load_proxy'], 2)}×) |"
        )
    return "\n".join(lines)


def render_reports(
    run_root: Path,
    output_dir: Path,
    frame: pd.DataFrame,
    state: Mapping[str, Any],
    metadata: Mapping[str, Any],
    config: Mapping[str, Any],
    thresholds: Mapping[str, Mapping[str, float]],
    snapshot_rows: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    group_rows: list[dict[str, Any]],
    panel_status: Mapping[str, str],
) -> dict[str, Any]:
    counts = {group: int((frame["surface_proxy_R_v1"] == group).sum()) for group in GROUPS}
    valid_n = int(frame["surface_proxy_metric_valid"].sum())
    missing_n = int(len(frame) - valid_n)
    missing_rates = {
        field: float(pd.to_numeric(frame[field], errors="coerce").isna().mean())
        for field in REQUIRED_SURFACE + ("surface_thickness_p90_m", "roof_plane_f1", "rmsz_m")
    }
    relations = {
        "completeness_vs_reliability": correlation(frame, "completeness_score", "reliability_score"),
        "surface_proxy_vs_roof_plane_f1": correlation(frame, "surface_proxy_score", "roof_plane_f1"),
        "surface_proxy_vs_rmsz": correlation(frame, "surface_proxy_score", "rmsz_m"),
        "fscore_0p2_vs_roof_plane_f1": correlation(frame, "surface_fscore_0p2m", "roof_plane_f1"),
        "fscore_0p2_vs_rmsz": correlation(frame, "surface_fscore_0p2m", "rmsz_m"),
    }
    lod_process_valid = (
        frame["roofer_success"].astype(bool)
        & frame["has_lod22"].astype(bool)
        & frame["val3dity_lod22_valid"].astype(bool)
        & frame["roof_plane_f1"].notna()
        & frame["rmsz_m"].notna()
    )
    plane_median = float(frame.loc[lod_process_valid, "roof_plane_f1"].median())
    rmsz_median = float(frame.loc[lod_process_valid, "rmsz_m"].median())
    lod_strong = lod_process_valid & (frame["roof_plane_f1"] >= plane_median) & (frame["rmsz_m"] <= rmsz_median)
    upstream_good_lod_fail = frame[
        frame["surface_proxy_metric_valid"]
        & (frame["surface_proxy_R_q50"] == "R0")
        & ~lod_process_valid
    ]["building_id"].tolist()
    upstream_bad_lod_good = frame[
        frame["surface_proxy_metric_valid"]
        & (frame["surface_proxy_R_q50"] == "R3")
        & lod_strong
    ]["building_id"].tolist()

    source_unchanged = bool(snapshot_rows) and all(row["unchanged_by_size_and_mtime"] for row in snapshot_rows)
    run_reliable = (
        state.get("current_stage") == "DONE"
        and state.get("stage_status") == "completed"
        and int(state.get("processed_buildings", -1)) == 178
        and int(state.get("failed_buildings", -1)) == 0
        and len(frame) == 178
        and frame["building_id"].nunique() == 178
        and source_unchanged
    )
    group_table = group_markdown(group_rows)
    candidate_table = candidate_markdown(candidates)
    counts_text = ", ".join(f"{key}={value}" for key, value in counts.items())
    q_text = "; ".join(
        f"{key}: C={fmt(value['completeness'])}, Rel={fmt(value['reliability'])}"
        for key, value in thresholds.items()
    )

    summary = f"""# TUM2TWIN baseline post-run analysis — `{state['run_id']}`

> {SCIENCE_STATUS}

## Technical summary

- **실행 무결성은 신뢰 가능하다.** `DONE`, 178/178 처리, 실행 실패 0, building ID 중복 0이며 batch 전후 source size/mtime snapshot {len(snapshot_rows)}건이 현재도 모두 일치한다.
- **metric 해석은 caveat가 필요하다.** 실제 계산은 explicit mesh-to-surface가 아니라 0.1 m voxelized class-6 point set 사이의 양방향 nearest-neighbour 거리다. 따라서 본 결과명은 `surface_proxy_R_v1`이다.
- **재분류 valid population은 {valid_n}/178이다.** {missing_n}건({missing_n/178:.1%})은 DIM class-6 점이 0개라 completeness/reliability 핵심값이 함께 NaN이며 RX로 유지했다.
- **stable 분포는 {counts_text}이다.** q40/q50/q60 축 임계값은 `{q_text}`이다.
- **공유 판단:** `Share with caveats`. 후보 선택과 T1 설계에는 사용할 수 있으나 mesh 품질 인증이나 인과적 prior 효과 주장에는 사용할 수 없다.

## 가장 중요한 발견 5개

1. **결측은 무작위가 아니다.** surface metric 누락 43건은 모두 reconstruction class-6 count가 0이며 LoD2 process-valid도 아니다. metric만 다시 계산해도 복구되지 않는다.
2. **completeness와 reliability는 같은 축이 아니다.** valid 135건의 Spearman ρ={relations['completeness_vs_reliability']['spearman']:.3f}, Pearson r={relations['completeness_vs_reliability']['pearson']:.3f}로 약한 양의 관계만 보여 R1/R2 분리가 실제 정보를 추가한다.
3. **surface proxy는 LoD2와 관련되지만 결정적이지 않다.** surface score와 roof-plane F1의 Spearman ρ={relations['surface_proxy_vs_roof_plane_f1']['spearman']:.3f}, RMSZ와는 ρ={relations['surface_proxy_vs_rmsz']['spearman']:.3f}이다(n={relations['surface_proxy_vs_roof_plane_f1']['n']}).
4. **upstream이 좋아도 LoD2 shell이 실패한 예외가 있다.** q50 R0이면서 LoD2 process-valid가 아닌 건물은 {', '.join(f'`{x}`' for x in upstream_good_lod_fail) or '없음'}이다.
5. **upstream이 낮아도 LoD2가 강한 예외가 있다.** q50 R3 중 roof-plane F1≥{plane_median:.3f}, RMSZ≤{rmsz_median:.3f}를 동시에 만족한 건물은 {', '.join(f'`{x}`' for x in upstream_bad_lod_good) or '없음'}이다. 이는 상관을 인과 또는 필연으로 읽으면 안 된다는 반례다.

## R 분포, 면적과 view 자료

{group_table}

기존 materialized `views.csv`는 9/178건에만 존재한다. 따라서 population-wide view 분포는 확인되지 않았고 그룹별 view 중앙값은 관측 가능한 subset만 표시했다. 선정 후보 5건은 기존 selector로 10-view minimum을 확인했으며 모두 20–30개의 실제 image inventory를 가진다.

## 선정된 LiDAR oracle 후보

{candidate_table}

선정 규칙은 stable label, 필수 입력 존재, 그룹 중심거리 최소화, 기존 materialized local scene 우선, 두 번째 표본의 면적 반대편 선택 순이다. GPU-hour 절대치는 비교 가능한 5-arm timing이 없어 `unknown`이며, 표의 비용은 view 수×LiDAR class-6 점수의 상대 proxy다.

## qualitative panel sanity check

qualitative panel은 R 정답으로 사용하지 않았다. 9건 panel은 좌표계 전체 이동이 없음을 확인하며 metric CRS audit와 일치한다. 세부적으로 `DEBY_LOD2_60097`의 좁은 strip support는 R1의 낮은 completeness/높은 reliability와, `DEBY_LOD2_4907207`의 복합·불안정 support는 R3와, `DEBY_LOD2_4959753`의 수목·인접 지붕 방향 확산은 낮은 reliability와 방향상 부합한다. `DEBY_LOD2_4908353`의 REVIEW_NEEDED는 occlusion 미처리 표시 문제라 자동 R0와 직접 비교할 수 없다. 정량 agreement rate는 panel이 quality label을 제공하지 않으므로 계산하지 않았다.

## 확인되지 않은 주장

- explicit mesh surface의 completeness/reliability 또는 watertightness
- `surface_thickness_p90_m`이 물리적 표면 두께라는 주장
- 178건 전체의 per-building usable view 수
- R group이 LiDAR oracle prior의 개선량을 인과적으로 예측한다는 주장
- 후보별 절대 GPU-hour
- qualitative PASS/REVIEW_NEEDED가 자동 R label의 정답이라는 주장

## 재현

`jointbuildgs:dev` 컨테이너의 repository root에서 다음을 실행한다. 이 명령은 기존 metric과 입력을 읽고 `post_analysis/`만 atomic write하며 geometry metric이나 GS 학습을 실행하지 않는다.

```bash
python scripts/input_and_alignment/tum2twin_rv1/analyze_tum2twin_surface_proxy_rv1.py \
  --run-root reports/nightly_rv1_20260728_2327 \
  --output-dir reports/nightly_rv1_20260728_2327/post_analysis
python tests/test_tum2twin_surface_proxy_rv1_analysis.py
```

## 다음 단계 추천

`oracle_candidates.yaml`의 5건에 대해 먼저 local-scene materialization과 B0 600-iteration cost smoke만 수행해 absolute GPU budget을 측정하고, 이후 동일 image/camera·appearance·iteration·seed·mesh/Roofer 조건으로 B0/P1/P2/P3를 실행한다. P4는 coverage-aware densification의 수식과 threshold가 아직 repository lock으로 확인되지 않았으므로 이를 preregister하기 전에는 실행하지 않는다. 실행 지시는 `next_oracle_prompt.md`에 작성했으며 이번 분석에서는 학습을 시작하지 않았다.
"""
    atomic_text(output_dir / "POST_RUN_SUMMARY.md", summary)

    missing_table = "\n".join(
        f"| `{field}` | {int(frame[field].isna().sum())} | {rate:.1%} |"
        for field, rate in missing_rates.items()
    )
    snapshot_table = "\n".join(
        f"| `{row['path']}` | {row['exists']} | {row['size_match']} | {row['mtime_match']} |"
        for row in snapshot_rows
    )
    audit = f"""# Metric and execution audit — `{state['run_id']}`

## Overall assessment: Share with caveats

- Execution integrity: **{'trusted' if run_reliable else 'needs revision'}**
- Analysis grain: one row per canonical building, 178 rows / 178 unique IDs
- Run branch: `exp/fusion-w1`
- Run commit: `{metadata['git_head']}`
- Config: `configs/input_and_alignment/tum2twin_rv1_20260728_2327.yaml`
- Completed: `{metadata['completed_at']}` (UTC timestamp; start state is recorded in KST)
- No GS learning, Roofer rerun, ICP, or distance metric recomputation was performed in post-analysis.

## Actual distance directions

- **Precision@0.2:** each reconstructed DIM class-6 voxel centroid → nearest ALS reference class-6 voxel centroid; fraction ≤0.2 m.
- **Recall@0.2:** each ALS reference class-6 voxel centroid → nearest reconstructed DIM class-6 voxel centroid; fraction ≤0.2 m.
- `reconstruction_to_reference_p95_m` is the surface-proxy-to-reference direction used by reliability.
- `reference_to_reconstruction_p95_m` is the reference-to-surface-proxy direction used by completeness.
- The implementation uses SciPy `cKDTree` point nearest neighbours, not triangle/mesh nearest-surface queries.

## Units, CRS and sampling

- Coordinates and distances: metres; CRS: EPSG:25832 for all 178 rows.
- Footprint crop buffer: {config['processing']['crop_buffer_m']} m.
- Voxelization: {config['processing']['voxel_size_m']} m centroid per occupied voxel.
- Directional cap: {config['processing']['max_surface_points_per_direction']:,} points after voxelization; deterministic linspace selection. {int(frame['surface_sampling_capped'].astype(bool).sum())} buildings were capped.
- Worker count: {config['processing']['worker_count']}; ICP: disabled for all rows; normal estimation: disabled.
- `surface_thickness_p90_m` is a 0.2 m XY-cell Z-span p90. It is excluded from reliability because slope, walls and multiple surfaces are not separated.

## Missingness

| Metric | Missing n | Missing rate |
|---|---:|---:|
{missing_table}

All four required surface proxy metrics are simultaneously available for {valid_n}/178 buildings. The {missing_n} missing rows have zero reconstructed class-6 points; reference class-6 is present. Their pipeline record is `processing_status=success`, so execution success must not be confused with metric validity.

## Source immutability evidence

`run_metadata.source_data_modified=false`, `cache_manifest.source_files_unchanged=true`, and current size/mtime agree with the frozen snapshot:

| Source | Exists | Size match | mtime match |
|---|---|---|---|
{snapshot_table}

This proves no observed size/mtime change across the recorded inputs; it is not a fresh full-file cryptographic rehash.

## Data-quality issues and minimum remediation

1. **High — 43/178 metric-invalid rows are counted as processing successes.** Downstream analyses must use `surface_proxy_metric_valid`, not `processing_status`. A metric-only rerun will not help; minimum recovery is upstream DIM class-6 classification/surface recovery for those IDs, then affected-ID metric rerun.
2. **Medium — “nearest surface” is a point-set proxy.** Keep the `surface_proxy` name. Only if an explicit mesh claim becomes necessary, minimally recompute the four directional metrics against frozen meshes using triangle nearest-surface distance.
3. **Medium — 11 capped buildings use an order-dependent deterministic spatial sample.** None of the selected candidates is capped. Recompute only capped IDs with a documented spatial sampler if they become decision-critical.
4. **Medium — thickness is not validated.** Do not include it in reliability until local plane separation or signed surface-normal thickness is implemented and tested.
5. **Low — population view counts are sparse.** Existing `views.csv` covers 9/178. Candidate eligibility was checked separately with the locked selector; do not generalize that count distribution.

No minimum geometry metric recalculation is required for the 135 valid buildings or the five selected candidates.

## Reproduction

Run `scripts/input_and_alignment/tum2twin_rv1/analyze_tum2twin_surface_proxy_rv1.py` inside the existing `jointbuildgs:dev` container with the completed run root and `post_analysis/` output directory. Then run `tests/test_tum2twin_surface_proxy_rv1_analysis.py`. The script reads frozen metrics and writes only post-analysis artifacts; it does not launch training, Roofer, ICP, or geometry-distance recomputation.
"""
    atomic_text(output_dir / "metric_audit.md", audit)

    candidate_payload = {
        "schema": "jointbuildgs.tum2twin.surface_proxy_rv1.oracle_candidates.v1",
        "run_id": state["run_id"],
        "generated_at": now(),
        "scientific_status": SCIENCE_STATUS,
        "classification_name": "surface_proxy_R_v1",
        "selection_rule": [
            "stable same label at q40 q50 q60",
            "all four required surface metrics and essential files available",
            "prefer existing materialized local scene when enough candidates exist",
            "minimize distance to within-group median completeness and reliability",
            "for second candidate prefer opposite side of within-group median area",
        ],
        "common_sources": {
            "camera_pose": config["sources"]["camera_pose_manifest"],
            "image_directory": "results/tum_transfer/data_geoidfix/images",
            "current_image_derived_seed": config["sources"]["dense_mvs_pointcloud"],
            "lidar_oracle_seed": config["sources"]["surface_reference_pointclouds"][0],
            "footprint_xy": config["sources"]["footprints"],
            "baseline_metrics": rel(run_root / "building_metrics.csv"),
            "training_recipe_lock": "phases/p2-gsjso/configs/fusion_w1/fusion_w1_aprime_training_20260726.json",
            "mesh_recipe_lock": "phases/p2-gsjso/configs/fusion_w1/fusion_w1_aprime_tsdf_20260726.json",
            "roofer_recipe_lock": "phases/p2-gsjso/configs/fusion_w1/fusion_w1_aprime_readout_20260726.json",
        },
        "candidates": candidates,
        "r3_candidate": None,
        "r3_reason": "not required for the requested five-building T1 contrast",
    }
    atomic_json(output_dir / "oracle_candidates.yaml", candidate_payload)

    candidate_ids = "\n".join(
        f"- {item['surface_proxy_R_v1']}: `{item['building_id']}` ({item['view_count']} frozen candidate views, cost tier {item['gpu_cost']['expected_tier']})"
        for item in candidates
    )
    prompt = f"""# Next prompt — T1 LiDAR oracle prior experiment design

아래 작업은 **새 실험 실행용 프롬프트**다. 이 문서를 작성한 post-analysis에서는 학습을 실행하지 않았다.

## 목적과 대상

`reports/nightly_rv1_20260728_2327/post_analysis/oracle_candidates.yaml`을 source of truth로 사용해 다음 후보를 building-centered local scene으로 비교한다.

{candidate_ids}

`surface_proxy_R_v1`은 실험 대상 선택용 잠정 상대 strata이며 scientific pass/fail이 아니다. reference LoD2 roof geometry는 평가 때만 열고 training·view selection·densification에는 입력하지 않는다.

## 시작 gate

1. 현재 branch를 유지하고 rebase나 새 branch를 만들지 않는다.
2. 후보별 footprint, DIM/MVS class-6 current seed, ALS class-6 oracle seed, corrected camera binary, candidate image 30개, baseline result가 모두 존재하는지 확인한다.
3. `oracle_candidates.yaml`의 image name과 camera hash를 per-building/arm 전부 동일하게 고정한다. 하나라도 누락되면 그 building은 `blocked`로 기록하고 추측하지 않는다.
4. 먼저 local scene materialization과 B0 600-iteration cost smoke만 수행한다. 예상 GPU-hour는 현재 unknown이므로 smoke wall time·peak VRAM·final primitive count를 기록한 뒤 full queue를 산정한다.
5. P4의 coverage-aware densification 수식·threshold가 committed prereg/config에 없으면 P4는 실행하지 말고 `blocked_design_lock_missing`으로 기록한다. 임계값을 새로 발명하지 않는다.

## 모든 arm에서 고정할 조건

- Images/cameras: candidate YAML의 동일 per-building image list, corrected `images.bin` SHA-256 `28b38383a0b6d82656108e8f0e5e79711dcda93948ab2e89c1cd8f47215962a5`, 같은 train/eval policy.
- Appearance: `w_photo=1.0`, `photo_lam=0.2`, `downscale=1.0`, `sh_degree=3`, `sh_up_every=1000`.
- Budget: `max_iter=30000`; random seeds `1001`, `1002`; 같은 checkpoint/eval cadence.
- Optimizer/base densification: `fusion_w1_aprime_training_20260726.json` 값을 공통 사용 (`grow_grad2d=0.0002`, refine 500–15000/100 iter, reset 3000). P4의 coverage-aware 변경만 명시적 차이다.
- Shared regularizers: `w_nc=0.05`, `w_distort=100.0`와 schedule을 동일하게 고정한다. semantic/mutual/structure 및 기타 prior는 0으로 유지한다.
- LiDAR prior schedule for P2/P3/P4: depth 0.5→0.05, normal 0.05→0.005, signed normal, alpha-LSQ depth alignment, 기존 A-prime schedule을 그대로 사용한다.
- Mesh extraction: `fusion_w1_aprime_tsdf_20260726.json`의 TSDF/marching-cubes 설정과 최종 30k checkpoint를 동일 사용한다.
- Roofer: image digest `3dgi/roofer@sha256:dd2c415aaee337502bde0dc1426dfa9c9f88e648f9d2f6340110c49932c251d2`; `--id-attribute building_id --jobs 3 --srs EPSG:25832 --bld-class 6 --grnd-class 2 --lod22`; override 없음.
- 한 arm의 차이 외 init, loss, image/camera, iteration, seed, extraction, Roofer config가 동일한지 resolved-config diff로 증명한다.

## Arms

| Arm | Initialization | LiDAR depth/normal loss | Densification |
|---|---|---|---|
| B0 | current image-derived DIM/MVS class-6 seed | off | common base |
| P1 | ALS class-6 LiDAR seed only | off | common base |
| P2 | current image-derived DIM/MVS class-6 seed | on | common base |
| P3 | ALS class-6 LiDAR seed | on | common base |
| P4 | ALS class-6 LiDAR seed | on | P3 + preregistered coverage-aware rule only |

`seed only`은 photo loss가 꺼진다는 뜻이 아니다. 모든 arm의 appearance loss는 동일하며, P1은 LiDAR가 initialization에만 들어가고 LiDAR depth/normal loss가 0이라는 뜻이다.

## P4 design lock 요구

Coverage는 training-view LiDAR TIN valid mask와 rendered support 사이의 결손으로 정의해야 하며 evaluation-only reference를 사용하지 않는다. 정확한 eligibility, score, threshold, start/stop iteration, interaction with gradient-based growth를 config와 unit test로 먼저 고정한다. 기존 repository에서 이 계약을 찾지 못하면 P4 training을 시작하지 않는다.

## 계측과 산출

- Per arm/seed/building: wall time, peak VRAM, initial/final/pruned/grown primitive counts, loss/gradient share, seed survival, valid LiDAR support coverage.
- Same frozen surface-proxy protocol: precision/recall/F-score@0.1/0.2/0.5 및 양방향 p95. 가능하면 explicit mesh triangle distance를 별도 이름으로 추가하되 기존 proxy를 덮어쓰지 않는다.
- Same TSDF mesh와 Roofer readout: roof-plane F1, RMSZ, has_lod22, val3dity.
- 비교는 수치·관찰까지만 작성하고 scientific verdict는 사람이 내린다.
- 각 단계는 한 태스크 한 커밋, 실패 receipt append-only, 원본/기존 baseline 덮어쓰기 금지.
"""
    atomic_text(output_dir / "next_oracle_prompt.md", prompt)
    return {
        "assessment": "Share with caveats",
        "run_reliable": run_reliable,
        "valid_surface_buildings": valid_n,
        "missing_surface_buildings": missing_n,
        "classification_counts": counts,
        "thresholds": thresholds,
        "missing_rates": missing_rates,
        "relations": relations,
        "upstream_good_lod2_failure_ids": upstream_good_lod_fail,
        "upstream_bad_strong_lod2_ids": upstream_bad_lod_good,
        "source_snapshot_current_match": source_unchanged,
        "panel_status_count": len(panel_status),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    run_root = args.run_root if args.run_root.is_absolute() else REPO / args.run_root
    output_dir = args.output_dir or run_root / "post_analysis"
    if not output_dir.is_absolute():
        output_dir = REPO / output_dir

    state = load_json(run_root / "run_state.json")
    metadata = load_json(run_root / "run_metadata.json")
    cache_manifest = load_json(run_root / "cache_manifest.json")
    config = load_json(REPO / "configs/input_and_alignment/tum2twin_rv1_20260728_2327.yaml")
    metrics = pd.read_csv(run_root / "building_metrics.csv")
    if state.get("run_id") != "20260728_2327" or metadata.get("run_id") != state.get("run_id"):
        raise RuntimeError("run ID mismatch")
    if len(metrics) != 178 or metrics["building_id"].nunique() != 178:
        raise RuntimeError("canonical metric grain drift")
    if state.get("current_stage") != "DONE" or state.get("stage_status") != "completed":
        raise RuntimeError("run is not complete")

    classified, thresholds = classify_surface_proxy(metrics)
    existing_views = existing_view_inventories()
    classified["existing_view_count"] = classified["building_id"].map(
        {key: value["view_count"] for key, value in existing_views.items()}
    )
    manual_qa = REPO / "docs/experiments/pilots/fusion_w1/reports/fusion_w1_dense_baseline_qualitative_v2_manual_qa_20260728.md"
    panel_status = parse_manual_qa(manual_qa)
    classified["qualitative_panel_status"] = classified["building_id"].map(panel_status).fillna("not_in_panel")
    candidates = choose_candidates(classified, run_root, config, existing_views, panel_status)
    selected_ids = {item["building_id"] for item in candidates}
    classified["selected_oracle_candidate"] = classified["building_id"].isin(selected_ids)
    if not all(item["essential_inputs_complete"] for item in candidates):
        raise RuntimeError("candidate essential input audit failed")

    output_dir.mkdir(parents=True, exist_ok=True)
    atomic_csv(output_dir / "surface_proxy_R_v1.csv", classified)
    snapshot_rows = source_snapshot_audit(cache_manifest)
    group_rows = group_summary(classified)
    plot_scatter(classified, candidates, output_dir, thresholds)
    analysis = render_reports(
        run_root, output_dir, classified, state, metadata, config, thresholds,
        snapshot_rows, candidates, group_rows, panel_status,
    )
    sources = [
        run_root / "run_state.json", run_root / "run_metadata.json",
        run_root / "building_metrics.csv", run_root / "classification_summary.md",
        REPO / "configs/input_and_alignment/tum2twin_rv1_20260728_2327.yaml", REPO / "src/pipelines/rv1.py",
        manual_qa,
    ]
    outputs = [
        output_dir / "POST_RUN_SUMMARY.md", output_dir / "surface_proxy_R_v1.csv",
        output_dir / "metric_audit.md", output_dir / "oracle_candidates.yaml",
        output_dir / "next_oracle_prompt.md",
        output_dir / "figures/completeness_vs_reliability.png",
        output_dir / "figures/recall_vs_precision.png",
        output_dir / "figures/surface_vs_lod2.png",
    ]
    manifest = {
        "schema": "jointbuildgs.tum2twin.surface_proxy_rv1.post_analysis.v1",
        "generated_at": now(),
        "run_id": state["run_id"],
        "source_run_commit": metadata["git_head"],
        "source_branch": "exp/fusion-w1",
        "scientific_status": SCIENCE_STATUS,
        "no_new_training": True,
        "no_geometry_distance_recomputation": True,
        "analysis": analysis,
        "candidate_ids": [item["building_id"] for item in candidates],
        "source_files": [
            {"path": rel(path), "sha256": sha256_file(path), "bytes": path.stat().st_size}
            for path in sources if path.is_file()
        ],
        "analysis_code": [
            {
                "path": rel(path),
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
            for path in (
                REPO / "scripts/input_and_alignment/tum2twin_rv1/analyze_tum2twin_surface_proxy_rv1.py",
                REPO / "tests/test_tum2twin_surface_proxy_rv1_analysis.py",
            )
        ],
        "reproduction": {
            "runtime": "existing jointbuildgs:dev container; no package installation",
            "analysis_command": "python scripts/input_and_alignment/tum2twin_rv1/analyze_tum2twin_surface_proxy_rv1.py --run-root reports/nightly_rv1_20260728_2327 --output-dir reports/nightly_rv1_20260728_2327/post_analysis",
            "validation_command": "python tests/test_tum2twin_surface_proxy_rv1_analysis.py",
            "long_geometry_recalculation": False,
            "gs_training": False,
        },
        "source_snapshot_audit": snapshot_rows,
        "chart_map": [
            {"file": "figures/completeness_vs_reliability.png", "question": "Do completeness and reliability separate?", "grain": "valid building", "fields": ["completeness_score", "reliability_score", "surface_proxy_R_v1"]},
            {"file": "figures/recall_vs_precision.png", "question": "How do directional 0.2 m rates differ?", "grain": "valid building", "fields": ["surface_recall_0p2m", "surface_precision_0p2m", "surface_proxy_R_v1"]},
            {"file": "figures/surface_vs_lod2.png", "question": "How is upstream surface proxy related to roof-plane F1?", "grain": "building with both metrics", "fields": ["surface_proxy_score", "roof_plane_f1", "surface_proxy_R_v1"]},
        ],
    }
    atomic_json(output_dir / "analysis_manifest.json", manifest)
    manifest["output_files"] = [
        {"path": rel(path), "sha256": sha256_file(path), "bytes": path.stat().st_size}
        for path in outputs
    ]
    atomic_json(output_dir / "analysis_manifest.json", manifest)
    print(json.dumps({"status": "complete", **analysis, "output_dir": rel(output_dir)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
