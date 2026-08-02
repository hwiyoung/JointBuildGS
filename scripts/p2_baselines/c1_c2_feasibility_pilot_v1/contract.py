"""Fail-closed implementation contract for the C1/C2 development pilot.

The module deliberately separates three domains:

* condition geometry is frozen from C1 or C2 evidence without stable IDs;
* development stable IDs are associated only after every component and
  component-derived ``R_derived`` input is add-once frozen;
* Roofer is executed once per unique ``(condition, component_id)`` operation,
  while the 102 score rows may share that operation.

Validation/held-out payload roots, target bboxes, LoD1/LoD2 priors and raw MVS
are not accepted by this API.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import re
import subprocess
import sys
import time
from datetime import date
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

import numpy as np
import laspy
from scipy import ndimage
from jsonschema import Draft202012Validator


REPO = Path(__file__).resolve().parents[3]
CONFIG_PATH = REPO / "configs/p2_baselines/c1_c2_feasibility_pilot_v1/pilot_v1.json"
TASK_ID = "P2-C1-C2-FEASIBILITY-PILOT-RECOVERY-R2-v1"
REPRESENTATIVE_SELECTION_TASK_ID = "P2-C1-C2-FEASIBILITY-PILOT-v1"
ACCEPTED_ATTESTATION_REUSE = {
    "source_handoff_id": "P2-W2C-C1-C2-FEASIBILITY-PILOT-v1",
    "source_task_id": "P2-C1-C2-FEASIBILITY-PILOT-v1",
    "source_receipt_path": "artifacts/manifests/handoffs/P2-W2C-C1-C2-FEASIBILITY-PILOT-v1/300-closed.json",
    "source_receipt_commit": "896fe284bc4d496e6e9c79720f4e75396a41d0b2",
    "source_receipt_sha256": "705348ecde9d139254bdd24e59ed02312d5321c20f802649f1ce4ca19f5b9bda",
    "record_identity_sha256": "f63d5d4405157615d807d6babd4a9bf74a16ab13818193945ed9bbfc02532db3",
}
CONDITIONS = ("C1_L_upper", "C2_MVS")
GRID_NAMES = (
    "min_z", "max_z", "count", "sum_z", "sum_z2",
    "class2_min_z", "class2_count", "class6_max_z", "class6_count",
)


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_ids(values: Iterable[str]) -> str:
    return sha256_bytes("".join(f"{value}\n" for value in sorted(values)).encode("utf-8"))


def _safe_repo_path(relative: str) -> Path:
    path = (REPO / relative).resolve()
    try:
        path.relative_to(REPO.resolve())
    except ValueError as error:
        raise RuntimeError(f"repository path escapes root: {relative}") from error
    return path


def load_config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def canonical_lf_bytes(path: Path) -> bytes:
    """Return the Git-canonical text identity on Windows or Linux."""

    data = path.read_bytes()
    return data.replace(b"\r\n", b"\n")


def read_bound_git_blob(spec: Mapping[str, Any]) -> bytes:
    """Read exact committed bytes and bind both Git blob and content digest."""

    path = str(spec["git_path"])
    blob = subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", f"HEAD:{path}"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    if blob != spec["git_blob"]:
        raise RuntimeError(f"frozen Git blob mismatch: {path}")
    data = subprocess.run(
        ["git", "-C", str(REPO), "show", f"HEAD:{path}"],
        check=True, capture_output=True,
    ).stdout
    if len(data) != int(spec["canonical_bytes"]) or sha256_bytes(data) != spec["canonical_sha256"]:
        raise RuntimeError(f"frozen Git content identity mismatch: {path}")
    return data


def validate_contract(config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Validate Git-owned scope without opening any scientific payload."""

    config = dict(config or load_config())
    if (
        config.get("task_id") != TASK_ID
        or config.get("representative_selection_task_id") != REPRESENTATIVE_SELECTION_TASK_ID
        or config.get("accepted_attestation_reuse") != ACCEPTED_ATTESTATION_REUSE
        or tuple(config["scope"]["condition_ids"]) != CONDITIONS
    ):
        raise RuntimeError("task or condition contract mismatch")
    scope = config["scope"]
    if scope["validation_payload_mount_allowed"] or scope["held_out_payload_mount_allowed"]:
        raise RuntimeError("validation/held-out payload mounts must remain prohibited")
    if scope["c3_c5_allowed"]:
        raise RuntimeError("C3-C5 must remain prohibited")
    roster_path = _safe_repo_path(scope["roster_path"])
    roster_bytes = roster_path.read_bytes()
    if len(roster_bytes) != int(scope["roster_bytes"]) or sha256_bytes(roster_bytes) != scope["roster_sha256"]:
        raise RuntimeError("development roster file identity mismatch")
    roster = list(csv.DictReader(io.StringIO(roster_bytes.decode("utf-8"), newline="")))
    if list(roster[0]) != ["stable_id", "group_id", "split"]:
        raise RuntimeError("roster columns differ from exact development-only schema")
    ids = [row["stable_id"] for row in roster]
    if len(ids) != 51 or len(set(ids)) != 51 or set(row["split"] for row in roster) != {"development"}:
        raise RuntimeError("roster must contain exactly 51 unique development IDs")
    if sha256_ids(ids) != scope["development_id_set_sha256"]:
        raise RuntimeError("development ID set digest mismatch")
    groups = Counter(row["group_id"] for row in roster)
    if dict(groups) != scope["group_sizes"]:
        raise RuntimeError(f"development group sizes mismatch: {dict(groups)}")
    scope_path = _safe_repo_path(scope["development_score_scope_path"])
    scope_bytes = canonical_lf_bytes(scope_path)
    if len(scope_bytes) != int(scope["development_score_scope_canonical_lf_bytes"]) or sha256_bytes(scope_bytes) != scope["development_score_scope_canonical_lf_sha256"]:
        raise RuntimeError("development score-scope file identity mismatch")
    score_scope = list(csv.DictReader(io.StringIO(scope_bytes.decode("utf-8"), newline="")))
    required_scope = ["stable_id", "group_id", "bbox_min_x", "bbox_min_y", "bbox_max_x", "bbox_max_y", "reference_patch_ids", "expected_score_cells"]
    if not score_scope or list(score_scope[0]) != required_scope:
        raise RuntimeError("development score scope schema mismatch")
    scope_ids = [row["stable_id"] for row in score_scope]
    if len(scope_ids) != 51 or set(scope_ids) != set(ids):
        raise RuntimeError("score-scope IDs differ from exact development roster")
    patch_pattern = re.compile(r"^UASPATCH_[0-9a-f]{20}$")
    expected_total = 0
    group_by_id = {row["stable_id"]: row["group_id"] for row in roster}
    for row in score_scope:
        if row["group_id"] != group_by_id[row["stable_id"]]:
            raise RuntimeError(f"score-scope group mismatch: {row['stable_id']}")
        patches = row["reference_patch_ids"].split(";")
        if not patches or any(not patch_pattern.fullmatch(value) for value in patches):
            raise RuntimeError(f"invalid frozen patch association: {row['stable_id']}")
        bounds = [float(row[name]) for name in ("bbox_min_x", "bbox_min_y", "bbox_max_x", "bbox_max_y")]
        if not all(math.isfinite(value) for value in bounds) or bounds[0] > bounds[2] or bounds[1] > bounds[3]:
            raise RuntimeError(f"invalid frozen score bbox: {row['stable_id']}")
        expected = int(row["expected_score_cells"])
        if expected <= 0:
            raise RuntimeError(f"invalid expected score-cell count: {row['stable_id']}")
        expected_total += expected
    if expected_total != int(scope["development_score_cell_rows"]):
        raise RuntimeError("development score-cell denominator is not exact 21,714")

    eligibility_bytes = read_bound_git_blob(config["frozen_lineage"]["eligibility"])
    split_bytes = read_bound_git_blob(config["frozen_lineage"]["split"])
    eligibility = {row["stable_id"]: row for row in csv.DictReader(io.StringIO(eligibility_bytes.decode("utf-8"), newline=""))}
    development = [row for row in csv.DictReader(io.StringIO(split_bytes.decode("utf-8"), newline="")) if row["split"] == "development"]
    if len(development) != 51 or sha256_ids(row["stable_id"] for row in development) != scope["development_id_set_sha256"]:
        raise RuntimeError("original frozen development split binding mismatch")
    development_by_id = {row["stable_id"]: row for row in development}
    for row in score_scope:
        source = eligibility.get(row["stable_id"])
        split = development_by_id.get(row["stable_id"])
        if source is None or split is None or split["group_id"] != row["group_id"]:
            raise RuntimeError(f"score scope is not derived from frozen split: {row['stable_id']}")
        exact = {
            "bbox_min_x": source["bbox_min_x"], "bbox_min_y": source["bbox_min_y"],
            "bbox_max_x": source["bbox_max_x"], "bbox_max_y": source["bbox_max_y"],
            "reference_patch_ids": source["reference_candidate_patch_ids"],
            "expected_score_cells": source["reference_candidate_score_cells"],
        }
        if any(row[key] != value for key, value in exact.items()):
            raise RuntimeError(f"score scope differs from frozen eligibility: {row['stable_id']}")
    if config["association"]["timing"] != "AFTER_CONDITION_COMPONENTS_AND_ALL_R_DERIVED_JOB_INPUTS_ARE_ADD_ONCE_FROZEN":
        raise RuntimeError("stable-ID association timing is not leakage-safe")
    if config["association"]["geometry_modification_allowed"] or config["association"]["crop_allowed"] or config["association"]["registration_allowed"]:
        raise RuntimeError("score association may not modify/crop/register condition geometry")
    if config["c1_materialization"].get("r1_reference_cells_used") is not False:
        raise RuntimeError("C1 condition geometry must use generic grid cells, never R1 score cells")
    if config["c1_materialization"].get("source_classification_fields_usable") is not False:
        raise RuntimeError("raw source classifications are all zero; class-specific grid fields are prohibited")
    if config["condition_geometry"].get("stable_id_used") or config["condition_geometry"].get("target_bbox_used"):
        raise RuntimeError("condition components must be stable-ID/bbox blind")
    if config["stage3"]["required_lod"] != "2.2" or config["stage3"]["lod11_fallback_allowed"]:
        raise RuntimeError("strict LoD2.2/no-fallback contract mismatch")
    execution = config["stage3"]["execution"]
    if any(execution.get(key) != value for key, value in {
        "serial_jobs": 1, "cpus_per_attempt": 2, "memory_bytes_per_attempt": 8000000000,
        "gpus_per_attempt": 0, "timeout_seconds_per_attempt": 600,
    }.items()):
        raise RuntimeError("per-attempt resource contract mismatch")
    peak = execution.get("peak_memory_capture") or {}
    if peak.get("status") != "UNAVAILABLE" or peak.get("reason") != "ROOFER_IMAGE_GNU_TIME_UNAVAILABLE_VERIFIED_IMMUTABLE_IMAGE":
        raise RuntimeError("peak-memory accounting contract mismatch")
    if config["retries"]["max_retry_attempts_per_execution_unit"] != 1 or config["retries"]["max_total_retry_attempts"] != 5:
        raise RuntimeError("retry caps differ from the bounded pilot contract")
    if config["caps"]["wall_clock_seconds_hard"] != 43200 or config["caps"]["new_output_bytes_hard"] != 100_000_000_000:
        raise RuntimeError("hard 12h/100GB caps differ from contract")
    representatives = representative_cases(roster)
    return {
        "status": "PASS_ZERO_SCIENTIFIC_PAYLOAD",
        "building_count": len(roster),
        "group_sizes": dict(sorted(groups.items())),
        "development_id_set_sha256": sha256_ids(ids),
        "representatives": representatives,
        "development_score_cell_rows": expected_total,
        "frozen_eligibility_blob": config["frozen_lineage"]["eligibility"]["git_blob"],
        "frozen_split_blob": config["frozen_lineage"]["split"]["git_blob"],
        "scientific_payload_bytes_read_or_hashed": 0,
        "scientific_verdict": None,
    }


def representative_cases(roster: Sequence[Mapping[str, str]]) -> dict[str, str]:
    grouped: defaultdict[str, list[str]] = defaultdict(list)
    for row in roster:
        grouped[row["group_id"]].append(row["stable_id"])
    return {
        group: min(
            ids,
            key=lambda stable_id: hashlib.sha256(
                f"{REPRESENTATIVE_SELECTION_TASK_ID}|{group}|{stable_id}".encode()
            ).hexdigest(),
        )
        for group, ids in sorted(grouped.items())
    }


