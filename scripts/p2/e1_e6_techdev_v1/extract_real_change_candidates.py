from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import laspy
import matplotlib.pyplot as plt
import numpy as np
from scipy.ndimage import binary_closing, binary_dilation, binary_opening
from shapely import contains_xy
from shapely.geometry import box, mapping, shape
from shapely.ops import unary_union


AOI = np.asarray([690791.74, 5335864.05, 691154.65, 5336353.85], dtype=np.float64)
RESOLUTION_M = 0.5
ALS_Z_SHIFT_M = 45.7
MIN_HEIGHT_THRESHOLD_M = 1.0
CELL_AREA_M2 = RESOLUTION_M**2
SCHEMA = "jointbuildgs.p2.e1_e6.real_change_candidates.v5"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def raster_shape() -> tuple[int, int]:
    width = int(math.ceil((AOI[2] - AOI[0]) / RESOLUTION_M))
    height = int(math.ceil((AOI[3] - AOI[1]) / RESOLUTION_M))
    return height, width


def update_maximum(target: np.ndarray, x: np.ndarray, y: np.ndarray, z: np.ndarray) -> None:
    column = np.floor((x - AOI[0]) / RESOLUTION_M).astype(np.int32)
    row = np.floor((y - AOI[1]) / RESOLUTION_M).astype(np.int32)
    inside = (
        (column >= 0) & (column < target.shape[1])
        & (row >= 0) & (row < target.shape[0])
        & np.isfinite(z)
    )
    if np.any(inside):
        np.maximum.at(target, (row[inside], column[inside]), z[inside].astype(np.float32))


def rasterize_classes(paths: list[Path], z_shift_m: float) -> tuple[np.ndarray, np.ndarray, list[dict]]:
    building = np.full(raster_shape(), -np.inf, dtype=np.float32)
    ground = np.full(raster_shape(), -np.inf, dtype=np.float32)
    source_receipts = []
    for path in paths:
        class_counts = {"2": 0, "6": 0}
        point_count = 0
        with laspy.open(path) as reader:
            for chunk in reader.chunk_iterator(2_000_000):
                point_count += len(chunk)
                classification = np.asarray(chunk.classification)
                for class_id, target in ((2, ground), (6, building)):
                    selected = classification == class_id
                    class_counts[str(class_id)] += int(np.count_nonzero(selected))
                    if np.any(selected):
                        update_maximum(
                            target,
                            np.asarray(chunk.x)[selected],
                            np.asarray(chunk.y)[selected],
                            np.asarray(chunk.z)[selected] + z_shift_m,
                        )
        source_receipts.append({
            "path": str(path),
            "sha256": sha256(path),
            "point_count": point_count,
            "class_counts": class_counts,
            "z_shift_m": z_shift_m,
        })
    return building, ground, source_receipts


def candidate_kind(positive_area: float, negative_area: float) -> tuple[str, str, str]:
    if positive_area >= 1.5 * max(negative_area, CELL_AREA_M2):
        return "CURRENT_GAIN_OR_RAISE", "현재 증가/신축 후보", "#fb7185"
    if negative_area >= 1.5 * max(positive_area, CELL_AREA_M2):
        return "CURRENT_LOSS_OR_LOWER", "현재 감소/철거 후보", "#22d3ee"
    return "ROOF_FORM_OR_MIXED_CHANGE", "지붕 형상/혼합 변화 후보", "#a78bfa"


def cell_mask_geometry(mask: np.ndarray, footprint) -> object:
    """Polygonize true raster cells as deterministic horizontal runs."""
    rectangles = []
    for row in np.flatnonzero(np.any(mask, axis=1)):
        columns = np.flatnonzero(mask[row])
        if not len(columns):
            continue
        splits = np.flatnonzero(np.diff(columns) > 1) + 1
        for run in np.split(columns, splits):
            x0 = AOI[0] + int(run[0]) * RESOLUTION_M
            x1 = AOI[0] + (int(run[-1]) + 1) * RESOLUTION_M
            y0 = AOI[1] + int(row) * RESOLUTION_M
            y1 = y0 + RESOLUTION_M
            rectangles.append(box(x0, y0, x1, y1))
    if not rectangles:
        return footprint.intersection(box(0, 0, 0, 0))
    return unary_union(rectangles).intersection(footprint)


