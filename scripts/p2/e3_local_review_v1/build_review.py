#!/usr/bin/env python3
"""Build the pre-training image/seed review package for one local E3 target.

The implementation deliberately reuses the canonical COLMAP readers, coordinate-safe
projection helpers, common-manifest prism/crop utilities, and prepared E3 seed.  It
does not materialize a training dataset or launch a learning run.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps
from shapely.geometry import shape
from torch.utils.tensorboard import SummaryWriter

from scripts.p2.qualitative_199_common_manifest_v1.build_manifest import (
    crop_xyxy,
    prism_points,
)
from src.stage2.colmap_io import read_cameras_bin, read_images_bin, read_points3d_bin
from src.stage2.image_projection import (
    base_to_canonical,
    canonical_to_base,
    in_frame_mask,
    project_canonical_points,
)
from src.stage2.pilot_scene_prep import WORLD_SHIFT, read_ply_xyz


SCHEMA = "jointbuildgs.p2.e3_local_review.receipt.v1"


def require_docker() -> None:
    if not Path("/.dockerenv").exists():
        raise RuntimeError("E3 local review must run in the pinned Docker image")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def load_building(path: Path, building_id: str) -> dict[str, Any]:
    matches = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if building_id in line
    ]
    matches = [row for row in matches if row.get("building_id") == building_id]
    if len(matches) != 1:
        raise RuntimeError(f"expected one building row for {building_id}, got {len(matches)}")
    return matches[0]


def load_footprint(path: Path, building_id: str) -> Any:
    payload = json.loads(path.read_text(encoding="utf-8"))
    matches = []
    for feature in payload.get("features", []):
        properties = feature.get("properties", {})
        values = {str(value) for value in properties.values()}
        if building_id in values or building_id.replace("DEBY_LOD2_", "") in values:
            matches.append(shape(feature["geometry"]))
    if len(matches) != 1:
        raise RuntimeError(f"expected one shared footprint for {building_id}, got {len(matches)}")
    return matches[0]


def camera_center(image: Any) -> np.ndarray:
    rotation = image.R()
    return -(rotation.T @ np.asarray(image.tvec, dtype=np.float64))


def angular_separation(left: np.ndarray, right: np.ndarray) -> float:
    return math.degrees(math.acos(float(np.clip(left @ right, -1.0, 1.0))))


def candidate_strata(candidate: Mapping[str, Any], config: Mapping[str, Any]) -> tuple[int, int]:
    azimuth_width = 360.0 / int(config["azimuth_bin_count"])
    azimuth_bin = int(float(candidate["azimuth_deg"]) // azimuth_width) % int(
        config["azimuth_bin_count"]
    )
    low, high = map(float, config["nadir_bin_edges_deg"])
    nadir = float(candidate["nadir_deg"])
    nadir_bin = 0 if nadir < low else 1 if nadir < high else 2
    return azimuth_bin, nadir_bin


def augment_validation(
    candidates: Sequence[dict[str, Any]], config: Mapping[str, Any]
) -> tuple[set[str], set[str]]:
    protected = {row["view_name"] for row in candidates if row["global_role"] == "eval"}
    target = max(
        int(config["minimum_validation_views"]),
        int(math.ceil(len(candidates) * float(config["validation_fraction"]))),
    )
    selected = [row for row in candidates if row["view_name"] in protected]
    additions: set[str] = set()
    pool = sorted(
        [row for row in candidates if row["global_role"] == "train"],
        key=lambda row: row["view_name"],
    )
    while len(selected) < target and pool:
        used_azimuth = {candidate_strata(row, config)[0] for row in selected}
        used_nadir = {candidate_strata(row, config)[1] for row in selected}

        def score(row: Mapping[str, Any]) -> tuple[float, ...]:
            azimuth_bin, nadir_bin = candidate_strata(row, config)
            minimum_angle = (
                min(
                    angular_separation(row["view_direction"], other["view_direction"])
                    for other in selected
                )
                if selected
                else 180.0
            )
            return (
                float(azimuth_bin not in used_azimuth),
                float(nadir_bin not in used_nadir),
                minimum_angle,
                float(row["projected_area_px2"]),
            )

        chosen = max(pool, key=score)
        additions.add(str(chosen["view_name"]))
        selected.append(chosen)
        pool.remove(chosen)
    if len(selected) < target:
        raise RuntimeError(f"cannot construct {target} local validation views")
    return protected, additions


def polygon_rings(geometry: Any) -> Iterable[np.ndarray]:
    polygons = list(geometry.geoms) if geometry.geom_type == "MultiPolygon" else [geometry]
    for polygon in polygons:
        yield np.asarray(polygon.exterior.coords, dtype=np.float64)
        for interior in polygon.interiors:
            yield np.asarray(interior.coords, dtype=np.float64)


def projected_footprint_rings(
    footprint: Any,
    z_m: float,
    scene_reference: Mapping[str, Any],
    image: Any,
    camera: Any,
) -> list[np.ndarray]:
    output = []
    for ring in polygon_rings(footprint):
        base = np.column_stack((ring[:, :2], np.full(len(ring), z_m)))
        canonical = base_to_canonical(base, scene_reference, input_datum="ellipsoidal")
        result = project_canonical_points(canonical, image, camera)
        valid = result.valid & np.isfinite(result.uv).all(axis=1)
        if np.all(valid):
            output.append(result.uv)
    return output


def crop_seed(
    points: np.ndarray,
    bbox_utm: Sequence[float],
    z_range_ellipsoidal: Sequence[float],
) -> np.ndarray:
    bbox = np.asarray(bbox_utm, dtype=np.float64)
    z_range = np.asarray(z_range_ellipsoidal, dtype=np.float64) - WORLD_SHIFT[2]
    keep = (
        (points[:, 0] >= bbox[0] - WORLD_SHIFT[0])
        & (points[:, 0] <= bbox[2] - WORLD_SHIFT[0])
        & (points[:, 1] >= bbox[1] - WORLD_SHIFT[1])
        & (points[:, 1] <= bbox[3] - WORLD_SHIFT[1])
        & (points[:, 2] >= z_range[0])
        & (points[:, 2] <= z_range[1])
    )
    return points[keep]


def depth_colors(depth: np.ndarray, kind: str) -> np.ndarray:
    if not len(depth):
        return np.empty((0, 3), dtype=np.uint8)
    low, high = np.percentile(depth, (2.0, 98.0))
    span = max(float(high - low), 1e-6)
    value = np.clip((depth - low) / span, 0.0, 1.0)
    if kind == "sparse":
        rgb = np.column_stack((40 + 80 * value, 220 - 60 * value, 255 - 30 * value))
    else:
        rgb = np.column_stack((255 - 30 * value, 130 + 90 * value, 35 + 30 * value))
    return np.rint(rgb).astype(np.uint8)


def draw_seed_overlay(
    base: Image.Image,
    points: np.ndarray,
    image: Any,
    camera: Any,
    crop: Sequence[int],
    maximum: int,
    kind: str,
) -> tuple[Image.Image, int, int]:
    result = project_canonical_points(points[:, :3], image, camera)
    inside = in_frame_mask(result, camera)
    x0, y0, x1, y1 = map(int, crop)
    inside &= (
        (result.uv[:, 0] >= x0)
        & (result.uv[:, 0] < x1)
        & (result.uv[:, 1] >= y0)
        & (result.uv[:, 1] < y1)
    )
    indices = np.flatnonzero(inside)
    projected_count = int(len(indices))
    if len(indices) > maximum:
        indices = indices[:: int(math.ceil(len(indices) / maximum))][:maximum]
    colors = depth_colors(result.depth[indices], kind)
    output = base.copy()
    draw = ImageDraw.Draw(output)
    radius = 2 if kind == "sparse" else 1
    for index, color in zip(indices, colors):
        px = float(result.uv[index, 0] - x0)
        py = float(result.uv[index, 1] - y0)
        fill = tuple(map(int, color))
        draw.ellipse((px - radius, py - radius, px + radius, py + radius), fill=fill)
    return output, projected_count, int(len(indices))


def fit_for_web(image: Image.Image, maximum_width: int) -> Image.Image:
    if image.width <= maximum_width:
        return image
    height = max(1, round(image.height * maximum_width / image.width))
    return image.resize((maximum_width, height), Image.Resampling.LANCZOS)


def label_panel(image: Image.Image, title: str, width: int = 300, height: int = 210) -> Image.Image:
    fitted = ImageOps.fit(image.convert("RGB"), (width, height), method=Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (width, height + 30), "#111827")
    canvas.paste(fitted, (0, 30))
    ImageDraw.Draw(canvas).text((8, 8), title, fill="white")
    return canvas


def contact_sheet(rows: Sequence[dict[str, Any]], output: Path) -> None:
    rendered = []
    for row in rows:
        panels = [
            label_panel(Image.open(row["original_path"]), f"{row['index']:02d} RGB · {row['local_role']}"),
            label_panel(Image.open(row["sparse_path"]), f"sparse · {row['sparse_projected_count']} px"),
            label_panel(Image.open(row["mvs_path"]), f"MVS 비교 · {row['mvs_projected_count']} px"),
        ]
        line = Image.new("RGB", (sum(panel.width for panel in panels), panels[0].height), "black")
        cursor = 0
        for panel in panels:
            line.paste(panel, (cursor, 0))
            cursor += panel.width
        rendered.append(line)
    sheet = Image.new("RGB", (rendered[0].width, sum(row.height for row in rendered)), "black")
    cursor = 0
    for row in rendered:
        sheet.paste(row, (0, cursor))
        cursor += row.height
    sheet.save(output)


def write_seed_assets(
    viewer: Path,
    sparse: np.ndarray,
    mvs: np.ndarray,
    target: np.ndarray,
) -> dict[str, Any]:
    assets = viewer / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    sparse_xyz = np.asarray(sparse[:, :3] - target, dtype=np.float32)
    sparse_rgb = np.asarray(np.clip(sparse[:, 3:6], 0, 255), dtype=np.uint8)
    mvs_xyz = np.asarray(mvs[:, :3] - target, dtype=np.float32)
    sparse_xyz.tofile(assets / "sparse_xyz_f32.bin")
    sparse_rgb.tofile(assets / "sparse_rgb_u8.bin")
    mvs_xyz.tofile(assets / "mvs_xyz_f32.bin")
    return {
        "sparse_xyz": "assets/sparse_xyz_f32.bin",
        "sparse_rgb": "assets/sparse_rgb_u8.bin",
        "mvs_xyz": "assets/mvs_xyz_f32.bin",
        "sparse_count": int(len(sparse)),
        "mvs_count": int(len(mvs)),
    }


def publish_tensorboard(
    root: Path,
    sheets: Sequence[Path],
    validation_rows: Sequence[dict[str, Any]],
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for old in root.glob("events.out.tfevents.*"):
        old.unlink()
    writer = SummaryWriter(root, filename_suffix=".input_review")
    for index, path in enumerate(sheets):
        writer.add_image(
            f"data/4906982/contact_sheet/page_{index + 1:02d}",
            np.asarray(Image.open(path).convert("RGB")),
            0,
            dataformats="HWC",
        )
    for row in validation_rows:
        tag = Path(row["view_name"]).stem
        for kind in ("original", "sparse", "mvs"):
            writer.add_image(
                f"data/4906982/validation/{tag}/{kind}",
                np.asarray(Image.open(row[f"{kind}_path"]).convert("RGB")),
                0,
                dataformats="HWC",
            )
    writer.add_text(
        "data/4906982/provenance",
        "Pre-training input review only. Sparse is the proposed S0 seed; MVS is display-only comparison. No learning run started.",
        0,
    )
    writer.flush()
    writer.close()


def build(config_path: Path, repo_root: Path, artifact_root: Path) -> dict[str, Any]:
    require_docker()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    inputs = {key: artifact_root / value for key, value in config["inputs"].items()}
    output_root = artifact_root / config["output_relative_root"]
    receipt_path = output_root / "receipt.json"
    source_paths = {
        key: path
        for key, path in inputs.items()
        if key != "tensorboard_publish_root"
    }
    sparse_root = inputs["colmap_root"] / "sparse"
    source_paths.update(
        {
            "colmap_cameras": sparse_root / "cameras.bin",
            "colmap_images": sparse_root / "images.bin",
            "colmap_points3D": sparse_root / "points3D.bin",
            "builder": Path(__file__),
            "viewer_index": repo_root / "src/apps/e3_local_seed_review/index.html",
            "viewer_app": repo_root / "src/apps/e3_local_seed_review/app.js",
        }
    )
    identity = {key: sha256(path) for key, path in source_paths.items() if path.is_file()}
    identity["config"] = sha256(config_path)

    building = load_building(inputs["building_manifest"], config["building_id"])
    footprint = load_footprint(inputs["shared_footprints"], config["building_id"])
    scene_reference = json.loads(inputs["scene_reference"].read_text(encoding="utf-8"))
    roles = json.loads(inputs["view_roles"].read_text(encoding="utf-8"))
    global_eval = set(map(str, roles["eval_views"]))
    colmap_root = inputs["colmap_root"]
    cameras = read_cameras_bin(sparse_root / "cameras.bin")
    images = read_images_bin(sparse_root / "images.bin")
    selection_base = prism_points(building["viewport_bbox_xy"], building["z_range_ellipsoidal_m"])
    selection_points = base_to_canonical(selection_base, scene_reference, input_datum="ellipsoidal")
    roof_base = np.vstack(
        [
            np.column_stack(
                (ring[:, :2], np.full(len(ring), building["z_range_ellipsoidal_m"][1]))
            )
            for ring in polygon_rings(footprint)
        ]
    )
    roof_points = base_to_canonical(roof_base, scene_reference, input_datum="ellipsoidal")
    center_base = np.asarray(
        [
            building["principal_frame"]["center_xy"][0],
            building["principal_frame"]["center_xy"][1],
            float(np.mean(building["z_range_ellipsoidal_m"])),
        ],
        dtype=np.float64,
    )
    center = base_to_canonical(center_base, scene_reference, input_datum="ellipsoidal")[0]
    selection_config = config["selection"]
    candidates = []
    for image in sorted(images.values(), key=lambda item: item.name):
        camera = cameras[image.camera_id]
        result = project_canonical_points(selection_points, image, camera)
        inside = in_frame_mask(result, camera)
        coverage = float(np.mean(inside))
        valid_uv = result.uv[inside]
        area = float(np.ptp(valid_uv[:, 0]) * np.ptp(valid_uv[:, 1])) if len(valid_uv) else 0.0
        minimum_area = float(selection_config["minimum_projected_area_fraction"]) * camera.width * camera.height
        center_canonical = camera_center(image)
        center_utm = canonical_to_base(center_canonical, scene_reference, output_datum="ellipsoidal")[0]
        delta = center_utm - center_base
        direction = delta / max(float(np.linalg.norm(delta)), 1e-12)
        camera_forward = image.R().T @ np.asarray([0.0, 0.0, 1.0], dtype=np.float64)
        camera_forward /= max(float(np.linalg.norm(camera_forward)), 1e-12)
        azimuth = math.degrees(math.atan2(float(delta[1]), float(delta[0]))) % 360.0
        nadir = math.degrees(math.acos(float(np.clip(direction[2], -1.0, 1.0))))
        roof_result = project_canonical_points(roof_points, image, camera)
        roof_inside = in_frame_mask(roof_result, camera)
        roof_coverage = float(np.mean(roof_inside))
        valid_roof_uv = roof_result.uv[
            roof_result.valid & np.isfinite(roof_result.uv).all(axis=1)
        ]
        roof_area = (
            float(np.ptp(valid_roof_uv[:, 0]) * np.ptp(valid_roof_uv[:, 1]))
            if len(valid_roof_uv)
            else 0.0
        )
        standard_gate = (
            coverage >= float(selection_config["minimum_projection_coverage"])
            and area >= minimum_area
        )
        near_nadir_gate = (
            nadir < float(selection_config["near_nadir_max_deg"])
            and roof_coverage
            >= float(selection_config["near_nadir_minimum_roof_vertex_coverage"])
            and roof_area >= minimum_area
        )
        if not (standard_gate or near_nadir_gate):
            continue
        front_uv = np.vstack(
            (
                result.uv[result.valid & np.isfinite(result.uv).all(axis=1)],
                valid_roof_uv,
            )
        )
        crop = crop_xyxy(
            front_uv,
            camera.width,
            camera.height,
            float(selection_config["crop_margin_scale"]),
            float(selection_config["crop_margin_fraction_of_width"]) * camera.width,
        )
        if crop is None:
            continue
        candidates.append(
            {
                "view_name": image.name,
                "image_id": int(image.id),
                "camera_id": int(image.camera_id),
                "crop_xyxy": list(map(int, crop)),
                "projection_coverage": coverage,
                "projected_area_px2": area,
                "projected_area_fraction": area / (camera.width * camera.height),
                "roof_vertex_coverage": roof_coverage,
                "selection_reason": "NEAR_NADIR_ROOF_GATE" if near_nadir_gate and not standard_gate else "CONTEXT_PRISM_GATE",
                "azimuth_deg": azimuth,
                "nadir_deg": nadir,
                "view_direction": direction,
                "camera_forward": camera_forward,
                "camera_center_canonical": center_canonical,
                "global_role": "eval" if image.name in global_eval else "train",
            }
        )
    if len(candidates) < int(selection_config["minimum_candidate_views"]):
        raise RuntimeError(f"only {len(candidates)} eligible views")
    protected, additions = augment_validation(candidates, selection_config)
    identity["selected_images"] = {
        row["view_name"]: sha256(colmap_root / "images" / row["view_name"])
        for row in candidates
    }
    if receipt_path.is_file():
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if receipt.get("schema") == SCHEMA and receipt.get("source_identity") == identity:
            print(json.dumps({"status": "reused", **receipt["summary"]}, ensure_ascii=False))
            return receipt
    if output_root.exists():
        raise RuntimeError(
            f"output exists but does not match current inputs; preserve it and use a new task id: {output_root}"
        )

    staging = output_root.with_name(output_root.name + f".staging.{os.getpid()}")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    staging_viewer = staging / "viewer"
    (staging_viewer / "images/original").mkdir(parents=True)
    (staging_viewer / "images/sparse").mkdir(parents=True)
    (staging_viewer / "images/mvs").mkdir(parents=True)

    sparse_all = read_points3d_bin(sparse_root / "points3D.bin")
    sparse = crop_seed(
        sparse_all,
        building["viewport_bbox_xy"],
        building["z_range_ellipsoidal_m"],
    )
    mvs_all = read_ply_xyz(inputs["mvs_seed"])
    mvs_xyz = crop_seed(
        mvs_all,
        building["viewport_bbox_xy"],
        building["z_range_ellipsoidal_m"],
    )
    if len(sparse) < 10 or len(mvs_xyz) < 10:
        raise RuntimeError("local seed crop is unexpectedly empty")

    rows = []
    maximum_width = int(config["display"]["maximum_crop_width_px"])
    high_z = float(building["z_range_ellipsoidal_m"][1])
    for index, candidate in enumerate(candidates, start=1):
        name = str(candidate["view_name"])
        role = (
            "GLOBAL_HELDOUT_PROTECTED"
            if name in protected
            else "LOCAL_VAL_ADDED"
            if name in additions
            else "LOCAL_TRAIN"
        )
        image = images[int(candidate["image_id"])]
        camera = cameras[int(candidate["camera_id"])]
        crop = candidate["crop_xyxy"]
        with Image.open(colmap_root / "images" / name) as source:
            base = source.convert("RGB").crop(tuple(crop))
        draw = ImageDraw.Draw(base)
        for ring in projected_footprint_rings(footprint, high_z, scene_reference, image, camera):
            shifted = [(float(x - crop[0]), float(y - crop[1])) for x, y in ring]
            draw.line(shifted, fill="#ffe000", width=4, joint="curve")
        sparse_overlay, sparse_projected, sparse_drawn = draw_seed_overlay(
            base,
            sparse,
            image,
            camera,
            crop,
            int(config["display"]["maximum_projected_sparse_points"]),
            "sparse",
        )
        mvs_overlay, mvs_projected, mvs_drawn = draw_seed_overlay(
            base,
            mvs_xyz,
            image,
            camera,
            crop,
            int(config["display"]["maximum_projected_mvs_points"]),
            "mvs",
        )
        stem = f"{index:02d}_{Path(name).stem}"
        paths = {}
        for kind, rendered in (("original", base), ("sparse", sparse_overlay), ("mvs", mvs_overlay)):
            destination = staging_viewer / "images" / kind / f"{stem}.jpg"
            fit_for_web(rendered, maximum_width).save(destination, quality=91, subsampling=0)
            paths[kind] = destination
        row = {
            "index": index,
            "view_name": name,
            "global_role": candidate["global_role"],
            "local_role": role,
            "crop_xyxy": crop,
            "projection_coverage": candidate["projection_coverage"],
            "projected_area_px2": candidate["projected_area_px2"],
            "projected_area_fraction": candidate["projected_area_fraction"],
            "roof_vertex_coverage": candidate["roof_vertex_coverage"],
            "selection_reason": candidate["selection_reason"],
            "azimuth_deg": candidate["azimuth_deg"],
            "nadir_deg": candidate["nadir_deg"],
            "sparse_projected_count": sparse_projected,
            "sparse_drawn_count": sparse_drawn,
            "mvs_projected_count": mvs_projected,
            "mvs_drawn_count": mvs_drawn,
            "original": paths["original"].relative_to(staging_viewer).as_posix(),
            "sparse": paths["sparse"].relative_to(staging_viewer).as_posix(),
            "mvs": paths["mvs"].relative_to(staging_viewer).as_posix(),
            "camera_center": (candidate["camera_center_canonical"] - center).tolist(),
            "camera_forward": candidate["camera_forward"].tolist(),
        }
        rows.append(row)

    csv_path = staging / "view_candidates.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        fields = [key for key in rows[0] if key not in {"camera_center", "original", "sparse", "mvs"}]
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows({key: row[key] for key in fields} for row in rows)

    sheets_root = staging_viewer / "contact_sheets"
    sheets_root.mkdir()
    per_page = int(config["display"]["contact_sheet_rows_per_page"])
    sheet_paths = []
    for page_index, start in enumerate(range(0, len(rows), per_page), start=1):
        page_rows = []
        for row in rows[start : start + per_page]:
            page_rows.append(
                {
                    **row,
                    "original_path": staging_viewer / row["original"],
                    "sparse_path": staging_viewer / row["sparse"],
                    "mvs_path": staging_viewer / row["mvs"],
                }
            )
        path = sheets_root / f"page_{page_index:02d}.jpg"
        contact_sheet(page_rows, path)
        sheet_paths.append(path)

    seed_assets = write_seed_assets(staging_viewer, sparse, mvs_xyz, center)
    footprint_rings = []
    for z_value in building["z_range_ellipsoidal_m"]:
        for ring in polygon_rings(footprint):
            base = np.column_stack((ring[:, :2], np.full(len(ring), float(z_value))))
            canonical = base_to_canonical(base, scene_reference, input_datum="ellipsoidal")
            footprint_rings.append((canonical - center).tolist())
    viewer_manifest = {
        "schema": "jointbuildgs.p2.e3_local_review.viewer.v1",
        "building_id": config["building_id"],
        "candidate_count": len(rows),
        "local_train_count": sum(row["local_role"] == "LOCAL_TRAIN" for row in rows),
        "global_heldout_count": len(protected),
        "added_local_validation_count": len(additions),
        "local_validation_count": len(protected | additions),
        "seed": seed_assets,
        "footprint_rings": footprint_rings,
        "views": rows,
        "contact_sheets": [path.relative_to(staging_viewer).as_posix() for path in sheet_paths],
        "mvs_seed_role": "DISPLAY_ONLY_COMPARISON_NOT_USED_BY_PROPOSED_S0",
        "training_started": False,
        "scientific_verdict": None,
    }
    atomic_json(staging_viewer / "viewer_manifest.json", viewer_manifest)
    app_root = repo_root / "src/apps/e3_local_seed_review"
    for name in ("index.html", "app.js"):
        shutil.copy2(app_root / name, staging_viewer / name)
    shutil.copy2(
        repo_root / "src/apps/gs3d_4way_viewer/build/three.module.min.js",
        staging_viewer / "three.module.min.js",
    )

    final_rows = []
    for row in rows:
        final_rows.append(
            {
                **row,
                "original_path": staging_viewer / row["original"],
                "sparse_path": staging_viewer / row["sparse"],
                "mvs_path": staging_viewer / row["mvs"],
            }
        )
    publish_tensorboard(
        inputs["tensorboard_publish_root"],
        sheet_paths,
        [row for row in final_rows if row["local_role"] != "LOCAL_TRAIN"],
    )

    summary = {
        "building_id": config["building_id"],
        "candidate_count": len(rows),
        "global_heldout_protected": len(protected),
        "local_validation_added": len(additions),
        "local_validation_total": len(protected | additions),
        "local_train_count": sum(row["local_role"] == "LOCAL_TRAIN" for row in rows),
        "sparse_seed_count": int(len(sparse)),
        "mvs_seed_comparison_count": int(len(mvs_xyz)),
        "contact_sheet_count": len(sheet_paths),
        "training_started": False,
    }
    receipt = {
        "schema": SCHEMA,
        "task_id": config["task_id"],
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source_identity": identity,
        "summary": summary,
        "viewer_relative_path": "viewer/index.html",
        "tensorboard_publish_root": str(inputs["tensorboard_publish_root"]),
        "existing_e1_e6_viewer_modified": False,
        "scientific_verdict": None,
    }
    atomic_json(staging / "receipt.json", receipt)
    (staging / "NOTES.md").write_text(
        "# E3 local input review notes\n\n"
        "- Target: `DEBY_LOD2_4906982`.\n"
        "- Existing global held-out views are protected; deterministic azimuth/nadir-stratified views only fill the local validation shortfall.\n"
        "- Sparse SfM is the proposed S0 seed. ROI MVS seed is display-only in this review.\n"
        "- No training, checkpoint selection, extraction, or scientific verdict occurred.\n",
        encoding="utf-8",
    )
    os.replace(staging, output_root)
    print(json.dumps({"status": "built", **summary}, ensure_ascii=False))
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    args = parser.parse_args()
    build(args.config.resolve(), args.repo_root.resolve(), args.artifact_root.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