class AddOnceStore:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, relative: str) -> Path:
        target = (self.root / relative).resolve()
        try:
            target.relative_to(self.root)
        except ValueError as error:
            raise RuntimeError(f"output escapes task namespace: {relative}") from error
        return target

    def add(self, relative: str, data: bytes) -> dict[str, Any]:
        target = self.path(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise RuntimeError(f"add-once output already exists without completed checkpoint: {relative}")
        pending = target.with_name(f".{target.name}.pending")
        if pending.exists():
            raise RuntimeError(f"partial add-once output requires quarantine: {pending}")
        descriptor = os.open(pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o640)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.link(pending, target)
            pending.unlink()
            directory_fd = os.open(target.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except Exception:
            raise
        return {"path": relative, "bytes": len(data), "sha256": sha256_bytes(data)}

    def add_json(self, relative: str, value: Any) -> dict[str, Any]:
        return self.add(relative, canonical_json_bytes(value))

    def read_verified(self, record: Mapping[str, Any]) -> bytes:
        path = self.path(str(record["path"]))
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"record output missing/non-regular: {path}")
        data = path.read_bytes()
        if len(data) != int(record["bytes"]) or sha256_bytes(data) != record["sha256"]:
            raise RuntimeError(f"record output digest mismatch: {path}")
        return data


def capture_exact_once(path: Path, *, expected_bytes: int | None, expected_sha256: str | None) -> tuple[bytes, dict[str, Any]]:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"scientific input is not a regular file: {path}")
    digest = hashlib.sha256()
    chunks: list[bytes] = []
    total = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            chunks.append(chunk)
            total += len(chunk)
    observed = {"path": path.as_posix(), "bytes": total, "sha256": digest.hexdigest(), "full_read_and_digest_passes": 1}
    if expected_bytes is not None and total != expected_bytes:
        raise RuntimeError(f"input byte mismatch: {path}")
    if expected_sha256 is not None and observed["sha256"] != expected_sha256:
        raise RuntimeError(f"input digest mismatch: {path}")
    return b"".join(chunks), observed


