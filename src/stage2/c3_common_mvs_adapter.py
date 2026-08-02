"""Exact one-read adapter from the frozen 1 m common MVS PLY to GS-local XYZ.

The input classification values are checked only as identity evidence.  Every
input row is retained in source order, its EPSG:25832 XYZ is translated in
float64 by ``-[690953, 5336071, 604]``, and only binary float32 XYZ is
published.  Classification and RGB have no output or loss interface.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import subprocess
import tempfile
from typing import BinaryIO

import numpy as np


REPO = Path(__file__).resolve().parents[2]
EXACT_INPUT_BYTES = 7_327_590
EXACT_INPUT_SHA256 = "c7d63387d720dc4028c2b00e9cc6abb83d41161d6f033199ee619765fdfaf8dd"
EXACT_INPUT_POINTS = 222_044
EXACT_CLASS_COUNTS = ((2, 130_155), (6, 91_889))
GS_LOCAL_SHIFT_XYZ = (690_953.0, 5_336_071.0, 604.0)
EXACT_SFM_SPARSE_POINTS = 371_808
EXACT_FINAL_CONCAT_POINTS = 593_852
RECEIPT_SCHEMA = "jointbuildgs.c3_common_mvs_gs_local_adapter_receipt.v1"


class C3CommonMvsAdapterError(RuntimeError):
    """The exact common-MVS adapter failed closed."""


@dataclass(frozen=True)
class CommonMvsAdapterConfig:
    source_path: Path
    output_path: Path
    receipt_path: Path
    expected_input_bytes: int = EXACT_INPUT_BYTES
    expected_input_sha256: str = EXACT_INPUT_SHA256
    expected_input_points: int = EXACT_INPUT_POINTS
    expected_class_counts: tuple[tuple[int, int], ...] = EXACT_CLASS_COUNTS
    shift_xyz: tuple[float, float, float] = GS_LOCAL_SHIFT_XYZ
    chunk_rows: int = 4096

    def validate(self, *, require_exact_common: bool) -> None:
        if self.expected_input_bytes <= 0 or self.expected_input_points <= 0:
            raise C3CommonMvsAdapterError("expected bytes and points must be positive")
        if re.fullmatch(r"[0-9a-f]{64}", self.expected_input_sha256) is None:
            raise C3CommonMvsAdapterError("expected input SHA-256 must be lowercase hex")
        if self.chunk_rows <= 0:
            raise C3CommonMvsAdapterError("chunk_rows must be positive")
        counts = tuple(self.expected_class_counts)
        if (
            not counts
            or tuple(sorted(counts)) != counts
            or len({class_id for class_id, _ in counts}) != len(counts)
            or any(class_id < 0 or count <= 0 for class_id, count in counts)
            or sum(count for _, count in counts) != self.expected_input_points
        ):
            raise C3CommonMvsAdapterError("expected class counts are invalid")
        if len(self.shift_xyz) != 3 or not all(math.isfinite(value) for value in self.shift_xyz):
            raise C3CommonMvsAdapterError("GS-local shift must contain three finite values")
        source = self.source_path.resolve(strict=False)
        output = self.output_path.resolve(strict=False)
        receipt = self.receipt_path.resolve(strict=False)
        if len({source, output, receipt}) != 3:
            raise C3CommonMvsAdapterError("source, output, and receipt paths must be distinct")
        if self.output_path.suffix.lower() != ".ply":
            raise C3CommonMvsAdapterError("adapter output must use a .ply path")
        if self.receipt_path.suffix.lower() != ".json":
            raise C3CommonMvsAdapterError("adapter receipt must use a .json path")
        if require_exact_common and (
            self.expected_input_bytes != EXACT_INPUT_BYTES
            or self.expected_input_sha256 != EXACT_INPUT_SHA256
            or self.expected_input_points != EXACT_INPUT_POINTS
            or counts != EXACT_CLASS_COUNTS
            or tuple(self.shift_xyz) != GS_LOCAL_SHIFT_XYZ
        ):
            raise C3CommonMvsAdapterError(
                "production adapter requires the exact attested common-MVS identity and shift"
            )


def _open_source(path: Path) -> BinaryIO:
    """Single indirection used to verify one natural input open in tests."""

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


def _ascii_header(point_count: int) -> bytes:
    return (
        "ply\n"
        "format ascii 1.0\n"
        f"element vertex {point_count}\n"
        "property double x\n"
        "property double y\n"
        "property double z\n"
        "property uchar classification\n"
        "end_header\n"
    ).encode("ascii")


def _binary_xyz_header(point_count: int) -> bytes:
    return (
        "ply\n"
        "format binary_little_endian 1.0\n"
        "comment JointBuildGS C3 exact 1m common MVS GS-local adapter v1\n"
        f"element vertex {point_count}\n"
        "property float x\n"
        "property float y\n"
        "property float z\n"
        "end_header\n"
    ).encode("ascii")


def _actual_clean_repository_head() -> str:
    repo = REPO.resolve(strict=True)
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
        raise C3CommonMvsAdapterError("cannot bind adapter to the actual repository HEAD") from error
    head = head_process.stdout.strip()
    if re.fullmatch(r"[0-9a-f]{40}", head) is None:
        raise C3CommonMvsAdapterError("actual repository HEAD is not an exact commit")
    if status_process.stdout:
        raise C3CommonMvsAdapterError("production adapter requires a clean repository worktree")
    return head


def _update_bounds(
    minimum: np.ndarray, maximum: np.ndarray, values: np.ndarray
) -> None:
    minimum[:] = np.minimum(minimum, np.min(values, axis=0))
    maximum[:] = np.maximum(maximum, np.max(values, axis=0))


def _write_xyz_batch(
    output: BinaryIO,
    output_digest: "hashlib._Hash",
    world_rows: list[tuple[float, float, float]],
    shift: np.ndarray,
    input_min: np.ndarray,
    input_max: np.ndarray,
    local64_min: np.ndarray,
    local64_max: np.ndarray,
    serialized_min: np.ndarray,
    serialized_max: np.ndarray,
) -> int:
    if not world_rows:
        return 0
    world = np.asarray(world_rows, dtype=np.float64)
    if world.ndim != 2 or world.shape[1] != 3 or not np.isfinite(world).all():
        raise C3CommonMvsAdapterError("input XYZ must remain finite float64")
    local64 = world - shift
    if not np.isfinite(local64).all():
        raise C3CommonMvsAdapterError("GS-local float64 transform produced non-finite XYZ")
    serialized = np.ascontiguousarray(local64, dtype="<f4")
    if not np.isfinite(serialized).all():
        raise C3CommonMvsAdapterError("GS-local float32 serialization produced non-finite XYZ")
    _update_bounds(input_min, input_max, world)
    _update_bounds(local64_min, local64_max, local64)
    _update_bounds(serialized_min, serialized_max, serialized.astype(np.float64))
    payload = serialized.tobytes(order="C")
    output.write(payload)
    output_digest.update(payload)
    world_rows.clear()
    return len(payload)


def _stream_once_to_output_temp(
    config: CommonMvsAdapterConfig,
) -> tuple[Path, dict[str, object], dict[str, object]]:
    source = config.source_path
    if source.is_symlink() or not source.is_file():
        raise C3CommonMvsAdapterError("input must be a regular non-symlink file")
    before = source.stat()
    if before.st_size != config.expected_input_bytes:
        raise C3CommonMvsAdapterError("input byte identity differs before natural read")

    file_descriptor, raw_temp = tempfile.mkstemp(
        prefix=f".{config.output_path.name}.",
        suffix=".tmp",
        dir=config.output_path.parent,
    )
    output_temp = Path(raw_temp)
    input_digest = hashlib.sha256()
    output_digest = hashlib.sha256()
    total_input_bytes = 0
    total_output_bytes = 0
    input_min = np.full(3, np.inf, dtype=np.float64)
    input_max = np.full(3, -np.inf, dtype=np.float64)
    local64_min = np.full(3, np.inf, dtype=np.float64)
    local64_max = np.full(3, -np.inf, dtype=np.float64)
    serialized_min = np.full(3, np.inf, dtype=np.float64)
    serialized_max = np.full(3, -np.inf, dtype=np.float64)
    class_counts = {class_id: 0 for class_id, _ in config.expected_class_counts}
    shift = np.asarray(config.shift_xyz, dtype=np.float64)
    try:
        with os.fdopen(file_descriptor, "wb") as output, _open_source(source) as input_stream:
            opened = os.fstat(input_stream.fileno())
            before_identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            opened_identity = (
                opened.st_dev,
                opened.st_ino,
                opened.st_size,
                opened.st_mtime_ns,
            )
            if before_identity != opened_identity:
                raise C3CommonMvsAdapterError("input changed between stat and open")

            expected_header = _ascii_header(config.expected_input_points)
            observed_header = bytearray()
            for _ in range(expected_header.count(b"\n")):
                raw = input_stream.readline()
                if not raw:
                    raise C3CommonMvsAdapterError("ASCII PLY header is truncated")
                observed_header.extend(raw)
                input_digest.update(raw)
                total_input_bytes += len(raw)
            if bytes(observed_header) != expected_header:
                raise C3CommonMvsAdapterError("ASCII PLY header differs from the exact schema")

            output_header = _binary_xyz_header(config.expected_input_points)
            output.write(output_header)
            output_digest.update(output_header)
            total_output_bytes += len(output_header)
            world_rows: list[tuple[float, float, float]] = []
            for row_index in range(config.expected_input_points):
                raw = input_stream.readline()
                if not raw:
                    raise C3CommonMvsAdapterError(
                        f"ASCII PLY ended before row {row_index}"
                    )
                input_digest.update(raw)
                total_input_bytes += len(raw)
                try:
                    tokens = raw.decode("ascii").strip().split()
                except UnicodeDecodeError as error:
                    raise C3CommonMvsAdapterError("ASCII PLY row is not ASCII") from error
                if len(tokens) != 4 or re.fullmatch(r"[0-9]+", tokens[3]) is None:
                    raise C3CommonMvsAdapterError("ASCII PLY row must be x y z classification")
                try:
                    xyz = (float(tokens[0]), float(tokens[1]), float(tokens[2]))
                    class_id = int(tokens[3])
                except ValueError as error:
                    raise C3CommonMvsAdapterError("ASCII PLY row contains an invalid number") from error
                if not all(math.isfinite(value) for value in xyz):
                    raise C3CommonMvsAdapterError("ASCII PLY contains non-finite XYZ")
                if class_id not in class_counts:
                    raise C3CommonMvsAdapterError("ASCII PLY contains a class outside exact 2/6 identity")
                class_counts[class_id] += 1
                world_rows.append(xyz)
                if len(world_rows) >= config.chunk_rows:
                    total_output_bytes += _write_xyz_batch(
                        output,
                        output_digest,
                        world_rows,
                        shift,
                        input_min,
                        input_max,
                        local64_min,
                        local64_max,
                        serialized_min,
                        serialized_max,
                    )
            total_output_bytes += _write_xyz_batch(
                output,
                output_digest,
                world_rows,
                shift,
                input_min,
                input_max,
                local64_min,
                local64_max,
                serialized_min,
                serialized_max,
            )
            trailing_bytes = 0
            while True:
                extra = input_stream.read(1 << 20)
                if not extra:
                    break
                input_digest.update(extra)
                total_input_bytes += len(extra)
                trailing_bytes += len(extra)
            closed = os.fstat(input_stream.fileno())
            output.flush()
            os.fsync(output.fileno())

        after = source.stat()
        closed_identity = (closed.st_dev, closed.st_ino, closed.st_size, closed.st_mtime_ns)
        after_identity = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        if len({before_identity, opened_identity, closed_identity, after_identity}) != 1:
            raise C3CommonMvsAdapterError("input identity changed during natural read")
        if trailing_bytes:
            raise C3CommonMvsAdapterError("ASCII PLY has bytes after the exact vertex rows")
        if total_input_bytes != config.expected_input_bytes:
            raise C3CommonMvsAdapterError("natural-read byte count differs from exact identity")
        input_sha256 = input_digest.hexdigest()
        if input_sha256 != config.expected_input_sha256:
            raise C3CommonMvsAdapterError("natural-read SHA-256 differs from exact identity")
        observed_counts = tuple(sorted(class_counts.items()))
        if observed_counts != tuple(config.expected_class_counts):
            raise C3CommonMvsAdapterError("natural-read class counts differ from exact identity")
        expected_output_bytes = len(_binary_xyz_header(config.expected_input_points)) + (
            config.expected_input_points * 12
        )
        if total_output_bytes != expected_output_bytes or output_temp.stat().st_size != expected_output_bytes:
            raise C3CommonMvsAdapterError("binary XYZ output size or row count differs")
        input_record: dict[str, object] = {
            "path": str(source),
            "bytes": total_input_bytes,
            "sha256": input_sha256,
            "format": "ascii_ply_double_xyz_uchar_classification",
            "vertex_count": config.expected_input_points,
            "class_counts": {str(key): value for key, value in observed_counts},
            "bounds_epsg25832_float64": {
                "min_xyz": input_min.tolist(),
                "max_xyz": input_max.tolist(),
            },
            "natural_stream_reads": 1,
            "digest_computed_during_natural_read": True,
            "standalone_rehash_passes": 0,
        }
        output_record: dict[str, object] = {
            "format": "binary_little_endian_ply_xyz_float32",
            "vertex_count": config.expected_input_points,
            "bytes": total_output_bytes,
            "sha256": output_digest.hexdigest(),
            "bounds_gs_local_float64_before_serialization": {
                "min_xyz": local64_min.tolist(),
                "max_xyz": local64_max.tolist(),
            },
            "bounds_gs_local_float32_serialized": {
                "min_xyz": serialized_min.tolist(),
                "max_xyz": serialized_max.tolist(),
            },
            "digest_computed_during_natural_write": True,
            "standalone_rehash_passes": 0,
        }
        return output_temp, input_record, output_record
    except Exception:
        try:
            os.close(file_descriptor)
        except OSError:
            pass
        output_temp.unlink(missing_ok=True)
        raise


def _write_receipt_temp(receipt: dict[str, object], path: Path) -> Path:
    descriptor, raw_temp = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temp = Path(raw_temp)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(_canonical_json_bytes(receipt))
            stream.flush()
            os.fsync(stream.fileno())
        return temp
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        temp.unlink(missing_ok=True)
        raise


def _publish_pair_add_once(
    output_temp: Path,
    output_path: Path,
    receipt_temp: Path,
    receipt_path: Path,
) -> None:
    if output_path.exists() or receipt_path.exists():
        raise C3CommonMvsAdapterError("output or receipt appeared before add-once publication")
    output_linked = False
    try:
        os.link(output_temp, output_path)
        output_linked = True
        os.link(receipt_temp, receipt_path)
    except OSError as error:
        if output_linked:
            output_path.unlink(missing_ok=True)
        raise C3CommonMvsAdapterError(
            "add-once publication failed without overwriting a target"
        ) from error
    finally:
        output_temp.unlink(missing_ok=True)
        receipt_temp.unlink(missing_ok=True)


def _adapt(
    config: CommonMvsAdapterConfig,
    *,
    require_exact_common: bool,
    repository_commit: str,
    receipt_schema: str,
    receipt_status: str,
) -> dict[str, object]:
    config.validate(require_exact_common=require_exact_common)
    if config.output_path.exists() or config.receipt_path.exists():
        raise C3CommonMvsAdapterError("adapter output and receipt are add-once")
    config.output_path.parent.mkdir(parents=True, exist_ok=True)
    config.receipt_path.parent.mkdir(parents=True, exist_ok=True)
    output_temp: Path | None = None
    receipt_temp: Path | None = None
    try:
        output_temp, input_record, output_record = _stream_once_to_output_temp(config)
        if require_exact_common and _actual_clean_repository_head() != repository_commit:
            raise C3CommonMvsAdapterError("repository HEAD changed during the adapter run")
        producer_bytes = Path(__file__).read_bytes()
        output_record["path"] = str(config.output_path)
        output_record["publication"] = "ADD_ONCE_HARDLINK_FROM_SAME_FILESYSTEM_TEMP"
        receipt: dict[str, object] = {
            "schema": receipt_schema,
            "status": receipt_status,
            "repository_commit": repository_commit,
            "repository_worktree_clean_at_start_and_before_publication": (
                True if require_exact_common else None
            ),
            "producer": {
                "path": "src/stage2/c3_common_mvs_adapter.py",
                "sha256": hashlib.sha256(producer_bytes).hexdigest(),
                "python": platform.python_version(),
                "numpy": np.__version__,
            },
            "input": input_record,
            "transform": {
                "input_crs": "EPSG:25832",
                "output_frame": "GS_LOCAL_EQUALS_EPSG25832_MINUS_FIXED_SHIFT",
                "subtract_xyz_float64": list(config.shift_xyz),
                "serialized_dtype": "float32_little_endian",
                "row_order": "EXACT_SOURCE_ORDER_NO_FILTER_NO_DEDUPLICATION",
                "classification_role": "INPUT_IDENTITY_CHECK_ONLY",
                "classification_written_to_output": False,
                "classification_exposed_to_loss": False,
            },
            "output": output_record,
            "training_side_concat_contract": {
                "concatenation_performed_by_adapter": False,
                "order": "ALL_371808_SFM_SPARSE_THEN_ALL_222044_COMMON_MVS_LOCAL",
                "sfm_sparse_points": EXACT_SFM_SPARSE_POINTS,
                "common_mvs_local_points": config.expected_input_points,
                "exact_final_initial_gaussians": (
                    EXACT_SFM_SPARSE_POINTS + config.expected_input_points
                ),
                "production_exact_final_initial_gaussians": EXACT_FINAL_CONCAT_POINTS,
                "mvs_output_has_rgb": False,
                "mvs_rgb_initialization": "SCENE_MEAN_RGB_FALLBACK",
                "classification_used_for_output_or_loss": False,
            },
            "pass_accounting": {
                "input_natural_stream_reads": 1,
                "input_standalone_rehash_passes": 0,
                "output_natural_writes": 1,
                "output_standalone_rehash_passes": 0,
            },
            "performance_runs_started": 0,
            "scientific_verdict": None,
        }
        receipt_temp = _write_receipt_temp(receipt, config.receipt_path)
        _publish_pair_add_once(
            output_temp,
            config.output_path,
            receipt_temp,
            config.receipt_path,
        )
        output_temp = None
        receipt_temp = None
        return receipt
    finally:
        if output_temp is not None:
            output_temp.unlink(missing_ok=True)
        if receipt_temp is not None:
            receipt_temp.unlink(missing_ok=True)


def adapt_common_mvs_to_gs_local(
    config: CommonMvsAdapterConfig,
) -> dict[str, object]:
    """Run the exact production adapter bound to the actual clean Git HEAD."""

    config.validate(require_exact_common=True)
    if config.output_path.exists() or config.receipt_path.exists():
        raise C3CommonMvsAdapterError("adapter output and receipt are add-once")
    repository_commit = _actual_clean_repository_head()
    return _adapt(
        config,
        require_exact_common=True,
        repository_commit=repository_commit,
        receipt_schema=RECEIPT_SCHEMA,
        receipt_status="COMPLETED_EXACT_COMMON_MVS_GS_LOCAL_ADAPTER",
    )


def _adapt_common_mvs_to_gs_local_for_test(
    config: CommonMvsAdapterConfig,
) -> dict[str, object]:
    """Synthetic-only path with no execution authority or production receipt schema."""

    return _adapt(
        config,
        require_exact_common=False,
        repository_commit="0" * 40,
        receipt_schema="jointbuildgs.c3_common_mvs_adapter_test_fixture_receipt.v1",
        receipt_status="COMPLETED_SYNTHETIC_TEST_FIXTURE_NO_EXECUTION_AUTHORITY",
    )
