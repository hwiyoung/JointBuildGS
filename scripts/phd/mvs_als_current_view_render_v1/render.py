#!/usr/bin/env python3
"""Render exact MVS and Existing-ALS points into three frozen current views.

The two sources are always projected into independent nearest-depth buffers.
Two representations are deliberately kept separate:

* ``raw``: one nearest-depth pixel per projected exact source point;
* ``proxy``: a source-independent, display-only disk expansion of ``raw``.

Neither representation selects a source, supplies a source weight, fuses
geometry, or performs Gaussian optimization.  The RGB/edge measurements are
diagnostics of image consistency and renderability, not correctness labels.
"""
from __future__ import annotations

import argparse
import colorsys
import csv
import hashlib
import itertools
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import cv2
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from src.stage2.colmap_io import Camera, Image, read_cameras_bin, read_images_bin


REPO = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = REPO / "configs/phd/mvs_als_current_view_render_v1/pilot_v1.json"
SOURCE_NAMES = ("mvs", "existing_als")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path, chunk_bytes: int = 8 << 20) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(chunk_bytes), b""):
            value.update(block)
    return value.hexdigest()


def sha256_array(value: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(value).tobytes()).hexdigest()


def atomic_bytes(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(value)
    os.replace(temporary, path)


def atomic_json(path: Path, value: Any) -> None:
    atomic_bytes(path, (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8"))


def atomic_npz(path: Path, **arrays: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp.npz")
    np.savez_compressed(temporary, **arrays)
    os.replace(temporary, path)


def atomic_rgb_png(path: Path, rgb: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp.png")
    ok = cv2.imwrite(str(temporary), cv2.cvtColor(np.asarray(rgb, np.uint8), cv2.COLOR_RGB2BGR))
    if not ok:
        raise RuntimeError(f"PNG write failed: {path}")
    os.replace(temporary, path)


def load_config(path: Path) -> dict[str, Any]:
    cfg = json.loads(path.read_text(encoding="utf-8"))
    if cfg.get("scientific_verdict", "missing") is not None:
        raise ValueError("scientific_verdict must remain null")
    if cfg.get("status") != "DEVELOPMENT_NON_CONFIRMATORY":
        raise ValueError("renderer status must remain DEVELOPMENT_NON_CONFIRMATORY")
    views = cfg["inputs"]["selected_views"]
    if [row["role"] for row in views] != ["TOP", "OBLIQUE_A", "OBLIQUE_B"]:
        raise ValueError("the three frozen camera roles drifted")
    if [int(row["colmap_image_id"]) for row in views] != [90, 840, 659]:
        raise ValueError("the three frozen COLMAP image IDs drifted")
    if len({row["name"] for row in views}) != 3:
        raise ValueError("selected view names must be unique")
    input_paths = json.dumps(cfg["inputs"], sort_keys=True).lower()
    for token in ("uas", "lod2", "roofsurface", "groundsurface", "stable_id", "journal1"):
        if token in input_paths:
            raise ValueError(f"prohibited token in input binding: {token}")
    radius = int(cfg["render"]["display_splat_radius_px"])
    if radius < 1 or radius > 8:
        raise ValueError("display_splat_radius_px must be in [1, 8]")
    overlay = cfg.get("relation_patch_overlay", {})
    if overlay.get("use") != "DISPLAY_ONLY":
        raise ValueError("relation/patch overlay use must remain DISPLAY_ONLY")
    if float(overlay.get("core_visibility_tolerance_m", 0.0)) <= 0:
        raise ValueError("core visibility tolerance must be positive")
    return cfg


def verify_regular_file(path: Path, expected: dict[str, Any], label: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise RuntimeError(f"{label} is missing or not a regular file: {path}")
    size = path.stat().st_size
    if size != int(expected["bytes"]):
        raise RuntimeError(f"{label} byte drift: {size} != {expected['bytes']}")
    digest = sha256_file(path)
    if digest != expected["sha256"]:
        raise RuntimeError(f"{label} hash drift: {digest} != {expected['sha256']}")
    return {"path": str(path), "bytes": size, "sha256": digest}


def _crosswalk_row_by_name(crosswalk: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = crosswalk.get("rows")
    if not isinstance(rows, list):
        raise RuntimeError("exact-937 crosswalk has no rows")
    result = {str(row["basename"]): row for row in rows}
    if len(result) != len(rows):
        raise RuntimeError("exact-937 crosswalk contains duplicate basenames")
    return result


def verify_inputs(
    cfg: dict[str, Any], repo_root: Path, artifact_root: Path,
) -> tuple[dict[str, Any], dict[int, Camera], dict[int, Image]]:
    inputs = cfg["inputs"]
    relation = inputs["source_relation"]
    relation_root = artifact_root / relation["relative_root"]
    records: dict[str, Any] = {
        "source_relation_partition_receipt": verify_regular_file(
            relation_root / relation["partition_receipt"]["relative_path"],
            relation["partition_receipt"],
            "source relation partition receipt",
        )
    }
    receipt = json.loads(
        (relation_root / relation["partition_receipt"]["relative_path"]).read_text(encoding="utf-8")
    )
    tile_rows = {row["tile_id"]: row for row in receipt["tiles"]}
    if relation["tile_id"] not in tile_rows:
        raise RuntimeError("selected source tile is absent from partition receipt")
    tile_row = tile_rows[relation["tile_id"]]
    records["source_partitions"] = {}
    for source in SOURCE_NAMES:
        expected = relation["partitions"][source]
        path = relation_root / expected["relative_path"]
        record = verify_regular_file(path, expected, f"{source} exact source partition")
        if int(expected["point_count"]) * 3 * 4 != int(expected["bytes"]):
            raise RuntimeError(f"{source} partition count/byte contract is inconsistent")
        receipt_key = "mvs_points" if source == "mvs" else "als_points"
        if int(tile_row[receipt_key]) != int(expected["point_count"]):
            raise RuntimeError(f"{source} partition count differs from partition receipt")
        records["source_partitions"][source] = record

    relation_core = inputs["source_relation_core_map"]
    relation_core_path = artifact_root / relation_core["relative_root"] / relation_core["relative_path"]
    records["source_relation_core_map"] = verify_regular_file(
        relation_core_path, relation_core, "frozen source relation core map"
    )

    patch_input = inputs["surface_patch"]
    patch_root = artifact_root / patch_input["relative_root"]
    records["surface_patch"] = {
        "artifact_manifest": verify_regular_file(
            patch_root / patch_input["artifact_manifest"]["relative_path"],
            patch_input["artifact_manifest"], "surface patch artifact manifest",
        ),
        "validation_receipt": verify_regular_file(
            patch_root / patch_input["validation_receipt"]["relative_path"],
            patch_input["validation_receipt"], "surface patch validation receipt",
        ),
        "outputs": {},
    }
    patch_manifest = json.loads(
        (patch_root / patch_input["artifact_manifest"]["relative_path"]).read_text(encoding="utf-8")
    )
    patch_validation = json.loads(
        (patch_root / patch_input["validation_receipt"]["relative_path"]).read_text(encoding="utf-8")
    )
    if patch_manifest.get("scientific_verdict", "missing") is not None:
        raise RuntimeError("surface patch artifact manifest scientific_verdict is not null")
    if patch_validation.get("scientific_verdict", "missing") is not None:
        raise RuntimeError("surface patch validation scientific_verdict is not null")
    if any(value != "PASS" for value in patch_validation.get("checks", {}).values()):
        raise RuntimeError("surface patch validation receipt contains a non-PASS check")
    manifest_outputs = patch_manifest.get("outputs", {})
    for name, expected in patch_input["outputs"].items():
        manifest_record = manifest_outputs.get(name)
        if not isinstance(manifest_record, dict):
            raise RuntimeError(f"surface patch manifest omits required output: {name}")
        if (
            int(manifest_record.get("bytes", -1)) != int(expected["bytes"])
            or manifest_record.get("sha256") != expected["sha256"]
        ):
            raise RuntimeError(f"surface patch manifest/output contract drift: {name}")
        records["surface_patch"]["outputs"][name] = verify_regular_file(
            patch_root / name, expected, f"surface patch output {name}"
        )
    records["surface_patch"]["patch_count"] = int(patch_validation["patch_count"])
    records["surface_patch"]["relation_core_count"] = int(patch_validation["relation_core_count"])

    camera_root = artifact_root / inputs["current_image_camera_root_relative_path"]
    records["camera_files"] = {}
    for relative, expected in inputs["camera_files"].items():
        records["camera_files"][relative] = verify_regular_file(
            camera_root / relative, expected, f"current camera file {relative}"
        )
    crosswalk_path = repo_root / inputs["exact_937_crosswalk"]["git_relative_path"]
    records["exact_937_crosswalk"] = verify_regular_file(
        crosswalk_path, inputs["exact_937_crosswalk"], "exact-937 crosswalk"
    )
    crosswalk = json.loads(crosswalk_path.read_text(encoding="utf-8"))
    if int(crosswalk.get("member_count", -1)) != int(inputs["exact_937_crosswalk"]["member_count"]):
        raise RuntimeError("exact-937 member count drift")
    exact_by_name = _crosswalk_row_by_name(crosswalk)

    cameras = read_cameras_bin(camera_root / "sparse/cameras.bin")
    images = read_images_bin(camera_root / "sparse/images.bin")
    records["selected_views"] = []
    for view in inputs["selected_views"]:
        image_id = int(view["colmap_image_id"])
        if image_id not in images:
            raise RuntimeError(f"selected COLMAP image ID is missing: {image_id}")
        image = images[image_id]
        if image.name != view["name"]:
            raise RuntimeError(f"selected COLMAP image/name drift: {image_id}: {image.name}")
        if image.camera_id not in cameras:
            raise RuntimeError(f"camera {image.camera_id} for image {image_id} is missing")
        exact = exact_by_name.get(view["name"])
        if exact is None:
            raise RuntimeError(f"selected image is outside exact-937: {view['name']}")
        if int(exact["colmap_image_id"]) != image_id:
            raise RuntimeError(f"crosswalk image ID drift for {view['name']}")
        if str(exact["source_camera_uid"]) != str(view["source_camera_uid"]):
            raise RuntimeError(f"crosswalk camera UID drift for {view['name']}")
        image_record = verify_regular_file(
            camera_root / "images" / view["name"],
            {"bytes": view["image_bytes"], "sha256": view["image_sha256"]},
            f"current RGB {view['name']}",
        )
        image_record.update(
            role=view["role"], colmap_image_id=image_id,
            source_camera_uid=str(view["source_camera_uid"]), camera_id=image.camera_id,
        )
        records["selected_views"].append(image_record)
    records["prohibited_inputs_accessed"] = []
    return records, cameras, images


def prism_bounds(cfg: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    value = cfg["pilot_prism_local_xyz_m"]
    minimum = np.array([value[axis][0] for axis in "xyz"], dtype=np.float32)
    maximum = np.array([value[axis][1] for axis in "xyz"], dtype=np.float32)
    if not bool(np.all(maximum > minimum)):
        raise ValueError("pilot prism bounds are invalid")
    return minimum, maximum


def select_half_open_prism(points: np.ndarray, minimum: np.ndarray, maximum: np.ndarray) -> np.ndarray:
    points = np.asarray(points)
    keep = np.all((points >= minimum) & (points < maximum), axis=1)
    return np.ascontiguousarray(points[keep], dtype="<f4")


def load_source_crop(
    path: Path, point_count: int, minimum: np.ndarray, maximum: np.ndarray,
) -> np.ndarray:
    value = np.memmap(path, dtype="<f4", mode="r", shape=(int(point_count), 3))
    return select_half_open_prism(value, minimum, maximum)


def scaled_camera(camera: Camera, downscale: float) -> tuple[np.ndarray, int, int]:
    width = int(round(camera.width * downscale))
    height = int(round(camera.height * downscale))
    intrinsic = camera.K().copy()
    intrinsic[0, :] *= downscale
    intrinsic[1, :] *= downscale
    return intrinsic, width, height


def project_points(
    points: np.ndarray, rotation: np.ndarray, translation: np.ndarray,
    intrinsic: np.ndarray, width: int, height: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    x, y, z, _ = project_points_indexed(
        points, rotation, translation, intrinsic, width, height
    )
    return x, y, z


def project_points_indexed(
    points: np.ndarray, rotation: np.ndarray, translation: np.ndarray,
    intrinsic: np.ndarray, width: int, height: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    if len(points) == 0:
        return (
            np.empty(0, dtype=np.int32), np.empty(0, dtype=np.int32),
            np.empty(0, dtype=np.float32), np.empty(0, dtype=np.int64),
        )
    camera_xyz = np.asarray(points, dtype=np.float64) @ rotation.T + translation
    z = camera_xyz[:, 2]
    finite_front = np.isfinite(camera_xyz).all(axis=1) & (z > 1e-6)
    original_index = np.flatnonzero(finite_front)
    camera_xyz = camera_xyz[finite_front]
    z = z[finite_front]
    u = intrinsic[0, 0] * camera_xyz[:, 0] / z + intrinsic[0, 2]
    v = intrinsic[1, 1] * camera_xyz[:, 1] / z + intrinsic[1, 2]
    x = np.floor(u + 0.5).astype(np.int64)
    y = np.floor(v + 0.5).astype(np.int64)
    inside = (x >= 0) & (x < width) & (y >= 0) & (y < height)
    return (
        x[inside].astype(np.int32), y[inside].astype(np.int32),
        z[inside].astype(np.float32), original_index[inside].astype(np.int64),
    )


def nearest_zbuffer(
    x: np.ndarray, y: np.ndarray, z: np.ndarray, width: int, height: int,
) -> np.ndarray:
    depth = np.full(height * width, np.inf, dtype=np.float32)
    if len(z):
        index = y.astype(np.int64) * width + x.astype(np.int64)
        np.minimum.at(depth, index, z)
    return depth.reshape(height, width)


def disk_offsets(radius: int) -> list[tuple[int, int]]:
    return [
        (dy, dx)
        for dy in range(-radius, radius + 1)
        for dx in range(-radius, radius + 1)
        if dx * dx + dy * dy <= radius * radius
    ]


def connected_display_proxy(raw_depth: np.ndarray, radius: int) -> np.ndarray:
    """Min-depth disk expansion of raw visible pixels, for display only."""
    raw = np.asarray(raw_depth, dtype=np.float32)
    height, width = raw.shape
    result = np.full_like(raw, np.inf)
    for dy, dx in disk_offsets(radius):
        source_y0, source_y1 = max(0, -dy), min(height, height - dy)
        source_x0, source_x1 = max(0, -dx), min(width, width - dx)
        target_y0, target_y1 = source_y0 + dy, source_y1 + dy
        target_x0, target_x1 = source_x0 + dx, source_x1 + dx
        np.minimum(
            result[target_y0:target_y1, target_x0:target_x1],
            raw[source_y0:source_y1, source_x0:source_x1],
            out=result[target_y0:target_y1, target_x0:target_x1],
        )
    return result


def prism_corners(minimum: np.ndarray, maximum: np.ndarray) -> np.ndarray:
    return np.asarray(list(itertools.product(*zip(minimum, maximum))), dtype=np.float32)


def projected_prism_roi(
    minimum: np.ndarray, maximum: np.ndarray, image: Image, intrinsic: np.ndarray,
    width: int, height: int, padding: int, minimum_size: int,
) -> tuple[int, int, int, int]:
    corners = prism_corners(minimum, maximum)
    camera_xyz = corners.astype(np.float64) @ image.R().T + image.tvec
    keep = camera_xyz[:, 2] > 1e-6
    if not bool(keep.any()):
        raise RuntimeError(f"pilot prism is behind current camera {image.id}")
    camera_xyz = camera_xyz[keep]
    u = intrinsic[0, 0] * camera_xyz[:, 0] / camera_xyz[:, 2] + intrinsic[0, 2]
    v = intrinsic[1, 1] * camera_xyz[:, 1] / camera_xyz[:, 2] + intrinsic[1, 2]
    x0 = max(0, int(math.floor(float(np.min(u)))) - padding)
    x1 = min(width, int(math.ceil(float(np.max(u)))) + padding + 1)
    y0 = max(0, int(math.floor(float(np.min(v)))) - padding)
    y1 = min(height, int(math.ceil(float(np.max(v)))) + padding + 1)
    if x1 <= x0 or y1 <= y0:
        raise RuntimeError(f"projected pilot prism is outside current camera {image.id}")

    def expand(lo: int, hi: int, limit: int) -> tuple[int, int]:
        missing = max(0, minimum_size - (hi - lo))
        lo = max(0, lo - missing // 2)
        hi = min(limit, hi + missing - missing // 2)
        if hi - lo < minimum_size:
            lo = max(0, hi - minimum_size)
            hi = min(limit, lo + minimum_size)
        return lo, hi

    x0, x1 = expand(x0, x1, width)
    y0, y1 = expand(y0, y1, height)
    return x0, y0, x1, y1


def validate_patch_bindings(
    relation_rows: np.ndarray, membership: np.ndarray, summary: np.ndarray,
    expected_core_count: int, expected_patch_count: int,
) -> None:
    relation_required = {"x", "y", "z", "relation_class", "core_source"}
    membership_required = {
        "core_index", "patch_id", "raw_relation_class", "patch_relation_class",
        "core_source", "patch_status",
    }
    summary_required = {"patch_id", "patch_uid", "core_source", "patch_status"}
    if not relation_required.issubset(relation_rows.dtype.names or ()):
        raise RuntimeError("source relation core schema drift")
    if not membership_required.issubset(membership.dtype.names or ()):
        raise RuntimeError("surface patch membership schema drift")
    if not summary_required.issubset(summary.dtype.names or ()):
        raise RuntimeError("surface patch summary schema drift")
    if len(relation_rows) != expected_core_count or len(membership) != expected_core_count:
        raise RuntimeError("relation/patch core count drift")
    if len(summary) != expected_patch_count:
        raise RuntimeError("surface patch summary count drift")
    if not np.array_equal(membership["core_index"], np.arange(expected_core_count, dtype=np.uint32)):
        raise RuntimeError("surface patch membership order drift")
    if not np.array_equal(membership["raw_relation_class"], relation_rows["relation_class"]):
        raise RuntimeError("surface patch raw relation provenance drift")
    if not np.array_equal(membership["core_source"], relation_rows["core_source"]):
        raise RuntimeError("surface patch source-family provenance drift")
    patch_ids = np.asarray(summary["patch_id"], dtype=np.uint32)
    if len(np.unique(patch_ids)) != len(patch_ids) or bool(np.any(patch_ids == 0)):
        raise RuntimeError("surface patch summary IDs are invalid")
    assigned = np.asarray(membership["patch_id"], dtype=np.uint32)
    if not np.all(np.isin(np.unique(assigned[assigned > 0]), patch_ids)):
        raise RuntimeError("surface patch membership references an unknown patch")


def raw_source_visibility_mask(
    x: np.ndarray, y: np.ndarray, z: np.ndarray, core_source: np.ndarray,
    raw_depth_by_source: dict[str, np.ndarray], tolerance_m: float,
) -> np.ndarray:
    """Gate each relation core only against its own exact-source raw z-buffer."""
    visible = np.zeros(len(z), dtype=bool)
    for source_code, source_name in ((0, "mvs"), (1, "existing_als")):
        selected = np.asarray(core_source) == source_code
        if not bool(selected.any()):
            continue
        reference = raw_depth_by_source[source_name][y[selected], x[selected]]
        visible[selected] = np.isfinite(reference) & (np.abs(z[selected] - reference) <= tolerance_m)
    unknown = ~np.isin(core_source, [0, 1])
    if bool(unknown.any()):
        raise RuntimeError("relation core contains an unknown source family")
    return visible


def patch_uid_color(uid: bytes | np.bytes_ | str, patch_id: int) -> tuple[float, float, float]:
    if patch_id == 0:
        return (0.39, 0.46, 0.55)
    if isinstance(uid, (bytes, np.bytes_)):
        text = bytes(uid).decode("ascii").rstrip("\x00")
    else:
        text = str(uid)
    digest = hashlib.sha256(text.encode("ascii")).digest()
    hue = int.from_bytes(digest[:2], "little") / 65535.0
    return colorsys.hsv_to_rgb(hue, 0.72, 0.94)


def save_relation_patch_projection_panel(
    path: Path, rgb: np.ndarray, x: np.ndarray, y: np.ndarray, core_indices: np.ndarray,
    relation_rows: np.ndarray, membership: np.ndarray, summary: np.ndarray,
    overlay_cfg: dict[str, Any], audit: dict[str, Any],
) -> None:
    raw_class = membership["raw_relation_class"][core_indices]
    patch_class = membership["patch_relation_class"][core_indices]
    patch_id = membership["patch_id"][core_indices]
    family = membership["core_source"][core_indices]
    status = membership["patch_status"][core_indices]
    summary_uid = {
        int(row["patch_id"]): row["patch_uid"]
        for row in summary
    }
    raw_colors = [overlay_cfg["relation_class_colors"][str(int(value))] for value in raw_class]
    patch_colors = [overlay_cfg["relation_class_colors"][str(int(value))] for value in patch_class]
    uid_colors = [patch_uid_color(summary_uid.get(int(value), b""), int(value)) for value in patch_id]
    family_colors = [overlay_cfg["source_family_colors"][str(int(value))] for value in family]
    status_colors = [overlay_cfg["patch_status_colors"][str(int(value))] for value in status]

    fig, axes = plt.subplots(2, 3, figsize=(14.5, 9), dpi=150, constrained_layout=True)
    panels = [
        (None, "Current RGB (exact camera crop)"),
        (raw_colors, "Frozen raw five-class relation cores"),
        (patch_colors, "Patch-aggregated relation class"),
        (uid_colors, "Patch UID (deterministic color)"),
        (family_colors, "Core source family: MVS cyan / ALS violet"),
        (status_colors, "Patch status"),
    ]
    for axis, (colors, title) in zip(axes.ravel(), panels):
        axis.imshow(rgb)
        if colors is not None and len(core_indices):
            axis.scatter(
                x, y, s=float(overlay_cfg["marker_size_px2"]), c=colors,
                alpha=float(overlay_cfg["marker_alpha"]), linewidths=0.20,
                edgecolors="#111827",
            )
        axis.set_title(title, fontsize=10)
        axis.axis("off")
    fig.suptitle(
        "Display-only relation/patch audit overlay — "
        f"{audit['visibility_gated_cores']} visible cores; own-source raw-z tolerance "
        f"±{float(overlay_cfg['core_visibility_tolerance_m']):.2f} m",
        fontsize=12,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp.png")
    fig.savefig(temporary)
    plt.close(fig)
    os.replace(temporary, path)


def finite_depth_stats(depth: np.ndarray) -> dict[str, Any]:
    mask = np.isfinite(depth)
    values = depth[mask]
    result: dict[str, Any] = {
        "valid_pixels": int(mask.sum()),
        "valid_fraction": float(mask.mean()),
    }
    for label, q in (("minimum_m", 0.0), ("median_m", 0.5), ("p95_m", 0.95), ("maximum_m", 1.0)):
        result[label] = float(np.quantile(values, q)) if len(values) else None
    return result


def residual_stats(first: np.ndarray, second: np.ndarray) -> tuple[np.ndarray, dict[str, Any]]:
    common = np.isfinite(first) & np.isfinite(second)
    signed = np.full(first.shape, np.nan, dtype=np.float32)
    signed[common] = first[common] - second[common]
    values = signed[common]
    absolute = np.abs(values)
    result: dict[str, Any] = {
        "common_pixels": int(common.sum()),
        "common_fraction": float(common.mean()),
        "signed_definition": "MVS_CAMERA_Z_MINUS_EXISTING_ALS_CAMERA_Z",
    }
    for label, array, q in (
        ("signed_median_m", values, 0.5),
        ("absolute_median_m", absolute, 0.5),
        ("absolute_p90_m", absolute, 0.9),
        ("absolute_p95_m", absolute, 0.95),
    ):
        result[label] = float(np.quantile(array, q)) if len(array) else None
    return signed, result


def mask_connectivity(mask: np.ndarray) -> dict[str, Any]:
    value = np.asarray(mask, dtype=np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(value, connectivity=8)
    component_sizes = stats[1:, cv2.CC_STAT_AREA] if count > 1 else np.empty(0, dtype=np.int32)
    valid = int(value.sum())
    return {
        "component_count": int(max(0, count - 1)),
        "largest_component_pixels": int(component_sizes.max()) if len(component_sizes) else 0,
        "largest_component_fraction_of_valid": (
            float(component_sizes.max() / valid) if len(component_sizes) and valid else 0.0
        ),
    }


def rgb_and_geometry_edges(
    rgb: np.ndarray, depth: np.ndarray, canny_low: int, canny_high: int,
    thresholds: Iterable[int],
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    gray = cv2.cvtColor(np.asarray(rgb, np.uint8), cv2.COLOR_RGB2GRAY)
    rgb_edge = cv2.Canny(gray, canny_low, canny_high) > 0
    mask = np.isfinite(depth).astype(np.uint8)
    kernel = np.ones((3, 3), dtype=np.uint8)
    geometry_edge = cv2.morphologyEx(mask, cv2.MORPH_GRADIENT, kernel) > 0
    distance = cv2.distanceTransform((~rgb_edge).astype(np.uint8), cv2.DIST_L2, 3)
    samples = distance[geometry_edge]
    metrics: dict[str, Any] = {
        "rgb_edge_pixels": int(rgb_edge.sum()),
        "geometry_edge_pixels": int(geometry_edge.sum()),
        "geometry_to_rgb_edge_distance_median_px": float(np.median(samples)) if len(samples) else None,
        "geometry_to_rgb_edge_distance_p90_px": float(np.quantile(samples, 0.9)) if len(samples) else None,
    }
    for threshold in thresholds:
        metrics[f"geometry_edge_within_{int(threshold)}px_fraction"] = (
            float((samples <= int(threshold)).mean()) if len(samples) else None
        )
    return rgb_edge, geometry_edge, metrics


def mask_overlay(rgb: np.ndarray, mvs_mask: np.ndarray, als_mask: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(np.asarray(rgb, np.uint8), cv2.COLOR_RGB2GRAY)
    overlay = np.repeat(gray[..., None], 3, axis=2).astype(np.float32) * 0.55
    only_mvs = mvs_mask & ~als_mask
    only_als = als_mask & ~mvs_mask
    common = mvs_mask & als_mask
    overlay[only_mvs] = (40, 205, 255)
    overlay[only_als] = (255, 170, 30)
    overlay[common] = (245, 245, 245)
    return np.clip(overlay, 0, 255).astype(np.uint8)


def edge_overlay(
    rgb: np.ndarray, rgb_edge: np.ndarray, mvs_edge: np.ndarray, als_edge: np.ndarray,
) -> np.ndarray:
    value = (np.asarray(rgb, np.uint8).astype(np.float32) * 0.48).astype(np.uint8)
    value[rgb_edge] = (220, 220, 220)
    value[mvs_edge & ~als_edge] = (25, 220, 255)
    value[als_edge & ~mvs_edge] = (255, 145, 25)
    value[mvs_edge & als_edge] = (255, 255, 255)
    return value


def save_panels(
    path: Path, edge_path: Path, rgb: np.ndarray,
    mvs_raw: np.ndarray, als_raw: np.ndarray, mvs_proxy: np.ndarray, als_proxy: np.ndarray,
    raw_signed: np.ndarray, proxy_signed: np.ndarray,
    raw_edges: tuple[np.ndarray, np.ndarray, np.ndarray],
    proxy_edges: tuple[np.ndarray, np.ndarray, np.ndarray], residual_max: float,
) -> None:
    finite_values = np.concatenate(
        [value[np.isfinite(value)] for value in (mvs_raw, als_raw, mvs_proxy, als_proxy)]
    )
    depth_lo, depth_hi = np.quantile(finite_values, [0.02, 0.98])
    raw_mask_view = mask_overlay(rgb, np.isfinite(mvs_raw), np.isfinite(als_raw))
    proxy_mask_view = mask_overlay(rgb, np.isfinite(mvs_proxy), np.isfinite(als_proxy))
    raw_edge_view = edge_overlay(rgb, *raw_edges)
    proxy_edge_view = edge_overlay(rgb, *proxy_edges)
    current_edge_view = np.asarray(rgb).copy()
    current_edge_view[raw_edges[0]] = (240, 240, 240)

    panels = [
        (rgb, "Current RGB", {}),
        (mvs_raw, "MVS raw point z-buffer", {"cmap": "turbo", "vmin": depth_lo, "vmax": depth_hi}),
        (als_raw, "Existing ALS raw point z-buffer", {"cmap": "turbo", "vmin": depth_lo, "vmax": depth_hi}),
        (raw_mask_view, "Raw masks: MVS cyan / ALS orange", {}),
        (np.abs(raw_signed), "Raw common |depth residual|", {"cmap": "magma", "vmin": 0, "vmax": residual_max}),
        (raw_edge_view, "Raw geometry edges over RGB", {}),
        (current_edge_view, "Current RGB edges", {}),
        (mvs_proxy, "MVS connected display proxy", {"cmap": "turbo", "vmin": depth_lo, "vmax": depth_hi}),
        (als_proxy, "Existing ALS connected display proxy", {"cmap": "turbo", "vmin": depth_lo, "vmax": depth_hi}),
        (proxy_mask_view, "Proxy masks: MVS cyan / ALS orange", {}),
        (np.abs(proxy_signed), "Proxy common |depth residual|", {"cmap": "magma", "vmin": 0, "vmax": residual_max}),
        (proxy_edge_view, "Proxy geometry edges over RGB", {}),
    ]
    fig, axes = plt.subplots(2, 6, figsize=(21, 7.2), dpi=145, constrained_layout=True)
    for axis, (value, title, kwargs) in zip(axes.ravel(), panels):
        shown = value
        if np.issubdtype(np.asarray(value).dtype, np.floating):
            shown = np.where(np.isfinite(value), value, np.nan)
        axis.imshow(shown, **kwargs)
        axis.set_title(title, fontsize=9)
        axis.axis("off")
    fig.suptitle(
        "Raw exact-source projection (top) vs display-only connected proxy (bottom)",
        fontsize=12,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp.png")
    fig.savefig(temporary)
    plt.close(fig)
    os.replace(temporary, path)

    fig, axes = plt.subplots(1, 3, figsize=(14, 4.5), dpi=145, constrained_layout=True)
    for axis, value, title in zip(
        axes, (current_edge_view, raw_edge_view, proxy_edge_view),
        ("Current RGB edges", "Raw projected geometry edges", "Connected proxy edges"),
    ):
        axis.imshow(value)
        axis.set_title(title)
        axis.axis("off")
    temporary = edge_path.with_suffix(".tmp.png")
    fig.savefig(temporary)
    plt.close(fig)
    os.replace(temporary, edge_path)


def artifact_record(path: Path, root: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(root).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def source_git_head(repo_root: Path) -> str:
    env = os.environ.get("JBGS_SOURCE_GIT_HEAD", "").strip()
    if env:
        return env
    return "UNKNOWN"


def render(cfg_path: Path, repo_root: Path, artifact_root: Path) -> Path:
    cfg = load_config(cfg_path)
    inputs, cameras, images = verify_inputs(cfg, repo_root, artifact_root)
    output_root = artifact_root / cfg["output_relative_root"]
    output_root.mkdir(parents=True, exist_ok=True)
    minimum, maximum = prism_bounds(cfg)
    relation = cfg["inputs"]["source_relation"]
    relation_root = artifact_root / relation["relative_root"]
    source_points: dict[str, np.ndarray] = {}
    source_records: dict[str, Any] = {}
    for source in SOURCE_NAMES:
        expected = relation["partitions"][source]
        points = load_source_crop(
            relation_root / expected["relative_path"], expected["point_count"], minimum, maximum
        )
        if len(points) == 0:
            raise RuntimeError(f"pilot prism contains no {source} source points")
        source_points[source] = points
        source_records[source] = {
            "points_in_half_open_prism": len(points),
            "selected_xyz_f32le_sha256": sha256_array(points),
            "minimum_local_xyz_m": points.min(axis=0).astype(float).tolist(),
            "maximum_local_xyz_m": points.max(axis=0).astype(float).tolist(),
        }

    relation_core_cfg = cfg["inputs"]["source_relation_core_map"]
    relation_rows = np.load(
        artifact_root / relation_core_cfg["relative_root"] / relation_core_cfg["relative_path"],
        mmap_mode="r", allow_pickle=False,
    )
    patch_cfg = cfg["inputs"]["surface_patch"]
    patch_root = artifact_root / patch_cfg["relative_root"]
    patch_membership = np.load(patch_root / "patch_membership.npy", mmap_mode="r", allow_pickle=False)
    patch_summary = np.load(patch_root / "surface_patch_summary.npy", mmap_mode="r", allow_pickle=False)
    validate_patch_bindings(
        relation_rows, patch_membership, patch_summary,
        int(relation_core_cfg["core_count"]), int(inputs["surface_patch"]["patch_count"]),
    )
    relation_xyz = np.column_stack(
        (relation_rows["x"], relation_rows["y"], relation_rows["z"])
    ).astype(np.float32, copy=False)
    relation_in_prism = np.all(
        (relation_xyz >= minimum[None, :]) & (relation_xyz < maximum[None, :]), axis=1
    )
    relation_prism_indices = np.flatnonzero(relation_in_prism)
    relation_prism_xyz = np.ascontiguousarray(relation_xyz[relation_prism_indices], dtype=np.float32)
    if not len(relation_prism_indices):
        raise RuntimeError("pilot prism contains no relation cores for patch overlay")

    input_manifest = {
        "schema": "jointbuildgs.phd.mvs_als_current_view_render.input_manifest.v1",
        "task_id": cfg["task_id"],
        "created_at": utc_now(),
        "config_path": str(cfg_path),
        "config_sha256": sha256_file(cfg_path),
        "verified_inputs": inputs,
        "pilot_prism_local_xyz_m": cfg["pilot_prism_local_xyz_m"],
        "selected_source_crops": source_records,
        "source_relation_class_used": "DISPLAY_ONLY",
        "surface_patch_used": "DISPLAY_ONLY",
        "relation_cores_in_pilot_prism": len(relation_prism_indices),
        "relation_patch_overlay_changes_source_zbuffers_or_metrics": False,
        "prohibited_inputs_accessed": [],
        "scientific_verdict": None,
    }
    atomic_json(output_root / "resolved_input_manifest.json", input_manifest)

    render_cfg = cfg["render"]
    camera_root = artifact_root / cfg["inputs"]["current_image_camera_root_relative_path"]
    view_metrics: list[dict[str, Any]] = []
    for view in cfg["inputs"]["selected_views"]:
        image = images[int(view["colmap_image_id"])]
        camera = cameras[image.camera_id]
        intrinsic, width, height = scaled_camera(camera, float(render_cfg["downscale"]))
        rgb_bgr = cv2.imread(str(camera_root / "images" / view["name"]), cv2.IMREAD_COLOR)
        if rgb_bgr is None:
            raise RuntimeError(f"current RGB decode failed: {view['name']}")
        if (rgb_bgr.shape[1], rgb_bgr.shape[0]) != (camera.width, camera.height):
            raise RuntimeError(f"RGB/camera size drift: {view['name']}")
        rgb = cv2.cvtColor(rgb_bgr, cv2.COLOR_BGR2RGB)
        rgb = cv2.resize(rgb, (width, height), interpolation=cv2.INTER_AREA)
        roi = projected_prism_roi(
            minimum, maximum, image, intrinsic, width, height,
            int(render_cfg["roi_padding_px"]), int(render_cfg["minimum_roi_size_px"]),
        )
        x0, y0, x1, y1 = roi
        rgb_roi = np.ascontiguousarray(rgb[y0:y1, x0:x1])
        raw_full: dict[str, np.ndarray] = {}
        projected_counts: dict[str, int] = {}
        for source in SOURCE_NAMES:
            px, py, pz = project_points(
                source_points[source], image.R(), image.tvec, intrinsic, width, height
            )
            raw_full[source] = nearest_zbuffer(px, py, pz, width, height)
            projected_counts[source] = len(pz)
        raw = {source: np.ascontiguousarray(value[y0:y1, x0:x1]) for source, value in raw_full.items()}
        proxy = {
            source: connected_display_proxy(value, int(render_cfg["display_splat_radius_px"]))
            for source, value in raw.items()
        }
        raw_signed, raw_residual = residual_stats(raw["mvs"], raw["existing_als"])
        proxy_signed, proxy_residual = residual_stats(proxy["mvs"], proxy["existing_als"])

        core_x, core_y, core_z, projected_local_index = project_points_indexed(
            relation_prism_xyz, image.R(), image.tvec, intrinsic, width, height
        )
        projected_core_indices = relation_prism_indices[projected_local_index]
        visibility = raw_source_visibility_mask(
            core_x, core_y, core_z,
            patch_membership["core_source"][projected_core_indices], raw_full,
            float(cfg["relation_patch_overlay"]["core_visibility_tolerance_m"]),
        )
        inside_roi = (
            (core_x >= x0) & (core_x < x1) & (core_y >= y0) & (core_y < y1)
        )
        display_keep = visibility & inside_roi
        visible_core_indices = projected_core_indices[display_keep]
        visible_x = core_x[display_keep] - x0
        visible_y = core_y[display_keep] - y0
        visible_sources = patch_membership["core_source"][visible_core_indices]
        visible_raw_classes = patch_membership["raw_relation_class"][visible_core_indices]
        visible_patch_classes = patch_membership["patch_relation_class"][visible_core_indices]
        visible_statuses = patch_membership["patch_status"][visible_core_indices]
        overlay_audit = {
            "use": "DISPLAY_ONLY",
            "visibility_gate": cfg["relation_patch_overlay"]["visibility_gate"],
            "visibility_tolerance_m": float(
                cfg["relation_patch_overlay"]["core_visibility_tolerance_m"]
            ),
            "relation_cores_in_pilot_prism": len(relation_prism_indices),
            "cores_projected_in_full_image": len(projected_core_indices),
            "cores_projected_inside_roi": int(inside_roi.sum()),
            "visibility_gated_cores": len(visible_core_indices),
            "visibility_rejected_or_outside_roi_cores": int(
                len(projected_core_indices) - len(visible_core_indices)
            ),
            "visible_core_count_by_source_family": {
                str(code): int((visible_sources == code).sum()) for code in (0, 1)
            },
            "visible_raw_relation_class_counts": {
                str(code): int((visible_raw_classes == code).sum()) for code in range(1, 6)
            },
            "visible_patch_relation_class_counts": {
                str(code): int((visible_patch_classes == code).sum()) for code in range(1, 6)
            },
            "visible_patch_status_counts": {
                str(code): int((visible_statuses == code).sum()) for code in range(0, 5)
            },
            "changes_source_zbuffers_or_metrics": False,
            "source_authority_decision": None,
        }

        thresholds = [int(value) for value in render_cfg["edge_distance_thresholds_px"]]
        raw_rgb_edge, raw_mvs_edge, raw_mvs_edge_metrics = rgb_and_geometry_edges(
            rgb_roi, raw["mvs"], int(render_cfg["canny_low"]), int(render_cfg["canny_high"]), thresholds
        )
        _, raw_als_edge, raw_als_edge_metrics = rgb_and_geometry_edges(
            rgb_roi, raw["existing_als"], int(render_cfg["canny_low"]), int(render_cfg["canny_high"]), thresholds
        )
        proxy_rgb_edge, proxy_mvs_edge, proxy_mvs_edge_metrics = rgb_and_geometry_edges(
            rgb_roi, proxy["mvs"], int(render_cfg["canny_low"]), int(render_cfg["canny_high"]), thresholds
        )
        _, proxy_als_edge, proxy_als_edge_metrics = rgb_and_geometry_edges(
            rgb_roi, proxy["existing_als"], int(render_cfg["canny_low"]), int(render_cfg["canny_high"]), thresholds
        )

        view_root = output_root / "views" / view["role"].lower()
        atomic_rgb_png(view_root / "current_rgb.png", rgb_roi)
        atomic_npz(
            view_root / "source_independent_projections.npz",
            mvs_raw_depth_camera_z_m=raw["mvs"],
            existing_als_raw_depth_camera_z_m=raw["existing_als"],
            mvs_connected_display_proxy_depth_camera_z_m=proxy["mvs"],
            existing_als_connected_display_proxy_depth_camera_z_m=proxy["existing_als"],
            raw_signed_common_residual_m=raw_signed,
            proxy_signed_common_residual_m=proxy_signed,
            rgb_edges=raw_rgb_edge.astype(np.uint8),
            mvs_raw_geometry_edges=raw_mvs_edge.astype(np.uint8),
            existing_als_raw_geometry_edges=raw_als_edge.astype(np.uint8),
            mvs_proxy_geometry_edges=proxy_mvs_edge.astype(np.uint8),
            existing_als_proxy_geometry_edges=proxy_als_edge.astype(np.uint8),
        )
        save_panels(
            view_root / "comparison_panel.png", view_root / "edge_comparison_panel.png", rgb_roi,
            raw["mvs"], raw["existing_als"], proxy["mvs"], proxy["existing_als"],
            raw_signed, proxy_signed,
            (raw_rgb_edge, raw_mvs_edge, raw_als_edge),
            (proxy_rgb_edge, proxy_mvs_edge, proxy_als_edge),
            float(render_cfg["depth_residual_display_max_m"]),
        )
        save_relation_patch_projection_panel(
            view_root / "relation_patch_projection_panel.png", rgb_roi,
            visible_x, visible_y, visible_core_indices,
            relation_rows, patch_membership, patch_summary,
            cfg["relation_patch_overlay"], overlay_audit,
        )
        center = (-image.R().T @ image.tvec).astype(float)
        metric = {
            "role": view["role"],
            "colmap_image_id": int(view["colmap_image_id"]),
            "source_camera_uid": str(view["source_camera_uid"]),
            "name": view["name"],
            "image_sha256": view["image_sha256"],
            "camera_id": int(image.camera_id),
            "camera_model": camera.model,
            "native_size_wh": [int(camera.width), int(camera.height)],
            "render_size_wh": [width, height],
            "intrinsic_scaled": intrinsic.astype(float).tolist(),
            "camera_center_local_xyz_m": center.tolist(),
            "roi_xyxy_half_open_px": list(roi),
            "roi_size_wh": [x1 - x0, y1 - y0],
            "points_projected_in_full_image": projected_counts,
            "raw": {
                source: {
                    **finite_depth_stats(raw[source]),
                    **mask_connectivity(np.isfinite(raw[source])),
                }
                for source in SOURCE_NAMES
            },
            "connected_display_proxy": {
                source: {
                    **finite_depth_stats(proxy[source]),
                    **mask_connectivity(np.isfinite(proxy[source])),
                }
                for source in SOURCE_NAMES
            },
            "raw_common_residual": raw_residual,
            "proxy_common_residual": proxy_residual,
            "rgb_edge_diagnostics": {
                "raw": {"mvs": raw_mvs_edge_metrics, "existing_als": raw_als_edge_metrics},
                "connected_display_proxy": {
                    "mvs": proxy_mvs_edge_metrics, "existing_als": proxy_als_edge_metrics,
                },
            },
            "relation_patch_overlay": overlay_audit,
            "source_relation_class_used": "DISPLAY_ONLY",
            "surface_patch_used": "DISPLAY_ONLY",
            "source_authority_decision": None,
            "scientific_verdict": None,
        }
        atomic_json(view_root / "metrics.json", metric)
        view_metrics.append(metric)

    csv_path = output_root / "view_metrics.csv"
    csv_rows: list[dict[str, Any]] = []
    for metric in view_metrics:
        row: dict[str, Any] = {
            "role": metric["role"], "colmap_image_id": metric["colmap_image_id"],
            "name": metric["name"],
        }
        for representation, key in (("raw", "raw"), ("proxy", "connected_display_proxy")):
            for source in SOURCE_NAMES:
                values = metric[key][source]
                row[f"{representation}_{source}_valid_fraction"] = values["valid_fraction"]
                row[f"{representation}_{source}_component_count"] = values["component_count"]
                row[f"{representation}_{source}_largest_component_fraction"] = values[
                    "largest_component_fraction_of_valid"
                ]
            residual = metric[f"{representation}_common_residual"]
            row[f"{representation}_common_fraction"] = residual["common_fraction"]
            row[f"{representation}_absolute_residual_median_m"] = residual["absolute_median_m"]
            row[f"{representation}_absolute_residual_p90_m"] = residual["absolute_p90_m"]
        csv_rows.append(row)
    temporary_csv = csv_path.with_suffix(".tmp.csv")
    with temporary_csv.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(csv_rows[0]))
        writer.writeheader()
        writer.writerows(csv_rows)
    os.replace(temporary_csv, csv_path)

    technical_return = {
        "schema": "jointbuildgs.phd.mvs_als_current_view_render.technical_return.v1",
        "task_id": cfg["task_id"],
        "status": "COMPLETE_DEVELOPMENT_NON_CONFIRMATORY",
        "created_at": utc_now(),
        "source_git_head": source_git_head(repo_root),
        "config_sha256": sha256_file(cfg_path),
        "view_count": len(view_metrics),
        "view_roles": [row["role"] for row in view_metrics],
        "source_points_in_pilot_prism": {
            source: source_records[source]["points_in_half_open_prism"] for source in SOURCE_NAMES
        },
        "relation_cores_in_pilot_prism": len(relation_prism_indices),
        "visibility_gated_relation_cores_by_view": {
            row["role"]: row["relation_patch_overlay"]["visibility_gated_cores"]
            for row in view_metrics
        },
        "representations": {
            "raw": cfg["interpretation_boundary"]["raw_point_zbuffer"],
            "connected_display_proxy": cfg["interpretation_boundary"]["connected_display_proxy"],
        },
        "interpretation": cfg["interpretation_boundary"]["metrics"],
        "source_relation_class_used": "DISPLAY_ONLY",
        "surface_patch_used": "DISPLAY_ONLY",
        "relation_patch_overlay_visibility_gate": {
            "definition": cfg["relation_patch_overlay"]["visibility_gate"],
            "tolerance_m": cfg["relation_patch_overlay"]["core_visibility_tolerance_m"],
            "changes_source_zbuffers_or_metrics": False,
        },
        "source_authority_decision": None,
        "source_weights": None,
        "fusion_performed": False,
        "gaussian_optimization_performed": False,
        "prohibited_inputs_accessed": [],
        "scientific_verdict": None,
    }
    atomic_json(output_root / "technical_return.json", technical_return)

    inventory_paths = sorted(
        path for path in output_root.rglob("*")
        if path.is_file() and path.name not in {"artifact_manifest.json", "validation_receipt.json"}
    )
    artifact_manifest = {
        "schema": "jointbuildgs.phd.mvs_als_current_view_render.artifact_manifest.v1",
        "task_id": cfg["task_id"],
        "created_at": utc_now(),
        "artifacts": [artifact_record(path, output_root) for path in inventory_paths],
        "scientific_verdict": None,
    }
    atomic_json(output_root / "artifact_manifest.json", artifact_manifest)
    validate_output(cfg, output_root)
    return output_root


def validate_output(cfg: dict[str, Any], output_root: Path) -> dict[str, Any]:
    manifest_path = output_root / "artifact_manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError("artifact manifest is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("scientific_verdict", "missing") is not None:
        raise RuntimeError("artifact manifest scientific_verdict is not null")
    failures: list[str] = []
    for record in manifest["artifacts"]:
        path = output_root / record["path"]
        if not path.is_file() or path.is_symlink():
            failures.append(f"missing regular artifact: {record['path']}")
            continue
        if path.stat().st_size != int(record["bytes"]):
            failures.append(f"byte drift: {record['path']}")
        elif sha256_file(path) != record["sha256"]:
            failures.append(f"hash drift: {record['path']}")
    technical = json.loads((output_root / "technical_return.json").read_text(encoding="utf-8"))
    if technical.get("scientific_verdict", "missing") is not None:
        failures.append("technical_return scientific_verdict is not null")
    if technical.get("source_authority_decision", "missing") is not None:
        failures.append("source authority decision was emitted")
    if technical.get("fusion_performed") is not False:
        failures.append("fusion_performed must remain false")
    if technical.get("gaussian_optimization_performed") is not False:
        failures.append("gaussian_optimization_performed must remain false")
    if technical.get("source_relation_class_used") != "DISPLAY_ONLY":
        failures.append("source relation class use is not DISPLAY_ONLY")
    if technical.get("surface_patch_used") != "DISPLAY_ONLY":
        failures.append("surface patch use is not DISPLAY_ONLY")
    overlay_gate = technical.get("relation_patch_overlay_visibility_gate", {})
    if overlay_gate.get("changes_source_zbuffers_or_metrics") is not False:
        failures.append("relation/patch overlay changed source z-buffer/metric contract")
    if technical.get("prohibited_inputs_accessed") != []:
        failures.append("prohibited input access is non-empty")
    expected_roles = [row["role"].lower() for row in cfg["inputs"]["selected_views"]]
    for role in expected_roles:
        for filename in (
            "current_rgb.png", "source_independent_projections.npz", "comparison_panel.png",
            "edge_comparison_panel.png", "relation_patch_projection_panel.png", "metrics.json",
        ):
            if not (output_root / "views" / role / filename).is_file():
                failures.append(f"missing view output: {role}/{filename}")
        metrics_path = output_root / "views" / role / "metrics.json"
        if metrics_path.is_file():
            metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
            overlay = metrics.get("relation_patch_overlay", {})
            if metrics.get("source_relation_class_used") != "DISPLAY_ONLY":
                failures.append(f"source relation class use drift: {role}")
            if metrics.get("surface_patch_used") != "DISPLAY_ONLY":
                failures.append(f"surface patch use drift: {role}")
            if overlay.get("changes_source_zbuffers_or_metrics") is not False:
                failures.append(f"overlay/source metric separation drift: {role}")
            if overlay.get("source_authority_decision", "missing") is not None:
                failures.append(f"overlay emitted a source authority decision: {role}")
            if int(overlay.get("visibility_gated_cores", 0)) <= 0:
                failures.append(f"overlay contains no visibility-gated cores: {role}")
    if failures:
        raise RuntimeError("output validation failed: " + "; ".join(failures))
    receipt = {
        "schema": "jointbuildgs.phd.mvs_als_current_view_render.validation.v1",
        "task_id": cfg["task_id"],
        "status": "PASS",
        "validated_at": utc_now(),
        "artifact_count": len(manifest["artifacts"]),
        "artifact_manifest_sha256": sha256_file(manifest_path),
        "checks": {
            "artifact_hashes": "PASS",
            "three_frozen_views": "PASS",
            "source_independent_raw_and_proxy_outputs": "PASS",
            "relation_patch_display_only_overlay": "PASS",
            "own_source_raw_z_visibility_gate": "PASS",
            "relation_patch_overlay_does_not_change_source_metrics": "PASS",
            "no_source_authority_decision": "PASS",
            "no_fusion_or_gaussian_optimization": "PASS",
            "prohibited_inputs_accessed_empty": "PASS",
            "scientific_verdict_null": "PASS",
        },
        "scientific_verdict": None,
    }
    atomic_json(output_root / "validation_receipt.json", receipt)
    return receipt


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("run-and-validate", "validate"))
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--repo-root", type=Path, default=REPO)
    parser.add_argument("--artifact-root", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = load_config(args.config)
    artifact_root = args.artifact_root or Path(os.environ.get("JBGS_ARTIFACT_ROOT", cfg["artifact_root"]))
    if args.command == "run-and-validate":
        output = render(args.config, args.repo_root, artifact_root)
        receipt = json.loads((output / "validation_receipt.json").read_text(encoding="utf-8"))
    else:
        output = artifact_root / cfg["output_relative_root"]
        receipt = validate_output(cfg, output)
    print(json.dumps({"output_root": str(output), **receipt}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
