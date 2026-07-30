#!/usr/bin/env python3
"""Phase-0 mono-normal diagnostic from pinned full-frame cache and cached DLT points.

This is a learning-zero, inference-zero measurement.  It verifies the cached
Omnidata executable state and every selected normal map before projecting the
locked footprint-inside DLT point pools through the fixed COLMAP cameras.
LoD2 and ALS are not loaded by this script.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import subprocess
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp")

import matplotlib
import numpy as np
from PIL import Image, ImageDraw
from shapely import contains_xy, make_valid
from shapely.geometry import GeometryCollection, MultiPolygon, Polygon, box, shape
from shapely.ops import unary_union
from sklearn.linear_model import LinearRegression, RANSACRegressor

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in os.sys.path:
    os.sys.path.insert(0, str(REPO))

from src.stage2.colmap_io import read_cameras_bin, read_images_bin  # noqa: E402

RUN_ID = "20260715_e5_c001_s3ap_phase0_mononormal"
RUN_DIR = REPO / "phases/p2-gsjso/runs" / RUN_ID
CONFIG_PATH = REPO / "phases/p2-gsjso/configs/e5_c001_s3ap_phase0_mononormal.json"
SCRIPT_PATH = Path(__file__).resolve()
OUT_CSV = REPO / "docs/experiments/input-and-alignment/e5_c001_s3ap/tables/mononormal_diag.csv"
FIG_DIR = REPO / "docs/figs/e5_c001_s3ap_phase0"
MANIFEST_PATH = RUN_DIR / "manifest.json"
PROGRESS_PATH = RUN_DIR / "progress.json"
RUN_LOG = RUN_DIR / "run.log"
INVENTORY_PATH = RUN_DIR / "normal_cache_inventory.csv"
SAMPLES_PATH = RUN_DIR / "angle_samples.npz"

FIELDS = [
    "row_type",
    "building_id",
    "view_stem",
    "image_name",
    "model_name",
    "model_revision",
    "model_code_tree_sha256",
    "weights_sha256",
    "normal_frame",
    "normal_path",
    "normal_sha256",
    "normal_hash_match",
    "fm_plane_source",
    "fm_inside_point_count",
    "fm_plane_ax",
    "fm_plane_by",
    "fm_plane_c",
    "fm_plane_normal_x",
    "fm_plane_normal_y",
    "fm_plane_normal_z",
    "fm_plane_ransac_inlier_count",
    "fm_plane_ransac_inlier_ratio",
    "fm_plane_internal_rms_m",
    "visible_view_count",
    "projected_positive_depth_count",
    "projected_in_frame_count_raw",
    "sampled_unique_pixel_count",
    "finite_normal_count",
    "angle_median_deg_absdot",
    "angle_mad_deg_absdot",
    "angle_q25_deg_absdot",
    "angle_q75_deg_absdot",
    "angle_p90_deg_absdot",
    "within_22p5_count",
    "within_22p5_rate",
    "within_22p5_denominator",
    "cache_reprojection_crosscheck_max_px",
    "summary_aggregation",
    "status",
    "figure_path",
    "footprint_role",
    "pure_fm_fit",
    "originating_pair_endpoint_views_only",
    "gt_lod2_or_als_used",
    "gate_applied",
    "learning_runs_started",
    "new_mononormal_inference_runs",
    "new_mast3r_inference_runs",
    "note",
]

INVENTORY_FIELDS = [
    "view_stem",
    "buildings",
    "normal_path",
    "expected_sha256",
    "actual_sha256",
    "hash_match",
    "shape",
    "dtype",
    "finite_fraction",
    "unit_norm_median",
    "unit_norm_max_abs_error",
    "status",
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def rel(path: Path | str) -> str:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = REPO / candidate
    try:
        return str(candidate.resolve().relative_to(REPO.resolve()))
    except ValueError:
        return str(candidate.resolve())


def resolve(path: str) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else REPO / candidate


def sha256_file(path: Path, block_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_tree_sha256(root: Path, roots: Sequence[Path]) -> tuple[str, int]:
    files: list[Path] = []
    for candidate in roots:
        if candidate.is_file():
            files.append(candidate)
        elif candidate.is_dir():
            files.extend(
                path
                for path in candidate.rglob("*")
                if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
            )
    digest = hashlib.sha256()
    for path in sorted(files, key=lambda item: str(item.relative_to(root))):
        relative = str(path.relative_to(root)).replace("\\", "/")
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest(), len(files)


def fmt(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (bool, np.bool_)):
        return "true" if bool(value) else "false"
    if isinstance(value, (float, np.floating)):
        return "" if not math.isfinite(float(value)) else f"{float(value):.6f}"
    return str(value)


def atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    os.replace(temporary, path)


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    atomic_text(path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def atomic_csv(path: Path, rows: Sequence[dict[str, Any]], fields: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows({key: fmt(row.get(key)) for key in fields} for row in rows)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def save_opaque_png(figure: Any, output: Path, dpi: int) -> None:
    """Save a white-background RGB PNG atomically for renderer portability."""
    output.parent.mkdir(parents=True, exist_ok=True)
    render_path = output.with_name(f".{output.stem}.render.png")
    rgb_path = output.with_name(f".{output.stem}.rgb.png")
    figure.patch.set_facecolor("white")
    figure.patch.set_alpha(1.0)
    try:
        figure.savefig(
            render_path,
            dpi=dpi,
            facecolor="white",
            edgecolor="white",
            transparent=False,
            bbox_inches=None,
        )
        with Image.open(render_path) as rendered:
            rendered.convert("RGB").save(rgb_path, format="PNG", compress_level=6)
        os.replace(rgb_path, output)
    finally:
        render_path.unlink(missing_ok=True)
        rgb_path.unlink(missing_ok=True)


def log(message: str) -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    line = f"{now()} {message}"
    with RUN_LOG.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    print(line, flush=True)


def git_value(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO, text=True).strip()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def flatten_polygons(geometry: Any) -> list[Polygon]:
    if geometry is None or geometry.is_empty:
        return []
    if isinstance(geometry, Polygon):
        return [geometry]
    if isinstance(geometry, MultiPolygon):
        return list(geometry.geoms)
    if isinstance(geometry, GeometryCollection):
        out: list[Polygon] = []
        for part in geometry.geoms:
            out.extend(flatten_polygons(part))
        return out
    return []


def load_footprints(path: Path) -> tuple[dict[str, Any], str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    crs = str(payload.get("crs", {}).get("properties", {}).get("name", ""))
    if "25832" not in crs:
        raise RuntimeError(f"footprint CRS mismatch: {crs}")
    pieces: dict[str, list[Any]] = defaultdict(list)
    for feature in payload.get("features", []):
        properties = feature.get("properties") or {}
        identifier = str(properties.get("building_id", ""))
        if identifier and not identifier.startswith("DEBY_LOD2_"):
            identifier = f"DEBY_LOD2_{identifier}"
        geometry = make_valid(shape(feature["geometry"]))
        if identifier and not geometry.is_empty:
            pieces[identifier].append(geometry)
    return {key: make_valid(unary_union(value)) for key, value in pieces.items()}, crs


def load_frames(sparse_dir: Path, image_dir: Path) -> dict[str, dict[str, Any]]:
    cameras = read_cameras_bin(sparse_dir / "cameras.bin")
    images = read_images_bin(sparse_dir / "images.bin")
    frames: dict[str, dict[str, Any]] = {}
    for item in images.values():
        image_path = image_dir / item.name
        if not image_path.exists():
            continue
        camera = cameras[item.camera_id]
        frames[Path(item.name).stem] = {
            "path": image_path,
            "name": item.name,
            "K": camera.K(),
            "R": item.R(),
            "t": np.asarray(item.tvec, dtype=np.float64),
            "width": int(camera.width),
            "height": int(camera.height),
        }
    return frames


def project(local_xyz: np.ndarray, frame: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    xyz = np.asarray(local_xyz, dtype=np.float64)
    camera = (frame["R"] @ xyz.T).T + frame["t"]
    homogeneous = (frame["K"] @ camera.T).T
    depth = camera[:, 2]
    pixels = np.full((len(xyz), 2), np.nan, dtype=np.float64)
    positive = depth > 1e-9
    pixels[positive] = homogeneous[positive, :2] / homogeneous[positive, 2:3]
    return pixels, depth


def fm_plane_normal(row: dict[str, Any]) -> np.ndarray:
    ax = float(row["plane_ax"])
    by = float(row["plane_by"])
    normal = np.asarray([-ax, -by, 1.0], dtype=np.float64)
    normal /= np.linalg.norm(normal)
    if normal[2] < 0:
        normal *= -1
    return normal


def fit_fm_plane(points: np.ndarray, config: dict[str, Any]) -> dict[str, Any]:
    """Fit z=ax+by+c using only finite footprint-inside DLT XYZ."""
    xyz = np.asarray(points, dtype=np.float64)
    finite = np.isfinite(xyz).all(axis=1)
    xyz = xyz[finite]
    if len(xyz) < 3 or len(np.unique(np.round(xyz[:, :2], 6), axis=0)) < 3:
        raise RuntimeError(f"insufficient XY support for GT-free FM plane: n={len(xyz)}")
    lock = config["measurement"]["fm_plane_ransac"]
    centre = np.mean(xyz[:, :2], axis=0)
    predictors = xyz[:, :2] - centre
    minimum = max(
        int(lock["min_samples_floor"]),
        int(math.ceil(float(lock["min_samples_fraction"]) * len(xyz))),
    )
    minimum = min(minimum, len(xyz))
    model = RANSACRegressor(
        estimator=LinearRegression(),
        min_samples=minimum,
        residual_threshold=float(lock["residual_threshold_m"]),
        max_trials=int(lock["max_trials"]),
        random_state=int(lock["random_seed"]),
    )
    model.fit(predictors, xyz[:, 2])
    predicted = np.asarray(model.predict(predictors), dtype=np.float64)
    inlier = np.abs(xyz[:, 2] - predicted) <= float(lock["residual_threshold_m"])
    estimator = model.estimator_
    ax, by = [float(value) for value in estimator.coef_]
    intercept = float(estimator.intercept_ - ax * centre[0] - by * centre[1])
    internal_rms = float(np.sqrt(np.mean((xyz[inlier, 2] - predicted[inlier]) ** 2))) if np.any(inlier) else None
    return {
        "plane_status": "fit",
        "plane_ax": ax,
        "plane_by": by,
        "plane_c": intercept,
        "ransac_inlier_count": int(np.count_nonzero(inlier)),
        "ransac_inlier_ratio": float(np.mean(inlier)),
        "plane_internal_rms_m": internal_rms,
    }


def angle_stats(angles: np.ndarray, threshold: float) -> dict[str, Any]:
    values = np.asarray(angles, dtype=np.float64)
    values = values[np.isfinite(values)]
    if not len(values):
        return {
            "finite_normal_count": 0,
            "angle_median_deg_absdot": None,
            "angle_mad_deg_absdot": None,
            "angle_q25_deg_absdot": None,
            "angle_q75_deg_absdot": None,
            "angle_p90_deg_absdot": None,
            "within_22p5_count": 0,
            "within_22p5_rate": None,
            "within_22p5_denominator": 0,
        }
    median = float(np.median(values))
    within = int(np.count_nonzero(values <= threshold))
    return {
        "finite_normal_count": int(len(values)),
        "angle_median_deg_absdot": median,
        "angle_mad_deg_absdot": float(np.median(np.abs(values - median))),
        "angle_q25_deg_absdot": float(np.percentile(values, 25)),
        "angle_q75_deg_absdot": float(np.percentile(values, 75)),
        "angle_p90_deg_absdot": float(np.percentile(values, 90)),
        "within_22p5_count": within,
        "within_22p5_rate": float(within / len(values)),
        "within_22p5_denominator": int(len(values)),
    }


def polygon_local_rings(geometry: Any, plane_row: dict[str, Any], offset: np.ndarray) -> list[list[np.ndarray]]:
    ax = float(plane_row["plane_ax"])
    by = float(plane_row["plane_by"])
    intercept = float(plane_row["plane_c"])
    out: list[list[np.ndarray]] = []
    for polygon in flatten_polygons(geometry):
        rings: list[np.ndarray] = []
        for coordinates in [np.asarray(polygon.exterior.coords), *[np.asarray(ring.coords) for ring in polygon.interiors]]:
            local_xy = coordinates[:, :2] - offset[:2]
            z = ax * local_xy[:, 0] + by * local_xy[:, 1] + intercept
            rings.append(np.column_stack([local_xy, z]))
        out.append(rings)
    return out


def projected_footprint(geometry: Any, plane_row: dict[str, Any], frame: dict[str, Any], offset: np.ndarray) -> list[list[np.ndarray]]:
    output: list[list[np.ndarray]] = []
    for polygon_rings in polygon_local_rings(geometry, plane_row, offset):
        projected: list[np.ndarray] = []
        valid = True
        for ring in polygon_rings:
            pixels, depth = project(ring, frame)
            if np.any(depth <= 0) or not np.isfinite(pixels).all():
                valid = False
                break
            projected.append(pixels)
        if valid and projected:
            output.append(projected)
    return output


def projected_geometry(rings: Sequence[Sequence[np.ndarray]]) -> Any:
    polygons: list[Any] = []
    for polygon_rings in rings:
        candidate = make_valid(Polygon(polygon_rings[0], polygon_rings[1:]))
        polygons.extend(flatten_polygons(candidate))
    return make_valid(unary_union(polygons)) if polygons else Polygon()


def crop_bounds(geometry: Any, pixels: np.ndarray, width: int, height: int) -> tuple[int, int, int, int]:
    frame_box = box(0, 0, width - 1, height - 1)
    visible = geometry.intersection(frame_box) if geometry is not None and not geometry.is_empty else Polygon()
    bounds: tuple[float, float, float, float] | None = None
    if not visible.is_empty:
        bounds = visible.bounds
    finite = np.asarray(pixels, dtype=np.float64)
    finite = finite[np.isfinite(finite).all(axis=1)] if len(finite) else finite
    if len(finite):
        sample_bounds = (float(finite[:, 0].min()), float(finite[:, 1].min()), float(finite[:, 0].max()), float(finite[:, 1].max()))
        if bounds is None:
            bounds = sample_bounds
        else:
            bounds = (
                min(bounds[0], sample_bounds[0]), min(bounds[1], sample_bounds[1]),
                max(bounds[2], sample_bounds[2]), max(bounds[3], sample_bounds[3]),
            )
    if bounds is None:
        return 0, 0, width, height
    minx, miny, maxx, maxy = bounds
    centre_x = min(max((minx + maxx) / 2.0, 0.0), float(width - 1))
    centre_y = min(max((miny + maxy) / 2.0, 0.0), float(height - 1))
    side = min(max(maxx - minx, maxy - miny, 180.0) * 1.55, max(width, height) * 0.72)
    x0 = max(0, int(math.floor(centre_x - side / 2)))
    y0 = max(0, int(math.floor(centre_y - side / 2)))
    x1 = min(width, int(math.ceil(centre_x + side / 2)))
    y1 = min(height, int(math.ceil(centre_y + side / 2)))
    if x1 - x0 < 160:
        x0, x1 = max(0, x0 - 80), min(width, x1 + 80)
    if y1 - y0 < 160:
        y0, y1 = max(0, y0 - 80), min(height, y1 + 80)
    return x0, y0, x1, y1


def make_normal_overlay(
    image: np.ndarray,
    normal: np.ndarray,
    rings: Sequence[Sequence[np.ndarray]],
    alpha: float,
) -> np.ndarray:
    height, width = image.shape[:2]
    mask_image = Image.new("L", (width, height), 0)
    drawer = ImageDraw.Draw(mask_image)
    for polygon_rings in rings:
        drawer.polygon([tuple(value) for value in polygon_rings[0]], fill=255)
        for hole in polygon_rings[1:]:
            drawer.polygon([tuple(value) for value in hole], fill=0)
    mask = np.asarray(mask_image, dtype=np.float32)[:, :, None] / 255.0
    normal_rgb = np.clip((normal + 1.0) * 127.5, 0, 255)
    mix = alpha * mask
    return np.clip(image.astype(np.float32) * (1.0 - mix) + normal_rgb * mix, 0, 255).astype(np.uint8)


def draw_projected_rings(ax: Any, rings: Sequence[Sequence[np.ndarray]], x0: int, y0: int, color: str) -> None:
    first = True
    for polygon_rings in rings:
        for ring in polygon_rings:
            ax.plot(
                ring[:, 0] - x0,
                ring[:, 1] - y0,
                color=color,
                linewidth=1.8,
                linestyle="-" if first else "--",
                label="FM-plane footprint" if first else None,
            )
            first = False


def overlay_figure(
    short: str,
    view_stems: Sequence[str],
    frames: dict[str, dict[str, Any]],
    normal_arrays: dict[str, np.ndarray],
    point_pixels: dict[str, np.ndarray],
    angle_by_view: dict[str, np.ndarray],
    footprint: Any,
    plane_row: dict[str, Any],
    offset: np.ndarray,
    config: dict[str, Any],
) -> Path:
    palette = config["visual"]["palette"]
    columns = 3
    rows = int(math.ceil(len(view_stems) / columns))
    figure, axes = plt.subplots(rows, columns, figsize=(4.1 * columns, 3.6 * rows + 0.45), squeeze=False)
    for axis, stem in zip(axes.ravel(), view_stems):
        frame = frames[stem]
        image = np.asarray(Image.open(frame["path"]).convert("RGB"))
        normal = normal_arrays[stem]
        rings = projected_footprint(footprint, plane_row, frame, offset)
        geometry = projected_geometry(rings)
        pixels = point_pixels[stem]
        overlay = make_normal_overlay(image, normal, rings, float(config["visual"]["overlay_alpha"]))
        x0, y0, x1, y1 = crop_bounds(geometry, pixels, image.shape[1], image.shape[0])
        axis.imshow(overlay[y0:y1, x0:x1])
        draw_projected_rings(axis, rings, x0, y0, palette["footprint"])
        if len(pixels):
            axis.scatter(
                pixels[:, 0] - x0,
                pixels[:, 1] - y0,
                s=15,
                facecolors=palette["fm_point_face"],
                edgecolors=palette["fm_point_edge"],
                linewidths=0.55,
                marker="o",
                label="unique FM projection pixel",
            )
        angles = angle_by_view[stem]
        median = float(np.median(angles)) if len(angles) else None
        median_text = "NA" if median is None else f"{median:.1f} deg"
        axis.set_title(f"{stem[-14:]}\nN={len(angles)}; median={median_text}", fontsize=9)
        axis.set_xlim(0, x1 - x0)
        axis.set_ylim(y1 - y0, 0)
        axis.axis("off")
    for axis in axes.ravel()[len(view_stems):]:
        axis.axis("off")
    figure.suptitle(f"{short} mono-normal at projected FM-point pixels", fontsize=13, y=0.985)
    figure.text(
        0.5,
        0.015,
        "RGB=(world normal XYZ+1)/2; gold=footprint extended at FM fitted plane; white/black circles=sample pixels",
        ha="center",
        fontsize=8,
        color="#333333",
    )
    figure.tight_layout(rect=(0.01, 0.055, 0.99, 0.91 if rows == 1 else 0.94))
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    output = FIG_DIR / f"mononormal_{short}_overlay.png"
    save_opaque_png(figure, output, dpi=170)
    plt.close(figure)
    return output


def distribution_figure(samples: dict[str, np.ndarray], config: dict[str, Any]) -> Path:
    targets = list(config["targets"])
    palette = config["visual"]["palette"]
    threshold = float(config["measurement"]["within_angle_deg"])
    start, stop = [float(value) for value in config["visual"]["histogram_range_deg"]]
    step = float(config["visual"]["histogram_bin_deg"])
    bins = np.arange(start, stop + step, step)
    figure, axes = plt.subplots(1, len(targets), figsize=(12.4, 3.8), sharex=True)
    for index, (axis, short) in enumerate(zip(np.atleast_1d(axes), targets)):
        values = np.asarray(samples[short], dtype=np.float64)
        weights = np.full(len(values), 100.0 / len(values)) if len(values) else None
        axis.hist(values, bins=bins, weights=weights, color=palette["histogram"], edgecolor="#23384D", linewidth=0.55)
        axis.axvline(threshold, color=palette["threshold"], linestyle="--", linewidth=1.4, label="22.5 deg")
        if len(values):
            median = float(np.median(values))
            rate = float(np.mean(values <= threshold))
            axis.axvline(median, color=palette["median"], linewidth=1.8, label="median")
            subtitle = f"N={len(values)} building-view pixels\nmedian={median:.1f} deg; <=22.5 deg={rate:.3f}"
        else:
            subtitle = "N=0 building-view pixels"
        axis.set_title(f"{short}\n{subtitle}", fontsize=9)
        axis.set_xlim(start, stop)
        axis.set_xlabel("absolute-dot angle (deg)")
        axis.grid(axis="y", color="#D9D9D9", linewidth=0.7)
        if index == 0:
            axis.set_ylabel("sample share (%)")
            axis.legend(loc="upper right", frameon=False, fontsize=8)
    figure.suptitle("Mono-normal vs FM fitted-plane angle distributions", fontsize=13)
    figure.tight_layout(rect=(0.01, 0.01, 0.99, 0.92))
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    output = FIG_DIR / "mononormal_angle_distribution.png"
    save_opaque_png(figure, output, dpi=180)
    plt.close(figure)
    return output


def verify_model_pin(config: dict[str, Any]) -> dict[str, Any]:
    model = config["model"]
    torch_home = REPO / "results/tum_transfer/e5_s1_full_factor/C001/torch_hub"
    code_root = torch_home / "hub/alexsax_omnidata_models_main"
    code_hash, code_files = stable_tree_sha256(code_root, [code_root / "hubconf.py", code_root / "omnidata_models"])
    if code_hash != model["cached_code_tree_sha256"]:
        raise RuntimeError(f"Omnidata code tree hash mismatch: {code_hash}")
    weights_path = resolve(model["weights_path"])
    if weights_path.stat().st_size != int(model["weights_bytes"]):
        raise RuntimeError("Omnidata weights byte count mismatch")
    weights_hash = sha256_file(weights_path)
    if weights_hash != model["weights_sha256"]:
        raise RuntimeError(f"Omnidata weights hash mismatch: {weights_hash}")
    backbone_path = resolve(model["backbone_weights_path"])
    if backbone_path.stat().st_size != int(model["backbone_weights_bytes"]):
        raise RuntimeError("Omnidata backbone weights byte count mismatch")
    backbone_hash = sha256_file(backbone_path)
    if backbone_hash != model["backbone_weights_sha256"]:
        raise RuntimeError(f"Omnidata backbone hash mismatch: {backbone_hash}")
    timm_root = resolve(model["timm_path"])
    timm_hash, timm_files = stable_tree_sha256(timm_root, [timm_root / "timm", timm_root / "timm-0.4.12.dist-info"])
    if timm_hash != model["timm_tree_sha256"]:
        raise RuntimeError(f"timm tree hash mismatch: {timm_hash}")
    generator_log = resolve(model["generator_run_log"])
    generator_text = generator_log.read_text(encoding="utf-8", errors="replace")
    if '"done": 400, "total": 428' not in generator_text or '"rows": 428' not in generator_text:
        raise RuntimeError("source inference log does not attest the complete 428-view cache")
    runtime_rows = read_csv(resolve(model["generator_runtime_csv"]))
    normal_runtime = next((row for row in runtime_rows if row.get("component") == "mono_normal"), None)
    if normal_runtime is None or normal_runtime.get("torch") != model["torch_version_at_cache_generation"]:
        raise RuntimeError("source mono-normal runtime pin mismatch")
    subprocess.run(
        ["git", "cat-file", "-e", f"{model['generator_artifact_commit']}^{{commit}}"],
        cwd=REPO,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return {
        "code_tree_sha256": code_hash,
        "code_tree_file_count": code_files,
        "weights_sha256": weights_hash,
        "weights_bytes": weights_path.stat().st_size,
        "backbone_weights_sha256": backbone_hash,
        "backbone_weights_bytes": backbone_path.stat().st_size,
        "timm_tree_sha256": timm_hash,
        "timm_tree_file_count": timm_files,
        "revision": model["revision"],
        "revision_evidence": model["revision_recovery_rule"],
        "cache_generation_rows": 428,
        "cache_generation_runtime": normal_runtime,
    }


def gpu_status() -> dict[str, Any]:
    command = [
        "nvidia-smi",
        "--query-gpu=index,uuid,name,memory.used,memory.total,utilization.gpu",
        "--format=csv,noheader,nounits",
    ]
    process = subprocess.run(command, text=True, capture_output=True, check=False)
    return {
        "command": " ".join(command),
        "returncode": process.returncode,
        "output": process.stdout.strip(),
        "stderr": process.stderr.strip(),
        "gpu_compute_used": False,
    }


def source_hashes(config: dict[str, Any]) -> dict[str, str]:
    inputs = config["inputs"]
    paths = [
        CONFIG_PATH,
        SCRIPT_PATH,
        resolve(inputs["normal_hash_manifest"]),
        resolve(inputs["visible_view_manifest"]),
        resolve(inputs["fm_rescore_csv"]),
        resolve(inputs["fm_rescore_manifest"]),
        resolve(inputs["footprints"]),
        resolve(inputs["train_manifest"]),
        resolve(inputs["sparse_dir"]) / "cameras.bin",
        resolve(inputs["sparse_dir"]) / "images.bin",
        resolve(config["model"]["generator_run_log"]),
        resolve(config["model"]["generator_runtime_csv"]),
        resolve(config["model"]["weights_path"]),
        resolve(config["model"]["backbone_weights_path"]),
    ]
    return {rel(path): sha256_file(path) for path in paths}


def run(config: dict[str, Any]) -> dict[str, Any]:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    if RUN_LOG.exists():
        RUN_LOG.unlink()
    log("start phase0 mono-normal cache diagnostic; learning=0 new_inference=0")
    gpu = gpu_status()
    log(f"gpu preflight returncode={gpu['returncode']} output={gpu['output']!r}; compute_used=false")
    pin = verify_model_pin(config)
    log(
        "model pin verified "
        f"revision={pin['revision']} code={pin['code_tree_sha256']} weights={pin['weights_sha256']}"
    )

    inputs = config["inputs"]
    old_manifest_path = resolve(inputs["cached_dlt_manifest"])
    old_manifest = json.loads(old_manifest_path.read_text(encoding="utf-8"))
    normal_manifest = json.loads(resolve(inputs["normal_hash_manifest"]).read_text(encoding="utf-8"))
    rescore_manifest = json.loads(resolve(inputs["fm_rescore_manifest"]).read_text(encoding="utf-8"))
    rescore_path = resolve(inputs["fm_rescore_csv"])
    expected_rescore_hash = rescore_manifest["output_sha256"].get(rel(rescore_path))
    actual_rescore_hash = sha256_file(rescore_path)
    if expected_rescore_hash != actual_rescore_hash:
        raise RuntimeError("FM rescore CSV hash mismatch against its manifest")
    rescore_rows = read_csv(rescore_path)
    pair_rows = [row for row in rescore_rows if row.get("row_type") == "view_pair"]
    visible_views = old_manifest["locked_visible_views"]

    train_manifest = json.loads(resolve(inputs["train_manifest"]).read_text(encoding="utf-8"))
    offset = np.asarray(train_manifest["world_offset"], dtype=np.float64)
    footprints, footprint_crs = load_footprints(resolve(inputs["footprints"]))
    frames = load_frames(resolve(inputs["sparse_dir"]), resolve(inputs["image_dir"]))
    targets = [str(value) for value in config["targets"]]

    normal_dir = resolve(inputs["normal_cache_dir"])
    normal_files = sorted(normal_dir.glob("*.npy"))
    if len(normal_files) != 428:
        raise RuntimeError(f"normal cache file count mismatch: {len(normal_files)} != 428")
    expected_normal_hashes = normal_manifest["t0_3"]["selected_normal_hashes"]
    view_to_buildings: dict[str, set[str]] = defaultdict(set)
    for short in targets:
        for view in visible_views[short]:
            view_to_buildings[str(view["stem"])].add(short)

    inventory: list[dict[str, Any]] = []
    normal_arrays: dict[str, np.ndarray] = {}
    for index, stem in enumerate(sorted(view_to_buildings), start=1):
        path = normal_dir / f"{stem}.npy"
        relative = rel(path)
        expected = expected_normal_hashes.get(relative)
        if expected is None:
            raise RuntimeError(f"no locked source hash for normal cache: {relative}")
        actual = sha256_file(path)
        if actual != expected:
            raise RuntimeError(f"normal cache hash mismatch: {relative}")
        array = np.load(path, allow_pickle=False)
        if array.ndim != 3 or array.shape[2] != 3 or array.dtype != np.float32:
            raise RuntimeError(f"normal cache shape/dtype mismatch: {relative} {array.shape} {array.dtype}")
        finite = np.isfinite(array).all(axis=2)
        norms = np.linalg.norm(array[finite], axis=1) if np.any(finite) else np.asarray([], dtype=np.float32)
        if not np.all(finite) or not len(norms) or float(np.max(np.abs(norms - 1.0))) > 1e-4:
            raise RuntimeError(f"normal cache finite/unit check failed: {relative}")
        for short in view_to_buildings[stem]:
            frame = frames.get(stem)
            if frame is None:
                raise RuntimeError(f"missing COLMAP frame: {stem}")
            if array.shape[:2] != (frame["height"], frame["width"]):
                raise RuntimeError(f"normal/frame dimension mismatch: {stem}")
        normal_arrays[stem] = array
        inventory.append(
            {
                "view_stem": stem,
                "buildings": ";".join(sorted(view_to_buildings[stem])),
                "normal_path": relative,
                "expected_sha256": expected,
                "actual_sha256": actual,
                "hash_match": True,
                "shape": "x".join(str(value) for value in array.shape),
                "dtype": str(array.dtype),
                "finite_fraction": float(np.mean(finite)),
                "unit_norm_median": float(np.median(norms)),
                "unit_norm_max_abs_error": float(np.max(np.abs(norms - 1.0))),
                "status": "verified",
            }
        )
        atomic_csv(INVENTORY_PATH, inventory, INVENTORY_FIELDS)
        atomic_json(PROGRESS_PATH, {"stage": "normal_cache_verify", "done": index, "total": len(view_to_buildings), "updated_utc": now()})
    log(f"normal cache verified selected_unique={len(inventory)} total_cache={len(normal_files)}")

    rows: list[dict[str, Any]] = [
        {
            "row_type": "model",
            "building_id": "ALL",
            "model_name": config["model"]["name"],
            "model_revision": config["model"]["revision"],
            "model_code_tree_sha256": pin["code_tree_sha256"],
            "weights_sha256": pin["weights_sha256"],
            "normal_frame": config["model"]["normal_frame"],
            "visible_view_count": sum(len(visible_views[short]) for short in targets),
            "status": "verified_cache_reuse",
            "footprint_role": config["measurement"]["footprint_role"],
            "pure_fm_fit": True,
            "originating_pair_endpoint_views_only": True,
            "gt_lod2_or_als_used": False,
            "gate_applied": False,
            "learning_runs_started": 0,
            "new_mononormal_inference_runs": 0,
            "new_mast3r_inference_runs": 0,
            "note": "428-view cache complete; 8 unique locked-view files hash-verified; no inference in this run",
        }
    ]
    atomic_csv(OUT_CSV, rows, FIELDS)

    old_pair_hashes = old_manifest["output_sha256"]
    all_angles: dict[str, np.ndarray] = {}
    samples_for_npz: dict[str, np.ndarray] = {}
    output_figures: list[Path] = []
    cache_mismatch_total = 0
    reprojection_max_all = 0.0
    per_building_manifest: dict[str, Any] = {}

    for building_index, short in enumerate(targets, start=1):
        bid = f"DEBY_LOD2_{short}"
        footprint = footprints.get(bid)
        if footprint is None:
            raise RuntimeError(f"missing footprint for {short}")
        pooled: list[np.ndarray] = []
        endpoint_points: dict[str, list[np.ndarray]] = defaultdict(list)
        endpoint_pixels: dict[str, list[np.ndarray]] = defaultdict(list)
        eligible_rows = [
            row for row in pair_rows
            if row.get("building_id") == bid and truthy(row.get("eligible_summary_pair"))
        ]
        building_reprojection_max = 0.0
        for pair_row in eligible_rows:
            cache_path = resolve(pair_row["cache_path"])
            expected_cache_hash = old_pair_hashes.get(rel(cache_path))
            if expected_cache_hash != sha256_file(cache_path):
                raise RuntimeError(f"cached DLT hash mismatch: {rel(cache_path)}")
            with np.load(cache_path, allow_pickle=False) as archive:
                world = np.asarray(archive["world_local_xyz"], dtype=np.float64)
                cached_inside = np.asarray(archive["inside_footprint_score_mask"], dtype=bool)
                pixels_a = np.asarray(archive["pixels_a"], dtype=np.float64)
                pixels_b = np.asarray(archive["pixels_b"], dtype=np.float64)
            current_inside = contains_xy(footprint, world[:, 0] + offset[0], world[:, 1] + offset[1]) if len(world) else np.zeros(0, dtype=bool)
            mismatch = int(np.count_nonzero(current_inside != cached_inside))
            cache_mismatch_total += mismatch
            if mismatch:
                raise RuntimeError(f"footprint-inside cache mismatch: {rel(cache_path)} count={mismatch}")
            inside_world = world[current_inside]
            pooled.append(inside_world)
            for stem, cached_pixels in [(pair_row["view_a"], pixels_a), (pair_row["view_b"], pixels_b)]:
                projected, depth = project(world, frames[stem])
                finite = (depth > 0) & np.isfinite(projected).all(axis=1) & np.isfinite(cached_pixels).all(axis=1)
                if np.any(finite):
                    error = np.linalg.norm(projected[finite] - cached_pixels[finite], axis=1)
                    building_reprojection_max = max(building_reprojection_max, float(np.max(error)))
                endpoint_points[stem].append(inside_world)
                endpoint_pixels[stem].append(cached_pixels[current_inside])
        points = np.concatenate(pooled, axis=0) if pooled else np.zeros((0, 3), dtype=np.float64)
        expected_point_count = int(config["measurement"]["expected_fm_inside_point_count"][short])
        if len(points) != expected_point_count:
            raise RuntimeError(f"FM inside pool mismatch {short}: {len(points)} != {expected_point_count}")
        if building_reprojection_max > 2.000001:
            raise RuntimeError(f"cached fixed-camera reprojection cross-check exceeds 2px for {short}: {building_reprojection_max}")
        reprojection_max_all = max(reprojection_max_all, building_reprojection_max)
        plane_fit = fit_fm_plane(points, config)
        plane_normal = fm_plane_normal(plane_fit)

        view_stems = [str(view["stem"]) for view in visible_views[short]]
        building_angles: list[np.ndarray] = []
        point_pixels: dict[str, np.ndarray] = {}
        angle_by_view: dict[str, np.ndarray] = {}
        building_rows: list[dict[str, Any]] = []
        for stem in view_stems:
            frame = frames[stem]
            view_points = np.concatenate(endpoint_points[stem], axis=0) if endpoint_points[stem] else np.zeros((0, 3), dtype=np.float64)
            source_pixels = np.concatenate(endpoint_pixels[stem], axis=0) if endpoint_pixels[stem] else np.zeros((0, 2), dtype=np.float64)
            if len(view_points) != len(source_pixels):
                raise RuntimeError(f"endpoint point/pixel count mismatch: {short} {stem}")
            projected, depth = project(view_points, frame)
            positive = (
                (depth > 0) & np.isfinite(projected).all(axis=1) & np.isfinite(source_pixels).all(axis=1)
            ) if len(view_points) else np.zeros(0, dtype=bool)
            source_positive = source_pixels[positive]
            rounded = np.rint(source_positive).astype(np.int64) if len(source_positive) else np.zeros((0, 2), dtype=np.int64)
            in_frame = (
                (rounded[:, 0] >= 0) & (rounded[:, 0] < frame["width"])
                & (rounded[:, 1] >= 0) & (rounded[:, 1] < frame["height"])
            ) if len(rounded) else np.zeros(0, dtype=bool)
            in_frame_pixels = rounded[in_frame]
            unique_pixels = np.unique(in_frame_pixels, axis=0) if len(in_frame_pixels) else np.zeros((0, 2), dtype=np.int64)
            normal = normal_arrays[stem]
            sampled = normal[unique_pixels[:, 1], unique_pixels[:, 0]].astype(np.float64) if len(unique_pixels) else np.zeros((0, 3), dtype=np.float64)
            finite_normal = np.isfinite(sampled).all(axis=1)
            sampled = sampled[finite_normal]
            unique_pixels = unique_pixels[finite_normal]
            sampled /= np.maximum(np.linalg.norm(sampled, axis=1, keepdims=True), 1e-12)
            dots = np.abs(sampled @ plane_normal)
            angles = np.degrees(np.arccos(np.clip(dots, -1.0, 1.0))) if len(sampled) else np.asarray([], dtype=np.float64)
            stats = angle_stats(angles, float(config["measurement"]["within_angle_deg"]))
            normal_path = normal_dir / f"{stem}.npy"
            row = {
                "row_type": "view",
                "building_id": bid,
                "view_stem": stem,
                "image_name": frame["name"],
                "model_name": config["model"]["name"],
                "model_revision": config["model"]["revision"],
                "model_code_tree_sha256": pin["code_tree_sha256"],
                "weights_sha256": pin["weights_sha256"],
                "normal_frame": config["model"]["normal_frame"],
                "normal_path": rel(normal_path),
                "normal_sha256": next(item["actual_sha256"] for item in inventory if item["view_stem"] == stem),
                "normal_hash_match": True,
                "fm_plane_source": config["measurement"]["fm_plane_source"],
                "fm_inside_point_count": len(points),
                "fm_plane_ax": float(plane_fit["plane_ax"]),
                "fm_plane_by": float(plane_fit["plane_by"]),
                "fm_plane_c": float(plane_fit["plane_c"]),
                "fm_plane_normal_x": float(plane_normal[0]),
                "fm_plane_normal_y": float(plane_normal[1]),
                "fm_plane_normal_z": float(plane_normal[2]),
                "fm_plane_ransac_inlier_count": int(plane_fit["ransac_inlier_count"]),
                "fm_plane_ransac_inlier_ratio": float(plane_fit["ransac_inlier_ratio"]),
                "fm_plane_internal_rms_m": plane_fit["plane_internal_rms_m"],
                "visible_view_count": len(view_stems),
                "projected_positive_depth_count": int(np.count_nonzero(positive)),
                "projected_in_frame_count_raw": int(len(in_frame_pixels)),
                "sampled_unique_pixel_count": int(len(unique_pixels)),
                **stats,
                "cache_reprojection_crosscheck_max_px": building_reprojection_max,
                "summary_aggregation": "integer-pixel dedupe within building-view; view row",
                "status": "measured" if len(angles) else "no_projected_fm_pixels",
                "figure_path": rel(FIG_DIR / f"mononormal_{short}_overlay.png"),
                "footprint_role": config["measurement"]["footprint_role"],
                "pure_fm_fit": True,
                "originating_pair_endpoint_views_only": True,
                "gt_lod2_or_als_used": False,
                "gate_applied": False,
                "learning_runs_started": 0,
                "new_mononormal_inference_runs": 0,
                "new_mast3r_inference_runs": 0,
                "note": "originating pair endpoint source pixels only; fixed-COLMAP DLT reprojection cross-checked; abs-dot handles unoriented normal sign",
            }
            building_rows.append(row)
            point_pixels[stem] = unique_pixels.astype(np.float64)
            angle_by_view[stem] = angles
            samples_for_npz[f"{short}__{stem}"] = angles.astype(np.float32)
            building_angles.append(angles)
        pooled_angles = np.concatenate(building_angles) if building_angles else np.asarray([], dtype=np.float64)
        all_angles[short] = pooled_angles
        samples_for_npz[f"{short}__pooled_building_view"] = pooled_angles.astype(np.float32)
        summary_stats = angle_stats(pooled_angles, float(config["measurement"]["within_angle_deg"]))
        summary_row = {
            "row_type": "building_summary",
            "building_id": bid,
            "model_name": config["model"]["name"],
            "model_revision": config["model"]["revision"],
            "model_code_tree_sha256": pin["code_tree_sha256"],
            "weights_sha256": pin["weights_sha256"],
            "normal_frame": config["model"]["normal_frame"],
            "fm_plane_source": config["measurement"]["fm_plane_source"],
            "fm_inside_point_count": len(points),
            "fm_plane_ax": float(plane_fit["plane_ax"]),
            "fm_plane_by": float(plane_fit["plane_by"]),
            "fm_plane_c": float(plane_fit["plane_c"]),
            "fm_plane_normal_x": float(plane_normal[0]),
            "fm_plane_normal_y": float(plane_normal[1]),
            "fm_plane_normal_z": float(plane_normal[2]),
            "fm_plane_ransac_inlier_count": int(plane_fit["ransac_inlier_count"]),
            "fm_plane_ransac_inlier_ratio": float(plane_fit["ransac_inlier_ratio"]),
            "fm_plane_internal_rms_m": plane_fit["plane_internal_rms_m"],
            "visible_view_count": len(view_stems),
            "projected_positive_depth_count": sum(int(row["projected_positive_depth_count"]) for row in building_rows),
            "projected_in_frame_count_raw": sum(int(row["projected_in_frame_count_raw"]) for row in building_rows),
            "sampled_unique_pixel_count": sum(int(row["sampled_unique_pixel_count"]) for row in building_rows),
            **summary_stats,
            "cache_reprojection_crosscheck_max_px": building_reprojection_max,
            "summary_aggregation": config["measurement"]["building_summary"],
            "status": "measured" if len(pooled_angles) else "no_projected_fm_pixels",
            "figure_path": rel(FIG_DIR / f"mononormal_{short}_overlay.png"),
            "footprint_role": config["measurement"]["footprint_role"],
            "pure_fm_fit": True,
            "originating_pair_endpoint_views_only": True,
            "gt_lod2_or_als_used": False,
            "gate_applied": False,
            "learning_runs_started": 0,
            "new_mononormal_inference_runs": 0,
            "new_mast3r_inference_runs": 0,
            "note": "22.5-degree denominator is the sum of finite unique integer pixels over locked visible views",
        }
        rows.extend(building_rows)
        rows.append(summary_row)
        atomic_csv(OUT_CSV, rows, FIELDS)
        figure_path = overlay_figure(
            short, view_stems, frames, normal_arrays, point_pixels, angle_by_view,
            footprint, plane_fit, offset, config,
        )
        output_figures.append(figure_path)
        np.savez_compressed(SAMPLES_PATH, **samples_for_npz)
        per_building_manifest[short] = {
            "fm_inside_point_count": len(points),
            "eligible_pair_count": len(eligible_rows),
            "visible_view_count": len(view_stems),
            "building_view_unique_pixel_denominator": int(len(pooled_angles)),
            "angle_median_deg_absdot": summary_stats["angle_median_deg_absdot"],
            "within_22p5_count": summary_stats["within_22p5_count"],
            "within_22p5_rate": summary_stats["within_22p5_rate"],
            "cache_reprojection_crosscheck_max_px": building_reprojection_max,
            "gt_free_fm_plane": plane_fit,
        }
        atomic_json(
            PROGRESS_PATH,
            {
                "stage": "building_measurement",
                "done": building_index,
                "total": len(targets),
                "last_building": short,
                "partial_rows": len(rows),
                "updated_utc": now(),
            },
        )
        log(
            f"building={short} fm_points={len(points)} views={len(view_stems)} "
            f"denominator={len(pooled_angles)} median_deg={summary_stats['angle_median_deg_absdot']} "
            f"within22p5={summary_stats['within_22p5_rate']}"
        )

    distribution_path = distribution_figure(all_angles, config)
    output_figures.append(distribution_path)
    np.savez_compressed(SAMPLES_PATH, **samples_for_npz)

    model_angles = np.concatenate([all_angles[short] for short in targets])
    model_stats = angle_stats(model_angles, float(config["measurement"]["within_angle_deg"]))
    rows[0].update(
        {
            "fm_inside_point_count": sum(int(config["measurement"]["expected_fm_inside_point_count"][short]) for short in targets),
            "sampled_unique_pixel_count": int(len(model_angles)),
            **model_stats,
            "summary_aggregation": "pool building-summary building-view pixels across three targets",
            "figure_path": rel(distribution_path),
        }
    )
    atomic_csv(OUT_CSV, rows, FIELDS)
    atomic_json(
        PROGRESS_PATH,
        {
            "stage": "complete",
            "done": len(targets),
            "total": len(targets),
            "row_count": len(rows),
            "updated_utc": now(),
        },
    )
    log(f"complete rows={len(rows)} selected_normal_files={len(inventory)} figures={len(output_figures)}")

    outputs = [OUT_CSV, INVENTORY_PATH, SAMPLES_PATH, PROGRESS_PATH, RUN_LOG, *output_figures]
    output_hashes = {rel(path): sha256_file(path) for path in outputs}
    manifest = {
        "schema": "jointbuildgs.s3ap.phase0.mononormal_diag.manifest.v1",
        "created_utc": now(),
        "status": "complete",
        "git_head_at_measurement": git_value("rev-parse", "HEAD"),
        "branch": git_value("branch", "--show-current"),
        "crs": config["crs"],
        "docker": config["measurement_runtime"],
        "gpu_preflight": gpu,
        "learning_runs_started": 0,
        "new_mononormal_inference_runs": 0,
        "new_mast3r_inference_runs": 0,
        "model_pin": pin,
        "revision_recovery": {
            "repository": config["model"]["repository"],
            "revision": config["model"]["revision"],
            "rule": config["model"]["revision_recovery_rule"],
            "used_subtree_exact_match": True,
        },
        "cache_integrity": {
            "full_frame_cache_file_count": len(normal_files),
            "selected_unique_file_count": len(inventory),
            "selected_hash_match_count": sum(int(item["hash_match"]) for item in inventory),
            "selected_finite_unit_count": sum(item["status"] == "verified" for item in inventory),
            "footprint_inside_mask_mismatch_count": cache_mismatch_total,
            "fixed_camera_reprojection_crosscheck_max_px": reprojection_max_all,
        },
        "measurement_rule": config["measurement"],
        "pure_fm_fit": True,
        "originating_pair_endpoint_views_only": True,
        "footprint_crs_source": footprint_crs,
        "world_offset": offset.tolist(),
        "rows": {
            "total": len(rows),
            "model": sum(row["row_type"] == "model" for row in rows),
            "view": sum(row["row_type"] == "view" for row in rows),
            "building_summary": sum(row["row_type"] == "building_summary" for row in rows),
        },
        "buildings": per_building_manifest,
        "source_sha256": source_hashes(config),
        "normal_cache_inventory": inventory,
        "output_sha256": output_hashes,
        "interpretation_or_verdict": None,
        "gate_applied": False,
        "gt_lod2_or_als_used": False,
    }
    atomic_json(MANIFEST_PATH, manifest)
    return manifest


def partial_manifest(config: dict[str, Any], error: Exception) -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    try:
        log(f"partial failure={type(error).__name__}: {error}")
    except Exception:  # noqa: BLE001
        pass
    atomic_json(
        PROGRESS_PATH,
        {
            "stage": "partial",
            "error_type": type(error).__name__,
            "error": str(error),
            "updated_utc": now(),
        },
    )
    existing = [path for path in [OUT_CSV, INVENTORY_PATH, SAMPLES_PATH, PROGRESS_PATH, RUN_LOG] if path.exists()]
    manifest = {
        "schema": "jointbuildgs.s3ap.phase0.mononormal_diag.manifest.v1",
        "created_utc": now(),
        "status": "partial",
        "failure": {"type": type(error).__name__, "message": str(error)},
        "learning_runs_started": 0,
        "new_mononormal_inference_runs": 0,
        "new_mast3r_inference_runs": 0,
        "pure_fm_fit": True,
        "originating_pair_endpoint_views_only": True,
        "gt_lod2_or_als_used": False,
        "gate_applied": False,
        "configured_model_pin": config.get("model", {}),
        "output_sha256": {rel(path): sha256_file(path) for path in existing},
        "interpretation_or_verdict": None,
    }
    atomic_json(MANIFEST_PATH, manifest)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(CONFIG_PATH))
    return parser


def main() -> None:
    args = build_parser().parse_args()
    config = json.loads(resolve(args.config).read_text(encoding="utf-8"))
    try:
        manifest = run(config)
    except Exception as error:  # noqa: BLE001
        partial_manifest(config, error)
        raise
    print(
        json.dumps(
            {
                "status": manifest["status"],
                "csv": rel(OUT_CSV),
                "view_rows": manifest["rows"]["view"],
                "building_summary_rows": manifest["rows"]["building_summary"],
                "learning_runs_started": 0,
                "new_mononormal_inference_runs": 0,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
