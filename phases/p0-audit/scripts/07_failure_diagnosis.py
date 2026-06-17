#!/usr/bin/env python3
"""T7 post-audit diagnosis for DIM-only roof-matching failures.

Run from phases/p0-audit/. Host mode re-runs this script inside the P0 tools
container so LAZ/GIS dependencies stay in the recorded audit toolchain.
"""

from __future__ import annotations

import csv
import json
import math
import os
import shutil
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


TASK_ID = "T7"
BUILDING_CLASS = 6
GRID_CELL_M = 1.0
MIN_PLANE_POINTS = 20
SURFACE_POINT_QUANTILE = 0.10
HOLE_QUANTILE = 0.90
PLANE_RMSE_QUANTILE = 0.90
VIEW_COUNT_QUANTILE = 0.10
INCIDENCE_QUANTILE = 0.90
MAX_VISIBLE_SAMPLE_POINTS = 60
GRAZING_INCIDENT_ANGLE_DEG = 75.0
CANONICAL_RUN = "w3_2b_roofer_repeatability_20260612_220747/run_2"


@dataclass
class Camera:
    image_id: int
    name: str
    qvec: np.ndarray
    tvec: np.ndarray
    rot: np.ndarray
    center_canonical: np.ndarray
    center_base: np.ndarray


@dataclass
class CameraModel:
    width: int
    height: int
    params: np.ndarray


@dataclass
class Footprint:
    building_id: str
    area_m2: float
    bbox: tuple[float, float, float, float]
    ring: np.ndarray


@dataclass
class Cloud:
    label: str
    paths: list[Path]
    x: np.ndarray
    y: np.ndarray
    z: np.ndarray
    classification: np.ndarray
    crs_text: str


@dataclass
class SurfaceMetric:
    point_count: int
    density_pts_m2: float
    hole_ratio: float
    plane_rmse_m: float
    roof_z_median: float
    roof_z_p90: float
    normal: np.ndarray | None


def host_entrypoint() -> None:
    repo = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.setdefault("P0_UID", str(os.getuid()))
    env.setdefault("P0_GID", str(os.getgid()))
    run_id = env.get("RUN_ID") or datetime.now().strftime("t7_failure_diagnosis_%Y%m%d_%H%M%S")
    git_commit = capture(["git", "rev-parse", "--short", "HEAD"], cwd=repo.parent).strip()
    run_dir = repo / "runs" / run_id
    logs_dir = run_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    write_host_config(run_dir, run_id, git_commit)
    compose = ["docker", "compose", "-f", str(repo / "env/docker-compose.p0.yml")]
    if env.get("SKIP_BUILD") != "1":
        run(compose + ["build", "tools"], cwd=repo, env=env, log_path=logs_dir / "build_tools.log")
    write_host_versions(repo, run_dir, compose, env, git_commit)
    try:
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
                f"P0_GIT_COMMIT={git_commit}",
                "tools",
                "python",
                "/workspace/scripts/07_failure_diagnosis.py",
                "--mode",
                "compute",
            ],
            cwd=repo,
            env=env,
            log_path=logs_dir / "compute.log",
        )
    except subprocess.CalledProcessError as exc:
        record_issue(repo, run_id, f"failed with exit code {exc.returncode}")
        raise

    print(f"run_id={run_id}")
    print(f"run_dir=runs/{run_id}")
    print("report=docs/W3_failure_diagnosis.md")


