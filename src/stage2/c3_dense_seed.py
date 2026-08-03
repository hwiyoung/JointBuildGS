"""One-read C3 dense-MVS seed preflight and selected derivative producer.

The producer reads the exact common ``dim_dense.ply`` natural stream once,
computes the source SHA-256 while consuming that stream, and builds all three
frozen voxel candidates from the same cropped points.  Intermediate external
sort runs are private scratch data.  Only the finest candidate satisfying the
dense-point cap is published, once, as a local-coordinate XYZ PLY.

The historical ``seed_prep_dense`` pipeline used PDAL's
``voxelcenternearestneighbor`` filter.  The frozen OpenMVS source is already in
GS-local coordinates, so this implementation first adds the exact local-to-world
translation, preserves the representative rule on a fixed EPSG:25832 origin,
and makes previously implicit ties deterministic: world XYZ lexicographic order,
then source row.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import heapq
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import tempfile
from typing import BinaryIO, Iterable

import numpy as np


EXACT_DENSE_SOURCE_POINTS = 43_942_554
EXACT_DENSE_SOURCE_BYTES = 659_138_498
EXACT_SFM_SPARSE_POINTS = 371_808
FROZEN_AOI_XY = (690_791.74, 5_335_864.05, 691_154.65, 5_336_353.85)
LOCAL_OFFSET_XYZ = (690_953.0, 5_336_071.0, 604.0)
LOCAL_Z_RANGE = (-65.0, 30.0)
VOXEL_ORIGIN_XYZ = (0.0, 0.0, 0.0)
VOXEL_SPACINGS_M = (0.10, 0.20, 0.40)
MAX_DENSE_SEED_POINTS = 3_000_000
UTARGET199_NEUTRAL_VOXEL_SPACINGS_M = (0.50, 1.00, 2.00, 4.00)
UTARGET199_NEUTRAL_MAX_DENSE_SEED_POINTS = 220_000
UTARGET199_NEUTRAL_CONTRACT = "UTARGET199_NEUTRAL_UNCLASSIFIED_DENSE_V1"
REPRESENTATIVE_RULE = "VOXEL_CENTER_NEAREST_WORLD_XYZ_LEXICOGRAPHIC_THEN_SOURCE_ROW"
VOXEL_INDEX_RULE = "FLOOR_EACH_AXIS_OF_EPSG25832_XYZ_MINUS_FIXED_ORIGIN_DIV_VOXEL_M"
OUTPUT_ORDER = "LEXICOGRAPHIC_VOXEL_IX_IY_IZ"
RECEIPT_SCHEMA = "jointbuildgs.c3_dense_seed_receipt.v1"
REPO = Path(__file__).resolve().parents[2]

_PLY_SCALAR_TYPES = {
    "char": "i1",
    "int8": "i1",
    "uchar": "u1",
    "uint8": "u1",
    "short": "<i2",
    "int16": "<i2",
    "ushort": "<u2",
    "uint16": "<u2",
    "int": "<i4",
    "int32": "<i4",
    "uint": "<u4",
    "uint32": "<u4",
    "float": "<f4",
    "float32": "<f4",
    "double": "<f8",
    "float64": "<f8",
}

_RUN_DTYPE = np.dtype(
    [
        ("ix", "<i8"),
        ("iy", "<i8"),
        ("iz", "<i8"),
        ("world_x", "<f8"),
        ("world_y", "<f8"),
        ("world_z", "<f8"),
        ("source_row", "<u8"),
    ],
    align=False,
)


class C3DenseSeedError(RuntimeError):
    """The bounded C3 dense-seed contract failed closed."""


@dataclass(frozen=True)
class DenseSeedConfig:
    """Frozen producer parameters plus exact source identity expectations."""

    source_path: Path
    output_path: Path
    receipt_path: Path
    expected_input_bytes: int = EXACT_DENSE_SOURCE_BYTES
    expected_input_points: int = EXACT_DENSE_SOURCE_POINTS
    expected_input_sha256: str | None = None
    aoi_xy: tuple[float, float, float, float] = FROZEN_AOI_XY
    local_offset_xyz: tuple[float, float, float] = LOCAL_OFFSET_XYZ
    local_z_range: tuple[float, float] = LOCAL_Z_RANGE
    voxel_spacings_m: tuple[float, float, float] = VOXEL_SPACINGS_M
    voxel_origin_xyz: tuple[float, float, float] = VOXEL_ORIGIN_XYZ
    max_dense_points: int = MAX_DENSE_SEED_POINTS
    chunk_points: int = 1_000_000
    temp_parent: Path | None = None
    contract: str = "FIRST_WAVE_V2"

    def validate(self, *, require_exact_common: bool) -> None:
        if self.expected_input_bytes <= 0 or self.expected_input_points <= 0:
            raise C3DenseSeedError("expected source bytes and points must be positive")
        if self.expected_input_sha256 is not None and re.fullmatch(
            r"[0-9a-f]{64}", self.expected_input_sha256
        ) is None:
            raise C3DenseSeedError("expected source SHA-256 must be 64 lowercase hex digits")
        allowed_voxel_contracts = {
            "FIRST_WAVE_V2": (VOXEL_SPACINGS_M, MAX_DENSE_SEED_POINTS),
            UTARGET199_NEUTRAL_CONTRACT: (
                UTARGET199_NEUTRAL_VOXEL_SPACINGS_M,
                UTARGET199_NEUTRAL_MAX_DENSE_SEED_POINTS,
            ),
        }
        expected_contract = allowed_voxel_contracts.get(self.contract)
        if expected_contract is None:
            raise C3DenseSeedError("unknown C3 dense-seed contract")
        if tuple(self.voxel_spacings_m) != tuple(expected_contract[0]):
            raise C3DenseSeedError(
                f"C3 voxel candidates differ from contract {self.contract}"
            )
        if tuple(self.voxel_origin_xyz) != VOXEL_ORIGIN_XYZ:
            raise C3DenseSeedError("C3 voxel origin must remain fixed at EPSG:25832 [0,0,0]")
        if self.max_dense_points <= 0 or self.chunk_points <= 0:
            raise C3DenseSeedError("point cap and chunk size must be positive")
        min_x, min_y, max_x, max_y = self.aoi_xy
        if not all(math.isfinite(value) for value in self.aoi_xy) or not (
            min_x < max_x and min_y < max_y
        ):
            raise C3DenseSeedError("AOI bounds are invalid")
        if not all(math.isfinite(value) for value in self.local_offset_xyz):
            raise C3DenseSeedError("local offset is invalid")
        if not all(math.isfinite(value) for value in self.local_z_range) or not (
            self.local_z_range[0] < self.local_z_range[1]
        ):
            raise C3DenseSeedError("local Z range is invalid")
        source = self.source_path.resolve(strict=False)
        output = self.output_path.resolve(strict=False)
        receipt = self.receipt_path.resolve(strict=False)
        if len({source, output, receipt}) != 3:
            raise C3DenseSeedError("source, output, and receipt paths must be distinct")
        if self.output_path.suffix.lower() != ".ply":
            raise C3DenseSeedError("selected dense derivative must use a .ply path")
        if self.receipt_path.suffix.lower() != ".json":
            raise C3DenseSeedError("dense-seed receipt must use a .json path")
        if require_exact_common and (
            self.expected_input_bytes != EXACT_DENSE_SOURCE_BYTES
            or self.expected_input_points != EXACT_DENSE_SOURCE_POINTS
            or tuple(self.aoi_xy) != FROZEN_AOI_XY
            or tuple(self.local_offset_xyz) != LOCAL_OFFSET_XYZ
            or tuple(self.local_z_range) != LOCAL_Z_RANGE
            or self.max_dense_points != expected_contract[1]
        ):
            raise C3DenseSeedError(
                "production C3 entry requires exact source size/count, AOI, local transform, Z, and 3M cap"
            )


@dataclass(frozen=True)
class _PlyHeader:
    vertex_count: int
    dtype: np.dtype
    x_name: str
    y_name: str
    z_name: str
    properties: tuple[tuple[str, str], ...]
    header_bytes: int


def _open_source(path: Path) -> BinaryIO:
    """Single indirection used by tests to prove one natural source open."""

    return path.open("rb")


def _canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _spacing_key(spacing: float) -> str:
    return f"{spacing:.2f}"


def _spacing_slug(spacing: float) -> str:
    return _spacing_key(spacing).replace(".", "p")


def _read_header(stream: BinaryIO, digest: "hashlib._Hash") -> _PlyHeader:
    lines: list[str] = []
    header_bytes = 0
    while True:
        raw = stream.readline()
        if not raw:
            raise C3DenseSeedError("PLY header ended before end_header")
        digest.update(raw)
        header_bytes += len(raw)
        if header_bytes > 1_048_576:
            raise C3DenseSeedError("PLY header exceeds the 1 MiB safety bound")
        try:
            line = raw.decode("ascii").strip()
        except UnicodeDecodeError as error:
            raise C3DenseSeedError("PLY header must be ASCII") from error
        lines.append(line)
        if line == "end_header":
            break
    if not lines or lines[0] != "ply" or "format binary_little_endian 1.0" not in lines:
        raise C3DenseSeedError("source must be binary_little_endian PLY 1.0")

    active_element: str | None = None
    element_counts: dict[str, int] = {}
    vertex_properties: list[tuple[str, str]] = []
    for line in lines[1:]:
        tokens = line.split()
        if not tokens or tokens[0] in {"comment", "obj_info", "format", "end_header"}:
            continue
        if tokens[0] == "element":
            if len(tokens) != 3:
                raise C3DenseSeedError("malformed PLY element declaration")
            try:
                count = int(tokens[2])
            except ValueError as error:
                raise C3DenseSeedError("PLY element count is not an integer") from error
            if count < 0 or tokens[1] in element_counts:
                raise C3DenseSeedError("PLY element declaration is invalid or duplicated")
            active_element = tokens[1]
            element_counts[active_element] = count
            continue
        if tokens[0] == "property":
            if active_element is None:
                raise C3DenseSeedError("PLY property precedes an element")
            if len(tokens) >= 2 and tokens[1] == "list":
                if element_counts[active_element] != 0:
                    raise C3DenseSeedError("non-empty PLY list elements are unsupported")
                continue
            if len(tokens) != 3 or tokens[1] not in _PLY_SCALAR_TYPES:
                raise C3DenseSeedError("unsupported PLY scalar property")
            if active_element == "vertex":
                vertex_properties.append((tokens[2], tokens[1]))
            elif element_counts[active_element] != 0:
                raise C3DenseSeedError("only a non-empty vertex element is supported")
            continue
        raise C3DenseSeedError(f"unsupported PLY header directive: {tokens[0]}")

    if "vertex" not in element_counts or element_counts["vertex"] <= 0:
        raise C3DenseSeedError("PLY must contain a non-empty vertex element")
    if any(name != "vertex" and count != 0 for name, count in element_counts.items()):
        raise C3DenseSeedError("PLY contains unsupported non-vertex payload")
    lowered = [name.lower() for name, _ in vertex_properties]
    if len(lowered) != len(set(lowered)) or not {"x", "y", "z"}.issubset(lowered):
        raise C3DenseSeedError("PLY vertex properties require unique x/y/z names")
    dtype = np.dtype(
        [(name, _PLY_SCALAR_TYPES[type_name]) for name, type_name in vertex_properties],
        align=False,
    )
    xyz_names = {name.lower(): name for name, _ in vertex_properties}
    return _PlyHeader(
        vertex_count=element_counts["vertex"],
        dtype=dtype,
        x_name=xyz_names["x"],
        y_name=xyz_names["y"],
        z_name=xyz_names["z"],
        properties=tuple(vertex_properties),
        header_bytes=header_bytes,
    )


def _write_chunk_run(
    path: Path,
    world_xyz: np.ndarray,
    source_rows: np.ndarray,
    spacing: float,
    origin_xyz: tuple[float, float, float],
) -> None:
    origin = np.asarray(origin_xyz, dtype=np.float64)
    voxel = np.floor((world_xyz - origin) / spacing).astype(np.int64)
    centers = origin + (voxel.astype(np.float64) + 0.5) * spacing
    distance_sq = np.sum(np.square(world_xyz - centers), axis=1)
    order = np.lexsort(
        (
            source_rows,
            world_xyz[:, 2],
            world_xyz[:, 1],
            world_xyz[:, 0],
            distance_sq,
            voxel[:, 2],
            voxel[:, 1],
            voxel[:, 0],
        )
    )
    ordered_voxel = voxel[order]
    first = np.ones(len(order), dtype=np.bool_)
    if len(order) > 1:
        first[1:] = np.any(ordered_voxel[1:] != ordered_voxel[:-1], axis=1)
    chosen = order[first]
    records = np.empty(len(chosen), dtype=_RUN_DTYPE)
    records["ix"] = voxel[chosen, 0]
    records["iy"] = voxel[chosen, 1]
    records["iz"] = voxel[chosen, 2]
    records["world_x"] = world_xyz[chosen, 0]
    records["world_y"] = world_xyz[chosen, 1]
    records["world_z"] = world_xyz[chosen, 2]
    records["source_row"] = source_rows[chosen]
    with path.open("xb") as stream:
        stream.write(records.tobytes(order="C"))


def _read_source_once_to_runs(
    config: DenseSeedConfig, scratch: Path
) -> tuple[dict[float, list[Path]], dict[str, object]]:
    source = config.source_path
    if source.is_symlink() or not source.is_file():
        raise C3DenseSeedError("dense source must be a regular non-symlink file")
    before = source.stat()
    if before.st_size != config.expected_input_bytes:
        raise C3DenseSeedError("dense source byte size differs before natural-stream read")

    runs: dict[float, list[Path]] = {spacing: [] for spacing in config.voxel_spacings_m}
    digest = hashlib.sha256()
    total_bytes = 0
    finite_points = 0
    cropped_points = 0
    min_x, min_y, max_x, max_y = config.aoi_xy
    z_min = config.local_offset_xyz[2] + config.local_z_range[0]
    z_max = config.local_offset_xyz[2] + config.local_z_range[1]
    with _open_source(source) as stream:
        opened = os.fstat(stream.fileno())
        if (opened.st_size, opened.st_mtime_ns) != (before.st_size, before.st_mtime_ns):
            raise C3DenseSeedError("dense source changed between stat and open")
        header = _read_header(stream, digest)
        total_bytes += header.header_bytes
        if header.vertex_count != config.expected_input_points:
            raise C3DenseSeedError("dense source vertex count differs")
        row_start = 0
        chunk_index = 0
        while row_start < header.vertex_count:
            count = min(config.chunk_points, header.vertex_count - row_start)
            expected = count * header.dtype.itemsize
            raw = stream.read(expected)
            if len(raw) != expected:
                raise C3DenseSeedError("dense source PLY body is truncated")
            digest.update(raw)
            total_bytes += len(raw)
            vertices = np.frombuffer(raw, dtype=header.dtype, count=count)
            source_local_xyz = np.column_stack(
                (
                    vertices[header.x_name].astype(np.float64, copy=False),
                    vertices[header.y_name].astype(np.float64, copy=False),
                    vertices[header.z_name].astype(np.float64, copy=False),
                )
            )
            finite = np.all(np.isfinite(source_local_xyz), axis=1)
            finite_points += int(np.count_nonzero(finite))
            world_xyz = source_local_xyz + np.asarray(
                config.local_offset_xyz, dtype=np.float64
            )
            keep = (
                finite
                & (world_xyz[:, 0] >= min_x)
                & (world_xyz[:, 0] <= max_x)
                & (world_xyz[:, 1] >= min_y)
                & (world_xyz[:, 1] <= max_y)
                & (world_xyz[:, 2] >= z_min)
                & (world_xyz[:, 2] <= z_max)
            )
            kept = world_xyz[keep]
            kept_rows = np.arange(row_start, row_start + count, dtype=np.uint64)[keep]
            cropped_points += len(kept)
            if len(kept):
                for spacing in config.voxel_spacings_m:
                    path = scratch / f"run_{_spacing_slug(spacing)}_{chunk_index:06d}.bin"
                    _write_chunk_run(
                        path, kept, kept_rows, spacing, config.voxel_origin_xyz
                    )
                    runs[spacing].append(path)
            row_start += count
            chunk_index += 1
        trailing_bytes = 0
        while True:
            extra = stream.read(1 << 20)
            if not extra:
                break
            digest.update(extra)
            total_bytes += len(extra)
            trailing_bytes += len(extra)
        closed_state = os.fstat(stream.fileno())

    after = source.stat()
    identity_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    identity_opened = (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
    identity_closed = (
        closed_state.st_dev,
        closed_state.st_ino,
        closed_state.st_size,
        closed_state.st_mtime_ns,
    )
    identity_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if len({identity_before, identity_opened, identity_closed, identity_after}) != 1:
        raise C3DenseSeedError("dense source identity changed during natural-stream read")
    if trailing_bytes:
        raise C3DenseSeedError("dense source contains unexpected bytes after vertex payload")
    if total_bytes != config.expected_input_bytes:
        raise C3DenseSeedError("dense source bytes consumed differ from the exact expectation")
    source_sha256 = digest.hexdigest()
    if (
        config.expected_input_sha256 is not None
        and source_sha256 != config.expected_input_sha256
    ):
        raise C3DenseSeedError("dense source SHA-256 differs after the one natural read")
    return runs, {
        "path": str(source),
        "bytes": total_bytes,
        "sha256": source_sha256,
        "vertex_count": header.vertex_count,
        "ply_format": "binary_little_endian_1.0",
        "ply_properties": [
            {"name": name, "type": type_name} for name, type_name in header.properties
        ],
        "finite_points": finite_points,
        "cropped_points": cropped_points,
        "natural_stream_reads": 1,
        "digest_computed_during_natural_read": True,
        "standalone_rehash_passes": 0,
    }


def _heap_item(
    mapping: np.memmap,
    index: int,
    run_index: int,
    spacing: float,
    origin_xyz: tuple[float, float, float],
) -> tuple[object, ...]:
    record = mapping[index]
    ix, iy, iz = int(record["ix"]), int(record["iy"]), int(record["iz"])
    world_x = float(record["world_x"])
    world_y = float(record["world_y"])
    world_z = float(record["world_z"])
    center_x = origin_xyz[0] + (ix + 0.5) * spacing
    center_y = origin_xyz[1] + (iy + 0.5) * spacing
    center_z = origin_xyz[2] + (iz + 0.5) * spacing
    distance_sq = (
        (world_x - center_x) ** 2
        + (world_y - center_y) ** 2
        + (world_z - center_z) ** 2
    )
    return (
        ix,
        iy,
        iz,
        distance_sq,
        world_x,
        world_y,
        world_z,
        int(record["source_row"]),
        run_index,
        index,
    )


def _flush_xyz_buffer(stream: BinaryIO, buffer: list[tuple[float, float, float]]) -> None:
    if buffer:
        values = np.asarray(buffer, dtype="<f4")
        stream.write(values.tobytes(order="C"))
        buffer.clear()


def _merge_runs_to_candidate_body(
    run_paths: Iterable[Path],
    body_path: Path,
    spacing: float,
    origin_xyz: tuple[float, float, float],
    local_offset_xyz: tuple[float, float, float],
) -> int:
    mappings: list[np.memmap] = []
    heap: list[tuple[object, ...]] = []
    try:
        for run_index, path in enumerate(run_paths):
            if path.stat().st_size % _RUN_DTYPE.itemsize:
                raise C3DenseSeedError("temporary voxel run has an invalid byte length")
            count = path.stat().st_size // _RUN_DTYPE.itemsize
            if count == 0:
                continue
            mapping = np.memmap(path, dtype=_RUN_DTYPE, mode="r", shape=(count,))
            mappings.append(mapping)
            actual_index = len(mappings) - 1
            heapq.heappush(
                heap,
                _heap_item(mapping, 0, actual_index, spacing, origin_xyz),
            )
        candidate_count = 0
        last_key: tuple[int, int, int] | None = None
        output_buffer: list[tuple[float, float, float]] = []
        with body_path.open("xb") as stream:
            while heap:
                item = heapq.heappop(heap)
                key = (int(item[0]), int(item[1]), int(item[2]))
                run_index = int(item[8])
                source_index = int(item[9])
                if key != last_key:
                    output_buffer.append(
                        (
                            float(item[4]) - local_offset_xyz[0],
                            float(item[5]) - local_offset_xyz[1],
                            float(item[6]) - local_offset_xyz[2],
                        )
                    )
                    candidate_count += 1
                    last_key = key
                    if len(output_buffer) >= 65_536:
                        _flush_xyz_buffer(stream, output_buffer)
                next_index = source_index + 1
                mapping = mappings[run_index]
                if next_index < len(mapping):
                    heapq.heappush(
                        heap,
                        _heap_item(
                            mapping, next_index, run_index, spacing, origin_xyz
                        ),
                    )
            _flush_xyz_buffer(stream, output_buffer)
        if body_path.stat().st_size != candidate_count * 12:
            raise C3DenseSeedError("temporary candidate body size differs from XYZ count")
        return candidate_count
    finally:
        for mapping in mappings:
            mmap_object = getattr(mapping, "_mmap", None)
            if mmap_object is not None:
                mmap_object.close()


def _selected_ply_header(point_count: int) -> bytes:
    return (
        "ply\n"
        "format binary_little_endian 1.0\n"
        "comment JointBuildGS C3 selected dense seed v1\n"
        f"element vertex {point_count}\n"
        "property float x\n"
        "property float y\n"
        "property float z\n"
        "end_header\n"
    ).encode("ascii")


def _write_selected_output_temp(
    body_path: Path, output_parent: Path, output_name: str, point_count: int
) -> tuple[Path, int, str]:
    file_descriptor, raw_path = tempfile.mkstemp(
        prefix=f".{output_name}.", suffix=".tmp", dir=output_parent
    )
    temp_path = Path(raw_path)
    digest = hashlib.sha256()
    total_bytes = 0
    try:
        with os.fdopen(file_descriptor, "wb") as output, body_path.open("rb") as body:
            header = _selected_ply_header(point_count)
            output.write(header)
            digest.update(header)
            total_bytes += len(header)
            while True:
                chunk = body.read(1 << 20)
                if not chunk:
                    break
                output.write(chunk)
                digest.update(chunk)
                total_bytes += len(chunk)
            output.flush()
            os.fsync(output.fileno())
    except Exception:
        try:
            os.close(file_descriptor)
        except OSError:
            pass
        temp_path.unlink(missing_ok=True)
        raise
    return temp_path, total_bytes, digest.hexdigest()


def _write_receipt_temp(receipt: dict[str, object], parent: Path, name: str) -> Path:
    file_descriptor, raw_path = tempfile.mkstemp(
        prefix=f".{name}.", suffix=".tmp", dir=parent
    )
    temp_path = Path(raw_path)
    try:
        with os.fdopen(file_descriptor, "wb") as stream:
            stream.write(_canonical_json_bytes(receipt))
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        try:
            os.close(file_descriptor)
        except OSError:
            pass
        temp_path.unlink(missing_ok=True)
        raise
    return temp_path


def _publish_pair_add_once(
    output_temp: Path, output_path: Path, receipt_temp: Path, receipt_path: Path
) -> None:
    if output_path.exists() or receipt_path.exists():
        raise C3DenseSeedError("output or receipt appeared before add-once publication")
    output_linked = False
    try:
        os.link(output_temp, output_path)
        output_linked = True
        os.link(receipt_temp, receipt_path)
    except OSError as error:
        if output_linked:
            output_path.unlink(missing_ok=True)
        raise C3DenseSeedError("add-once publication failed without overwriting targets") from error
    finally:
        output_temp.unlink(missing_ok=True)
        receipt_temp.unlink(missing_ok=True)


def _actual_clean_repository_head_for_repo(repository: Path) -> str:
    repo = repository.resolve(strict=True)
    git = [
        "git",
        "-c",
        "safe.directory=",
        "-c",
        f"safe.directory={repo}",
        "-C",
        str(repo),
    ]
    try:
        head_process = subprocess.run(
            [*git, "rev-parse", "--verify", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
        status_process = subprocess.run(
            [*git, "status", "--porcelain=v1", "--untracked-files=all"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise C3DenseSeedError("cannot bind the producer to the actual repository HEAD") from error
    head = head_process.stdout.strip()
    if re.fullmatch(r"[0-9a-f]{40}", head) is None:
        raise C3DenseSeedError("actual repository HEAD is not an exact commit")
    if status_process.stdout:
        raise C3DenseSeedError("production C3 producer requires a clean repository worktree")
    return head


def _actual_clean_repository_head() -> str:
    return _actual_clean_repository_head_for_repo(REPO)


def _produce_dense_seed(
    config: DenseSeedConfig,
    *,
    require_exact_common: bool,
    repository_commit: str,
    receipt_schema: str,
    receipt_status: str,
) -> dict[str, object]:
    """Shared implementation; only the public wrapper has production authority."""

    config.validate(require_exact_common=require_exact_common)
    if config.output_path.exists() or config.receipt_path.exists():
        raise C3DenseSeedError("selected output and receipt are add-once")
    config.output_path.parent.mkdir(parents=True, exist_ok=True)
    config.receipt_path.parent.mkdir(parents=True, exist_ok=True)
    if config.temp_parent is not None:
        config.temp_parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(
        prefix="c3_dense_seed_",
        dir=config.temp_parent if config.temp_parent is not None else None,
    ) as directory:
        scratch = Path(directory)
        scratch_capacity = shutil.disk_usage(scratch)
        scratch_worst_case_bytes = config.expected_input_points * (
            len(config.voxel_spacings_m) * (_RUN_DTYPE.itemsize + 12)
        )
        if scratch_capacity.free < scratch_worst_case_bytes:
            raise C3DenseSeedError("scratch capacity is below the deterministic worst-case bound")
        runs, input_receipt = _read_source_once_to_runs(config, scratch)
        candidate_counts: dict[float, int] = {}
        candidate_bodies: dict[float, Path] = {}
        for spacing in config.voxel_spacings_m:
            body = scratch / f"candidate_{_spacing_slug(spacing)}.xyz"
            candidate_counts[spacing] = _merge_runs_to_candidate_body(
                runs[spacing],
                body,
                spacing,
                config.voxel_origin_xyz,
                config.local_offset_xyz,
            )
            candidate_bodies[spacing] = body
        ordered_counts = [candidate_counts[value] for value in config.voxel_spacings_m]
        if not all(
            left >= right for left, right in zip(ordered_counts, ordered_counts[1:])
        ):
            raise C3DenseSeedError("voxel candidate counts violate nested-grid monotonicity")
        selected_spacing = next(
            (
                spacing
                for spacing in config.voxel_spacings_m
                if 0 < candidate_counts[spacing] <= config.max_dense_points
            ),
            None,
        )
        if selected_spacing is None:
            raise C3DenseSeedError("no frozen voxel candidate satisfies the dense-point cap")
        selected_count = candidate_counts[selected_spacing]
        if require_exact_common and _actual_clean_repository_head() != repository_commit:
            raise C3DenseSeedError("repository HEAD changed during the production preflight")
        output_temp, output_bytes, output_sha256 = _write_selected_output_temp(
            candidate_bodies[selected_spacing],
            config.output_path.parent,
            config.output_path.name,
            selected_count,
        )
        producer_path = Path(__file__)
        producer_bytes = producer_path.read_bytes()
        world_z_range = [
            config.local_offset_xyz[2] + config.local_z_range[0],
            config.local_offset_xyz[2] + config.local_z_range[1],
        ]
        receipt: dict[str, object] = {
            "schema": receipt_schema,
            "status": receipt_status,
            "repository_commit": repository_commit,
            "repository_worktree_clean_at_start_and_before_output_write": (
                True if require_exact_common else None
            ),
            "producer": {
                "path": "src/stage2/c3_dense_seed.py",
                "sha256": hashlib.sha256(producer_bytes).hexdigest(),
                "python": platform.python_version(),
                "numpy": np.__version__,
            },
            "input": input_receipt,
            "input_coordinate_frame": {
                "frame": "GS_LOCAL",
                "world_crs": "EPSG:25832",
                "local_to_world_translation": list(config.local_offset_xyz),
            },
            "crop_and_transform": {
                "crs": "EPSG:25832",
                "aoi_xy_inclusive": list(config.aoi_xy),
                "world_z_inclusive": world_z_range,
                "local_offset_xyz": list(config.local_offset_xyz),
                "local_z_inclusive": list(config.local_z_range),
                "operation_order": [
                    "FILTER_NONFINITE",
                    "TRANSFORM_SOURCE_GS_LOCAL_TO_WORLD_EPSG25832",
                    "CROP_FROZEN_AOI_XY_AND_WORLD_Z_INCLUSIVE",
                    "VOXELIZE_IN_WORLD_EPSG25832",
                    "TRANSFORM_SELECTED_REPRESENTATIVES_TO_LOCAL_XYZ",
                ],
            },
            "voxel_preflight": {
                "candidate_voxel_m_ascending": list(config.voxel_spacings_m),
                "candidate_dense_point_counts": {
                    _spacing_key(spacing): candidate_counts[spacing]
                    for spacing in config.voxel_spacings_m
                },
                "max_dense_seed_points": config.max_dense_points,
                "selection_rule": "FINEST_ASCENDING_CANDIDATE_WITH_DENSE_POINTS_LE_CAP",
                "selected_voxel_m": selected_spacing,
                "selected_dense_point_count": selected_count,
                "voxel_origin_xyz": list(config.voxel_origin_xyz),
                "voxel_index_rule": VOXEL_INDEX_RULE,
                "representative_rule": REPRESENTATIVE_RULE,
                "output_order": OUTPUT_ORDER,
            },
            "output": {
                "path": str(config.output_path),
                "format": "binary_little_endian_ply_xyz_float32",
                "vertex_count": selected_count,
                "bytes": output_bytes,
                "sha256": output_sha256,
                "publication": "ADD_ONCE_HARDLINK_FROM_SAME_FILESYSTEM_TEMP",
                "digest_computed_during_natural_write": True,
                "standalone_rehash_passes": 0,
            },
            "training_side_contract": {
                "concat_performed_by_this_producer": False,
                "all_sfm_sparse_points_to_concat_at_training": EXACT_SFM_SPARSE_POINTS,
                "selected_dense_points_to_add_once_at_training": selected_count,
                "sparse_only_allowed": False,
                "full_dense_direct_allowed": False,
                "full_dense_source_points": config.expected_input_points,
                "contract": config.contract,
                "classification_or_semantic_filtering": False,
            },
            "pass_accounting": {
                "source_natural_stream_reads": 1,
                "source_standalone_rehash_passes": 0,
                "selected_output_natural_writes": 1,
                "selected_output_standalone_rehash_passes": 0,
                "published_candidate_outputs": 1,
            },
            "scratch_capacity_preflight": {
                "free_bytes_before_source_read": scratch_capacity.free,
                "deterministic_worst_case_bytes": scratch_worst_case_bytes,
                "passed": True,
            },
            "performance_runs_started": 0,
            "scientific_verdict": None,
        }
        receipt_temp = _write_receipt_temp(
            receipt, config.receipt_path.parent, config.receipt_path.name
        )
        _publish_pair_add_once(
            output_temp,
            config.output_path,
            receipt_temp,
            config.receipt_path,
        )
        return receipt


def produce_dense_seed(config: DenseSeedConfig) -> dict[str, object]:
    """Run the exact-common production contract and bind it to the actual clean HEAD."""

    # Validate the frozen scientific inputs before invoking Git or opening the payload.
    config.validate(require_exact_common=True)
    repository_commit = _actual_clean_repository_head()
    return _produce_dense_seed(
        config,
        require_exact_common=True,
        repository_commit=repository_commit,
        receipt_schema=RECEIPT_SCHEMA,
        receipt_status="COMPLETED_PREFLIGHT_SELECTED_DENSE_SEED",
    )


def produce_utarget199_neutral_dense_seed(
    config: DenseSeedConfig,
) -> dict[str, object]:
    """Publish the unclassified, geometry-only dense seed shared by C3/C4/C5."""

    if config.contract != UTARGET199_NEUTRAL_CONTRACT:
        raise C3DenseSeedError(
            "U_target=199 neutral producer requires its exact named contract"
        )
    config.validate(require_exact_common=True)
    repository_commit = _actual_clean_repository_head()
    return _produce_dense_seed(
        config,
        require_exact_common=True,
        repository_commit=repository_commit,
        receipt_schema="jointbuildgs.c3_utarget199_neutral_dense_seed_receipt.v1",
        receipt_status="COMPLETED_NEUTRAL_UNCLASSIFIED_DENSE_SEED",
    )


def _produce_dense_seed_for_test(config: DenseSeedConfig) -> dict[str, object]:
    """Non-authoritative synthetic fixture path; never emits the production schema/status."""

    return _produce_dense_seed(
        config,
        require_exact_common=False,
        repository_commit="0" * 40,
        receipt_schema="jointbuildgs.c3_dense_seed_test_fixture_receipt.v1",
        receipt_status="COMPLETED_SYNTHETIC_TEST_FIXTURE_NO_EXECUTION_AUTHORITY",
    )
