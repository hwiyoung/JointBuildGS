#!/usr/bin/env python3
"""Measure MVS/ALS baselines and select deterministic positive-control candidates."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import platform
import subprocess
import time
from pathlib import Path

import laspy
import numpy as np
from PIL import Image, ImageDraw
from shapely.geometry import Point, shape
from shapely.ops import unary_union


ROOT = Path(__file__).resolve().parents[2]


def append_log(path: Path, message: str) -> None:
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(f"{stamp}\t{message}\n")
        f.flush()
        os.fsync(f.fileno())


def run(command: list[str], log: Path) -> subprocess.CompletedProcess:
    append_log(log, "command=" + " ".join(command))
    completed = subprocess.run(command, text=True, capture_output=True)
    with log.open("a", encoding="utf-8") as f:
        if completed.stdout:
            f.write(completed.stdout)
        if completed.stderr:
            f.write(completed.stderr)
        f.flush()
        os.fsync(f.fileno())
    if completed.returncode:
        raise RuntimeError(f"command failed ({completed.returncode}): {' '.join(command)}")
    return completed


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def write_csv(path: Path, rows: list[dict], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = fieldnames or (list(rows[0]) if rows else [])
    tmp = path.with_suffix(path.suffix + ".part")
    with tmp.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(16 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def walk_coordinates(value):
    if isinstance(value, list):
        if len(value) >= 2 and all(isinstance(v, (int, float)) for v in value[:2]):
            yield value
        else:
            for child in value:
                yield from walk_coordinates(child)


def parse_daporp(path: Path) -> dict[str, dict]:
    lines = [line.split() for line in path.read_text(encoding="latin1").splitlines() if line.strip()]
    result = {}
    for i in range(0, len(lines), 3):
        head, a, b = lines[i : i + 3]
        stem, _, x, y, z = head
        r11, r21, r31, r12, r22, r32, r13, r23, r33 = [float(v) for v in a + b]
        result[stem] = {
            "center": np.array([float(x), float(y), float(z)]),
            "r_cam_to_world": np.array([[r11, r12, r13], [r21, r22, r23], [r31, r32, r33]]),
        }
    return result


def raster_info(path: Path, log: Path) -> dict:
    completed = run(["gdalinfo", "-json", str(path)], log)
    return json.loads(completed.stdout)


def pixel_xy(x: float, y: float, gt: list[float]) -> tuple[float, float]:
    return ((x - gt[0]) / gt[1], (y - gt[3]) / gt[5])


def geometry_mask(geometry, size: tuple[int, int], gt: list[float]) -> np.ndarray:
    width, height = size
    image = Image.new("1", (width, height), 0)
    draw = ImageDraw.Draw(image)
    polygons = [geometry] if geometry.geom_type == "Polygon" else list(geometry.geoms)
    for polygon in polygons:
        exterior = [pixel_xy(x, y, gt) for x, y in polygon.exterior.coords]
        draw.polygon(exterior, fill=1)
        for interior in polygon.interiors:
            draw.polygon([pixel_xy(x, y, gt) for x, y in interior.coords], fill=0)
    return np.asarray(image, dtype=bool)


def grid_coverage(points_xy: np.ndarray, polygon, grid: float, radius: float) -> tuple[int, int, float]:
    minx, miny, maxx, maxy = polygon.bounds
    xs = np.arange(minx + grid / 2, maxx, grid)
    ys = np.arange(miny + grid / 2, maxy, grid)
    centers = np.array([(x, y) for y in ys for x in xs if polygon.covers(Point(x, y))], dtype=float)
    if centers.size == 0:
        return 0, 0, math.nan
    if points_xy.size == 0:
        return 0, len(centers), 1.0
    local = points_xy[
        (points_xy[:, 0] >= minx - radius) & (points_xy[:, 0] <= maxx + radius)
        & (points_xy[:, 1] >= miny - radius) & (points_xy[:, 1] <= maxy + radius)
    ]
    if local.size == 0:
        return 0, len(centers), 1.0
    cell = radius
    buckets: dict[tuple[int, int], list[np.ndarray]] = {}
    for point in local:
        key = (math.floor(point[0] / cell), math.floor(point[1] / cell))
        buckets.setdefault(key, []).append(point)
    covered = 0
    radius2 = radius * radius
    for center in centers:
        key = (math.floor(center[0] / cell), math.floor(center[1] / cell))
        hit = False
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                candidates = buckets.get((key[0] + dx, key[1] + dy), [])
                if any(float(np.sum((candidate - center) ** 2)) <= radius2 for candidate in candidates):
                    hit = True
                    break
            if hit:
                break
        covered += int(hit)
    return covered, len(centers), 1.0 - covered / len(centers)


def f(value, digits=6) -> str:
    if value is None or not math.isfinite(float(value)):
        return ""
    return f"{float(value):.{digits}f}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/fair_pilot/vaihingen_area3.json")
    args = parser.parse_args()
    cfg = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    run_dir = ROOT / "fair-pilot" / "runs" / cfg["run_id"]
    log = run_dir / "run.log"
    work = ROOT / "fair-pilot" / "staging" / "area3_work_epsg25832"
    source = ROOT / "fair-pilot" / "staging" / "area3_source_epsg32632"
    tmp_dir = run_dir / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    append_log(log, "stage=stats_candidates status=started")

    footprints_doc = json.loads((work / "footprints_area3_epsg25832.geojson").read_text(encoding="utf-8"))
    footprints_source_doc = json.loads((work / "footprints_area3_source_epsg32632.geojson").read_text(encoding="utf-8"))
    roofs_source_doc = json.loads((work / "roofs_area3_source_epsg32632.geojson").read_text(encoding="utf-8"))
    target_polygons = [shape(feature["geometry"]).buffer(0) for feature in footprints_doc["features"]]
    source_polygons = [shape(feature["geometry"]).buffer(0) for feature in footprints_source_doc["features"]]
    union = unary_union(target_polygons)

    dim_path = work / "dim_official_09cm_area3_epsg25832.tif"
    ortho_path = work / "ortho_09cm_area3_epsg25832.tif"
    dim_info = raster_info(dim_path, log)
    ortho_info = raster_info(ortho_path, log)
    dim_size = tuple(dim_info["size"])
    ortho_size = tuple(ortho_info["size"])
    dim_gt = dim_info["geoTransform"]
    ortho_gt = ortho_info["geoTransform"]

    dim_bin = tmp_dir / "dim_official.bin"
    run(["gdal_translate", "-of", "ENVI", "-ot", "Float32", str(dim_path), str(dim_bin)], log)
    dim = np.fromfile(dim_bin, dtype="<f4").reshape(dim_size[1], dim_size[0])
    ortho_png = tmp_dir / "ortho.png"
    run(["gdal_translate", "-of", "PNG", str(ortho_path), str(ortho_png)], log)
    ortho = np.asarray(Image.open(ortho_png), dtype=np.float32)
    if ortho.ndim == 2:
        gray = ortho
    else:
        gray = ortho[..., :3].mean(axis=2)
    grad_y, grad_x = np.gradient(gray)
    gradient = np.hypot(grad_x, grad_y)

    als_file = work / "als_area3_buf10_epsg25832.laz"
    als_las = laspy.read(als_file)
    als_xyz = np.column_stack([als_las.x, als_las.y, als_las.z])

    mvs_manifest_path = run_dir / "mvs_manifest.json"
    mvs_manifest = json.loads(mvs_manifest_path.read_text(encoding="utf-8")) if mvs_manifest_path.exists() else {"status": "not_run"}
    custom_xyz = np.empty((0, 3), dtype=float)
    custom_laz = work / "dim_colmap_area3_epsg25832.laz"
    fused = ROOT / mvs_manifest.get("fused", {}).get("path", "fair-pilot/runs/20260714_vaihingen_area3/mvs/fused_source_epsg32632.ply")
    if mvs_manifest.get("status") == "complete" and fused.exists():
        prepare = json.loads((run_dir / "prepare_summary.json").read_text(encoding="utf-8"))
        xmin, ymin, xmax, ymax = prepare["source_bbox"]
        pipeline = {
            "pipeline": [
                {"type": "readers.ply", "filename": str(fused), "spatialreference": cfg["pilot"]["source_crs"]},
                {"type": "filters.crop", "bounds": f"([{xmin-10},{xmax+10}],[{ymin-10},{ymax+10}])"},
                {"type": "filters.reprojection", "out_srs": cfg["pilot"]["output_crs"]},
                {"type": "writers.las", "filename": str(custom_laz), "compression": "laszip", "a_srs": cfg["pilot"]["output_crs"], "minor_version": 4, "dataformat_id": 6},
            ]
        }
        pipeline_path = tmp_dir / "mvs_reproject_pipeline.json"
        atomic_text(pipeline_path, json.dumps(pipeline, indent=2) + "\n")
        try:
            run(["pdal", "pipeline", str(pipeline_path)], log)
            mvs_las = laspy.read(custom_laz)
            custom_xyz = np.column_stack([mvs_las.x, mvs_las.y, mvs_las.z])
        except Exception as exc:
            append_log(log, f"stage=stats_candidates custom_mvs_reprojection=failed reason={type(exc).__name__}:{exc}")

    # Roof reference height per source footprint; reference is candidate/scoring metadata only.
    roof_points = np.array(
        [coordinate[:3] for feature in roofs_source_doc["features"] for coordinate in walk_coordinates(feature["geometry"]["coordinates"]) if len(coordinate) >= 3],
        dtype=float,
    )
    poses = parse_daporp(source / "Images" / "daporp.dat")
    selected_poses = {stem: poses[stem] for stem in cfg["pilot"]["images"]}
    axis_change = np.diag([1.0, -1.0, -1.0])
    rules = cfg["candidate_rules"]
    grid = float(rules["coverage_grid_m"])
    radius = float(rules["coverage_radius_m"])
    metrics = []
    for index, (polygon, source_polygon) in enumerate(zip(target_polygons, source_polygons)):
        candidate_id = f"vaihingen_a3_{index:03d}"
        area = float(polygon.area)
        center = polygon.centroid
        source_center = source_polygon.centroid
        nearest = min(float(polygon.distance(other)) for j, other in enumerate(target_polygons) if j != index)
        neighbors = unary_union([other for j, other in enumerate(target_polygons) if j != index])
        ring = polygon.buffer(10.0).difference(polygon)
        ring_fraction = float(ring.intersection(neighbors).area / ring.area) if ring.area else math.nan

        dim_mask = geometry_mask(polygon, dim_size, dim_gt)
        ortho_mask = geometry_mask(polygon, ortho_size, ortho_gt)
        dim_values = dim[dim_mask]
        valid_dim = np.isfinite(dim_values) & (dim_values > -9000)
        dim_valid_count = int(valid_dim.sum())
        dim_total = int(dim_values.size)
        dim_hole = 1.0 - dim_valid_count / dim_total if dim_total else math.nan
        dim_z_median = float(np.median(dim_values[valid_dim])) if dim_valid_count else math.nan
        texture_values = gradient[ortho_mask]
        texture_median = float(np.median(texture_values)) if texture_values.size else math.nan
        texture_p10 = float(np.percentile(texture_values, 10)) if texture_values.size else math.nan

        in_als = als_xyz[
            (als_xyz[:, 0] >= polygon.bounds[0]) & (als_xyz[:, 0] <= polygon.bounds[2])
            & (als_xyz[:, 1] >= polygon.bounds[1]) & (als_xyz[:, 1] <= polygon.bounds[3])
        ]
        if in_als.size:
            inside = np.array([polygon.covers(Point(x, y)) for x, y in in_als[:, :2]], dtype=bool)
            in_als = in_als[inside]
        in_custom = custom_xyz[
            (custom_xyz[:, 0] >= polygon.bounds[0]) & (custom_xyz[:, 0] <= polygon.bounds[2])
            & (custom_xyz[:, 1] >= polygon.bounds[1]) & (custom_xyz[:, 1] <= polygon.bounds[3])
        ]
        if in_custom.size:
            inside = np.array([polygon.covers(Point(x, y)) for x, y in in_custom[:, :2]], dtype=bool)
            in_custom = in_custom[inside]
        custom_covered, custom_grid_total, custom_hole = grid_coverage(in_custom[:, :2], polygon, grid, radius)

        roof_local = roof_points[
            (roof_points[:, 0] >= source_polygon.bounds[0] - 0.5) & (roof_points[:, 0] <= source_polygon.bounds[2] + 0.5)
            & (roof_points[:, 1] >= source_polygon.bounds[1] - 0.5) & (roof_points[:, 1] <= source_polygon.bounds[3] + 0.5)
        ]
        if roof_local.size:
            roof_inside = np.array([source_polygon.buffer(0.5).covers(Point(x, y)) for x, y in roof_local[:, :2]], dtype=bool)
            roof_local = roof_local[roof_inside]
        roof_z = float(np.median(roof_local[:, 2])) if roof_local.size else dim_z_median

        world = np.array([source_center.x, source_center.y, roof_z])
        visible = []
        for stem, pose in selected_poses.items():
            r_cw = axis_change @ pose["r_cam_to_world"].T
            camera = r_cw @ (world - pose["center"])
            if camera[2] <= 0:
                continue
            u = 10000.0 * camera[0] / camera[2] + 3840.0
            v = 10000.0 * camera[1] / camera[2] + 6912.0
            if 0 <= u < 7680 and 0 <= v < 13824:
                visible.append(stem)
        bh_values = []
        for a in range(len(visible)):
            for b in range(a + 1, len(visible)):
                ca = selected_poses[visible[a]]["center"]
                cb = selected_poses[visible[b]]["center"]
                baseline = float(np.linalg.norm(ca - cb))
                height = (float(np.linalg.norm(ca - world)) + float(np.linalg.norm(cb - world))) / 2
                bh_values.append(baseline / height if height else math.nan)

        metrics.append(
            {
                "candidate_id": candidate_id, "source_feature_index": index,
                "centroid_e_epsg25832": center.x, "centroid_n_epsg25832": center.y, "footprint_area_m2": area,
                "texture_gradient_median": texture_median, "texture_gradient_p10": texture_p10,
                "nearest_building_distance_m": nearest, "building_fraction_in_10m_ring": ring_fraction,
                "visible_view_count": len(visible), "visible_views": ";".join(visible),
                "max_baseline_height_ratio": max(bh_values) if bh_values else math.nan,
                "reference_roof_z_m": roof_z,
                "official_dim_cells": dim_valid_count, "official_dim_hole_ratio": dim_hole,
                "official_dim_density_cells_m2": dim_valid_count / area if area else math.nan, "official_dim_z_median": dim_z_median,
                "custom_dim_points": len(in_custom), "custom_dim_density_points_m2": len(in_custom) / area if area else math.nan,
                "custom_dim_grid_cells_covered": custom_covered, "custom_dim_grid_cells_total": custom_grid_total,
                "custom_dim_hole_ratio": custom_hole,
                "als_points": len(in_als), "als_density_points_m2": len(in_als) / area if area else math.nan,
            }
        )
        write_csv(run_dir / "building_metrics_incremental.csv", metrics, list(metrics[0]))
        append_log(log, f"stage=stats_candidates item={index+1}/{len(target_polygons)} candidate_id={candidate_id}")

    eligible = [row for row in metrics if row["footprint_area_m2"] >= float(rules["minimum_footprint_area_m2"])]
    texture_threshold = float(np.percentile([row["texture_gradient_median"] for row in eligible], rules["textureless_gradient_percentile"]))
    open_threshold = float(np.percentile([row["nearest_building_distance_m"] for row in eligible], rules["open_nearest_building_percentile"]))
    rows = []
    for row in metrics:
        textureless = row["footprint_area_m2"] >= float(rules["minimum_footprint_area_m2"]) and row["texture_gradient_median"] <= texture_threshold
        open_site = row["nearest_building_distance_m"] >= open_threshold and row["building_fraction_in_10m_ring"] <= float(rules["open_building_fraction_10m_max"])
        good_geometry = row["visible_view_count"] >= int(rules["good_view_count_min"]) and row["max_baseline_height_ratio"] >= float(rules["good_max_baseline_height_ratio_min"])
        selected = textureless and open_site and good_geometry
        rendered = {
            "candidate_id": row["candidate_id"], "source_feature_index": row["source_feature_index"],
            "centroid_e_epsg25832": f(row["centroid_e_epsg25832"], 3), "centroid_n_epsg25832": f(row["centroid_n_epsg25832"], 3),
            "footprint_area_m2": f(row["footprint_area_m2"], 9),
            "texture_gradient_median": f(row["texture_gradient_median"], 9), "texture_gradient_p10": f(row["texture_gradient_p10"], 9),
            "textureless_threshold_p40": f(texture_threshold, 9), "texture_class": "textureless" if textureless else "other",
            "nearest_building_distance_m": f(row["nearest_building_distance_m"], 9), "open_threshold_p50_m": f(open_threshold, 9),
            "building_fraction_in_10m_ring": f(row["building_fraction_in_10m_ring"], 9),
            "open_building_fraction_10m_max": f(rules["open_building_fraction_10m_max"], 9),
            "openness_class": "open" if open_site else "not_open",
            "visible_view_count": row["visible_view_count"], "visible_views": row["visible_views"],
            "max_baseline_height_ratio": f(row["max_baseline_height_ratio"], 9), "view_geometry_class": "good" if good_geometry else "other",
            "official_dim_cells": row["official_dim_cells"], "official_dim_hole_ratio": f(row["official_dim_hole_ratio"]),
            "official_dim_density_cells_m2": f(row["official_dim_density_cells_m2"]), "official_dim_z_median": f(row["official_dim_z_median"]),
            "custom_dim_status": mvs_manifest.get("status", "not_run"),
            "custom_dim_points": row["custom_dim_points"], "custom_dim_density_points_m2": f(row["custom_dim_density_points_m2"]),
            "custom_dim_grid_cells_covered": row["custom_dim_grid_cells_covered"], "custom_dim_grid_cells_total": row["custom_dim_grid_cells_total"],
            "custom_dim_hole_ratio": f(row["custom_dim_hole_ratio"]),
            "als_points": row["als_points"], "als_density_points_m2": f(row["als_density_points_m2"]),
            "reference_roof_z_m": f(row["reference_roof_z_m"]), "selected_positive_control": str(selected).lower(),
            "crs": cfg["pilot"]["output_crs"],
            "reference_role": "footprint/roof reference used only for pilot candidate definition and measurement; not GS training input",
        }
        rows.append(rendered)

    candidates = [row for row in rows if row["selected_positive_control"] == "true"]
    candidates.sort(key=lambda row: (-float(row["official_dim_hole_ratio"] or 0), float(row["texture_gradient_median"]), -float(row["nearest_building_distance_m"])))
    fields = list(rows[0])
    write_csv(run_dir / "all_building_metrics.csv", rows, fields)
    write_csv(ROOT / "fair-pilot" / "docs" / "positive_control_candidates.csv", candidates, fields)

    footprint_mask = geometry_mask(union, dim_size, dim_gt)
    footprint_dim = dim[footprint_mask]
    footprint_valid = np.isfinite(footprint_dim) & (footprint_dim > -9000)
    custom_extent = None
    if custom_xyz.size:
        custom_extent = [float(custom_xyz[:, 0].min()), float(custom_xyz[:, 1].min()), float(custom_xyz[:, 2].min()), float(custom_xyz[:, 0].max()), float(custom_xyz[:, 1].max()), float(custom_xyz[:, 2].max())]
    report = f"""# fair-pilot MVS baseline statistics — Vaihingen Area 3