def compute_entrypoint() -> None:
    root = Path("/workspace")
    docs = root / "docs"
    data = root / "data"
    figs = docs / "figs"
    package = docs / "G1_package"
    package_figs = package / "figs"
    run_id = os.environ["RUN_ID"]
    run_dir = root / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    figs.mkdir(parents=True, exist_ok=True)

    paired = read_csv(docs / "W3_2c_canonical_paired_status.csv")
    failure_ids = [
        row["building_id"]
        for row in paired
        if row["coverage_control_population"] == "yes"
        and row["dim_failure_bucket_v1"] == "roof_matching_assembly_failure"
    ]
    control_ids = [
        row["building_id"]
        for row in paired
        if row["coverage_control_population"] == "yes" and row["paired_category"] == "both_success"
    ]
    if len(failure_ids) != 8:
        raise RuntimeError(f"Expected 8 canonical DIM-only roof-matching failures, got {len(failure_ids)}")
    if len(control_ids) != 71:
        raise RuntimeError(f"Expected 71 coverage-control both-success buildings, got {len(control_ids)}")

    paired_by_id = {row["building_id"]: row for row in paired}
    footprints = load_footprints(data / "work/footprints/lod2_ground_plan.geojson", set(failure_ids + control_ids))
    all_scene_footprints = load_footprints(
        data / "work/footprints/lod2_ground_plan.geojson",
        {row["building_id"] for row in paired if row["footprint_bbox_intersects_box"] == "yes"},
    )
    assert_epsg25832_footprints(footprints)
    bbox = combined_bbox(list(footprints.values()), buffer_m=12.0)

    dim_path = data / "work/w2/dim_v1_classified_z_minus0p174.laz"
    if not dim_path.exists():
        dim_path = data / "work/classify/dim_v1_classified_z.laz"
    dim_cloud = read_cloud("DIM", [dim_path], bbox)
    als_cloud = read_cloud("ALS", sorted((data / "raw/als").glob("*.laz")), bbox)
    assert_epsg25832_cloud("DIM", dim_cloud)
    assert_epsg25832_cloud("ALS", als_cloud)

    camera_model = parse_camera_model(data / "work/colmap/sparse/0/cameras.txt")
    scene_ref = read_json(data / "work/opf/opf/scene_reference_frame.json")
    cameras = parse_colmap_cameras(data / "work/colmap/sparse/0/images.txt", scene_ref)
    assert_epsg25832_camera_range(cameras)

    surface_by_id: dict[str, dict[str, SurfaceMetric]] = {}
    for bid, footprint in footprints.items():
        surface_by_id[bid] = {
            "DIM": surface_metrics(dim_cloud, footprint),
            "ALS": surface_metrics(als_cloud, footprint),
        }

    occluder_heights = {
        bid: surface_metrics(als_cloud, footprint).roof_z_p90
        for bid, footprint in all_scene_footprints.items()
        if intersects_bbox(footprint.bbox, bbox)
    }

    rows: list[dict[str, str]] = []
    numeric_rows: list[dict[str, Any]] = []
    for bid in failure_ids + control_ids:
        footprint = footprints[bid]
        dim = surface_by_id[bid]["DIM"]
        als = surface_by_id[bid]["ALS"]
        roof_z = finite_or(als.roof_z_median, dim.roof_z_median)
        normal = als.normal if als.normal is not None else dim.normal
        visibility = visibility_metrics(
            footprint=footprint,
            roof_z=roof_z,
            normal=normal,
            cameras=cameras,
            camera_model=camera_model,
            scene_ref=scene_ref,
            occluder_footprints=all_scene_footprints,
            occluder_heights=occluder_heights,
        )
        cohort = "failure_8" if bid in failure_ids else "control_success_71"
        pair = paired_by_id[bid]
        numeric = {
            "building_id": bid,
            "cohort": cohort,
            "footprint_area_m2": footprint.area_m2,
            "dim_point_count": dim.point_count,
            "dim_density_pts_m2": dim.density_pts_m2,
            "dim_hole_ratio": dim.hole_ratio,
            "dim_plane_rmse_m": dim.plane_rmse_m,
            "als_point_count": als.point_count,
            "als_density_pts_m2": als.density_pts_m2,
            "als_hole_ratio": als.hole_ratio,
            "als_plane_rmse_m": als.plane_rmse_m,
            "view_count": visibility["view_count"],
            "median_incidence_deg": visibility["median_incidence_deg"],
            "median_in_frame_sample_fraction": visibility["median_in_frame_sample_fraction"],
            "occlusion_risk_view_fraction": visibility["occlusion_risk_view_fraction"],
            "paired_category": pair["paired_category"],
            "dim_reason": pair["dim_reason"],
        }
        numeric_rows.append(numeric)

    thresholds = derive_thresholds([row for row in numeric_rows if row["cohort"] == "control_success_71"])
    for numeric in numeric_rows:
        if numeric["cohort"] == "failure_8":
            classification, surface_recoverable, classification_note = classify_case(numeric, thresholds)
        else:
            classification = "control_success"
            surface_recoverable = ""
            classification_note = "Control-success row used only for threshold distribution."
        numeric["classification"] = classification
        numeric["surface_forming_recoverable"] = surface_recoverable
        numeric["classification_note"] = classification_note
        rows.append(format_metric_row(numeric))

    failure_rows = [row for row in rows if row["cohort"] == "failure_8"]
    control_summary = summarize_control([row for row in numeric_rows if row["cohort"] == "control_success_71"])
    threshold_rows = format_threshold_rows(thresholds)
    class_counts = Counter(row["classification"] for row in failure_rows)
    recoverable_count = sum(row["surface_forming_recoverable"] == "yes" for row in failure_rows)
    observation_limited_count = class_counts["관측부족"]

    metrics_csv = docs / "W3_failure_diagnosis_building_metrics.csv"
    control_csv = docs / "W3_failure_diagnosis_control_summary.csv"
    thresholds_csv = docs / "W3_failure_diagnosis_thresholds.csv"
    metrics_json = data / "work/diagnose/t7_failure_diagnosis_metrics.json"
    point_fig = figs / "w3_failure_t7_point_clips.png"
    count_fig = figs / "w3_failure_t7_classification_counts.png"
    report_md = docs / "W3_failure_diagnosis.md"

    write_csv(metrics_csv, rows)
    write_csv(control_csv, control_summary)
    write_csv(thresholds_csv, threshold_rows)
    write_metrics_json(metrics_json, run_id, failure_ids, control_ids, thresholds, numeric_rows)
    render_point_clip_figure(
        point_fig,
        failure_ids,
        footprints,
        surface_by_id,
        dim_cloud,
        als_cloud,
    )
    render_classification_counts(count_fig, class_counts)
    write_report(
        report_md,
        run_id,
        run_dir,
        failure_rows,
        control_summary,
        threshold_rows,
        point_fig,
        count_fig,
        metrics_csv,
        control_csv,
        thresholds_csv,
        metrics_json,
        recoverable_count,
        observation_limited_count,
        class_counts,
    )
    add_to_g1_package(
        package,
        package_figs,
        report_md,
        metrics_csv,
        control_csv,
        thresholds_csv,
        point_fig,
        count_fig,
    )
    copy_outputs(
        run_dir,
        [
            report_md,
            metrics_csv,
            control_csv,
            thresholds_csv,
            metrics_json,
            point_fig,
            count_fig,
            package / "W3_failure_diagnosis.md",
            package / "t7_failure_diagnosis_building_metrics.csv",
            package / "t7_failure_diagnosis_control_summary.csv",
            package / "t7_failure_diagnosis_thresholds.csv",
            package_figs / "fig_10_t7_failure_point_clips.png",
            package_figs / "fig_11_t7_failure_classification_counts.png",
            package / "manifest.json",
        ],
    )

    print(f"failure_ids={','.join(failure_ids)}")
    print(f"control_success_n={len(control_ids)}")
    print(f"surface_forming_recoverable={recoverable_count}")
    print(f"observation_limited={observation_limited_count}")
    print(f"class_counts={dict(class_counts)}")
    print(f"report={rel(report_md)}")
    print(f"metrics={rel(metrics_csv)}")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


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
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout).strip())
    return proc.stdout


def record_issue(repo: Path, run_id: str, message: str) -> None:
    issues = repo / "docs/issues.md"
    with issues.open("a", encoding="utf-8") as fh:
        fh.write(f"\n## {TASK_ID} Failure Diagnosis\n\n")
        fh.write(f"- {run_id}: {message}. See runs/{run_id}/logs/.\n")


