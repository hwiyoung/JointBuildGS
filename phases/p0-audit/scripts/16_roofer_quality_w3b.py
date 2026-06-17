#!/usr/bin/env python3
"""W3-1b addendum: roof matching overlays and internal boundary metrics.

Run from phases/p0-audit/. Host mode records a run and executes the computation inside
the P0 tools container. The compute mode imports W3-1 parsing/matching helpers
from scripts/15_roofer_quality_w3.py.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import math
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from typing import Any


TASK_ID = "W3-1b"
BASE_W3_RUN_ID = "w3_1_roofer_quality_20260612_210850"
BASE_W2_RUN_ID = "w2_1_roofer_default_20260612_152729"
OUTLIER_BUILDING_ID = "DEBY_LOD2_4906973"
INTERNAL_BOUNDARY_SAMPLE_SPACING_M = 0.50
MIN_SHARED_BOUNDARY_LENGTH_M = 0.20


def host_entrypoint() -> None:
    repo = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.setdefault("P0_UID", str(os.getuid()))
    env.setdefault("P0_GID", str(os.getgid()))
    run_id = env.get("RUN_ID") or datetime.now().strftime("w3_1b_roofer_quality_%Y%m%d_%H%M%S")
    git_commit = capture(["git", "rev-parse", "--short", "HEAD"], cwd=repo.parent).strip()
    run_dir = repo / "runs" / run_id
    logs_dir = run_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    compose = ["docker", "compose", "-f", str(repo / "env/docker-compose.p0.yml")]

    write_host_config(run_dir, run_id, git_commit)
    if env.get("SKIP_BUILD") != "1":
        run(compose + ["build", "tools"], cwd=repo, env=env, log_path=logs_dir / "build_tools.log")
    write_host_versions(repo, run_dir, compose, env, git_commit)
    run(
        compose
        + [
            "run",
            "-T",
            "--rm",
            "-e",
            f"RUN_ID={run_id}",
            "-e",
            f"P0_GIT_COMMIT={git_commit}",
            "tools",
            "python",
            "/workspace/scripts/16_roofer_quality_w3b.py",
            "--mode",
            "compute",
        ],
        cwd=repo,
        env=env,
        log_path=logs_dir / "compute.log",
    )
    print(f"run_id={run_id}")
    print(f"run_dir=runs/{run_id}")
    print("report=docs/W3_1b_matching_validation.md")


def compute_entrypoint() -> None:
    w3 = load_w3_module(Path("/workspace/scripts/15_roofer_quality_w3.py"))
    root = Path("/workspace")
    docs = root / "docs"
    figs = docs / "figs"
    figs.mkdir(parents=True, exist_ok=True)
    run_id = os.environ["RUN_ID"]
    run_dir = root / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    metrics_rows = read_csv(docs / "W3_1_roofer_quality_metrics.csv")
    building_ids = [row["building_id"] for row in metrics_rows]
    if len(building_ids) != 67:
        raise RuntimeError(f"Expected 67 W3-1 metric rows, got {len(building_ids)}")

    reference = w3.parse_lod2_roofs(Path(w3.LOD2_DIR), set(building_ids))
    als_pred = w3.parse_cityjson_roofs(Path(w3.ALS_CITYJSON), set(building_ids))
    dim_pred = w3.parse_cityjson_roofs(Path(w3.DIM_CITYJSON), set(building_ids))

    internal_rows = build_internal_boundary_rows(w3, building_ids, reference, als_pred, dim_pred)
    summary_rows = build_internal_summary(internal_rows)
    overlay_rows = select_overlay_rows(metrics_rows)
    overlay_paths = render_overlay_figures(w3, overlay_rows, reference, als_pred, dim_pred, figs)
    outlier_rows = build_outlier_rows(w3, OUTLIER_BUILDING_ID, reference, als_pred, dim_pred, metrics_rows)

    internal_csv = docs / "W3_1b_internal_boundary_metrics.csv"
    summary_csv = docs / "W3_1b_internal_boundary_summary.csv"
    overlay_csv = docs / "W3_1b_overlay_selection.csv"
    outlier_csv = docs / "W3_1b_height_outlier_note.csv"
    report = docs / "W3_1b_matching_validation.md"
    write_csv(internal_csv, internal_rows)
    write_csv(summary_csv, summary_rows)
    write_csv(overlay_csv, overlay_rows)
    write_csv(outlier_csv, outlier_rows)
    write_report(report, run_id, overlay_rows, overlay_paths, summary_rows, outlier_rows)
    update_w3_report_link(docs / "W3_1_roofer_quality.md")

    snapshot_paths = [
        internal_csv,
        summary_csv,
        overlay_csv,
        outlier_csv,
        report,
        docs / "W3_1_roofer_quality.md",
        *overlay_paths.values(),
    ]
    copy_outputs(run_dir, snapshot_paths)
    write_run_summary(run_dir / "w3_1b_summary.json", overlay_rows, summary_rows, outlier_rows, overlay_paths)

    print(f"buildings={len(building_ids)}")
    print(f"internal_metrics={rel(internal_csv)}")
    print(f"internal_summary={rel(summary_csv)}")
    for bucket, path in overlay_paths.items():
        print(f"overlay_{bucket}={rel(path)}")
    print(f"outlier_note={rel(outlier_csv)}")
    print(f"report={rel(report)}")


def load_w3_module(path: Path) -> Any:
    spec = importlib.util.spec_from_file_location("w3_roofer_quality", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def build_internal_boundary_rows(
    w3: Any,
    building_ids: list[str],
    reference: dict[str, list[Any]],
    als_pred: dict[str, list[Any]],
    dim_pred: dict[str, list[Any]],
) -> list[dict[str, str]]:
    rows = []
    for building_id in building_ids:
        ref_surfaces = reference[building_id]
        for label, pred_lookup in (("als", als_pred), ("dim", dim_pred)):
            pred_surfaces = pred_lookup[building_id]
            matches = w3.match_surfaces(ref_surfaces, pred_surfaces)
            metrics = internal_boundary_metrics(w3, matches)
            rows.append(
                {
                    "building_id": building_id,
                    "input": label,
                    "ref_roof_planes": str(len(ref_surfaces)),
                    "pred_roof_planes": str(len(pred_surfaces)),
                    "matched_planes": str(len(matches)),
                    "matched_plane_pairs": str(metrics["matched_plane_pairs"]),
                    "shared_pair_count": str(metrics["shared_pair_count"]),
                    "ref_internal_length_m": format_value(metrics["ref_internal_length_m"]),
                    "pred_internal_length_m": format_value(metrics["pred_internal_length_m"]),
                    "ref_internal_samples": str(metrics["ref_internal_samples"]),
                    "pred_internal_samples": str(metrics["pred_internal_samples"]),
                    "internal_boundary_chamfer_m": format_value(metrics["internal_boundary_chamfer_m"]),
                    "internal_boundary_hausdorff_m": format_value(metrics["internal_boundary_hausdorff_m"]),
                }
            )
    return rows


def internal_boundary_metrics(w3: Any, matches: list[dict[str, Any]]) -> dict[str, Any]:
    ref_lines = []
    pred_lines = []
    shared_pair_count = 0
    matched_plane_pairs = 0
    for first, second in combinations(matches, 2):
        matched_plane_pairs += 1
        ref_shared = shared_boundary_lines(w3, first["ref"].polygon, second["ref"].polygon)
        pred_shared = shared_boundary_lines(w3, first["pred"].polygon, second["pred"].polygon)
        if ref_shared or pred_shared:
            shared_pair_count += 1
        ref_lines.extend(ref_shared)
        pred_lines.extend(pred_shared)

    ref_points = sample_line_points(ref_lines, INTERNAL_BOUNDARY_SAMPLE_SPACING_M)
    pred_points = sample_line_points(pred_lines, INTERNAL_BOUNDARY_SAMPLE_SPACING_M)
    ref_length = sum(float(line.length) for line in ref_lines)
    pred_length = sum(float(line.length) for line in pred_lines)
    if len(ref_points) == 0 or len(pred_points) == 0:
        chamfer = math.nan
        hausdorff = math.nan
    else:
        ref_to_pred = w3.min_distances(ref_points, pred_points)
        pred_to_ref = w3.min_distances(pred_points, ref_points)
        chamfer = float((ref_to_pred.mean() + pred_to_ref.mean()) / 2.0)
        hausdorff = float(max(ref_to_pred.max(), pred_to_ref.max()))
    return {
        "matched_plane_pairs": matched_plane_pairs,
        "shared_pair_count": shared_pair_count,
        "ref_internal_length_m": ref_length,
        "pred_internal_length_m": pred_length,
        "ref_internal_samples": int(len(ref_points)),
        "pred_internal_samples": int(len(pred_points)),
        "internal_boundary_chamfer_m": chamfer,
        "internal_boundary_hausdorff_m": hausdorff,
    }


def shared_boundary_lines(w3: Any, left: Any, right: Any) -> list[Any]:
    geom = left.boundary.intersection(right.boundary)
    return [line for line in w3.flatten_lines(geom) if float(line.length) >= MIN_SHARED_BOUNDARY_LENGTH_M]


def sample_line_points(lines: list[Any], spacing: float) -> Any:
    import numpy as np

    points = []
    for line in lines:
        length = float(line.length)
        if length <= 0:
            continue
        n = max(2, int(math.ceil(length / spacing)) + 1)
        for distance in np.linspace(0.0, length, n):
            pt = line.interpolate(float(distance))
            points.append((pt.x, pt.y))
    return np.asarray(points, dtype=float) if points else np.empty((0, 2), dtype=float)


def build_internal_summary(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    by_building: dict[str, dict[str, dict[str, str]]] = {}
    for row in rows:
        by_building.setdefault(row["building_id"], {})[row["input"]] = row
    summary = []
    for metric in ("internal_boundary_chamfer_m", "internal_boundary_hausdorff_m"):
        als_values = []
        dim_values = []
        for pair in by_building.values():
            als = parse_float(pair.get("als", {}).get(metric, ""))
            dim = parse_float(pair.get("dim", {}).get(metric, ""))
            if als is None or dim is None:
                continue
            if math.isfinite(als) and math.isfinite(dim):
                als_values.append(als)
                dim_values.append(dim)
        als_median = median(als_values)
        dim_median = median(dim_values)
        summary.append(
            {
                "metric": metric,
                "n_paired_finite": str(len(als_values)),
                "als_median": format_value(als_median),
                "dim_median": format_value(dim_median),
                "dim_minus_als": format_value(dim_median - als_median),
                "dim_over_als": format_value(safe_ratio(dim_median, als_median)),
                "definition": "matched roof-surface shared boundaries sampled at 0.50 m",
            }
        )
    return summary


def select_overlay_rows(metrics_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    candidates = []
    for row in metrics_rows:
        als_f1 = float(row["als_plane_f1"])
        dim_f1 = float(row["dim_plane_f1"])
        ref_n = int(row["ref_roof_planes"])
        candidates.append(
            {
                "building_id": row["building_id"],
                "ref_roof_planes": row["ref_roof_planes"],
                "als_plane_f1": row["als_plane_f1"],
                "dim_plane_f1": row["dim_plane_f1"],
                "mean_plane_f1": format_value((als_f1 + dim_f1) / 2.0),
                "_mean": (als_f1 + dim_f1) / 2.0,
                "_ref_n": ref_n,
            }
        )

    high_pool = [row for row in candidates if row["_mean"] >= 0.99 and row["_ref_n"] >= 2] or candidates
    mid_pool = [row for row in candidates if row["_ref_n"] >= 2] or candidates
    low_pool = [row for row in candidates if row["_ref_n"] >= 2] or candidates
    selected = {
        "high": max(high_pool, key=lambda row: (row["_ref_n"], row["building_id"])),
        "mid": min(mid_pool, key=lambda row: (abs(row["_mean"] - 0.5), -row["_ref_n"], row["building_id"])),
        "low": min(low_pool, key=lambda row: (row["_mean"], -row["_ref_n"], row["building_id"])),
    }
    rows = []
    for bucket, row in selected.items():
        rows.append(
            {
                "bucket": bucket,
                "building_id": row["building_id"],
                "ref_roof_planes": row["ref_roof_planes"],
                "als_plane_f1": row["als_plane_f1"],
                "dim_plane_f1": row["dim_plane_f1"],
                "mean_plane_f1": row["mean_plane_f1"],
                "selection_rule": selection_rule(bucket),
            }
        )
    return rows


def selection_rule(bucket: str) -> str:
    if bucket == "high":
        return "highest mean F1 group; tie-breaker larger ref_roof_planes"
    if bucket == "mid":
        return "closest to mean F1 0.5; tie-breaker larger ref_roof_planes"
    return "lowest mean F1; tie-breaker larger ref_roof_planes"


def render_overlay_figures(
    w3: Any,
    overlay_rows: list[dict[str, str]],
    reference: dict[str, list[Any]],
    als_pred: dict[str, list[Any]],
    dim_pred: dict[str, list[Any]],
    figs: Path,
) -> dict[str, Path]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    paths = {}
    for row in overlay_rows:
        bucket = row["bucket"]
        building_id = row["building_id"]
        ref_surfaces = reference[building_id]
        panels = [("ALS", als_pred[building_id], row["als_plane_f1"]), ("DIM", dim_pred[building_id], row["dim_plane_f1"])]
        fig, axes = plt.subplots(1, 2, figsize=(12, 6), dpi=180)
        for ax, (label, pred_surfaces, f1) in zip(axes, panels):
            matches = w3.match_surfaces(ref_surfaces, pred_surfaces)
            draw_overlay_panel(w3, ax, ref_surfaces, pred_surfaces, matches)
            ax.set_title(f"{label}: F1={f1}, matched={len(matches)}")
        fig.suptitle(f"W3-1b matching overlay ({bucket}) - {building_id}", fontsize=11)
        fig.tight_layout()
        path = figs / f"w3_1b_matching_overlay_{bucket}_{building_id}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path)
        plt.close(fig)
        row["figure"] = f"docs/figs/{path.name}"
        paths[bucket] = path
    return paths


def draw_overlay_panel(w3: Any, ax: Any, ref_surfaces: list[Any], pred_surfaces: list[Any], matches: list[dict[str, Any]]) -> None:
    draw_surfaces(w3, ax, ref_surfaces, edge_color="#222222", face_color="#d9d9d9", alpha=0.45, label="reference")
    draw_surfaces(w3, ax, pred_surfaces, edge_color="#e67e22", face_color="#f5b041", alpha=0.28, label="prediction")
    for match in matches:
        ref_pt = match["ref"].polygon.representative_point()
        pred_pt = match["pred"].polygon.representative_point()
        ax.plot([ref_pt.x, pred_pt.x], [ref_pt.y, pred_pt.y], color="#2ca25f", linewidth=1.0, alpha=0.85)
        ax.text(
            (ref_pt.x + pred_pt.x) / 2.0,
            (ref_pt.y + pred_pt.y) / 2.0,
            f"{match['iou']:.2f}",
            fontsize=6,
            color="#006d2c",
        )
    set_equal_bounds(w3, ax, [*ref_surfaces, *pred_surfaces])
    ax.grid(color="0.9", linewidth=0.5)
    ax.legend(loc="upper right", fontsize=7)


def draw_surfaces(
    w3: Any,
    ax: Any,
    surfaces: list[Any],
    edge_color: str,
    face_color: str,
    alpha: float,
    label: str,
) -> None:
    first = True
    for surface in surfaces:
        for polygon in w3.flatten_polygons(surface.polygon):
            x, y = polygon.exterior.xy
            ax.fill(x, y, facecolor=face_color, edgecolor=edge_color, linewidth=1.0, alpha=alpha, label=label if first else None)
            ax.plot(x, y, color=edge_color, linewidth=1.0)
            for interior in polygon.interiors:
                ix, iy = interior.xy
                ax.plot(ix, iy, color=edge_color, linewidth=0.7, linestyle=":")
            first = False


def set_equal_bounds(w3: Any, ax: Any, surfaces: list[Any]) -> None:
    polygons = []
    for surface in surfaces:
        polygons.extend(w3.flatten_polygons(surface.polygon))
    if not polygons:
        return
    min_x = min(poly.bounds[0] for poly in polygons)
    min_y = min(poly.bounds[1] for poly in polygons)
    max_x = max(poly.bounds[2] for poly in polygons)
    max_y = max(poly.bounds[3] for poly in polygons)
    width = max_x - min_x
    height = max_y - min_y
    pad = max(width, height, 1.0) * 0.08
    ax.set_xlim(min_x - pad, max_x + pad)
    ax.set_ylim(min_y - pad, max_y + pad)
    ax.set_aspect("equal", adjustable="box")


def build_outlier_rows(
    w3: Any,
    building_id: str,
    reference: dict[str, list[Any]],
    als_pred: dict[str, list[Any]],
    dim_pred: dict[str, list[Any]],
    metrics_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    metric_row = next(row for row in metrics_rows if row["building_id"] == building_id)
    scene_lookup = {row["building_id"]: row for row in read_csv(Path("/workspace/docs/scene_aoi_buildings.csv"))}
    scene_row = scene_lookup.get(building_id, {})
    rows = []
    for label, pred_lookup in (("als", als_pred), ("dim", dim_pred)):
        matches = w3.match_surfaces(reference[building_id], pred_lookup[building_id])
        stats = matched_height_stats(w3, matches)
        rows.append(
            {
                "building_id": building_id,
                "input": label,
                "source_gml": scene_row.get("source_files", ""),
                "ref_roof_planes": str(len(reference[building_id])),
                "pred_roof_planes": str(len(pred_lookup[building_id])),
                "matched_planes": str(len(matches)),
                "plane_f1": metric_row[f"{label}_plane_f1"],
                "height_bias_m": metric_row[f"{label}_height_bias_m"],
                "matched_ref_median_z_m": format_value(stats["ref_median_z_m"]),
                "matched_pred_median_z_m": format_value(stats["pred_median_z_m"]),
                "matched_pred_minus_ref_median_m": format_value(stats["pred_minus_ref_median_m"]),
                "matched_sample_count": str(stats["sample_count"]),
                "note": "LoD2 reference roof is about 4.8 m higher than both ALS and DIM Roofer outputs over the same XY footprint; mark as reference_mismatch_candidate for manual review.",
            }
        )
    return rows


def matched_height_stats(w3: Any, matches: list[dict[str, Any]]) -> dict[str, Any]:
    import numpy as np

    ref_values = []
    pred_values = []
    for match in matches:
        intersection = match["ref"].polygon.intersection(match["pred"].polygon)
        samples = w3.sample_polygon_points(intersection, w3.HEIGHT_SAMPLE_SPACING_M)
        if len(samples) == 0:
            continue
        ref_values.append(match["ref"].z_at(samples[:, 0], samples[:, 1]))
        pred_values.append(match["pred"].z_at(samples[:, 0], samples[:, 1]))
    if not ref_values:
        return {
            "ref_median_z_m": math.nan,
            "pred_median_z_m": math.nan,
            "pred_minus_ref_median_m": math.nan,
            "sample_count": 0,
        }
    ref = np.concatenate(ref_values)
    pred = np.concatenate(pred_values)
    return {
        "ref_median_z_m": float(np.median(ref)),
        "pred_median_z_m": float(np.median(pred)),
        "pred_minus_ref_median_m": float(np.median(pred - ref)),
        "sample_count": int(ref.size),
    }


def write_report(
    path: Path,
    run_id: str,
    overlay_rows: list[dict[str, str]],
    overlay_paths: dict[str, Path],
    summary_rows: list[dict[str, str]],
    outlier_rows: list[dict[str, str]],
) -> None:
    lines = [
        "# W3-1b Matching Validation Addendum",
        "",
        f"- Run ID: `{run_id}`",
        f"- Base W3-1 run: `{BASE_W3_RUN_ID}`",
        f"- Base Roofer default run: `{BASE_W2_RUN_ID}`",
        f"- Internal boundary metric: shared boundaries among matched roof-surface pairs, sampled every {INTERNAL_BOUNDARY_SAMPLE_SPACING_M:.2f} m.",
        f"- Shared boundary extraction ignores line segments shorter than {MIN_SHARED_BOUNDARY_LENGTH_M:.2f} m.",
        "",
        "## Matching Overlay Spot Checks",
        "",
    ]
    lines.extend(markdown_table(overlay_rows))
    lines.append("")
    for row in overlay_rows:
        bucket = row["bucket"]
        path_obj = overlay_paths[bucket]
        lines.extend([f"![{bucket} overlay](figs/{path_obj.name})", ""])
    lines.extend(["## Internal Boundary Summary", ""])
    lines.extend(markdown_table(summary_rows))
    lines.extend(
        [
            "",
            "## Height Bias Outlier Note",
            "",
            f"- Outlier building: `{OUTLIER_BUILDING_ID}`.",
            "- Observation: both ALS and DIM Roofer outputs are about 4.8 m below the LoD2 reference roof over nearly the same XY footprint.",
            "- Review note: this is a `reference_mismatch_candidate` consistent with possible extension/reconstruction or another reference/source-time mismatch; keep it explicit rather than mixing it with ordinary roof matching error.",
            "",
        ]
    )
    lines.extend(markdown_table(outlier_rows))
    lines.extend(
        [
            "",
            "## Files",
            "",
            "- Internal boundary metrics: `docs/W3_1b_internal_boundary_metrics.csv`",
            "- Internal boundary summary: `docs/W3_1b_internal_boundary_summary.csv`",
            "- Overlay selection: `docs/W3_1b_overlay_selection.csv`",
            "- Height outlier note: `docs/W3_1b_height_outlier_note.csv`",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def update_w3_report_link(path: Path) -> None:
    marker = "## W3-1b Addendum"
    text = path.read_text(encoding="utf-8")
    if marker in text:
        return
    addendum = [
        "",
        marker,
        "",
        "- Matching spot-check overlays, internal boundary metrics, and the common height-bias outlier note are recorded in `docs/W3_1b_matching_validation.md`.",
    ]
    path.write_text(text.rstrip() + "\n" + "\n".join(addendum) + "\n", encoding="utf-8")


def write_run_summary(
    path: Path,
    overlay_rows: list[dict[str, str]],
    summary_rows: list[dict[str, str]],
    outlier_rows: list[dict[str, str]],
    overlay_paths: dict[str, Path],
) -> None:
    payload = {
        "task": TASK_ID,
        "run_id": os.environ["RUN_ID"],
        "base_w3_run_id": BASE_W3_RUN_ID,
        "base_w2_run_id": BASE_W2_RUN_ID,
        "internal_boundary_sample_spacing_m": INTERNAL_BOUNDARY_SAMPLE_SPACING_M,
        "min_shared_boundary_length_m": MIN_SHARED_BOUNDARY_LENGTH_M,
        "overlay_selection": overlay_rows,
        "internal_boundary_summary": summary_rows,
        "outlier_note": outlier_rows,
        "figures": {key: rel(path) for key, path in overlay_paths.items()},
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_host_config(run_dir: Path, run_id: str, git_commit: str) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    config = {
        "task": "W3-1b_matching_validation_internal_boundaries",
        "run_id": run_id,
        "git_commit": git_commit,
        "base_w3_run_id": BASE_W3_RUN_ID,
        "base_w2_run_id": BASE_W2_RUN_ID,
        "population": "W3-1 Roofer default both_success paired set",
        "internal_boundary_sample_spacing_m": INTERNAL_BOUNDARY_SAMPLE_SPACING_M,
        "min_shared_boundary_length_m": MIN_SHARED_BOUNDARY_LENGTH_M,
        "outlier_building_id": OUTLIER_BUILDING_ID,
    }
    (run_dir / "config.yaml").write_text(to_yaml(config), encoding="utf-8")


def write_host_versions(repo: Path, run_dir: Path, compose: list[str], env: dict[str, str], git_commit: str) -> None:
    lines = [
        "# W3-1b Tool Versions",
        "",
        f"- Generated: {datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')}",
        f"- Run ID: {run_dir.name}",
        f"- Repository commit: {git_commit}",
        "",
        "```console",
    ]
    commands = [
        ["git", "status", "--short", "--branch"],
        [
            *compose,
            "run",
            "-T",
            "--rm",
            "tools",
            "python",
            "-c",
            "import numpy, matplotlib, shapely, lxml; print('numpy ' + numpy.__version__); print('matplotlib ' + matplotlib.__version__); print('shapely ' + shapely.__version__); print('lxml ' + lxml.__version__)",
        ],
    ]
    for cmd in commands:
        lines.append("$ " + " ".join(cmd))
        lines.append(capture(cmd, cwd=repo if cmd[0] != "git" else repo.parent, env=env))
    lines.append("```")
    (run_dir / "versions.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(cmd: list[str], cwd: Path | None = None, env: dict[str, str] | None = None, log_path: Path | None = None) -> None:
    print("+ " + " ".join(cmd), flush=True)
    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("w", encoding="utf-8") as log:
            log.write("+ " + " ".join(cmd) + "\n")
            proc = subprocess.run(cmd, cwd=cwd, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            log.write(proc.stdout)
            print(proc.stdout, end="", flush=True)
            proc.check_returncode()
            return
    subprocess.run(cmd, cwd=cwd, env=env, text=True, check=True)


def capture(cmd: list[str], cwd: Path | None = None, env: dict[str, str] | None = None) -> str:
    proc = subprocess.run(cmd, cwd=cwd, env=env, text=True, capture_output=True, check=False)
    return ((proc.stdout or "") + (proc.stderr or "")).strip()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        raise RuntimeError(f"No rows for {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def copy_outputs(run_dir: Path, paths: list[Path]) -> None:
    snapshot = run_dir / "docs_snapshot"
    snapshot.mkdir(parents=True, exist_ok=True)
    for path in paths:
        shutil.copy2(path, snapshot / path.name)


def markdown_table(rows: list[dict[str, str]]) -> list[str]:
    if not rows:
        return ["_No rows._"]
    headers = [key for key in rows[0].keys() if not key.startswith("_")]
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(header, "")) for header in headers) + " |")
    return lines


def parse_float(value: str | float | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def median(values: list[float]) -> float:
    if not values:
        return math.nan
    import numpy as np

    return float(np.median(np.asarray(values, dtype=float)))


def safe_ratio(numerator: float, denominator: float) -> float:
    if denominator is None or not math.isfinite(denominator) or abs(denominator) < 1e-12:
        return math.nan
    return float(numerator / denominator)


def format_value(value: Any) -> str:
    if isinstance(value, int):
        return str(value)
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not math.isfinite(numeric):
        return ""
    return f"{numeric:.6f}"


def rel(path: Path) -> str:
    text = str(path)
    return text.replace("/workspace/", "")


def to_yaml(value: Any, indent: int = 0) -> str:
    pad = " " * indent
    if isinstance(value, dict):
        lines = []
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                lines.append(f"{pad}{key}:")
                lines.append(to_yaml(item, indent + 2))
            else:
                lines.append(f"{pad}{key}: {item}")
        return "\n".join(lines) + "\n"
    if isinstance(value, list):
        lines = []
        for item in value:
            if isinstance(item, (dict, list)):
                lines.append(f"{pad}-")
                lines.append(to_yaml(item, indent + 2))
            else:
                lines.append(f"{pad}- {item}")
        return "\n".join(lines) + "\n"
    return f"{pad}{value}\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("host", "compute"), default="host")
    args = parser.parse_args()
    if args.mode == "compute":
        compute_entrypoint()
    else:
        host_entrypoint()


if __name__ == "__main__":
    main()
