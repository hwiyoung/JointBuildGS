#!/usr/bin/env python3
"""Compare ALS and DIM input point clouds for W1 diagnosis.

Run from phases/p0-audit/. The host entrypoint re-runs this script inside the P0 tools
container so laspy/matplotlib execution stays in the audit toolchain.
"""

from __future__ import annotations

import csv
import json
import math
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


TASK_ID = "T6"
BUILDING_CLASS = 6
GROUND_CLASS = 2
BOUNDARY_BAND_M = 8.0
WALL_EDGE_BAND_M = 2.0
MIN_ROOF_POINTS = 40


@dataclass
class Footprint:
    building_id: str
    area_m2: float
    bbox: tuple[float, float, float, float]
    ring: np.ndarray


@dataclass
class PointCloud:
    label: str
    x: np.ndarray
    y: np.ndarray
    z: np.ndarray
    classification: np.ndarray
    source_files: list[str]

    @property
    def point_count(self) -> int:
        return int(self.x.size)


@dataclass
class Diagnosis:
    label: str
    source_files: list[str]
    point_count: int
    building_point_count: int
    density_pts_m2: float
    building_density_pts_m2: float
    roof_sample_buildings: int
    roof_plane_rmse_median: float
    roof_plane_rmse_iqr: tuple[float, float]
    boundary_sample_count: int
    boundary_noise_width_m: float
    wall_like_ratio: float
    wall_like_count: int
    footprint_building_point_count: int
    roof_residuals: np.ndarray
    boundary_signed_distances: np.ndarray


def host_entrypoint() -> None:
    repo = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.setdefault("P0_UID", str(os.getuid()))
    env.setdefault("P0_GID", str(os.getgid()))

    compose = ["docker", "compose", "-f", str(repo / "env/docker-compose.p0.yml")]
    if env.get("SKIP_BUILD") != "1":
        run(compose + ["build", "tools"], cwd=repo, env=env)

    git_commit = subprocess.check_output(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=repo.parent,
        text=True,
    ).strip()
    run_id = env.get("RUN_ID") or datetime.now().strftime("t6_diagnose_%Y%m%d_%H%M%S")

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
                f"P0_GIT_COMMIT={git_commit}",
                "-e",
                f"RUN_ID={run_id}",
                "tools",
                "python",
                "/workspace/scripts/06_diagnose.py",
                *sys.argv[1:],
            ],
            cwd=repo,
            env=env,
        )
    except subprocess.CalledProcessError as exc:
        record_issue(repo, run_id, f"failed with exit code {exc.returncode}")
        raise


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


def capture(cmd: list[str]) -> str:
    proc = subprocess.run(cmd, text=True, capture_output=True, check=False)
    return (proc.stdout or proc.stderr).strip()


def record_issue(repo: Path, run_id: str, message: str) -> None:
    issues = repo / "docs/issues.md"
    with issues.open("a", encoding="utf-8") as fh:
        fh.write(f"\n## {TASK_ID} W1 Input Diagnosis\n\n")
        fh.write(f"- {run_id}: {message}. See runs/{run_id}/logs/.\n")


def load_scene_aoi(path: Path) -> tuple[tuple[float, float, float, float], float]:
    data = json.loads(path.read_text(encoding="utf-8"))
    feature = data["features"][0]
    props = feature["properties"]
    bbox = (
        float(props["min_x"]),
        float(props["min_y"]),
        float(props["max_x"]),
        float(props["max_y"]),
    )
    area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
    return bbox, area


def load_intersecting_ids(csv_path: Path) -> set[str]:
    with csv_path.open("r", encoding="utf-8", newline="") as fh:
        return {row["building_id"] for row in csv.DictReader(fh)}


