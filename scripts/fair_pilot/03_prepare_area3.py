#!/usr/bin/env python3
"""Prepare EPSG:25832 reference assets and a fixed-pose COLMAP workspace."""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import subprocess
import time
from pathlib import Path

import numpy as np
from pyproj import Transformer


ROOT = Path(__file__).resolve().parents[3]


def append_log(path: Path, message: str) -> None:
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(f"{stamp}\t{message}\n")
        f.flush()
        os.fsync(f.fileno())


def run(command: list[str], log: Path) -> None:
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


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def walk_coordinates(value):
    if isinstance(value, list):
        if len(value) >= 2 and all(isinstance(v, (int, float)) for v in value[:2]):
            yield value
        else:
            for child in value:
                yield from walk_coordinates(child)


def parse_daporp(path: Path) -> dict[str, dict]:
    lines = [line.split() for line in path.read_text(encoding="latin1").splitlines() if line.strip()]
    if len(lines) % 3:
        raise ValueError("daporp.dat must contain three lines per image")
    result = {}
    for i in range(0, len(lines), 3):
        head, a, b = lines[i : i + 3]
        stem, focal, x, y, z = head
        values = [float(v) for v in a + b]
        if len(values) != 9:
            raise ValueError(f"invalid rotation payload for {stem}")
        r11, r21, r31, r12, r22, r32, r13, r23, r33 = values
        r_cam_to_world = np.array(
            [[r11, r12, r13], [r21, r22, r23], [r31, r32, r33]], dtype=float
        )
        result[stem] = {
            "focal_mm": float(focal),
            "center": np.array([float(x), float(y), float(z)], dtype=float),
            "r_cam_to_world": r_cam_to_world,
        }
    return result


