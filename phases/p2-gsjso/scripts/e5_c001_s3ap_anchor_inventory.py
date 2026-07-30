#!/usr/bin/env python3
"""S3-A-prime learning-zero boundary-geometry inventory.

This script measures two independent sources around the locked textureless
three buildings.  It never trains, seeds, filters with LoD2, or mutates a
checkpoint.  LoD2 roof z is loaded only after candidates have been selected
and is used solely for the reported absolute z error.

Canonical invocation (repository root)::

    docker run --rm --user "$(id -u):$(id -g)" --gpus all \
      -e HOME=/tmp -e MPLCONFIGDIR=/tmp/matplotlib -e XDG_CACHE_HOME=/tmp \
      -v "$PWD:/workspace/JointBuildGS" -w /workspace/JointBuildGS \
      jointbuildgs:dev python \
      phases/p2-gsjso/scripts/e5_c001_s3ap_anchor_inventory.py

Observed-point multiview rule
-----------------------------
* COLMAP sparse points: track length >= 2.
* Dense initialization points: project into all 428 locked COLMAP cameras;
  count a view when the point is in-frame, in front of the camera, and agrees
  with that view's existing PatchMatch depth within max(0.50 m, 2% depth).
  A point passes when at least two views agree.

Ground rule
-----------
"5 m ring" is implemented as the exterior footprint ring
``footprint.buffer(5 m) - footprint``.  The reported ground is the q10 of the
combined sparse+dense observed points in that ring.  This explicit exterior
interpretation prevents roof points inside larger footprints from becoming
the ground estimator.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import struct
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp")

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from PIL import Image as PILImage  # noqa: E402
from shapely import contains_xy, make_valid  # noqa: E402
from shapely.geometry import MultiPolygon, Polygon, shape  # noqa: E402
from shapely.ops import unary_union  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
SCRIPT_DIR = Path(__file__).resolve().parent
PYDEPS = REPO / "results/tum_transfer/e5_s1_full_factor/C001/python_deps/timm_0_4_12"
for path in (PYDEPS, SCRIPT_DIR, REPO):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import e5_c001_8way as eight  # noqa: E402
from src.stage2.colmap_io import read_array  # noqa: E402
from src.stage2.dataloader import ColmapDataset  # noqa: E402


RUN_ID = "20260714_e5_c001_s3ap_anchor_inventory"
RUN_DIR = REPO / "phases/p2-gsjso/runs" / RUN_ID
DATA_ROOT = REPO / "results/tum_transfer/e5_pilot/C001/data_geoidfix_C001_buf20"
SPARSE = DATA_ROOT / "sparse/0/points3D.bin"
DENSE = REPO / "results/tum_transfer/e5_pilot/C001/seeds/seed_dense_C001_buf20.ply"
FOOTPRINTS = REPO / "results/tum_transfer/analysis/footprints_aoi.geojson"
TRAIN_MANIFEST = REPO / "results/tum_transfer/e5_pilot/C001/C001_train_prep_manifest.json"
DATUM_CONFIG = REPO / "configs/input_and_alignment/projection_datum.json"
PJPL = (
    REPO
    / "results/tum_transfer/e5_s3_semantic_guided/C001/runs"
    / "gs_e5_C001_s3a_semantic_guided_gate/audit/pjpl_depth_anchor_views.csv"
)
CKPT_ROOT = REPO / "results/tum_transfer/e5_s2p_interaction/C001/runs"
CKPTS = {
    "render_arm1p_r1": CKPT_ROOT / "gs_e5_C001_s2p_arm1p_dense_r1/ckpt/final.pt",
    "render_arm1p_r2": CKPT_ROOT / "gs_e5_C001_s2p_arm1p_dense_r2/ckpt/final.pt",
}
OUT_CSV = REPO / "docs/experiments/input-and-alignment/e5_c001_s3ap/tables/e5_c001_s3ap_anchor_inventory.csv"
FIG_DIR = REPO / "docs/figs/e5_c001_s3ap_anchor_inventory"
MANIFEST = RUN_DIR / "manifest.json"
VIEW_CSV = RUN_DIR / "render_view_inventory.csv"

TARGETS = ["4907199", "8568391", "8568392"]
BANDS = [0.5, 1.0, 1.5]
ALPHA_THRESHOLD = 0.5
GROUND_RING_M = 5.0
UPPER_OFFSET_M = 1.5
DENSE_ABS_TOL_M = 0.50
DENSE_REL_TOL = 0.02


@dataclass(frozen=True)
class SparsePoint:
    xyz: tuple[float, float, float]
    track_len: int


def full_id(short: str) -> str:
    return short if short.startswith("DEBY_LOD2_") else f"DEBY_LOD2_{short}"


def rel(path: Path | str) -> str:
    path = Path(path)
    try:
        return str(path.resolve().relative_to(REPO.resolve()))
    except ValueError:
        return str(path.resolve())


def sha256_file(path: Path, block_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: Sequence[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        fields = list(rows[0]) if rows else []
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def git_value(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO, text=True).strip()


def load_world_offset() -> np.ndarray:
    payload = json.loads(TRAIN_MANIFEST.read_text(encoding="utf-8"))
    value = np.asarray(payload["world_offset"], dtype=np.float64)
    if value.shape != (3,) or not np.all(np.isfinite(value)):
        raise RuntimeError(f"invalid world offset: {value!r}")
    return value


def load_geoid() -> float:
    payload = json.loads(DATUM_CONFIG.read_text(encoding="utf-8"))
    if payload.get("geo_crs") != "EPSG:25832":
        raise RuntimeError("anchor inventory requires EPSG:25832")
    return float(payload["orthometric_geoid_m"])


def load_footprints() -> dict[str, Polygon | MultiPolygon]:
    payload = json.loads(FOOTPRINTS.read_text(encoding="utf-8"))
    crs = str(payload.get("crs", {}).get("properties", {}).get("name", ""))
    if "25832" not in crs:
        raise RuntimeError(f"footprint CRS is not EPSG:25832: {crs!r}")
    pieces: dict[str, list[Any]] = defaultdict(list)
    wanted = {full_id(short) for short in TARGETS}
    for feature in payload["features"]:
        bid = str((feature.get("properties") or {}).get("building_id", ""))
        if bid not in wanted:
            continue
        geom = make_valid(shape(feature["geometry"]))
        if not geom.is_empty:
            pieces[bid].append(geom)
    out: dict[str, Polygon | MultiPolygon] = {}
    for bid in sorted(wanted):
        geom = make_valid(unary_union(pieces[bid]))
        if not isinstance(geom, (Polygon, MultiPolygon)) or geom.is_empty:
            raise RuntimeError(f"missing polygonal footprint: {bid}")
        out[bid] = geom
    return out


def _read(handle: Any, fmt: str) -> tuple[Any, ...]:
    size = struct.calcsize(fmt)
    data = handle.read(size)
    if len(data) != size:
        raise EOFError("unexpected COLMAP points3D EOF")
    return struct.unpack(fmt, data)


def read_sparse_with_tracks(path: Path) -> tuple[np.ndarray, np.ndarray]:
    xyz: list[tuple[float, float, float]] = []
    tracks: list[int] = []
    with path.open("rb") as handle:
        count = int(_read(handle, "<Q")[0])
        for _ in range(count):
            _point_id = _read(handle, "<Q")[0]
            xyz.append(tuple(float(v) for v in _read(handle, "<ddd")))
            _rgb = _read(handle, "<BBB")
            _error = _read(handle, "<d")[0]
            track_len = int(_read(handle, "<Q")[0])
            handle.seek(8 * track_len, 1)
            tracks.append(track_len)
    return np.asarray(xyz, dtype=np.float32), np.asarray(tracks, dtype=np.int32)


def read_dense(path: Path) -> np.ndarray:
    header = 0
    count: int | None = None
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            header += 1
            if line.startswith("element vertex "):
                count = int(line.split()[-1])
            if line.strip() == "end_header":
                break
    if count is None:
        raise RuntimeError("dense PLY vertex count missing")
    xyz = np.loadtxt(path, skiprows=header, max_rows=count, usecols=(0, 1, 2), dtype=np.float32)
    xyz = np.asarray(xyz, dtype=np.float32).reshape(-1, 3)
    if len(xyz) != count:
        raise RuntimeError(f"dense PLY count mismatch: {len(xyz)} != {count}")
    return xyz


def points_in_geom(points_local: np.ndarray, geom: Any, offset: np.ndarray) -> np.ndarray:
    x = points_local[:, 0].astype(np.float64) + float(offset[0])
    y = points_local[:, 1].astype(np.float64) + float(offset[1])
    minx, miny, maxx, maxy = geom.bounds
    bbox = (x >= minx) & (x <= maxx) & (y >= miny) & (y <= maxy)
    idx = np.flatnonzero(bbox)
    out = np.zeros(len(points_local), dtype=bool)
    if len(idx):
        out[idx] = contains_xy(geom, x[idx], y[idx])
    return out


def boundary_distance(points_local: np.ndarray, footprint: Any, offset: np.ndarray) -> np.ndarray:
    # Only a small bbox subset reaches this function; scalar boundary.distance
    # is stable across the Shapely versions in the frozen image.
    from shapely.geometry import Point

    x = points_local[:, 0].astype(np.float64) + float(offset[0])
    y = points_local[:, 1].astype(np.float64) + float(offset[1])
    return np.asarray([footprint.boundary.distance(Point(float(px), float(py))) for px, py in zip(x, y)], dtype=np.float64)


@lru_cache(maxsize=None)
def load_depth_for_frame(frame_name: str) -> np.ndarray | None:
    paths = [
        DATA_ROOT / "stereo/depth_maps" / f"{frame_name}.geometric.bin",
        DATA_ROOT / "stereo/depth_maps" / f"{frame_name}.photometric.bin",
    ]
    for path in paths:
        if path.exists():
            return np.asarray(read_array(path), dtype=np.float32)
    return None


def dense_visibility_count(points_local: np.ndarray, ds: ColmapDataset) -> np.ndarray:
    counts = np.zeros(len(points_local), dtype=np.int16)
    if not len(points_local):
        return counts
    hom = np.column_stack([points_local.astype(np.float64), np.ones(len(points_local))])
    for frame in ds.frames:
        depth_map = load_depth_for_frame(frame.name)
        if depth_map is None:
            continue
        w2c = np.eye(4, dtype=np.float64)
        w2c[:3, :3] = frame.R
        w2c[:3, 3] = frame.t
        cam = (w2c @ hom.T).T[:, :3]
        z = cam[:, 2]
        uvw = (frame.K @ cam.T).T
        uv = uvw[:, :2] / np.maximum(uvw[:, 2:3], 1e-12)
        # PatchMatch maps retain their own COLMAP processing resolution, which
        # can differ from the camera/image resolution.  Dataloader normally
        # resizes the map to the frame; for this point sample, map the projected
        # pixel into the native depth raster instead.
        u = np.rint(uv[:, 0] * depth_map.shape[1] / float(frame.width)).astype(np.int64)
        v = np.rint(uv[:, 1] * depth_map.shape[0] / float(frame.height)).astype(np.int64)
        valid = np.isfinite(uv).all(axis=1) & np.isfinite(z) & (z > 0)
        valid &= (u >= 0) & (u < depth_map.shape[1]) & (v >= 0) & (v < depth_map.shape[0])
        idx = np.flatnonzero(valid)
        if not len(idx):
            continue
        measured = depth_map[v[idx], u[idx]].astype(np.float64)
        tol = np.maximum(DENSE_ABS_TOL_M, DENSE_REL_TOL * np.abs(z[idx]))
        agrees = np.isfinite(measured) & (measured > 0) & (np.abs(measured - z[idx]) <= tol)
        counts[idx[agrees]] += 1
    return counts


def iter_polygons(geom: Polygon | MultiPolygon) -> Iterator[Polygon]:
    if isinstance(geom, Polygon):
        yield geom
    else:
        yield from geom.geoms


def ref_roof_z_local(refs: list[eight.RoofSurface], offset: np.ndarray, geoid: float) -> float:
    values: list[float] = []
    for surface in refs:
        for polygon in iter_polygons(surface.polygon):
            xy = np.asarray(polygon.exterior.coords, dtype=np.float64)[:, :2]
            values.extend(surface.z_at(xy[:, 0], xy[:, 1]).tolist())
    if not values:
        raise RuntimeError("reference roof z is empty")
    return float(np.median(values) + geoid - offset[2])


def load_pjpl_views() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {short: [] for short in TARGETS}
    for row in read_csv(PJPL):
        short = row["building_id"]
        if short in out:
            out[short].append(row["view_stem"])
    expected = {"4907199": 6, "8568391": 3, "8568392": 3}
    for short, count in expected.items():
        if len(out[short]) != count or len(set(out[short])) != count:
            raise RuntimeError(f"P-J/P-L view drift for {short}: {out[short]}")
    return out


def make_model_from_state(state: dict[str, Any], device: Any) -> Any:
    import torch
    from src.stage2.model import GaussianModel2D

    model = GaussianModel2D.__new__(GaussianModel2D)
    torch.nn.Module.__init__(model)
    n_sh = int(state["sh0"].shape[1] + state["shN"].shape[1])
    sh_degree = int(round(math.sqrt(n_sh) - 1))
    model.sh_degree = sh_degree
    model.max_sh_degree = sh_degree
    model.active_sh_degree = sh_degree
    model.num_classes = int(state.get("sem_logits").shape[-1]) if "sem_logits" in state else 4
    for key in ["means", "quats", "log_scales", "opacities_raw", "sh0", "shN", "sem_logits"]:
        if key in state:
            setattr(model, key, torch.nn.Parameter(state[key].to(device).float(), requires_grad=False))
    model.eval()
    return model


def project_utm(points_utm_localz: np.ndarray, frame: Any, offset: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    local = np.asarray(points_utm_localz, dtype=np.float64).copy()
    local[:, 0] -= offset[0]
    local[:, 1] -= offset[1]
    camera = (frame.R @ local.T).T + frame.t.reshape(1, 3)
    uvw = (frame.K @ camera.T).T
    uv = uvw[:, :2] / np.maximum(uvw[:, 2:3], 1e-12)
    return uv, camera[:, 2]


def densify_boundary(footprint: Any, z_local: float, max_step: float = 0.20) -> np.ndarray:
    chunks: list[np.ndarray] = []
    for polygon in iter_polygons(footprint):
        coords = np.asarray(polygon.exterior.coords, dtype=np.float64)[:, :2]
        rows: list[np.ndarray] = []
        for a, b in zip(coords[:-1], coords[1:]):
            n = max(2, int(math.ceil(np.linalg.norm(b - a) / max_step)) + 1)
            t = np.linspace(0.0, 1.0, n, endpoint=False)
            rows.append(a[None, :] * (1.0 - t[:, None]) + b[None, :] * t[:, None])
        if rows:
            xy = np.vstack(rows)
            chunks.append(np.column_stack([xy, np.full(len(xy), z_local)]))
    return np.vstack(chunks)


def render_crop_bounds(footprint: Any, z_local: float, frame: Any, offset: np.ndarray) -> tuple[int, int, int, int]:
    ring = densify_boundary(footprint.buffer(2.0), z_local, max_step=0.30)
    uv, depth = project_utm(ring, frame, offset)
    valid = np.isfinite(uv).all(axis=1) & np.isfinite(depth) & (depth > 0)
    if not np.any(valid):
        raise RuntimeError(f"cannot project crop for {frame.name}")
    xy = uv[valid]
    margin = 24
    x0 = max(0, int(math.floor(float(xy[:, 0].min()))) - margin)
    y0 = max(0, int(math.floor(float(xy[:, 1].min()))) - margin)
    x1 = min(int(frame.width), int(math.ceil(float(xy[:, 0].max()))) + margin + 1)
    y1 = min(int(frame.height), int(math.ceil(float(xy[:, 1].max()))) + margin + 1)
    if x1 <= x0 or y1 <= y0:
        raise RuntimeError(f"empty projected crop for {frame.name}")
    return x0, y0, x1, y1


def unproject_crop(depth: np.ndarray, alpha: np.ndarray, frame: Any, crop: tuple[int, int, int, int]) -> np.ndarray:
    x0, y0, _x1, _y1 = crop
    valid = np.isfinite(depth) & np.isfinite(alpha) & (depth > 0) & (alpha >= ALPHA_THRESHOLD)
    v, u = np.nonzero(valid)
    if not len(u):
        return np.zeros((0, 3), dtype=np.float64)
    z = depth[v, u].astype(np.float64)
    uu = u.astype(np.float64) + x0
    vv = v.astype(np.float64) + y0
    fx, fy = float(frame.K[0, 0]), float(frame.K[1, 1])
    cx, cy = float(frame.K[0, 2]), float(frame.K[1, 2])
    camera = np.column_stack([(uu - cx) / fx * z, (vv - cy) / fy * z, z])
    world = (frame.R.T @ (camera - frame.t.reshape(1, 3)).T).T
    return world


def finite_stats(values: np.ndarray) -> tuple[float | None, float | None, float | None]:
    values = np.asarray(values, dtype=np.float64)
    values = values[np.isfinite(values)]
    if not len(values):
        return None, None, None
    median = float(np.median(values))
    mad = float(np.median(np.abs(values - median)))
    std = float(np.std(values))
    return median, mad, std


def fmt(value: Any, digits: int = 6) -> Any:
    if value is None:
        return ""
    if isinstance(value, (float, np.floating)):
        if not math.isfinite(float(value)):
            return ""
        return f"{float(value):.{digits}f}"
    return value


def measure_observed(
    short: str,
    footprint: Any,
    sparse: np.ndarray,
    sparse_tracks: np.ndarray,
    dense: np.ndarray,
    offset: np.ndarray,
    ds: ColmapDataset,
    ground_z: float,
    ref_z: float,
) -> tuple[list[dict[str, Any]], dict[str, np.ndarray]]:
    outer = footprint.buffer(max(BANDS) + 0.05)
    sparse_bbox = points_in_geom(sparse, outer, offset)
    dense_bbox = points_in_geom(dense, outer, offset)
    sparse_cand = sparse[sparse_bbox]
    dense_cand = dense[dense_bbox]
    sparse_dist = boundary_distance(sparse_cand, footprint, offset)
    dense_dist = boundary_distance(dense_cand, footprint, offset)
    sparse_pass = sparse_tracks[sparse_bbox] >= 2
    dense_views = dense_visibility_count(dense_cand, ds)
    dense_pass = dense_views >= 2
    all_points = np.vstack([sparse_cand, dense_cand])
    all_dist = np.concatenate([sparse_dist, dense_dist])
    all_pass = np.concatenate([sparse_pass, dense_pass])
    rows: list[dict[str, Any]] = []
    selected_overlay: dict[str, np.ndarray] = {}
    for band in BANDS:
        eligible = all_dist <= band
        selected = eligible & all_pass
        upper = selected & (all_points[:, 2] >= ground_z + UPPER_OFFSET_M)
        z50, zmad, zstd = finite_stats(all_points[upper, 2])
        denominator = int(np.count_nonzero(eligible))
        rows.append(
            {
                "building_id": full_id(short),
                "band_width_m": band,
                "source": "observed_sfm_plus_dense",
                "source_role": "measurement_input_only",
                "view_aggregation": "not_applicable_point_inventory",
                "visible_view_count": "",
                "upper_nonempty_view_count": "",
                "visible_views": "",
                "all_count": int(np.count_nonzero(selected)),
                "upper_count": int(np.count_nonzero(upper)),
                "upper_z_median_local_m": z50,
                "upper_z_mad_m": zmad,
                "upper_z_std_m": zstd,
                "ground_z_q10_local_m": ground_z,
                "reference_roof_z_local_m": ref_z,
                "abs_delta_z_ref_m": abs(z50 - ref_z) if z50 is not None else None,
                "multiview_candidate_count": denominator,
                "multiview_pass_count": int(np.count_nonzero(selected)),
                "multiview_pass_rate": float(np.count_nonzero(selected) / denominator) if denominator else None,
                "multiview_method": (
                    "SfM COLMAP track_len>=2; dense-init reprojection to 428 locked poses with existing "
                    "PatchMatch depth agreement abs<=max(0.50m,0.02*camera_z), visible_views>=2"
                ),
                "alpha_threshold": "",
                "per_view_all_counts": "",
                "per_view_upper_counts": "",
                "crs": "EPSG:25832",
                "z_frame": "GS-local ellipsoidal",
                "gt_role": "reference roof z used only after candidate selection for abs_delta_z_ref_m",
            }
        )
        if math.isclose(band, 1.0):
            selected_overlay["all"] = all_points[selected]
            selected_overlay["upper"] = all_points[upper]
    return rows, selected_overlay


def render_sources(
    footprints: dict[str, Any],
    refs_z: dict[str, float],
    views: dict[str, list[str]],
    ds: ColmapDataset,
    offset: np.ndarray,
    device_name: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, dict[str, dict[str, np.ndarray]]]]:
    import torch
    from src.stage2.renderer import render

    device = torch.device(device_name)
    frame_by_stem = {Path(frame.name).stem: frame for frame in ds.frames}
    dataset_idx = {Path(frame.name).stem: idx for idx, frame in enumerate(ds.frames)}
    rows: list[dict[str, Any]] = []
    view_rows: list[dict[str, Any]] = []
    overlay: dict[str, dict[str, dict[str, np.ndarray]]] = defaultdict(dict)
    for source, ckpt in CKPTS.items():
        payload = torch.load(ckpt, map_location="cpu", weights_only=False)
        model = make_model_from_state(payload["state_dict"], device)
        for short in TARGETS:
            footprint = footprints[full_id(short)]
            per_band: dict[float, list[dict[str, Any]]] = {band: [] for band in BANDS}
            for stem in views[short]:
                frame = frame_by_stem[stem]
                idx = dataset_idx[stem]
                crop = render_crop_bounds(footprint, refs_z[short], frame, offset)
                x0, y0, x1, y1 = crop
                batch = ds[idx]
                K_crop = batch["K"].clone()
                K_crop[0, 2] -= x0
                K_crop[1, 2] -= y0
                with torch.no_grad():
                    rendered = render(
                        model,
                        batch["w2c"].to(device),
                        K_crop.to(device),
                        x1 - x0,
                        y1 - y0,
                        sh_degree=model.active_sh_degree,
                        render_mode="RGB+ED",
                    )
                depth = rendered["depth"].detach().cpu().numpy()
                alpha = rendered["alpha"].detach().cpu().numpy()
                world = unproject_crop(depth, alpha, frame, crop)
                world_utm = world.copy()
                if len(world_utm):
                    world_utm[:, 0] += offset[0]
                    world_utm[:, 1] += offset[1]
                    distance = boundary_distance(world, footprint, offset)
                else:
                    distance = np.zeros(0, dtype=np.float64)
                for band in BANDS:
                    chosen = distance <= band
                    upper = chosen & (world[:, 2] >= ground_by_short[short] + UPPER_OFFSET_M)
                    z50, zmad, zstd = finite_stats(world[upper, 2])
                    item = {
                        "building_id": full_id(short),
                        "band_width_m": band,
                        "source": source,
                        "view_stem": stem,
                        "all_count": int(np.count_nonzero(chosen)),
                        "upper_count": int(np.count_nonzero(upper)),
                        "upper_z_median_local_m": z50,
                        "upper_z_mad_m": zmad,
                        "upper_z_std_m": zstd,
                        "ground_z_q10_local_m": ground_by_short[short],
                        "reference_roof_z_local_m": refs_z[short],
                        "abs_delta_z_ref_m": abs(z50 - refs_z[short]) if z50 is not None else None,
                        "alpha_threshold": ALPHA_THRESHOLD,
                        "crop_xyxy": ";".join(str(v) for v in crop),
                    }
                    per_band[band].append(item)
                    view_rows.append({key: fmt(value) for key, value in item.items()})
                    if math.isclose(band, 1.0):
                        overlay[short].setdefault(source, {})[stem] = world[upper]
            for band in BANDS:
                items = per_band[band]
                all_counts = np.asarray([item["all_count"] for item in items], dtype=np.float64)
                upper_counts = np.asarray([item["upper_count"] for item in items], dtype=np.float64)
                z_values = np.asarray(
                    [item["upper_z_median_local_m"] for item in items if item["upper_z_median_local_m"] is not None],
                    dtype=np.float64,
                )
                mad_values = np.asarray(
                    [item["upper_z_mad_m"] for item in items if item["upper_z_mad_m"] is not None],
                    dtype=np.float64,
                )
                std_values = np.asarray(
                    [item["upper_z_std_m"] for item in items if item["upper_z_std_m"] is not None],
                    dtype=np.float64,
                )
                z50 = float(np.median(z_values)) if len(z_values) else None
                rows.append(
                    {
                        "building_id": full_id(short),
                        "band_width_m": band,
                        "source": source,
                        "source_role": "Arm1-prime final rendered depth; measurement only",
                        "view_aggregation": (
                            "counts = median over all locked visible P-J/P-L views including zero; "
                            "z statistics = median over nonempty upper-point views"
                        ),
                        "visible_view_count": len(items),
                        "upper_nonempty_view_count": int(np.count_nonzero(upper_counts > 0)),
                        "visible_views": ";".join(item["view_stem"] for item in items),
                        "all_count": float(np.median(all_counts)),
                        "upper_count": float(np.median(upper_counts)),
                        "upper_z_median_local_m": z50,
                        "upper_z_mad_m": float(np.median(mad_values)) if len(mad_values) else None,
                        "upper_z_std_m": float(np.median(std_values)) if len(std_values) else None,
                        "ground_z_q10_local_m": ground_by_short[short],
                        "reference_roof_z_local_m": refs_z[short],
                        "abs_delta_z_ref_m": abs(z50 - refs_z[short]) if z50 is not None else None,
                        "multiview_candidate_count": "",
                        "multiview_pass_count": "",
                        "multiview_pass_rate": "",
                        "multiview_method": "not_applicable_render_inventory",
                        "alpha_threshold": ALPHA_THRESHOLD,
                        "per_view_all_counts": ";".join(str(int(value)) for value in all_counts),
                        "per_view_upper_counts": ";".join(str(int(value)) for value in upper_counts),
                        "crs": "EPSG:25832",
                        "z_frame": "GS-local ellipsoidal",
                        "gt_role": "reference roof z used only after candidate selection for abs_delta_z_ref_m",
                    }
                )
        del model
        if device.type == "cuda":
            torch.cuda.empty_cache()
    return rows, view_rows, overlay


def camera_vertical_score(frame: Any) -> float:
    optical_world = frame.R.T @ np.asarray([0.0, 0.0, 1.0])
    return abs(float(optical_world[2] / max(np.linalg.norm(optical_world), 1e-12)))


def project_local(points: np.ndarray, frame: Any) -> np.ndarray:
    if not len(points):
        return np.zeros((0, 2), dtype=np.float64)
    camera = (frame.R @ points.T).T + frame.t.reshape(1, 3)
    uvw = (frame.K @ camera.T).T
    return uvw[:, :2] / np.maximum(uvw[:, 2:3], 1e-12)


def make_overlays(
    footprints: dict[str, Any],
    refs_z: dict[str, float],
    views: dict[str, list[str]],
    ds: ColmapDataset,
    offset: np.ndarray,
    observed: dict[str, dict[str, np.ndarray]],
    rendered: dict[str, dict[str, dict[str, np.ndarray]]],
) -> list[Path]:
    frame_by_stem = {Path(frame.name).stem: frame for frame in ds.frames}
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    colors = {"observed": "#1f77b4", "render_arm1p_r1": "#d62728", "render_arm1p_r2": "#ff7f0e"}
    for short in TARGETS:
        candidates = [frame_by_stem[stem] for stem in views[short]]
        nadir = max(candidates, key=camera_vertical_score)
        oblique = min(candidates, key=camera_vertical_score)
        if oblique.name == nadir.name and len(candidates) > 1:
            oblique = candidates[1]
        footprint = footprints[full_id(short)]
        fig, axes = plt.subplots(1, 2, figsize=(14, 7), dpi=180)
        for ax, frame, label in zip(axes, [nadir, oblique], ["ortho-like", "oblique"]):
            crop = render_crop_bounds(footprint, refs_z[short], frame, offset)
            image = PILImage.open(DATA_ROOT / "images" / frame.name).convert("RGB")
            ax.imshow(image)
            for width, style, color in [(0.5, ":", "#00ffff"), (1.0, "-", "#00ff66"), (1.5, "--", "#ffff00")]:
                for polygon in iter_polygons(footprint.buffer(width)):
                    ring = np.asarray(polygon.exterior.coords, dtype=np.float64)[:, :2]
                    xyz = np.column_stack([ring, np.full(len(ring), refs_z[short])])
                    uv, depth = project_utm(xyz, frame, offset)
                    valid = depth > 0
                    ax.plot(uv[valid, 0], uv[valid, 1], style, color=color, linewidth=1.0, label=f"band {width:.1f}m")
            for polygon in iter_polygons(footprint):
                ring = np.asarray(polygon.exterior.coords, dtype=np.float64)[:, :2]
                xyz = np.column_stack([ring, np.full(len(ring), refs_z[short])])
                uv, depth = project_utm(xyz, frame, offset)
                valid = depth > 0
                ax.plot(uv[valid, 0], uv[valid, 1], color="white", linewidth=1.8, label="footprint")
            obs = observed[short]["upper"]
            uv_obs = project_local(obs, frame)
            if len(uv_obs):
                ax.scatter(uv_obs[:, 0], uv_obs[:, 1], s=18, c=colors["observed"], edgecolors="white", linewidths=0.25, label="observed upper")
            for source in ["render_arm1p_r1", "render_arm1p_r2"]:
                pts = rendered.get(short, {}).get(source, {}).get(Path(frame.name).stem, np.zeros((0, 3)))
                uv = project_local(pts, frame)
                if len(uv):
                    stride = max(1, int(math.ceil(len(uv) / 4000)))
                    ax.scatter(uv[::stride, 0], uv[::stride, 1], s=3, c=colors[source], alpha=0.60, label=source.replace("render_arm1p_", "render "))
            x0, y0, x1, y1 = crop
            ax.set_xlim(x0, x1)
            ax.set_ylim(y1, y0)
            ax.set_title(f"{label}: {Path(frame.name).stem}")
            ax.axis("off")
        handles, labels = axes[0].get_legend_handles_labels()
        unique: dict[str, Any] = {}
        for handle, label in zip(handles, labels):
            unique.setdefault(label, handle)
        fig.legend(unique.values(), unique.keys(), loc="lower center", ncol=4, fontsize=8)
        fig.suptitle(f"{full_id(short)} | 1.0 m upper-boundary inventory overlay", fontsize=13)
        fig.tight_layout(rect=[0, 0.06, 1, 0.96])
        path = FIG_DIR / f"anchor_inventory_{short}.png"
        fig.savefig(path, bbox_inches="tight")
        plt.close(fig)
        outputs.append(path)
    return outputs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", default="cuda:0")
    args = parser.parse_args()
    offset = load_world_offset()
    geoid = load_geoid()
    footprints = load_footprints()
    refs = eight.parse_lod2_roofs(eight.LOD2_DIR, set(footprints))
    refs_z = {short: ref_roof_z_local(refs[full_id(short)], offset, geoid) for short in TARGETS}
    views = load_pjpl_views()
    sparse, sparse_tracks = read_sparse_with_tracks(SPARSE)
    dense = read_dense(DENSE)
    ds = ColmapDataset(DATA_ROOT, downscale=1.0, load_depth=False, load_normal=False)

    global ground_by_short
    ground_by_short = {}
    for short in TARGETS:
        footprint = footprints[full_id(short)]
        ring = footprint.buffer(GROUND_RING_M).difference(footprint)
        sparse_ground = sparse[points_in_geom(sparse, ring, offset), 2]
        dense_ground = dense[points_in_geom(dense, ring, offset), 2]
        values = np.concatenate([sparse_ground, dense_ground]).astype(np.float64)
        if not len(values):
            raise RuntimeError(f"empty exterior 5m ground ring: {short}")
        ground_by_short[short] = float(np.quantile(values, 0.10))

    rows: list[dict[str, Any]] = []
    observed_overlay: dict[str, dict[str, np.ndarray]] = {}
    for short in TARGETS:
        measured, overlay = measure_observed(
            short,
            footprints[full_id(short)],
            sparse,
            sparse_tracks,
            dense,
            offset,
            ds,
            ground_by_short[short],
            refs_z[short],
        )
        rows.extend(measured)
        observed_overlay[short] = overlay

    render_rows, view_rows, rendered_overlay = render_sources(
        footprints, refs_z, views, ds, offset, args.device
    )
    rows.extend(render_rows)
    fields = [
        "building_id", "band_width_m", "source", "source_role", "view_aggregation",
        "visible_view_count", "upper_nonempty_view_count", "visible_views", "all_count", "upper_count",
        "upper_z_median_local_m", "upper_z_mad_m", "upper_z_std_m",
        "ground_z_q10_local_m", "reference_roof_z_local_m", "abs_delta_z_ref_m",
        "multiview_candidate_count", "multiview_pass_count", "multiview_pass_rate",
        "multiview_method", "alpha_threshold", "per_view_all_counts", "per_view_upper_counts",
        "crs", "z_frame", "gt_role",
    ]
    write_csv(OUT_CSV, [{key: fmt(row.get(key)) for key in fields} for row in rows], fields)
    write_csv(VIEW_CSV, view_rows)
    figures = make_overlays(
        footprints, refs_z, views, ds, offset, observed_overlay, rendered_overlay
    )

    expected_rows = len(TARGETS) * len(BANDS) * (1 + len(CKPTS))
    if len(rows) != expected_rows:
        raise AssertionError(f"inventory row count {len(rows)} != {expected_rows}")
    if any(str(row["gt_role"]).startswith("") is False for row in rows):
        raise AssertionError("missing GT role")
    source_hashes = {
        rel(path): sha256_file(path)
        for path in [SPARSE, DENSE, FOOTPRINTS, TRAIN_MANIFEST, DATUM_CONFIG, PJPL, *CKPTS.values()]
    }
    output_hashes = {rel(path): sha256_file(path) for path in [OUT_CSV, VIEW_CSV, *figures]}
    payload = {
        "schema": "jointbuildgs.s3ap.anchor_inventory.v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "git_head_at_measurement": git_value("rev-parse", "HEAD"),
        "branch": git_value("branch", "--show-current"),
        "learning_runs_started": 0,
        "crs": "EPSG:25832",
        "world_offset": offset.tolist(),
        "geoid_m_evaluation_only_reference_conversion": geoid,
        "targets": TARGETS,
        "bands_m": BANDS,
        "ground_rule": "q10(combined sparse+dense points in exterior footprint ring buffer(5m)-footprint)",
        "upper_rule": "z_local >= ground_q10 + 1.5m",
        "observed_multiview_rule": (
            "sparse track_len>=2; dense reprojected to all 428 poses and existing PatchMatch depth, "
            "abs error <= max(0.50m,2% camera z), at least two views"
        ),
        "render_rule": "Arm1-prime final expected depth pixels with alpha>=0.5; building median over locked P-J/P-L views",
        "pjpl_views": views,
        "ground_z_q10_local_m": ground_by_short,
        "reference_roof_z_local_m_evaluation_only": refs_z,
        "source_sha256": source_hashes,
        "script_sha256": sha256_file(Path(__file__).resolve()),
        "output_sha256": output_hashes,
        "gt_separation": "LoD2 is not used to generate or filter candidates; only abs_delta_z_ref_m and projection display height",
        "no_interpretation_or_verdict": True,
    }
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {rel(OUT_CSV)} rows={len(rows)}")
    print(f"wrote {rel(VIEW_CSV)} rows={len(view_rows)}")
    for figure in figures:
        print(f"wrote {rel(figure)}")
    print(f"wrote {rel(MANIFEST)}")


if __name__ == "__main__":
    main()