def load_footprints(geojson_path: Path, building_ids: set[str]) -> list[Footprint]:
    data = json.loads(geojson_path.read_text(encoding="utf-8"))
    footprints: list[Footprint] = []
    for feature in data["features"]:
        props = feature["properties"]
        building_id = props["building_id"]
        if building_id not in building_ids:
            continue
        ring = np.array(feature["geometry"]["coordinates"][0], dtype=float)
        if ring.shape[0] < 4:
            continue
        if not np.allclose(ring[0], ring[-1]):
            ring = np.vstack([ring, ring[0]])
        footprints.append(
            Footprint(
                building_id=building_id,
                area_m2=float(props["area_m2"]),
                bbox=(
                    float(props["min_x"]),
                    float(props["min_y"]),
                    float(props["max_x"]),
                    float(props["max_y"]),
                ),
                ring=ring,
            )
        )
    if not footprints:
        raise RuntimeError("No scene AOI footprints found for W1 diagnosis")
    return footprints


def read_laz_points(label: str, paths: list[Path], bbox: tuple[float, float, float, float]) -> PointCloud:
    import laspy

    xs: list[np.ndarray] = []
    ys: list[np.ndarray] = []
    zs: list[np.ndarray] = []
    classes: list[np.ndarray] = []
    min_x, min_y, max_x, max_y = bbox

    for path in paths:
        with laspy.open(path) as fh:
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
        raise RuntimeError(f"No {label} points overlap the scene AOI")

    return PointCloud(
        label=label,
        x=np.concatenate(xs),
        y=np.concatenate(ys),
        z=np.concatenate(zs),
        classification=np.concatenate(classes),
        source_files=[path.name for path in paths],
    )


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


def distance_to_ring(xs: np.ndarray, ys: np.ndarray, ring: np.ndarray) -> np.ndarray:
    d2_min = np.full(xs.shape, np.inf, dtype=np.float64)
    for idx in range(ring.shape[0] - 1):
        x1, y1 = ring[idx]
        x2, y2 = ring[idx + 1]
        vx = x2 - x1
        vy = y2 - y1
        seg_len2 = vx * vx + vy * vy
        if seg_len2 == 0.0:
            continue
        t = ((xs - x1) * vx + (ys - y1) * vy) / seg_len2
        t = np.clip(t, 0.0, 1.0)
        proj_x = x1 + t * vx
        proj_y = y1 + t * vy
        d2 = (xs - proj_x) ** 2 + (ys - proj_y) ** 2
        d2_min = np.minimum(d2_min, d2)
    return np.sqrt(d2_min)


def fit_plane_rmse(xs: np.ndarray, ys: np.ndarray, zs: np.ndarray) -> float | None:
    if zs.size < MIN_ROOF_POINTS:
        return None
    cx = float(np.mean(xs))
    cy = float(np.mean(ys))
    design = np.column_stack([xs - cx, ys - cy, np.ones_like(xs)])
    coef, *_ = np.linalg.lstsq(design, zs, rcond=None)
    residuals = zs - design @ coef
    abs_residuals = np.abs(residuals)
    keep_cutoff = float(np.percentile(abs_residuals, 95.0))
    keep = abs_residuals <= keep_cutoff
    if np.count_nonzero(keep) >= MIN_ROOF_POINTS:
        design = design[keep]
        zs = zs[keep]
        coef, *_ = np.linalg.lstsq(design, zs, rcond=None)
        residuals = zs - design @ coef
    return float(np.sqrt(np.mean(residuals**2)))


def sample_array(values: np.ndarray, max_count: int = 300_000) -> np.ndarray:
    if values.size <= max_count:
        return values
    idx = np.linspace(0, values.size - 1, max_count, dtype=np.int64)
    return values[idx]