def rotmat_to_qvec(r: np.ndarray) -> np.ndarray:
    # COLMAP Hamilton quaternion, scalar first.
    k = np.array(
        [
            [r[0, 0] - r[1, 1] - r[2, 2], r[0, 1] + r[1, 0], r[0, 2] + r[2, 0], r[2, 1] - r[1, 2]],
            [r[0, 1] + r[1, 0], r[1, 1] - r[0, 0] - r[2, 2], r[1, 2] + r[2, 1], r[0, 2] - r[2, 0]],
            [r[0, 2] + r[2, 0], r[1, 2] + r[2, 1], r[2, 2] - r[0, 0] - r[1, 1], r[1, 0] - r[0, 1]],
            [r[2, 1] - r[1, 2], r[0, 2] - r[2, 0], r[1, 0] - r[0, 1], r[0, 0] + r[1, 1] + r[2, 2]],
        ]
    ) / 3.0
    eigvals, eigvecs = np.linalg.eigh(k)
    q = eigvecs[:, np.argmax(eigvals)][[3, 0, 1, 2]]
    if q[0] < 0:
        q *= -1
    return q / np.linalg.norm(q)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/fair_pilot/vaihingen_area3.json")
    args = parser.parse_args()
    cfg = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    run_dir = ROOT / "fair-pilot" / "runs" / cfg["run_id"]
    log = run_dir / "run.log"
    source = ROOT / "fair-pilot" / "staging" / "area3_source_epsg32632"
    work = ROOT / "fair-pilot" / "staging" / "area3_work_epsg25832"
    workspace = run_dir / "workspace"
    work.mkdir(parents=True, exist_ok=True)
    workspace.mkdir(parents=True, exist_ok=True)
    append_log(log, "stage=prepare status=started")

    ref_dir = source / "Reference_3d_reconstruction"
    footprint_shp = ref_dir / "Reference_Buildings" / "building_outline_area_3.shp"
    roof_dxf = ref_dir / "Reference_Roofs" / "gebaeude_area_3_3D_dachflaechen.dxf"
    footprint_geojson = work / "footprints_area3_epsg25832.geojson"
    footprint_gpkg = work / "footprints_area3_epsg25832.gpkg"
    roof_geojson = work / "roofs_area3_epsg25832.geojson"
    source_footprint_geojson = work / "footprints_area3_source_epsg32632.geojson"
    source_roof_geojson = work / "roofs_area3_source_epsg32632.geojson"

    for path in [footprint_geojson, footprint_gpkg, roof_geojson, source_footprint_geojson, source_roof_geojson]:
        if path.exists():
            path.unlink()
    run(["ogr2ogr", "-f", "GeoJSON", str(source_footprint_geojson), str(footprint_shp)], log)
    run(["ogr2ogr", "-f", "GPKG", "-t_srs", cfg["pilot"]["output_crs"], str(footprint_gpkg), str(footprint_shp), "-nln", "footprints_area3"], log)
    run(["ogr2ogr", "-f", "GeoJSON", "-t_srs", cfg["pilot"]["output_crs"], str(footprint_geojson), str(footprint_shp)], log)
    run(["ogr2ogr", "-f", "GeoJSON", "-dim", "XYZ", "-nlt", "PROMOTE_TO_MULTI", "-a_srs", cfg["pilot"]["source_crs"], str(source_roof_geojson), str(roof_dxf)], log)
    run(["ogr2ogr", "-f", "GeoJSON", "-dim", "XYZ", "-nlt", "PROMOTE_TO_MULTI", "-s_srs", cfg["pilot"]["source_crs"], "-t_srs", cfg["pilot"]["output_crs"], str(roof_geojson), str(roof_dxf)], log)

    footprints_source = json.loads(source_footprint_geojson.read_text(encoding="utf-8"))
    source_xy = [xy for feature in footprints_source["features"] for xy in walk_coordinates(feature["geometry"]["coordinates"])]
    xmin, ymin = np.min(np.array(source_xy)[:, :2], axis=0)
    xmax, ymax = np.max(np.array(source_xy)[:, :2], axis=0)
    transformer = Transformer.from_crs(cfg["pilot"]["source_crs"], cfg["pilot"]["output_crs"], always_xy=True)
    target_corners = np.array([transformer.transform(x, y) for x, y in [(xmin, ymin), (xmin, ymax), (xmax, ymin), (xmax, ymax)]])
    txmin, tymin = target_corners.min(axis=0) - 10.0
    txmax, tymax = target_corners.max(axis=0) + 10.0

    raster_jobs = [
        (source / "DSM" / "DSM_09cm_matching.tif", work / "dim_official_09cm_area3_epsg25832.tif", "0.09", "bilinear", "-9999"),
        (source / "DSM" / "DSM_25cm_ALS.tif", work / "als_dsm_25cm_area3_epsg25832.tif", "0.25", "bilinear", "-9999"),
        (source / "Ortho" / "TOP_Mosaic_09cm.tif", work / "ortho_09cm_area3_epsg25832.tif", "0.09", "bilinear", "0"),
    ]
    for src, dst, resolution, resampling, nodata in raster_jobs:
        run(
            [
                "gdalwarp", "-overwrite", "-s_srs", cfg["pilot"]["source_crs"], "-t_srs", cfg["pilot"]["output_crs"],
                "-te", f"{txmin:.3f}", f"{tymin:.3f}", f"{txmax:.3f}", f"{tymax:.3f}",
                "-tr", resolution, resolution, "-r", resampling, "-dstnodata", nodata,
                "-co", "TILED=YES", "-co", "COMPRESS=DEFLATE", str(src), str(dst),
            ],
            log,
        )

    # Stage ALS source strips as a bounded, reprojected point cloud.
    als_out = work / "als_area3_buf10_epsg25832.laz"
    pipeline = {
        "pipeline": [
            {"type": "readers.las", "filename": str(source / "ALS" / "Vaihingen_Strip_03.LAS"), "spatialreference": cfg["pilot"]["source_crs"]},
            {"type": "readers.las", "filename": str(source / "ALS" / "Vaihingen_Strip_05.LAS"), "spatialreference": cfg["pilot"]["source_crs"]},
            {"type": "filters.merge"},
            {"type": "filters.crop", "bounds": f"([{xmin-10:.3f},{xmax+10:.3f}],[{ymin-10:.3f},{ymax+10:.3f}])"},
            {"type": "filters.reprojection", "out_srs": cfg["pilot"]["output_crs"]},
            {"type": "writers.las", "filename": str(als_out), "compression": "laszip", "a_srs": cfg["pilot"]["output_crs"], "minor_version": 4, "dataformat_id": 6},
        ]
    }
    pipeline_path = workspace / "als_stage_pipeline.json"
    atomic_json(pipeline_path, pipeline)
    run(["pdal", "pipeline", str(pipeline_path)], log)

    # Downsample the locked ten images to 25% for bounded provided-pose MVS.
    image_dir = workspace / "images"
    image_dir.mkdir(parents=True, exist_ok=True)
    scale = float(cfg["pilot"]["image_scale"])
    percent = f"{scale * 100:g}%"
    for index, stem in enumerate(cfg["pilot"]["images"], 1):
        src = source / "Images" / f"{stem}.tif"
        dst = image_dir / f"{stem}.png"
        if not dst.exists():
            run(["gdal_translate", "-of", "PNG", "-ot", "Byte", "-scale", "0", "2047", "0", "255", "-outsize", percent, percent, str(src), str(dst)], log)
        append_log(log, f"stage=prepare image={index}/{len(cfg['pilot']['images'])} path={dst.relative_to(ROOT)}")

    # Fixed COLMAP poses from daporp.dat. DGPF camera axes -> COLMAP CV axes.
    poses = parse_daporp(source / "Images" / "daporp.dat")
    width, height = 1920, 3456
    focal = 10000.0 * scale
    cx, cy = 3840.0 * scale, 6912.0 * scale
    sparse = workspace / "sparse_text"
    sparse.mkdir(parents=True, exist_ok=True)
    (sparse / "cameras.txt").write_text(f"1 PINHOLE {width} {height} {focal:.12f} {focal:.12f} {cx:.12f} {cy:.12f}\n", encoding="utf-8")

    roof_source = json.loads(source_roof_geojson.read_text(encoding="utf-8"))
    roof_zs = [float(c[2]) for feature in roof_source["features"] for c in walk_coordinates(feature["geometry"]["coordinates"]) if len(c) >= 3]
    reference_z = float(np.median(roof_zs)) if roof_zs else 260.0
    centroid = np.mean(np.array(source_xy)[:, :2], axis=0)
    world_test = np.array([centroid[0], centroid[1], reference_z])
    image_lines = []
    checks = []
    axis_change = np.diag([1.0, -1.0, -1.0])
    for image_id, stem in enumerate(cfg["pilot"]["images"], 1):
        pose = poses[stem]
        r_doc = pose["r_cam_to_world"]
        r_cw = axis_change @ r_doc.T
        center = pose["center"]
        tvec = -r_cw @ center
        qvec = rotmat_to_qvec(r_cw)
        camera_point = r_cw @ world_test + tvec
        u = focal * camera_point[0] / camera_point[2] + cx
        v = focal * camera_point[1] / camera_point[2] + cy
        checks.append(
            {
                "image": stem,
                "center_x_source": center[0], "center_y_source": center[1], "center_z_m": center[2],
                "rotation_det": float(np.linalg.det(r_cw)), "projected_centroid_u": u, "projected_centroid_v": v,
                "centroid_depth_m": camera_point[2], "centroid_in_bounds": int(0 <= u < width and 0 <= v < height and camera_point[2] > 0),
            }
        )
        values = [*qvec.tolist(), *tvec.tolist()]
        image_lines.append(f"{image_id} " + " ".join(f"{v:.15g}" for v in values) + f" 1 {stem}.png\n\n")
    (sparse / "images.txt").write_text("".join(image_lines), encoding="utf-8")
    (sparse / "points3D.txt").write_text("", encoding="utf-8")
    with (run_dir / "pose_check.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(checks[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(checks)

    # PatchMatch neighbor file: all other locked Area 3 views, ordered by camera-baseline distance.
    patch_lines = []
    for stem in cfg["pilot"]["images"]:
        center = poses[stem]["center"]
        neighbors = sorted((other for other in cfg["pilot"]["images"] if other != stem), key=lambda other: float(np.linalg.norm(poses[other]["center"] - center)))
        patch_lines.extend([f"{stem}.png\n", ", ".join(f"{other}.png" for other in neighbors) + "\n"])
    stereo = workspace / "stereo"
    stereo.mkdir(parents=True, exist_ok=True)
    (stereo / "patch-match.cfg").write_text("".join(patch_lines), encoding="utf-8")
    (stereo / "fusion.cfg").write_text("".join(f"{stem}.png\n" for stem in cfg["pilot"]["images"]), encoding="utf-8")

    summary = {
        "task_id": cfg["task_id"], "run_id": cfg["run_id"], "stage": "prepare", "status": "complete",
        "pilot_area": cfg["pilot"]["area"], "source_crs": cfg["pilot"]["source_crs"], "output_crs": cfg["pilot"]["output_crs"],
        "source_bbox": [float(xmin), float(ymin), float(xmax), float(ymax)],
        "output_bbox_with_buffer": [float(txmin), float(tymin), float(txmax), float(tymax)],
        "reference_roof_z_median_source": reference_z,
        "footprint_features": len(footprints_source["features"]),
        "images": cfg["pilot"]["images"], "image_scale": scale, "image_size": [width, height],
        "colmap_camera": {"model": "PINHOLE", "fx": focal, "fy": focal, "cx": cx, "cy": cy},
        "pose_axis_conversion": "R_world_to_colmap_camera = diag(1,-1,-1) @ R_dgpf_camera_to_world.T",
        "centroid_visible_views": sum(row["centroid_in_bounds"] for row in checks),
        "official_dim": str((work / "dim_official_09cm_area3_epsg25832.tif").relative_to(ROOT)),
        "als": str(als_out.relative_to(ROOT)),
    }
    atomic_json(run_dir / "prepare_summary.json", summary)
    append_log(log, f"stage=prepare status=complete images={len(cfg['pilot']['images'])} centroid_visible={summary['centroid_visible_views']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