Generated by `scripts/fair_pilot/05_stats_candidates.py`. Numbers and locked classifications only.

## Run boundary

| Field | Value |
|---|---|
| Pilot | Vaihingen Area 3 (Residential Area) |
| Source CRS | {cfg['pilot']['source_crs']} |
| Output CRS | {cfg['pilot']['output_crs']} |
| Original images staged | {len(cfg['pilot']['images'])} |
| Pose source | `Images/daporp.dat`, fixed |
| GS training | 0 |
| LoD2/roof reference role | candidate definition and measurement only; not training input |

## Dense-image-matching baseline

| Metric | Official ISPRS Match-T DIM | Fixed-pose COLMAP pilot |
|---|---:|---:|
| Status | complete | {mvs_manifest.get('status', 'not_run')} |
| Native evidence | 9 cm DSM | fused point cloud |
| Area 3 footprint valid cells / points | {int(footprint_valid.sum())} | {len(custom_xyz)} |
| Area 3 footprint raster hole ratio | {f(1.0 - footprint_valid.sum() / footprint_valid.size if footprint_valid.size else math.nan)} | see per-building 0.25 m grid |
| Z median in footprint [m] | {f(float(np.median(footprint_dim[footprint_valid])) if footprint_valid.any() else math.nan)} | {f(float(np.median(custom_xyz[:,2])) if custom_xyz.size else math.nan)} |
| Fixed-pose output extent E/N/Z | n/a | {custom_extent or 'n/a'} |
| Reprojection threshold | source product | {cfg['pilot']['reprojection_error_px']} px |

