#!/usr/bin/env python3
"""Prepare S3-A-prime Phase-1 external seed surfaces without training.

The canonical seed geometry is copied from the committed Phase-0 P0 surface
NPZ.  LoD2 and ALS are not opened; the strict engine metadata records only the
three required false declarations.  The only supplied vector is the target
footprint, used as a spatial mask.  For the two B targets, observed sparse/dense
points in a 1 m boundary band are measured against the FM/P0 plane; accepted
points are written only as a separate lineage.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import platform
import struct
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp")

import matplotlib
import numpy as np
from shapely import contains_xy, make_valid
from shapely.geometry import GeometryCollection, MultiPolygon, Point, Polygon, shape
from shapely.ops import unary_union

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from src.stage2.colmap_io import read_array, read_cameras_bin, read_images_bin
from src.stage2.semantic_seed import SURFACE_SEED_SCHEMA, load_surface_seed_npz


REPO = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = REPO / "phases/p2-gsjso/configs/e5_c001/e5_c001_s3ap_phase1_seedprep.json"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def rel(path: Path | str) -> str:
    value = Path(path).resolve()
    try:
        return str(value.relative_to(REPO.resolve()))
    except ValueError:
        return str(value)


def sha256_file(path: Path, block_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def array_payload_sha256(array: np.ndarray) -> str:
    canonical = np.ascontiguousarray(array)
    return sha256_bytes(canonical.tobytes(order="C"))


def git_value(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO, text=True).strip()


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def fmt(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (bool, np.bool_)):
        return "true" if bool(value) else "false"
    if isinstance(value, (float, np.floating)):
        return "" if not math.isfinite(float(value)) else f"{float(value):.12f}"
    return str(value)


def atomic_csv(path: Path, rows: Sequence[dict[str, Any]], fields: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows({field: fmt(row.get(field)) for field in fields} for row in rows)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def npy_bytes(array: np.ndarray) -> bytes:
    stream = io.BytesIO()
    np.lib.format.write_array(stream, np.asarray(array), allow_pickle=False)
    return stream.getvalue()


def atomic_deterministic_npz(path: Path, arrays: dict[str, np.ndarray]) -> None:
    """Write an NPZ with fixed ZIP metadata so identical arrays hash identically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("wb") as raw:
        with zipfile.ZipFile(raw, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for key in sorted(arrays):
                info = zipfile.ZipInfo(f"{key}.npy", date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o600 << 16
                archive.writestr(info, npy_bytes(arrays[key]), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
        raw.flush()
        os.fsync(raw.fileno())
    os.replace(tmp, path)


def flatten_polygons(geom: Any) -> list[Polygon]:
    if geom is None or geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        return [geom]
    if isinstance(geom, MultiPolygon):
        return list(geom.geoms)
    if isinstance(geom, GeometryCollection):
        out: list[Polygon] = []
        for part in geom.geoms:
            out.extend(flatten_polygons(part))
        return out
    return []


def load_footprints(path: Path, targets: Sequence[str]) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    crs = str(payload.get("crs", {}).get("properties", {}).get("name", ""))
    if "25832" not in crs:
        raise RuntimeError(f"footprint CRS is not EPSG:25832: {crs!r}")
    pieces: dict[str, list[Any]] = {short: [] for short in targets}
    for feature in payload.get("features", []):
        bid = str((feature.get("properties") or {}).get("building_id", ""))
        short = bid.removeprefix("DEBY_LOD2_")
        if short in pieces:
            geom = make_valid(shape(feature["geometry"]))
            if not geom.is_empty:
                pieces[short].append(geom)
    result = {short: make_valid(unary_union(values)) for short, values in pieces.items() if values}
    missing = sorted(set(targets) - set(result))
    if missing:
        raise RuntimeError(f"missing footprints: {missing}")
    return result


def _read(handle: Any, fmt_code: str) -> tuple[Any, ...]:
    size = struct.calcsize(fmt_code)
    value = handle.read(size)
    if len(value) != size:
        raise EOFError("unexpected COLMAP points3D EOF")
    return struct.unpack(fmt_code, value)


def read_sparse_points(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    xyz: list[tuple[float, float, float]] = []
    rgb: list[tuple[int, int, int]] = []
    track_length: list[int] = []
    with path.open("rb") as handle:
        count = int(_read(handle, "<Q")[0])
        for _ in range(count):
            _point_id = _read(handle, "<Q")[0]
            xyz.append(tuple(float(value) for value in _read(handle, "<ddd")))
            rgb.append(tuple(int(value) for value in _read(handle, "<BBB")))
            _error = _read(handle, "<d")[0]
            length = int(_read(handle, "<Q")[0])
            handle.seek(8 * length, 1)
            track_length.append(length)
    return (
        np.asarray(xyz, dtype=np.float64),
        np.asarray(rgb, dtype=np.uint8),
        np.asarray(track_length, dtype=np.int32),
    )


def read_dense_xyz(path: Path) -> np.ndarray:
    header_lines = 0
    count: int | None = None
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            header_lines += 1
            if line.startswith("element vertex "):
                count = int(line.split()[-1])
            if line.strip() == "end_header":
                break
    if count is None:
        raise RuntimeError(f"PLY vertex count missing: {rel(path)}")
    xyz = np.loadtxt(path, skiprows=header_lines, max_rows=count, usecols=(0, 1, 2), dtype=np.float32)
    xyz = np.asarray(xyz, dtype=np.float64).reshape(-1, 3)
    if len(xyz) != count:
        raise RuntimeError(f"PLY count mismatch: {len(xyz)} != {count}")
    return xyz


def point_band_candidates(points_local: np.ndarray, footprint: Any, offset: np.ndarray, band_m: float) -> tuple[np.ndarray, np.ndarray]:
    world_xy = points_local[:, :2] + offset[None, :2]
    outer = footprint.buffer(band_m + 0.05)
    minx, miny, maxx, maxy = outer.bounds
    bbox = (
        (world_xy[:, 0] >= minx) & (world_xy[:, 0] <= maxx)
        & (world_xy[:, 1] >= miny) & (world_xy[:, 1] <= maxy)
    )
    index = np.flatnonzero(bbox)
    if not len(index):
        return index, np.zeros(0, dtype=np.float64)
    distance = np.asarray([
        footprint.boundary.distance(Point(float(x), float(y)))
        for x, y in world_xy[index]
    ], dtype=np.float64)
    keep = distance <= band_m
    return index[keep], distance[keep]


def footprint_covers_mask(points_local: np.ndarray, footprint: Any, offset: np.ndarray) -> np.ndarray:
    world_xy = points_local[:, :2] + offset[None, :2]
    # covers includes exact footprint-boundary coordinates; candidate sets are small.
    return np.asarray([
        footprint.covers(Point(float(x), float(y))) for x, y in world_xy
    ], dtype=bool)


def resolve_depth_map(depth_dir: Path, image_name: str) -> Path | None:
    for suffix in (".geometric.bin", ".photometric.bin"):
        path = depth_dir / f"{image_name}{suffix}"
        if path.exists():
            return path
    return None


def dense_visibility_counts(
    points: np.ndarray,
    cameras: dict[int, Any],
    images: dict[int, Any],
    depth_dir: Path,
    absolute_tolerance: float,
    relative_tolerance: float,
) -> tuple[np.ndarray, list[Path]]:
    counts = np.zeros(len(points), dtype=np.int16)
    used_paths: list[Path] = []
    if not len(points):
        return counts, used_paths
    hom = np.column_stack([points, np.ones(len(points), dtype=np.float64)])
    for image_id in sorted(images):
        image = images[image_id]
        camera = cameras[image.camera_id]
        depth_path = resolve_depth_map(depth_dir, image.name)
        if depth_path is None:
            continue
        used_paths.append(depth_path)
        depth_map = np.asarray(read_array(depth_path), dtype=np.float32)
        w2c = np.eye(4, dtype=np.float64)
        w2c[:3, :3] = image.R()
        w2c[:3, 3] = image.tvec
        camera_xyz = (w2c @ hom.T).T[:, :3]
        z = camera_xyz[:, 2]
        uvw = (camera.K() @ camera_xyz.T).T
        uv = uvw[:, :2] / np.maximum(uvw[:, 2:3], 1e-12)
        u = np.rint(uv[:, 0] * depth_map.shape[1] / float(camera.width)).astype(np.int64)
        v = np.rint(uv[:, 1] * depth_map.shape[0] / float(camera.height)).astype(np.int64)
        valid = np.isfinite(uv).all(axis=1) & np.isfinite(z) & (z > 0)
        valid &= (u >= 0) & (u < depth_map.shape[1]) & (v >= 0) & (v < depth_map.shape[0])
        idx = np.flatnonzero(valid)
        if not len(idx):
            continue
        measured = depth_map[v[idx], u[idx]].astype(np.float64)
        tolerance = np.maximum(absolute_tolerance, relative_tolerance * np.abs(z[idx]))
        agrees = np.isfinite(measured) & (measured > 0) & (np.abs(measured - z[idx]) <= tolerance)
        counts[idx[agrees]] += 1
    return counts, used_paths


def plane_from_surface(points: np.ndarray) -> tuple[np.ndarray, float]:
    design = np.column_stack([points[:, 0], points[:, 1], np.ones(len(points))])
    coefficient = np.linalg.lstsq(design, points[:, 2], rcond=None)[0]
    residual = points[:, 2] - design @ coefficient
    return coefficient.astype(np.float64), float(np.max(np.abs(residual)))


def metadata_for_seed(
    config: dict[str, Any],
    short: str,
    lineage: str,
    source_npz: Path,
    source_key: str,
    source_payload_sha: str,
    plane: np.ndarray,
    height_anchor: float,
    height_anchor_count: int,
) -> dict[str, Any]:
    lineage_object = {
        "kind": lineage,
        "source_artifact": rel(source_npz),
        "source_array": source_key,
        "source_array_payload_sha256": source_payload_sha,
    }
    return {
        "schema": config["seed_contract"]["schema"],
        "seed_type": "surface",
        "building_id": f"DEBY_LOD2_{short}",
        "crs": config["crs"],
        "coordinate_frame": config["seed_contract"]["coordinate_frame"],
        "coordinate_frame_definition": config["seed_contract"]["coordinate_frame_definition"],
        "lineage": lineage_object,
        "source_npz": rel(source_npz),
        "source_key": source_key,
        "source_npz_sha256": sha256_file(source_npz),
        "source_array_payload_sha256": source_payload_sha,
        "grid_m": float(config["canonical_surface"]["grid_m"]),
        "grid_spacing_m": float(config["canonical_surface"]["grid_m"]),
        "height_anchor_source": "all_footprint_inside_fm_z_median",
        "height_anchor_count": int(height_anchor_count),
        "height_anchor_z_median_local_m": float(height_anchor),
        "plane_ax_local": float(plane[0]),
        "plane_by_local": float(plane[1]),
        "plane_c_local": float(plane[2]),
        "seed_semantic": int(config["seed_contract"]["sem"]),
        "init_opacity": float(config["seed_contract"]["loader_derived_init_opacity"]),
        "rgb_source": "C001_COLMAP_sparse_initialization_mean",
        "footprint_role": "surface extent and target spatial mask only",
        "gt_used_for_seed_generation": False,
        "lod2_used_for_seed_generation": False,
        "als_used_for_seed_generation": False,
        "learning_runs_started": 0,
    }


def validate_seed_npz(path: Path, config: dict[str, Any]) -> dict[str, Any]:
    payload = np.load(path, allow_pickle=False)
    required = set(config["seed_contract"]["required_npz_keys"])
    if set(payload.files) != required:
        raise RuntimeError(f"seed NPZ key contract mismatch {rel(path)}: {payload.files}")
    metadata = json.loads(str(payload["metadata_json"].item()))
    xyz = np.asarray(payload["xyz"])
    rgb = np.asarray(payload["rgb"])
    sem = np.asarray(payload["sem"])
    if xyz.dtype != np.float32 or xyz.ndim != 2 or xyz.shape[1] != 3 or not np.isfinite(xyz).all():
        raise RuntimeError(f"invalid xyz contract: {rel(path)} {xyz.shape} {xyz.dtype}")
    if rgb.dtype != np.float32 or rgb.shape != xyz.shape or not np.isfinite(rgb).all():
        raise RuntimeError(f"invalid rgb contract: {rel(path)}")
    if sem.dtype != np.int64 or sem.shape != (len(xyz),) or not np.all(sem == int(config["seed_contract"]["sem"])):
        raise RuntimeError(f"invalid semantic contract: {rel(path)}")
    # This is the authoritative engine round trip.  It rejects extra arrays and
    # truth-geometry side channels, and derives the locked 0.10 opacity.
    loaded = load_surface_seed_npz(path)
    expected_opacity = np.float32(config["seed_contract"]["loader_derived_init_opacity"])
    if loaded.metadata.get("schema") != SURFACE_SEED_SCHEMA:
        raise RuntimeError(f"engine schema round-trip mismatch: {rel(path)}")
    if loaded.init_opacity.dtype != np.float32 or loaded.init_opacity.shape != (len(xyz),):
        raise RuntimeError(f"engine derived opacity shape mismatch: {rel(path)}")
    if not np.all(loaded.init_opacity == expected_opacity):
        raise RuntimeError(f"engine derived opacity value mismatch: {rel(path)}")
    return {
        "metadata": metadata, "xyz": loaded.xyz, "rgb": loaded.rgb,
        "sem": loaded.sem, "opacity": loaded.init_opacity,
    }


SEED_FIELDS = [
    "building_id", "surface_lineage", "source_p0_npz", "source_p0_npz_sha256", "source_surface_key",
    "source_surface_dtype", "source_surface_count", "source_surface_payload_sha256",
    "canonical_float32_payload_sha256", "seed_npz", "seed_npz_sha256", "seed_xyz_payload_sha256",
    "seed_xyz_byte_equal_canonical_float32", "seed_xyz_max_abs_diff_vs_canonical_float32_m",
    "seed_xyz_max_abs_quantization_vs_source_float64_m", "fm_source_key", "fm_inside_point_count",
    "height_anchor_source", "height_anchor_z_median_local_m", "plane_ax_local", "plane_by_local",
    "plane_c_local", "canonical_plane_max_abs_residual_m", "grid_m", "seed_count", "sem",
    "init_opacity", "scene_mean_rgb_r", "scene_mean_rgb_g", "scene_mean_rgb_b", "bc_applicable",
    "bc_eligible_count", "bc_aux_seed_npz", "bc_aux_seed_count", "footprint_role", "crs",
    "coordinate_frame", "candidate_reference_inputs_loaded", "learning_runs_started", "new_mast3r_inference_runs",
    "status",
]


BOUNDARY_FIELDS = [
    "row_type", "building_id", "bc_applicable", "source", "band_width_m", "height_tolerance_m",
    "candidate_count", "multiview_pass_count", "target_address_count", "height_match_count",
    "eligible_count", "multiview_reject_count", "non_target_address_count", "height_mismatch_count",
    "eligible_height_residual_abs_median_m", "eligible_height_residual_abs_mad_m",
    "candidate_rule", "target_spatial_address_rule", "height_match_rule", "multiview_rule",
    "plane_source", "aux_seed_lineage", "aux_seed_npz", "aux_seed_count", "footprint_role",
    "candidate_reference_inputs_loaded", "crs", "learning_runs_started", "status",
]


def write_progress(path: Path, stage: str, completed: Iterable[str], status: str) -> None:
    atomic_text(path, json.dumps({
        "schema": "jointbuildgs.s3ap.phase1.seedprep.progress.v1",
        "updated_utc": now(),
        "stage": stage,
        "completed_buildings": list(completed),
        "status": status,
        "learning_runs_started": 0,
        "new_mast3r_inference_runs": 0,
    }, ensure_ascii=False, indent=2) + "\n")


def plot_outline(ax: Any, geom: Any, centre: np.ndarray, color: str, linestyle: str, label: str, linewidth: float = 1.5) -> None:
    first = True
    for polygon in flatten_polygons(geom):
        for ring in [polygon.exterior, *polygon.interiors]:
            xy = np.asarray(ring.coords, dtype=np.float64) - centre[None, :]
            ax.plot(xy[:, 0], xy[:, 1], color=color, linestyle=linestyle, linewidth=linewidth, label=label if first else None)
            first = False


def make_building_figure(
    path: Path,
    short: str,
    footprint: Any,
    offset: np.ndarray,
    surface: np.ndarray,
    seed_xyz: np.ndarray,
    fm: np.ndarray,
    boundary_detail: dict[str, np.ndarray] | None,
    byte_equal: bool,
    max_diff: float,
    band_m: float,
) -> None:
    centre = np.asarray(footprint.centroid.coords[0], dtype=np.float64)
    surface_world = surface[:, :2] + offset[:2]
    seed_world = seed_xyz[:, :2].astype(np.float64) + offset[:2]
    fm_world = fm[:, :2] + offset[:2]
    fig, axes = plt.subplots(1, 3, figsize=(15, 5), dpi=160)
    for ax in axes:
        plot_outline(ax, footprint, centre, "#138aa0", "-", "target footprint", 1.7)
        ax.set_aspect("equal")
        ax.set_xlabel("E - centre [m]")
        ax.set_ylabel("N - centre [m]")

    axes[0].scatter(surface_world[:, 0] - centre[0], surface_world[:, 1] - centre[1], s=20, facecolors="none", edgecolors="#566573", linewidths=0.7, label="Phase-0 P0")
    axes[0].scatter(seed_world[:, 0] - centre[0], seed_world[:, 1] - centre[1], s=7, c="#355c7d", marker=".", label="Phase-1 seed")
    axes[0].set_title(f"Canonical copy | N={len(seed_xyz)}\nbyte_equal={str(byte_equal).lower()}, maxdiff={max_diff:.3g} m")
    axes[0].legend(fontsize=7, loc="best")

    axes[1].scatter(fm_world[:, 0] - centre[0], fm_world[:, 1] - centre[1], s=13, c="#3f474d", marker="x", linewidths=0.6, label="FM inside input")
    axes[1].set_title(f"FM height-anchor input | N={len(fm)}")
    axes[1].legend(fontsize=7, loc="best")

    if boundary_detail is None:
        axes[2].text(0.5, 0.5, "B-c not applicable", transform=axes[2].transAxes, ha="center", va="center", color="#566573")
        axes[2].set_title("Boundary propagation inventory | N/A")
    else:
        plot_outline(axes[2], footprint.buffer(band_m), centre, "#99a3a4", "--", "1 m outer band", 1.0)
        categories = [
            ("multiview_reject", "#c4c9cc", ".", "multiview reject"),
            ("non_target", "#7f8c8d", "x", "outside target address"),
            ("height_mismatch", "#8064a2", "^", "target / height mismatch"),
            ("eligible", "#c49a46", "o", "eligible"),
        ]
        total = 0
        for key, color, marker, label in categories:
            values = boundary_detail.get(key, np.empty((0, 3)))
            total += len(values)
            if len(values):
                world = values[:, :2] + offset[:2]
                axes[2].scatter(world[:, 0] - centre[0], world[:, 1] - centre[1], s=18, c=color, marker=marker, linewidths=0.6, label=f"{label} ({len(values)})")
        axes[2].set_title(f"Observed 1 m boundary classes | N={total}")
        axes[2].legend(fontsize=6.5, loc="best")
    fig.suptitle(f"DEBY_LOD2_{short} | S3-A-prime Phase 1 seed preparation | EPSG:25832 | measurement only", fontsize=11)
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.stem + ".tmp" + path.suffix)
    fig.savefig(tmp)
    plt.close(fig)
    os.replace(tmp, path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    args = parser.parse_args()
    config_path = Path(args.config).resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config.get("schema") != "jointbuildgs.s3ap.phase1.seedprep.lock.v1":
        raise RuntimeError("config schema mismatch")
    if config["learning_runs_allowed"] != 0 or config["new_mast3r_inference_allowed"] is not False:
        raise RuntimeError("learning/inference lock mismatch")

    source = {key: (REPO / value).resolve() for key, value in config["sources"].items()}
    run_dir = (REPO / config["outputs"]["run_dir"]).resolve()
    seed_dir = run_dir / "seeds"
    progress_path = run_dir / "progress.json"
    log_path = run_dir / "run.log"
    manifest_path = run_dir / "manifest.json"
    out_seed_csv = (REPO / config["outputs"]["seed_manifest_csv"]).resolve()
    out_boundary_csv = (REPO / config["outputs"]["boundary_csv"]).resolve()
    figure_dir = (REPO / config["outputs"]["figure_dir"]).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    seed_dir.mkdir(parents=True, exist_ok=True)
    figure_dir.mkdir(parents=True, exist_ok=True)
    atomic_text(log_path, "")

    def log(message: str) -> None:
        line = f"{now()} {message}"
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        print(line, flush=True)

    write_progress(progress_path, "preflight", [], "started")
    targets = list(config["targets"])
    for path in source.values():
        if not path.exists():
            raise FileNotFoundError(rel(path))
    offset = np.asarray(json.loads(source["train_manifest"].read_text(encoding="utf-8"))["world_offset"], dtype=np.float64)
    if offset.shape != (3,) or not np.all(np.isfinite(offset)):
        raise RuntimeError("invalid world_offset")
    footprints = load_footprints(source["footprints"], targets)
    p0 = np.load(source["p0_fill_npz"], allow_pickle=False)
    sparse_xyz, sparse_rgb_u8, sparse_track = read_sparse_points(source["sparse_points"])
    dense_xyz = read_dense_xyz(source["dense_init"])
    scene_rgb = (sparse_rgb_u8.astype(np.float64).mean(axis=0) / 255.0).astype(np.float32)
    if not np.isfinite(scene_rgb).all():
        raise RuntimeError("scene mean RGB is not finite")
    log(f"preflight p0_sha={sha256_file(source['p0_fill_npz'])} scene_rgb={scene_rgb.tolist()} learning=0")

    surface_by_short: dict[str, np.ndarray] = {}
    fm_by_short: dict[str, np.ndarray] = {}
    plane_by_short: dict[str, np.ndarray] = {}
    plane_residual_by_short: dict[str, float] = {}
    anchor_by_short: dict[str, float] = {}
    seed_path_by_short: dict[str, Path] = {}
    seed_validation_by_short: dict[str, dict[str, Any]] = {}
    seed_rows: list[dict[str, Any]] = []
    completed: list[str] = []
    for short in targets:
        surface_key = config["canonical_surface"]["surface_key"].format(short=short)
        fm_key = config["canonical_surface"]["fm_key"].format(short=short)
        if surface_key not in p0.files or fm_key not in p0.files:
            raise RuntimeError(f"canonical keys missing for {short}")
        surface = np.asarray(p0[surface_key], dtype=np.float64)
        fm = np.asarray(p0[fm_key], dtype=np.float64)
        if surface.ndim != 2 or surface.shape[1] != 3 or not len(surface) or not np.isfinite(surface).all():
            raise RuntimeError(f"invalid canonical surface {short}")
        if fm.ndim != 2 or fm.shape[1] != 3 or not len(fm) or not np.isfinite(fm).all():
            raise RuntimeError(f"invalid FM anchor input {short}")
        plane, plane_residual = plane_from_surface(surface)
        if plane_residual > 1e-9:
            raise RuntimeError(f"canonical surface is not planar within lock: {short} residual={plane_residual}")
        anchor = float(np.median(fm[:, 2]))
        xyz = np.ascontiguousarray(surface, dtype="<f4")
        source_float32 = np.ascontiguousarray(surface.astype("<f4", copy=False))
        rgb = np.repeat(scene_rgb[None, :], len(xyz), axis=0).astype(np.float32, copy=False)
        sem = np.full(len(xyz), int(config["seed_contract"]["sem"]), dtype=np.int64)
        source_sha64 = array_payload_sha256(np.ascontiguousarray(surface))
        source_sha32 = array_payload_sha256(source_float32)
        metadata = metadata_for_seed(
            config, short, "p0_plane_fill", source["p0_fill_npz"], surface_key,
            source_sha64, plane, anchor, len(fm),
        )
        seed_path = seed_dir / f"DEBY_LOD2_{short}_p0_surface_seed.npz"
        atomic_deterministic_npz(seed_path, {
            "xyz": xyz,
            "rgb": rgb,
            "sem": sem,
            "metadata_json": np.asarray(json.dumps(metadata, ensure_ascii=False, sort_keys=True, separators=(",", ":"))),
        })
        validated = validate_seed_npz(seed_path, config)
        byte_equal = validated["xyz"].tobytes(order="C") == source_float32.tobytes(order="C")
        max_diff = float(np.max(np.abs(validated["xyz"].astype(np.float64) - source_float32.astype(np.float64))))
        quantization = float(np.max(np.abs(validated["xyz"].astype(np.float64) - surface)))
        if not byte_equal or max_diff != 0.0:
            raise RuntimeError(f"canonical seed equality failed: {short}")
        seed_rows.append({
            "building_id": f"DEBY_LOD2_{short}",
            "surface_lineage": "p0_plane_fill",
            "source_p0_npz": rel(source["p0_fill_npz"]),
            "source_p0_npz_sha256": sha256_file(source["p0_fill_npz"]),
            "source_surface_key": surface_key,
            "source_surface_dtype": str(surface.dtype),
            "source_surface_count": len(surface),
            "source_surface_payload_sha256": source_sha64,
            "canonical_float32_payload_sha256": source_sha32,
            "seed_npz": rel(seed_path),
            "seed_npz_sha256": sha256_file(seed_path),
            "seed_xyz_payload_sha256": array_payload_sha256(validated["xyz"]),
            "seed_xyz_byte_equal_canonical_float32": byte_equal,
            "seed_xyz_max_abs_diff_vs_canonical_float32_m": max_diff,
            "seed_xyz_max_abs_quantization_vs_source_float64_m": quantization,
            "fm_source_key": fm_key,
            "fm_inside_point_count": len(fm),
            "height_anchor_source": "all_footprint_inside_fm_z_median",
            "height_anchor_z_median_local_m": anchor,
            "plane_ax_local": plane[0],
            "plane_by_local": plane[1],
            "plane_c_local": plane[2],
            "canonical_plane_max_abs_residual_m": plane_residual,
            "grid_m": float(config["canonical_surface"]["grid_m"]),
            "seed_count": len(xyz),
            "sem": int(config["seed_contract"]["sem"]),
            "init_opacity": float(config["seed_contract"]["loader_derived_init_opacity"]),
            "scene_mean_rgb_r": scene_rgb[0],
            "scene_mean_rgb_g": scene_rgb[1],
            "scene_mean_rgb_b": scene_rgb[2],
            "bc_applicable": short in config["boundary_propagation"]["applicable_targets"],
            "bc_eligible_count": None,
            "bc_aux_seed_npz": "",
            "bc_aux_seed_count": 0,
            "footprint_role": "surface extent and target spatial mask only",
            "crs": config["crs"],
            "coordinate_frame": config["seed_contract"]["coordinate_frame"],
            "candidate_reference_inputs_loaded": False,
            "learning_runs_started": 0,
            "new_mast3r_inference_runs": 0,
            "status": "canonical_seed_prepared_boundary_pending",
        })
        atomic_csv(out_seed_csv, seed_rows, SEED_FIELDS)
        surface_by_short[short] = surface
        fm_by_short[short] = fm
        plane_by_short[short] = plane
        plane_residual_by_short[short] = plane_residual
        anchor_by_short[short] = anchor
        seed_path_by_short[short] = seed_path
        seed_validation_by_short[short] = validated
        completed.append(short)
        write_progress(progress_path, "canonical_seeds", completed, f"building_complete:{short}")
        log(f"canonical {short} N={len(xyz)} byte_equal={byte_equal} maxdiff={max_diff:.12g} anchor={anchor:.12f}")

    bc = config["boundary_propagation"]
    applicable = set(bc["applicable_targets"])
    band_m = float(bc["band_m"])
    height_tol = float(bc["height_tolerance_m"])
    boundary_rows: list[dict[str, Any]] = []
    boundary_plot: dict[str, dict[str, np.ndarray] | None] = {short: None for short in targets}
    depth_paths_used: set[Path] = set()
    completed = []
    cameras = read_cameras_bin(source["sparse_cameras"])
    images = read_images_bin(source["sparse_images"])
    for short in targets:
        if short not in applicable:
            boundary_rows.append({
                "row_type": "building_summary", "building_id": f"DEBY_LOD2_{short}",
                "bc_applicable": False, "source": "not_applicable_A_target", "band_width_m": band_m,
                "height_tolerance_m": height_tol, "candidate_count": 0, "multiview_pass_count": 0,
                "target_address_count": 0, "height_match_count": 0, "eligible_count": 0,
                "multiview_reject_count": 0, "non_target_address_count": 0, "height_mismatch_count": 0,
                "candidate_rule": bc["candidate_rule"], "target_spatial_address_rule": bc["target_spatial_address_rule"],
                "height_match_rule": bc["height_match_rule"], "multiview_rule": "not_applicable",
                "plane_source": "canonical P0 fill", "aux_seed_lineage": "none", "aux_seed_npz": "",
                "aux_seed_count": 0, "footprint_role": "target address mask only",
                "candidate_reference_inputs_loaded": False, "crs": config["crs"], "learning_runs_started": 0,
                "status": "not_applicable_A_target",
            })
            atomic_csv(out_boundary_csv, boundary_rows, BOUNDARY_FIELDS)
            seed_rows[targets.index(short)].update({"bc_eligible_count": 0, "status": "prepared"})
            atomic_csv(out_seed_csv, seed_rows, SEED_FIELDS)
            completed.append(short)
            write_progress(progress_path, "boundary_inventory", completed, f"building_complete:{short}")
            continue

        source_entries: list[dict[str, Any]] = []
        plot_parts = {key: [] for key in ("multiview_reject", "non_target", "height_mismatch", "eligible")}
        for source_name, all_points, source_mv_mask, mv_rule in (
            ("observed_sfm", sparse_xyz, None, bc["sparse_multiview_rule"]),
            ("observed_dense_init", dense_xyz, None, bc["dense_multiview_rule"]),
        ):
            candidate_index, _distance = point_band_candidates(all_points, footprints[short], offset, band_m)
            candidates = all_points[candidate_index]
            if source_name == "observed_sfm":
                multiview = sparse_track[candidate_index] >= 2
            else:
                visibility, used = dense_visibility_counts(
                    candidates, cameras, images, source["depth_maps"],
                    float(bc["dense_visibility_abs_tolerance_m"]),
                    float(bc["dense_visibility_relative_tolerance"]),
                )
                depth_paths_used.update(used)
                multiview = visibility >= int(bc["dense_min_views"])
            target_address = footprint_covers_mask(candidates, footprints[short], offset)
            plane = plane_by_short[short]
            predicted = plane[0] * candidates[:, 0] + plane[1] * candidates[:, 1] + plane[2]
            abs_residual = np.abs(candidates[:, 2] - predicted)
            height_match = abs_residual <= height_tol
            eligible = multiview & target_address & height_match
            multiview_reject = ~multiview
            non_target = multiview & ~target_address
            height_mismatch = multiview & target_address & ~height_match
            plot_parts["multiview_reject"].append(candidates[multiview_reject])
            plot_parts["non_target"].append(candidates[non_target])
            plot_parts["height_mismatch"].append(candidates[height_mismatch])
            plot_parts["eligible"].append(candidates[eligible])
            eligible_residual = abs_residual[eligible]
            median = float(np.median(eligible_residual)) if len(eligible_residual) else None
            mad = float(np.median(np.abs(eligible_residual - median))) if median is not None else None
            row = {
                "row_type": "source", "building_id": f"DEBY_LOD2_{short}", "bc_applicable": True,
                "source": source_name, "band_width_m": band_m, "height_tolerance_m": height_tol,
                "candidate_count": len(candidates), "multiview_pass_count": int(multiview.sum()),
                "target_address_count": int((multiview & target_address).sum()),
                "height_match_count": int((multiview & height_match).sum()), "eligible_count": int(eligible.sum()),
                "multiview_reject_count": int(multiview_reject.sum()), "non_target_address_count": int(non_target.sum()),
                "height_mismatch_count": int(height_mismatch.sum()),
                "eligible_height_residual_abs_median_m": median,
                "eligible_height_residual_abs_mad_m": mad,
                "candidate_rule": bc["candidate_rule"], "target_spatial_address_rule": bc["target_spatial_address_rule"],
                "height_match_rule": bc["height_match_rule"], "multiview_rule": mv_rule,
                "plane_source": "canonical P0 fill; FM anchored", "aux_seed_lineage": "observed_boundary_height_matched",
                "aux_seed_npz": "", "aux_seed_count": 0, "footprint_role": "target address mask only",
                "candidate_reference_inputs_loaded": False, "crs": config["crs"], "learning_runs_started": 0,
                "status": "classified",
            }
            boundary_rows.append(row)
            source_entries.append({"row": row, "points": candidates[eligible], "source_code": 0 if source_name == "observed_sfm" else 1})
            atomic_csv(out_boundary_csv, boundary_rows, BOUNDARY_FIELDS)

        eligible_parts = [entry["points"] for entry in source_entries if len(entry["points"])]
        eligible_points = np.concatenate(eligible_parts, axis=0) if eligible_parts else np.empty((0, 3), dtype=np.float64)
        aux_path: Path | None = None
        if len(eligible_points):
            aux_path = seed_dir / f"DEBY_LOD2_{short}_bc_aux_seed.npz"
            aux_metadata = metadata_for_seed(
                config, short, "observed_boundary_height_matched", source["p0_fill_npz"],
                config["canonical_surface"]["surface_key"].format(short=short),
                array_payload_sha256(surface_by_short[short]), plane_by_short[short], anchor_by_short[short], len(fm_by_short[short]),
            )
            aux_metadata.pop("source_npz", None)
            aux_metadata.pop("source_key", None)
            aux_metadata.pop("source_npz_sha256", None)
            aux_metadata.pop("source_array_payload_sha256", None)
            aux_metadata.update({
                "boundary_band_m": band_m,
                "plane_height_match_tolerance_m": height_tol,
                "spatial_scope": "target_footprint_boundary_band_inside_only",
                "lineage": {
                    "kind": "observed_boundary_height_matched",
                    "ordered_source_blocks": [
                        {
                            "source": entry["row"]["source"],
                            "count": int(len(entry["points"])),
                        }
                        for entry in source_entries
                    ],
                    "plane_filter_artifact": rel(source["p0_fill_npz"]),
                    "plane_filter_surface_array": config["canonical_surface"]["surface_key"].format(short=short),
                    "height_tolerance_m": height_tol,
                },
            })
            aux_xyz = np.ascontiguousarray(eligible_points, dtype=np.float32)
            atomic_deterministic_npz(aux_path, {
                "xyz": aux_xyz,
                "rgb": np.repeat(scene_rgb[None, :], len(aux_xyz), axis=0).astype(np.float32),
                "sem": np.full(len(aux_xyz), int(config["seed_contract"]["sem"]), dtype=np.int64),
                "metadata_json": np.asarray(json.dumps(aux_metadata, ensure_ascii=False, sort_keys=True, separators=(",", ":"))),
            })
            validate_seed_npz(aux_path, config)
        for entry in source_entries:
            entry["row"].update({
                "aux_seed_npz": rel(aux_path) if aux_path else "",
                "aux_seed_count": len(eligible_points),
            })
        eligible_residual_all = np.abs(
            eligible_points[:, 2]
            - (plane_by_short[short][0] * eligible_points[:, 0]
               + plane_by_short[short][1] * eligible_points[:, 1]
               + plane_by_short[short][2])
        ) if len(eligible_points) else np.empty(0)
        median_all = float(np.median(eligible_residual_all)) if len(eligible_residual_all) else None
        mad_all = float(np.median(np.abs(eligible_residual_all - median_all))) if median_all is not None else None
        summary = {
            "row_type": "building_summary", "building_id": f"DEBY_LOD2_{short}", "bc_applicable": True,
            "source": "observed_sfm_plus_dense", "band_width_m": band_m, "height_tolerance_m": height_tol,
            "candidate_count": sum(entry["row"]["candidate_count"] for entry in source_entries),
            "multiview_pass_count": sum(entry["row"]["multiview_pass_count"] for entry in source_entries),
            "target_address_count": sum(entry["row"]["target_address_count"] for entry in source_entries),
            "height_match_count": sum(entry["row"]["height_match_count"] for entry in source_entries),
            "eligible_count": len(eligible_points),
            "multiview_reject_count": sum(entry["row"]["multiview_reject_count"] for entry in source_entries),
            "non_target_address_count": sum(entry["row"]["non_target_address_count"] for entry in source_entries),
            "height_mismatch_count": sum(entry["row"]["height_mismatch_count"] for entry in source_entries),
            "eligible_height_residual_abs_median_m": median_all,
            "eligible_height_residual_abs_mad_m": mad_all,
            "candidate_rule": bc["candidate_rule"], "target_spatial_address_rule": bc["target_spatial_address_rule"],
            "height_match_rule": bc["height_match_rule"],
            "multiview_rule": f"{bc['sparse_multiview_rule']}; {bc['dense_multiview_rule']}",
            "plane_source": "canonical P0 fill; FM anchored", "aux_seed_lineage": "observed_boundary_height_matched" if len(eligible_points) else "none",
            "aux_seed_npz": rel(aux_path) if aux_path else "", "aux_seed_count": len(eligible_points),
            "footprint_role": "target address mask only", "candidate_reference_inputs_loaded": False,
            "crs": config["crs"], "learning_runs_started": 0,
            "status": "aux_seed_prepared" if len(eligible_points) else "eligible_zero_no_aux_seed",
        }
        boundary_rows.append(summary)
        atomic_csv(out_boundary_csv, boundary_rows, BOUNDARY_FIELDS)
        plot_parts_final = {
            key: np.concatenate(values, axis=0) if values else np.empty((0, 3), dtype=np.float64)
            for key, values in plot_parts.items()
        }
        boundary_plot[short] = plot_parts_final
        seed_row = seed_rows[targets.index(short)]
        seed_row.update({
            "bc_eligible_count": len(eligible_points),
            "bc_aux_seed_npz": rel(aux_path) if aux_path else "",
            "bc_aux_seed_count": len(eligible_points),
            "status": "prepared",
        })
        atomic_csv(out_seed_csv, seed_rows, SEED_FIELDS)
        completed.append(short)
        write_progress(progress_path, "boundary_inventory", completed, f"building_complete:{short}")
        log(f"boundary {short} candidates={summary['candidate_count']} multiview={summary['multiview_pass_count']} target={summary['target_address_count']} eligible={len(eligible_points)}")

    figure_paths: list[Path] = []
    completed = []
    for short in targets:
        figure_path = figure_dir / f"seedprep_{short}.png"
        validation = seed_validation_by_short[short]
        source_float32 = np.ascontiguousarray(surface_by_short[short], dtype=np.float32)
        seed_xyz = validation["xyz"]
        byte_equal = seed_xyz.tobytes(order="C") == source_float32.tobytes(order="C")
        max_diff = float(np.max(np.abs(seed_xyz.astype(np.float64) - source_float32.astype(np.float64))))
        make_building_figure(
            figure_path, short, footprints[short], offset, surface_by_short[short], seed_xyz,
            fm_by_short[short], boundary_plot[short], byte_equal, max_diff, band_m,
        )
        figure_paths.append(figure_path)
        completed.append(short)
        write_progress(progress_path, "figures", completed, f"building_complete:{short}")

    # Hash the exact depth maps actually used by dense multiview classification.
    depth_inventory_lines = [f"{rel(path)}|{sha256_file(path)}" for path in sorted(depth_paths_used)]
    depth_inventory_sha = sha256_bytes(("\n".join(depth_inventory_lines) + "\n").encode("utf-8"))
    log(f"depth_inventory files={len(depth_paths_used)} aggregate_sha256={depth_inventory_sha}")
    write_progress(progress_path, "complete", targets, "complete")
    log("complete learning=0 new_mast3r_inference=0 candidate_reference_inputs_loaded=false")

    source_paths = [
        config_path, Path(__file__).resolve(), source["p0_fill_npz"], source["footprints"],
        source["train_manifest"], source["sparse_points"], source["sparse_cameras"],
        source["sparse_images"], source["dense_init"], source["engine_seed_loader"],
    ]
    output_paths = [out_seed_csv, out_boundary_csv, progress_path, log_path, *seed_path_by_short.values(), *figure_paths]
    for row in seed_rows:
        if row.get("bc_aux_seed_npz"):
            output_paths.append(REPO / str(row["bc_aux_seed_npz"]))
    source_commit = subprocess.check_output(
        ["git", "log", "-n", "1", "--format=%H", "--", rel(source["p0_fill_npz"])],
        cwd=REPO, text=True,
    ).strip()
    manifest = {
        "schema": "jointbuildgs.s3ap.phase1.seedprep.v1",
        "created_utc": now(),
        "git_head_at_generation": git_value("rev-parse", "HEAD"),
        "branch": git_value("branch", "--show-current"),
        "phase0_p0_source_commit": source_commit,
        "targets": targets,
        "crs": config["crs"],
        "world_offset": offset.tolist(),
        "learning_runs_started": 0,
        "new_mast3r_inference_runs": 0,
        "candidate_reference_inputs_loaded": False,
        "candidate_generation_inputs": [
            rel(source["p0_fill_npz"]), rel(source["footprints"]), rel(source["sparse_points"]),
            rel(source["dense_init"]), rel(source["sparse_cameras"]), rel(source["sparse_images"]),
            "existing PatchMatch depth maps for dense multiview visibility only",
        ],
        "footprint_role": "canonical P0 extent inherited; target spatial address mask for B-c",
        "canonical_surface": config["canonical_surface"],
        "seed_contract": config["seed_contract"],
        "engine_loader_contract_sha256": sha256_file(source["engine_seed_loader"]),
        "boundary_propagation": config["boundary_propagation"],
        "canonical_equality": {
            row["building_id"]: {
                "source_float32_payload_sha256": row["canonical_float32_payload_sha256"],
                "seed_xyz_payload_sha256": row["seed_xyz_payload_sha256"],
                "byte_equal": row["seed_xyz_byte_equal_canonical_float32"],
                "max_abs_diff_m": row["seed_xyz_max_abs_diff_vs_canonical_float32_m"],
            }
            for row in seed_rows
        },
        "depth_map_inventory": {
            "used_file_count": len(depth_paths_used),
            "path_and_content_sha256_aggregate": depth_inventory_sha,
            "aggregation": "sha256(newline-joined sorted repo-relative-path|file-sha256 records plus terminal newline)",
        },
        "docker": config["docker"],
        "versions": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "matplotlib": matplotlib.__version__,
        },
        "source_sha256": {rel(path): sha256_file(path) for path in source_paths},
        "output_sha256": {rel(path): sha256_file(path) for path in sorted(set(output_paths))},
        "interpretation_or_verdict": None,
    }
    atomic_text(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(f"wrote {rel(out_seed_csv)} rows={len(seed_rows)}")
    print(f"wrote {rel(out_boundary_csv)} rows={len(boundary_rows)}")
    print(f"wrote {rel(manifest_path)}")


if __name__ == "__main__":
    main()
