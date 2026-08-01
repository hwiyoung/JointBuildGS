#!/usr/bin/env python3
"""Execute the bounded Gate S0 integrated-freeze evidence closure.

The first invocation is add-once and reads only packet-authorized scientific
paths.  The completed ledger is written last.  A later invocation reads only
that ledger and exits without touching external scientific payloads or outputs.
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
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

import laspy
import numpy as np
import scipy
from scipy import ndimage


REPO = Path(__file__).resolve().parents[4]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.stage3.gate_s0_integrated_v1.interface import synthetic_smoke_payload  # noqa: E402


TASK = "P2-GATE-S0-INTEGRATED-FREEZE-CLOSURE-v1"
HANDOFF = "P2-W2C-GATE-S0-INTEGRATED-FREEZE-CLOSURE-v1"
CONFIG_PATH = REPO / "configs/input_and_alignment/gate_s0/integrated_freeze_closure_v1/integrated_freeze_v1.json"
MANIFEST_ROOT = REPO / "artifacts/manifests/gate_s0/integrated_freeze_closure_v1"
DOC_ROOT = REPO / "docs/research/preregistration/gate_s0/integrated_freeze_closure_v1"
LEDGER_PATH = MANIFEST_ROOT / "no_repeat_operation_ledger_v1.json"
ALLOWED_PREEXISTING_RELATIVE = Path("acceptance/artifact_root_preflight_v1.json")
STARTED_RELATIVE = Path("control/started_v1.json")
INTENDED_REPO_OUTPUTS = (
    MANIFEST_ROOT / "four_path_fingerprint_v1.json",
    MANIFEST_ROOT / "component_enablement_v1.json",
    MANIFEST_ROOT / "c1_c4_derivative_manifest_v1.json",
    MANIFEST_ROOT / "independent_reference_manifest_v1.json",
    MANIFEST_ROOT / "universe_manifest_v1.json",
    MANIFEST_ROOT / "split_manifest_v1.json",
    MANIFEST_ROOT / "stage3_common_interface_manifest_v1.json",
    MANIFEST_ROOT / "administrative_cost_caps_v1.json",
    MANIFEST_ROOT / "external_output_records_v1.json",
    DOC_ROOT / "frame_datum_registration_gravity_receipt_v1.json",
    DOC_ROOT / "reference_id_join_v1.csv",
    DOC_ROOT / "eligibility_ledger_v1.csv",
    DOC_ROOT / "stage3_synthetic_smoke_receipt_v1.json",
)


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO, text=True).strip()


def file_blob(path: Path) -> str:
    return git("hash-object", str(path.resolve().relative_to(REPO)))


def write_repo_json(path: Path, payload: Any) -> dict[str, Any]:
    data = canonical_json_bytes(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise RuntimeError(f"refusing to overwrite Git output: {path.relative_to(REPO)}")
    path.write_bytes(data)
    return {"path": path.relative_to(REPO).as_posix(), "bytes": len(data), "sha256": sha256_bytes(data)}


def write_repo_csv(path: Path, fieldnames: Sequence[str], rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise RuntimeError(f"refusing to overwrite Git output: {path.relative_to(REPO)}")
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    data = buffer.getvalue().encode("utf-8")
    path.write_bytes(data)
    return {"path": path.relative_to(REPO).as_posix(), "bytes": len(data), "sha256": sha256_bytes(data)}


def write_external_json(path: Path, payload: Any) -> dict[str, Any]:
    data = canonical_json_bytes(payload)
    writer = AddOnceWriter(path)
    writer.write(data)
    record = writer.close()
    record.update({"uri": artifact_uri(path), "digest_method": "same_stream_as_add_once_serialization"})
    return record


class AddOnceWriter:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.handle = os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o664), "wb", buffering=0)
        self.digest = hashlib.sha256()
        self.bytes = 0

    def write(self, data: bytes) -> None:
        self.handle.write(data)
        self.digest.update(data)
        self.bytes += len(data)

    def close(self) -> dict[str, Any]:
        self.handle.flush()
        os.fsync(self.handle.fileno())
        self.handle.close()
        return {"bytes": self.bytes, "sha256": self.digest.hexdigest()}


@dataclass
class GridSummary:
    bbox: tuple[float, float, float, float]
    cell: float

    def __post_init__(self) -> None:
        x0, y0, x1, y1 = self.bbox
        self.nx = int(math.ceil((x1 - x0) / self.cell))
        self.ny = int(math.ceil((y1 - y0) / self.cell))
        size = self.nx * self.ny
        self.min_z = np.full(size, np.inf, dtype=np.float64)
        self.max_z = np.full(size, -np.inf, dtype=np.float64)
        self.count = np.zeros(size, dtype=np.uint64)
        self.raw_class2 = np.zeros(size, dtype=np.uint64)
        self.raw_class6 = np.zeros(size, dtype=np.uint64)
        self.points_seen = 0
        self.points_in_aoi = 0

    def update(self, x: np.ndarray, y: np.ndarray, z: np.ndarray, classification: np.ndarray | None = None) -> None:
        self.points_seen += int(len(x))
        x0, y0, x1, y1 = self.bbox
        keep = np.isfinite(x) & np.isfinite(y) & np.isfinite(z)
        keep &= (x >= x0) & (x < x1) & (y >= y0) & (y < y1)
        if not np.any(keep):
            return
        xk = np.asarray(x[keep], dtype=np.float64)
        yk = np.asarray(y[keep], dtype=np.float64)
        zk = np.asarray(z[keep], dtype=np.float64)
        ix = np.floor((xk - x0) / self.cell).astype(np.int64)
        iy = np.floor((yk - y0) / self.cell).astype(np.int64)
        flat = iy * self.nx + ix
        np.minimum.at(self.min_z, flat, zk)
        np.maximum.at(self.max_z, flat, zk)
        np.add.at(self.count, flat, 1)
        self.points_in_aoi += int(len(flat))
        if classification is not None:
            ck = np.asarray(classification[keep], dtype=np.uint8)
            if np.any(ck == 2):
                np.add.at(self.raw_class2, flat[ck == 2], 1)
            if np.any(ck == 6):
                np.add.at(self.raw_class6, flat[ck == 6], 1)

    def centers(self) -> tuple[np.ndarray, np.ndarray]:
        x0, y0, _, _ = self.bbox
        iy, ix = np.indices((self.ny, self.nx))
        return x0 + (ix.ravel() + 0.5) * self.cell, y0 + (iy.ravel() + 0.5) * self.cell

    def building_mask(self, min_height: float, min_points: int) -> np.ndarray:
        return np.isfinite(self.min_z) & ((self.max_z - self.min_z) >= min_height) & (self.count >= min_points)

    def coverage(self, bbox: tuple[float, float, float, float], mask: np.ndarray | None = None) -> int:
        x0, y0, _, _ = self.bbox
        bx0, by0, bx1, by1 = bbox
        ix0 = max(0, int(math.floor((bx0 - x0) / self.cell)))
        iy0 = max(0, int(math.floor((by0 - y0) / self.cell)))
        ix1 = min(self.nx, int(math.ceil((bx1 - x0) / self.cell)))
        iy1 = min(self.ny, int(math.ceil((by1 - y0) / self.cell)))
        if ix0 >= ix1 or iy0 >= iy1:
            return 0
        base = np.isfinite(self.min_z).reshape(self.ny, self.nx)[iy0:iy1, ix0:ix1]
        if mask is not None:
            base &= mask.reshape(self.ny, self.nx)[iy0:iy1, ix0:ix1]
        return int(np.count_nonzero(base))

    def z_range(self, bbox: tuple[float, float, float, float]) -> tuple[float, float] | None:
        x0, y0, _, _ = self.bbox
        bx0, by0, bx1, by1 = bbox
        ix0 = max(0, int(math.floor((bx0 - x0) / self.cell)))
        iy0 = max(0, int(math.floor((by0 - y0) / self.cell)))
        ix1 = min(self.nx, int(math.ceil((bx1 - x0) / self.cell)))
        iy1 = min(self.ny, int(math.ceil((by1 - y0) / self.cell)))
        if ix0 >= ix1 or iy0 >= iy1:
            return None
        lo = self.min_z.reshape(self.ny, self.nx)[iy0:iy1, ix0:ix1]
        hi = self.max_z.reshape(self.ny, self.nx)[iy0:iy1, ix0:ix1]
        finite = np.isfinite(lo)
        if not np.any(finite):
            return None
        return float(np.min(lo[finite])), float(np.max(hi[finite]))


def merkle_root(records: Sequence[dict[str, Any]]) -> str:
    leaves = [
        hashlib.sha256(f"{r['path']}\0{r['bytes']}\0{r['sha256']}\n".encode()).digest()
        for r in records
    ]
    if not leaves:
        return hashlib.sha256(b"").hexdigest()
    while len(leaves) > 1:
        if len(leaves) % 2:
            leaves.append(leaves[-1])
        leaves = [hashlib.sha256(leaves[i] + leaves[i + 1]).digest() for i in range(0, len(leaves), 2)]
    return leaves[0].hex()


def hash_file_once(path: Path, *, capture: bool = False) -> tuple[dict[str, Any], bytes | None]:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"selected hash target is not a regular non-symlink file: {path}")
    digest = hashlib.sha256()
    total = 0
    captured = bytearray() if capture else None
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(8 * 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            total += len(chunk)
            if captured is not None:
                captured.extend(chunk)
    return {"bytes": total, "sha256": digest.hexdigest()}, bytes(captured) if captured is not None else None


CAMERA_MODEL_PARAMS = {0: 3, 1: 4, 2: 4, 3: 5, 4: 8, 5: 8, 6: 12, 7: 5, 8: 4, 9: 5, 10: 12}


def parse_colmap_cameras(data: bytes) -> dict[int, dict[str, Any]]:
    stream = io.BytesIO(data)
    count = struct.unpack("<Q", stream.read(8))[0]
    cameras: dict[int, dict[str, Any]] = {}
    for _ in range(count):
        camera_id, model_id = struct.unpack("<ii", stream.read(8))
        width, height = struct.unpack("<QQ", stream.read(16))
        nparams = CAMERA_MODEL_PARAMS[model_id]
        params = struct.unpack(f"<{nparams}d", stream.read(8 * nparams))
        cameras[camera_id] = {"model_id": model_id, "width": width, "height": height, "params": params}
    if stream.tell() != len(data):
        raise RuntimeError("unexpected trailing cameras.bin bytes")
    return cameras


def qvec_rotation(q: Sequence[float]) -> np.ndarray:
    w, x, y, z = q
    return np.array(
        [
            [1 - 2 * y * y - 2 * z * z, 2 * x * y - 2 * w * z, 2 * x * z + 2 * w * y],
            [2 * x * y + 2 * w * z, 1 - 2 * x * x - 2 * z * z, 2 * y * z - 2 * w * x],
            [2 * x * z - 2 * w * y, 2 * y * z + 2 * w * x, 1 - 2 * x * x - 2 * y * y],
        ],
        dtype=np.float64,
    )


def parse_colmap_images(data: bytes) -> list[dict[str, Any]]:
    stream = io.BytesIO(data)
    count = struct.unpack("<Q", stream.read(8))[0]
    images: list[dict[str, Any]] = []
    for _ in range(count):
        image_id = struct.unpack("<i", stream.read(4))[0]
        qvec = struct.unpack("<4d", stream.read(32))
        tvec = struct.unpack("<3d", stream.read(24))
        camera_id = struct.unpack("<i", stream.read(4))[0]
        name_bytes = bytearray()
        while True:
            value = stream.read(1)
            if value == b"\0":
                break
            if not value:
                raise RuntimeError("truncated images.bin name")
            name_bytes.extend(value)
        points = struct.unpack("<Q", stream.read(8))[0]
        stream.seek(points * 24, io.SEEK_CUR)
        rotation = qvec_rotation(qvec)
        translation = np.asarray(tvec, dtype=np.float64)
        center = -(rotation.T @ translation)
        images.append(
            {
                "image_id": image_id,
                "camera_id": camera_id,
                "name": name_bytes.decode("utf-8"),
                "rotation": rotation,
                "translation": translation,
                "center": center,
            }
        )
    if stream.tell() != len(data):
        raise RuntimeError("unexpected trailing images.bin bytes")
    return images


def fingerprint_sparse(path: Path) -> tuple[dict[str, Any], dict[int, dict[str, Any]], list[dict[str, Any]]]:
    if path.is_symlink() or not path.is_dir():
        raise RuntimeError(f"selected sparse target is not a non-symlink directory: {path}")
    members: list[dict[str, Any]] = []
    captures: dict[str, bytes] = {}
    with os.scandir(path) as iterator:
        entries = sorted(list(iterator), key=lambda item: item.name.encode("utf-8"))
    for entry in entries:
        if entry.is_symlink() or not entry.is_file(follow_symlinks=False):
            raise RuntimeError(f"sparse member is not a regular file: {entry.name}")
        record, data = hash_file_once(Path(entry.path), capture=entry.name in {"cameras.bin", "images.bin"})
        record["path"] = entry.name
        members.append(record)
        if data is not None:
            captures[entry.name] = data
    if len(members) != 5:
        raise RuntimeError(f"expected five sparse members, found {len(members)}")
    cameras = parse_colmap_cameras(captures["cameras.bin"])
    images = parse_colmap_images(captures["images.bin"])
    return {
        "files": len(members),
        "directory_entries_enumerated": len(entries),
        "directory_entries_statted": len(entries),
        "bytes": sum(r["bytes"] for r in members),
        "members": members,
        "merkle_sha256": merkle_root(members),
        "directory_identity_algorithm": "bytewise UTF-8 member-name order; regular non-symlink files only; leaf=SHA256(path\\0bytes\\0sha256\\n); duplicate-last binary Merkle tree",
        "directory_identity_algorithm_version": "JOINTBUILDGS_SPARSE_MERKLE_V1",
    }, cameras, images


PLY_TYPES = {
    "char": "i1", "int8": "i1", "uchar": "u1", "uint8": "u1",
    "short": "<i2", "int16": "<i2", "ushort": "<u2", "uint16": "<u2",
    "int": "<i4", "int32": "<i4", "uint": "<u4", "uint32": "<u4",
    "float": "<f4", "float32": "<f4", "double": "<f8", "float64": "<f8",
}


def hash_ply_and_grid(path: Path, grid: GridSummary, shift: Sequence[float]) -> tuple[dict[str, Any], dict[str, Any]]:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"selected PLY hash target is not a regular non-symlink file: {path}")
    digest = hashlib.sha256()
    total = 0
    header_lines: list[str] = []
    with path.open("rb") as handle:
        while True:
            line = handle.readline()
            if not line:
                raise RuntimeError("truncated PLY header")
            digest.update(line)
            total += len(line)
            decoded = line.decode("ascii").strip()
            header_lines.append(decoded)
            if decoded == "end_header":
                break
        if header_lines[1] != "format binary_little_endian 1.0":
            raise RuntimeError(f"unsupported PLY format: {header_lines[1]}")
        vertex_count = None
        vertex_properties: list[tuple[str, str]] = []
        active = None
        for line in header_lines:
            parts = line.split()
            if parts[:1] == ["element"]:
                active = parts[1]
                if active == "vertex":
                    vertex_count = int(parts[2])
            elif parts[:1] == ["property"] and active == "vertex":
                if parts[1] == "list":
                    raise RuntimeError("list property in PLY vertex is unsupported")
                vertex_properties.append((parts[2], PLY_TYPES[parts[1]]))
        if vertex_count is None:
            raise RuntimeError("PLY vertex count missing")
        dtype = np.dtype(vertex_properties)
        for required in ("x", "y", "z"):
            if required not in dtype.names:
                raise RuntimeError(f"PLY vertex property missing: {required}")
        vertices_read = 0
        records_per_chunk = max(1, (16 * 1024 * 1024) // dtype.itemsize)
        while vertices_read < vertex_count:
            take = min(records_per_chunk, vertex_count - vertices_read)
            data = handle.read(take * dtype.itemsize)
            if len(data) != take * dtype.itemsize:
                raise RuntimeError("truncated PLY vertex body")
            digest.update(data)
            total += len(data)
            array = np.frombuffer(data, dtype=dtype, count=take)
            grid.update(
                np.asarray(array["x"], dtype=np.float64) + float(shift[0]),
                np.asarray(array["y"], dtype=np.float64) + float(shift[1]),
                np.asarray(array["z"], dtype=np.float64) + float(shift[2]),
            )
            vertices_read += take
        while True:
            data = handle.read(8 * 1024 * 1024)
            if not data:
                break
            digest.update(data)
            total += len(data)
    return {
        "bytes": total,
        "sha256": digest.hexdigest(),
        "vertex_count": vertex_count,
        "vertex_properties": [name for name, _ in vertex_properties],
        "header_lines": header_lines,
    }, terrain_gravity(grid)


def terrain_gravity(grid: GridSummary) -> dict[str, Any]:
    z = grid.min_z.reshape(grid.ny, grid.nx)
    valid = np.isfinite(z)
    if np.count_nonzero(valid) < 100:
        raise RuntimeError("insufficient MVS terrain cells for gravity")
    nearest = ndimage.distance_transform_edt(~valid, return_distances=False, return_indices=True)
    filled = z[tuple(nearest)]
    dz_dy, dz_dx = np.gradient(filled, grid.cell, grid.cell)
    east = np.stack([np.full_like(dz_dx, grid.cell), np.zeros_like(dz_dx), dz_dx * grid.cell], axis=-1)
    north = np.stack([np.zeros_like(dz_dy), np.full_like(dz_dy, grid.cell), dz_dy * grid.cell], axis=-1)
    normals = np.cross(east, north)[valid]
    norms = np.linalg.norm(normals, axis=1)
    normals = normals[norms > 1e-12]
    normals /= np.linalg.norm(normals, axis=1, keepdims=True)
    median = np.median(normals, axis=0)
    median /= np.linalg.norm(median)
    dots = normals @ median
    inliers = normals[dots >= math.cos(math.radians(20.0))]
    up = np.mean(inliers, axis=0)
    up /= np.linalg.norm(up)
    gravity = -up
    angles = np.degrees(np.arccos(np.clip(inliers @ up, -1.0, 1.0)))
    return {
        "method": "terrain MVS one-metre minimum-surface east-cross-north normals; 20-degree robust consensus",
        "normal_orientation_rule": "ordered east cross north tangents from selected dense-MVS terrain cells; no fixed gravity vector",
        "terrain_cell_count": int(np.count_nonzero(valid)),
        "inlier_normal_count": int(len(inliers)),
        "up": [float(v) for v in up],
        "gravity": [float(v) for v in gravity],
        "angular_median_deg": float(np.median(angles)),
        "angular_p95_deg": float(np.percentile(angles, 95)),
    }


def utm_inverse(easting: np.ndarray, northing: np.ndarray, *, a: float, inv_f: float) -> tuple[np.ndarray, np.ndarray]:
    f = 1.0 / inv_f
    e2 = f * (2.0 - f)
    ep2 = e2 / (1.0 - e2)
    k0 = 0.9996
    x = easting - 500000.0
    m = northing / k0
    mu = m / (a * (1 - e2 / 4 - 3 * e2**2 / 64 - 5 * e2**3 / 256))
    e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
    j1 = 3 * e1 / 2 - 27 * e1**3 / 32
    j2 = 21 * e1**2 / 16 - 55 * e1**4 / 32
    j3 = 151 * e1**3 / 96
    j4 = 1097 * e1**4 / 512
    fp = mu + j1 * np.sin(2 * mu) + j2 * np.sin(4 * mu) + j3 * np.sin(6 * mu) + j4 * np.sin(8 * mu)
    sin_fp, cos_fp = np.sin(fp), np.cos(fp)
    tan_fp = np.tan(fp)
    c1 = ep2 * cos_fp**2
    t1 = tan_fp**2
    n1 = a / np.sqrt(1 - e2 * sin_fp**2)
    r1 = a * (1 - e2) / (1 - e2 * sin_fp**2) ** 1.5
    d = x / (n1 * k0)
    lat = fp - (n1 * tan_fp / r1) * (
        d**2 / 2 - (5 + 3 * t1 + 10 * c1 - 4 * c1**2 - 9 * ep2) * d**4 / 24
        + (61 + 90 * t1 + 298 * c1 + 45 * t1**2 - 252 * ep2 - 3 * c1**2) * d**6 / 720
    )
    lon = math.radians(9.0) + (
        d - (1 + 2 * t1 + c1) * d**3 / 6
        + (5 - 2 * c1 + 28 * t1 - 3 * c1**2 + 8 * ep2 + 24 * t1**2) * d**5 / 120
    ) / cos_fp
    return lat, lon


def utm_forward(lat: np.ndarray, lon: np.ndarray, *, a: float, inv_f: float) -> tuple[np.ndarray, np.ndarray]:
    f = 1.0 / inv_f
    e2 = f * (2.0 - f)
    ep2 = e2 / (1.0 - e2)
    k0 = 0.9996
    lon0 = math.radians(9.0)
    n = a / np.sqrt(1 - e2 * np.sin(lat) ** 2)
    t = np.tan(lat) ** 2
    c = ep2 * np.cos(lat) ** 2
    aa = np.cos(lat) * (lon - lon0)
    m = a * (
        (1 - e2 / 4 - 3 * e2**2 / 64 - 5 * e2**3 / 256) * lat
        - (3 * e2 / 8 + 3 * e2**2 / 32 + 45 * e2**3 / 1024) * np.sin(2 * lat)
        + (15 * e2**2 / 256 + 45 * e2**3 / 1024) * np.sin(4 * lat)
        - (35 * e2**3 / 3072) * np.sin(6 * lat)
    )
    easting = 500000 + k0 * n * (aa + (1 - t + c) * aa**3 / 6 + (5 - 18 * t + t**2 + 72 * c - 58 * ep2) * aa**5 / 120)
    northing = k0 * (m + n * np.tan(lat) * (aa**2 / 2 + (5 - t + 9 * c + 4 * c**2) * aa**4 / 24 + (61 - 58 * t + t**2 + 600 * c - 330 * ep2) * aa**6 / 720))
    return easting, northing


def epsg32632_to_25832(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    lat, lon = utm_inverse(x, y, a=6378137.0, inv_f=298.257223563)
    return utm_forward(lat, lon, a=6378137.0, inv_f=298.257222101)


def process_laz_once(path: Path, grid: GridSummary, *, transform: bool) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"selected LAZ input is not a regular non-symlink file: {path}")
    classes = Counter()
    chunks = 0
    with laspy.open(path) as reader:
        header = reader.header
        try:
            crs = header.parse_crs()
            crs_text = crs.to_string() if crs is not None else None
        except ModuleNotFoundError as error:
            if error.name != "pyproj":
                raise
            crs_text = "UNPARSED_PYPROJ_NOT_INSTALLED_USE_FROZEN_CONFIG_PROVENANCE"
        point_count = int(header.point_count)
        point_format = int(header.point_format.id)
        scales = [float(v) for v in header.scales]
        offsets = [float(v) for v in header.offsets]
        for points in reader.chunk_iterator(1_000_000):
            x = np.asarray(points.x, dtype=np.float64)
            y = np.asarray(points.y, dtype=np.float64)
            z = np.asarray(points.z, dtype=np.float64)
            classification = np.asarray(points.classification, dtype=np.uint8)
            unique, counts = np.unique(classification, return_counts=True)
            classes.update({str(int(k)): int(v) for k, v in zip(unique, counts)})
            if transform:
                x, y = epsg32632_to_25832(x, y)
            grid.update(x, y, z, classification)
            chunks += 1
    return {
        "path": path.as_posix(),
        "source_file_size_bytes": path.stat().st_size,
        "actual_io_bytes_read": "UNKNOWN_NOT_INSTRUMENTED_BY_LASPY_LAZ_BACKEND",
        "logical_decode_passes": 1,
        "point_count": point_count,
        "point_format": point_format,
        "scales": scales,
        "offsets": offsets,
        "parsed_crs": crs_text,
        "vertical_crs": None,
        "raw_class_counts": dict(sorted(classes.items(), key=lambda item: int(item[0]))),
        "chunks": chunks,
        "full_content_passes": 1,
        "input_full_hashes": 0,
    }


def write_grid_ply(path: Path, grid: GridSummary, min_height: float, min_points: int) -> dict[str, Any]:
    valid = np.isfinite(grid.min_z)
    building = grid.building_mask(min_height, min_points)
    x, y = grid.centers()
    count = int(np.count_nonzero(valid) + np.count_nonzero(building))
    writer = AddOnceWriter(path)
    header = (
        "ply\nformat ascii 1.0\n"
        f"element vertex {count}\n"
        "property double x\nproperty double y\nproperty double z\n"
        "property uchar classification\nend_header\n"
    ).encode("ascii")
    writer.write(header)
    for idx in np.flatnonzero(valid):
        writer.write(f"{x[idx]:.3f} {y[idx]:.3f} {grid.min_z[idx]:.3f} 2\n".encode("ascii"))
    for idx in np.flatnonzero(building):
        writer.write(f"{x[idx]:.3f} {y[idx]:.3f} {grid.max_z[idx]:.3f} 6\n".encode("ascii"))
    record = writer.close()
    record.update({"uri": artifact_uri(path), "ground_points": int(np.count_nonzero(valid)), "building_points": int(np.count_nonzero(building)), "digest_method": "same_stream_as_add_once_serialization"})
    return record


def artifact_uri(path: Path) -> str:
    root = CURRENT_ARTIFACT_ROOT.resolve()
    return "artifact://JointBuildGS/" + path.resolve().relative_to(root).as_posix()


def reference_rows(grid: GridSummary, min_height: float, min_points: int, min_component: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    mask = grid.building_mask(min_height, min_points).reshape(grid.ny, grid.nx)
    labels, components = ndimage.label(mask, structure=np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], dtype=np.uint8))
    sizes = np.bincount(labels.ravel())
    keep_components = {idx for idx in range(1, len(sizes)) if sizes[idx] >= min_component}
    keep = np.isin(labels, list(keep_components))
    top = grid.max_z.reshape(grid.ny, grid.nx)
    if not np.any(keep):
        return [], {"component_count": 0, "cell_count": 0}
    nearest = ndimage.distance_transform_edt(~keep, return_distances=False, return_indices=True)
    filled = top[tuple(nearest)]
    dz_dy, dz_dx = np.gradient(filled, grid.cell, grid.cell)
    normals = np.stack([-dz_dx, -dz_dy, np.ones_like(dz_dx)], axis=-1)
    normals /= np.linalg.norm(normals, axis=-1, keepdims=True)
    x, y = grid.centers()
    rows: list[dict[str, Any]] = []
    component_ids: dict[int, str] = {}
    for label_id in sorted(keep_components):
        cells = np.flatnonzero(labels.ravel() == label_id)
        identity = hashlib.sha256(
            ("|".join(f"{int(i)}:{grid.max_z[i]:.3f}" for i in cells) + "\n").encode()
        ).hexdigest()[:20]
        component_ids[label_id] = f"UASREF_{identity}"
    for flat in np.flatnonzero(keep.ravel()):
        iy, ix = divmod(int(flat), grid.nx)
        normal = normals[iy, ix]
        normal_bin = tuple(int(round(float(v) * 20)) for v in normal)
        component = component_ids[int(labels[iy, ix])]
        plane_id = hashlib.sha256(f"{component}|{normal_bin}\n".encode()).hexdigest()[:16]
        rows.append(
            {
                "reference_component_id": component,
                "reference_plane_id": f"PLANE_{plane_id}",
                "cell_x": f"{x[flat]:.3f}",
                "cell_y": f"{y[flat]:.3f}",
                "z": f"{grid.max_z[flat]:.3f}",
                "normal_x": f"{normal[0]:.9f}",
                "normal_y": f"{normal[1]:.9f}",
                "normal_z": f"{normal[2]:.9f}",
                "class": "6",
            }
        )
    return rows, {"component_count": len(component_ids), "cell_count": len(rows), "plane_count": len({row["reference_plane_id"] for row in rows})}


def write_external_csv(path: Path, fieldnames: Sequence[str], rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    writer = AddOnceWriter(path)
    buffer = io.StringIO(newline="")
    csv_writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
    csv_writer.writeheader()
    writer.write(buffer.getvalue().encode("utf-8"))
    for row in rows:
        buffer = io.StringIO(newline="")
        csv_writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
        csv_writer.writerow(row)
        writer.write(buffer.getvalue().encode("utf-8"))
    record = writer.close()
    record.update({"uri": artifact_uri(path), "rows": len(rows), "digest_method": "same_stream_as_add_once_serialization"})
    return record


def parse_bbox(text: str) -> tuple[float, float, float, float]:
    values = tuple(float(value) for value in text.split(","))
    if len(values) != 4:
        raise ValueError(text)
    return values  # type: ignore[return-value]


def camera_view_support(
    bbox: tuple[float, float, float, float],
    z_range: tuple[float, float] | None,
    cameras: dict[int, dict[str, Any]],
    images: Sequence[dict[str, Any]],
    margin: float,
) -> int:
    if z_range is None:
        return 0
    x0, y0, x1, y1 = bbox
    z0, z1 = z_range
    xs = (x0, (x0 + x1) / 2, x1)
    ys = (y0, (y0 + y1) / 2, y1)
    points_global = np.array([(x, y, z) for z in (z0, z1) for y in ys for x in xs], dtype=np.float64)
    points_local = points_global - np.array([690953.0, 5336071.0, 604.0])
    support = 0
    for image in images:
        camera = cameras[image["camera_id"]]
        xyz = (image["rotation"] @ points_local.T).T + image["translation"]
        positive = xyz[:, 2] > 1e-6
        if not np.any(positive):
            continue
        params = camera["params"]
        if camera["model_id"] == 1:
            fx, fy, cx, cy = params
        elif camera["model_id"] == 0:
            fx, cx, cy = params
            fy = fx
        else:
            fx = fy = params[0]
            cx, cy = params[1], params[2]
        uv = np.empty((len(xyz), 2), dtype=np.float64)
        uv[:, 0] = fx * xyz[:, 0] / xyz[:, 2] + cx
        uv[:, 1] = fy * xyz[:, 1] / xyz[:, 2] + cy
        inside = positive & (uv[:, 0] >= -margin) & (uv[:, 0] <= camera["width"] + margin) & (uv[:, 1] >= -margin) & (uv[:, 1] <= camera["height"] + margin)
        if np.any(inside):
            support += 1
    return support


def terrain_residual(a: GridSummary, b: GridSummary, label: str) -> dict[str, Any]:
    valid = np.isfinite(a.min_z) & np.isfinite(b.min_z)
    delta = a.min_z[valid] - b.min_z[valid]
    if not len(delta):
        return {"pair": label, "overlap_cells": 0, "status": "MISSING", "transform_fitted": false_value()}
    median = float(np.median(delta))
    mad = float(np.median(np.abs(delta - median)))
    return {
        "pair": label,
        "overlap_cells": int(len(delta)),
        "z_delta_a_minus_b_median_m": median,
        "z_delta_mad_m": mad,
        "z_delta_rmse_m": float(np.sqrt(np.mean(delta**2))),
        "transform_fitted": false_value(),
        "transform_applied_from_reference": false_value(),
        "interpretation": "post-transform measurement only; no translation, rotation, crop, threshold or stopping rule was fitted",
        "status": "PARTIAL_VERTICAL_DATUM_UNKNOWN" if "C1" in label else "READY_MEASUREMENT",
    }


def false_value() -> bool:
    return False


def load_candidate_ids_after_reference_freeze(path: Path) -> tuple[list[str], dict[str, Any]]:
    """Read only the first stable-ID field from the frozen ledger.

    The historical CSV contains LoD2-derived bbox text in later columns.  Those
    bytes are necessarily traversed to reach line boundaries, but the fields are
    never decoded, parsed, returned or used.  This is an identity-only join, not
    an admissible spatial crosswalk.
    """
    stable_ids: list[str] = []
    bytes_read = 0
    with path.open("rb") as handle:
        header = handle.readline()
        bytes_read += len(header)
        if header.split(b",", 1)[0] != b"stable_id":
            raise RuntimeError("candidate ledger first field is not stable_id")
        for line in handle:
            bytes_read += len(line)
            stable_ids.append(line.split(b",", 1)[0].decode("ascii"))
    stable_ids.sort()
    if len(stable_ids) != 199 or len(set(stable_ids)) != 199:
        raise RuntimeError("candidate ledger is not exact 199 unique IDs")
    digest = sha256_bytes("".join(f"{stable_id}\n" for stable_id in stable_ids).encode())
    if digest != "047717a5d678aeed540602a2d4fc9a57a076e2ac9205b22a4de75315c1622fe5":
        raise RuntimeError("candidate stable-ID set digest mismatch")
    return stable_ids, {
        "path": path.relative_to(REPO).as_posix(),
        "bytes_read_for_line_traversal": bytes_read,
        "parsed_columns": ["stable_id"],
        "lod2_bbox_columns_parsed_or_used": 0,
        "stable_id_count": len(stable_ids),
        "stable_id_set_sha256": digest,
        "join_stage": "AFTER_PRE_ID_REFERENCE_DIGEST_FREEZE",
    }


def load_c5_ids() -> set[str]:
    path = REPO / "artifacts/manifests/gate_s0/common_base_r2a/lod2_derived_lod1_lineage_v1.csv"
    with path.open(newline="", encoding="utf-8") as handle:
        rows = csv.DictReader(handle)
        return {row["stable_building_id"] for row in rows}


def identity_only_reference_join(stable_ids: Sequence[str]) -> list[dict[str, Any]]:
    return [
        {
            "stable_id": stable_id,
            "reference_component_ids": "",
            "reference_component_count": "UNKNOWN",
            "reference_cell_count": "UNKNOWN",
            "join_status": "MISSING_INDEPENDENT_STABLE_ID_SPATIAL_CROSSWALK",
            "geometry_modified_by_join": "false",
            "lod2_coordinates_used": "false",
            "join_stage": "AFTER_PRE_ID_REFERENCE_DIGEST_FREEZE",
        }
        for stable_id in stable_ids
    ]


def assign_splits(rows: Sequence[dict[str, Any]], seed: str) -> dict[str, str]:
    groups: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        if row["e_paired"] != "true":
            continue
        groups[row["spatial_group_id"]].append(row["stable_id"])
    ordered = sorted(groups, key=lambda group: hashlib.sha256(f"{seed}|{group}".encode()).hexdigest())
    total = sum(len(groups[group]) for group in ordered)
    targets = {"development": 0.6 * total, "validation": 0.2 * total, "held_out": 0.2 * total}
    assigned = {"development": 0, "validation": 0, "held_out": 0}
    result: dict[str, str] = {}
    for group in ordered:
        choices = sorted(targets, key=lambda split: (assigned[split] / max(targets[split], 1.0), split))
        split = choices[0]
        result[group] = split
        assigned[split] += len(groups[group])
    return result


def no_repeat_preflight(output_root: Path) -> dict[str, Any]:
    if not output_root.is_dir():
        raise RuntimeError("accepted output namespace is missing")
    seen: list[str] = []
    directory_entries = 0
    directories_scanned = 0
    for root, dirs, files in os.walk(output_root):
        directories_scanned += 1
        directory_entries += len(dirs) + len(files)
        rel_root = Path(root).relative_to(output_root)
        for name in sorted(files):
            seen.append((rel_root / name).as_posix())
        dirs.sort()
    allowed = {ALLOWED_PREEXISTING_RELATIVE.as_posix()}
    unexpected = sorted(set(seen) - allowed)
    if unexpected:
        raise RuntimeError(f"partial output without completed ledger: {unexpected}")
    return {
        "task_namespace_entries_enumerated": directory_entries,
        "task_namespace_file_entries_enumerated": len(seen),
        "task_namespace_directories_scanned": directories_scanned,
        "allowed_preexisting_control_files": sorted(seen),
        "unexpected_outputs": unexpected,
        "completed_ledger_present": False,
        "external_scientific_payload_read_bytes_before_guard": 0,
        "external_scientific_payload_hashed_bytes_before_guard": 0,
    }


def repo_output_preflight() -> dict[str, Any]:
    existing = [path.relative_to(REPO).as_posix() for path in INTENDED_REPO_OUTPUTS if path.exists()]
    if existing:
        raise RuntimeError(f"intended Git output exists without completed ledger: {existing}")
    return {"exact_paths_checked": len(INTENDED_REPO_OUTPUTS), "existing_paths": existing}


def completed_ledger_reuse_receipt(data: bytes) -> dict[str, Any]:
    payload = json.loads(data)
    return {
        "status": "COMPLETED_LEDGER_REUSED",
        "ledger_lookup_bytes_read": len(data),
        "ledger_lookup_bytes_hashed": len(data),
        "ledger_sha256": sha256_bytes(data),
        "external_scientific_payload_read_bytes": 0,
        "external_scientific_payload_hashed_bytes": 0,
        "non_ledger_output_bytes_read_or_hashed": 0,
        "writes": 0,
        "operation_id": payload["operation_identity"]["operation_id"],
    }


CURRENT_ARTIFACT_ROOT = Path("/artifacts/JointBuildGS")


def main() -> int:
    global CURRENT_ARTIFACT_ROOT
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", default="/artifacts/JointBuildGS")
    args = parser.parse_args()

    if LEDGER_PATH.exists():
        data = LEDGER_PATH.read_bytes()
        print(json.dumps(completed_ledger_reuse_receipt(data), sort_keys=True))
        return 0

    CURRENT_ARTIFACT_ROOT = Path(args.artifact_root).resolve()
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if CURRENT_ARTIFACT_ROOT.as_posix() != config["artifact_root"]:
        raise RuntimeError("artifact root differs from accepted config")
    output_root = CURRENT_ARTIFACT_ROOT / config["output_namespace"]
    guard = no_repeat_preflight(output_root)
    guard["repo_output_guard"] = repo_output_preflight()

    script_blob = file_blob(Path(__file__))
    config_blob = file_blob(CONFIG_PATH)
    operation_id = sha256_bytes(canonical_json_bytes({
        "task_id": TASK,
        "accepted_commit": config["accepted_commit"],
        "effective_source_commit": config["effective_source_commit"],
        "experiment_host": platform.node(),
        "artifact_root": CURRENT_ARTIFACT_ROOT.as_posix(),
        "script_blob": script_blob,
        "config_blob": config_blob,
    }))
    started_record = write_external_json(
        output_root / STARTED_RELATIVE,
        {
            "schema": "jointbuildgs.gate_s0_integrated_started.v1",
            "task_id": TASK,
            "status": "STARTED_ADD_ONCE",
            "created_at": utc_now(),
            "operation_id": operation_id,
            "accepted_commit": config["accepted_commit"],
            "artifact_root": CURRENT_ARTIFACT_ROOT.as_posix(),
            "purpose": "crash-persistent no-repeat intent written before any selected scientific path stat/read/hash",
            "scientific_verdict": None,
        },
    )
    print(json.dumps({"stage": "STARTED_MARKER_WRITTEN", "operation_id": operation_id}, sort_keys=True), flush=True)
    operation_identity = {
        "schema": "jointbuildgs.gate_s0_integrated_operation_identity.v1",
        "operation_id": operation_id,
        "task_id": TASK,
        "experiment_host": platform.node(),
        "resolved_host_artifact_root": "/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts",
        "resolved_container_artifact_root": CURRENT_ARTIFACT_ROOT.as_posix(),
        "executable": {"path": str(Path(__file__).relative_to(REPO)), "git_blob_oid": script_blob, "containing_commit": "SELF"},
        "config": {"path": str(CONFIG_PATH.relative_to(REPO)), "git_blob_oid": config_blob, "containing_commit": "SELF"},
        "accepted_commit": config["accepted_commit"],
        "effective_source_commit": config["effective_source_commit"],
        "execution_command": "python scripts/input_and_alignment/gate_s0/integrated_freeze_closure_v1/run_integrated_freeze.py --artifact-root /artifacts/JointBuildGS",
        "runtime": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "laspy": laspy.__version__,
            "laspy_laz_backends_available": ["LazrsParallel", "Lazrs"],
            "laspy_laz_backend_selection": "laspy default preference from exact accepted image",
            "docker_image_id": "sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774",
        },
    }

    aoi = tuple(float(v) for v in config["aoi"]["bbox"])
    cell = float(config["grid"]["cell_m"])
    min_height = float(config["grid"]["minimum_building_height_m"])
    min_points = int(config["grid"]["minimum_points_per_building_cell"])
    payload_root = CURRENT_ARTIFACT_ROOT / config["retained_chain"]["payload_root"]

    sparse_spec, scene_spec, ply_spec, laz_spec = config["retained_chain"]["paths"]
    print(json.dumps({"stage": "HASH_SPARSE_ONCE"}), flush=True)
    sparse_record, cameras, images = fingerprint_sparse(payload_root / sparse_spec["path"])
    if sparse_record["files"] != sparse_spec["expected_files"] or sparse_record["bytes"] != sparse_spec["expected_bytes"]:
        raise RuntimeError("sparse exact byte/file count mismatch")
    print(json.dumps({"stage": "HASH_SCENE_MVS_ONCE"}), flush=True)
    scene_record, _ = hash_file_once(payload_root / scene_spec["path"])
    if scene_record["bytes"] != scene_spec["expected_bytes"]:
        raise RuntimeError("scene.mvs byte count mismatch")
    mvs_grid = GridSummary(aoi, cell)
    print(json.dumps({"stage": "HASH_AND_PROCESS_DENSE_PLY_ONCE"}), flush=True)
    ply_record, gravity = hash_ply_and_grid(payload_root / ply_spec["path"], mvs_grid, (690953.0, 5336071.0, 604.0))
    if ply_record["bytes"] != ply_spec["expected_bytes"]:
        raise RuntimeError("dense PLY byte count mismatch")
    print(json.dumps({"stage": "HASH_DENSE_LAZ_ONCE"}), flush=True)
    laz_record, _ = hash_file_once(payload_root / laz_spec["path"])
    if laz_record["bytes"] != laz_spec["expected_bytes"]:
        raise RuntimeError("dense LAZ byte count mismatch")
    selected_bytes = sparse_record["bytes"] + scene_record["bytes"] + ply_record["bytes"] + laz_record["bytes"]
    if selected_bytes != config["retained_chain"]["byte_ceiling"]:
        raise RuntimeError("four-path byte ceiling mismatch")

    external_records: list[dict[str, Any]] = [started_record]
    mvs_ply = write_grid_ply(output_root / "derived/mvs_common_class26_v1.ply", mvs_grid, min_height, min_points)
    external_records.append(mvs_ply)

    c1_grid = GridSummary(aoi, cell)
    c1_path = CURRENT_ARTIFACT_ROOT / config["c1"]["path"]
    print(json.dumps({"stage": "PROCESS_C1_ONCE"}), flush=True)
    c1_input = process_laz_once(c1_path, c1_grid, transform=True)
    c1_ply = write_grid_ply(output_root / "derived/c1_nadir_class26_v1.ply", c1_grid, min_height, min_points)
    external_records.append(c1_ply)

    ref_rows, ref_stats = reference_rows(c1_grid, min_height, min_points, int(config["grid"]["minimum_reference_component_cells"]))
    ref_fields = ["reference_component_id", "reference_plane_id", "cell_x", "cell_y", "z", "normal_x", "normal_y", "normal_z", "class"]
    reference_record = write_external_csv(output_root / "reference/uas_reference_pre_id_v1.csv", ref_fields, ref_rows)
    reference_record["freeze_stage"] = "BEFORE_ANY_STABLE_ID_JOIN"
    external_records.append(reference_record)
    pre_id_digest = reference_record["sha256"]

    c4_grid = GridSummary(aoi, cell)
    c4_inputs: list[dict[str, Any]] = []
    for tile in config["c4"]["tiles"]:
        print(json.dumps({"stage": "PROCESS_C4_TILE_ONCE", "tile": tile["tile_id"]}), flush=True)
        c4_inputs.append(process_laz_once(CURRENT_ARTIFACT_ROOT / tile["path"], c4_grid, transform=False))
    c4_ply = write_grid_ply(output_root / "derived/c4_als_class26_v1.ply", c4_grid, min_height, min_points)
    external_records.append(c4_ply)

    stable_ids, candidate_identity_read = load_candidate_ids_after_reference_freeze(REPO / config["eligibility"]["candidate_ledger"])
    c5_ids = load_c5_ids()
    joins = identity_only_reference_join(stable_ids)
    join_record = write_repo_csv(
        DOC_ROOT / "reference_id_join_v1.csv",
        ["stable_id", "reference_component_ids", "reference_component_count", "reference_cell_count", "join_status", "geometry_modified_by_join", "lod2_coordinates_used", "join_stage"],
        joins,
    )

    eligibility_rows: list[dict[str, Any]] = []
    for stable_id in stable_ids:
        c5_cov = stable_id in c5_ids
        eligibility_rows.append({
            "stable_id": stable_id,
            "candidate_set_member": "true",
            "independent_spatial_crosswalk": "MISSING",
            "current_image_view_support": "UNKNOWN_NO_ADMISSIBLE_ID_GEOMETRY",
            "c1_class6_cells": "UNKNOWN_NO_ADMISSIBLE_ID_GEOMETRY",
            "retained_mvs_class6_cells": "UNKNOWN_NO_ADMISSIBLE_ID_GEOMETRY",
            "c4_als_class6_cells": "UNKNOWN_NO_ADMISSIBLE_ID_GEOMETRY",
            "c5_lod1_available": str(c5_cov).lower(),
            "c5_prior_role": "LOD2_DERIVED_COARSE_LOD1_INPUT_ONLY",
            "independent_reference_component_count": "UNKNOWN_NO_ADMISSIBLE_ID_GEOMETRY",
            "independent_reference_coverage": "UNKNOWN_NO_ADMISSIBLE_ID_GEOMETRY",
            "c1_attemptable": "UNKNOWN",
            "c2_attemptable": "UNKNOWN",
            "c3_attemptable": "UNKNOWN",
            "c4_attemptable": "UNKNOWN",
            "c5_attemptable": "UNKNOWN",
            "u_target": "UNKNOWN",
            "e_paired": "UNKNOWN",
            "spatial_group_id": "MISSING_NO_INDEPENDENT_SPATIAL_CROSSWALK",
            "split": "UNASSIGNED_ELIGIBILITY_MISSING",
            "exclusion_reason": "INDEPENDENT_STABLE_ID_SPATIAL_CROSSWALK_MISSING;INPUT_LOD2_BBOX_PROHIBITED_FOR_CROP_OR_JOIN;C1_VERTICAL_DATUM_UNKNOWN",
            "held_out_accessed": "false",
        })
    split_by_group = assign_splits(eligibility_rows, config["eligibility"]["split_seed"])
    for row in eligibility_rows:
        if row["e_paired"] == "true":
            row["split"] = split_by_group[row["spatial_group_id"]]

    eligibility_fields = list(eligibility_rows[0])
    eligibility_record = write_repo_csv(DOC_ROOT / "eligibility_ledger_v1.csv", eligibility_fields, eligibility_rows)
    u_ids = [row["stable_id"] for row in eligibility_rows if row["u_target"] == "true"]
    e_ids = [row["stable_id"] for row in eligibility_rows if row["e_paired"] == "true"]

    smoke = synthetic_smoke_payload()
    smoke_writer = AddOnceWriter(output_root / "stage3/synthetic_common_interface_smoke.city.jsonl")
    smoke_writer.write(smoke)
    smoke_record = smoke_writer.close()
    smoke_record.update({"uri": artifact_uri(output_root / "stage3/synthetic_common_interface_smoke.city.jsonl"), "digest_method": "same_stream_as_add_once_serialization"})
    external_records.append(smoke_record)

    horizontal_checks = []
    for x, y, ex, ey in [
        (690791.74, 5335864.05, 690791.740001741, 5335864.049877891),
        (691154.65, 5336353.85, 691154.650001744, 5336353.849877889),
        (690953.0, 5336071.0, 690953.000001742, 5336070.999877892),
    ]:
        tx, ty = epsg32632_to_25832(np.array([x]), np.array([y]))
        horizontal_checks.append({"source": [x, y], "target": [float(tx[0]), float(ty[0])], "proj_9_3_1_reference": [ex, ey], "residual_m": math.hypot(float(tx[0]) - ex, float(ty[0]) - ey)})

    fingerprint = {
        "schema": "jointbuildgs.gate_s0_four_path_fingerprint.v1",
        "task_id": TASK,
        "operation_identity": operation_identity,
        "paths": [
            {"id": "sfm_sparse", "uri": "artifact://JointBuildGS/phase-payloads/p0-audit/data/work/mvs/colmap_dense/sparse", **sparse_record, "full_passes": 1},
            {"id": "dense_mvs_scene", "uri": "artifact://JointBuildGS/phase-payloads/p0-audit/data/work/mvs/openmvs/scene.mvs", **scene_record, "full_passes": 1},
            {"id": "dense_mvs_ply", "uri": "artifact://JointBuildGS/phase-payloads/p0-audit/data/work/mvs/openmvs/dim_dense.ply", **ply_record, "full_passes": 1, "processing_in_same_pass": "AOI support grid and terrain-normal gravity source"},
            {"id": "dense_mvs_laz", "uri": "artifact://JointBuildGS/phase-payloads/p0-audit/data/work/mvs/dim/dim_v1.laz", **laz_record, "full_passes": 1},
        ],
        "selected_logical_path_count": 4,
        "selected_regular_file_count": sparse_record["files"] + 3,
        "total_bytes": selected_bytes,
        "byte_ceiling": config["retained_chain"]["byte_ceiling"],
        "stereo_tree_entries_enumerated": 0,
        "stereo_tree_bytes_read_or_hashed": 0,
        "scientific_verdict": None,
    }
    write_repo_json(MANIFEST_ROOT / "four_path_fingerprint_v1.json", fingerprint)

    component_manifest = {
        "schema": "jointbuildgs.gate_s0_component_enablement.v1",
        "task_id": TASK,
        "common_source": config["common_source"],
        "components": [
            {"component": "source_membership", "enablement": "ON", "readiness": "READY", "evidence": "DEC-P1-012 exact 962/937/25"},
            {"component": "sfm_sparse", "enablement": "ON", "readiness": "READY", "evidence": sparse_record["merkle_sha256"]},
            {"component": "dense_mvs", "enablement": "ON", "readiness": "PARTIAL", "evidence": "four-path hashes bound; producer route strongly corroborated, not exact run-script attestation"},
            {"component": "depth", "enablement": "OFF", "readiness": "READY_OFF", "evidence": "first-wave administrative choice; no recovery/regeneration"},
            {"component": "normal_map_supervision", "enablement": "OFF", "readiness": "READY_OFF", "evidence": "first-wave administrative choice; no recovery/regeneration"},
            {"component": "confidence", "enablement": "OFF", "readiness": "READY_OFF", "evidence": "first-wave administrative choice; no generation"},
            {"component": "segmentation", "enablement": "OFF", "readiness": "READY_OFF", "evidence": "first-wave administrative choice; no generation"},
            {"component": "gravity", "enablement": "ON", "readiness": "READY", "evidence": gravity},
        ],
        "scientific_verdict": None,
    }
    write_repo_json(MANIFEST_ROOT / "component_enablement_v1.json", component_manifest)

    frame_receipt = {
        "schema": "jointbuildgs.gate_s0_frame_datum_gravity_receipt.v1",
        "task_id": TASK,
        "horizontal_transform": {
            "source": "EPSG:32632",
            "target": "EPSG:25832",
            "pipeline": "+proj=pipeline +step +inv +proj=utm +zone=32 +ellps=WGS84 +step +proj=utm +zone=32 +ellps=GRS80",
            "implementation": "pure Python vectorized UTM inverse/forward in task executable",
            "cross_check": "host PROJ 9.3.1 cs2cs only; processing executed in Docker",
            "checks": horizontal_checks,
            "max_cross_check_residual_m": max(item["residual_m"] for item in horizontal_checks),
        },
        "vertical_datum_contract": {
            "C1": "UNKNOWN; no vertical correction applied; not silently equated to DHHN2016",
            "C2_MVS": "retained canonical coordinates; producer evidence previously describes EGM96 but exact vertical transform remains unbound",
            "C4": "provider DHHN2016 declaration recorded",
            "evaluation_reference": "C1 UNKNOWN; independent reference remains PARTIAL for absolute vertical scoring",
        },
        "gravity": gravity,
        "registration_residuals": [terrain_residual(c1_grid, mvs_grid, "C1_MINUS_MVS"), terrain_residual(c1_grid, c4_grid, "C1_MINUS_C4_ALS")],
        "scientific_verdict": None,
    }
    write_repo_json(DOC_ROOT / "frame_datum_registration_gravity_receipt_v1.json", frame_receipt)

    derivatives = {
        "schema": "jointbuildgs.gate_s0_c1_c4_derivatives.v1",
        "task_id": TASK,
        "operation_identity": operation_identity,
        "classification_rule": config["c1"]["classification_rule"],
        "C1": {"input": c1_input, "output": c1_ply, "evaluation_class": "SELF_REFERENCE_UPPER_BASELINE", "readiness": "PARTIAL_VERTICAL_DATUM_UNKNOWN"},
        "C4": {"inputs": c4_inputs, "output": c4_ply, "input_independence": "four exact 2022 ALS tiles; distinct from 2024 C1 UAS source", "readiness": "READY_INPUT_PARTIAL_REGISTRATION"},
        "raw_input_digest_rehashes": 0,
        "scientific_verdict": None,
    }
    write_repo_json(MANIFEST_ROOT / "c1_c4_derivative_manifest_v1.json", derivatives)

    reference_manifest = {
        "schema": "jointbuildgs.gate_s0_independent_uas_reference.v1",
        "task_id": TASK,
        "source": {"asset_id": config["c1"]["asset_id"], "attested_sha256": config["c1"]["sha256_attested"], "full_passes_this_task": 1, "full_hashes_this_task": 0},
        "construction": "AOI-wide non-GT one-metre min/max classification and connected roof-cell/normal components from UAS LiDAR only",
        "pre_id_geometry": {**reference_record, **ref_stats},
        "pre_id_geometry_sha256": pre_id_digest,
        "identity_label_join": join_record,
        "candidate_identity_read": candidate_identity_read,
        "post_join_geometry_sha256": pre_id_digest,
        "geometry_digest_equal_before_after_id_join": True,
        "input_lod2_source_asset_reads": 0,
        "historical_candidate_ledger_bbox_fields_parsed_or_used": 0,
        "historical_candidate_ledger_line_bytes_traversed": candidate_identity_read["bytes_read_for_line_traversal"],
        "input_lod2_used_for_geometry_registration_crop_tuning_stopping": False,
        "stable_id_join_timing": "after pre-ID geometry digest freeze",
        "identity_rows_without_spatial_crosswalk": len(joins),
        "C1_evaluation_class": "SELF_REFERENCE_UPPER_BASELINE",
        "C2_to_C5_reference_role": "SCORE_ONLY_INDEPENDENT_OF_INPUT_LOD2",
        "readiness": "PARTIAL_REFERENCE_FROZEN_BUT_ID_SPATIAL_CROSSWALK_AND_VERTICAL_DATUM_MISSING",
        "scientific_verdict": None,
    }
    write_repo_json(MANIFEST_ROOT / "independent_reference_manifest_v1.json", reference_manifest)

    universe_manifest = {
        "schema": "jointbuildgs.gate_s0_universe.v1",
        "task_id": TASK,
        "candidate_count": 199,
        "candidate_stable_id_set_sha256": config["eligibility"]["stable_id_set_sha256"],
        "eligibility_ledger": eligibility_record,
        "u_target_status": "MISSING",
        "u_target_count": None,
        "u_target_id_set_sha256": None,
        "e_paired_status": "MISSING",
        "e_paired_count": None,
        "e_paired_id_set_sha256": None,
        "strict_blockers": ["INDEPENDENT_STABLE_ID_SPATIAL_CROSSWALK_MISSING", "C1_VERTICAL_DATUM_UNKNOWN"],
        "method_failures_after_execution_are_g0_not_exclusions": True,
        "held_out_accessed": False,
        "scientific_verdict": None,
    }
    write_repo_json(MANIFEST_ROOT / "universe_manifest_v1.json", universe_manifest)

    split_counts = Counter(row["split"] for row in eligibility_rows if row["e_paired"] == "true")
    split_manifest = {
        "schema": "jointbuildgs.gate_s0_exhaustive_spatial_split.v1",
        "task_id": TASK,
        "mode": "EXHAUSTIVE_PARTITION",
        "seed": config["eligibility"]["split_seed"],
        "algorithm": "whole 50 m spatial groups ordered by SHA256(seed|group_id), allocated 60/20/20 without splitting groups",
        "eligible_count": None,
        "group_assignments": split_by_group,
        "split_counts": dict(split_counts),
        "all_e_paired_assigned_exactly_once": None,
        "group_cross_split_count": None,
        "held_out_accessed": False,
        "status": "MISSING_E_PAIRED_AND_INDEPENDENT_SPATIAL_GROUPS",
        "scientific_verdict": None,
    }
    write_repo_json(MANIFEST_ROOT / "split_manifest_v1.json", split_manifest)

    stage3_manifest = {
        "schema": "jointbuildgs.gate_s0_stage3_common_interface.v1",
        "task_id": TASK,
        "interface_path": "src/stage3/gate_s0_integrated_v1/interface.py",
        "interface_git_blob": file_blob(REPO / "src/stage3/gate_s0_integrated_v1/interface.py"),
        "conditions": ["C1_L_upper", "C2_MVS", "C3_GS_image", "C4_GS_lidar_prior", "C5_GS_lod1_prior"],
        "roofprint_protocol": "R_DERIVED_NON_GT_CONVEX_HULL_V1",
        "external_roofprint_allowed": False,
        "input_classes": {"ground": 2, "building": 6},
        "crs": "EPSG:25832",
        "gravity_sha256": sha256_bytes(canonical_json_bytes(gravity)),
        "roofer": {"version": "1.0.0", "image": config["stage3"]["roofer_image"], "local_availability": "MISSING_AS_OF_PRE_EXECUTION_DOCKER_IMAGE_INSPECT"},
        "p0_tools": {"image": config["stage3"]["p0_tools_image"], "local_availability": "MISSING_AS_OF_PRE_EXECUTION_DOCKER_IMAGE_INSPECT"},
        "synthetic_smoke": smoke_record,
        "quality_comparison_executed": False,
        "readiness": "PARTIAL_PENDING_PINNED_RUNTIME_AVAILABILITY",
        "scientific_verdict": None,
    }
    write_repo_json(MANIFEST_ROOT / "stage3_common_interface_manifest_v1.json", stage3_manifest)
    write_repo_json(DOC_ROOT / "stage3_synthetic_smoke_receipt_v1.json", {
        "schema": "jointbuildgs.gate_s0_stage3_smoke_receipt.v1",
        "task_id": TASK,
        "output": smoke_record,
        "conditions_exercised": 5,
        "external_roofprint_rejected_by_interface": True,
        "performance_or_quality_result": False,
        "scientific_verdict": None,
    })
    write_repo_json(MANIFEST_ROOT / "administrative_cost_caps_v1.json", {
        "schema": "jointbuildgs.gate_s0_administrative_cost_caps.v1",
        "task_id": TASK,
        **config["cost_caps"],
        "performance_authority": "NONE",
        "scientific_verdict": None,
    })

    output_manifest_path = MANIFEST_ROOT / "external_output_records_v1.json"
    output_records_manifest = {
        "schema": "jointbuildgs.gate_s0_integrated_external_outputs.v1",
        "task_id": TASK,
        "artifact_root": CURRENT_ARTIFACT_ROOT.as_posix(),
        "records": external_records,
        "digest_method": "each output SHA-256 computed in the sole add-once serialization stream",
        "scientific_verdict": None,
    }
    write_repo_json(output_manifest_path, output_records_manifest)

    accounting = {
        "retained_selected_read_bytes": selected_bytes,
        "retained_selected_hashed_bytes": selected_bytes,
        "retained_selected_logical_path_full_passes": 4,
        "retained_selected_regular_files": sparse_record["files"] + 3,
        "c1_source_file_size_bytes": c1_path.stat().st_size,
        "c1_actual_io_bytes_read": "UNKNOWN_NOT_INSTRUMENTED_BY_LASPY_LAZ_BACKEND",
        "c1_logical_decode_passes": 1,
        "c4_source_file_size_bytes": sum((CURRENT_ARTIFACT_ROOT / tile["path"]).stat().st_size for tile in config["c4"]["tiles"]),
        "c4_actual_io_bytes_read": "UNKNOWN_NOT_INSTRUMENTED_BY_LASPY_LAZ_BACKEND",
        "c4_logical_decode_passes": 4,
        "c1_c4_input_hash_bytes": 0,
        "c5_external_output_read_or_hash_bytes": 0,
        "images_zip_read_or_hash_bytes": 0,
        "opf_zip_read_or_hash_bytes": 0,
        "r1_large_input_read_or_hash_bytes": 0,
        "stereo_tree_entries_enumerated": 0,
        "stereo_tree_read_or_hash_bytes": 0,
        "input_lod2_source_geometry_asset_read_or_hash_bytes": 0,
        "historical_candidate_ledger_line_bytes_traversed": candidate_identity_read["bytes_read_for_line_traversal"],
        "historical_candidate_ledger_bbox_fields_parsed_or_used": 0,
        "held_out_read_or_hash_bytes": 0,
        "fusion_w1_read_or_hash_bytes": 0,
        "r_ext_read_or_hash_bytes": 0,
        "external_output_written_bytes": sum(record["bytes"] for record in external_records),
    }
    ledger = {
        "schema": "jointbuildgs.gate_s0_integrated_no_repeat_ledger.v1",
        "task_id": TASK,
        "handoff_id": HANDOFF,
        "status": "COMPLETED",
        "completed_at": utc_now(),
        "operation_identity": operation_identity,
        "pre_access_guard": guard,
        "first_invocation": accounting,
        "second_invocation_contract": {
            "ledger_lookup_bytes_read": "REPORT_ACTUAL",
            "ledger_lookup_bytes_hashed": "REPORT_ACTUAL",
            "external_scientific_payload_read_bytes": 0,
            "external_scientific_payload_hashed_bytes": 0,
            "non_ledger_output_bytes_read_or_hashed": 0,
            "writes": 0,
        },
        "r2b_accounting_correction": "A completed lookup reads and hashes the completed ledger itself; only non-ledger outputs and external payloads remain zero-read/zero-hash on reuse.",
        "forbidden_paths_accessed": [],
        "scientific_verdict": None,
    }
    write_repo_json(LEDGER_PATH, ledger)
    print(json.dumps({"status": "COMPLETED", "operation_id": operation_id, "accounting": accounting}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