def resolve_checkpoint_record(
    checkpoint_path: Path,
    record_key: str,
    expected_relative: str,
    *,
    expected_checkpoint_bytes: int,
    expected_checkpoint_sha256: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    checkpoint_bytes, checkpoint_input = capture_exact_once(
        checkpoint_path,
        expected_bytes=expected_checkpoint_bytes,
        expected_sha256=expected_checkpoint_sha256,
    )
    body = json.loads(checkpoint_bytes)
    value: Any = body
    for key in record_key.split("."):
        if not isinstance(value, Mapping) or key not in value:
            raise RuntimeError(f"attestation key missing: {record_key}")
        value = value[key]
    if not isinstance(value, Mapping) or not {"path", "bytes", "sha256"}.issubset(value):
        raise RuntimeError("attestation record is incomplete")
    observed_path = str(value["path"]).replace("\\", "/")
    if not observed_path.endswith(expected_relative):
        raise RuntimeError("attestation record points to a different derivative")
    return {"bytes": int(value["bytes"]), "sha256": str(value["sha256"]), "path": observed_path}, checkpoint_input


def resolve_c1_grid_checkpoint(checkpoint_path: Path, spec: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Bind the generic grid and prove the raw source did not carry classes 2/6."""

    checkpoint_bytes, checkpoint_input = capture_exact_once(
        checkpoint_path,
        expected_bytes=int(spec["attestation_checkpoint_bytes"]),
        expected_sha256=str(spec["attestation_checkpoint_sha256"]),
    )
    body = json.loads(checkpoint_bytes)
    if body.get("stage") != "c1_reference_frozen_pre_c5" or body.get("status") != "COMPLETED_FSYNC":
        raise RuntimeError("C1 checkpoint stage/status mismatch")
    payload = body.get("payload") or {}
    grid = payload.get("grid") or {}
    observed_path = str(grid.get("path", "")).replace("\\", "/")
    if not observed_path.endswith(str(spec["artifact_relative_path"])):
        raise RuntimeError("C1 checkpoint points to a different grid")
    record = {"path": observed_path, "bytes": int(grid.get("bytes", -1)), "sha256": str(grid.get("sha256", ""))}
    if record["bytes"] != int(spec["bytes"]) or record["sha256"] != spec["sha256"]:
        raise RuntimeError("C1 grid identity differs from exact 050 checkpoint")
    source = payload.get("input") or {}
    normalized_counts = {str(key): int(value) for key, value in (source.get("raw_class_counts") or {}).items()}
    if int(source.get("point_count", -1)) != int(spec["raw_point_count"]) or normalized_counts != dict(spec["raw_class_counts"]):
        raise RuntimeError("C1 raw point/class-count attestation mismatch")
    return record, checkpoint_input


@dataclass(frozen=True)
class Point:
    x: float
    y: float
    z: float
    classification: int
    ix: int
    iy: int


def _grid_index(x: float, y: float, config: Mapping[str, Any]) -> tuple[int, int]:
    x0, y0 = config["frame"]["aoi_bbox"][:2]
    cell = float(config["frame"]["grid_cell_m"])
    return int(math.floor((x - x0) / cell + 1e-9)), int(math.floor((y - y0) / cell + 1e-9))


def load_c1_grid(data: bytes, config: Mapping[str, Any]) -> tuple[list[Point], dict[str, Any]]:
    bbox = tuple(float(value) for value in config["frame"]["aoi_bbox"])
    cell = float(config["frame"]["grid_cell_m"])
    nx = int(math.ceil((bbox[2] - bbox[0]) / cell))
    ny = int(math.ceil((bbox[3] - bbox[1]) / cell))
    arrays: dict[str, np.ndarray] = {}
    with np.load(io.BytesIO(data), allow_pickle=False) as source:
        if set(source.files) != set(GRID_NAMES):
            raise RuntimeError("C1 grid NPZ allowlist mismatch")
        for name in GRID_NAMES:
            value = np.asarray(source[name])
            if value.dtype.hasobject or value.shape != (nx * ny,):
                raise RuntimeError(f"C1 grid member shape/type mismatch: {name}")
            if name in {"min_z", "max_z", "count"}:
                arrays[name] = value
    points: list[Point] = []
    lower = arrays["min_z"].reshape(ny, nx)
    observed = (arrays["count"].reshape(ny, nx) > 0) & np.isfinite(lower)
    if not np.any(observed):
        raise RuntimeError("C1 grid has no generic observed terrain cells")
    nearest = ndimage.distance_transform_edt(~observed, return_distances=False, return_indices=True)
    filled = lower[tuple(nearest)]
    windows = config["c1_materialization"]["terrain_filter_windows_cells"]
    terrain = np.minimum.reduce([ndimage.grey_opening(filled, size=(int(size), int(size)), mode="nearest") for size in windows])
    ground = observed.ravel()
    building = (
        (arrays["count"] >= int(config["c1_materialization"]["minimum_points_per_cell"]))
        & np.isfinite(arrays["max_z"])
        & ((arrays["max_z"] - terrain.ravel()) >= float(config["c1_materialization"]["minimum_height_above_terrain_m"]))
    )
    for classification, mask, heights in ((2, ground, arrays["min_z"]), (6, building, arrays["max_z"])):
        for flat in np.flatnonzero(mask):
            iy, ix = divmod(int(flat), nx)
            points.append(Point(bbox[0] + (ix + 0.5) * cell, bbox[1] + (iy + 0.5) * cell, float(heights[flat]), classification, ix, iy))
    return points, {
        "method": "ALL_FROZEN_C1_GRID_GENERIC_MIN_MAX_COUNT_TO_ROOFER_CLASS26_V1",
        "ground_points": int(np.count_nonzero(ground)),
        "building_points": int(np.count_nonzero(building)),
        "minimum_points_per_cell": int(config["c1_materialization"]["minimum_points_per_cell"]),
        "minimum_height_above_terrain_m": float(config["c1_materialization"]["minimum_height_above_terrain_m"]),
        "terrain_filter_windows_cells": list(windows),
        "source_fields": ["min_z", "max_z", "count"],
        "class_specific_fields_used": False,
        "source_raw_class_counts": dict(config["c1_materialization"]["source_raw_class_counts"]),
        "r1_reference_cells_used": False,
    }


def parse_ascii_class26_ply(data: bytes, config: Mapping[str, Any]) -> tuple[list[Point], dict[str, Any]]:
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError as error:
        raise RuntimeError("class26 PLY must be the frozen ASCII derivative") from error
    lines = text.splitlines()
    if len(lines) < 8 or lines[0] != "ply" or "format ascii 1.0" not in lines[:3]:
        raise RuntimeError("unsupported PLY header")
    try:
        end = lines.index("end_header")
    except ValueError as error:
        raise RuntimeError("PLY end_header missing") from error
    vertex_lines = [line for line in lines[:end] if line.startswith("element vertex ")]
    if len(vertex_lines) != 1:
        raise RuntimeError("PLY vertex count declaration missing/ambiguous")
    expected = int(vertex_lines[0].split()[-1])
    points: list[Point] = []
    for line in lines[end + 1:]:
        if not line.strip():
            continue
        fields = line.split()
        if len(fields) != 4:
            raise RuntimeError("class26 PLY row must be x y z classification")
        x, y, z = (float(value) for value in fields[:3])
        classification = int(fields[3])
        if classification not in (2, 6) or not all(math.isfinite(value) for value in (x, y, z)):
            raise RuntimeError("class26 PLY contains invalid value/class")
        ix, iy = _grid_index(x, y, config)
        points.append(Point(x, y, z, classification, ix, iy))
    if len(points) != expected:
        raise RuntimeError("PLY vertex count mismatch")
    return points, {"ground_points": sum(p.classification == 2 for p in points), "building_points": sum(p.classification == 6 for p in points)}


def ply_bytes(points: Sequence[Point]) -> bytes:
    header = (
        "ply\nformat ascii 1.0\n"
        f"element vertex {len(points)}\n"
        "property double x\nproperty double y\nproperty double z\n"
        "property uchar classification\nend_header\n"
    )
    body = "".join(f"{point.x:.3f} {point.y:.3f} {point.z:.6f} {point.classification}\n" for point in points)
    return (header + body).encode("ascii")


def las_bytes(points: Sequence[Point], config: Mapping[str, Any]) -> bytes:
    """Serialize deterministic uncompressed LAS accepted by Roofer.

    The offset depends only on the condition points and never on a target ID,
    bbox, UAS score reference or output.
    """

    if not points:
        raise RuntimeError("cannot serialize an empty Roofer point cloud")
    rule = config["roofer_pointcloud"]
    if rule["format"] != "LAS_1_2_POINT_FORMAT_3_UNCOMPRESSED":
        raise RuntimeError("Roofer point-cloud format contract mismatch")
    header = laspy.LasHeader(point_format=3, version="1.2")
    header.scales = np.asarray(rule["coordinate_scale_m"], dtype=np.float64)
    minima = [min(getattr(point, axis) for point in points) for axis in ("x", "y", "z")]
    header.offsets = np.asarray([math.floor(value / 1000.0) * 1000.0 for value in minima], dtype=np.float64)
    header.creation_date = date.fromisoformat(rule["creation_date"])
    header.system_identifier = rule["system_identifier"]
    header.generating_software = rule["generating_software"]
    cloud = laspy.LasData(header)
    cloud.x = np.asarray([point.x for point in points], dtype=np.float64)
    cloud.y = np.asarray([point.y for point in points], dtype=np.float64)
    cloud.z = np.asarray([point.z for point in points], dtype=np.float64)
    cloud.classification = np.asarray([point.classification for point in points], dtype=np.uint8)
    output = io.BytesIO()
    cloud.write(output, do_compress=False)
    return output.getvalue()


def convex_hull_xy(points: Sequence[Point]) -> list[tuple[float, float]]:
    values = sorted(set((point.x, point.y) for point in points))
    if len(values) < 3:
        return []

    def cross(origin: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
        return (a[0] - origin[0]) * (b[1] - origin[1]) - (a[1] - origin[1]) * (b[0] - origin[0])

    lower: list[tuple[float, float]] = []
    for value in values:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], value) <= 0:
            lower.pop()
        lower.append(value)
    upper: list[tuple[float, float]] = []
    for value in reversed(values):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], value) <= 0:
            upper.pop()
        upper.append(value)
    hull = lower[:-1] + upper[:-1]
    return hull + [hull[0]] if len(hull) >= 3 else []


def derive_components(condition: str, points: Sequence[Point], config: Mapping[str, Any]) -> tuple[list[dict[str, Any]], dict[tuple[int, int], str]]:
    by_cell: dict[tuple[int, int], Point] = {}
    for point in points:
        if point.classification == 6:
            key = (point.ix, point.iy)
            current = by_cell.get(key)
            if current is None or point.z > current.z:
                by_cell[key] = point
    remaining = set(by_cell)
    offsets = [(dx, dy) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dx or dy]
    minimum = int(config["condition_geometry"]["minimum_component_points"])
    components: list[dict[str, Any]] = []
    cell_to_component: dict[tuple[int, int], str] = {}
    while remaining:
        start = min(remaining)
        remaining.remove(start)
        queue = deque([start])
        cells: list[tuple[int, int]] = []
        while queue:
            key = queue.popleft()
            cells.append(key)
            for dx, dy in offsets:
                adjacent = (key[0] + dx, key[1] + dy)
                if adjacent in remaining:
                    remaining.remove(adjacent)
                    queue.append(adjacent)
        if len(cells) < minimum:
            continue
        member_points = [by_cell[key] for key in sorted(cells)]
        identity_bytes = "".join(f"{p.ix},{p.iy},{p.z:.6f}\n" for p in member_points).encode()
        component_id = f"{condition}_COMP_{sha256_bytes(condition.encode() + b'|' + identity_bytes)[:20]}"
        hull = convex_hull_xy(member_points)
        tile_size = float(config["condition_geometry"]["fixed_tile_size_m"])
        anchor_x, anchor_y = (float(v) for v in config["condition_geometry"]["fixed_tile_anchor"])
        touched_tiles = sorted({(math.floor((p.x - anchor_x) / tile_size), math.floor((p.y - anchor_y) / tile_size)) for p in member_points})
        record = {
            "condition_id": condition,
            "component_id": component_id,
            "point_count": len(member_points),
            "cells": [[x, y] for x, y in sorted(cells)],
            "touched_tiles": [[int(x), int(y)] for x, y in touched_tiles],
            "polygon": [[round(x, 6), round(y, 6)] for x, y in hull],
            "pre_roofer_failure": None if hull else "NON_POLYGON_CONDITION_COMPONENT",
        }
        components.append(record)
        for key in cells:
            cell_to_component[key] = component_id
    components.sort(key=lambda value: value["component_id"])
    return components, cell_to_component


def component_job(condition: str, component: Mapping[str, Any], points: Sequence[Point], config: Mapping[str, Any]) -> tuple[bytes, bytes]:
    component_cells = {tuple(value) for value in component["cells"]}
    touched_tiles = {tuple(value) for value in component["touched_tiles"]}
    tile_size = float(config["condition_geometry"]["fixed_tile_size_m"])
    anchor_x, anchor_y = (float(v) for v in config["condition_geometry"]["fixed_tile_anchor"])
    selected: list[Point] = []
    for point in points:
        if point.classification == 6 and (point.ix, point.iy) in component_cells:
            selected.append(point)
        elif point.classification == 2:
            tile = (math.floor((point.x - anchor_x) / tile_size), math.floor((point.y - anchor_y) / tile_size))
            if tile in touched_tiles:
                selected.append(point)
    selected.sort(key=lambda p: (p.classification, p.iy, p.ix, p.z))
    polygon = component["polygon"]
    geojson = {
        "type": "FeatureCollection",
        "name": "R_DERIVED_NON_GT_CONVEX_HULL_V1",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::25832"}},
        "features": [{
            "type": "Feature",
            "properties": {"component_id": component["component_id"], "condition_id": condition, "source": "condition_class6_component_only"},
            "geometry": {"type": "Polygon", "coordinates": [polygon]},
        }],
    }
    return las_bytes(selected, config), canonical_json_bytes(geojson)


def project_development_score_cells(
    path: Path,
    spec: Mapping[str, Any],
    score_scope: Sequence[Mapping[str, str]],
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    """One-pass exact projection of global R1 cells to the 51 development units.

    Patch membership reduces transient retention; the inclusive frozen building
    bbox creates the exact building-cell identities used by the original R1
    eligibility mapping. Geometry has already been frozen before this function
    is called, so these bboxes can only affect score association.
    """

    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"scientific input is not a regular file: {path}")
    scopes_by_patch: defaultdict[str, list[Mapping[str, str]]] = defaultdict(list)
    for item in score_scope:
        for patch_id in item["reference_patch_ids"].split(";"):
            scopes_by_patch[patch_id].append(item)
    digest = hashlib.sha256()
    total_bytes = 0
    total_rows = 0
    retained_source_cells: set[tuple[str, str]] = set()
    projected: list[dict[str, str]] = []
    header: list[str] | None = None
    with path.open("rb") as handle:
        for raw_line in handle:
            digest.update(raw_line)
            total_bytes += len(raw_line)
            parsed = next(csv.reader([raw_line.decode("utf-8")]))
            if header is None:
                header = parsed
                required = {"patch_id", "flat_index", "cell_ix", "cell_iy", "cell_x", "cell_y", "top_z", "normal_x", "normal_y", "normal_z"}
                if not required.issubset(header):
                    raise RuntimeError("frozen reference cell table schema mismatch")
                continue
            if len(parsed) != len(header):
                raise RuntimeError("frozen reference cell row width mismatch")
            total_rows += 1
            row = dict(zip(header, parsed))
            candidate_scopes = scopes_by_patch.get(row["patch_id"], ())
            if not candidate_scopes:
                continue
            x, y = float(row["cell_x"]), float(row["cell_y"])
            source_identity = (row["patch_id"], row["flat_index"])
            retained_here = False
            for scope in candidate_scopes:
                if (
                    float(scope["bbox_min_x"]) <= x <= float(scope["bbox_max_x"])
                    and float(scope["bbox_min_y"]) <= y <= float(scope["bbox_max_y"])
                ):
                    projected.append({"stable_id": scope["stable_id"], "group_id": scope["group_id"], **row})
                    retained_here = True
            if retained_here:
                retained_source_cells.add(source_identity)
    observed_sha = digest.hexdigest()
    if total_bytes != int(spec["bytes"]) or observed_sha != spec["sha256"] or total_rows != int(spec["expected_rows"]):
        raise RuntimeError("global reference-cell identity/count mismatch")
    expected = {item["stable_id"]: int(item["expected_score_cells"]) for item in score_scope}
    actual = Counter(item["stable_id"] for item in projected)
    if dict(actual) != expected or len(projected) != sum(expected.values()):
        raise RuntimeError(f"development score-cell projection mismatch: expected={expected}, actual={dict(actual)}")
    identities = [(item["stable_id"], item["patch_id"], item["flat_index"]) for item in projected]
    if len(identities) != len(set(identities)):
        raise RuntimeError("development score-cell identity duplicated")
    return projected, {
        "path": path.as_posix(), "bytes": total_bytes, "sha256": observed_sha,
        "global_rows_streamed": total_rows, "full_read_and_digest_passes": 1,
        "development_building_cell_rows_retained": len(projected),
        "development_unique_source_cells_retained": len(retained_source_cells),
        "non_development_rows_retained_scored_or_promoted": 0,
    }


def associate_development(
    roster: Sequence[Mapping[str, str]],
    reference_rows: Sequence[Mapping[str, str]],
    component_maps: Mapping[str, Mapping[tuple[int, int], str]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_stable_id: defaultdict[str, list[Mapping[str, str]]] = defaultdict(list)
    for row in reference_rows:
        by_stable_id[row["stable_id"]].append(row)
    group_by_id = {row["stable_id"]: row["group_id"] for row in roster}
    mappings: list[dict[str, Any]] = []
    score_cells: list[dict[str, Any]] = []
    for stable_id in sorted(group_by_id):
        selected_reference = sorted(
            by_stable_id.get(stable_id, []),
            key=lambda row: (row["patch_id"], int(row["flat_index"])),
        )
        if not selected_reference:
            raise RuntimeError(f"development stable ID has no frozen reference score cells: {stable_id}")
        for row in selected_reference:
            score_cells.append(dict(row))
        for condition in CONDITIONS:
            counts: Counter[str] = Counter()
            component_map = component_maps[condition]
            for row in selected_reference:
                component_id = component_map.get((int(row["cell_ix"]), int(row["cell_iy"])))
                if component_id:
                    counts[component_id] += 1
            component_id = min(((-count, name) for name, count in counts.items()), default=(0, None))[1]
            overlap = counts.get(component_id, 0) if component_id else 0
            mappings.append({
                "building_id": stable_id,
                "group_id": group_by_id[stable_id],
                "split": "development",
                "method_id": condition,
                "component_id": component_id,
                "operation_unit_id": f"{condition}|{component_id}" if component_id else None,
                "reference_cell_count": len(selected_reference),
                "component_overlap_reference_cells": overlap,
                "association_role": "SCORE_IDENTITY_ONLY_AFTER_FROZEN_CONDITION_GEOMETRY",
            })
    if len(mappings) != 102:
        raise RuntimeError("association did not produce exact 51x2 result rows")
    return mappings, score_cells


def jsonl_bytes(rows: Sequence[Mapping[str, Any]]) -> bytes:
    return b"".join(canonical_json_bytes(row) for row in rows)


def parse_jsonl(data: bytes) -> list[dict[str, Any]]:
    return [json.loads(line) for line in data.decode("utf-8").splitlines() if line.strip()]


def output_tree_bytes(root: Path) -> int:
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file() and not path.is_symlink())


def compact_file_record(store: AddOnceStore, path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"required runtime record is missing/non-regular: {path}")
    try:
        relative = path.resolve().relative_to(store.root).as_posix()
    except ValueError as error:
        raise RuntimeError("runtime record escapes task namespace") from error
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            total += len(chunk)
    return {"path": relative, "bytes": total, "sha256": digest.hexdigest(), "full_hash_passes": 1}


def prepare_synthetic(store: AddOnceStore) -> dict[str, Any]:
    completed = store.path("control/synthetic_inputs_v1.json")
    if completed.is_file():
        return json.loads(completed.read_bytes())
    points: list[Point] = []
    features = []
    labels = ("C1_L_upper", "C2_MVS", "C3_GS_image", "C4_GS_lidar_prior", "C5_GS_lod1_prior")
    for index, label in enumerate(labels):
        x0 = float(index * 20)
        polygon = [[x0 + 1, 1], [x0 + 9, 1], [x0 + 9, 9], [x0 + 1, 9], [x0 + 1, 1]]
        for x, y in polygon[:-1]:
            points.append(Point(x, y, 5.0, 6, int(x), int(y)))
        for x, y in ((x0, 0), (x0 + 10, 0), (x0 + 10, 10), (x0, 10)):
            points.append(Point(x, y, 0.0, 2, int(x), int(y)))
        features.append({"type": "Feature", "properties": {"component_id": f"synthetic-{label}"}, "geometry": {"type": "Polygon", "coordinates": [polygon]}})
    input_record = store.add("smoke/work/input.las", las_bytes(points, load_config()))
    roofprint_record = store.add_json("smoke/work/r_derived.geojson", {"type": "FeatureCollection", "features": features})
    body = {
        "schema": "jointbuildgs.p2_c1_c2_synthetic_inputs.v1",
        "status": "READY_ZERO_SCIENTIFIC_PAYLOAD",
        "condition_labels": list(labels),
        "input": input_record,
        "r_derived": roofprint_record,
        "scientific_payload_bytes_read_or_hashed": 0,
        "scientific_verdict": None,
    }
    store.add_json("control/synthetic_inputs_v1.json", body)
    return body


def _cityjson_records(output_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(output_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in (".json", ".jsonl", ".cityjson", ".city.json"):
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(json.loads(line))
    return records


def _validate_semantic_shape(values: Any, boundaries: Any, levels: int, definitions: Sequence[Any]) -> tuple[bool, list[int]]:
    if not isinstance(values, list) or not isinstance(boundaries, list) or len(values) != len(boundaries):
        return False, []
    if levels == 1:
        indices: list[int] = []
        for value in values:
            if value is None:
                continue
            if not isinstance(value, int) or value < 0 or value >= len(definitions):
                return False, []
            indices.append(value)
        return True, indices
    indices: list[int] = []
    for child_values, child_boundaries in zip(values, boundaries):
        ok, child_indices = _validate_semantic_shape(child_values, child_boundaries, levels - 1, definitions)
        if not ok:
            return False, []
        indices.extend(child_indices)
    return True, indices


def _validate_boundary_indices(boundaries: Any, depth: int, vertex_count: int) -> tuple[bool, list[list[int]]]:
    if depth == 1:
        if not isinstance(boundaries, list) or len(boundaries) < 3 or any(not isinstance(value, int) or value < 0 or value >= vertex_count for value in boundaries):
            return False, []
        return True, [boundaries]
    if not isinstance(boundaries, list) or not boundaries:
        return False, []
    rings: list[list[int]] = []
    for child in boundaries:
        ok, child_rings = _validate_boundary_indices(child, depth - 1, vertex_count)
        if not ok:
            return False, []
        rings.extend(child_rings)
    return True, rings


def provisional_output_check(output_dir: Path, *, expected_features_min: int = 1) -> dict[str, Any]:
    """Internal CityJSON structure screen plus a non-G2 ring diagnostic."""

    records = _cityjson_records(output_dir)
    object_count = 0
    lod22 = 0
    surfaces: Counter[str] = Counter()
    finite_vertices = True
    g1_failures: set[str] = set()
    all_rings: list[list[int]] = []
    for record in records:
        vertices = record.get("vertices", [])
        record_vertices_ok = isinstance(vertices, list) and all(
            isinstance(vertex, list) and len(vertex) >= 3 and all(isinstance(v, (int, float)) and math.isfinite(v) for v in vertex[:3])
            for vertex in vertices
        )
        finite_vertices &= record_vertices_ok
        if not record_vertices_ok:
            g1_failures.add("INVALID_VERTEX_SHAPE_OR_VALUE")
        city_objects = record.get("CityObjects") or {}
        if not isinstance(city_objects, Mapping):
            g1_failures.add("CITYOBJECTS_NOT_MAPPING")
            city_objects = {}
        for object_id, city_object in city_objects.items():
            if not isinstance(object_id, str) or not isinstance(city_object, Mapping):
                g1_failures.add("INVALID_CITYOBJECT_ENTRY")
                continue
            object_count += 1
            for relation, inverse in (("children", "parents"), ("parents", "children")):
                refs = city_object.get(relation, [])
                if refs is None:
                    refs = []
                if not isinstance(refs, list) or len(refs) != len(set(refs)) or any(not isinstance(ref, str) or ref not in city_objects for ref in refs):
                    g1_failures.add(f"INVALID_{relation.upper()}_REFERENCES")
                    continue
                for ref in refs:
                    inverse_refs = city_objects[ref].get(inverse, []) if isinstance(city_objects[ref], Mapping) else []
                    if not isinstance(inverse_refs, list) or object_id not in inverse_refs:
                        g1_failures.add("ASYMMETRIC_PARENT_CHILD_RELATION")
            for geometry in city_object.get("geometry", []):
                if str(geometry.get("lod")) == "2.2":
                    lod22 += 1
                elif str(geometry.get("lod")) == "1.1":
                    raise RuntimeError("LoD1.1 fallback is prohibited")
                geometry_type = geometry.get("type")
                depth_by_type = {"MultiSurface": 3, "CompositeSurface": 3, "Solid": 4, "MultiSolid": 5, "CompositeSolid": 5}
                semantic_levels = {"MultiSurface": 1, "CompositeSurface": 1, "Solid": 2, "MultiSolid": 3, "CompositeSolid": 3}
                depth = depth_by_type.get(geometry_type)
                boundaries = geometry.get("boundaries")
                if depth is None:
                    g1_failures.add("UNSUPPORTED_GEOMETRY_TYPE")
                    continue
                ok, rings = _validate_boundary_indices(boundaries, depth, len(vertices) if isinstance(vertices, list) else 0)
                if not ok:
                    g1_failures.add("BOUNDARY_INDEX_OR_SHAPE_INVALID")
                else:
                    all_rings.extend(rings)
                semantics = geometry.get("semantics") or {}
                definitions = semantics.get("surfaces", []) if isinstance(semantics, Mapping) else []
                if not isinstance(definitions, list) or any(not isinstance(item, Mapping) or not isinstance(item.get("type"), str) for item in definitions):
                    g1_failures.add("SEMANTIC_DEFINITIONS_INVALID")
                    continue
                semantic_ok, used_indices = _validate_semantic_shape(semantics.get("values"), boundaries, semantic_levels[geometry_type], definitions)
                if not semantic_ok:
                    g1_failures.add("SEMANTIC_VALUES_SHAPE_OR_INDEX_INVALID")
                    continue
                for index in used_indices:
                    surfaces[str(definitions[index]["type"])] += 1
    required = {"RoofSurface", "WallSurface", "GroundSurface"}
    g0 = object_count >= expected_features_min and lod22 >= expected_features_min and required.issubset(surfaces)
    g1 = bool(records) and finite_vertices and object_count >= expected_features_min and not g1_failures
    ring_diagnostic = (
        bool(all_rings) and "BOUNDARY_INDEX_OR_SHAPE_INVALID" not in g1_failures
        and all(len(set(ring)) >= 3 and all(left != right for left, right in zip(ring, ring[1:])) for ring in all_rings)
    )
    return {
        "records": len(records),
        "city_object_count": object_count,
        "lod22_geometry_count": lod22,
        "semantic_surface_counts": dict(surfaces),
        "G0_generated": g0,
        "G1_schema_semantic": g1,
        "G1_check_class": "INTERNAL_CITYJSON_BOUNDARY_SEMANTICS_PARENT_CHILD_VALIDATION",
        "G1_failure_reasons": sorted(g1_failures),
        "geometry_ring_diagnostic": ring_diagnostic,
        "geometry_ring_diagnostic_class": "DIAGNOSTIC_RING_INDEX_SANITY_NOT_G2_NOT_VAL3DITY",
        "G2_geometry_topology_valid": None,
        "G2_null_reason": "CANONICAL_VALIDATOR_UNAVAILABLE",
    }


def verify_synthetic(store: AddOnceStore, output_dir: Path, exit_code: int) -> dict[str, Any]:
    receipt_path = store.path("control/synthetic_smoke_pass_v1.json")
    if receipt_path.is_file():
        body = json.loads(receipt_path.read_bytes())
        for record in body.get("output_records", []):
            store.read_verified(record)
        for name in ("attempt_started", "attempt_result", "runtime_log", "roofer_internal_log"):
            record = body.get(name)
            if record:
                store.read_verified(record)
        return {**body, "fast_path": True, "synthetic_reexecution": 0, "new_writes": 0}
    started = store.path("smoke/attempt_01.started.json")
    if not started.is_file():
        raise RuntimeError("synthetic Roofer was not durably started")
    result_relative = "smoke/attempt_01.result.json"
    output_records = [
        compact_file_record(store, path)
        for path in sorted(output_dir.rglob("*"))
        if path.is_file() and not path.is_symlink()
    ] if output_dir.is_dir() and not output_dir.is_symlink() else []
    runtime_path = store.path("smoke/work/runtime.log")
    runtime_log = (
        compact_file_record(store, runtime_path)
        if runtime_path.is_file() and not runtime_path.is_symlink()
        else None
    )
    internal_path = store.path("smoke/work/roofer.log.json")
    internal_log = compact_file_record(store, internal_path) if internal_path.is_file() and not internal_path.is_symlink() else None
    if exit_code != 0:
        store.add_json(result_relative, {
            "status": "FAILED", "exit_code": exit_code,
            "failure_reason": f"SYNTHETIC_ROOFER_EXIT_{exit_code}",
            "runtime_log": runtime_log, "roofer_internal_log": internal_log,
            "output_records": output_records,
            "scientific_payload_bytes_read_or_hashed": 0,
            "scientific_verdict": None,
        })
        raise RuntimeError(f"synthetic Roofer exited {exit_code}")
    try:
        check = provisional_output_check(output_dir, expected_features_min=5)
    except (RuntimeError, ValueError, json.JSONDecodeError) as error:
        store.add_json(result_relative, {
            "status": "FAILED", "exit_code": exit_code,
            "failure_reason": f"SYNTHETIC_VALIDATION_ERROR:{error}",
            "runtime_log": runtime_log, "roofer_internal_log": internal_log,
            "output_records": output_records,
            "scientific_payload_bytes_read_or_hashed": 0,
            "scientific_verdict": None,
        })
        raise
    if not (check["G0_generated"] and check["G1_schema_semantic"]):
        store.add_json(result_relative, {
            "status": "FAILED", "exit_code": exit_code,
            "failure_reason": "SYNTHETIC_G0_G1_REQUIREMENTS_NOT_MET",
            "check": check, "scientific_payload_bytes_read_or_hashed": 0,
            "runtime_log": runtime_log, "roofer_internal_log": internal_log,
            "output_records": output_records,
            "scientific_verdict": None,
        })
        raise RuntimeError("synthetic Roofer output failed strict LoD2.2/schema screen")
    if runtime_log is None:
        raise RuntimeError("synthetic runtime log is missing")
    attempt_result = store.add_json(result_relative, {
        "status": "PASS", "exit_code": exit_code, "check": check,
        "runtime_log": runtime_log, "roofer_internal_log": internal_log,
        "output_records": output_records,
        "scientific_payload_bytes_read_or_hashed": 0,
        "scientific_verdict": None,
    })
    body = {
        "schema": "jointbuildgs.p2_c1_c2_synthetic_smoke.v1", "status": "PASS", **check,
        "attempt_started": compact_file_record(store, started),
        "attempt_result": attempt_result,
        "runtime_log": runtime_log,
        "roofer_internal_log": internal_log,
        "output_records": output_records,
        "scientific_payload_bytes_read_or_hashed": 0,
        "scientific_verdict": None,
    }
    store.add_json("control/synthetic_smoke_pass_v1.json", body)
    return body


def next_synthetic_action(store: AddOnceStore) -> dict[str, Any]:
    """Start the sole smoke attempt, or prove the completed no-reexecution path."""

    pass_path = store.path("control/synthetic_smoke_pass_v1.json")
    if pass_path.is_file():
        body = verify_synthetic(store, store.path("smoke/work/out"), 0)
        return {"action": "SKIP_COMPLETED", "receipt": body, "new_writes": 0}
    started = store.path("smoke/attempt_01.started.json")
    result = store.path("smoke/attempt_01.result.json")
    output = store.path("smoke/work/out")
    if started.exists() or result.exists() or output.exists():
        raise RuntimeError("synthetic smoke is partial or failed; duplicate execution is prohibited")
    marker = {
        "status": "STARTED", "attempt_number": 1,
        "started_unix": time.time(), "retry_allowed": False,
        "scientific_payload_bytes_read_or_hashed": 0,
        "scientific_verdict": None,
    }
    store.add_json("smoke/attempt_01.started.json", marker)
    return {"action": "RUN", "attempt_number": 1}


def prepare_scientific(
    store: AddOnceStore,
    *,
    c1_grid_path: Path,
    c1_checkpoint_path: Path,
    c2_ply_path: Path,
    c2_checkpoint_path: Path,
    reference_cells_path: Path,
    source_commit: str,
    run_id: str,
    handoff_id: str,
    accepted_receipt_path: Path,
    accepted_commit: str,
    project_image_id: str,
    artifact_root_token: str,
) -> dict[str, Any]:
    """Freeze condition jobs, then and only then open score-only reference."""

    completed_path = store.path("control/scientific_prepared_v1.json")
    if completed_path.is_file():
        body = json.loads(completed_path.read_bytes())
        authority = body.get("execution_authority") or {}
        receipt_bytes = accepted_receipt_path.read_bytes()
        if (
            body.get("status") != "PREPARED" or body.get("source_commit") != source_commit or body.get("run_id") != run_id
            or authority.get("handoff_id") != handoff_id or authority.get("accepted_commit") != accepted_commit
            or authority.get("project_image_id") != project_image_id or authority.get("artifact_root_token") != artifact_root_token
            or authority.get("accepted_receipt", {}).get("sha256") != sha256_bytes(receipt_bytes)
        ):
            raise RuntimeError("completed prepare identity mismatch")
        return {**body, "fast_path": True, "scientific_source_reopens": 0, "new_writes": 0}
    smoke = store.path("control/synthetic_smoke_pass_v1.json")
    if not smoke.is_file() or json.loads(smoke.read_bytes()).get("status") != "PASS":
        raise RuntimeError("synthetic zero-payload smoke must pass before scientific input opens")
    config = load_config()
    started_at = time.time()
    receipt_bytes = accepted_receipt_path.read_bytes()
    receipt = json.loads(receipt_bytes)
    if (
        handoff_id != config["handoff_id"] or receipt.get("handoff_id") != handoff_id
        or receipt.get("state") != "accepted" or receipt.get("direction") != "work_to_experiment"
        or receipt.get("verification", {}).get("docker_image_digest") != project_image_id
        or not re.fullmatch(r"[0-9a-f]{40}", accepted_commit)
        or artifact_root_token != "artifact://JointBuildGS"
    ):
        raise RuntimeError("accepted execution authority identity mismatch")
    planned_inputs = {
        "c1_grid": {key: config["inputs"]["c1_grid"][key] for key in ("artifact_relative_path", "bytes", "sha256")},
        "c1_checkpoint": {
            "path": config["inputs"]["c1_grid"]["attestation_checkpoint_relative_path"],
            "bytes": config["inputs"]["c1_grid"]["attestation_checkpoint_bytes"],
            "sha256": config["inputs"]["c1_grid"]["attestation_checkpoint_sha256"],
        },
        "c2_derivative": {key: config["inputs"]["c2_mvs_class26"][key] for key in ("artifact_relative_path", "bytes", "sha256")},
        "c2_checkpoint": {
            "path": config["inputs"]["c2_mvs_class26"]["attestation_checkpoint_relative_path"],
            "bytes": config["inputs"]["c2_mvs_class26"]["attestation_checkpoint_bytes"],
            "sha256": config["inputs"]["c2_mvs_class26"]["attestation_checkpoint_sha256"],
        },
        "reference_candidate_cells": {key: config["inputs"]["reference_candidate_cells"][key] for key in ("artifact_relative_path", "bytes", "sha256")},
        "development_score_scope": {
            "path": config["scope"]["development_score_scope_path"],
            "canonical_lf_bytes": config["scope"]["development_score_scope_canonical_lf_bytes"],
            "canonical_lf_sha256": config["scope"]["development_score_scope_canonical_lf_sha256"],
        },
        "eligibility_git_blob": config["frozen_lineage"]["eligibility"],
        "split_git_blob": config["frozen_lineage"]["split"],
    }
    identity = {
        "task_id": TASK_ID,
        "handoff_id": handoff_id,
        "source_commit": source_commit,
        "accepted_commit": accepted_commit,
        "accepted_receipt": {"path": accepted_receipt_path.as_posix(), "bytes": len(receipt_bytes), "sha256": sha256_bytes(receipt_bytes)},
        "project_image_id": project_image_id,
        "roofer_image": config["stage3"]["roofer_image"],
        "artifact_root_token": artifact_root_token,
        "run_id": run_id,
        "config_canonical_lf_sha256": sha256_bytes(canonical_lf_bytes(CONFIG_PATH)),
        "development_id_set_sha256": config["scope"]["development_id_set_sha256"],
        "exact_inputs": planned_inputs,
    }
    operation_id = sha256_bytes(canonical_json_bytes(identity))
    store.add_json("control/scientific_started_v1.json", {**identity, "operation_id": operation_id, "started_unix": started_at, "scientific_verdict": None})

    # C1 is derived only from generic min/max/count because raw classes are all 0.
    c1_spec = config["inputs"]["c1_grid"]
    store.add_json("attempts/c1_condition_source/attempt_01.json", {"operation_id": operation_id, "opened_after_smoke": True, "reference_score_cells_opened": False})
    c1_attestation, c1_checkpoint_input = resolve_c1_grid_checkpoint(c1_checkpoint_path, c1_spec)
    c1_bytes, c1_input = capture_exact_once(c1_grid_path, expected_bytes=c1_attestation["bytes"], expected_sha256=c1_attestation["sha256"])
    c1_points, c1_stats = load_c1_grid(c1_bytes, config)
    c1_derivative = store.add("conditions/C1_L_upper/c1_grid_all_class26_v1.ply", ply_bytes(c1_points))
    c1_components, c1_map = derive_components("C1_L_upper", c1_points, config)

    # C2 consumes only the frozen common-MVS derivative, attested by its checkpoint.
    c2_spec = config["inputs"]["c2_mvs_class26"]
    attestation, checkpoint_input = resolve_checkpoint_record(
        c2_checkpoint_path,
        c2_spec["attestation_record_key"],
        c2_spec["artifact_relative_path"],
        expected_checkpoint_bytes=int(c2_spec["attestation_checkpoint_bytes"]),
        expected_checkpoint_sha256=c2_spec["attestation_checkpoint_sha256"],
    )
    store.add_json("attempts/c2_condition_source/attempt_01.json", {"operation_id": operation_id, "opened_after_smoke": True, "reference_or_uas_opened": False, "raw_dim_dense_opened": False})
    c2_bytes, c2_input = capture_exact_once(c2_ply_path, expected_bytes=attestation["bytes"], expected_sha256=attestation["sha256"])
    c2_points, c2_stats = parse_ascii_class26_ply(c2_bytes, config)
    c2_components, c2_map = derive_components("C2_MVS", c2_points, config)

    component_sets = {"C1_L_upper": (c1_components, c1_points), "C2_MVS": (c2_components, c2_points)}
    job_records: list[dict[str, Any]] = []
    component_records: list[dict[str, Any]] = []
    for condition in CONDITIONS:
        components, condition_points = component_sets[condition]
        for component in components:
            component_records.append(component)
            if component["pre_roofer_failure"]:
                continue
            input_bytes, roofprint_bytes = component_job(condition, component, condition_points, config)
            prefix = f"operations/{condition}/{component['component_id']}/work"
            input_record = store.add(f"{prefix}/input.las", input_bytes)
            roofprint_record = store.add(f"{prefix}/r_derived.geojson", roofprint_bytes)
            job_records.append({
                "operation_unit_id": f"{condition}|{component['component_id']}",
                "condition_id": condition,
                "component_id": component["component_id"],
                "work_directory": prefix,
                "input": input_record,
                "r_derived": roofprint_record,
                "output_directory": f"{prefix}/out",
                "stable_id_used_to_derive_input": False,
                "reference_or_bbox_used_to_derive_input": False,
            })
    components_record = store.add("freeze/condition_components_v1.jsonl", jsonl_bytes(component_records))
    all_jobs_record = store.add("freeze/all_condition_jobs_v1.jsonl", jsonl_bytes(job_records))
    store.add_json("checkpoints/120-condition_components_and_r_derived_frozen.json", {
        "ordinal": 120,
        "stage": "condition_components_and_all_r_derived_frozen",
        "operation_id": operation_id,
        "c1_input": c1_input,
        "c1_attestation_checkpoint": c1_checkpoint_input,
        "c1_attestation": c1_attestation,
        "c1_derivative": c1_derivative,
        "c1_stats": c1_stats,
        "c2_input": c2_input,
        "c2_attestation_checkpoint": checkpoint_input,
        "c2_attestation": attestation,
        "c2_stats": c2_stats,
        "components": components_record,
        "all_jobs": all_jobs_record,
        "reference_score_cells_opened_before_checkpoint": False,
    })

    # Score-only UAS evidence is opened strictly after condition/R_derived freeze.
    contract = validate_contract(config)
    roster = read_csv(_safe_repo_path(config["scope"]["roster_path"]))
    score_scope = read_csv(_safe_repo_path(config["scope"]["development_score_scope_path"]))
    store.add_json("control/preselected_cases_v1.json", {
        "rule": config["representative_case_rule"], "cases": contract["representatives"],
        "chosen_before_score_outcomes": True,
        "condition_geometry_checkpoint": components_record["sha256"],
    })
    reference_spec = config["inputs"]["reference_candidate_cells"]
    store.add_json("attempts/reference_score_source/attempt_01.json", {"operation_id": operation_id, "condition_geometry_checkpoint": components_record["sha256"], "role": "SCORE_ONLY"})
    reference_rows, reference_input = project_development_score_cells(reference_cells_path, reference_spec, score_scope)
    mappings, dev_score_cells = associate_development(roster, reference_rows, {"C1_L_upper": c1_map, "C2_MVS": c2_map})
    score_record = store.add("freeze/development_score_cells_v1.jsonl", jsonl_bytes(dev_score_cells))
    jobs_by_unit = {row["operation_unit_id"]: row for row in job_records}
    required_units = sorted({row["operation_unit_id"] for row in mappings if row["operation_unit_id"]})
    component_by_id = {row["component_id"]: row for row in component_records}
    for mapping in mappings:
        if mapping["operation_unit_id"] and mapping["operation_unit_id"] not in jobs_by_unit:
            mapping["pre_roofer_failure"] = component_by_id[mapping["component_id"]]["pre_roofer_failure"]
        else:
            mapping["pre_roofer_failure"] = None
    mapping_record = store.add("freeze/development_score_association_with_pre_roofer_status_v1.jsonl", jsonl_bytes(mappings))
    execution_units = [jobs_by_unit[value] for value in required_units if value in jobs_by_unit]
    execution_record = store.add("freeze/execution_units_v1.jsonl", jsonl_bytes(execution_units))
    execution_tsv = "operation_unit_id\twork_directory\n" + "".join(
        f"{row['operation_unit_id']}\t{row['work_directory']}\n" for row in execution_units
    )
    execution_tsv_record = store.add("freeze/execution_units_v1.tsv", execution_tsv.encode("utf-8"))
    duplicate_savings = sum(row["operation_unit_id"] in jobs_by_unit for row in mappings) - len(execution_units)
    if duplicate_savings < 0:
        raise RuntimeError("unique-operation accounting underflow")
    if time.time() - started_at > int(config["caps"]["wall_clock_seconds_hard"]):
        raise RuntimeError("hard 12-hour cap exceeded during preparation")
    if output_tree_bytes(store.root) > int(config["caps"]["new_output_bytes_hard"]):
        raise RuntimeError("hard 100GB new-output cap exceeded during preparation")
    body = {
        "schema": "jointbuildgs.p2_c1_c2_scientific_prepared.v1",
        "status": "PREPARED",
        "source_commit": source_commit,
        "run_id": run_id,
        "operation_id": operation_id,
        "condition_components": components_record,
        "all_condition_jobs": all_jobs_record,
        "development_score_association": mapping_record,
        "development_score_cells": score_record,
        "execution_units": execution_record,
        "execution_units_tsv": execution_tsv_record,
        "result_rows": len(mappings),
        "unique_execution_units": len(execution_units),
        "duplicate_roofer_calculations_prevented": duplicate_savings,
        "execution_authority": identity,
        "tool_records": {
            "project_image_id": project_image_id,
            "roofer_image": config["stage3"]["roofer_image"],
            "roofer_version": config["stage3"]["roofer_version"],
            "python_version": sys.version.split()[0],
        },
        "input_records": {
            "c1_grid": c1_input, "c1_checkpoint": c1_checkpoint_input,
            "c2_derivative": c2_input, "c2_checkpoint": checkpoint_input,
            "reference_candidate_cells": reference_input,
            "development_score_scope": planned_inputs["development_score_scope"],
            "eligibility_git_blob": config["frozen_lineage"]["eligibility"],
            "split_git_blob": config["frozen_lineage"]["split"],
        },
        "output_records": {
            "c1_derivative": c1_derivative, "components": components_record,
            "all_jobs": all_jobs_record, "score_association": mapping_record,
            "score_cells": score_record, "execution_units": execution_record,
            "execution_units_tsv": execution_tsv_record,
        },
        "reference_inputs": {"cells": reference_input},
        "validation_payload_accesses": 0,
        "held_out_payload_accesses": 0,
        "raw_dim_dense_accesses": 0,
        "scientific_verdict": None,
    }
    store.add_json("control/scientific_prepared_v1.json", body)
    return body


def execution_units(store: AddOnceStore) -> list[dict[str, Any]]:
    prepared = json.loads(store.path("control/scientific_prepared_v1.json").read_bytes())
    return parse_jsonl(store.read_verified(prepared["execution_units"]))


def _unit_slug(unit_id: str) -> str:
    if not re.fullmatch(r"C[12]_[A-Za-z0-9_]+\|C[12]_[A-Za-z0-9_]+", unit_id):
        raise RuntimeError("invalid operation unit ID")
    return sha256_bytes(unit_id.encode())[:24]


def next_attempt(store: AddOnceStore, unit_id: str) -> dict[str, Any]:
    config = load_config()
    units = {row["operation_unit_id"]: row for row in execution_units(store)}
    if unit_id not in units:
        raise RuntimeError("operation unit is not in frozen execution manifest")
    slug = _unit_slug(unit_id)
    final = store.path(f"operation_records/{slug}/final_v1.json")
    if final.is_file():
        return {"action": "SKIP_COMPLETED", "unit": units[unit_id], "new_writes": 0}
    attempts = sorted(store.path(f"operation_records/{slug}").glob("attempt_*.started.json")) if store.path(f"operation_records/{slug}").exists() else []
    max_attempts = int(config["retries"]["max_attempts_per_execution_unit"])
    if len(attempts) >= max_attempts:
        raise RuntimeError("per-operation attempt cap exhausted")
    retry_count = sum(1 for path in store.root.glob("operation_records/*/attempt_02.started.json"))
    number = len(attempts) + 1
    if number > 1 and retry_count >= int(config["retries"]["max_total_retry_attempts"]):
        raise RuntimeError("task-total retry cap exhausted")
    quarantine_state: dict[str, Any] | None = None
    if number == 2:
        attempt_one_result_path = store.path(f"operation_records/{slug}/attempt_01.result.json")
        if attempt_one_result_path.is_symlink() or not attempt_one_result_path.is_file():
            raise RuntimeError("attempt 2 requires a durable attempt-1 result")
        attempt_one_result = json.loads(attempt_one_result_path.read_bytes())
        if (
            attempt_one_result.get("status") != "RETRY_AUTHORIZED_INFRASTRUCTURE_ONLY"
            or attempt_one_result.get("attempt_number") != 1
            or attempt_one_result.get("exit_code") not in config["retries"]["retryable_exit_codes"]
        ):
            raise RuntimeError("attempt 1 is not explicitly retry-authorized")
        output_dir = store.path(units[unit_id]["output_directory"])
        quarantine = output_dir.with_name("out.attempt_01.quarantine")
        if quarantine.exists():
            raise RuntimeError("attempt-1 output quarantine already exists")
        if output_dir.is_symlink() or not output_dir.is_dir():
            raise RuntimeError("attempt-1 output directory is missing/non-regular before retry")
        roofer_log = output_dir.parent / "roofer.log.json"
        roofer_log_quarantine = output_dir.parent / "roofer.log.attempt_01.quarantine.json"
        if roofer_log_quarantine.exists():
            raise RuntimeError("attempt-1 Roofer internal-log quarantine already exists")
        log_moved = False
        if roofer_log.exists():
            if roofer_log.is_symlink() or not roofer_log.is_file():
                raise RuntimeError("attempt-1 Roofer internal log is non-regular")
            roofer_log.rename(roofer_log_quarantine)
            log_moved = True
        output_dir.rename(quarantine)
        quarantined_files = [
            path for path in sorted(quarantine.rglob("*"))
            if path.is_file() and not path.is_symlink()
        ]
        quarantined_output_records = [compact_file_record(store, path) for path in quarantined_files]
        quarantined_internal_log = (
            compact_file_record(store, roofer_log_quarantine) if log_moved else None
        )
        quarantine_state = {
            "path": quarantine.relative_to(store.root).as_posix(),
            "files": len(quarantined_files),
            "bytes": sum(record["bytes"] for record in quarantined_output_records),
            "content_hashes": len(quarantined_output_records),
            "output_records": quarantined_output_records,
            "roofer_internal_log_moved": log_moved,
            "roofer_internal_log": quarantined_internal_log,
            "attempt_1_result": compact_file_record(store, attempt_one_result_path),
            "retry_authorization_status": attempt_one_result["status"],
        }
        output_dir.mkdir()
        directory_fd = os.open(output_dir.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    marker = {"operation_unit_id": unit_id, "attempt_number": number, "started_unix": time.time(), "parameter_change_allowed": False, "quality_driven_retry_allowed": False, "quarantined_previous_output": quarantine_state}
    store.add_json(f"operation_records/{slug}/attempt_{number:02d}.started.json", marker)
    return {"action": "RUN", "attempt_number": number, "unit": units[unit_id]}


def record_attempt(
    store: AddOnceStore,
    unit_id: str,
    attempt_number: int,
    exit_code: int,
    runtime_seconds: float,
    peak_memory_bytes: int | None,
    peak_memory_unavailable_reason: str | None,
) -> dict[str, Any]:
    config = load_config()
    units = {row["operation_unit_id"]: row for row in execution_units(store)}
    unit = units.get(unit_id)
    if unit is None:
        raise RuntimeError("operation unit is not frozen")
    slug = _unit_slug(unit_id)
    marker = store.path(f"operation_records/{slug}/attempt_{attempt_number:02d}.started.json")
    if not marker.is_file():
        raise RuntimeError("attempt was not durably started before execution")
    final_path = store.path(f"operation_records/{slug}/final_v1.json")
    if final_path.exists():
        raise RuntimeError("operation already has final add-once result")
    if peak_memory_bytes is None and not peak_memory_unavailable_reason:
        raise RuntimeError("peak memory requires a measured byte count or an honest unavailable reason")
    if peak_memory_bytes is not None and peak_memory_unavailable_reason is not None:
        raise RuntimeError("peak memory byte count and unavailable reason are mutually exclusive")
    output_dir = store.path(unit["output_directory"])
    runtime_log = compact_file_record(store, store.path(unit["work_directory"]) / f"runtime.attempt_{attempt_number}.log")
    check: dict[str, Any] | None = None
    validation_error = None
    if exit_code == 0:
        try:
            check = provisional_output_check(output_dir)
        except (RuntimeError, ValueError, json.JSONDecodeError) as error:
            validation_error = str(error)
    retryable = exit_code in set(config["retries"]["retryable_exit_codes"]) and validation_error is None and attempt_number == 1
    total_retries = sum(1 for path in store.root.glob("operation_records/*/attempt_02.started.json"))
    retry_authorized = retryable and total_retries < int(config["retries"]["max_total_retry_attempts"])
    attempt_body = {
        "status": "RETRY_AUTHORIZED_INFRASTRUCTURE_ONLY" if retry_authorized else "TERMINAL_ATTEMPT_RESULT",
        "operation_unit_id": unit_id,
        "attempt_number": attempt_number,
        "exit_code": exit_code,
        "runtime_seconds": runtime_seconds,
        "peak_memory_bytes": peak_memory_bytes,
        "peak_memory_unavailable_reason": peak_memory_unavailable_reason,
        "runtime_log": runtime_log,
        "provisional_check": check,
        "validation_error": validation_error,
    }
    store.add_json(f"operation_records/{slug}/attempt_{attempt_number:02d}.result.json", attempt_body)
    if retry_authorized:
        return attempt_body
    internal_log_path = store.path(unit["work_directory"]) / "roofer.log.json"
    internal_log_record = (
        compact_file_record(store, internal_log_path)
        if internal_log_path.is_file() and not internal_log_path.is_symlink()
        else None
    )
    succeeded = exit_code == 0 and validation_error is None and check is not None and bool(check["G0_generated"])
    output_bytes = output_tree_bytes(output_dir) if output_dir.exists() else 0
    output_records = [
        compact_file_record(store, path)
        for path in sorted(output_dir.rglob("*"))
        if path.is_file() and not path.is_symlink()
    ] if output_dir.exists() else []
    runtime_logs = []
    attempt_runtime_seconds: list[float] = []
    for number in range(1, attempt_number + 1):
        result_path = store.path(f"operation_records/{slug}/attempt_{number:02d}.result.json")
        attempt_result = json.loads(result_path.read_bytes())
        runtime_logs.append(attempt_result["runtime_log"])
        attempt_runtime_seconds.append(float(attempt_result["runtime_seconds"]))
    marker_body = json.loads(marker.read_bytes())
    final = {
        "operation_unit_id": unit_id,
        "condition_id": unit["condition_id"],
        "component_id": unit["component_id"],
        "status": "COMPLETE" if succeeded else "FAILED_G0",
        "attempt_count": attempt_number,
        "retry_count": max(0, attempt_number - 1),
        "runtime_seconds": sum(attempt_runtime_seconds),
        "attempt_runtime_seconds": attempt_runtime_seconds,
        "peak_memory_bytes": peak_memory_bytes,
        "peak_memory_unavailable_reason": peak_memory_unavailable_reason,
        "output_bytes": output_bytes,
        "output_records": output_records,
        "roofer_internal_log": internal_log_record,
        "G0_generated": succeeded,
        "G1_schema_semantic": check["G1_schema_semantic"] if check else None,
        "G1_check_class": "INTERNAL_CITYJSON_BOUNDARY_SEMANTICS_PARENT_CHILD_VALIDATION",
        "G1_failure_reasons": check["G1_failure_reasons"] if check else ["NO_VALIDATABLE_CITYJSON_OUTPUT"],
        "geometry_ring_diagnostic": check["geometry_ring_diagnostic"] if check else None,
        "geometry_ring_diagnostic_class": "DIAGNOSTIC_RING_INDEX_SANITY_NOT_G2_NOT_VAL3DITY",
        "G2_geometry_topology_valid": None,
        "G2_null_reason": "CANONICAL_VALIDATOR_UNAVAILABLE",
        "failure_reasons": [] if succeeded else sorted({
            value for value in (
                validation_error,
                f"ROOFER_EXIT_{exit_code}" if exit_code else None,
                "G0_OUTPUT_REQUIREMENTS_NOT_MET" if exit_code == 0 and check is not None and not check["G0_generated"] else None,
            ) if value
        }),
        "quarantine_state": marker_body.get("quarantined_previous_output"),
        "runtime_logs": runtime_logs,
        "scientific_verdict": None,
    }
    store.add_json(f"operation_records/{slug}/final_v1.json", final)
    if output_tree_bytes(store.root) > int(config["caps"]["new_output_bytes_hard"]):
        raise RuntimeError("hard 100GB new-output cap exceeded")
    return final


def group_balanced_summary(
    rows: Sequence[Mapping[str, Any]],
    metric: str,
    group_sizes: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    group_sizes = dict(group_sizes or load_config()["scope"]["group_sizes"])
    by_group: defaultdict[str, list[float]] = defaultdict(list)
    for row in rows:
        value = row.get("metrics", {}).get(metric)
        if isinstance(value, (int, float)) and math.isfinite(float(value)):
            by_group[row["group_id"]].append(float(value))
    unexpected = set(by_group) - set(group_sizes)
    if unexpected:
        raise RuntimeError(f"unexpected development groups in summary: {sorted(unexpected)}")
    group_means = {
        group: (sum(by_group[group]) / len(by_group[group]) if by_group[group] else None)
        for group in sorted(group_sizes)
    }
    complete = all(value is not None for value in group_means.values())
    group_rows = [
        {
            "group_id": group,
            "denominator": int(group_sizes[group]),
            "values_with_metric": len(by_group[group]),
            "mean": group_means[group],
        }
        for group in sorted(group_sizes)
    ]
    return {
        "metric": metric,
        "group_means": group_means,
        "groups": group_rows,
        "unweighted_group_mean": sum(float(value) for value in group_means.values()) / 5 if complete else None,
        "groups_with_value": sum(value is not None for value in group_means.values()),
        "all_five_groups_have_value": complete,
        "inferential_statistics": None,
        "interpretation": "DESCRIPTIVE_ONLY_NO_INFERENCE_N51_FIVE_GROUPS",
    }


def validate_result_rows(rows: Sequence[Mapping[str, Any]], config: Mapping[str, Any]) -> dict[str, Any]:
    schema_path = _safe_repo_path(config["result"]["schema_path"])
    schema = json.loads(schema_path.read_bytes())
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    errors: list[str] = []
    for index, row in enumerate(rows):
        for error in sorted(validator.iter_errors(row), key=lambda item: list(item.absolute_path)):
            location = ".".join(str(value) for value in error.absolute_path) or "<row>"
            errors.append(f"row {index} {location}: {error.message}")
            if len(errors) >= 20:
                break
        if len(errors) >= 20:
            break
    if errors:
        raise RuntimeError("result schema validation failed: " + " | ".join(errors))
    return {
        "schema_path": config["result"]["schema_path"],
        "schema_sha256": sha256_bytes(schema_path.read_bytes()),
        "validated_rows": len(rows),
        "validation_errors": 0,
    }


def condition_group_technical_summary(
    rows: Sequence[Mapping[str, Any]],
    group_sizes: Mapping[str, int],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for method in CONDITIONS:
        for group_id, denominator in sorted(group_sizes.items()):
            selected = [row for row in rows if row["method_id"] == method and row["group_id"] == group_id]
            if len(selected) != int(denominator):
                raise RuntimeError(f"condition/group denominator mismatch: {method}/{group_id}")
            failures: Counter[str] = Counter()
            for row in selected:
                failures.update(row["failure_reasons"])
                if row["G1_schema_semantic"] is False:
                    failures.update(row["G1_failure_reasons"])
            runtimes = [float(row["runtime_seconds"]) for row in selected if isinstance(row["runtime_seconds"], (int, float))]
            result.append({
                "method_id": method,
                "group_id": group_id,
                "denominator": int(denominator),
                "attempted": sum(int(row["attempt_count"]) > 0 for row in selected),
                "G0_generated": sum(row["G0_generated"] is True for row in selected),
                "G1_true": sum(row["G1_schema_semantic"] is True for row in selected),
                "failed_G0": sum(row["G0_generated"] is not True for row in selected),
                "runtime_seconds_sum": sum(runtimes) if runtimes else None,
                "runtime_seconds_median": float(np.median(runtimes)) if runtimes else None,
                "failure_reason_counts": dict(sorted(failures.items())),
            })
    return result


def _transformed_vertices(record: Mapping[str, Any], inherited: Mapping[str, Any] | None) -> np.ndarray:
    transform = record.get("transform") or inherited or {"scale": [1, 1, 1], "translate": [0, 0, 0]}
    vertices = np.asarray(record.get("vertices", []), dtype=np.float64)
    scale = np.asarray(transform.get("scale", [1, 1, 1]), dtype=np.float64)
    translate = np.asarray(transform.get("translate", [0, 0, 0]), dtype=np.float64)
    if vertices.ndim != 2 or (vertices.size and vertices.shape[1] < 3) or scale.shape != (3,) or translate.shape != (3,):
        raise RuntimeError("CityJSON vertex/transform shape is invalid")
    return vertices[:, :3] * scale + translate if vertices.size else np.empty((0, 3), dtype=np.float64)


def _roof_rings(geometry: Mapping[str, Any]) -> Iterator[list[int]]:
    semantics = geometry.get("semantics") or {}
    surfaces = semantics.get("surfaces") or []
    roofs = {index for index, value in enumerate(surfaces) if isinstance(value, Mapping) and value.get("type") == "RoofSurface"}
    boundaries, values = geometry.get("boundaries") or [], semantics.get("values") or []
    candidates: list[tuple[Any, Any]] = []
    if geometry.get("type") in ("MultiSurface", "CompositeSurface"):
        candidates = list(zip(boundaries, values))
    elif geometry.get("type") == "Solid":
        candidates = [(surface, semantic) for shell, shell_values in zip(boundaries, values) for surface, semantic in zip(shell, shell_values)]
    elif geometry.get("type") in ("MultiSolid", "CompositeSolid"):
        candidates = [(surface, semantic) for solid, solid_values in zip(boundaries, values) for shell, shell_values in zip(solid, solid_values) for surface, semantic in zip(shell, shell_values)]
    for rings, semantic in candidates:
        if semantic in roofs and isinstance(rings, list) and rings and isinstance(rings[0], list):
            if len(rings) != 1:
                raise RuntimeError("RoofSurface inner rings are unsupported by the frozen metric triangulation")
            yield [int(value) for value in rings[0]]


def roof_triangles(output_dir: Path) -> list[np.ndarray]:
    triangles: list[np.ndarray] = []
    for path in sorted(output_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in (".json", ".jsonl", ".cityjson"):
            continue
        inherited: Mapping[str, Any] | None = None
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            if record.get("type") == "CityJSON" and record.get("transform"):
                inherited = record["transform"]
            vertices = _transformed_vertices(record, inherited)
            for city_object in (record.get("CityObjects") or {}).values():
                for geometry in city_object.get("geometry", []):
                    if str(geometry.get("lod")) != "2.2":
                        continue
                    for ring in _roof_rings(geometry):
                        if len(ring) >= 2 and ring[0] == ring[-1]:
                            ring = ring[:-1]
                        if len(ring) < 3 or any(index < 0 or index >= len(vertices) for index in ring):
                            raise RuntimeError("RoofSurface ring has invalid vertex references")
                        first = vertices[ring[0]]
                        for index in range(1, len(ring) - 1):
                            triangle = np.vstack((first, vertices[ring[index]], vertices[ring[index + 1]]))
                            if np.linalg.norm(np.cross(triangle[1] - triangle[0], triangle[2] - triangle[0])) > 1e-12:
                                triangles.append(triangle)
    return triangles


def _closest_point_triangle(point: np.ndarray, triangle: np.ndarray) -> np.ndarray:
    a, b, c = triangle
    ab, ac, ap = b - a, c - a, point - a
    d1, d2 = float(np.dot(ab, ap)), float(np.dot(ac, ap))
    if d1 <= 0 and d2 <= 0:
        return a
    bp = point - b
    d3, d4 = float(np.dot(ab, bp)), float(np.dot(ac, bp))
    if d3 >= 0 and d4 <= d3:
        return b
    vc = d1 * d4 - d3 * d2
    if vc <= 0 and d1 >= 0 and d3 <= 0:
        return a + (d1 / (d1 - d3)) * ab
    cp = point - c
    d5, d6 = float(np.dot(ab, cp)), float(np.dot(ac, cp))
    if d6 >= 0 and d5 <= d6:
        return c
    vb = d5 * d2 - d1 * d6
    if vb <= 0 and d2 >= 0 and d6 <= 0:
        return a + (d2 / (d2 - d6)) * ac
    va = d3 * d6 - d5 * d4
    if va <= 0 and (d4 - d3) >= 0 and (d5 - d6) >= 0:
        return b + ((d4 - d3) / ((d4 - d3) + (d5 - d6))) * (c - b)
    denominator = 1.0 / (va + vb + vc)
    v, w = vb * denominator, vc * denominator
    return a + ab * v + ac * w


def _vertical_z(x: float, y: float, triangle: np.ndarray) -> float | None:
    a, b, c = triangle
    denominator = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
    if abs(float(denominator)) <= 1e-12:
        return None
    alpha = ((b[1] - c[1]) * (x - c[0]) + (c[0] - b[0]) * (y - c[1])) / denominator
    beta = ((c[1] - a[1]) * (x - c[0]) + (a[0] - c[0]) * (y - c[1])) / denominator
    gamma = 1.0 - alpha - beta
    return float(alpha * a[2] + beta * b[2] + gamma * c[2]) if min(alpha, beta, gamma) >= -1e-9 else None


def score_continuous(reference_rows: Sequence[Mapping[str, Any]], triangles: Sequence[np.ndarray]) -> dict[str, Any]:
    deferred_names = ("roof_plane_completeness", "roof_plane_correctness", "roof_plane_quality", "oversegmentation", "undersegmentation")
    null_reasons = {name: "MATCHING_RULE_AND_G3_THRESHOLD_NOT_FROZEN" for name in deferred_names}
    names = ("reference_vertical_coverage", "height_error_signed_mean_m", "height_error_signed_median_m", "height_error_mae_m", "RMSZ_m", "RMSXY_m", "surface_distance_rmse_m", "surface_distance_p95_m", "normal_angular_error_median_deg", "normal_angular_error_p95_deg")
    if not reference_rows or not triangles:
        null_reasons.update({name: "NO_REFERENCE_CELLS_OR_PREDICTED_ROOF_SURFACE" for name in names})
        return {"reference_cell_count": len(reference_rows), "vertically_scored_cell_count": 0, **{name: None for name in names}, **{name: None for name in deferred_names}, "null_reasons": null_reasons}
    vertical_errors: list[float] = []
    distances: list[float] = []
    xy_distances: list[float] = []
    angles: list[float] = []
    for row in reference_rows:
        point = np.asarray([float(row["cell_x"]), float(row["cell_y"]), float(row["top_z"])], dtype=np.float64)
        vertical = [value for value in (_vertical_z(point[0], point[1], triangle) for triangle in triangles) if value is not None]
        if vertical:
            vertical_errors.append(max(vertical) - point[2])
        candidates = [(_closest_point_triangle(point, triangle), triangle) for triangle in triangles]
        closest, triangle = min(candidates, key=lambda value: float(np.linalg.norm(value[0] - point)))
        distances.append(float(np.linalg.norm(closest - point)))
        xy_distances.append(float(np.linalg.norm(closest[:2] - point[:2])))
        predicted = np.cross(triangle[1] - triangle[0], triangle[2] - triangle[0])
        predicted /= np.linalg.norm(predicted)
        reference = np.asarray([float(row["normal_x"]), float(row["normal_y"]), float(row["normal_z"])], dtype=np.float64)
        if np.linalg.norm(reference) > 0:
            angles.append(math.degrees(math.acos(float(np.clip(abs(np.dot(predicted, reference / np.linalg.norm(reference))), 0.0, 1.0)))))
    errors, distance_array, xy_array, angle_array = map(lambda value: np.asarray(value, dtype=np.float64), (vertical_errors, distances, xy_distances, angles))
    def metric(values: np.ndarray, function: Any, name: str) -> float | None:
        if not len(values):
            null_reasons[name] = "NO_VALID_SCORE_CORRESPONDENCE"
            return None
        return float(function(values))
    return {
        "reference_cell_count": len(reference_rows),
        "vertically_scored_cell_count": len(errors),
        "reference_vertical_coverage": len(errors) / len(reference_rows),
        "height_error_signed_mean_m": metric(errors, np.mean, "height_error_signed_mean_m"),
        "height_error_signed_median_m": metric(errors, np.median, "height_error_signed_median_m"),
        "height_error_mae_m": metric(errors, lambda x: np.mean(np.abs(x)), "height_error_mae_m"),
        "RMSZ_m": metric(errors, lambda x: np.sqrt(np.mean(x * x)), "RMSZ_m"),
        "RMSXY_m": metric(xy_array, lambda x: np.sqrt(np.mean(x * x)), "RMSXY_m"),
        "surface_distance_rmse_m": metric(distance_array, lambda x: np.sqrt(np.mean(x * x)), "surface_distance_rmse_m"),
        "surface_distance_p95_m": metric(distance_array, lambda x: np.percentile(x, 95, method="linear"), "surface_distance_p95_m"),
        "normal_angular_error_median_deg": metric(angle_array, np.median, "normal_angular_error_median_deg"),
        "normal_angular_error_p95_deg": metric(angle_array, lambda x: np.percentile(x, 95, method="linear"), "normal_angular_error_p95_deg"),
        **{name: None for name in deferred_names},
        "null_reasons": null_reasons,
    }


def finalize(store: AddOnceStore) -> dict[str, Any]:
    """Create exact 102-row descriptive results from terminal unique operations."""

    completed = store.path("control/finalized_v1.json")
    if completed.is_file():
        return {**json.loads(completed.read_bytes()), "fast_path": True, "operation_output_reopens": 0, "new_writes": 0}
    config = load_config()
    prepared = json.loads(store.path("control/scientific_prepared_v1.json").read_bytes())
    synthetic_smoke = json.loads(store.path("control/synthetic_smoke_pass_v1.json").read_bytes())
    if synthetic_smoke.get("status") != "PASS":
        raise RuntimeError("synthetic smoke PASS ledger is missing before finalize")
    units = {row["operation_unit_id"]: row for row in execution_units(store)}
    operation_results: dict[str, dict[str, Any]] = {}
    triangles: dict[str, list[np.ndarray]] = {}
    roofer_points_by_unit = roofer_point_counts(store, units)
    for unit_id, unit in units.items():
        final_path = store.path(f"operation_records/{_unit_slug(unit_id)}/final_v1.json")
        if not final_path.is_file():
            raise RuntimeError(f"execution unit is not terminal: {unit_id}")
        result = json.loads(final_path.read_bytes())
        operation_results[unit_id] = result
        if result["G0_generated"]:
            triangles[unit_id] = roof_triangles(store.path(unit["output_directory"]))
    mappings = parse_jsonl(store.read_verified(prepared["development_score_association"]))
    cells = parse_jsonl(store.read_verified(prepared["development_score_cells"]))
    by_building: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in cells:
        by_building[row["stable_id"]].append(row)
    components = {row["component_id"]: row for row in parse_jsonl(store.read_verified(prepared["condition_components"]))}
    rows: list[dict[str, Any]] = []
    for mapping in mappings:
        unit_id = mapping["operation_unit_id"]
        operation = operation_results.get(unit_id) if unit_id else None
        references = by_building[mapping["building_id"]]
        succeeded = bool(operation and operation["G0_generated"])
        metrics = score_continuous(references, triangles.get(unit_id, []))
        component = components.get(mapping["component_id"])
        unit = units.get(unit_id) if unit_id else None
        roofer_points = roofer_points_by_unit.get(unit_id) if unit is not None else None
        method = mapping["method_id"]
        rows.append({
            "building_id": mapping["building_id"], "group_id": mapping["group_id"], "split": "development",
            "method_id": method, "run_id": prepared["run_id"], "operation_id": prepared["operation_id"],
            "criterion_version": config["result"]["criterion_version"],
            "reference_provenance": config["result"]["c1_reference_provenance"] if method == "C1_L_upper" else config["result"]["c2_reference_provenance"],
            "component_id": mapping["component_id"], "operation_unit_id": unit_id,
            "G0_generated": succeeded,
            "G1_schema_semantic": operation["G1_schema_semantic"] if operation else None,
            "G1_check_class": "INTERNAL_CITYJSON_BOUNDARY_SEMANTICS_PARENT_CHILD_VALIDATION",
            "G1_failure_reasons": operation["G1_failure_reasons"] if operation else ["NO_EXECUTED_CITYJSON_OUTPUT"],
            "geometry_ring_diagnostic": operation["geometry_ring_diagnostic"] if operation else None,
            "geometry_ring_diagnostic_class": "DIAGNOSTIC_RING_INDEX_SANITY_NOT_G2_NOT_VAL3DITY",
            "G2_geometry_topology_valid": None, "G2_null_reason": "CANONICAL_VALIDATOR_UNAVAILABLE",
            "G3_roof_structure_acceptable": None, "G4_geometric_accuracy_acceptable": None, "PASS_usable": None,
            "threshold_null_reason": "THRESHOLD_NOT_FROZEN",
            "attempt_count": operation["attempt_count"] if operation else 0,
            "retry_count": operation["retry_count"] if operation else 0,
            "runtime_seconds": operation["runtime_seconds"] if operation else None,
            "peak_memory_bytes": operation["peak_memory_bytes"] if operation else None,
            "peak_memory_unavailable_reason": operation["peak_memory_unavailable_reason"] if operation else "NO_ROOFER_EXECUTION",
            "input_point_count": component["point_count"] if component else None,
            "roofer_input_point_count": roofer_points,
            "output_bytes": operation["output_bytes"] if operation else 0,
            "failure_reasons": operation["failure_reasons"] if operation else [mapping.get("pre_roofer_failure") or "UNASSOCIATED_CONDITION_COMPONENT"],
            "metrics": metrics, "scientific_verdict": None,
        })
    if len(rows) != 102 or len({(row["building_id"], row["method_id"]) for row in rows}) != 102:
        raise RuntimeError("final result matrix is not exact 51x2")
    schema_validation = validate_result_rows(rows, config)
    metrics_record = store.add("results/building_method_metrics_v1.jsonl", jsonl_bytes(rows))
    metric_names = ("reference_vertical_coverage", "height_error_mae_m", "RMSZ_m", "RMSXY_m", "surface_distance_rmse_m", "surface_distance_p95_m", "normal_angular_error_median_deg")
    summaries = [{"method_id": method, **group_balanced_summary([row for row in rows if row["method_id"] == method], name)} for method in CONDITIONS for name in metric_names]
    summary_record = store.add("results/group_balanced_descriptive_v1.jsonl", jsonl_bytes(summaries))
    technical_groups = condition_group_technical_summary(rows, config["scope"]["group_sizes"])
    technical_group_record = store.add("results/condition_group_technical_summary_v1.jsonl", jsonl_bytes(technical_groups))
    input_definition_record = store.add(
        "results/development_input_definition_v1.csv",
        canonical_lf_bytes(_safe_repo_path(config["scope"]["development_score_scope_path"])),
    )
    cases = json.loads(store.path("control/preselected_cases_v1.json").read_bytes())["cases"]
    case_record = store.add("results/preselected_case_index_v1.jsonl", jsonl_bytes([row for row in rows if cases.get(row["group_id"]) == row["building_id"]]))
    method_summary = {
        method: {
            "denominator": 51,
            "G0_generated": sum(row["G0_generated"] for row in rows if row["method_id"] == method),
            "G1_provisional_true": sum(row["G1_schema_semantic"] is True for row in rows if row["method_id"] == method),
            "G2_canonical_available": 0,
            "G3_G4_PASS_available": 0,
            "self_reference": method == "C1_L_upper",
        }
        for method in CONDITIONS
    }
    def input_identity_lines() -> str:
        output = []
        for name, record in prepared["input_records"].items():
            path = record.get("path") or record.get("artifact_relative_path") or record.get("git_path") or "GIT_OWNED_SCOPE"
            size = record.get("bytes", record.get("canonical_bytes", record.get("canonical_lf_bytes")))
            digest = record.get("sha256", record.get("canonical_sha256", record.get("canonical_lf_sha256", record.get("git_blob"))))
            output.append(f"| {name} | {path} | {size} | {digest} |")
        return "\n".join(output)

    panel_lines: list[str] = []
    for method in CONDITIONS:
        panel_lines.extend([
            f"## {method} technical panel",
            "",
            "| group | denominator | attempted | G0 | G1 | failed G0 | runtime sum (s) | failure reasons |",
            "|---|---:|---:|---:|---:|---:|---:|---|",
        ])
        for item in technical_groups:
            if item["method_id"] == method:
                panel_lines.append(
                    f"| {item['group_id']} | {item['denominator']} | {item['attempted']} | {item['G0_generated']} | "
                    f"{item['G1_true']} | {item['failed_G0']} | {item['runtime_seconds_sum']} | "
                    f"`{json.dumps(item['failure_reason_counts'], sort_keys=True, separators=(',', ':'))}` |"
                )
        panel_lines.append("")
    report = f"""# C1/C2 development feasibility pilot compact report

- Result rows: 102 (exact 51 development buildings x 2 conditions)
- Exact score projection: {config['scope']['development_score_cell_rows']} building-cell rows from one global 20,520-row stream; non-development retained/scored/promoted: 0
- Exact 51-building input definition: `development_input_definition_v1.csv` (group, bbox, patch IDs, expected score-cell count)
- Unique Roofer operations: {prepared['unique_execution_units']}
- Duplicate component calculations prevented: {prepared['duplicate_roofer_calculations_prevented']}
- C1 G0: {method_summary['C1_L_upper']['G0_generated']}/51 (self-reference upper baseline)
- C2 G0: {method_summary['C2_MVS']['G0_generated']}/51 (independent UAS score reference)
- Canonical G2: null (`CANONICAL_VALIDATOR_UNAVAILABLE`)
- G3/G4/PASS_usable: null (`THRESHOLD_NOT_FROZEN`)
- Inference: prohibited; five-group mean is null unless every frozen group has a metric value
- Validation/held-out access: 0/0
- scientific_verdict: null

## Bound inputs

| input | exact path/identity | bytes | SHA-256 or Git blob |
|---|---|---:|---|
{input_identity_lines()}

{chr(10).join(panel_lines)}
## Qualitative fixed-view evidence

- status: `NOT_RENDERED`
- reason: `{config['result']['qualitative_fixed_view_null_reason']}`
- The five outcome-free representatives remain in the compact case table; no post-outcome visual selection occurred.
"""
    report_record = store.add("results/C1_C2_DEVELOPMENT_REPORT_v1.md", report.encode("utf-8"))
    compact_ledger_records = [
        compact_file_record(store, path)
        for relative_root in ("control", "checkpoints", "attempts", "operation_records")
        for path in sorted(store.path(relative_root).rglob("*"))
        if path.is_file() and not path.is_symlink()
    ]
    body = {
        "schema": "jointbuildgs.p2_c1_c2_finalized.v1", "status": "TECHNICAL_RESULTS_COMPLETE_FOR_WORK_HOST_REVIEW",
        "run_id": prepared["run_id"], "operation_id": prepared["operation_id"], "result_rows": 102,
        "unique_execution_units": prepared["unique_execution_units"],
        "duplicate_roofer_calculations_prevented": prepared["duplicate_roofer_calculations_prevented"],
        "method_summary": method_summary, "metrics": metrics_record, "group_balanced_descriptive": summary_record,
        "condition_group_technical_summary": technical_group_record,
        "development_input_definition": input_definition_record,
        "preselected_cases": case_record, "report": report_record,
        "result_schema_validation": schema_validation,
        "execution_authority": prepared["execution_authority"],
        "tool_records": prepared["tool_records"],
        "input_records": prepared["input_records"],
        "output_records": {
            **prepared["output_records"],
            "synthetic_smoke": synthetic_smoke,
            "metrics": metrics_record, "group_balanced_descriptive": summary_record,
            "condition_group_technical_summary": technical_group_record,
            "development_input_definition": input_definition_record,
            "preselected_cases": case_record, "report": report_record,
            "compact_control_checkpoint_attempt_ledgers": compact_ledger_records,
            "roofer_operations": [
                {"operation_unit_id": unit_id, "final": operation_results[unit_id], "outputs": operation_results[unit_id].get("output_records", [])}
                for unit_id in sorted(operation_results)
            ],
        },
        "qualitative_fixed_view": {"status": "NOT_RENDERED", "reason": config["result"]["qualitative_fixed_view_null_reason"]},
        "canonical_G2": None, "G3": None, "G4": None, "PASS_usable": None, "scientific_verdict": None,
    }
    store.add_json("control/finalized_v1.json", body)
    return body


def roofer_point_counts(store: AddOnceStore, units: Mapping[str, Mapping[str, Any]]) -> dict[str, int]:
    """Read/verify each unique operation LAS exactly once, then cache its count."""

    result: dict[str, int] = {}
    for unit_id, unit in units.items():
        with laspy.open(io.BytesIO(store.read_verified(unit["input"])), closefd=False) as reader:
            result[unit_id] = int(reader.header.point_count)
    return result


def _csv_bytes(fieldnames: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def promote(store: AddOnceStore, repo_root: Path, promotion_parent_commit: str) -> dict[str, Any]:
    """Promote compact results only; never reopen frozen scientific sources."""

    repo_root = repo_root.resolve()
    git_store = AddOnceStore(repo_root)
    manifest_relative = "artifacts/manifests/p2_baselines/c1_c2_feasibility_pilot_recovery_r2_v1/technical_result_manifest_v1.json"
    existing = git_store.path(manifest_relative)
    if existing.is_file():
        manifest = json.loads(existing.read_bytes())
        for record in manifest["promoted_records"]:
            git_store.read_verified(record)
        return {**manifest, "fast_path": True, "scientific_source_reopens": 0, "new_writes": 0}
    if not re.fullmatch(r"[0-9a-f]{40}", promotion_parent_commit):
        raise RuntimeError("promotion parent commit must be an exact full SHA")
    finalized = json.loads(store.path("control/finalized_v1.json").read_bytes())
    if finalized.get("status") != "TECHNICAL_RESULTS_COMPLETE_FOR_WORK_HOST_REVIEW" or finalized.get("scientific_verdict") is not None:
        raise RuntimeError("external finalized ledger is not promotable")
    actual_head = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "-C", str(repo_root), "status", "--porcelain=v1", "--untracked-files=all"],
        check=True, capture_output=True, text=True,
    ).stdout
    accepted_commit = (finalized.get("execution_authority") or {}).get("accepted_commit")
    if actual_head != promotion_parent_commit or accepted_commit != promotion_parent_commit:
        raise RuntimeError("promotion parent is not the exact clean accepted repository HEAD")
    if dirty:
        raise RuntimeError("repository must be clean before add-once result promotion")
    rows = parse_jsonl(store.read_verified(finalized["metrics"]))
    summaries = parse_jsonl(store.read_verified(finalized["group_balanced_descriptive"]))
    technical_groups = parse_jsonl(store.read_verified(finalized["condition_group_technical_summary"]))
    input_definition = store.read_verified(finalized["development_input_definition"])
    cases = parse_jsonl(store.read_verified(finalized["preselected_cases"]))
    external_report = store.read_verified(finalized["report"])
    if len(rows) != 102 or len(cases) != 10:
        raise RuntimeError("compact promotion inputs differ from exact 102 rows/5x2 cases")
    metrics_fields = [
        "building_id", "group_id", "split", "method_id", "reference_provenance", "component_id", "operation_unit_id",
        "G0_generated", "G1_schema_semantic", "G1_check_class", "G1_failure_reasons",
        "geometry_ring_diagnostic", "geometry_ring_diagnostic_class", "G2_geometry_topology_valid", "G2_null_reason",
        "G3_roof_structure_acceptable", "G4_geometric_accuracy_acceptable", "PASS_usable", "threshold_null_reason",
        "attempt_count", "retry_count", "runtime_seconds", "peak_memory_bytes", "peak_memory_unavailable_reason", "input_point_count", "roofer_input_point_count", "output_bytes",
        "reference_cell_count", "vertically_scored_cell_count", "reference_vertical_coverage", "height_error_signed_mean_m",
        "height_error_signed_median_m", "height_error_mae_m", "RMSZ_m", "RMSXY_m", "surface_distance_rmse_m",
        "surface_distance_p95_m", "normal_angular_error_median_deg", "normal_angular_error_p95_deg", "failure_reasons",
    ]
    flat_rows = []
    for row in rows:
        flat = {name: row.get(name) for name in metrics_fields}
        for name in metrics_fields:
            if name in row["metrics"]:
                flat[name] = row["metrics"][name]
        flat["failure_reasons"] = ";".join(row["failure_reasons"])
        flat["G1_failure_reasons"] = ";".join(row["G1_failure_reasons"])
        flat_rows.append(flat)
    summary_fields = ["method_id", "metric", "unweighted_group_mean", "groups_with_value", "all_five_groups_have_value", "inferential_statistics", "interpretation", "group_means_json", "groups_with_denominators_json"]
    flat_summaries = [{
        **{name: row.get(name) for name in summary_fields},
        "group_means_json": json.dumps(row["group_means"], sort_keys=True, separators=(",", ":")),
        "groups_with_denominators_json": json.dumps(row["groups"], sort_keys=True, separators=(",", ":")),
    } for row in summaries]
    technical_fields = ["method_id", "group_id", "denominator", "attempted", "G0_generated", "G1_true", "failed_G0", "runtime_seconds_sum", "runtime_seconds_median", "failure_reason_counts_json"]
    flat_technical = [{
        **{name: row.get(name) for name in technical_fields},
        "failure_reason_counts_json": json.dumps(row["failure_reason_counts"], sort_keys=True, separators=(",", ":")),
    } for row in technical_groups]
    case_fields = ["building_id", "group_id", "method_id", "reference_provenance", "G0_generated", "G1_schema_semantic", "RMSZ_m", "RMSXY_m", "surface_distance_rmse_m", "reference_vertical_coverage", "operation_unit_id"]
    flat_cases = [{**{name: row.get(name) for name in case_fields}, **{name: row["metrics"].get(name) for name in case_fields if name in row["metrics"]}} for row in cases]
    prefix = "docs/experiments/p2/c1_c2_feasibility_pilot_recovery_r2_v1"
    promoted = [
        git_store.add(f"{prefix}/C1_C2_DEVELOPMENT_REPORT_v1.md", external_report),
        git_store.add(f"{prefix}/building_method_metrics_v1.csv", _csv_bytes(metrics_fields, flat_rows)),
        git_store.add(f"{prefix}/group_balanced_descriptive_v1.csv", _csv_bytes(summary_fields, flat_summaries)),
        git_store.add(f"{prefix}/condition_group_technical_summary_v1.csv", _csv_bytes(technical_fields, flat_technical)),
        git_store.add(f"{prefix}/development_input_definition_v1.csv", input_definition),
        git_store.add(f"{prefix}/preselected_case_metrics_v1.csv", _csv_bytes(case_fields, flat_cases)),
    ]
    manifest = {
        "schema": "jointbuildgs.p2_c1_c2_feasibility_technical_result_manifest.v1",
        "task_id": TASK_ID,
        "promotion_parent_commit": promotion_parent_commit,
        "run_id": finalized["run_id"],
        "operation_id": finalized["operation_id"],
        "external_namespace": "artifact://JointBuildGS/phase-payloads/p2-baselines/c1_c2_feasibility_pilot_recovery_r2_v1/P2-C1-C2-FEASIBILITY-PILOT-RECOVERY-R2-v1/",
        "external_records": {
            "metrics": finalized["metrics"], "group_balanced_descriptive": finalized["group_balanced_descriptive"],
            "condition_group_technical_summary": finalized["condition_group_technical_summary"],
            "development_input_definition": finalized["development_input_definition"],
            "preselected_cases": finalized["preselected_cases"], "report": finalized["report"],
        },
        "execution_authority": finalized["execution_authority"],
        "tool_records": finalized["tool_records"],
        "input_records": finalized["input_records"],
        "output_records": finalized["output_records"],
        "result_schema_validation": finalized["result_schema_validation"],
        "qualitative_fixed_view": finalized["qualitative_fixed_view"],
        "result_rows": 102,
        "unique_execution_units": finalized["unique_execution_units"],
        "duplicate_roofer_calculations_prevented": finalized["duplicate_roofer_calculations_prevented"],
        "method_summary": finalized["method_summary"],
        "validation_payload_accesses": 0,
        "held_out_payload_accesses": 0,
        "canonical_G2": None,
        "G3": None,
        "G4": None,
        "PASS_usable": None,
        "promoted_records": promoted,
        "scientific_source_reopens_during_promotion": 0,
        "scientific_verdict": None,
    }
    git_store.add_json(manifest_relative, manifest)
    return manifest
