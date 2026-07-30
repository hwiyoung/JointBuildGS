#!/usr/bin/env python3
"""Shared deterministic utilities for the S3-B step-0 learning-zero measurements."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import subprocess
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

import cv2
import numpy as np
from lxml import etree
from shapely import contains_xy, make_valid
from shapely.geometry import GeometryCollection, MultiPolygon, Point, Polygon, shape
from shapely.ops import unary_union


REPO = Path(__file__).resolve().parents[3]
DEFAULT_LOCK = REPO / "phases/p2-gsjso/configs/e5_c001/e5_c001_s3b0_lock.json"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (REPO / path).resolve()


def rel(value: str | Path) -> str:
    path = Path(value).resolve()
    try:
        return str(path.relative_to(REPO.resolve()))
    except ValueError:
        return str(path)


def full_id(short: str) -> str:
    return short if short.startswith("DEBY_LOD2_") else f"DEBY_LOD2_{short}"


def short_id(value: str) -> str:
    return str(value).removeprefix("DEBY_LOD2_")


def sha256_file(path: Path, block_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def array_payload_sha256(value: np.ndarray) -> str:
    return sha256_bytes(np.ascontiguousarray(value).tobytes(order="C"))


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


def atomic_json(path: Path, value: Any) -> None:
    atomic_text(path, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def fmt(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (bool, np.bool_)):
        return "true" if bool(value) else "false"
    if isinstance(value, (float, np.floating)):
        return "" if not math.isfinite(float(value)) else f"{float(value):.12f}"
    return str(value)


def atomic_csv(path: Path, rows: Sequence[dict[str, Any]], fields: Sequence[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        seen: set[str] = set()
        ordered: list[str] = []
        for row in rows:
            for key in row:
                if key not in seen:
                    seen.add(key)
                    ordered.append(key)
        fields = ordered
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows({key: fmt(row.get(key)) for key in fields} for row in rows)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def npy_bytes(array: np.ndarray) -> bytes:
    stream = io.BytesIO()
    np.lib.format.write_array(stream, np.asarray(array), allow_pickle=False)
    return stream.getvalue()


def atomic_deterministic_npz(path: Path, arrays: dict[str, np.ndarray]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("wb") as raw:
        with zipfile.ZipFile(raw, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for key in sorted(arrays):
                info = zipfile.ZipInfo(f"{key}.npy", date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o600 << 16
                archive.writestr(info, npy_bytes(arrays[key]), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
        raw.flush()
        os.fsync(raw.fileno())
    os.replace(tmp, path)


def load_lock(path: Path = DEFAULT_LOCK) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema") != "jointbuildgs.s3b0.measurement.lock.v1":
        raise RuntimeError("S3-B step-0 lock schema mismatch")
    if int(value.get("learning_runs_allowed", -1)) != 0:
        raise RuntimeError("S3-B step-0 requires learning_runs_allowed=0")
    return value


def flatten_polygons(geom: Any) -> list[Polygon]:
    if geom is None or geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        return [geom]
    if isinstance(geom, MultiPolygon):
        return list(geom.geoms)
    if isinstance(geom, GeometryCollection):
        out: list[Polygon] = []
        for item in geom.geoms:
            out.extend(flatten_polygons(item))
        return out
    return []


def load_footprints(path: Path, wanted: Iterable[str] | None = None) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    crs = str(payload.get("crs", {}).get("properties", {}).get("name", ""))
    if "25832" not in crs:
        raise RuntimeError(f"footprint CRS is not EPSG:25832: {crs!r}")
    wanted_full = {full_id(value) for value in wanted} if wanted is not None else None
    pieces: dict[str, list[Any]] = defaultdict(list)
    for feature in payload.get("features", []):
        bid = str((feature.get("properties") or {}).get("building_id", ""))
        if not bid or (wanted_full is not None and bid not in wanted_full):
            continue
        geom = make_valid(shape(feature["geometry"]))
        if not geom.is_empty:
            pieces[bid].append(geom)
    result: dict[str, Any] = {}
    for bid, values in pieces.items():
        geom = make_valid(unary_union(values))
        if flatten_polygons(geom):
            result[bid] = geom
    if wanted_full is not None:
        missing = sorted(wanted_full - set(result))
        if missing:
            raise RuntimeError(f"missing footprints: {missing}")
    return result


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def gml_id(element: etree._Element) -> str:
    return next(
        (str(value) for key, value in element.attrib.items() if local_name(key) == "id"),
        "",
    )


def first_poslist(element: etree._Element) -> np.ndarray | None:
    for child in element.iter():
        if local_name(child.tag) == "posList" and child.text:
            values = np.asarray([float(value) for value in child.text.split()], dtype=np.float64)
            return values.reshape(-1, 3)
    return None


def load_lod2_roofs(lod2_dir: Path, targets: Sequence[str]) -> dict[str, list[dict[str, Any]]]:
    wanted = {full_id(short): short_id(short) for short in targets}
    output: dict[str, list[dict[str, Any]]] = {short_id(short): [] for short in targets}
    for path in sorted(lod2_dir.glob("*.gml")):
        for _event, element in etree.iterparse(str(path), events=("end",), recover=True):
            if local_name(element.tag) != "Building":
                continue
            bid = gml_id(element)
            if bid in wanted:
                short = wanted[bid]
                index = 0
                for surface in element.iter():
                    if local_name(surface.tag) != "RoofSurface":
                        continue
                    for polygon_element in surface.iter():
                        if local_name(polygon_element.tag) != "Polygon":
                            continue
                        ring = first_poslist(polygon_element)
                        if ring is None or len(ring) < 3:
                            continue
                        if not np.allclose(ring[0], ring[-1]):
                            ring = np.vstack([ring, ring[0]])
                        polygon = make_valid(Polygon(ring[:, :2]))
                        if polygon.is_empty or polygon.area <= 0.01:
                            continue
                        points = ring[:-1]
                        x0, y0, _zmean = points.mean(axis=0)
                        design = np.column_stack(
                            [
                                points[:, 0] - x0,
                                points[:, 1] - y0,
                                np.ones(len(points)),
                            ]
                        )
                        ax, by, z0 = np.linalg.lstsq(design, points[:, 2], rcond=None)[0]
                        index += 1
                        output[short].append(
                            {
                                "id": f"{bid}_roof_{index}",
                                "ring": ring,
                                "polygon": polygon,
                                "x0": float(x0),
                                "y0": float(y0),
                                "z0": float(z0),
                                "ax": float(ax),
                                "by": float(by),
                                "source": path,
                            }
                        )
            element.clear()
            parent = element.getparent()
            if parent is not None:
                while element.getprevious() is not None:
                    del parent[0]
    missing = sorted(short for short, roofs in output.items() if not roofs)
    if missing:
        raise RuntimeError(f"missing LoD2 roofs: {missing}")
    return output


def reference_roof_z(
    xy_utm: np.ndarray,
    roofs: Sequence[dict[str, Any]],
    geoid_m: float,
) -> np.ndarray:
    xy = np.asarray(xy_utm, dtype=np.float64).reshape(-1, 2)
    values = np.full(len(xy), np.nan, dtype=np.float64)
    for roof in roofs:
        mask = contains_xy(roof["polygon"], xy[:, 0], xy[:, 1])
        if np.any(mask):
            values[mask] = (
                roof["z0"]
                + roof["ax"] * (xy[mask, 0] - roof["x0"])
                + roof["by"] * (xy[mask, 1] - roof["y0"])
                + geoid_m
            )
    for index in np.flatnonzero(~np.isfinite(values)):
        nearest = min(
            roofs,
            key=lambda roof: roof["polygon"].distance(
                Point(float(xy[index, 0]), float(xy[index, 1]))
            ),
        )
        values[index] = (
            nearest["z0"]
            + nearest["ax"] * (xy[index, 0] - nearest["x0"])
            + nearest["by"] * (xy[index, 1] - nearest["y0"])
            + geoid_m
        )
    return values


def load_world_offset(path: Path) -> np.ndarray:
    value = np.asarray(json.loads(path.read_text(encoding="utf-8"))["world_offset"], dtype=np.float64)
    if value.shape != (3,) or not np.all(np.isfinite(value)):
        raise RuntimeError(f"invalid world offset: {value!r}")
    return value


def load_fm_summaries(path: Path) -> dict[str, dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    output: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row.get("row_type") != "building_summary":
            continue
        short = short_id(row["building_id"])
        output[short] = {
            "inside_point_count": int(row["inside_point_count"]),
            "inside_z_median_local_m": float(row["inside_z_median_local_m"]),
            "plane": np.asarray(
                [float(row["plane_ax"]), float(row["plane_by"]), float(row["plane_c"])],
                dtype=np.float64,
            ),
            "ground_z_local_m": float(row["ground_z_local_m"]),
            "source_row": row,
        }
    return output


def load_crop_contexts(prepared_root: Path, targets: Sequence[str]) -> list[dict[str, Any]]:
    contexts: list[dict[str, Any]] = []
    for short in targets:
        root = prepared_root / full_id(short)
        manifest_path = root / "camera_crop_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for view in manifest["views"]:
            stem = str(view["view_stem"])
            contexts.append(
                {
                    "short": short,
                    "building_id": full_id(short),
                    "stem": stem,
                    "root": root,
                    "manifest_path": manifest_path,
                    "view": view,
                    "image_path": root / "images" / f"{stem}.png",
                    "semantic_path": root / "semantic" / f"{stem}.png",
                    "semantic_region_path": root / "semantic_regions" / f"{stem}.npz",
                    "normal_path": root / "mono_normal" / f"{stem}.npy",
                    "depth_path": root / "mono_depth" / f"{stem}.npy",
                }
            )
    contexts.sort(key=lambda row: (row["short"], row["stem"]))
    return contexts


def densify_ring(coords: Iterable[Sequence[float]], max_step_m: float = 0.20) -> np.ndarray:
    points = np.asarray([(float(item[0]), float(item[1])) for item in coords], dtype=np.float64)
    if len(points) < 3:
        return points
    if not np.allclose(points[0], points[-1]):
        points = np.vstack([points, points[0]])
    rows: list[np.ndarray] = []
    for left, right in zip(points[:-1], points[1:]):
        count = max(1, int(math.ceil(float(np.linalg.norm(right - left)) / max_step_m)))
        for index in range(count):
            rows.append(left + (right - left) * (index / count))
    return np.asarray(rows, dtype=np.float64)


def plane_z_local(xy_utm: np.ndarray, plane: np.ndarray, offset: np.ndarray) -> np.ndarray:
    local_xy = np.asarray(xy_utm, dtype=np.float64) - offset[None, :2]
    return plane[0] * local_xy[:, 0] + plane[1] * local_xy[:, 1] + plane[2]


def project_utm(
    xy_utm: np.ndarray,
    z_local: np.ndarray | float,
    view: dict[str, Any],
    offset: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    xy = np.asarray(xy_utm, dtype=np.float64)
    z = np.broadcast_to(np.asarray(z_local, dtype=np.float64), (len(xy),))
    local = np.column_stack([xy[:, 0] - offset[0], xy[:, 1] - offset[1], z])
    rotation = np.asarray(view["R_w2c"], dtype=np.float64)
    translation = np.asarray(view["t_w2c"], dtype=np.float64)
    camera = local @ rotation.T + translation[None, :]
    intrinsic = np.asarray(view["K_crop"], dtype=np.float64)
    uvw = camera @ intrinsic.T
    uv = uvw[:, :2] / np.maximum(uvw[:, 2:3], 1e-12)
    return uv, camera[:, 2]


def project_geometry_mask(
    geom: Any,
    plane: np.ndarray,
    view: dict[str, Any],
    offset: np.ndarray,
    shape_hw: tuple[int, int],
    max_step_m: float = 0.20,
) -> tuple[np.ndarray, list[np.ndarray], list[np.ndarray]]:
    height, width = shape_hw
    result = np.zeros((height, width), dtype=np.uint8)
    exterior_uvs: list[np.ndarray] = []
    exterior_depths: list[np.ndarray] = []
    for polygon in flatten_polygons(geom):
        exterior = densify_ring(polygon.exterior.coords, max_step_m=max_step_m)
        z = plane_z_local(exterior, plane, offset)
        uv, depth = project_utm(exterior, z, view, offset)
        exterior_uvs.append(uv)
        exterior_depths.append(depth)
        valid_projection = (
            len(uv) >= 3
            and np.all(np.isfinite(uv))
            and np.all(np.isfinite(depth))
            and np.all(depth > 1e-6)
            and float(np.max(np.abs(uv))) < 1e7
        )
        if not valid_projection:
            continue
        local = np.zeros_like(result)
        cv2.fillPoly(local, [np.rint(uv).astype(np.int32)], 1)
        for interior in polygon.interiors:
            ring = densify_ring(interior.coords, max_step_m=max_step_m)
            iz = plane_z_local(ring, plane, offset)
            iuv, idepth = project_utm(ring, iz, view, offset)
            if len(iuv) >= 3 and np.all(np.isfinite(iuv)) and np.all(idepth > 1e-6):
                cv2.fillPoly(local, [np.rint(iuv).astype(np.int32)], 0)
        result |= local
    return result.astype(bool), exterior_uvs, exterior_depths


def iou(left: np.ndarray, right: np.ndarray) -> tuple[int, int, float]:
    left_b = np.asarray(left, dtype=bool)
    right_b = np.asarray(right, dtype=bool)
    intersection = int(np.logical_and(left_b, right_b).sum())
    union = int(np.logical_or(left_b, right_b).sum())
    return intersection, union, float(intersection / union) if union else 1.0


def boundary(mask: np.ndarray) -> np.ndarray:
    value = np.asarray(mask, dtype=np.uint8)
    eroded = cv2.erode(value, np.ones((3, 3), dtype=np.uint8), iterations=1)
    return (value > 0) & (eroded == 0)


def source_hashes(paths: Iterable[Path]) -> dict[str, str]:
    return {rel(path): sha256_file(path) for path in sorted(set(paths)) if path.exists() and path.is_file()}