The official 9 cm DIM DSM is the dataset-provided dense-matching product. Its
technical description states that small voids were filled by nonlinear diffusion;
the recorded hole ratio therefore describes the distributed baseline raster.

## ALS staging

| Metric | Value |
|---|---:|
| Reprojected Area 3 + 10 m points | {len(als_xyz)} |
| Extent E min / N min / Z min | {f(als_xyz[:,0].min(),3)} / {f(als_xyz[:,1].min(),3)} / {f(als_xyz[:,2].min(),3)} |
| Extent E max / N max / Z max | {f(als_xyz[:,0].max(),3)} / {f(als_xyz[:,1].max(),3)} / {f(als_xyz[:,2].max(),3)} |

## Positive-control classification

| Field | Locked value |
|---|---:|
| Footprint count | {len(rows)} |
| Area-eligible count (>= {rules['minimum_footprint_area_m2']} m2) | {len(eligible)} |
| Textureless threshold (eligible-building gradient p{rules['textureless_gradient_percentile']}) | {f(texture_threshold,9)} |
| Open threshold (eligible-building nearest-distance p{rules['open_nearest_building_percentile']}) [m] | {f(open_threshold,9)} |
| Open 10 m ring building-fraction maximum | {rules['open_building_fraction_10m_max']} |
| Good view minimum | {rules['good_view_count_min']} views |
| Good max B/H minimum | {rules['good_max_baseline_height_ratio_min']} |
| Selected positive-control candidates | {len(candidates)} |

