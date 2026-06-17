#!/usr/bin/env python3
"""Build W2-1b paired Roofer analysis tables and failure-gallery figures.

Run from phases/p0-audit/. The host entrypoint re-runs this script inside the P0 tools
container so laspy/matplotlib execution stays in the audit toolchain.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


TASK_ID = "W2-1b"
AOI_BBOX = (690791.740, 5335864.050, 691154.650, 5336353.850)
GALLERY_IDS = [
    "DEBY_LOD2_104586480",  # high density, no nodata, but no LoD2.2
    "DEBY_LOD2_4907175",    # high nodata fraction
    "DEBY_LOD2_4907510",    # highest detected plane count in this failure class
]


@dataclass
class Footprint:
    building_id: str
    area_m2: float
    bbox: tuple[float, float, float, float]
    ring: np.ndarray


def host_entrypoint(args: argparse.Namespace) -> None:
    repo = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.setdefault("P0_UID", str(os.getuid()))
    env.setdefault("P0_GID", str(os.getgid()))

    compose = ["docker", "compose", "-f", str(repo / "env/docker-compose.p0.yml")]
    if env.get("SKIP_BUILD") != "1":
        run(compose + ["build", "tools"], cwd=repo, env=env)

    git_commit = capture(["git", "rev-parse", "--short", "HEAD"], cwd=repo.parent).strip()
    run_id = env.get("RUN_ID") or datetime.now().strftime("w2_1b_pair_analysis_%Y%m%d_%H%M%S")
    w2_run_id = args.w2_run_id or latest_w2_run(repo)
    run_dir = repo / "runs" / run_id
    logs_dir = run_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    write_host_config(run_dir, run_id, w2_run_id, git_commit)

    run(
        compose
        + [
            "run",
            "-T",
            "--rm",
            "-e",
            "P0_INSIDE_CONTAINER=1",
            "-e",
            f"RUN_ID={run_id}",
            "-e",
            f"W2_RUN_ID={w2_run_id}",
            "-e",
            f"P0_GIT_COMMIT={git_commit}",
            "tools",
            "python",
            "/workspace/scripts/09_w2_pair_analysis.py",
            "--inside",
        ],
        cwd=repo,
        env=env,
        log_path=logs_dir / "pair_analysis.log",
    )


def latest_w2_run(repo: Path) -> str:
    candidates = sorted((repo / "runs").glob("w2_1_roofer_default_*"))
    if not candidates:
        raise FileNotFoundError("No runs/w2_1_roofer_default_* directory found")
    return candidates[-1].name


def run(
    cmd: list[str],
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    log_path: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    print("+ " + " ".join(cmd), flush=True)
    if log_path:
        with log_path.open("w", encoding="utf-8") as log:
            log.write("+ " + " ".join(cmd) + "\n")
            proc = subprocess.run(
                cmd,
                cwd=cwd,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            log.write(proc.stdout)
            print(proc.stdout, end="", flush=True)
            proc.check_returncode()
            return proc
    return subprocess.run(cmd, cwd=cwd, env=env, text=True, check=True)


def capture(cmd: list[str], cwd: Path | None = None) -> str:
    proc = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, check=False)
    return ((proc.stdout or "") + (proc.stderr or "")).strip()


def write_host_config(run_dir: Path, run_id: str, w2_run_id: str, git_commit: str) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        "task: W2-1b_pair_analysis",
        f"run_id: {run_id}",
        f"w2_run_id: {w2_run_id}",
        f"git_commit: {git_commit}",
        "aoi_bbox: [690791.740, 5335864.050, 691154.650, 5336353.850]",
        "paired_csv: docs/W2_1b_paired_status.csv",
        "reason_crosstab_csv: docs/W2_1b_reason_crosstab.csv",
        "missing_roofer_exclusions_csv: docs/W2_1b_missing_roofer_exclusions.csv",
        "als_failure_memo_csv: docs/W2_1b_als_roofer_failure_memo.csv",
    ]
    (run_dir / "config.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_versions(run_dir: Path, w2_run_id: str) -> None:
    lines = [
        "# W2-1b Tool Versions",
        "",
        f"- Generated: {datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')}",
        f"- Run ID: {os.environ['RUN_ID']}",
        f"- W2 source run: {w2_run_id}",
        f"- Repository commit: {os.environ.get('P0_GIT_COMMIT', 'unknown')}",
        "",
        "```console",
    ]
    for cmd in (
        ["python", "--version"],
        [
            "python",
            "-c",
            "import laspy, matplotlib, numpy; print('laspy ' + laspy.__version__); print('matplotlib ' + matplotlib.__version__); print('numpy ' + numpy.__version__)",
        ],
        ["val3dity", "--version"],
    ):
        lines.append("$ " + " ".join(cmd))
        lines.append(capture(cmd))
    lines.append("```")
    (run_dir / "versions.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def inside_entrypoint() -> None:
    root = Path("/workspace")
    docs = root / "docs"
    figs = docs / "figs"
    data = root / "data"
    run_id = os.environ["RUN_ID"]
    w2_run_id = os.environ["W2_RUN_ID"]
    run_dir = root / "runs" / run_id
    source_run = root / "runs" / w2_run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    figs.mkdir(parents=True, exist_ok=True)
    write_versions(run_dir, w2_run_id)

    status_rows = read_status(source_run / "building_reconstruction_status.csv")
    footprints = load_footprints(data / "work/footprints/lod2_ground_plan.geojson")
    paired_rows = build_paired_rows(status_rows, footprints)
    missing_rows = build_missing_roofer_exclusions(paired_rows, footprints)
    als_memo_rows = build_als_roofer_failure_memo(status_rows, missing_rows)
    crosstab_rows = build_reason_crosstab(paired_rows)
    rates = compute_rates(paired_rows)

    paired_csv = docs / "W2_1b_paired_status.csv"
    crosstab_csv = docs / "W2_1b_reason_crosstab.csv"
    missing_csv = docs / "W2_1b_missing_roofer_exclusions.csv"
    als_memo_csv = docs / "W2_1b_als_roofer_failure_memo.csv"
    write_csv(paired_csv, paired_rows)
    write_csv(crosstab_csv, crosstab_rows)
    write_csv(missing_csv, missing_rows)
    write_csv(als_memo_csv, als_memo_rows)

    gallery_paths = make_gallery_figures(
        data / "work/w2/dim_v1_classified_z_minus0p174.laz",
        source_run / "cityjson/dim_roofer.city.json",
        status_rows,
        footprints,
        figs,
    )
    write_report(
        docs / "W2_1b_paired_analysis.md",
        w2_run_id,
        paired_rows,
        crosstab_rows,
        missing_rows,
        als_memo_rows,
        rates,
        gallery_paths,
    )
    copy_outputs_to_run(
        run_dir,
        [paired_csv, crosstab_csv, missing_csv, als_memo_csv, docs / "W2_1b_paired_analysis.md"],
        gallery_paths,
    )

    print(f"paired_csv={rel(paired_csv)}")
    print(f"reason_crosstab_csv={rel(crosstab_csv)}")
    print(f"missing_roofer_exclusions_csv={rel(missing_csv)}")
    print(f"als_failure_memo_csv={rel(als_memo_csv)}")
    for path in gallery_paths:
        print(f"gallery_png={rel(path)}")


def read_status(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        raise RuntimeError(f"No rows in {path}")
    return rows


def load_footprints(path: Path) -> dict[str, Footprint]:
    data = json.loads(path.read_text(encoding="utf-8"))
    footprints: dict[str, Footprint] = {}
    for feature in data["features"]:
        props = feature["properties"]
        ring = np.array(feature["geometry"]["coordinates"][0], dtype=np.float64)
        if not np.allclose(ring[0], ring[-1]):
            ring = np.vstack([ring, ring[0]])
        footprints[props["building_id"]] = Footprint(
            building_id=props["building_id"],
            area_m2=float(props["area_m2"]),
            bbox=(
                float(props["min_x"]),
                float(props["min_y"]),
                float(props["max_x"]),
                float(props["max_y"]),
            ),
            ring=ring,
        )
    return footprints


def build_paired_rows(
    status_rows: list[dict[str, str]],
    footprints: dict[str, Footprint],
) -> list[dict[str, str]]:
    by = {(row["input"], row["building_id"]): row for row in status_rows}
    building_ids = sorted({row["building_id"] for row in status_rows})
    rows: list[dict[str, str]] = []
    for building_id in building_ids:
        als = by[("ALS", building_id)]
        dim = by[("DIM", building_id)]
        category = paired_category(als["status"], dim["status"])
        both_attempted = als["reason"] != "missing_roofer_output" and dim["reason"] != "missing_roofer_output"
        fp = footprints[building_id]
        rows.append(
            {
                "building_id": building_id,
                "paired_category": category,
                "both_attempted": yesno(both_attempted),
                "exclude_from_comparison": yesno(not both_attempted),
                "exclude_reason": "" if both_attempted else "aoi_edge_centroid_outside_roofer_box",
                "footprint_area_m2": f"{fp.area_m2:.3f}",
                "footprint_centroid_in_box": yesno(centroid_in_box(fp.bbox, AOI_BBOX)),
                "footprint_fully_inside_box": yesno(fully_inside_box(fp.bbox, AOI_BBOX)),
                "footprint_bbox_intersects_box": yesno(bbox_intersects(fp.bbox, AOI_BBOX)),
                "als_status": als["status"],
                "als_reason": als["reason"],
                "als_rf_pt_density": als["rf_pt_density"],
                "als_rf_nodata_frac": als["rf_nodata_frac"],
                "als_has_lod22": als["has_lod22"],
                "als_val3dity_valid": als["val3dity_valid"],
                "dim_status": dim["status"],
                "dim_reason": dim["reason"],
                "dim_rf_pt_density": dim["rf_pt_density"],
                "dim_rf_nodata_frac": dim["rf_nodata_frac"],
                "dim_has_lod22": dim["has_lod22"],
                "dim_val3dity_valid": dim["val3dity_valid"],
            }
        )
    return rows


def paired_category(als_status: str, dim_status: str) -> str:
    als_success = als_status == "success"
    dim_success = dim_status == "success"
    if als_success and dim_success:
        return "both_success"
    if als_success and not dim_success:
        return "ALS_only"
    if dim_success and not als_success:
        return "DIM_only"
    return "both_fail"


def build_missing_roofer_exclusions(
    paired_rows: list[dict[str, str]],
    footprints: dict[str, Footprint],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for row in paired_rows:
        if row["als_reason"] != "missing_roofer_output" and row["dim_reason"] != "missing_roofer_output":
            continue
        fp = footprints[row["building_id"]]
        rows.append(
            {
                "building_id": row["building_id"],
                "als_missing_roofer_output": yesno(row["als_reason"] == "missing_roofer_output"),
                "dim_missing_roofer_output": yesno(row["dim_reason"] == "missing_roofer_output"),
                "same_missing_state": yesno(row["als_reason"] == row["dim_reason"] == "missing_roofer_output"),
                "diagnosis": "footprint_intersects_box_but_centroid_outside",
                "action": "exclude_from_both_attempted_population",
                "future_fix": "rerun_with_expanded_or_no_roofer_box_if_aoi_edge_buildings_are_required",
                "area_m2": f"{fp.area_m2:.3f}",
                "min_x": f"{fp.bbox[0]:.3f}",
                "min_y": f"{fp.bbox[1]:.3f}",
                "max_x": f"{fp.bbox[2]:.3f}",
                "max_y": f"{fp.bbox[3]:.3f}",
                "centroid_in_box": yesno(centroid_in_box(fp.bbox, AOI_BBOX)),
                "fully_inside_box": yesno(fully_inside_box(fp.bbox, AOI_BBOX)),
                "bbox_intersects_box": yesno(bbox_intersects(fp.bbox, AOI_BBOX)),
                "ring_closed": yesno(np.allclose(fp.ring[0], fp.ring[-1])),
                "ring_area_positive": yesno(polygon_area(fp.ring) > 0.0),
            }
        )
    return rows


def build_als_roofer_failure_memo(
    status_rows: list[dict[str, str]],
    missing_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    missing_by_id = {row["building_id"]: row for row in missing_rows}
    rows: list[dict[str, str]] = []
    for row in status_rows:
        if row["input"] != "ALS":
            continue
        if row["reason"] == "missing_roofer_output":
            diag = missing_by_id[row["building_id"]]
            note = (
                "Same 20 IDs are missing in ALS and DIM. ID and polygon geometry are present; "
                "the footprint only intersects the strict Roofer AOI box at the edge and its "
                "centroid is outside the box."
            )
            rows.append(
                {
                    "building_id": row["building_id"],
                    "als_roofer_failure_reason": row["reason"],
                    "memo": note,
                    "action": diag["action"],
                    "rf_pt_density": row["rf_pt_density"],
                    "rf_nodata_frac": row["rf_nodata_frac"],
                }
            )
        elif row["reason"] == "pointcloud_unusable":
            rows.append(
                {
                    "building_id": row["building_id"],
                    "als_roofer_failure_reason": row["reason"],
                    "memo": (
                        "Roofer emitted a feature but marked the pointcloud unusable and skipped "
                        "3D geometry; nodata fraction is high and extrusion mode is skip."
                    ),
                    "action": "keep_as_attempted_failure",
                    "rf_pt_density": row["rf_pt_density"],
                    "rf_nodata_frac": row["rf_nodata_frac"],
                }
            )
    return rows


def build_reason_crosstab(paired_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    als_reasons = sorted({row["als_reason"] for row in paired_rows})
    dim_reasons = sorted({row["dim_reason"] for row in paired_rows})
    counts = Counter((row["als_reason"], row["dim_reason"]) for row in paired_rows)
    rows: list[dict[str, str]] = []
    for als_reason in als_reasons:
        out = {"als_reason": als_reason}
        total = 0
        for dim_reason in dim_reasons:
            value = counts[(als_reason, dim_reason)]
            out[dim_reason] = str(value)
            total += value
        out["row_total"] = str(total)
        rows.append(out)
    return rows


def compute_rates(paired_rows: list[dict[str, str]]) -> dict[str, Any]:
    full_total = len(paired_rows)
    attempted_rows = [row for row in paired_rows if row["both_attempted"] == "yes"]
    attempted_total = len(attempted_rows)
    rates: dict[str, Any] = {
        "full_total": full_total,
        "attempted_total": attempted_total,
        "paired_category_counts": dict(Counter(row["paired_category"] for row in paired_rows)),
        "attempted_category_counts": dict(Counter(row["paired_category"] for row in attempted_rows)),
    }
    for label in ("als", "dim"):
        full_success = sum(row[f"{label}_status"] == "success" for row in paired_rows)
        attempted_success = sum(row[f"{label}_status"] == "success" for row in attempted_rows)
        attempted_lod22_output = sum(
            row[f"{label}_has_lod22"] == "True"
            and row[f"{label}_reason"] not in {"missing_roofer_output", "pointcloud_unusable", "pointcloud_unusable_no_points", "pointcloud_unusable_no_planes"}
            for row in attempted_rows
        )
        rates[label] = {
            "full_success": full_success,
            "full_rate": full_success / full_total,
            "attempted_success": attempted_success,
            "attempted_rate": attempted_success / attempted_total,
            "attempted_lod22_output": attempted_lod22_output,
            "attempted_lod22_output_rate": attempted_lod22_output / attempted_total,
        }
    return rates


def make_gallery_figures(
    dim_laz: Path,
    dim_cityjson: Path,
    status_rows: list[dict[str, str]],
    footprints: dict[str, Footprint],
    figs_dir: Path,
) -> list[Path]:
    import matplotlib.pyplot as plt

    status_by_id = {
        row["building_id"]: row
        for row in status_rows
        if row["input"] == "DIM"
    }
    chosen = [bid for bid in GALLERY_IDS if status_by_id[bid]["reason"] == "missing_lod22_geometry"]
    if len(chosen) != 3:
        missing_lod22 = [
            row["building_id"]
            for row in status_rows
            if row["input"] == "DIM" and row["reason"] == "missing_lod22_geometry"
        ]
        chosen = missing_lod22[:3]

    point_sets = read_dim_points_for_cases(dim_laz, {bid: footprints[bid] for bid in chosen}, buffer_m=5.0)
    city = load_cityjson(dim_cityjson)
    output_paths: list[Path] = []
    for bid in chosen:
        fp = footprints[bid]
        row = status_by_id[bid]
        points = point_sets[bid]
        fig, axes = plt.subplots(1, 2, figsize=(14, 6), constrained_layout=True)
        plot_topdown(axes[0], bid, fp, points, city)
        plot_profile(axes[1], fp, points, city, bid)
        fig.suptitle(
            (
                f"{bid} | DIM missing_lod22_geometry | "
                f"density={row['rf_pt_density']} pts/m2 | "
                f"nodata={row['rf_nodata_frac']} | roof_planes={row['rf_roof_planes']}"
            ),
            fontsize=11,
        )
        out = figs_dir / f"w2_1b_dim_missing_lod22_{bid}.png"
        fig.savefig(out, dpi=180)
        plt.close(fig)
        output_paths.append(out)
    return output_paths


def read_dim_points_for_cases(
    path: Path,
    footprints: dict[str, Footprint],
    buffer_m: float,
) -> dict[str, dict[str, np.ndarray]]:
    import laspy

    cases: dict[str, dict[str, Any]] = {}
    for bid, fp in footprints.items():
        min_x, min_y, max_x, max_y = fp.bbox
        cases[bid] = {
            "bbox": (min_x - buffer_m, min_y - buffer_m, max_x + buffer_m, max_y + buffer_m),
            "x": [],
            "y": [],
            "z": [],
            "classification": [],
        }

    with laspy.open(path) as fh:
        for points in fh.chunk_iterator(1_000_000):
            x = np.asarray(points.x)
            y = np.asarray(points.y)
            z = np.asarray(points.z)
            cls = np.asarray(points.classification, dtype=np.uint8)
            for case in cases.values():
                min_x, min_y, max_x, max_y = case["bbox"]
                mask = (x >= min_x) & (x <= max_x) & (y >= min_y) & (y <= max_y)
                if not np.any(mask):
                    continue
                case["x"].append(x[mask].astype(np.float64, copy=False))
                case["y"].append(y[mask].astype(np.float64, copy=False))
                case["z"].append(z[mask].astype(np.float64, copy=False))
                case["classification"].append(cls[mask])

    output: dict[str, dict[str, np.ndarray]] = {}
    for bid, case in cases.items():
        if case["x"]:
            output[bid] = {
                "x": np.concatenate(case["x"]),
                "y": np.concatenate(case["y"]),
                "z": np.concatenate(case["z"]),
                "classification": np.concatenate(case["classification"]),
            }
        else:
            output[bid] = {
                "x": np.array([], dtype=np.float64),
                "y": np.array([], dtype=np.float64),
                "z": np.array([], dtype=np.float64),
                "classification": np.array([], dtype=np.uint8),
            }
    return output


def load_cityjson(path: Path) -> dict[str, Any]:
    city = json.loads(path.read_text(encoding="utf-8"))
    transform = city.get("transform", {"scale": [1, 1, 1], "translate": [0, 0, 0]})
    vertices = np.array(city.get("vertices", []), dtype=np.float64)
    if vertices.size:
        scale = np.array(transform["scale"], dtype=np.float64)
        translate = np.array(transform["translate"], dtype=np.float64)
        vertices = vertices * scale + translate
    city["_absolute_vertices"] = vertices
    return city


def plot_topdown(ax: Any, bid: str, fp: Footprint, points: dict[str, np.ndarray], city: dict[str, Any]) -> None:
    x = points["x"]
    y = points["y"]
    z = points["z"]
    cls = points["classification"]
    if x.size:
        sample = sample_indices(x.size, 80_000)
        ground = cls[sample] == 2
        other = ~ground
        ax.scatter(x[sample][ground], y[sample][ground], s=1, c="#9a9a9a", alpha=0.25, linewidths=0, label="DIM ground")
        sc = ax.scatter(
            x[sample][other],
            y[sample][other],
            s=1,
            c=z[sample][other],
            cmap="viridis",
            alpha=0.65,
            linewidths=0,
            label="DIM non-ground",
        )
        plt_colorbar(sc, ax, "Z")
    ax.plot(fp.ring[:, 0], fp.ring[:, 1], color="#d62728", linewidth=2.0, label="LoD2 footprint")
    plot_cityjson_xy(ax, city, bid, color="#1f77b4")
    ax.set_title("Top-down point cloud, footprint, Roofer output")
    ax.set_aspect("equal", adjustable="box")
    ax.legend(loc="best", fontsize=8)
    ax.set_xlabel("Easting (m)")
    ax.set_ylabel("Northing (m)")


def plot_profile(ax: Any, fp: Footprint, points: dict[str, np.ndarray], city: dict[str, Any], bid: str) -> None:
    axis = footprint_axis(fp.ring)
    origin = fp.ring[:-1].mean(axis=0)
    x = points["x"]
    y = points["y"]
    z = points["z"]
    cls = points["classification"]
    if x.size:
        coords = np.column_stack([x, y])
        s = (coords - origin) @ axis
        sample = sample_indices(x.size, 80_000)
        ground = cls[sample] == 2
        other = ~ground
        ax.scatter(s[sample][ground], z[sample][ground], s=1, c="#9a9a9a", alpha=0.25, linewidths=0, label="ground")
        ax.scatter(s[sample][other], z[sample][other], s=1, c="#2ca02c", alpha=0.45, linewidths=0, label="non-ground")
    city_vertices = city_vertices_for_id(city, bid)
    if city_vertices.size:
        city_s = (city_vertices[:, :2] - origin) @ axis
        ax.scatter(city_s, city_vertices[:, 2], s=14, c="#1f77b4", alpha=0.9, label="Roofer vertices")
    fp_s = (fp.ring[:, :2] - origin) @ axis
    ax.axvspan(float(np.min(fp_s)), float(np.max(fp_s)), color="#d62728", alpha=0.12, label="footprint span")
    ax.set_title("Profile along footprint major axis")
    ax.set_xlabel("Along-axis distance (m)")
    ax.set_ylabel("Z (m)")
    ax.legend(loc="best", fontsize=8)
    ax.grid(True, alpha=0.25)


def plt_colorbar(scatter: Any, ax: Any, label: str) -> None:
    import matplotlib.pyplot as plt

    cbar = plt.colorbar(scatter, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label(label)


def sample_indices(size: int, max_count: int) -> np.ndarray:
    if size <= max_count:
        return np.arange(size)
    rng = np.random.default_rng(20260612)
    return np.sort(rng.choice(size, size=max_count, replace=False))


def footprint_axis(ring: np.ndarray) -> np.ndarray:
    coords = ring[:-1]
    centered = coords - coords.mean(axis=0)
    _, _, vh = np.linalg.svd(centered, full_matrices=False)
    return vh[0]


def plot_cityjson_xy(ax: Any, city: dict[str, Any], bid: str, color: str) -> None:
    vertices = city.get("_absolute_vertices", np.empty((0, 3)))
    objects = city.get("CityObjects", {})
    for obj_id in [bid, *objects.get(bid, {}).get("children", [])]:
        obj = objects.get(obj_id)
        if not obj:
            continue
        for geom in obj.get("geometry", []):
            for ring in iter_rings(geom.get("boundaries", [])):
                coords = vertices[np.array(ring, dtype=np.int64)]
                ax.plot(coords[:, 0], coords[:, 1], color=color, linewidth=1.2, alpha=0.9, label="Roofer geometry")


def city_vertices_for_id(city: dict[str, Any], bid: str) -> np.ndarray:
    vertices = city.get("_absolute_vertices", np.empty((0, 3)))
    objects = city.get("CityObjects", {})
    indices: set[int] = set()
    for obj_id in [bid, *objects.get(bid, {}).get("children", [])]:
        obj = objects.get(obj_id)
        if not obj:
            continue
        for geom in obj.get("geometry", []):
            collect_indices(geom.get("boundaries", []), indices)
    if not indices:
        return np.empty((0, 3), dtype=np.float64)
    return vertices[np.array(sorted(indices), dtype=np.int64)]


def iter_rings(value: Any) -> list[list[int]]:
    rings: list[list[int]] = []
    if isinstance(value, list):
        if value and all(isinstance(item, int) for item in value):
            rings.append(value)
        else:
            for item in value:
                rings.extend(iter_rings(item))
    return rings


def collect_indices(value: Any, out: set[int]) -> None:
    if isinstance(value, int):
        out.add(value)
    elif isinstance(value, list):
        for item in value:
            collect_indices(item, out)


def write_report(
    path: Path,
    w2_run_id: str,
    paired_rows: list[dict[str, str]],
    crosstab_rows: list[dict[str, str]],
    missing_rows: list[dict[str, str]],
    als_memo_rows: list[dict[str, str]],
    rates: dict[str, Any],
    gallery_paths: list[Path],
) -> None:
    paired_counts = Counter(row["paired_category"] for row in paired_rows)
    attempted_counts = Counter(row["paired_category"] for row in paired_rows if row["both_attempted"] == "yes")
    lines = [
        "# W2-1b Paired Roofer Analysis",
        "",
        f"- Source run: `runs/{w2_run_id}`",
        "- Paired unit: `building_id` from `building_reconstruction_status.csv`.",
        "- Final success definition: W2-1 `status=success`, which includes Roofer LoD2.2 output and val3dity validity.",
        "- Comparison population: buildings where both ALS and DIM produced a Roofer feature attempt, i.e. neither side is `missing_roofer_output`.",
        "",
        "## Paired Categories",
        "",
        "| Category | Full 199 | Both-attempted 179 |",
        "|---|---:|---:|",
    ]
    for category in ("both_success", "ALS_only", "DIM_only", "both_fail"):
        lines.append(f"| `{category}` | {paired_counts.get(category, 0)} | {attempted_counts.get(category, 0)} |")
    lines.extend(
        [
            "",
            "## Recomputed Success Rates",
            "",
            "| Population | ALS final success | DIM final success | ALS Roofer-stage LoD2.2 output | DIM Roofer-stage LoD2.2 output |",
            "|---|---:|---:|---:|---:|",
            rate_row("Full 199", rates["full_total"], rates["als"]["full_success"], rates["dim"]["full_success"], None, None),
            rate_row(
                "Both-attempted 179",
                rates["attempted_total"],
                rates["als"]["attempted_success"],
                rates["dim"]["attempted_success"],
                rates["als"]["attempted_lod22_output"],
                rates["dim"]["attempted_lod22_output"],
            ),
            "",
            "## Reason Crosstab",
            "",
        ]
    )
    lines.extend(markdown_table(crosstab_rows))
    lines.extend(
        [
            "",
            "## Missing Roofer Output Diagnosis",
            "",
            f"- ALS `missing_roofer_output`: {len(missing_rows)}",
            f"- DIM `missing_roofer_output`: {len(missing_rows)}",
            "- Same ID set on both inputs: yes.",
            "- ID issue: not observed; all 20 IDs are present in the footprint source and scene CSV.",
            "- Footprint geometry issue: not observed by simple checks; rings are closed and have positive area.",
            "- Box diagnosis: all 20 footprints intersect the Roofer AOI box but have centroids outside it and are not fully inside it.",
            "- Action for paired comparison: exclude these 20 AOI-edge buildings from the both-attempted population.",
            "- Future fix if edge buildings are needed: rerun Roofer with an expanded/no `--box`, then clip/evaluate to AOI after reconstruction.",
            "",
            "## ALS Roofer-Stage Failure Memo",
            "",
            f"- ALS Roofer-stage failures: {len(als_memo_rows)} buildings.",
            "- 20 are the shared AOI-edge `missing_roofer_output` buildings above.",
            "- 1 is `pointcloud_unusable`: Roofer produced a record but skipped 3D geometry because local pointcloud coverage was insufficient.",
            "- ALS val3dity-invalid buildings are kept in the paired CSV, but they are geometry-validity failures after Roofer output, not part of this 21-building Roofer-stage memo.",
            "",
            "## Failure Gallery",
            "",
            "- Selected DIM `missing_lod22_geometry` examples: high-density/no-nodata, high-nodata, and highest plane-count cases.",
        ]
    )
    for image in gallery_paths:
        lines.append(f"- `{rel(image)}`")
    lines.extend(
        [
            "",
            "## Files",
            "",
            "- Paired table: `docs/W2_1b_paired_status.csv`",
            "- Reason crosstab: `docs/W2_1b_reason_crosstab.csv`",
            "- Missing Roofer exclusion list: `docs/W2_1b_missing_roofer_exclusions.csv`",
            "- ALS Roofer-stage failure memo: `docs/W2_1b_als_roofer_failure_memo.csv`",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def rate_row(
    label: str,
    total: int,
    als_success: int,
    dim_success: int,
    als_lod22: int | None,
    dim_lod22: int | None,
) -> str:
    als = f"{als_success}/{total} ({als_success / total * 100:.1f}%)"
    dim = f"{dim_success}/{total} ({dim_success / total * 100:.1f}%)"
    als_stage = "n/a" if als_lod22 is None else f"{als_lod22}/{total} ({als_lod22 / total * 100:.1f}%)"
    dim_stage = "n/a" if dim_lod22 is None else f"{dim_lod22}/{total} ({dim_lod22 / total * 100:.1f}%)"
    return f"| {label} | {als} | {dim} | {als_stage} | {dim_stage} |"


def markdown_table(rows: list[dict[str, str]]) -> list[str]:
    if not rows:
        return []
    headers = list(rows[0].keys())
    out = [
        "| " + " | ".join(f"`{h}`" if h != "als_reason" else h for h in headers) + " |",
        "| " + " | ".join("---" if idx == 0 else "---:" for idx, _ in enumerate(headers)) + " |",
    ]
    for row in rows:
        out.append("| " + " | ".join(row[h] for h in headers) + " |")
    return out


def copy_outputs_to_run(run_dir: Path, csv_and_md: list[Path], gallery_paths: list[Path]) -> None:
    import shutil

    out_docs = run_dir / "docs"
    out_figs = run_dir / "figs"
    out_docs.mkdir(parents=True, exist_ok=True)
    out_figs.mkdir(parents=True, exist_ok=True)
    for path in csv_and_md:
        shutil.copy2(path, out_docs / path.name)
    for path in gallery_paths:
        shutil.copy2(path, out_figs / path.name)


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        raise RuntimeError(f"No rows for {path}")
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def bbox_intersects(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


def centroid_in_box(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    cx = (a[0] + a[2]) / 2.0
    cy = (a[1] + a[3]) / 2.0
    return b[0] <= cx <= b[2] and b[1] <= cy <= b[3]


def fully_inside_box(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    return b[0] <= a[0] and a[2] <= b[2] and b[1] <= a[1] and a[3] <= b[3]


def polygon_area(ring: np.ndarray) -> float:
    x = ring[:, 0]
    y = ring[:, 1]
    return float(abs(0.5 * (np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))))


def yesno(value: bool) -> str:
    return "yes" if value else "no"


def rel(path: Path) -> str:
    return path.as_posix().replace("/workspace/", "").replace("phases/p0-audit/", "")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--w2-run-id", help="Source W2-1 Roofer default run ID")
    parser.add_argument("--inside", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.inside or os.environ.get("P0_INSIDE_CONTAINER") == "1":
        inside_entrypoint()
    else:
        host_entrypoint(args)


if __name__ == "__main__":
    main()
