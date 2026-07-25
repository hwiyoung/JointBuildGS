#!/usr/bin/env python3
"""FUS-W1 section-3 laser seed and supervision preparation.

This command consumes the human-adopted, corrected COLMAP publication and the
registered Gate-A-v2 PASS.  It prepares one target or the complete core cohort:

* an un-downsampled class-6 target roof plus class-2 20 m ground-context seed;
* visibility-aware image RGB without removing points that receive no sample;
* independent class-6/class-2 2.5D TIN depth, normal, and valid masks;
* a directly consumable ``ColmapDataset`` root using the selected 10..30 views.

It never starts learning, point-cloud readout, Roofer, or scoring.  Corrected
poses are consumed as published; no alignment transform or geoid correction is
applied to a pose in this command.  Per-building manifests and then the stable
run manifest are written last.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import struct
import subprocess
import sys
from typing import Any, Iterable, Mapping, Sequence
import zipfile

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp")
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

import numpy as np
from PIL import Image as PILImage
from PIL import ImageDraw


REPO = Path(__file__).resolve().parents[3]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from projection_datum import (  # noqa: E402
    base_to_canonical_points,
    canonical_to_base_points,
)
from src.stage2.colmap_io import (  # noqa: E402
    CAMERA_MODEL_NAMES,
    Camera,
    Image as ColmapImage,
    read_cameras_bin,
    read_images_bin,
    read_points3d_bin,
)


DEFAULT_CONFIG = (
    REPO / "phases/p2-gsjso/configs/fusion_w1_preprocess_v1_20260725.json"
)
BUILDING_SCHEMA = "jointbuildgs.fusion_w1.preprocess_building.v1"
RUN_SCHEMA = "jointbuildgs.fusion_w1.preprocess_run.v1"
CONFIG_SCHEMA = "jointbuildgs.fusion_w1.preprocess.config.v1"
SCREEN_RASTER_MAX_BBOX_SAMPLES = 1_000_000
SCREEN_TRIANGLE_DENOMINATOR_EPS = 1.0e-12


class PreprocessError(RuntimeError):
    """Fail-closed input, geometry, or publication error."""


@dataclass(frozen=True)
class Target:
    building_id: str
    processing_order: int
    tier: str
    cohort: str
    queue_status: str
    cohort_resolution_status: str


@dataclass(frozen=True)
class SelectedView:
    selection_order: int
    image: ColmapImage
    camera: Camera
    class6_inframe_n: int
    class6_visible_n: int
    frame_radius: float
    nadir_deg: float
    azimuth_bin: int


@dataclass(frozen=True)
class Tin:
    vertices: np.ndarray
    simplices: np.ndarray
    normals_world: np.ndarray
    stats: dict[str, int | float]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def repo_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO / path


def relative(path: str | Path) -> str:
    value = Path(path).resolve()
    try:
        return str(value.relative_to(REPO.resolve()))
    except ValueError:
        return str(value)


def sha256_file(path: str | Path, block_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json_sha256(payload: Any) -> str:
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def load_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(repo_path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise PreprocessError(f"JSON root is not an object: {path}")
    return value


def fsync_parent(path: Path) -> None:
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    fsync_parent(path)


def atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    atomic_bytes(
        path,
        (
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8"),
    )


def format_csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (bool, np.bool_)):
        return "true" if bool(value) else "false"
    if isinstance(value, (float, np.floating)):
        number = float(value)
        return "" if not math.isfinite(number) else f"{number:.12f}"
    return str(value)


def atomic_csv(
    path: Path, rows: Sequence[Mapping[str, Any]], fields: Sequence[str]
) -> None:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream,
        fieldnames=list(fields),
        extrasaction="ignore",
        lineterminator="\n",
    )
    writer.writeheader()
    for row in rows:
        writer.writerow({key: format_csv_value(row.get(key)) for key in fields})
    atomic_bytes(path, stream.getvalue().encode("utf-8"))


def npy_bytes(array: np.ndarray) -> bytes:
    stream = io.BytesIO()
    np.lib.format.write_array(stream, np.asarray(array), allow_pickle=False)
    return stream.getvalue()


def atomic_npy(path: Path, array: np.ndarray) -> None:
    atomic_bytes(path, npy_bytes(np.asarray(array)))


def deterministic_npz_bytes(arrays: Mapping[str, np.ndarray]) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(
        stream, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        for key in sorted(arrays):
            info = zipfile.ZipInfo(
                f"{key}.npy", date_time=(1980, 1, 1, 0, 0, 0)
            )
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(
                info,
                npy_bytes(np.asarray(arrays[key])),
                compress_type=zipfile.ZIP_DEFLATED,
                compresslevel=9,
            )
    return stream.getvalue()


def atomic_npz(path: Path, arrays: Mapping[str, np.ndarray]) -> None:
    atomic_bytes(path, deterministic_npz_bytes(arrays))


def import_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise PreprocessError(f"cannot import helper: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def require_docker() -> None:
    if not Path("/.dockerenv").exists():
        raise PreprocessError("FUS-W1 preprocessing must run in pinned Docker")


def git(*arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=REPO,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if check and completed.returncode:
        raise PreprocessError(
            f"git {' '.join(arguments)} failed: {completed.stderr.strip()}"
        )
    return completed


def verify_method_lock(config: Mapping[str, Any]) -> dict[str, Any]:
    branch = git("branch", "--show-current").stdout.strip()
    if branch != config["branch"]:
        raise PreprocessError(f"branch {branch!r} != {config['branch']!r}")
    required = [
        *config["implementation_files"],
        config["inputs"]["r1_manifest"],
        config["inputs"]["r2_manifest"],
    ]
    records: list[dict[str, Any]] = []
    for item in required:
        path = repo_path(item)
        if not path.is_file():
            raise PreprocessError(f"required committed input missing: {item}")
        tracked = git("ls-files", "--error-unmatch", item, check=False)
        if tracked.returncode:
            raise PreprocessError(f"required method/input not tracked: {item}")
        difference = git("diff", "--quiet", "HEAD", "--", item, check=False)
        if difference.returncode:
            raise PreprocessError(f"required method/input differs from HEAD: {item}")
        records.append({"path": item, "sha256": sha256_file(path)})
    return {
        "branch": branch,
        "head": git("rev-parse", "HEAD").stdout.strip(),
        "required_files": records,
    }


def load_config(path: Path) -> dict[str, Any]:
    config = load_json(path)
    if config.get("schema") != CONFIG_SCHEMA:
        raise PreprocessError("unexpected preprocessing config schema")
    corrected_hash = config["r1_contract"]["corrected_images_sha256"]
    expected_namespace = f"pose_{corrected_hash[:16]}"
    if config["outputs"]["cache_namespace"] != expected_namespace:
        raise PreprocessError("cache namespace is not derived from pose hash")
    if config["subset_contract"]["downsample_default"] is not False:
        raise PreprocessError("default seed downsampling must remain disabled")
    minimum = int(config["view_selection"]["minimum_views"])
    maximum = int(config["view_selection"]["maximum_views"])
    if not 10 <= minimum <= maximum <= 30:
        raise PreprocessError("view count contract must remain within 10..30")
    return config


def verify_input_hashes(config: Mapping[str, Any]) -> dict[str, str]:
    observed: dict[str, str] = {}
    for logical, expected in config["input_sha256"].items():
        path = repo_path(logical)
        if not path.is_file():
            raise PreprocessError(f"locked input missing: {logical}")
        actual = sha256_file(path)
        if actual != expected:
            raise PreprocessError(
                f"locked input SHA drift: {logical}: {actual} != {expected}"
            )
        observed[logical] = actual
    return observed


def validate_authorization(
    config: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    r1 = load_json(config["inputs"]["r1_manifest"])
    contract1 = config["r1_contract"]
    for key in ("schema", "status", "derived_sparse", "image_count"):
        if r1.get(key) != contract1[key]:
            raise PreprocessError(f"R1 contract mismatch at {key}")
    if int(r1.get("transform_application_count", -1)) != int(
        contract1["transform_application_count"]
    ):
        raise PreprocessError("R1 transform application count is not one")
    if (
        r1.get("derived_sha256", {}).get("images.bin")
        != contract1["corrected_images_sha256"]
    ):
        raise PreprocessError("R1 corrected images.bin hash mismatch")
    if r1.get("source_pose_modified") is not False:
        raise PreprocessError("R1 source pose immutability declaration missing")
    if r1.get("als_source_modified") is not False:
        raise PreprocessError("R1 ALS immutability declaration missing")
    r2 = load_json(config["inputs"]["r2_manifest"])
    contract2 = config["r2_contract"]
    for key in ("schema", "status", "gate_a_version"):
        if r2.get(key) != contract2[key]:
            raise PreprocessError(f"R2 contract mismatch at {key}")
    slots = r2.get("gate_slots", {})
    for key in (
        "population_n",
        "core_population_n",
        "core_capable_matched_median_le_0p3_n",
        "numeric_source_role",
    ):
        if slots.get(key) != contract2[key]:
            raise PreprocessError(f"R2 gate slot mismatch at {key}")
    if slots.get("status") != "PASS":
        raise PreprocessError("Gate A v2 is not PASS")
    r2_r1 = r2.get("r1_pose_consumer", {})
    if r2_r1.get("manifest_sha256") != sha256_file(
        repo_path(config["inputs"]["r1_manifest"])
    ):
        raise PreprocessError("R2 does not bind the current R1 manifest")
    return r1, r2


def canonical_building_id(value: Any) -> str:
    text = str(value).strip()
    if not text:
        raise PreprocessError("empty building id")
    return text if text.startswith("DEBY_LOD2_") else f"DEBY_LOD2_{text}"


def load_targets(path: Path) -> list[Target]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        required = {
            "building_id",
            "processing_order",
            "tier",
            "cohort",
            "queue_status",
            "cohort_resolution_status",
        }
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise PreprocessError("w1_targets.csv header contract mismatch")
        rows = list(reader)
    output: list[Target] = []
    seen: set[str] = set()
    for row in rows:
        target = Target(
            building_id=canonical_building_id(row["building_id"]),
            processing_order=int(row["processing_order"]),
            tier=str(row["tier"]),
            cohort=str(row["cohort"]),
            queue_status=str(row["queue_status"]),
            cohort_resolution_status=str(row["cohort_resolution_status"]),
        )
        if target.building_id in seen:
            raise PreprocessError(f"duplicate target: {target.building_id}")
        seen.add(target.building_id)
        output.append(target)
    output.sort(key=lambda item: (item.processing_order, item.building_id))
    if len(output) != 178:
        raise PreprocessError(f"target population {len(output)} != 178")
    core = [target for target in output if target.cohort == "core"]
    if len(core) != 28:
        raise PreprocessError(f"core target population {len(core)} != 28")
    return output


def points_within_polygon_buffer(
    points_xy: np.ndarray,
    ring_xy: np.ndarray,
    buffer_m: float,
    *,
    chunk_size: int = 65536,
) -> np.ndarray:
    """Exact point-to-polygon buffer membership without altering point rows."""

    from matplotlib.path import Path as MplPath

    points = np.asarray(points_xy, dtype=np.float64)
    ring = np.asarray(ring_xy, dtype=np.float64)
    if points.ndim != 2 or points.shape[1] != 2:
        raise ValueError("points_xy must be Nx2")
    if ring.ndim != 2 or ring.shape[1] != 2 or len(ring) < 4:
        raise ValueError("ring_xy must be a closed polygon ring")
    if buffer_m < 0:
        raise ValueError("buffer must be non-negative")
    if not np.allclose(ring[0], ring[-1]):
        ring = np.vstack([ring, ring[0]])
    inside = MplPath(ring, closed=True).contains_points(points, radius=1.0e-10)
    if buffer_m == 0 or len(points) == 0:
        return inside
    threshold2 = float(buffer_m) ** 2
    output = inside.copy()
    starts = ring[:-1]
    vectors = ring[1:] - ring[:-1]
    lengths2 = np.einsum("ij,ij->i", vectors, vectors)
    valid_segments = lengths2 > 1.0e-18
    starts = starts[valid_segments]
    vectors = vectors[valid_segments]
    lengths2 = lengths2[valid_segments]
    for begin in range(0, len(points), chunk_size):
        end = min(len(points), begin + chunk_size)
        pending_local = np.flatnonzero(~output[begin:end])
        if not len(pending_local):
            continue
        query = points[begin:end][pending_local]
        minimum = np.full(len(query), np.inf, dtype=np.float64)
        for start, vector, length2 in zip(starts, vectors, lengths2):
            delta = query - start
            fraction = np.clip((delta @ vector) / length2, 0.0, 1.0)
            nearest = start + fraction[:, None] * vector
            distance2 = np.einsum(
                "ij,ij->i", query - nearest, query - nearest
            )
            minimum = np.minimum(minimum, distance2)
        accepted = pending_local[minimum <= threshold2 + 1.0e-12]
        output[begin + accepted] = True
    return output


def deterministic_cap(points: np.ndarray, cap: int) -> np.ndarray:
    if len(points) <= cap:
        return points
    return points[np.linspace(0, len(points) - 1, cap).astype(np.int64)]


def visibility_mask(
    uv: np.ndarray,
    camera_depth: np.ndarray,
    width: int,
    height: int,
    tolerance_m: float,
) -> np.ndarray:
    """Integer-pixel z-buffer with a small surface-depth tolerance."""

    pixels = np.asarray(uv, dtype=np.float64)
    depth = np.asarray(camera_depth, dtype=np.float64)
    valid = (
        np.isfinite(pixels).all(axis=1)
        & np.isfinite(depth)
        & (depth > 1.0)
        & (pixels[:, 0] >= 0)
        & (pixels[:, 0] < width)
        & (pixels[:, 1] >= 0)
        & (pixels[:, 1] < height)
    )
    output = np.zeros(len(depth), dtype=bool)
    indices = np.flatnonzero(valid)
    if not len(indices):
        return output
    x = np.floor(pixels[indices, 0]).astype(np.int64)
    y = np.floor(pixels[indices, 1]).astype(np.int64)
    linear = y * int(width) + x
    order = np.lexsort((indices, depth[indices], linear))
    ordered_indices = indices[order]
    ordered_linear = linear[order]
    ordered_depth = depth[ordered_indices]
    starts = np.r_[0, np.flatnonzero(ordered_linear[1:] != ordered_linear[:-1]) + 1]
    ends = np.r_[starts[1:], len(ordered_indices)]
    for start, end in zip(starts, ends):
        minimum = ordered_depth[start]
        winners = ordered_indices[start:end][
            ordered_depth[start:end] <= minimum + float(tolerance_m)
        ]
        output[winners] = True
    return output


def project_canonical(
    gate: Any,
    points_canonical: np.ndarray,
    image: ColmapImage,
    camera: Camera,
) -> tuple[np.ndarray, np.ndarray]:
    camera_xyz = (
        image.R() @ np.asarray(points_canonical, dtype=np.float64).T
    ).T + image.tvec
    depth = camera_xyz[:, 2]
    uv = np.full((len(camera_xyz), 2), np.nan, dtype=np.float64)
    front = depth > 1.0
    if np.any(front):
        uv[front] = gate.project_camera_points(camera, camera_xyz[front])
    return uv, depth


def rasterize_target_photo_support_mask(
    gate: Any,
    footprint_base_xy: np.ndarray,
    class6_canonical: np.ndarray,
    image: ColmapImage,
    camera: Camera,
    scene_reference: Mapping[str, Any],
    coordinate: Mapping[str, Any],
) -> tuple[np.ndarray, dict[str, Any]]:
    """Reproduce the locked target-footprint photo-control mask.

    The quality-axis control masks photo loss outside the selected building
    footprint. The footprint supplies XY only; its projection height comes
    from the actual class-6 ALS seed using the existing q80-upper-median
    convention. Buffered class-2 ground remains depth/normal supervision but
    is deliberately excluded from the photo mask.
    """

    ring = np.asarray(footprint_base_xy, dtype=np.float64)
    roof = np.asarray(class6_canonical, dtype=np.float64)
    if ring.ndim != 2 or ring.shape[1] != 2 or len(ring) < 4:
        raise PreprocessError("photo-support footprint must be a polygon ring")
    if roof.ndim != 2 or roof.shape[1] != 3 or len(roof) == 0:
        raise PreprocessError("photo-support height requires class-6 ALS points")
    if not np.allclose(ring[0], ring[-1]):
        ring = np.vstack([ring, ring[0]])
    q80 = float(np.quantile(roof[:, 2], 0.80))
    upper = roof[roof[:, 2] >= q80, 2]
    if len(upper) == 0:
        raise PreprocessError("photo-support class-6 upper-height sample is empty")
    roof_z = float(np.median(upper))
    ring_base = np.column_stack([ring, np.zeros(len(ring), dtype=np.float64)])
    ring_canonical = base_to_canonical_points(
        ring_base,
        scene_reference,
        input_datum=coordinate["base_vertical_datum"],
        geoid_m=float(coordinate["orthometric_to_ellipsoidal_geoid_m"]),
    )
    ring_canonical[:, 2] = roof_z
    uv, depth = project_canonical(gate, ring_canonical, image, camera)
    if not np.isfinite(uv).all() or np.any(depth <= 1.0):
        raise PreprocessError(
            f"target footprint cannot be projected in selected view {image.name}"
        )
    canvas = PILImage.new("1", (int(camera.width), int(camera.height)), color=0)
    draw = ImageDraw.Draw(canvas)
    draw.polygon(
        [(float(point[0]), float(point[1])) for point in uv[:-1]],
        fill=1,
    )
    mask = np.asarray(canvas, dtype=np.bool_)
    if not bool(mask.any()):
        raise PreprocessError(
            f"empty target-footprint photo-support mask: {image.name}"
        )
    return mask, {
        "method": "target_GroundSurface_XY_at_ALS_class6_q80_upper_median_height",
        "class6_height_source_points_n": int(len(roof)),
        "class6_q80_canonical_z_m": q80,
        "projection_canonical_z_m": roof_z,
        "true_pixels_n": int(mask.sum()),
        "true_pixel_fraction": float(mask.mean()),
        "buffered_class2_included": False,
        "non_target_class6_included": False,
    }


def select_views(
    gate: Any,
    class6_base: np.ndarray,
    cameras: Mapping[int, Camera],
    images_by_name: Mapping[str, ColmapImage],
    scene_reference: Mapping[str, Any],
    config: Mapping[str, Any],
) -> list[SelectedView]:
    contract = config["view_selection"]
    coordinate = config["coordinate_contract"]
    sample = deterministic_cap(
        class6_base, int(contract["projection_point_cap_for_ranking_only"])
    )
    sample_canonical = base_to_canonical_points(
        sample,
        scene_reference,
        input_datum=coordinate["base_vertical_datum"],
        geoid_m=float(coordinate["orthometric_to_ellipsoidal_geoid_m"]),
    )
    target = np.median(sample_canonical, axis=0)
    bin_count = int(contract["azimuth_bins"])
    candidates: dict[int, list[dict[str, Any]]] = {
        index: [] for index in range(bin_count)
    }
    for name, image in sorted(images_by_name.items()):
        camera = cameras.get(image.camera_id)
        if camera is None:
            raise PreprocessError(f"missing camera {image.camera_id}: {name}")
        uv, depth = project_canonical(gate, sample_canonical, image, camera)
        inframe = (
            np.isfinite(uv).all(axis=1)
            & (depth > 1.0)
            & (uv[:, 0] >= 0)
            & (uv[:, 0] < camera.width)
            & (uv[:, 1] >= 0)
            & (uv[:, 1] < camera.height)
        )
        count = int(inframe.sum())
        if count < int(contract["minimum_class6_inframe_points"]):
            continue
        visible = visibility_mask(
            uv,
            depth,
            camera.width,
            camera.height,
            float(config["rgb_sampling"]["zbuffer_absolute_tolerance_m"]),
        )
        center = -image.R().T @ image.tvec
        ray = center - target
        norm = float(np.linalg.norm(ray))
        nadir = (
            math.degrees(
                math.acos(min(1.0, abs(float(ray[2])) / max(norm, 1.0e-12)))
            )
            if norm > 1.0e-12
            else 0.0
        )
        angle = math.atan2(float(ray[1]), float(ray[0]))
        azimuth_bin = int(
            math.floor(
                ((angle + 2.0 * math.pi) % (2.0 * math.pi))
                / (2.0 * math.pi / bin_count)
            )
        ) % bin_count
        q = uv[inframe]
        radius = float(
            np.max(
                np.sqrt(
                    ((q[:, 0] - 0.5 * camera.width) / (0.5 * camera.width))
                    ** 2
                    + (
                        (q[:, 1] - 0.5 * camera.height)
                        / (0.5 * camera.height)
                    )
                    ** 2
                )
            )
        )
        candidates[azimuth_bin].append(
            {
                "rank": (-int(visible.sum()), radius, nadir, name),
                "image": image,
                "camera": camera,
                "inframe": count,
                "visible": int(visible.sum()),
                "radius": radius,
                "nadir": nadir,
                "bin": azimuth_bin,
            }
        )
    for values in candidates.values():
        values.sort(key=lambda value: value["rank"])
    chosen: list[dict[str, Any]] = []
    maximum = int(contract["maximum_views"])
    while len(chosen) < maximum:
        added = False
        for bin_index in range(bin_count):
            values = candidates[bin_index]
            if values and len(chosen) < maximum:
                chosen.append(values.pop(0))
                added = True
        if not added:
            break
    minimum = int(contract["minimum_views"])
    if len(chosen) < minimum:
        raise PreprocessError(
            f"only {len(chosen)} corrected-pose views; required {minimum}"
        )
    return [
        SelectedView(
            selection_order=index,
            image=value["image"],
            camera=value["camera"],
            class6_inframe_n=value["inframe"],
            class6_visible_n=value["visible"],
            frame_radius=value["radius"],
            nadir_deg=value["nadir"],
            azimuth_bin=value["bin"],
        )
        for index, value in enumerate(chosen, 1)
    ]


def bilinear_rgb(image: np.ndarray, uv: np.ndarray) -> np.ndarray:
    height, width = image.shape[:2]
    x = np.clip(uv[:, 0], 0.0, width - 1.0)
    y = np.clip(uv[:, 1], 0.0, height - 1.0)
    x0 = np.floor(x).astype(np.int64)
    y0 = np.floor(y).astype(np.int64)
    x1 = np.minimum(x0 + 1, width - 1)
    y1 = np.minimum(y0 + 1, height - 1)
    wx = x - x0
    wy = y - y0
    return (
        image[y0, x0] * ((1.0 - wx) * (1.0 - wy))[:, None]
        + image[y0, x1] * (wx * (1.0 - wy))[:, None]
        + image[y1, x0] * ((1.0 - wx) * wy)[:, None]
        + image[y1, x1] * (wx * wy)[:, None]
    )


def sample_seed_rgb(
    gate: Any,
    points_canonical: np.ndarray,
    selected: Sequence[SelectedView],
    image_paths: Mapping[str, Path],
    config: Mapping[str, Any],
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    sums = np.zeros((len(points_canonical), 3), dtype=np.float64)
    counts = np.zeros(len(points_canonical), dtype=np.uint16)
    per_view: list[dict[str, Any]] = []
    tolerance = float(config["rgb_sampling"]["zbuffer_absolute_tolerance_m"])
    for view in selected:
        uv, depth = project_canonical(
            gate, points_canonical, view.image, view.camera
        )
        visible = visibility_mask(
            uv, depth, view.camera.width, view.camera.height, tolerance
        )
        indices = np.flatnonzero(visible)
        path = image_paths[view.image.name]
        with PILImage.open(path) as source:
            if source.size != (view.camera.width, view.camera.height):
                raise PreprocessError(
                    f"image/COLMAP size mismatch: {view.image.name}"
                )
            pixels = np.asarray(source.convert("RGB"), dtype=np.float64)
        if len(indices):
            values = bilinear_rgb(pixels, uv[indices])
            sums[indices] += values
            if np.any(counts[indices] == np.iinfo(np.uint16).max):
                raise PreprocessError("RGB sample-count uint16 overflow")
            counts[indices] += 1
        per_view.append(
            {
                "image_name": view.image.name,
                "visible_seed_points_n": int(len(indices)),
                "image_sha256": sha256_file(path),
            }
        )
    default = np.asarray(
        config["rgb_sampling"]["default_unsampled_rgb"], dtype=np.float64
    )
    rgb = np.broadcast_to(default, sums.shape).copy()
    sampled = counts > 0
    rgb[sampled] = sums[sampled] / counts[sampled, None]
    rgb8 = np.clip(np.rint(rgb), 0, 255).astype(np.uint8)
    return rgb8, counts, {
        "method": config["rgb_sampling"]["method"],
        "sampled_points_n": int(sampled.sum()),
        "unsampled_points_n": int((~sampled).sum()),
        "unsampled_points_retained": True,
        "sample_count_min": int(counts.min()) if len(counts) else 0,
        "sample_count_median": float(np.median(counts)) if len(counts) else 0.0,
        "sample_count_max": int(counts.max()) if len(counts) else 0,
        "per_view": per_view,
    }


def unique_xy_median_z(points: np.ndarray) -> np.ndarray:
    values = np.asarray(points, dtype=np.float64)
    order = np.lexsort((values[:, 2], values[:, 1], values[:, 0]))
    ordered = values[order]
    starts = np.r_[
        0,
        np.flatnonzero(
            (ordered[1:, 0] != ordered[:-1, 0])
            | (ordered[1:, 1] != ordered[:-1, 1])
        )
        + 1,
    ]
    ends = np.r_[starts[1:], len(ordered)]
    output = np.empty((len(starts), 3), dtype=np.float64)
    for index, (start, end) in enumerate(zip(starts, ends)):
        output[index, :2] = ordered[start, :2]
        output[index, 2] = np.median(ordered[start:end, 2])
    return output


def build_tin(
    points_canonical: np.ndarray,
    *,
    maximum_xy_edge_m: float,
    maximum_slope_deg: float,
    minimum_xy_triangle_area_m2: float,
) -> Tin:
    from matplotlib.tri import Triangulation

    vertices = unique_xy_median_z(points_canonical)
    if len(vertices) < 3:
        raise PreprocessError("TIN requires at least three unique XY points")
    try:
        triangulation = Triangulation(vertices[:, 0], vertices[:, 1])
    except Exception as exc:
        raise PreprocessError(f"Delaunay TIN failed: {exc}") from exc
    simplices = np.asarray(triangulation.triangles, dtype=np.int64)
    triangle = vertices[simplices]
    edge01 = triangle[:, 1] - triangle[:, 0]
    edge02 = triangle[:, 2] - triangle[:, 0]
    edge12 = triangle[:, 2] - triangle[:, 1]
    xy_lengths = np.stack(
        [
            np.linalg.norm(edge01[:, :2], axis=1),
            np.linalg.norm(edge02[:, :2], axis=1),
            np.linalg.norm(edge12[:, :2], axis=1),
        ],
        axis=1,
    )
    maximum_edge = xy_lengths.max(axis=1)
    cross = np.cross(edge01, edge02)
    norm = np.linalg.norm(cross, axis=1)
    area_xy = 0.5 * np.abs(
        edge01[:, 0] * edge02[:, 1] - edge01[:, 1] * edge02[:, 0]
    )
    normals = np.zeros_like(cross)
    nonzero = norm > 1.0e-12
    normals[nonzero] = cross[nonzero] / norm[nonzero, None]
    flip = normals[:, 2] < 0
    normals[flip] *= -1.0
    slope = np.degrees(
        np.arctan2(
            np.linalg.norm(normals[:, :2], axis=1),
            np.maximum(np.abs(normals[:, 2]), 1.0e-12),
        )
    )
    area_ok = area_xy >= float(minimum_xy_triangle_area_m2)
    edge_ok = maximum_edge <= float(maximum_xy_edge_m)
    slope_ok = slope <= float(maximum_slope_deg)
    finite = np.isfinite(normals).all(axis=1) & nonzero
    valid = area_ok & edge_ok & slope_ok & finite
    if not np.any(valid):
        raise PreprocessError(
            "TIN has no valid triangles after area/edge/slope masking"
        )
    return Tin(
        vertices=vertices,
        simplices=simplices[valid],
        normals_world=normals[valid],
        stats={
            "source_points_n": int(len(points_canonical)),
            "unique_xy_vertices_n": int(len(vertices)),
            "triangles_initial_n": int(len(simplices)),
            "triangles_valid_n": int(valid.sum()),
            "triangles_dropped_small_area_n": int((~area_ok).sum()),
            "triangles_dropped_long_edge_n": int((area_ok & ~edge_ok).sum()),
            "triangles_dropped_steep_n": int(
                (area_ok & edge_ok & ~slope_ok).sum()
            ),
            "triangles_dropped_nonfinite_n": int((~finite).sum()),
            "maximum_xy_edge_m": float(maximum_xy_edge_m),
            "maximum_slope_deg": float(maximum_slope_deg),
            "minimum_xy_triangle_area_m2": float(minimum_xy_triangle_area_m2),
        },
    )


def rasterize_tin(
    gate: Any,
    tin: Tin,
    image: ColmapImage,
    camera: Camera,
    *,
    edge_margin: float,
    erosion_pixels: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, int]]:
    height = int(camera.height)
    width = int(camera.width)
    if not 0.0 <= float(edge_margin) < (1.0 / 3.0):
        raise ValueError("edge_margin must be in [0, 1/3)")
    if int(erosion_pixels) < 0:
        raise ValueError("erosion_pixels must be non-negative")
    pixel_count = height * width
    depth_flat = np.full(pixel_count, np.inf, dtype=np.float64)
    owner_flat = np.full(pixel_count, len(tin.simplices), dtype=np.int64)
    camera_xyz = (image.R() @ tin.vertices.T).T + image.tvec
    camera_depth = camera_xyz[:, 2]
    uv = np.full((len(tin.vertices), 2), np.nan, dtype=np.float64)
    front = camera_depth > 1.0
    if np.any(front):
        uv[front] = gate.project_camera_points(camera, camera_xyz[front])
    triangle_front = np.all(front[tin.simplices], axis=1)
    triangle_finite = np.isfinite(uv[tin.simplices]).all(axis=(1, 2))
    usable_triangles = triangle_front & triangle_finite
    triangle_has_candidate = np.zeros(len(tin.simplices), dtype=bool)
    candidate_pixels = 0
    screen_degenerate_n = 0
    screen_offframe_n = 0
    raster_chunks_n = 0
    maximum_chunk_samples_n = 0
    if np.any(usable_triangles):
        usable_ids = np.flatnonzero(usable_triangles)
        triangle_uv = uv[tin.simplices[usable_ids]]
        x0 = triangle_uv[:, 0, 0]
        y0 = triangle_uv[:, 0, 1]
        x1 = triangle_uv[:, 1, 0]
        y1 = triangle_uv[:, 1, 1]
        x2 = triangle_uv[:, 2, 0]
        y2 = triangle_uv[:, 2, 1]
        denominator = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        nondegenerate = np.abs(denominator) > SCREEN_TRIANGLE_DENOMINATOR_EPS
        screen_degenerate_n = int((~nondegenerate).sum())
        usable_ids = usable_ids[nondegenerate]
        triangle_uv = triangle_uv[nondegenerate]
        denominator = denominator[nondegenerate]
        if len(usable_ids):
            minimum_x = np.min(triangle_uv[:, :, 0], axis=1)
            maximum_x = np.max(triangle_uv[:, :, 0], axis=1)
            minimum_y = np.min(triangle_uv[:, :, 1], axis=1)
            maximum_y = np.max(triangle_uv[:, :, 1], axis=1)
            overlaps_frame = (
                (maximum_x >= 0.5)
                & (minimum_x <= float(width) - 0.5)
                & (maximum_y >= 0.5)
                & (minimum_y <= float(height) - 0.5)
            )
            screen_offframe_n = int((~overlaps_frame).sum())
            usable_ids = usable_ids[overlaps_frame]
            denominator = denominator[overlaps_frame]
            minimum_x = minimum_x[overlaps_frame]
            maximum_x = maximum_x[overlaps_frame]
            minimum_y = minimum_y[overlaps_frame]
            maximum_y = maximum_y[overlaps_frame]
        if len(usable_ids):
            xmin = np.clip(np.floor(minimum_x), 0, width - 1).astype(np.int64)
            xmax = np.clip(np.ceil(maximum_x), 0, width - 1).astype(np.int64)
            ymin = np.clip(np.floor(minimum_y), 0, height - 1).astype(np.int64)
            ymax = np.clip(np.ceil(maximum_y), 0, height - 1).astype(np.int64)
            box_width = xmax - xmin + 1
            box_height = ymax - ymin + 1
            box_samples = box_width * box_height
            cursor = 0
            while cursor < len(usable_ids):
                end = cursor
                sample_count = 0
                while end < len(usable_ids):
                    next_count = int(box_samples[end])
                    if end > cursor and (
                        sample_count + next_count
                        > SCREEN_RASTER_MAX_BBOX_SAMPLES
                    ):
                        break
                    sample_count += next_count
                    end += 1
                    if sample_count >= SCREEN_RASTER_MAX_BBOX_SAMPLES:
                        break
                chunk_areas = box_samples[cursor:end]
                starts = np.cumsum(
                    np.r_[np.int64(0), chunk_areas[:-1]], dtype=np.int64
                )
                local_triangle = np.repeat(
                    np.arange(end - cursor, dtype=np.int64), chunk_areas
                )
                local_sample = (
                    np.arange(sample_count, dtype=np.int64)
                    - starts[local_triangle]
                )
                chunk_width = box_width[cursor:end]
                sample_x_int = (
                    xmin[cursor:end][local_triangle]
                    + local_sample % chunk_width[local_triangle]
                )
                sample_y_int = (
                    ymin[cursor:end][local_triangle]
                    + local_sample // chunk_width[local_triangle]
                )
                triangle_id = usable_ids[cursor:end][local_triangle]
                sample_x = sample_x_int.astype(np.float64) + 0.5
                sample_y = sample_y_int.astype(np.float64) + 0.5
                q = uv[tin.simplices[triangle_id]]
                d = denominator[cursor:end][local_triangle]
                w0 = (
                    (q[:, 1, 1] - q[:, 2, 1]) * (sample_x - q[:, 2, 0])
                    + (q[:, 2, 0] - q[:, 1, 0]) * (sample_y - q[:, 2, 1])
                ) / d
                w1 = (
                    (q[:, 2, 1] - q[:, 0, 1]) * (sample_x - q[:, 2, 0])
                    + (q[:, 0, 0] - q[:, 2, 0]) * (sample_y - q[:, 2, 1])
                ) / d
                w2 = 1.0 - w0 - w1
                inside = (
                    (w0 >= float(edge_margin))
                    & (w1 >= float(edge_margin))
                    & (w2 >= float(edge_margin))
                )
                z = camera_depth[tin.simplices[triangle_id]]
                inverse_depth = w0 / z[:, 0] + w1 / z[:, 1] + w2 / z[:, 2]
                good = inside & np.isfinite(inverse_depth) & (inverse_depth > 0.0)
                if np.any(good):
                    candidate_triangle = triangle_id[good]
                    candidate_depth = 1.0 / inverse_depth[good]
                    linear = (
                        sample_y_int[good] * width + sample_x_int[good]
                    )
                    triangle_has_candidate[candidate_triangle] = True
                    candidate_pixels += int(good.sum())
                    chunk_depth = np.full(pixel_count, np.inf, dtype=np.float64)
                    np.minimum.at(chunk_depth, linear, candidate_depth)
                    at_chunk_minimum = candidate_depth == chunk_depth[linear]
                    chunk_owner = np.full(
                        pixel_count, len(tin.simplices), dtype=np.int64
                    )
                    np.minimum.at(
                        chunk_owner,
                        linear[at_chunk_minimum],
                        candidate_triangle[at_chunk_minimum],
                    )
                    active = np.flatnonzero(chunk_owner < len(tin.simplices))
                    closer = chunk_depth[active] < depth_flat[active]
                    equal_but_earlier = (
                        (chunk_depth[active] == depth_flat[active])
                        & (chunk_owner[active] < owner_flat[active])
                    )
                    update = active[closer | equal_but_earlier]
                    depth_flat[update] = chunk_depth[update]
                    owner_flat[update] = chunk_owner[update]
                raster_chunks_n += 1
                maximum_chunk_samples_n = max(
                    maximum_chunk_samples_n, int(sample_count)
                )
                cursor = end
    valid_before = np.isfinite(depth_flat).reshape(height, width)
    depth = depth_flat.reshape(height, width).astype(np.float32)
    normal = np.zeros((height, width, 3), dtype=np.float32)
    owned = owner_flat < len(tin.simplices)
    normal.reshape(-1, 3)[owned] = tin.normals_world[
        owner_flat[owned]
    ].astype(np.float32)
    valid = valid_before.copy()
    for _ in range(int(erosion_pixels)):
        if not np.any(valid):
            break
        padded = np.pad(valid, 1, mode="constant", constant_values=False)
        eroded = np.ones_like(valid)
        for row_offset in range(3):
            for column_offset in range(3):
                eroded &= padded[
                    row_offset : row_offset + height,
                    column_offset : column_offset + width,
                ]
        valid = eroded
    depth[~valid] = 0.0
    normal[~valid] = 0.0
    return depth, normal, valid, {
        "triangles_projected_n": int(triangle_has_candidate.sum()),
        "candidate_pixel_writes_n": int(candidate_pixels),
        "valid_pixels_before_outer_edge_mask_n": int(valid_before.sum()),
        "valid_pixels_after_outer_edge_mask_n": int(valid.sum()),
        "outer_edge_masked_pixels_n": int(valid_before.sum() - valid.sum()),
        "triangles_front_finite_n": int(usable_triangles.sum()),
        "triangles_screen_degenerate_n": int(screen_degenerate_n),
        "triangles_screen_offframe_n": int(screen_offframe_n),
        "raster_chunks_n": int(raster_chunks_n),
        "maximum_chunk_bbox_samples_n": int(maximum_chunk_samples_n),
    }


def combine_supervision(
    depth6: np.ndarray,
    normal6: np.ndarray,
    valid6: np.ndarray,
    depth2: np.ndarray,
    normal2: np.ndarray,
    valid2: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    choose6 = valid6 & (~valid2 | (depth6 <= depth2))
    choose2 = valid2 & ~choose6
    valid = choose6 | choose2
    depth = np.zeros(depth6.shape, dtype=np.float32)
    normal = np.zeros(normal6.shape, dtype=np.float32)
    source_class = np.zeros(depth6.shape, dtype=np.uint8)
    depth[choose6] = depth6[choose6]
    depth[choose2] = depth2[choose2]
    normal[choose6] = normal6[choose6]
    normal[choose2] = normal2[choose2]
    source_class[choose6] = 6
    source_class[choose2] = 2
    return depth, normal, valid, source_class


def write_colmap_array(path: Path, array: np.ndarray) -> None:
    value = np.asarray(array, dtype=np.float32)
    if value.ndim not in {2, 3}:
        raise ValueError("COLMAP array must be HxW or HxWxC")
    height, width = value.shape[:2]
    channels = 1 if value.ndim == 2 else value.shape[2]
    header = f"{width}&{height}&{channels}&".encode("ascii")
    atomic_bytes(path, header + np.ascontiguousarray(value).tobytes(order="C"))


def write_cameras_bin(path: Path, cameras: Mapping[int, Camera]) -> None:
    stream = io.BytesIO()
    stream.write(struct.pack("<Q", len(cameras)))
    for camera_id in sorted(cameras):
        camera = cameras[camera_id]
        model_id, parameter_count = CAMERA_MODEL_NAMES[camera.model]
        params = np.asarray(camera.params, dtype=np.float64)
        if len(params) != parameter_count:
            raise PreprocessError(f"invalid camera parameter count: {camera.id}")
        stream.write(
            struct.pack(
                "<iiQQ",
                int(camera.id),
                int(model_id),
                int(camera.width),
                int(camera.height),
            )
        )
        stream.write(struct.pack("<" + "d" * parameter_count, *params.tolist()))
    atomic_bytes(path, stream.getvalue())


def write_images_bin(path: Path, images: Mapping[int, ColmapImage]) -> None:
    stream = io.BytesIO()
    stream.write(struct.pack("<Q", len(images)))
    for image_id in sorted(images):
        image = images[image_id]
        stream.write(struct.pack("<I", int(image.id)))
        stream.write(struct.pack("<dddd", *image.qvec.astype(float).tolist()))
        stream.write(struct.pack("<ddd", *image.tvec.astype(float).tolist()))
        stream.write(struct.pack("<I", int(image.camera_id)))
        stream.write(image.name.encode("utf-8") + b"\x00")
        stream.write(struct.pack("<Q", 0))
    atomic_bytes(path, stream.getvalue())


def write_points3d_bin(path: Path, xyzrgb: np.ndarray) -> None:
    values = np.asarray(xyzrgb)
    if values.ndim != 2 or values.shape[1] < 6 or len(values) == 0:
        raise PreprocessError("corrected sparse subset must be non-empty Nx6")
    stream = io.BytesIO()
    stream.write(struct.pack("<Q", len(values)))
    for point_id, row in enumerate(values, 1):
        stream.write(struct.pack("<Q", point_id))
        stream.write(struct.pack("<ddd", *map(float, row[:3])))
        stream.write(
            struct.pack(
                "<BBB",
                *np.clip(np.rint(row[3:6]), 0, 255).astype(np.uint8).tolist(),
            )
        )
        stream.write(struct.pack("<d", 0.0))
        stream.write(struct.pack("<Q", 0))
    atomic_bytes(path, stream.getvalue())


def write_seed_las(
    path: Path,
    xyz_base: np.ndarray,
    classification: np.ndarray,
    rgb8: np.ndarray,
) -> dict[str, Any]:
    try:
        import laspy
        from pyproj import CRS
    except ImportError as exc:
        raise PreprocessError("laspy and pyproj are required in tools image") from exc
    header = laspy.LasHeader(point_format=3, version="1.4")
    header.scales = np.asarray([0.001, 0.001, 0.001])
    header.offsets = np.floor(np.min(xyz_base, axis=0))
    header.add_crs(CRS.from_epsg(25832))
    las = laspy.LasData(header)
    las.x = xyz_base[:, 0]
    las.y = xyz_base[:, 1]
    las.z = xyz_base[:, 2]
    las.classification = classification.astype(np.uint8)
    las.red = rgb8[:, 0].astype(np.uint16) * 257
    las.green = rgb8[:, 1].astype(np.uint16) * 257
    las.blue = rgb8[:, 2].astype(np.uint16) * 257
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    las.write(temporary)
    with temporary.open("rb+") as handle:
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    fsync_parent(path)
    check = laspy.read(path)
    observed = np.column_stack([check.x, check.y, check.z])
    maximum_error = float(np.max(np.abs(observed - xyz_base)))
    if maximum_error > 0.0005001:
        raise PreprocessError(f"LAS coordinate quantization error {maximum_error}")
    return {
        "point_format": 3,
        "version": "1.4",
        "scale_m": [0.001, 0.001, 0.001],
        "offset_m": header.offsets.astype(float).tolist(),
        "maximum_coordinate_roundtrip_error_m": maximum_error,
    }


def write_seed_ply(
    path: Path,
    xyz_canonical: np.ndarray,
    rgb8: np.ndarray,
    classification: np.ndarray,
) -> None:
    count = len(xyz_canonical)
    header = (
        "ply\n"
        "format binary_little_endian 1.0\n"
        f"element vertex {count}\n"
        "property float x\n"
        "property float y\n"
        "property float z\n"
        "property uchar red\n"
        "property uchar green\n"
        "property uchar blue\n"
        "property uchar classification\n"
        "end_header\n"
    ).encode("ascii")
    dtype = np.dtype(
        [
            ("x", "<f4"),
            ("y", "<f4"),
            ("z", "<f4"),
            ("red", "u1"),
            ("green", "u1"),
            ("blue", "u1"),
            ("classification", "u1"),
        ]
    )
    values = np.empty(count, dtype=dtype)
    values["x"] = xyz_canonical[:, 0]
    values["y"] = xyz_canonical[:, 1]
    values["z"] = xyz_canonical[:, 2]
    values["red"] = rgb8[:, 0]
    values["green"] = rgb8[:, 1]
    values["blue"] = rgb8[:, 2]
    values["classification"] = classification
    atomic_bytes(path, header + values.tobytes(order="C"))


def safe_image_path(image_dir: Path, name: str) -> Path:
    path = (image_dir / name).resolve()
    try:
        path.relative_to(image_dir.resolve())
    except ValueError as exc:
        raise PreprocessError(f"image name escapes source directory: {name}") from exc
    if not path.is_file():
        raise PreprocessError(f"training image missing: {name}")
    return path


def create_final_relative_symlink(
    staging_link: Path, final_link: Path, source: Path
) -> None:
    staging_link.parent.mkdir(parents=True, exist_ok=True)
    link_value = os.path.relpath(source.resolve(), start=final_link.parent.resolve())
    os.symlink(link_value, staging_link)


def collect_artifacts(
    staging_root: Path,
    final_root: Path,
    image_source_hashes: Mapping[str, str],
) -> tuple[dict[str, str], dict[str, str]]:
    hashes: dict[str, str] = {}
    kinds: dict[str, str] = {}
    for path in sorted(staging_root.rglob("*")):
        if path.name == "preprocess_manifest.json":
            continue
        final_path = final_root / path.relative_to(staging_root)
        logical = relative(final_path)
        if path.is_symlink():
            source_name = str(path.relative_to(staging_root / "images"))
            hashes[logical] = image_source_hashes[source_name]
            kinds[logical] = "relative_symlink_to_immutable_image"
        elif path.is_file():
            hashes[logical] = sha256_file(path)
            kinds[logical] = "file"
    return hashes, kinds


def verify_building_manifest(path: Path, corrected_pose_hash: str) -> dict[str, Any]:
    payload = load_json(path)
    if payload.get("schema") != BUILDING_SCHEMA or payload.get("status") != "PASSED":
        raise PreprocessError(f"invalid building preprocess manifest: {relative(path)}")
    if (
        payload.get("pose_binding", {}).get("corrected_images_sha256")
        != corrected_pose_hash
    ):
        raise PreprocessError("building preprocess pose-cache mismatch")
    for logical, expected in payload.get("artifact_sha256", {}).items():
        artifact = repo_path(logical)
        if not artifact.exists():
            raise PreprocessError(f"building artifact missing: {logical}")
        if sha256_file(artifact.resolve()) != expected:
            raise PreprocessError(f"building artifact SHA drift: {logical}")
    counts = payload["seed"]["classification_counts"]
    total = int(counts["2"]) + int(counts["6"])
    if total != int(payload["seed"]["output_points_n"]):
        raise PreprocessError("building seed class-count invariant failed")
    if payload["seed"]["downsample_applied"] is not False:
        raise PreprocessError("building seed unexpectedly downsampled")
    selected = payload["views"]["selected_names"]
    if not 10 <= len(selected) <= 30 or len(selected) != len(set(selected)):
        raise PreprocessError("building selected-view inventory invalid")
    return payload


def materialize_building(
    *,
    gate: Any,
    target: Target,
    footprint: np.ndarray,
    cloud: Any,
    ground_base: np.ndarray,
    cameras: Mapping[int, Camera],
    images_by_name: Mapping[str, ColmapImage],
    image_paths: Mapping[str, Path],
    corrected_sparse_points: np.ndarray,
    scene_reference: Mapping[str, Any],
    r1: Mapping[str, Any],
    r2: Mapping[str, Any],
    input_hashes: Mapping[str, str],
    config: Mapping[str, Any],
    final_root: Path,
    staging_root: Path,
) -> dict[str, Any]:
    coordinate = config["coordinate_contract"]
    class6_base = np.asarray(cloud.building_xyz, dtype=np.float64)
    class2_base = np.asarray(ground_base, dtype=np.float64)
    xyz_base = np.vstack([class6_base, class2_base])
    classification = np.concatenate(
        [
            np.full(len(class6_base), 6, dtype=np.uint8),
            np.full(len(class2_base), 2, dtype=np.uint8),
        ]
    )
    xyz_canonical = base_to_canonical_points(
        xyz_base,
        scene_reference,
        input_datum=coordinate["base_vertical_datum"],
        geoid_m=float(coordinate["orthometric_to_ellipsoidal_geoid_m"]),
    )
    selected = select_views(
        gate,
        class6_base,
        cameras,
        images_by_name,
        scene_reference,
        config,
    )
    rgb8, rgb_sample_count, rgb_stats = sample_seed_rgb(
        gate, xyz_canonical, selected, image_paths, config
    )

    views_rows: list[dict[str, Any]] = []
    image_hashes: dict[str, str] = {}
    for view in selected:
        source = image_paths[view.image.name]
        image_hash = sha256_file(source)
        image_hashes[view.image.name] = image_hash
        final_link = final_root / "images" / view.image.name
        staging_link = staging_root / "images" / view.image.name
        create_final_relative_symlink(staging_link, final_link, source)
        views_rows.append(
            {
                "selection_order": view.selection_order,
                "building_id": target.building_id,
                "image_name": view.image.name,
                "image_id": view.image.id,
                "camera_id": view.camera.id,
                "width": view.camera.width,
                "height": view.camera.height,
                "class6_inframe_n": view.class6_inframe_n,
                "class6_visible_n": view.class6_visible_n,
                "frame_radius": view.frame_radius,
                "nadir_deg": view.nadir_deg,
                "azimuth_bin": view.azimuth_bin,
                "corrected_pose_source_sha256": config["r1_contract"][
                    "corrected_images_sha256"
                ],
                "image_path": relative(final_link),
                "image_sha256": image_hash,
                "selection_used_image_intensity": False,
            }
        )
    views_fields = [
        "selection_order",
        "building_id",
        "image_name",
        "image_id",
        "camera_id",
        "width",
        "height",
        "class6_inframe_n",
        "class6_visible_n",
        "frame_radius",
        "nadir_deg",
        "azimuth_bin",
        "corrected_pose_source_sha256",
        "image_path",
        "image_sha256",
        "selection_used_image_intensity",
    ]
    atomic_csv(staging_root / config["outputs"]["views_csv"], views_rows, views_fields)

    seed_npz = staging_root / config["outputs"]["canonical_seed_npz"]
    atomic_npz(
        seed_npz,
        {
            "xyz": xyz_canonical.astype(np.float64),
            "xyz_base_epsg25832_orthometric": xyz_base.astype(np.float64),
            "rgb": rgb8.astype(np.uint8),
            "rgb_sample_count": rgb_sample_count.astype(np.uint16),
            "rgb_valid": (rgb_sample_count > 0).astype(np.uint8),
            "classification": classification.astype(np.uint8),
        },
    )
    seed_ply = staging_root / config["outputs"]["canonical_seed_ply"]
    write_seed_ply(seed_ply, xyz_canonical, rgb8, classification)
    seed_las = staging_root / config["outputs"]["base_seed_las"]
    las_stats = write_seed_las(seed_las, xyz_base, classification, rgb8)

    tin_cfg = config["tin_supervision"]
    class6_canonical = xyz_canonical[classification == 6]
    class2_canonical = xyz_canonical[classification == 2]
    tin6 = build_tin(
        class6_canonical,
        maximum_xy_edge_m=float(tin_cfg["class6"]["maximum_xy_edge_m"]),
        maximum_slope_deg=float(tin_cfg["class6"]["maximum_slope_deg"]),
        minimum_xy_triangle_area_m2=float(
            tin_cfg["minimum_xy_triangle_area_m2"]
        ),
    )
    tin2 = build_tin(
        class2_canonical,
        maximum_xy_edge_m=float(tin_cfg["class2"]["maximum_xy_edge_m"]),
        maximum_slope_deg=float(tin_cfg["class2"]["maximum_slope_deg"]),
        minimum_xy_triangle_area_m2=float(
            tin_cfg["minimum_xy_triangle_area_m2"]
        ),
    )
    supervision_rows: list[dict[str, Any]] = []
    photo_mask_audit: list[dict[str, Any]] = []
    subset_images: dict[int, ColmapImage] = {}
    subset_cameras: dict[int, Camera] = {}
    for view in selected:
        depth6, normal6, valid6, stats6 = rasterize_tin(
            gate,
            tin6,
            view.image,
            view.camera,
            edge_margin=float(tin_cfg["screen_barycentric_edge_margin"]),
            erosion_pixels=int(tin_cfg["outer_valid_mask_erosion_px"]),
        )
        depth2, normal2, valid2, stats2 = rasterize_tin(
            gate,
            tin2,
            view.image,
            view.camera,
            edge_margin=float(tin_cfg["screen_barycentric_edge_margin"]),
            erosion_pixels=int(tin_cfg["outer_valid_mask_erosion_px"]),
        )
        depth, normal_world, valid, source_class = combine_supervision(
            depth6, normal6, valid6, depth2, normal2, valid2
        )
        normal_camera = normal_world @ view.image.R().T
        normal_camera[~valid] = 0.0
        class6_path = (
            staging_root / "supervision" / "class6" / f"{view.image.name}.npz"
        )
        class2_path = (
            staging_root / "supervision" / "class2" / f"{view.image.name}.npz"
        )
        atomic_npz(
            class6_path,
            {
                "depth_camera_z_m": depth6.astype(np.float32),
                "normal_world": normal6.astype(np.float32),
                "valid": valid6.astype(np.uint8),
            },
        )
        atomic_npz(
            class2_path,
            {
                "depth_camera_z_m": depth2.astype(np.float32),
                "normal_world": normal2.astype(np.float32),
                "valid": valid2.astype(np.uint8),
            },
        )
        depth_path = (
            staging_root
            / "stereo"
            / "depth_maps"
            / f"{view.image.name}.geometric.bin"
        )
        normal_path = (
            staging_root
            / "stereo"
            / "normal_maps"
            / f"{view.image.name}.geometric.bin"
        )
        write_colmap_array(depth_path, depth)
        write_colmap_array(normal_path, normal_camera)
        combined_mask_path = (
            staging_root
            / "supervision"
            / "valid_masks"
            / f"{view.image.name}.npy"
        )
        atomic_npy(combined_mask_path, valid.astype(bool))
        photo_mask, photo_audit = rasterize_target_photo_support_mask(
            gate,
            footprint,
            class6_canonical,
            view.image,
            view.camera,
            scene_reference,
            coordinate,
        )
        photo_mask_path = (
            staging_root
            / "photo_support_masks"
            / f"{Path(view.image.name).stem}.npy"
        )
        atomic_npy(photo_mask_path, photo_mask)
        photo_mask_audit.append(
            {
                "image_name": view.image.name,
                **photo_audit,
            }
        )
        source_class_path = (
            staging_root
            / "supervision"
            / "source_class"
            / f"{view.image.name}.npy"
        )
        atomic_npy(source_class_path, source_class)
        subset_images[view.image.id] = view.image
        subset_cameras[view.camera.id] = view.camera
        supervision_rows.append(
            {
                "selection_order": view.selection_order,
                "building_id": target.building_id,
                "image_name": view.image.name,
                "class6_npz_path": relative(
                    final_root
                    / "supervision"
                    / "class6"
                    / f"{view.image.name}.npz"
                ),
                "class6_valid_pixels_n": int(valid6.sum()),
                "class6_outer_edge_masked_pixels_n": stats6[
                    "outer_edge_masked_pixels_n"
                ],
                "class2_npz_path": relative(
                    final_root
                    / "supervision"
                    / "class2"
                    / f"{view.image.name}.npz"
                ),
                "class2_valid_pixels_n": int(valid2.sum()),
                "class2_outer_edge_masked_pixels_n": stats2[
                    "outer_edge_masked_pixels_n"
                ],
                "combined_depth_path": relative(
                    final_root
                    / "stereo"
                    / "depth_maps"
                    / f"{view.image.name}.geometric.bin"
                ),
                "combined_normal_path": relative(
                    final_root
                    / "stereo"
                    / "normal_maps"
                    / f"{view.image.name}.geometric.bin"
                ),
                "combined_valid_mask_path": relative(
                    final_root
                    / "supervision"
                    / "valid_masks"
                    / f"{view.image.name}.npy"
                ),
                "photo_support_mask_path": relative(
                    final_root
                    / "photo_support_masks"
                    / f"{Path(view.image.name).stem}.npy"
                ),
                "photo_support_valid_pixels_n": int(photo_mask.sum()),
                "combined_valid_pixels_n": int(valid.sum()),
                "combined_class6_pixels_n": int((source_class == 6).sum()),
                "combined_class2_pixels_n": int((source_class == 2).sum()),
                "pose_sha256": config["r1_contract"]["corrected_images_sha256"],
            }
        )
    supervision_fields = [
        "selection_order",
        "building_id",
        "image_name",
        "class6_npz_path",
        "class6_valid_pixels_n",
        "class6_outer_edge_masked_pixels_n",
        "class2_npz_path",
        "class2_valid_pixels_n",
        "class2_outer_edge_masked_pixels_n",
        "combined_depth_path",
        "combined_normal_path",
        "combined_valid_mask_path",
        "photo_support_mask_path",
        "photo_support_valid_pixels_n",
        "combined_valid_pixels_n",
        "combined_class6_pixels_n",
        "combined_class2_pixels_n",
        "pose_sha256",
    ]
    supervision_index = staging_root / config["outputs"]["supervision_index"]
    atomic_csv(
        supervision_index, supervision_rows, supervision_fields
    )

    sparse_root = staging_root / "sparse" / "0"
    write_cameras_bin(sparse_root / "cameras.bin", subset_cameras)
    write_images_bin(sparse_root / "images.bin", subset_images)
    sparse_base = canonical_to_base_points(
        corrected_sparse_points[:, :3], scene_reference
    )
    sparse_keep = points_within_polygon_buffer(
        sparse_base[:, :2],
        footprint,
        float(config["subset_contract"]["ground_buffer_m"]),
    )
    sparse_subset = corrected_sparse_points[sparse_keep]
    write_points3d_bin(sparse_root / "points3D.bin", sparse_subset)

    parsed_names = sorted(
        image.name
        for image in read_images_bin(sparse_root / "images.bin").values()
    )
    selected_names = sorted(view.image.name for view in selected)
    image_link_names = sorted(
        str(path.relative_to(staging_root / "images"))
        for path in (staging_root / "images").rglob("*")
        if path.is_symlink()
    )
    depth_root = staging_root / "stereo" / "depth_maps"
    normal_root = staging_root / "stereo" / "normal_maps"
    depth_names = sorted(
        path.relative_to(depth_root).as_posix().removesuffix(".geometric.bin")
        for path in depth_root.rglob("*.geometric.bin")
    )
    normal_names = sorted(
        path.relative_to(normal_root).as_posix().removesuffix(".geometric.bin")
        for path in normal_root.rglob("*.geometric.bin")
    )
    index_names = sorted(row["image_name"] for row in supervision_rows)
    if not (
        selected_names
        == parsed_names
        == image_link_names
        == depth_names
        == normal_names
        == index_names
    ):
        raise PreprocessError("selected data-root view inventories differ")

    artifact_hashes, artifact_kinds = collect_artifacts(
        staging_root, final_root, image_hashes
    )
    class_counts = {
        "2": int((classification == 2).sum()),
        "6": int((classification == 6).sum()),
    }
    manifest = {
        "schema": BUILDING_SCHEMA,
        "status": "PASSED",
        "created_at": now_iso(),
        "task_id": config["task_id"],
        "run_id": config["run_id"],
        "building": {
            "building_id": target.building_id,
            "processing_order": target.processing_order,
            "tier": target.tier,
            "cohort": target.cohort,
            "queue_status": target.queue_status,
            "cohort_resolution_status": target.cohort_resolution_status,
        },
        "data_root": relative(final_root),
        "pose_binding": {
            "r1_manifest": config["inputs"]["r1_manifest"],
            "r1_manifest_sha256": sha256_file(
                repo_path(config["inputs"]["r1_manifest"])
            ),
            "corrected_sparse": config["inputs"]["corrected_sparse"],
            "corrected_images_sha256": config["r1_contract"][
                "corrected_images_sha256"
            ],
            "transform_application_count": 1,
            "additional_transform_application_count": 0,
            "cache_namespace": config["outputs"]["cache_namespace"],
        },
        "gate_binding": {
            "r2_manifest": config["inputs"]["r2_manifest"],
            "r2_manifest_sha256": sha256_file(
                repo_path(config["inputs"]["r2_manifest"])
            ),
            "gate_a_version": r2["gate_a_version"],
            "status": r2["status"],
        },
        "views": {
            "csv": {
                "path": relative(final_root / config["outputs"]["views_csv"]),
                "sha256": artifact_hashes[
                    relative(final_root / config["outputs"]["views_csv"])
                ],
            },
            "count": len(selected),
            "minimum": int(config["view_selection"]["minimum_views"]),
            "maximum": int(config["view_selection"]["maximum_views"]),
            "selection": config["view_selection"]["ranking"],
            "selected_names": selected_names,
            "inventory_equality_verified": True,
        },
        "seed": {
            "source_points_n": int(len(xyz_base)),
            "output_points_n": int(len(xyz_base)),
            "downsample_applied": False,
            "visibility_filter_geometry_drop_applied": False,
            "classification_counts": class_counts,
            "base_las": {
                "path": relative(final_root / config["outputs"]["base_seed_las"]),
                "sha256": artifact_hashes[
                    relative(final_root / config["outputs"]["base_seed_las"])
                ],
                "crs": "EPSG:25832",
                "vertical_datum": "orthometric",
                **las_stats,
            },
            "canonical_npz": {
                "path": relative(
                    final_root / config["outputs"]["canonical_seed_npz"]
                ),
                "sha256": artifact_hashes[
                    relative(
                        final_root / config["outputs"]["canonical_seed_npz"]
                    )
                ],
                "frame": coordinate["canonical_frame"],
                "vertical_conversion": {
                    "orthometric_to_ellipsoidal_geoid_m": float(
                        coordinate["orthometric_to_ellipsoidal_geoid_m"]
                    ),
                    "application_count": 1,
                },
            },
            "canonical_ply": {
                "path": relative(
                    final_root / config["outputs"]["canonical_seed_ply"]
                ),
                "sha256": artifact_hashes[
                    relative(
                        final_root / config["outputs"]["canonical_seed_ply"]
                    )
                ],
                "frame": coordinate["canonical_frame"],
            },
            "rgb": rgb_stats,
        },
        "supervision": {
            "index": {
                "path": relative(
                    final_root / config["outputs"]["supervision_index"]
                ),
                "sha256": artifact_hashes[
                    relative(
                        final_root / config["outputs"]["supervision_index"]
                    )
                ],
            },
            "views_n": len(supervision_rows),
            "classes": [2, 6],
            "pose_cache_namespace": config["outputs"]["cache_namespace"],
            "depth_definition": tin_cfg["depth_definition"],
            "normal_separate_frame": tin_cfg["normal_separate_frame"],
            "normal_colmap_bin_frame": tin_cfg["normal_colmap_bin_frame"],
            "invalid_depth": tin_cfg["invalid_depth"],
            "invalid_normal": tin_cfg["invalid_normal"],
            "walls_supervised": False,
            "class6_tin": tin6.stats,
            "class2_tin": tin2.stats,
            "screen_barycentric_edge_margin": float(
                tin_cfg["screen_barycentric_edge_margin"]
            ),
            "outer_valid_mask_erosion_px": int(
                tin_cfg["outer_valid_mask_erosion_px"]
            ),
            "valid_pixels": {
                "class6_total": int(
                    sum(row["class6_valid_pixels_n"] for row in supervision_rows)
                ),
                "class2_total": int(
                    sum(row["class2_valid_pixels_n"] for row in supervision_rows)
                ),
                "combined_total": int(
                    sum(row["combined_valid_pixels_n"] for row in supervision_rows)
                ),
            },
        },
        "photo_support_masks": {
            **config["photo_support_masks"],
            "views_n": len(supervision_rows),
            "valid_pixels_total": int(
                sum(
                    row["photo_support_valid_pixels_n"]
                    for row in supervision_rows
                )
            ),
            "source": (
                "approved target GroundSurface XY projected at the actual "
                "class6 ALS q80-upper median height; buffered class2 and "
                "non-target class6 are excluded"
            ),
            "per_view_audit": photo_mask_audit,
        },
        "colmap_data_root": {
            "directly_consumable": True,
            "selected_images_n": len(selected_names),
            "selected_names": selected_names,
            "sparse": {
                name: {
                    "path": relative(final_root / "sparse" / "0" / name),
                    "sha256": artifact_hashes[
                        relative(final_root / "sparse" / "0" / name)
                    ],
                }
                for name in ("cameras.bin", "images.bin", "points3D.bin")
            },
            "corrected_sparse_points_20m_n": int(len(sparse_subset)),
            "image_symlinks_preserve_source_pixels": True,
        },
        "source_inputs": {
            "sha256": dict(input_hashes),
            "source_als_tiles": list(cloud.source_tiles),
            "footprint_role": "approved GroundSurface XY crop/address only",
            "forbidden_lod2_components_read": [],
        },
        "artifact_sha256": artifact_hashes,
        "artifact_kind": artifact_kinds,
        "publication": {
            "manifest_written_last": True,
            "partial_building_reviewable": True,
            "learning_runs_started": 0,
            "readout_runs_started": 0,
            "roofer_runs_started": 0,
            "scoring_runs_started": 0,
        },
    }
    atomic_json(staging_root / config["outputs"]["building_manifest"], manifest)
    return manifest


def prepare_one(
    *,
    target: Target,
    gate: Any,
    als_store: Any,
    footprints: Mapping[str, np.ndarray],
    cameras: Mapping[int, Camera],
    images_by_name: Mapping[str, ColmapImage],
    image_paths: Mapping[str, Path],
    corrected_sparse_points: np.ndarray,
    scene_reference: Mapping[str, Any],
    r1: Mapping[str, Any],
    r2: Mapping[str, Any],
    input_hashes: Mapping[str, str],
    config: Mapping[str, Any],
    cache_root: Path,
) -> dict[str, Any]:
    final_root = (
        cache_root
        / config["outputs"]["building_root"]
        / target.building_id
    )
    final_manifest = final_root / config["outputs"]["building_manifest"]
    pose_hash = config["r1_contract"]["corrected_images_sha256"]
    if final_manifest.is_file():
        return verify_building_manifest(final_manifest, pose_hash)
    if final_root.exists():
        raise PreprocessError(
            f"incomplete final building directory exists: {relative(final_root)}"
        )
    staging_parent = cache_root / ".staging"
    staging_parent.mkdir(parents=True, exist_ok=True)
    staging_root = staging_parent / (
        f"{target.building_id}.{os.getpid()}.{datetime.now().strftime('%H%M%S%f')}"
    )
    staging_root.mkdir(parents=False, exist_ok=False)
    footprint = footprints[target.building_id]
    evidence = {
        "footprint_building_buffer_m": 0.0,
        "ground_context_buffer_m": float(
            config["subset_contract"]["ground_buffer_m"]
        ),
        "minimum_building_class_points": int(
            config["subset_contract"]["minimum_building_points"]
        ),
        "minimum_ground_class_points": int(
            config["subset_contract"]["minimum_ground_points"]
        ),
    }
    cloud = als_store.target_cloud(target.building_id, footprint, evidence)
    ground_keep = points_within_polygon_buffer(
        cloud.ground_xyz[:, :2],
        footprint,
        float(config["subset_contract"]["ground_buffer_m"]),
    )
    ground_base = cloud.ground_xyz[ground_keep]
    if len(ground_base) < int(config["subset_contract"]["minimum_ground_points"]):
        raise PreprocessError(f"{target.building_id}: too few buffered ground points")
    manifest = materialize_building(
        gate=gate,
        target=target,
        footprint=footprint,
        cloud=cloud,
        ground_base=ground_base,
        cameras=cameras,
        images_by_name=images_by_name,
        image_paths=image_paths,
        corrected_sparse_points=corrected_sparse_points,
        scene_reference=scene_reference,
        r1=r1,
        r2=r2,
        input_hashes=input_hashes,
        config=config,
        final_root=final_root,
        staging_root=staging_root,
    )
    final_root.parent.mkdir(parents=True, exist_ok=True)
    os.replace(staging_root, final_root)
    fsync_parent(final_root)
    return verify_building_manifest(final_manifest, pose_hash)


INDEX_FIELDS = [
    "processing_order",
    "building_id",
    "tier",
    "cohort",
    "status",
    "data_root",
    "building_manifest_path",
    "building_manifest_sha256",
    "views_n",
    "seed_points_n",
    "class2_n",
    "class6_n",
    "pose_sha256",
]

SEED_STATS_FIELDS = [
    "processing_order",
    "building_id",
    "tier",
    "cohort",
    "status",
    "source_points_n",
    "output_points_n",
    "class2_n",
    "class6_n",
    "downsample_applied",
    "rgb_sampled_points_n",
    "rgb_unsampled_points_n",
    "views_n",
    "pose_sha256",
    "building_manifest_path",
    "building_manifest_sha256",
]


def publish_run_manifest(
    config: Mapping[str, Any],
    targets: Sequence[Target],
    cache_root: Path,
    git_lock: Mapping[str, Any],
) -> dict[str, Any]:
    pose_hash = config["r1_contract"]["corrected_images_sha256"]
    records: list[dict[str, Any]] = []
    seed_stats_rows: list[dict[str, Any]] = []
    for target in targets:
        path = (
            cache_root
            / config["outputs"]["building_root"]
            / target.building_id
            / config["outputs"]["building_manifest"]
        )
        if not path.is_file():
            continue
        payload = verify_building_manifest(path, pose_hash)
        counts = payload["seed"]["classification_counts"]
        records.append(
            {
                "processing_order": target.processing_order,
                "building_id": target.building_id,
                "tier": target.tier,
                "cohort": target.cohort,
                "status": payload["status"],
                "data_root": payload["data_root"],
                "building_manifest_path": relative(path),
                "building_manifest_sha256": sha256_file(path),
                "views_n": payload["views"]["count"],
                "seed_points_n": payload["seed"]["output_points_n"],
                "class2_n": int(counts["2"]),
                "class6_n": int(counts["6"]),
                "pose_sha256": pose_hash,
            }
        )
        seed_stats_rows.append(
            {
                "processing_order": target.processing_order,
                "building_id": target.building_id,
                "tier": target.tier,
                "cohort": target.cohort,
                "status": payload["status"],
                "source_points_n": payload["seed"]["source_points_n"],
                "output_points_n": payload["seed"]["output_points_n"],
                "class2_n": int(counts["2"]),
                "class6_n": int(counts["6"]),
                "downsample_applied": payload["seed"]["downsample_applied"],
                "rgb_sampled_points_n": payload["seed"]["rgb"][
                    "sampled_points_n"
                ],
                "rgb_unsampled_points_n": payload["seed"]["rgb"][
                    "unsampled_points_n"
                ],
                "views_n": payload["views"]["count"],
                "pose_sha256": pose_hash,
                "building_manifest_path": relative(path),
                "building_manifest_sha256": sha256_file(path),
            }
        )
    records.sort(key=lambda row: (row["processing_order"], row["building_id"]))
    seed_stats_rows.sort(
        key=lambda row: (row["processing_order"], row["building_id"])
    )
    index_path = cache_root / config["outputs"]["run_index"]
    atomic_csv(index_path, records, INDEX_FIELDS)
    seed_stats_path = repo_path(config["outputs"]["seed_stats_csv"])
    atomic_csv(seed_stats_path, seed_stats_rows, SEED_STATS_FIELDS)
    core_expected = len([target for target in targets if target.cohort == "core"])
    core_completed = len([row for row in records if row["cohort"] == "core"])
    status = "PASSED" if core_completed == core_expected else "PARTIAL"
    cache_manifest_path = cache_root / config["outputs"]["cache_run_manifest"]
    cache_manifest = {
        "schema": RUN_SCHEMA,
        "status": status,
        "created_at": now_iso(),
        "task_id": config["task_id"],
        "run_id": config["run_id"],
        "core_expected_n": core_expected,
        "core_completed_n": core_completed,
        "completed_buildings_n": len(records),
        "pose_binding": {
            "r1_manifest": config["inputs"]["r1_manifest"],
            "r1_manifest_sha256": sha256_file(
                repo_path(config["inputs"]["r1_manifest"])
            ),
            "corrected_images_sha256": pose_hash,
            "cache_namespace": config["outputs"]["cache_namespace"],
        },
        "preprocess_index": {
            "path": relative(index_path),
            "sha256": sha256_file(index_path),
            "building_manifest_column": "building_manifest_path",
        },
        "fixed_outputs": {
            "w1_seed_stats": {
                "path": relative(seed_stats_path),
                "sha256": sha256_file(seed_stats_path),
                "rows_n": len(seed_stats_rows),
                "incremental_atomic_rebuild": True,
            }
        },
        "buildings": records,
        "git_lock": dict(git_lock),
        "publication": {
            "cache_manifest_written_after_index": True,
            "stable_manifest_pending": True,
            "partial_buildings_reviewable": True,
            "learning_runs_started": 0,
            "readout_runs_started": 0,
            "roofer_runs_started": 0,
            "scoring_runs_started": 0,
        },
    }
    atomic_json(cache_manifest_path, cache_manifest)
    stable_root = repo_path(config["outputs"]["stable_root"])
    stable_path = stable_root / config["outputs"]["stable_run_manifest"]
    stable_manifest = {
        **cache_manifest,
        "cache_binding": {
            "namespace": config["outputs"]["cache_namespace"],
            "cache_dir": relative(cache_root),
            "cache_run_manifest": {
                "path": relative(cache_manifest_path),
                "sha256": sha256_file(cache_manifest_path),
            },
            "preprocess_index": {
                "path": relative(index_path),
                "sha256": sha256_file(index_path),
            },
            "w1_seed_stats": {
                "path": relative(seed_stats_path),
                "sha256": sha256_file(seed_stats_path),
            },
        },
        "publication": {
            **cache_manifest["publication"],
            "stable_manifest_pending": False,
            "stable_manifest_written_last": True,
        },
    }
    atomic_json(stable_path, stable_manifest)
    return stable_manifest


def execute(config: Mapping[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    require_docker()
    git_lock = verify_method_lock(config)
    input_hashes = verify_input_hashes(config)
    r1, r2 = validate_authorization(config)
    gate = import_module(
        "fusion_w1_alignment_gate_lock1_preprocess",
        repo_path(config["inputs"]["alignment_helper_script"]),
    )
    targets = load_targets(repo_path(config["inputs"]["targets_csv"]))
    lookup = {target.building_id: target for target in targets}
    if args.all_core:
        selected_targets = [target for target in targets if target.cohort == "core"]
    else:
        building_id = canonical_building_id(args.building_id)
        if building_id not in lookup:
            raise PreprocessError(f"building not in canonical queue: {building_id}")
        selected_targets = [lookup[building_id]]
    target_ids = [target.building_id for target in selected_targets]
    footprints = gate.load_footprints(
        repo_path(config["inputs"]["footprint_xy"]),
        target_ids,
        config["inputs"]["footprint_id_field"],
        config["inputs"]["footprint_layer"],
        gate.load_config(repo_path(config["inputs"]["alignment_helper_config"])),
    )
    als_store = gate.ALSStore(
        [repo_path(path) for path in config["inputs"]["als_files"]],
        int(config["subset_contract"]["ground_class"]),
        int(config["subset_contract"]["building_class"]),
    )
    cameras, _images, images_by_name, image_paths = gate.load_training_inventory(
        repo_path(config["inputs"]["corrected_sparse"]),
        repo_path(config["inputs"]["training_image_dir"]),
        int(config["r1_contract"]["image_count"]),
    )
    if sha256_file(
        repo_path(config["inputs"]["corrected_sparse"]) / "images.bin"
    ) != config["r1_contract"]["corrected_images_sha256"]:
        raise PreprocessError("corrected pose hash drift before preparation")
    corrected_sparse_points = read_points3d_bin(
        repo_path(config["inputs"]["corrected_sparse"]) / "points3D.bin"
    )
    scene_reference = load_json(config["inputs"]["scene_reference_frame"])
    stable_root = repo_path(config["outputs"]["stable_root"])
    cache_root = stable_root / config["outputs"]["cache_namespace"]
    cache_root.mkdir(parents=True, exist_ok=True)
    prepared: list[str] = []
    for target in selected_targets:
        prepare_one(
            target=target,
            gate=gate,
            als_store=als_store,
            footprints=footprints,
            cameras=cameras,
            images_by_name=images_by_name,
            image_paths=image_paths,
            corrected_sparse_points=corrected_sparse_points,
            scene_reference=scene_reference,
            r1=r1,
            r2=r2,
            input_hashes=input_hashes,
            config=config,
            cache_root=cache_root,
        )
        prepared.append(target.building_id)
    run_manifest = publish_run_manifest(config, targets, cache_root, git_lock)
    return {
        "status": run_manifest["status"],
        "prepared_this_invocation": prepared,
        "core_completed_n": run_manifest["core_completed_n"],
        "stable_manifest": relative(
            stable_root / config["outputs"]["stable_run_manifest"]
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--building-id")
    group.add_argument("--all-core", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_config(args.config)
        result = execute(config, args)
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "BLOCKED",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