def overview(
    path: Path,
    delta: np.ndarray,
    candidates: list[dict],
    candidate_geometries: dict[str, object],
    threshold_m: float,
) -> None:
    masked = np.ma.masked_invalid(np.where(np.isfinite(delta), delta, np.nan))
    figure, axis = plt.subplots(figsize=(11, 13), constrained_layout=True)
    image = axis.imshow(
        masked,
        origin="lower",
        extent=[AOI[0], AOI[2], AOI[1], AOI[3]],
        cmap="coolwarm",
        vmin=-2 * threshold_m,
        vmax=2 * threshold_m,
        interpolation="nearest",
    )
    for item in candidates:
        geometry = candidate_geometries[item["stable_id"]]
        polygons = [geometry] if geometry.geom_type == "Polygon" else list(geometry.geoms)
        for polygon in polygons:
            x, y = polygon.exterior.xy
            axis.plot(x, y, color=item["color"], linewidth=1.8)
        centre = geometry.representative_point()
        axis.text(centre.x, centre.y, item["stable_id"].replace("DEBY_LOD2_", ""), fontsize=5)
    axis.set_title("2024 current ULS - 2022 existing ALS | class-6 DSM | automatic candidates")
    axis.set_aspect("equal")
    axis.set_xlabel("EPSG:25832 Easting")
    axis.set_ylabel("EPSG:25832 Northing")
    figure.colorbar(image, ax=axis, label="ground-aligned height difference (m)")
    figure.savefig(path, dpi=180)
    plt.close(figure)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--task-root", type=Path, required=True)
    args = parser.parse_args()
    artifacts = args.artifact_root.resolve()
    task = args.task_root.resolve()
    output_root = task / "prep/real_change_candidates"
    receipt_path = output_root / "receipt.json"
    candidates_path = output_root / "candidates.geojson"
    overview_path = output_root / "overview.png"
    if receipt_path.is_file() and candidates_path.is_file() and overview_path.is_file():
        prior_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if prior_receipt.get("schema") == SCHEMA:
            return 0
    output_root.mkdir(parents=True, exist_ok=True)

    baseline = artifacts / (
        "phase-payloads/p2/c1_c2_shared_footprint_199_v3/"
        "P2-C1-C2-SHARED-FOOTPRINT-199-ORIGINAL-GLOBAL-v3-replay-20260806a"
    )
    current_path = baseline / "work/C1_L_upper/classified_scene.laz"
    prior_paths = [
        artifacts / f"phase-payloads/p0-audit/data/raw/als/{tile}.laz"
        for tile in ("690_5335", "690_5336", "691_5335", "691_5336")
    ]
    footprint_path = baseline / "freeze/shared_footprints_199.geojson"
    for source in (current_path, footprint_path, *prior_paths):
        if not source.is_file():
            raise FileNotFoundError(source)

    print("[real change] rasterizing current E1 ULS", flush=True)
    current_building, current_ground, current_sources = rasterize_classes([current_path], 0.0)
    print("[real change] rasterizing existing ALS", flush=True)
    prior_building, prior_ground, prior_sources = rasterize_classes(prior_paths, ALS_Z_SHIFT_M)

    footprint_data = json.loads(footprint_path.read_text(encoding="utf-8"))
    geometries = {
        str(feature["properties"]["stable_id"]): shape(feature["geometry"])
        for feature in footprint_data["features"]
    }
    footprint_union = unary_union(list(geometries.values()))
    height, width = raster_shape()
    x = AOI[0] + (np.arange(width) + 0.5) * RESOLUTION_M
    y = AOI[1] + (np.arange(height) + 0.5) * RESOLUTION_M
    grid_x, grid_y = np.meshgrid(x, y)
    outside_footprints = ~contains_xy(footprint_union, grid_x, grid_y)
    ground_overlap = np.isfinite(current_ground) & np.isfinite(prior_ground) & outside_footprints
    ground_delta = current_ground[ground_overlap] - prior_ground[ground_overlap]
    if len(ground_delta) < 100:
        raise RuntimeError("insufficient overlapping ground cells for temporal alignment")
    residual_median = float(np.median(ground_delta))
    residual_mad = float(np.median(np.abs(ground_delta - residual_median)))
    sigma0 = 1.4826 * residual_mad
    threshold_m = max(MIN_HEIGHT_THRESHOLD_M, 3.0 * sigma0)
    aligned_prior_building = prior_building + residual_median
    current_valid = np.isfinite(current_building)
    prior_valid = np.isfinite(aligned_prior_building)
    overlap = current_valid & prior_valid
    delta = np.full_like(current_building, np.nan)
    delta[overlap] = current_building[overlap] - aligned_prior_building[overlap]

    current_support = binary_closing(current_valid, iterations=1)
    prior_support = binary_closing(prior_valid, iterations=1)
    current_ground_support = binary_closing(np.isfinite(current_ground), iterations=1)
    prior_ground_support = binary_closing(np.isfinite(prior_ground), iterations=1)
    # A missing building return is temporal evidence only if the other epoch
    # observes ground at that location. Otherwise it remains missing coverage.
    current_only = (
        current_support
        & ~binary_dilation(prior_support, iterations=1)
        & binary_dilation(prior_ground_support, iterations=1)
    )
    prior_only = (
        prior_support
        & ~binary_dilation(current_support, iterations=1)
        & binary_dilation(current_ground_support, iterations=1)
    )
    positive = binary_opening((overlap & (delta > threshold_m)) | current_only, iterations=1)
    negative = binary_opening((overlap & (delta < -threshold_m)) | prior_only, iterations=1)

    candidates = []
    features = []
    all_buildings = []
    candidate_geometries = {}
    for stable_id, geometry in geometries.items():
        inside = contains_xy(geometry, grid_x, grid_y)
        footprint_cells = int(np.count_nonzero(inside))
        if footprint_cells == 0:
            continue
        positive_area = float(np.count_nonzero(inside & positive) * CELL_AREA_M2)
        negative_area = float(np.count_nonzero(inside & negative) * CELL_AREA_M2)
        changed_area = positive_area + negative_area
        footprint_area = float(footprint_cells * CELL_AREA_M2)
        changed_fraction = changed_area / footprint_area
        current_coverage = float(np.count_nonzero(inside & current_valid) / footprint_cells)
        prior_coverage = float(np.count_nonzero(inside & prior_valid) / footprint_cells)
        overlap_values = delta[inside & overlap]
        median_delta = float(np.median(overlap_values)) if len(overlap_values) else None
        minimum_area = max(4.0, min(15.0, 0.20 * footprint_area))
        is_candidate = changed_area >= minimum_area and changed_fraction >= 0.20
        record = {
            "stable_id": stable_id,
            "footprint_area_m2": footprint_area,
            "current_building_coverage": current_coverage,
            "prior_building_coverage": prior_coverage,
            "positive_change_area_m2": positive_area,
            "negative_change_area_m2": negative_area,
            "changed_area_m2": changed_area,
            "changed_fraction": changed_fraction,
            "median_overlap_height_delta_m": median_delta,
            "candidate": is_candidate,
        }
        if is_candidate:
            kind, label, color = candidate_kind(positive_area, negative_area)
            # This score describes automatic signal strength, not verification.
            # Reserve "verified" for independent or human temporal confirmation.
            confidence = "STRONG_SIGNAL" if changed_fraction >= 0.45 and changed_area >= 20.0 else "REVIEW"
            change_geometry = cell_mask_geometry(inside & (positive | negative), geometry)
            if change_geometry.is_empty:
                raise RuntimeError(f"candidate polygonization unexpectedly empty: {stable_id}")
            record.update({
                "kind": kind,
                "label_ko": label,
                "color": color,
                "confidence": confidence,
                "change_polygon_area_m2": float(change_geometry.area),
            })
            candidates.append(record)
            candidate_geometries[stable_id] = change_geometry
            features.append({
                "type": "Feature",
                "geometry": mapping(change_geometry),
                "properties": record,
            })
        all_buildings.append(record)

    candidates.sort(key=lambda item: item["changed_area_m2"], reverse=True)
    features.sort(key=lambda item: item["properties"]["changed_area_m2"], reverse=True)
    collection = {
        "type": "FeatureCollection",
        "name": "REAL_TEMPORAL_CHANGE_CANDIDATES_E1_ULS_2024_VS_EXISTING_ALS_2022",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::25832"}},
        "features": features,
    }
    atomic_json(candidates_path, collection)
    overview(overview_path, delta, candidates, candidate_geometries, threshold_m)
    receipt = {
        "schema": SCHEMA,
        "role": "AUTOMATIC_CROSS_EPOCH_SENSOR_DIFFERENCE_CANDIDATES_NOT_VERIFIED_CHANGE_GT",
        "epochs": {"current": "2024-12-17", "prior": "2022-era"},
        "method": "GROUND_ALIGNED_CLASS6_DSM_DIFFERENCE_WITH_GROUND_CONFIRMED_SUPPORT_CHANGE",
        "crs": "EPSG:25832",
        "aoi": AOI.tolist(),
        "resolution_m": RESOLUTION_M,
        "als_vertical_shift_m": ALS_Z_SHIFT_M,
        "ground_overlap_cell_count": int(np.count_nonzero(ground_overlap)),
        "ground_residual_median_m": residual_median,
        "ground_sigma0_m": sigma0,
        "height_change_threshold_m": threshold_m,
        "candidate_rule": "changed_area >= max(4m2,min(15m2,20% footprint area)) AND changed_fraction >= 0.20",
        "candidate_count": len(candidates),
        "strong_signal_count": sum(item["confidence"] == "STRONG_SIGNAL" for item in candidates),
        "candidates": candidates,
        "all_buildings": all_buildings,
        "sources": {"current": current_sources, "prior": prior_sources, "footprints": str(footprint_path)},
        "outputs": {"geojson": str(candidates_path), "overview": str(overview_path)},
        "limitations": [
            "candidate geometry is a 0.5 m automatic change-cell polygon clipped by the shared building footprint, not a manually verified polygon",
            "class-6 support limits detection to the shared 199-building footprint population",
            "building support disappearance/appearance is accepted only where the other epoch observes ground",
            "roof sampling, occlusion, classification, and residual registration can create false candidates",
            "visual review found that most candidates do not show an unambiguous building-form change",
            "automatic candidates require visual or independent-source verification before GT promotion",
        ],
        "verified_real_change_count": 0,
        "scientific_verdict": None,
    }
    atomic_json(receipt_path, receipt)
    print(
        f"[real change] candidates={len(candidates)} "
        f"strong_signal={receipt['strong_signal_count']} verified=0",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