Visible view means that the footprint center at reference-roof z has positive
depth and projects inside the original image bounds; occlusion is not tested.
The reported B/H uses camera-centre baseline divided by mean slant range to that
center. These locked proxy definitions are used only for candidate classification.

Per-building audit rows: `fair-pilot/runs/{cfg['run_id']}/all_building_metrics.csv`.
Candidate rows: `fair-pilot/docs/positive_control_candidates.csv`.
"""
    atomic_text(ROOT / "fair-pilot" / "docs" / "baseline_mvs_stats.md", report)

    versions = [
        f"timestamp={time.strftime('%Y-%m-%dT%H:%M:%S%z')}", f"python={platform.python_version()}",
        f"tools_image_id={os.environ.get('FAIR_TOOLS_IMAGE_ID', 'not_provided')}",
        f"colmap_image_id={os.environ.get('FAIR_COLMAP_IMAGE_ID', 'not_provided')}",
        f"config_sha256={sha256(ROOT / args.config)}", f"source_archive_sha256={cfg['archive']['expected_sha256']}",
        f"git_head={subprocess.run(['git','-c',f'safe.directory={ROOT}','rev-parse','HEAD'],capture_output=True,text=True).stdout.strip()}",
        "source_crs=EPSG:32632", "output_crs=EPSG:25832", "gs_training_runs=0",
    ]
    for command in (["gdalinfo", "--version"], ["pdal", "--version"]):
        result = subprocess.run(command, capture_output=True, text=True)
        versions.append((result.stdout or result.stderr).strip().replace("\n", " | "))
    atomic_text(run_dir / "versions.txt", "\n".join(versions) + "\n")

    overall_status = "complete" if mvs_manifest.get("status") == "complete" else "partial"
    summary = {
        "task_id": cfg["task_id"], "run_id": cfg["run_id"], "stage": "stats_candidates", "status": "complete",
        "overall_status": overall_status,
        "training_runs": 0, "source_crs": cfg["pilot"]["source_crs"], "output_crs": cfg["pilot"]["output_crs"],
        "buildings": len(rows), "area_eligible": len(eligible), "positive_control_candidates": len(candidates),
        "thresholds": {"texture_gradient_p40": texture_threshold, "open_distance_p50_m": open_threshold, **rules},
        "official_dim": {"footprint_valid_cells": int(footprint_valid.sum()), "footprint_total_cells": int(footprint_valid.size)},
        "fixed_pose_colmap": {"status": mvs_manifest.get("status", "not_run"), "area3_points": len(custom_xyz)},
        "als_points": len(als_xyz),
        "artifacts": {
            "inventory": "fair-pilot/docs/data_inventory.md", "baseline": "fair-pilot/docs/baseline_mvs_stats.md",
            "candidates": "fair-pilot/docs/positive_control_candidates.csv", "all_metrics": f"fair-pilot/runs/{cfg['run_id']}/all_building_metrics.csv",
            "incremental_metrics": f"fair-pilot/runs/{cfg['run_id']}/building_metrics_incremental.csv",
        },
    }
    atomic_text(run_dir / "final_summary.json", json.dumps(summary, indent=2) + "\n")

    inventory_path = ROOT / "fair-pilot" / "docs" / "data_inventory.md"
    inventory = inventory_path.read_text(encoding="utf-8")
    inventory = inventory.replace("| Bounded Area 3 selective staging | pending |", "| Bounded Area 3 selective staging | complete |")
    inventory = inventory.replace("| Provided-pose MVS baseline | pending |", f"| Provided-pose MVS baseline | {mvs_manifest.get('status', 'not_run')} |")
    inventory = inventory.replace("| Candidate metrics | pending |", "| Candidate metrics | complete |")
    atomic_text(inventory_path, inventory)
    append_log(log, f"stage=stats_candidates status=complete candidates={len(candidates)} custom_mvs={mvs_manifest.get('status', 'not_run')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