def analyze_point_cloud(
    cloud: PointCloud,
    footprints: list[Footprint],
    aoi_area_m2: float,
) -> Diagnosis:
    building_mask = cloud.classification == BUILDING_CLASS
    bx = cloud.x[building_mask]
    by = cloud.y[building_mask]
    bz = cloud.z[building_mask]

    roof_residuals: list[float] = []
    boundary_distances: list[np.ndarray] = []
    wall_like_count = 0
    footprint_building_point_count = 0
    footprint_area = sum(item.area_m2 for item in footprints)

    for footprint in footprints:
        min_x, min_y, max_x, max_y = footprint.bbox
        bbox_mask = (bx >= min_x) & (bx <= max_x) & (by >= min_y) & (by <= max_y)
        if np.any(bbox_mask):
            local_x = bx[bbox_mask]
            local_y = by[bbox_mask]
            local_z = bz[bbox_mask]
            inside = points_in_polygon(local_x, local_y, footprint.ring)
            if np.any(inside):
                in_x = local_x[inside]
                in_y = local_y[inside]
                in_z = local_z[inside]
                footprint_building_point_count += int(in_z.size)

                roof_min = float(np.percentile(in_z, 65.0))
                roof_max = float(np.percentile(in_z, 99.5))
                roof = (in_z >= roof_min) & (in_z <= roof_max)
                rmse = fit_plane_rmse(in_x[roof], in_y[roof], in_z[roof])
                if rmse is not None and np.isfinite(rmse):
                    roof_residuals.append(rmse)

                edge_distance = distance_to_ring(in_x, in_y, footprint.ring)
                wall_height_cut = float(np.percentile(in_z, 70.0))
                wall_like = (edge_distance <= WALL_EDGE_BAND_M) & (in_z < wall_height_cut - 0.5)
                wall_like_count += int(np.count_nonzero(wall_like))

        exp_min_x = min_x - BOUNDARY_BAND_M
        exp_min_y = min_y - BOUNDARY_BAND_M
        exp_max_x = max_x + BOUNDARY_BAND_M
        exp_max_y = max_y + BOUNDARY_BAND_M
        near_bbox = (
            (bx >= exp_min_x)
            & (bx <= exp_max_x)
            & (by >= exp_min_y)
            & (by <= exp_max_y)
        )
        if np.any(near_bbox):
            near_x = bx[near_bbox]
            near_y = by[near_bbox]
            dist = distance_to_ring(near_x, near_y, footprint.ring)
            near = dist <= BOUNDARY_BAND_M
            if np.any(near):
                inside_near = points_in_polygon(near_x[near], near_y[near], footprint.ring)
                signed = np.where(inside_near, dist[near], -dist[near])
                boundary_distances.append(sample_array(signed, 2_000))

    roof_arr = np.array(roof_residuals, dtype=np.float64)
    boundary_arr = (
        sample_array(np.concatenate(boundary_distances), 400_000)
        if boundary_distances
        else np.array([], dtype=np.float64)
    )
    if roof_arr.size:
        roof_median = float(np.median(roof_arr))
        roof_iqr = (float(np.percentile(roof_arr, 25.0)), float(np.percentile(roof_arr, 75.0)))
    else:
        roof_median = math.nan
        roof_iqr = (math.nan, math.nan)
    boundary_width = (
        float(np.percentile(boundary_arr, 95.0) - np.percentile(boundary_arr, 5.0))
        if boundary_arr.size
        else math.nan
    )

    return Diagnosis(
        label=cloud.label,
        source_files=cloud.source_files,
        point_count=cloud.point_count,
        building_point_count=int(np.count_nonzero(building_mask)),
        density_pts_m2=cloud.point_count / aoi_area_m2,
        building_density_pts_m2=footprint_building_point_count / footprint_area,
        roof_sample_buildings=int(roof_arr.size),
        roof_plane_rmse_median=roof_median,
        roof_plane_rmse_iqr=roof_iqr,
        boundary_sample_count=int(boundary_arr.size),
        boundary_noise_width_m=boundary_width,
        wall_like_ratio=(wall_like_count / footprint_building_point_count if footprint_building_point_count else math.nan),
        wall_like_count=wall_like_count,
        footprint_building_point_count=footprint_building_point_count,
        roof_residuals=roof_arr,
        boundary_signed_distances=boundary_arr,
    )