def write_host_config(run_dir: Path, run_id: str, git_commit: str) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "config.yaml").write_text(
        "\n".join(
            [
                f"task_id: {TASK_ID}",
                f"run_id: {run_id}",
                f"git_commit: {git_commit}",
                "canonical_run: " + CANONICAL_RUN,
                "dim_pointcloud: data/work/w2/dim_v1_classified_z_minus0p174.laz",
                "als_pointcloud: data/raw/als/*.laz",
                "footprints: data/work/footprints/lod2_ground_plan.geojson",
                "colmap_poses: data/work/colmap/sparse/0/images.txt",
                "crs: EPSG:25832 numeric UTM32 coordinates",
                f"grid_cell_m: {GRID_CELL_M}",
                "classification_rule: control-success quantile thresholds; no P0 judgement",
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_host_versions(
    repo: Path,
    run_dir: Path,
    compose: list[str],
    env: dict[str, str],
    git_commit: str,
) -> None:
    lines = [
        "# T7 Failure Diagnosis Tool Versions",
        "",
        f"- Generated: {datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')}",
        f"- Run ID: {run_dir.name}",
        f"- Repository commit: {git_commit}",
        "",
        "```console",
    ]
    version_cmds = [
        ["git", "status", "--short", "--branch"],
        compose + ["run", "-T", "--rm", "tools", "python", "--version"],
        compose
        + [
            "run",
            "-T",
            "--rm",
            "tools",
            "python",
            "-c",
            "import laspy, matplotlib, numpy, shapely; print('laspy=' + laspy.__version__); print('matplotlib=' + matplotlib.__version__); print('numpy=' + numpy.__version__); print('shapely=' + shapely.__version__)",
        ],
        compose + ["run", "-T", "--rm", "tools", "pdal", "--version"],
    ]
    for cmd in version_cmds:
        proc = subprocess.run(cmd, cwd=repo, env=env, text=True, capture_output=True, check=False)
        lines.append("$ " + " ".join(cmd))
        out = (proc.stdout or proc.stderr).strip()
        if out:
            lines.append(out)
        if proc.returncode != 0:
            lines.append(f"[exit {proc.returncode}]")
    lines.append("```")
    (run_dir / "versions.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_footprints(path: Path, building_ids: set[str]) -> dict[str, Footprint]:
    data = read_json(path)
    output: dict[str, Footprint] = {}
    for feature in data["features"]:
        props = feature["properties"]
        bid = props["building_id"]
        if bid not in building_ids:
            continue
        ring = np.array(feature["geometry"]["coordinates"][0], dtype=np.float64)
        if ring.shape[0] < 4:
            continue
        if not np.allclose(ring[0], ring[-1]):
            ring = np.vstack([ring, ring[0]])
        output[bid] = Footprint(
            building_id=bid,
            area_m2=float(props["area_m2"]),
            bbox=(
                float(props["min_x"]),
                float(props["min_y"]),
                float(props["max_x"]),
                float(props["max_y"]),
            ),
            ring=ring,
        )
    missing = sorted(building_ids - output.keys())
    if missing:
        raise RuntimeError(f"Missing footprints: {', '.join(missing)}")
    return output


def assert_epsg25832_footprints(footprints: dict[str, Footprint]) -> None:
    xs = np.array([value for fp in footprints.values() for value in (fp.bbox[0], fp.bbox[2])])
    ys = np.array([value for fp in footprints.values() for value in (fp.bbox[1], fp.bbox[3])])
    if not np.all((100000.0 <= xs) & (xs <= 900000.0)):
        raise AssertionError("Footprint easting values are outside UTM zone 32 numeric range")
    if not np.all((5_000_000.0 <= ys) & (ys <= 6_200_000.0)):
        raise AssertionError("Footprint northing values are outside Germany UTM northing range")


def combined_bbox(footprints: list[Footprint], buffer_m: float) -> tuple[float, float, float, float]:
    return (
        min(fp.bbox[0] for fp in footprints) - buffer_m,
        min(fp.bbox[1] for fp in footprints) - buffer_m,
        max(fp.bbox[2] for fp in footprints) + buffer_m,
        max(fp.bbox[3] for fp in footprints) + buffer_m,
    )


def intersects_bbox(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    return a[2] >= b[0] and a[0] <= b[2] and a[3] >= b[1] and a[1] <= b[3]


def read_cloud(label: str, paths: list[Path], bbox: tuple[float, float, float, float]) -> Cloud:
    import laspy

    xs: list[np.ndarray] = []
    ys: list[np.ndarray] = []
    zs: list[np.ndarray] = []
    classes: list[np.ndarray] = []
    crs_text = ""
    min_x, min_y, max_x, max_y = bbox
    for path in paths:
        if not path.exists():
            raise FileNotFoundError(path)
        with laspy.open(path) as fh:
            if not crs_text:
                crs = fh.header.parse_crs()
                crs_text = crs.to_string() if crs else ""
            for points in fh.chunk_iterator(1_000_000):
                x = np.asarray(points.x)
                y = np.asarray(points.y)
                mask = (x >= min_x) & (x <= max_x) & (y >= min_y) & (y <= max_y)
                if not np.any(mask):
                    continue
                xs.append(x[mask].astype(np.float64, copy=False))
                ys.append(y[mask].astype(np.float64, copy=False))
                zs.append(np.asarray(points.z)[mask].astype(np.float64, copy=False))
                if hasattr(points, "classification"):
                    classes.append(np.asarray(points.classification, dtype=np.uint8)[mask])
                else:
                    classes.append(np.zeros(int(np.count_nonzero(mask)), dtype=np.uint8))
    if not xs:
        raise RuntimeError(f"No {label} points overlap T7 target bbox")
    return Cloud(
        label=label,
        paths=paths,
        x=np.concatenate(xs),
        y=np.concatenate(ys),
        z=np.concatenate(zs),
        classification=np.concatenate(classes),
        crs_text=crs_text,
    )


def assert_epsg25832_cloud(label: str, cloud: Cloud) -> None:
    x_med = float(np.median(cloud.x))
    y_med = float(np.median(cloud.y))
    if not (100000.0 <= x_med <= 900000.0 and 5_000_000.0 <= y_med <= 6_200_000.0):
        raise AssertionError(f"{label} point cloud is not in EPSG:25832 numeric range")
    if not cloud.crs_text:
        print(f"{label} CRS tag is empty; accepted by numeric UTM32 range and T5 footprint alignment.", flush=True)
        return
    crs_text = cloud.crs_text.upper()
    accepted = ("25832" in crs_text) or ("ETRS89" in crs_text) or ("UTM ZONE 32N" in crs_text)
    if not accepted:
        raise AssertionError(f"{label} CRS is not tagged as EPSG:25832/ETRS89 UTM32: {cloud.crs_text}")


def points_in_polygon(xs: np.ndarray, ys: np.ndarray, ring: np.ndarray) -> np.ndarray:
    inside = np.zeros(xs.shape, dtype=bool)
    for idx in range(ring.shape[0] - 1):
        x1, y1 = ring[idx]
        x2, y2 = ring[idx + 1]
        crossing = (y1 > ys) != (y2 > ys)
        if not np.any(crossing):
            continue
        x_at_y = (x2 - x1) * (ys[crossing] - y1) / (y2 - y1) + x1
        inside[crossing] ^= xs[crossing] < x_at_y
    return inside


def clip_building_points(cloud: Cloud, footprint: Footprint) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    min_x, min_y, max_x, max_y = footprint.bbox
    mask = (
        (cloud.classification == BUILDING_CLASS)
        & (cloud.x >= min_x)
        & (cloud.x <= max_x)
        & (cloud.y >= min_y)
        & (cloud.y <= max_y)
    )
    if not np.any(mask):
        return np.array([]), np.array([]), np.array([])
    x = cloud.x[mask]
    y = cloud.y[mask]
    z = cloud.z[mask]
    inside = points_in_polygon(x, y, footprint.ring)
    return x[inside], y[inside], z[inside]


def surface_metrics(cloud: Cloud, footprint: Footprint) -> SurfaceMetric:
    x, y, z = clip_building_points(cloud, footprint)
    if z.size == 0:
        return SurfaceMetric(0, 0.0, 1.0, math.nan, math.nan, math.nan, None)
    density = float(z.size / footprint.area_m2)
    hole_ratio = grid_hole_ratio(x, y, footprint)
    plane_rmse, normal = fit_plane(x, y, z)
    roof_z_median = float(np.median(z))
    roof_z_p90 = float(np.percentile(z, 90.0))
    return SurfaceMetric(
        point_count=int(z.size),
        density_pts_m2=density,
        hole_ratio=hole_ratio,
        plane_rmse_m=plane_rmse,
        roof_z_median=roof_z_median,
        roof_z_p90=roof_z_p90,
        normal=normal,
    )


def grid_hole_ratio(x: np.ndarray, y: np.ndarray, footprint: Footprint) -> float:
    min_x, min_y, max_x, max_y = footprint.bbox
    xs = np.arange(min_x + GRID_CELL_M * 0.5, max_x, GRID_CELL_M)
    ys = np.arange(min_y + GRID_CELL_M * 0.5, max_y, GRID_CELL_M)
    if xs.size == 0 or ys.size == 0:
        return 0.0 if x.size else 1.0
    grid_x, grid_y = np.meshgrid(xs, ys)
    inside = points_in_polygon(grid_x.ravel(), grid_y.ravel(), footprint.ring)
    total = int(np.count_nonzero(inside))
    if total == 0:
        return 0.0 if x.size else 1.0
    ix = np.floor((x - min_x) / GRID_CELL_M).astype(np.int64)
    iy = np.floor((y - min_y) / GRID_CELL_M).astype(np.int64)
    occupied = {(int(a), int(b)) for a, b in zip(ix, iy)}
    grid_ix = np.floor((grid_x.ravel()[inside] - min_x) / GRID_CELL_M).astype(np.int64)
    grid_iy = np.floor((grid_y.ravel()[inside] - min_y) / GRID_CELL_M).astype(np.int64)
    filled = sum((int(a), int(b)) in occupied for a, b in zip(grid_ix, grid_iy))
    return float(1.0 - filled / total)


def fit_plane(x: np.ndarray, y: np.ndarray, z: np.ndarray) -> tuple[float, np.ndarray | None]:
    if z.size < MIN_PLANE_POINTS:
        return math.nan, None
    cutoff = float(np.percentile(z, 35.0))
    roof = z >= cutoff
    if np.count_nonzero(roof) >= MIN_PLANE_POINTS:
        x = x[roof]
        y = y[roof]
        z = z[roof]
    cx = float(np.mean(x))
    cy = float(np.mean(y))
    design = np.column_stack([x - cx, y - cy, np.ones_like(x)])
    coef, *_ = np.linalg.lstsq(design, z, rcond=None)
    residuals = z - design @ coef
    keep_cutoff = float(np.percentile(np.abs(residuals), 95.0))
    keep = np.abs(residuals) <= keep_cutoff
    if np.count_nonzero(keep) >= MIN_PLANE_POINTS:
        design = design[keep]
        z = z[keep]
        coef, *_ = np.linalg.lstsq(design, z, rcond=None)
        residuals = z - design @ coef
    a, b, _ = coef
    normal = np.array([-a, -b, 1.0], dtype=np.float64)
    normal /= np.linalg.norm(normal)
    if normal[2] < 0.0:
        normal = -normal
    return float(np.sqrt(np.mean(residuals**2))), normal


def qvec_to_rotmat(qvec: np.ndarray) -> np.ndarray:
    q0, q1, q2, q3 = qvec
    return np.array(
        [
            [1 - 2 * q2 * q2 - 2 * q3 * q3, 2 * q1 * q2 - 2 * q0 * q3, 2 * q3 * q1 + 2 * q0 * q2],
            [2 * q1 * q2 + 2 * q0 * q3, 1 - 2 * q1 * q1 - 2 * q3 * q3, 2 * q2 * q3 - 2 * q0 * q1],
            [2 * q3 * q1 - 2 * q0 * q2, 2 * q2 * q3 + 2 * q0 * q1, 1 - 2 * q1 * q1 - 2 * q2 * q2],
        ],
        dtype=np.float64,
    )


def base_to_canonical(points: np.ndarray, scene_ref: dict[str, Any]) -> np.ndarray:
    transform = scene_ref.get("base_to_canonical", {})
    arr = points.copy()
    if transform.get("swap_xy", False):
        arr[:, [0, 1]] = arr[:, [1, 0]]
    shift = np.array(transform.get("shift", [0.0, 0.0, 0.0]), dtype=np.float64)
    scale = np.array(transform.get("scale", [1.0, 1.0, 1.0]), dtype=np.float64)
    return (arr + shift) * scale


def canonical_to_base(points: np.ndarray, scene_ref: dict[str, Any]) -> np.ndarray:
    transform = scene_ref.get("base_to_canonical", {})
    scale = np.array(transform.get("scale", [1.0, 1.0, 1.0]), dtype=np.float64)
    shift = np.array(transform.get("shift", [0.0, 0.0, 0.0]), dtype=np.float64)
    arr = points / scale - shift
    if transform.get("swap_xy", False):
        arr[:, [0, 1]] = arr[:, [1, 0]]
    return arr


def parse_camera_model(path: Path) -> CameraModel:
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            parts = stripped.split()
            if parts[1] != "FULL_OPENCV":
                raise RuntimeError(f"Expected FULL_OPENCV camera model, got {parts[1]}")
            return CameraModel(
                width=int(parts[2]),
                height=int(parts[3]),
                params=np.array([float(value) for value in parts[4:]], dtype=np.float64),
            )
    raise RuntimeError(f"No camera model found in {path}")


def parse_colmap_cameras(path: Path, scene_ref: dict[str, Any]) -> list[Camera]:
    lines: list[str] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                lines.append(stripped)
    if len(lines) % 2 != 0:
        raise RuntimeError(f"Unexpected COLMAP image line count: {len(lines)}")
    cameras: list[Camera] = []
    for idx in range(0, len(lines), 2):
        parts = lines[idx].split()
        qvec = np.array([float(value) for value in parts[1:5]], dtype=np.float64)
        tvec = np.array([float(value) for value in parts[5:8]], dtype=np.float64)
        rot = qvec_to_rotmat(qvec)
        center_canonical = -rot.T @ tvec
        center_base = canonical_to_base(center_canonical.reshape(1, 3), scene_ref)[0]
        cameras.append(
            Camera(
                image_id=int(parts[0]),
                name=" ".join(parts[9:]),
                qvec=qvec,
                tvec=tvec,
                rot=rot,
                center_canonical=center_canonical,
                center_base=center_base,
            )
        )
    return cameras


def assert_epsg25832_camera_range(cameras: list[Camera]) -> None:
    centers = np.vstack([camera.center_base for camera in cameras])
    if not np.all((100000.0 <= centers[:, 0]) & (centers[:, 0] <= 900000.0)):
        raise AssertionError("Camera easting values are outside UTM zone 32 numeric range")
    if not np.all((5_000_000.0 <= centers[:, 1]) & (centers[:, 1] <= 6_200_000.0)):
        raise AssertionError("Camera northing values are outside Germany UTM northing range")


def footprint_sample_points(footprint: Footprint, roof_z: float) -> np.ndarray:
    ring = footprint.ring[:-1]
    points = [ring]
    edge_points = []
    for idx in range(ring.shape[0]):
        p1 = ring[idx]
        p2 = ring[(idx + 1) % ring.shape[0]]
        edge_points.extend([p1 * 0.75 + p2 * 0.25, p1 * 0.5 + p2 * 0.5, p1 * 0.25 + p2 * 0.75])
    points.append(np.array(edge_points, dtype=np.float64))
    centroid = np.mean(ring, axis=0).reshape(1, 2)
    points.append(centroid)
    xy = np.vstack(points)
    if xy.shape[0] > MAX_VISIBLE_SAMPLE_POINTS:
        idx = np.linspace(0, xy.shape[0] - 1, MAX_VISIBLE_SAMPLE_POINTS, dtype=np.int64)
        xy = xy[idx]
    return np.column_stack([xy, np.full(xy.shape[0], roof_z, dtype=np.float64)])


def project_points(points_base: np.ndarray, camera: Camera, camera_model: CameraModel, scene_ref: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    points_canonical = base_to_canonical(points_base, scene_ref)
    cam = (camera.rot @ points_canonical.T).T + camera.tvec
    in_front = cam[:, 2] > 0.1
    u = np.full(points_base.shape[0], np.nan, dtype=np.float64)
    v = np.full(points_base.shape[0], np.nan, dtype=np.float64)
    if not np.any(in_front):
        return np.column_stack([u, v]), in_front
    fx, fy, cx, cy, k1, k2, p1, p2, k3, k4, k5, k6 = camera_model.params[:12]
    x = cam[in_front, 0] / cam[in_front, 2]
    y = cam[in_front, 1] / cam[in_front, 2]
    r2 = x * x + y * y
    r4 = r2 * r2
    r6 = r4 * r2
    denom = 1.0 + k4 * r2 + k5 * r4 + k6 * r6
    denom = np.where(np.abs(denom) < 1e-12, 1.0, denom)
    radial = (1.0 + k1 * r2 + k2 * r4 + k3 * r6) / denom
    xd = x * radial + 2.0 * p1 * x * y + p2 * (r2 + 2.0 * x * x)
    yd = y * radial + p1 * (r2 + 2.0 * y * y) + 2.0 * p2 * x * y
    u[in_front] = fx * xd + cx
    v[in_front] = fy * yd + cy
    return np.column_stack([u, v]), in_front


def visibility_metrics(
    footprint: Footprint,
    roof_z: float,
    normal: np.ndarray | None,
    cameras: list[Camera],
    camera_model: CameraModel,
    scene_ref: dict[str, Any],
    occluder_footprints: dict[str, Footprint],
    occluder_heights: dict[str, float],
) -> dict[str, float]:
    if not np.isfinite(roof_z):
        return {
            "view_count": 0,
            "median_incidence_deg": math.nan,
            "median_in_frame_sample_fraction": math.nan,
            "occlusion_risk_view_fraction": math.nan,
        }
    samples = footprint_sample_points(footprint, roof_z)
    centroid_xy = np.mean(footprint.ring[:-1], axis=0)
    centroid = np.array([centroid_xy[0], centroid_xy[1], roof_z], dtype=np.float64)
    normal_vec = normal if normal is not None else np.array([0.0, 0.0, 1.0], dtype=np.float64)

    incidence_angles: list[float] = []
    in_frame_fractions: list[float] = []
    occlusion_flags: list[bool] = []
    for camera in cameras:
        projected, in_front = project_points(samples, camera, camera_model, scene_ref)
        in_frame = (
            in_front
            & (projected[:, 0] >= 0.0)
            & (projected[:, 0] < camera_model.width)
            & (projected[:, 1] >= 0.0)
            & (projected[:, 1] < camera_model.height)
        )
        fraction = float(np.count_nonzero(in_frame) / samples.shape[0])
        if fraction < 0.35:
            continue
        view_vec = camera.center_base - centroid
        norm = float(np.linalg.norm(view_vec))
        if norm <= 0.0:
            continue
        unit = view_vec / norm
        cos_incidence = float(np.clip(np.dot(unit, normal_vec), -1.0, 1.0))
        angle = math.degrees(math.acos(abs(cos_incidence)))
        incidence_angles.append(angle)
        in_frame_fractions.append(fraction)
        occlusion_flags.append(
            approximate_occlusion_risk(
                camera.center_base,
                centroid,
                footprint.building_id,
                occluder_footprints,
                occluder_heights,
            )
        )

    view_count = len(incidence_angles)
    return {
        "view_count": float(view_count),
        "median_incidence_deg": float(np.median(incidence_angles)) if incidence_angles else math.nan,
        "median_in_frame_sample_fraction": float(np.median(in_frame_fractions)) if in_frame_fractions else math.nan,
        "occlusion_risk_view_fraction": (
            float(sum(occlusion_flags) / len(occlusion_flags)) if occlusion_flags else math.nan
        ),
    }


def approximate_occlusion_risk(
    camera_center: np.ndarray,
    target: np.ndarray,
    target_id: str,
    occluder_footprints: dict[str, Footprint],
    occluder_heights: dict[str, float],
) -> bool:
    from shapely.geometry import LineString, Polygon

    line = LineString([(camera_center[0], camera_center[1]), (target[0], target[1])])
    horizontal_len = line.length
    if horizontal_len <= 0.0:
        return False
    for bid, footprint in occluder_footprints.items():
        if bid == target_id:
            continue
        height = occluder_heights.get(bid, math.nan)
        if not np.isfinite(height):
            continue
        poly = Polygon(footprint.ring)
        if not line.intersects(poly):
            continue
        distance = line.project(poly.centroid)
        if distance <= 1.0 or distance >= horizontal_len - 1.0:
            continue
        line_z = camera_center[2] + (target[2] - camera_center[2]) * (distance / horizontal_len)
        if height > line_z - 0.5:
            return True
    return False


def finite_or(primary: float, fallback: float) -> float:
    return primary if np.isfinite(primary) else fallback


def percentile(values: list[float], q: float) -> float:
    arr = np.array([value for value in values if np.isfinite(value)], dtype=np.float64)
    return float(np.percentile(arr, q)) if arr.size else math.nan


def derive_thresholds(control_rows: list[dict[str, Any]]) -> dict[str, float]:
    return {
        "density_min_pts_m2": percentile([row["dim_density_pts_m2"] for row in control_rows], SURFACE_POINT_QUANTILE * 100.0),
        "hole_ratio_max": percentile([row["dim_hole_ratio"] for row in control_rows], HOLE_QUANTILE * 100.0),
        "plane_rmse_max_m": percentile([row["dim_plane_rmse_m"] for row in control_rows], PLANE_RMSE_QUANTILE * 100.0),
        "view_count_min": percentile([row["view_count"] for row in control_rows], VIEW_COUNT_QUANTILE * 100.0),
        "incidence_max_deg": min(
            GRAZING_INCIDENT_ANGLE_DEG,
            percentile([row["median_incidence_deg"] for row in control_rows], INCIDENCE_QUANTILE * 100.0),
        ),
        "occlusion_risk_max_fraction": 0.50,
    }


def classify_case(row: dict[str, Any], thresholds: dict[str, float]) -> tuple[str, str, str]:
    surface_density_ok = row["dim_density_pts_m2"] >= thresholds["density_min_pts_m2"]
    surface_holes_ok = row["dim_hole_ratio"] <= thresholds["hole_ratio_max"]
    surface_plane_ok = (
        not np.isfinite(row["dim_plane_rmse_m"]) or row["dim_plane_rmse_m"] <= thresholds["plane_rmse_max_m"]
    )
    view_count_ok = row["view_count"] >= thresholds["view_count_min"]
    incidence_ok = (
        not np.isfinite(row["median_incidence_deg"])
        or row["median_incidence_deg"] <= thresholds["incidence_max_deg"]
    )
    occlusion_ok = (
        not np.isfinite(row["occlusion_risk_view_fraction"])
        or row["occlusion_risk_view_fraction"] <= thresholds["occlusion_risk_max_fraction"]
    )
    if surface_density_ok and surface_holes_ok and surface_plane_ok:
        return "구조화부족", "no", "DIM class-6 surface is control-like, but Roofer did not form LoD2.2 geometry."
    if not view_count_ok or not incidence_ok or not occlusion_ok:
        reasons = []
        if not view_count_ok:
            reasons.append("view_count below control threshold")
        if not incidence_ok:
            reasons.append("median incidence is grazing")
        if not occlusion_ok:
            reasons.append("approximate occlusion risk is high")
        return "관측부족", "no", "; ".join(reasons)
    return "증거부족", "yes", "Views are control-like, but DIM class-6 density/hole/residual surface evidence is below threshold."


def format_metric_row(row: dict[str, Any]) -> dict[str, str]:
    return {
        "building_id": row["building_id"],
        "cohort": row["cohort"],
        "footprint_area_m2": fmt(row["footprint_area_m2"], 3),
        "dim_point_count": str(int(row["dim_point_count"])),
        "dim_density_pts_m2": fmt(row["dim_density_pts_m2"], 3),
        "dim_hole_ratio": fmt(row["dim_hole_ratio"], 3),
        "dim_plane_rmse_m": fmt(row["dim_plane_rmse_m"], 3),
        "als_density_pts_m2": fmt(row["als_density_pts_m2"], 3),
        "als_hole_ratio": fmt(row["als_hole_ratio"], 3),
        "als_plane_rmse_m": fmt(row["als_plane_rmse_m"], 3),
        "view_count": str(int(row["view_count"])),
        "median_incidence_deg": fmt(row["median_incidence_deg"], 2),
        "median_in_frame_sample_fraction": fmt(row["median_in_frame_sample_fraction"], 3),
        "occlusion_risk_view_fraction": fmt(row["occlusion_risk_view_fraction"], 3),
        "classification": row["classification"],
        "surface_forming_recoverable": row["surface_forming_recoverable"],
        "classification_note": row["classification_note"],
        "dim_reason": row["dim_reason"],
    }


def summarize_control(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    metrics = [
        ("dim_density_pts_m2", "DIM density pts/m2"),
        ("dim_hole_ratio", "DIM hole ratio"),
        ("dim_plane_rmse_m", "DIM plane RMSE m"),
        ("als_density_pts_m2", "ALS density pts/m2"),
        ("als_hole_ratio", "ALS hole ratio"),
        ("als_plane_rmse_m", "ALS plane RMSE m"),
        ("view_count", "View count"),
        ("median_incidence_deg", "Median incidence deg"),
        ("occlusion_risk_view_fraction", "Occlusion-risk view fraction"),
    ]
    output = []
    for key, label in metrics:
        values = np.array([row[key] for row in rows if np.isfinite(row[key])], dtype=np.float64)
        if values.size:
            output.append(
                {
                    "metric": label,
                    "n": str(values.size),
                    "median": fmt(float(np.median(values)), 3),
                    "p10": fmt(float(np.percentile(values, 10.0)), 3),
                    "p25": fmt(float(np.percentile(values, 25.0)), 3),
                    "p75": fmt(float(np.percentile(values, 75.0)), 3),
                    "p90": fmt(float(np.percentile(values, 90.0)), 3),
                }
            )
        else:
            output.append({"metric": label, "n": "0", "median": "n/a", "p10": "n/a", "p25": "n/a", "p75": "n/a", "p90": "n/a"})
    return output


def format_threshold_rows(thresholds: dict[str, float]) -> list[dict[str, str]]:
    return [
        {
            "threshold": "density_min_pts_m2",
            "value": fmt(thresholds["density_min_pts_m2"], 3),
            "source": f"control_success_71 DIM density p{int(SURFACE_POINT_QUANTILE * 100)}",
            "interpretation": "DIM building points are sufficient when value is >= threshold",
        },
        {
            "threshold": "hole_ratio_max",
            "value": fmt(thresholds["hole_ratio_max"], 3),
            "source": f"control_success_71 DIM hole ratio p{int(HOLE_QUANTILE * 100)}",
            "interpretation": "DIM footprint holes are small when value is <= threshold",
        },
        {
            "threshold": "plane_rmse_max_m",
            "value": fmt(thresholds["plane_rmse_max_m"], 3),
            "source": f"control_success_71 DIM plane RMSE p{int(PLANE_RMSE_QUANTILE * 100)}",
            "interpretation": "DIM roof plane residual is control-like when value is <= threshold",
        },
        {
            "threshold": "view_count_min",
            "value": fmt(thresholds["view_count_min"], 3),
            "source": f"control_success_71 view count p{int(VIEW_COUNT_QUANTILE * 100)}",
            "interpretation": "T2 pose visibility is sufficient when value is >= threshold",
        },
        {
            "threshold": "incidence_max_deg",
            "value": fmt(thresholds["incidence_max_deg"], 3),
            "source": f"min(control_success_71 incidence p{int(INCIDENCE_QUANTILE * 100)}, {GRAZING_INCIDENT_ANGLE_DEG:.0f} deg grazing cap)",
            "interpretation": "View angle is not grazing when value is <= threshold",
        },
        {
            "threshold": "occlusion_risk_max_fraction",
            "value": fmt(thresholds["occlusion_risk_max_fraction"], 3),
            "source": "fixed approximate occlusion-risk cap",
            "interpretation": "Approximate occlusion risk is acceptable when value is <= threshold",
        },
    ]


def write_metrics_json(
    path: Path,
    run_id: str,
    failure_ids: list[str],
    control_ids: list[str],
    thresholds: dict[str, float],
    rows: list[dict[str, Any]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_id": run_id,
        "task_id": TASK_ID,
        "canonical_run": CANONICAL_RUN,
        "crs": "EPSG:25832 numeric UTM32; OPF source WKT says EPSG:32632 but T2 range/LoD2 overlay is EPSG:25832 numeric alignment",
        "failure_ids": failure_ids,
        "control_success_ids": control_ids,
        "thresholds": thresholds,
        "rows": sanitize_json(rows),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sanitize_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: sanitize_json(val) for key, val in value.items()}
    if isinstance(value, list):
        return [sanitize_json(item) for item in value]
    if isinstance(value, float) and not np.isfinite(value):
        return None
    if isinstance(value, np.generic):
        return value.item()
    return value


def render_point_clip_figure(
    out_path: Path,
    failure_ids: list[str],
    footprints: dict[str, Footprint],
    surface_by_id: dict[str, dict[str, SurfaceMetric]],
    dim_cloud: Cloud,
    als_cloud: Cloud,
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(len(failure_ids), 2, figsize=(8.4, max(12.0, len(failure_ids) * 2.1)), constrained_layout=True)
    if len(failure_ids) == 1:
        axes = axes.reshape((1, 2))
    for row_idx, bid in enumerate(failure_ids):
        footprint = footprints[bid]
        for col_idx, (label, cloud, color) in enumerate((("DIM", dim_cloud, "#d62728"), ("ALS", als_cloud, "#1f77b4"))):
            ax = axes[row_idx, col_idx]
            x, y, _ = clip_building_points(cloud, footprint)
            if x.size > 2500:
                idx = np.linspace(0, x.size - 1, 2500, dtype=np.int64)
                x = x[idx]
                y = y[idx]
            ring = footprint.ring
            ax.plot(ring[:, 0], ring[:, 1], color="#111111", linewidth=0.8)
            ax.scatter(x, y, s=1.0, color=color, alpha=0.55, linewidths=0)
            metrics = surface_by_id[bid][label]
            ax.set_title(
                f"{bid.replace('DEBY_LOD2_', '')} {label}: {metrics.density_pts_m2:.1f} pts/m2, holes {metrics.hole_ratio:.2f}",
                fontsize=8,
            )
            min_x, min_y, max_x, max_y = footprint.bbox
            pad = max(max_x - min_x, max_y - min_y) * 0.25 + 1.0
            ax.set_xlim(min_x - pad, max_x + pad)
            ax.set_ylim(min_y - pad, max_y + pad)
            ax.set_aspect("equal", adjustable="box")
            ax.tick_params(labelsize=6)
    fig.suptitle("T7 DIM failure point clips against ALS class-6 reference", fontsize=11)
    fig.savefig(out_path, dpi=220)
    plt.close(fig)


def render_classification_counts(out_path: Path, class_counts: Counter[str]) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    labels = ["evidence", "structuring", "observation"]
    source_labels = ["증거부족", "구조화부족", "관측부족"]
    values = [class_counts.get(label, 0) for label in source_labels]
    colors = ["#4c78a8", "#f58518", "#54a24b"]
    fig, ax = plt.subplots(figsize=(6.8, 4.2), constrained_layout=True)
    bars = ax.bar(labels, values, color=colors)
    for bar, value in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2.0, value + 0.05, str(value), ha="center", va="bottom")
    ax.set_ylim(0, max(values + [1]) + 1)
    ax.set_ylabel("building count")
    ax.set_title("T7 DIM-only failure diagnosis counts (n=8)")
    ax.grid(True, axis="y", linewidth=0.3, alpha=0.35)
    fig.savefig(out_path, dpi=220)
    plt.close(fig)


def write_report(
    out_path: Path,
    run_id: str,
    run_dir: Path,
    failure_rows: list[dict[str, str]],
    control_summary: list[dict[str, str]],
    threshold_rows: list[dict[str, str]],
    point_fig: Path,
    count_fig: Path,
    metrics_csv: Path,
    control_csv: Path,
    thresholds_csv: Path,
    metrics_json: Path,
    recoverable_count: int,
    observation_limited_count: int,
    class_counts: Counter[str],
) -> None:
    out_path.write_text(
        "\n".join(
            [
                "# W3 Failure Diagnosis (T7)",
                "",
                f"- Run ID: {run_id}",
                f"- Run directory: {rel(run_dir)}",
                f"- Canonical input: `{CANONICAL_RUN}`",
                f"- Building metrics CSV: `{rel(metrics_csv)}`",
                f"- Control summary CSV: `{rel(control_csv)}`",
                f"- Threshold CSV: `{rel(thresholds_csv)}`",
                f"- Metrics JSON: `{rel(metrics_json)}`",
                "- CRS: EPSG:25832 numeric UTM32 for footprints, ALS/DIM LAZ, and camera centers after T2 OPF scene-reference transform.",
                "- Scope: automatic classification/observation only. P0 acceptance/rejection remains a human G1/E5 decision.",
                "",
                "## Failure Building Classification",
                "",
                markdown_table(
                    failure_rows,
                    [
                        "building_id",
                        "dim_density_pts_m2",
                        "dim_hole_ratio",
                        "dim_plane_rmse_m",
                        "view_count",
                        "median_incidence_deg",
                        "classification",
                        "surface_forming_recoverable",
                    ],
                ),
                "",
                "## Control Summary",
                "",
                markdown_table(control_summary, ["metric", "n", "median", "p10", "p25", "p75", "p90"]),
                "",
                "## Adopted Thresholds",
                "",
                markdown_table(threshold_rows, ["threshold", "value", "source", "interpretation"]),
                "",
                "## Figures",
                "",
                f"![8 failure point clips against ALS]({rel(point_fig).replace('docs/', '')})",
                "",
                f"![classification counts]({rel(count_fig).replace('docs/', '')})",
                "",
                "## Observations",
                "",
                f"- Surface-formation recovery candidates: {recoverable_count} / 8. Observation-limited cases: {observation_limited_count} / 8.",
                (
                    "- Classification counts: "
                    + ", ".join(f"{label} {class_counts.get(label, 0)}" for label in ["증거부족", "구조화부족", "관측부족"])
                    + "."
                ),
                "- `surface_forming_recoverable=yes` means the case has sufficient projected views but DIM class-6 density/hole/residual evidence falls below the control-success threshold.",
                "- `구조화부족` means DIM class-6 surface indicators are already control-like, so the observed failure is not attributed to image-based surface formation in this T7 table.",
                "- `관측부족` means T2 pose visibility, grazing angle, or approximate footprint occlusion is below the adopted control-success threshold.",
                "- Occlusion is a footprint/ALS-height line-of-sight approximation, not an image-depth proof.",
                "- E5 confirmation is still required before using these T7 categories as a method-level conclusion.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def markdown_table(rows: list[dict[str, str]], columns: list[str]) -> str:
    if not rows:
        return "_No rows._"
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(col, "")) for col in columns) + " |")
    return "\n".join(lines)


def add_to_g1_package(
    package: Path,
    package_figs: Path,
    report_md: Path,
    metrics_csv: Path,
    control_csv: Path,
    thresholds_csv: Path,
    point_fig: Path,
    count_fig: Path,
) -> None:
    package.mkdir(parents=True, exist_ok=True)
    package_figs.mkdir(parents=True, exist_ok=True)
    targets = [
        (report_md, package / "W3_failure_diagnosis.md"),
        (metrics_csv, package / "t7_failure_diagnosis_building_metrics.csv"),
        (control_csv, package / "t7_failure_diagnosis_control_summary.csv"),
        (thresholds_csv, package / "t7_failure_diagnosis_thresholds.csv"),
        (point_fig, package_figs / "fig_10_t7_failure_point_clips.png"),
        (count_fig, package_figs / "fig_11_t7_failure_classification_counts.png"),
    ]
    for src, dst in targets:
        shutil.copy2(src, dst)
    manifest_path = package / "manifest.json"
    if manifest_path.exists():
        manifest = read_json(manifest_path)
    else:
        manifest = {"package": "G1_package", "canonical_run": CANONICAL_RUN, "files": [], "figure_count": 0}
    files = set(manifest.get("files", []))
    for _, dst in targets:
        files.add(dst.relative_to(package).as_posix())
    manifest["files"] = sorted(files)
    manifest["figure_count"] = sum(1 for item in manifest["files"] if item.startswith("figs/") and item.endswith(".png"))
    manifest["t7_failure_diagnosis"] = {
        "report": "W3_failure_diagnosis.md",
        "figures": ["figs/fig_10_t7_failure_point_clips.png", "figs/fig_11_t7_failure_classification_counts.png"],
        "tables": [
            "t7_failure_diagnosis_building_metrics.csv",
            "t7_failure_diagnosis_control_summary.csv",
            "t7_failure_diagnosis_thresholds.csv",
        ],
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def copy_outputs(run_dir: Path, paths: list[Path]) -> None:
    snapshot = run_dir / "outputs"
    snapshot.mkdir(parents=True, exist_ok=True)
    for path in paths:
        if not path.exists():
            continue
        if path.is_relative_to(Path("/workspace/docs")):
            dst = snapshot / "docs" / path.relative_to(Path("/workspace/docs"))
        elif path.is_relative_to(Path("/workspace/data")):
            dst = snapshot / "data" / path.relative_to(Path("/workspace/data"))
        else:
            dst = snapshot / path.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dst)


def fmt(value: float, decimals: int) -> str:
    if value is None or not np.isfinite(float(value)):
        return "n/a"
    return f"{float(value):.{decimals}f}"


def rel(path: Path) -> str:
    text = path.as_posix()
    return text.replace("/workspace/", "")


def main() -> None:
    if os.environ.get("P0_INSIDE_CONTAINER") == "1":
        if "--mode" in sys.argv and "compute" in sys.argv:
            compute_entrypoint()
        else:
            compute_entrypoint()
    else:
        host_entrypoint()


if __name__ == "__main__":
    main()