def write_density_figure(
    als: PointCloud,
    dim: PointCloud,
    aoi_bbox: tuple[float, float, float, float],
    out_path: Path,
    cell_size: float = 5.0,
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LogNorm

    out_path.parent.mkdir(parents=True, exist_ok=True)
    min_x, min_y, max_x, max_y = aoi_bbox
    x_edges = np.arange(min_x, max_x + cell_size, cell_size)
    y_edges = np.arange(min_y, max_y + cell_size, cell_size)

    grids = []
    vmax_candidates = []
    for cloud in (als, dim):
        hist, _, _ = np.histogram2d(cloud.x, cloud.y, bins=[x_edges, y_edges])
        density = hist.T / (cell_size * cell_size)
        grids.append(density)
        positive = density[density > 0.0]
        if positive.size:
            vmax_candidates.append(float(np.percentile(positive, 98.0)))
    vmax = max(vmax_candidates) if vmax_candidates else 1.0
    vmin = 0.1
    cmap = plt.get_cmap("magma").copy()
    cmap.set_bad("#000000")

    fig, axes = plt.subplots(1, 2, figsize=(13, 6), constrained_layout=True)
    for ax, title, density in zip(axes, ["ALS point density", "DIM point density"], grids):
        masked_density = np.ma.masked_less_equal(density, 0.0)
        im = ax.imshow(
            masked_density,
            extent=[min_x, max_x, min_y, max_y],
            origin="lower",
            cmap=cmap,
            norm=LogNorm(vmin=vmin, vmax=max(vmax, vmin * 10.0)),
        )
        ax.set_title(title)
        ax.set_xlabel("Easting (EPSG:25832 m)")
        ax.set_ylabel("Northing (EPSG:25832 m)")
        ax.set_aspect("equal", adjustable="box")
    fig.colorbar(im, ax=axes, shrink=0.82, label="points / m2 (log scale)")
    fig.savefig(out_path, dpi=220)
    plt.close(fig)


def write_quality_figure(als: Diagnosis, dim: Diagnosis, out_path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 3, figsize=(15, 5), constrained_layout=True)

    roof_data = [als.roof_residuals, dim.roof_residuals]
    axes[0].boxplot(roof_data, tick_labels=["ALS", "DIM"], showfliers=False)
    axes[0].set_title("Roof plane fit residuals")
    axes[0].set_ylabel("RMSE (m)")
    axes[0].grid(True, linewidth=0.3, alpha=0.35)

    bins = np.linspace(-BOUNDARY_BAND_M, BOUNDARY_BAND_M, 60)
    if als.boundary_signed_distances.size:
        axes[1].hist(
            als.boundary_signed_distances,
            bins=bins,
            density=True,
            alpha=0.55,
            label="ALS",
            color="#1f77b4",
        )
    if dim.boundary_signed_distances.size:
        axes[1].hist(
            dim.boundary_signed_distances,
            bins=bins,
            density=True,
            alpha=0.55,
            label="DIM",
            color="#d62728",
        )
    axes[1].axvline(0.0, color="#111111", linewidth=0.8)
    axes[1].set_title("Signed boundary distances")
    axes[1].set_xlabel("distance to footprint edge (m)")
    axes[1].set_ylabel("density")
    axes[1].legend()
    axes[1].grid(True, linewidth=0.3, alpha=0.35)

    axes[2].bar(["ALS", "DIM"], [als.wall_like_ratio * 100.0, dim.wall_like_ratio * 100.0], color=["#1f77b4", "#d62728"])
    axes[2].set_title("Wall-like point ratio")
    axes[2].set_ylabel("% of footprint building points")
    axes[2].grid(True, axis="y", linewidth=0.3, alpha=0.35)

    fig.savefig(out_path, dpi=220)
    plt.close(fig)


def fmt_float(value: float, decimals: int = 3) -> str:
    if not np.isfinite(value):
        return "n/a"
    return f"{value:.{decimals}f}"


def write_metrics_json(
    out_path: Path,
    run_id: str,
    aoi_bbox: tuple[float, float, float, float],
    aoi_area_m2: float,
    footprint_count: int,
    als: Diagnosis,
    dim: Diagnosis,
) -> None:
    def pack(item: Diagnosis) -> dict[str, object]:
        return {
            "source_files": item.source_files,
            "point_count": item.point_count,
            "building_point_count": item.building_point_count,
            "density_pts_m2": item.density_pts_m2,
            "building_density_pts_m2": item.building_density_pts_m2,
            "roof_sample_buildings": item.roof_sample_buildings,
            "roof_plane_rmse_median": item.roof_plane_rmse_median,
            "roof_plane_rmse_iqr": item.roof_plane_rmse_iqr,
            "boundary_sample_count": item.boundary_sample_count,
            "boundary_noise_width_m": item.boundary_noise_width_m,
            "wall_like_ratio": item.wall_like_ratio,
            "wall_like_count": item.wall_like_count,
            "footprint_building_point_count": item.footprint_building_point_count,
        }

    out_path.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "aoi_bbox": aoi_bbox,
                "aoi_area_m2": aoi_area_m2,
                "footprint_count": footprint_count,
                "metrics": {"ALS": pack(als), "DIM": pack(dim)},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def observation_lines(als: Diagnosis, dim: Diagnosis) -> list[str]:
    density_ratio = dim.density_pts_m2 / als.density_pts_m2 if als.density_pts_m2 else math.nan
    residual_ratio = (
        dim.roof_plane_rmse_median / als.roof_plane_rmse_median
        if als.roof_plane_rmse_median and np.isfinite(als.roof_plane_rmse_median)
        else math.nan
    )
    boundary_delta = dim.boundary_noise_width_m - als.boundary_noise_width_m
    wall_delta_pp = (dim.wall_like_ratio - als.wall_like_ratio) * 100.0

    return [
        (
            f"- 이 장면에서 DIM AOI 밀도는 ALS의 {fmt_float(density_ratio, 2)}배입니다 "
            f"({fmt_float(dim.density_pts_m2, 2)} vs {fmt_float(als.density_pts_m2, 2)} pts/m2)."
        ),
        (
            f"- 매칭된 LoD2 footprint 지붕 샘플의 plane RMSE 중앙값은 DIM이 ALS의 "
            f"{fmt_float(residual_ratio, 2)}배입니다. 표본 건물 수는 ALS {als.roof_sample_buildings}개, "
            f"DIM {dim.roof_sample_buildings}개입니다."
        ),
        (
            f"- footprint 경계 +/-{BOUNDARY_BAND_M:.0f} m 밴드에서 DIM signed-distance 폭은 "
            f"ALS와 {fmt_float(boundary_delta, 2)} m 차이가 납니다."
        ),
        (
            f"- edge-band 및 below-roof 휴리스틱 기준 wall-like 비율은 DIM이 ALS와 "
            f"{fmt_float(wall_delta_pp, 2)}%p 차이가 납니다."
        ),
        (
            "- W2 진입 가능 여부 논의를 위해 동일 AOI, footprint, class, CRS 위의 관찰값은 확보됐습니다. "
            "이 리포트는 관찰 요약만 기록하며 go/no-go 판정은 하지 않습니다."
        ),
    ]


def write_report(
    out_path: Path,
    run_id: str,
    run_dir: Path,
    aoi_bbox: tuple[float, float, float, float],
    aoi_area_m2: float,
    footprint_count: int,
    density_fig: Path,
    quality_fig: Path,
    metrics_json: Path,
    als: Diagnosis,
    dim: Diagnosis,
) -> None:
    rel = lambda path: path.as_posix().replace("/workspace/", "")
    table = [
        "| Metric | ALS | DIM | Notes |",
        "|---|---:|---:|---|",
        (
            f"| AOI point density | {fmt_float(als.density_pts_m2, 2)} pts/m2 | "
            f"{fmt_float(dim.density_pts_m2, 2)} pts/m2 | all classes inside scene_aoi |"
        ),
        (
            f"| Building density in LoD2 footprints | {fmt_float(als.building_density_pts_m2, 2)} pts/m2 | "
            f"{fmt_float(dim.building_density_pts_m2, 2)} pts/m2 | class 6 points inside intersecting ground plans |"
        ),
        (
            f"| Roof plane fit residual | {fmt_float(als.roof_plane_rmse_median, 3)} m "
            f"(IQR {fmt_float(als.roof_plane_rmse_iqr[0], 3)}-{fmt_float(als.roof_plane_rmse_iqr[1], 3)}) | "
            f"{fmt_float(dim.roof_plane_rmse_median, 3)} m "
            f"(IQR {fmt_float(dim.roof_plane_rmse_iqr[0], 3)}-{fmt_float(dim.roof_plane_rmse_iqr[1], 3)}) | "
            "median per-building RMSE after top-35% roof sample plane fit |"
        ),
        (
            f"| Boundary noise width | {fmt_float(als.boundary_noise_width_m, 3)} m | "
            f"{fmt_float(dim.boundary_noise_width_m, 3)} m | p95-p05 signed distance for class 6 points within footprint-edge band |"
        ),
        (
            f"| Wall-like point ratio | {fmt_float(als.wall_like_ratio * 100.0, 2)}% | "
            f"{fmt_float(dim.wall_like_ratio * 100.0, 2)}% | edge-band class 6 points below each building's roof-height cutoff |"
        ),
    ]

    out_path.write_text(
        "\n".join(
            [
                "# W1 입력 점군 진단",
                "",
                f"- Run ID: {run_id}",
                f"- Run directory: {rel(run_dir)}",
                f"- Metrics JSON: {rel(metrics_json)}",
                f"- AOI: x=[{aoi_bbox[0]:.3f}, {aoi_bbox[2]:.3f}], y=[{aoi_bbox[1]:.3f}, {aoi_bbox[3]:.3f}], area={aoi_area_m2:,.1f} m2",
                f"- Intersecting LoD2 footprint buildings used: {footprint_count}",
                f"- ALS files: {', '.join(als.source_files)}",
                f"- DIM file: {', '.join(dim.source_files)}",
                "- CRS assertion: EPSG:25832 inputs from prior T4/T5 outputs.",
                "",
                "## 진단 표",
                "",
                "\n".join(table),
                "",
                "## 그림",
                "",
                f"![ALS and DIM point-density grids](figs/{density_fig.name})",
                "",
                f"![Roof, boundary, and wall diagnostics](figs/{quality_fig.name})",
                "",
                "## 방법 메모",
                "",
                "- 밀도는 `scene_aoi.gpkg` 내부 점을 기준으로 계산했고, building density는 AOI와 교차하는 LoD2 ground plan 내부의 class 6 점만 사용했습니다.",
                "- 지붕 잔차는 기준면 정확도 점수가 아니라 진단용 plane-fit RMSE입니다. 각 footprint 내부 class 6 점 중 상위 35% 높이 밴드만 골라 최소제곱 평면을 맞췄습니다.",
                f"- 경계부 노이즈 폭은 각 footprint 경계 +/-{BOUNDARY_BAND_M:.0f} m 밴드의 class 6 점 signed distance로 계산했습니다. 양수는 footprint 내부, 음수는 외부입니다.",
                f"- wall-like 비율은 휴리스틱입니다. footprint 경계 {WALL_EDGE_BAND_M:.0f} m 이내이고 건물별 70 percentile 높이보다 0.5 m 이상 낮은 class 6 점을 wall-like로 셌습니다.",
                "",
                "## W2 진입 가능 여부 관찰 요약",
                "",
                "\n".join(observation_lines(als, dim)),
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_versions(run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        "# T6 Tool Versions",
        "",
        f"- Generated: {datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')}",
        f"- Run ID: {os.environ['RUN_ID']}",
        f"- Repository commit: {os.environ.get('P0_GIT_COMMIT', 'unknown')}",
        "",
        "```console",
    ]
    for cmd in (
        ["python", "--version"],
        ["lasinfo", "--version"],
        [
            "python",
            "-c",
            "import laspy, matplotlib, numpy; print('laspy ' + laspy.__version__); print('matplotlib ' + matplotlib.__version__); print('numpy ' + numpy.__version__)",
        ],
    ):
        lines.append("$ " + " ".join(cmd))
        lines.append(capture(cmd))
    lines.append("```")
    (run_dir / "versions.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_config(run_dir: Path, values: dict[str, str | int | float]) -> None:
    lines = ["task: T6_w1_input_diagnosis"]
    for key, value in values.items():
        lines.append(f"{key}: {value}")
    (run_dir / "config.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    root = Path("/workspace")
    data = root / "data"
    docs = root / "docs"
    run_id = os.environ["RUN_ID"]
    run_dir = root / "runs" / run_id
    work_dir = data / "work/diagnose"
    figs_dir = docs / "figs"

    scene_aoi_geojson = data / "work/footprints/scene_aoi.geojson"
    footprints_geojson = data / "work/footprints/lod2_ground_plan.geojson"
    intersecting_csv = docs / "scene_aoi_buildings.csv"
    als_paths = sorted((data / "raw/als").glob("*.laz"))
    dim_path = data / "work/classify/dim_v1_classified.laz"
    report_path = docs / "W1_diagnosis.md"
    density_fig = figs_dir / "w1_density_grid.png"
    quality_fig = figs_dir / "w1_quality_diagnostics.png"
    metrics_json = work_dir / "w1_metrics.json"

    for path in (scene_aoi_geojson, footprints_geojson, intersecting_csv, dim_path):
        if not path.exists():
            raise FileNotFoundError(path)
    if not als_paths:
        raise FileNotFoundError(data / "raw/als")

    work_dir.mkdir(parents=True, exist_ok=True)
    figs_dir.mkdir(parents=True, exist_ok=True)
    write_versions(run_dir)

    aoi_bbox, aoi_area_m2 = load_scene_aoi(scene_aoi_geojson)
    building_ids = load_intersecting_ids(intersecting_csv)
    footprints = load_footprints(footprints_geojson, building_ids)

    als_cloud = read_laz_points("ALS", als_paths, aoi_bbox)
    dim_cloud = read_laz_points("DIM", [dim_path], aoi_bbox)
    als_diag = analyze_point_cloud(als_cloud, footprints, aoi_area_m2)
    dim_diag = analyze_point_cloud(dim_cloud, footprints, aoi_area_m2)

    write_density_figure(als_cloud, dim_cloud, aoi_bbox, density_fig)
    write_quality_figure(als_diag, dim_diag, quality_fig)
    write_metrics_json(metrics_json, run_id, aoi_bbox, aoi_area_m2, len(footprints), als_diag, dim_diag)
    write_config(
        run_dir,
        {
            "run_id": run_id,
            "scene_aoi": "data/work/footprints/scene_aoi.gpkg",
            "footprints": "data/work/footprints/lod2_ground_plan.gpkg",
            "intersecting_buildings": "docs/scene_aoi_buildings.csv",
            "als_file_count": len(als_paths),
            "dim_file": "data/work/classify/dim_v1_classified.laz",
            "aoi_area_m2": f"{aoi_area_m2:.3f}",
            "footprint_count": len(footprints),
            "boundary_band_m": BOUNDARY_BAND_M,
            "wall_edge_band_m": WALL_EDGE_BAND_M,
            "min_roof_points": MIN_ROOF_POINTS,
        },
    )
    write_report(
        report_path,
        run_id,
        run_dir,
        aoi_bbox,
        aoi_area_m2,
        len(footprints),
        density_fig,
        quality_fig,
        metrics_json,
        als_diag,
        dim_diag,
    )

    print(f"als_density_pts_m2={als_diag.density_pts_m2:.3f}")
    print(f"dim_density_pts_m2={dim_diag.density_pts_m2:.3f}")
    print(f"als_roof_rmse_median_m={als_diag.roof_plane_rmse_median:.3f}")
    print(f"dim_roof_rmse_median_m={dim_diag.roof_plane_rmse_median:.3f}")
    print(f"als_boundary_width_m={als_diag.boundary_noise_width_m:.3f}")
    print(f"dim_boundary_width_m={dim_diag.boundary_noise_width_m:.3f}")
    print(f"als_wall_like_ratio={als_diag.wall_like_ratio:.4f}")
    print(f"dim_wall_like_ratio={dim_diag.wall_like_ratio:.4f}")
    print(f"report={report_path}")
    print(f"density_figure={density_fig}")
    print(f"quality_figure={quality_fig}")


if __name__ == "__main__":
    if os.environ.get("P0_INSIDE_CONTAINER") != "1":
        host_entrypoint()
    else:
        main()
