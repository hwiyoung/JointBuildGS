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
import time
from datetime import date
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

import numpy as np
import laspy
from scipy import ndimage


REPO = Path(__file__).resolve().parents[3]
CONFIG_PATH = REPO / "configs/p2_baselines/c1_c2_feasibility_pilot_v1/pilot_v1.json"
TASK_ID = "P2-C1-C2-FEASIBILITY-PILOT-v1"
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


def validate_contract(config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Validate Git-owned scope without opening any scientific payload."""

    config = dict(config or load_config())
    if config.get("task_id") != TASK_ID or tuple(config["scope"]["condition_ids"]) != CONDITIONS:
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
    association_path = _safe_repo_path(scope["reference_association_path"])
    association_bytes = association_path.read_bytes()
    if len(association_bytes) != int(scope["reference_association_bytes"]) or sha256_bytes(association_bytes) != scope["reference_association_sha256"]:
        raise RuntimeError("development reference-association file identity mismatch")
    association = list(csv.DictReader(io.StringIO(association_bytes.decode("utf-8"), newline="")))
    if list(association[0]) != ["stable_id", "reference_patch_ids"]:
        raise RuntimeError("association file must not contain bbox/geometry fields")
    association_ids = [row["stable_id"] for row in association]
    if len(association_ids) != 51 or set(association_ids) != set(ids):
        raise RuntimeError("score association IDs differ from exact development roster")
    patch_pattern = re.compile(r"^UASPATCH_[0-9a-f]{20}$")
    for row in association:
        patches = row["reference_patch_ids"].split(";")
        if not patches or any(not patch_pattern.fullmatch(value) for value in patches):
            raise RuntimeError(f"invalid frozen patch association: {row['stable_id']}")
    if config["association"]["timing"] != "AFTER_CONDITION_COMPONENTS_AND_ALL_R_DERIVED_JOB_INPUTS_ARE_ADD_ONCE_FROZEN":
        raise RuntimeError("stable-ID association timing is not leakage-safe")
    if config["association"]["geometry_modification_allowed"] or config["association"]["crop_allowed"] or config["association"]["registration_allowed"]:
        raise RuntimeError("score association may not modify/crop/register condition geometry")
    if config["c1_materialization"].get("r1_reference_cells_used") is not False:
        raise RuntimeError("C1 condition geometry must use all grid class2/class6 cells, never R1 score cells")
    if config["condition_geometry"].get("stable_id_used") or config["condition_geometry"].get("target_bbox_used"):
        raise RuntimeError("condition components must be stable-ID/bbox blind")
    if config["stage3"]["required_lod"] != "2.2" or config["stage3"]["lod11_fallback_allowed"]:
        raise RuntimeError("strict LoD2.2/no-fallback contract mismatch")
    execution = config["stage3"]["execution"]
    if execution != {
        "serial_jobs": 1,
        "cpus_per_attempt": 2,
        "memory_bytes_per_attempt": 8000000000,
        "gpus_per_attempt": 0,
        "timeout_seconds_per_attempt": 600,
    }:
        raise RuntimeError("per-attempt resource contract mismatch")
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
        "scientific_payload_bytes_read_or_hashed": 0,
        "scientific_verdict": None,
    }


def representative_cases(roster: Sequence[Mapping[str, str]]) -> dict[str, str]:
    grouped: defaultdict[str, list[str]] = defaultdict(list)
    for row in roster:
        grouped[row["group_id"]].append(row["stable_id"])
    return {
        group: min(ids, key=lambda stable_id: hashlib.sha256(f"{TASK_ID}|{group}|{stable_id}".encode()).hexdigest())
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
            arrays[name] = value
    points: list[Point] = []
    class2 = arrays["class2_min_z"].reshape(ny, nx)
    class2_valid = (arrays["class2_count"].reshape(ny, nx) > 0) & np.isfinite(class2)
    if not np.any(class2_valid):
        raise RuntimeError("C1 grid has no class-2 terrain cells")
    nearest = ndimage.distance_transform_edt(~class2_valid, return_distances=False, return_indices=True)
    filled = class2[tuple(nearest)]
    windows = config["c1_materialization"]["terrain_filter_windows_cells"]
    terrain = np.minimum.reduce([ndimage.grey_opening(filled, size=(int(size), int(size)), mode="nearest") for size in windows])
    ground = class2_valid.ravel()
    building = (
        (arrays["class6_count"] >= int(config["c1_materialization"]["minimum_class6_points_per_cell"]))
        & np.isfinite(arrays["class6_max_z"])
        & ((arrays["class6_max_z"] - terrain.ravel()) >= float(config["c1_materialization"]["minimum_height_above_terrain_m"]))
    )
    for classification, mask, heights in ((2, ground, arrays["class2_min_z"]), (6, building, arrays["class6_max_z"])):
        for flat in np.flatnonzero(mask):
            iy, ix = divmod(int(flat), nx)
            points.append(Point(bbox[0] + (ix + 0.5) * cell, bbox[1] + (iy + 0.5) * cell, float(heights[flat]), classification, ix, iy))
    return points, {
        "method": "ALL_FROZEN_C1_GRID_CLASS2_CLASS6_CELLS_V1",
        "ground_points": int(np.count_nonzero(ground)),
        "building_points": int(np.count_nonzero(building)),
        "minimum_class6_points_per_cell": int(config["c1_materialization"]["minimum_class6_points_per_cell"]),
        "minimum_height_above_terrain_m": float(config["c1_materialization"]["minimum_height_above_terrain_m"]),
        "terrain_filter_windows_cells": list(windows),
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


def _reference_rows(data: bytes, expected_rows: int) -> list[dict[str, str]]:
    rows = list(csv.DictReader(io.StringIO(data.decode("utf-8"), newline="")))
    required = {"patch_id", "cell_ix", "cell_iy", "top_z", "normal_x", "normal_y", "normal_z"}
    if len(rows) != expected_rows or not rows or not required.issubset(rows[0]):
        raise RuntimeError("frozen reference cell table schema/count mismatch")
    return rows


def associate_development(
    roster: Sequence[Mapping[str, str]],
    association_rows: Sequence[Mapping[str, str]],
    reference_rows: Sequence[Mapping[str, str]],
    component_maps: Mapping[str, Mapping[tuple[int, int], str]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    patch_cells: defaultdict[str, list[Mapping[str, str]]] = defaultdict(list)
    for row in reference_rows:
        patch_cells[row["patch_id"]].append(row)
    patches_by_id = {row["stable_id"]: row["reference_patch_ids"].split(";") for row in association_rows}
    group_by_id = {row["stable_id"]: row["group_id"] for row in roster}
    mappings: list[dict[str, Any]] = []
    score_cells: list[dict[str, Any]] = []
    for stable_id in sorted(group_by_id):
        selected_reference: list[Mapping[str, str]] = []
        for patch_id in patches_by_id[stable_id]:
            selected_reference.extend(patch_cells.get(patch_id, []))
        if not selected_reference:
            raise RuntimeError(f"development stable ID has no frozen reference score cells: {stable_id}")
        for row in selected_reference:
            score_cells.append({"stable_id": stable_id, **dict(row)})
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


def provisional_output_check(output_dir: Path, *, expected_features_min: int = 1) -> dict[str, Any]:
    """Internal deterministic screen; it is not canonical val3dity G2."""

    records = _cityjson_records(output_dir)
    object_count = 0
    lod22 = 0
    surfaces: Counter[str] = Counter()
    finite_vertices = True
    for record in records:
        vertices = record.get("vertices", [])
        finite_vertices &= isinstance(vertices, list) and all(
            isinstance(vertex, list) and len(vertex) >= 3 and all(isinstance(v, (int, float)) and math.isfinite(v) for v in vertex[:3])
            for vertex in vertices
        )
        for city_object in (record.get("CityObjects") or {}).values():
            object_count += 1
            for geometry in city_object.get("geometry", []):
                if str(geometry.get("lod")) == "2.2":
                    lod22 += 1
                elif str(geometry.get("lod")) == "1.1":
                    raise RuntimeError("LoD1.1 fallback is prohibited")
                semantics = geometry.get("semantics") or {}
                definitions = semantics.get("surfaces", [])
                def used_indices(value: Any) -> Iterator[int]:
                    if isinstance(value, int):
                        yield value
                    elif isinstance(value, list):
                        for child in value:
                            yield from used_indices(child)
                for index in used_indices(semantics.get("values", [])):
                    if 0 <= index < len(definitions) and isinstance(definitions[index], Mapping) and isinstance(definitions[index].get("type"), str):
                        surfaces[definitions[index]["type"]] += 1
    required = {"RoofSurface", "WallSurface", "GroundSurface"}
    g0 = object_count >= expected_features_min and lod22 >= expected_features_min and required.issubset(surfaces)
    g1 = bool(records) and finite_vertices and object_count >= expected_features_min
    internal = g1 and g0
    return {
        "records": len(records),
        "city_object_count": object_count,
        "lod22_geometry_count": lod22,
        "semantic_surface_counts": dict(surfaces),
        "G0_generated": g0,
        "G1_schema_semantic": g1,
        "G1_check_class": "PROVISIONAL_TECHNICAL_INTERNAL_SCHEMA_SEMANTIC",
        "G2_internal_screen": internal,
        "G2_check_class": "DIAGNOSTIC_INTERNAL_NOT_CANONICAL_VAL3DITY",
        "G2_geometry_topology_valid": None,
        "G2_null_reason": "CANONICAL_VALIDATOR_UNAVAILABLE",
    }


def verify_synthetic(store: AddOnceStore, output_dir: Path, exit_code: int) -> dict[str, Any]:
    receipt_path = store.path("control/synthetic_smoke_pass_v1.json")
    if receipt_path.is_file():
        return json.loads(receipt_path.read_bytes())
    if exit_code != 0:
        raise RuntimeError(f"synthetic Roofer exited {exit_code}")
    check = provisional_output_check(output_dir, expected_features_min=5)
    if not (check["G0_generated"] and check["G1_schema_semantic"]):
        raise RuntimeError("synthetic Roofer output failed strict LoD2.2/schema screen")
    body = {"schema": "jointbuildgs.p2_c1_c2_synthetic_smoke.v1", "status": "PASS", **check, "scientific_payload_bytes_read_or_hashed": 0, "scientific_verdict": None}
    store.add_json("control/synthetic_smoke_pass_v1.json", body)
    return body


def prepare_scientific(
    store: AddOnceStore,
    *,
    c1_grid_path: Path,
    c2_ply_path: Path,
    c2_checkpoint_path: Path,
    reference_cells_path: Path,
    patch_summary_path: Path,
    source_commit: str,
    run_id: str,
) -> dict[str, Any]:
    """Freeze condition jobs, then and only then open score-only reference."""

    completed_path = store.path("control/scientific_prepared_v1.json")
    if completed_path.is_file():
        body = json.loads(completed_path.read_bytes())
        if body.get("status") != "PREPARED" or body.get("source_commit") != source_commit or body.get("run_id") != run_id:
            raise RuntimeError("completed prepare identity mismatch")
        return {**body, "fast_path": True, "scientific_source_reopens": 0, "new_writes": 0}
    smoke = store.path("control/synthetic_smoke_pass_v1.json")
    if not smoke.is_file() or json.loads(smoke.read_bytes()).get("status") != "PASS":
        raise RuntimeError("synthetic zero-payload smoke must pass before scientific input opens")
    config = load_config()
    contract = validate_contract(config)
    roster = read_csv(_safe_repo_path(config["scope"]["roster_path"]))
    association_rows = read_csv(_safe_repo_path(config["scope"]["reference_association_path"]))
    started_at = time.time()
    identity = {
        "task_id": TASK_ID,
        "source_commit": source_commit,
        "run_id": run_id,
        "config_sha256": sha256_bytes(CONFIG_PATH.read_bytes()),
        "development_id_set_sha256": contract["development_id_set_sha256"],
    }
    operation_id = sha256_bytes(canonical_json_bytes(identity))
    store.add_json("control/scientific_started_v1.json", {**identity, "operation_id": operation_id, "started_unix": started_at, "scientific_verdict": None})
    store.add_json("control/preselected_cases_v1.json", {"rule": config["representative_case_rule"], "cases": contract["representatives"], "chosen_before_outcomes": True})

    # C1 is derived only from all frozen grid class-2/class-6 cells.
    c1_spec = config["inputs"]["c1_grid"]
    store.add_json("attempts/c1_condition_source/attempt_01.json", {"operation_id": operation_id, "opened_after_smoke": True, "reference_score_cells_opened": False})
    c1_bytes, c1_input = capture_exact_once(c1_grid_path, expected_bytes=int(c1_spec["bytes"]), expected_sha256=c1_spec["sha256"])
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
    reference_spec = config["inputs"]["c1_reference_cells"]
    patch_spec = config["inputs"]["c1_patch_summary"]
    store.add_json("attempts/reference_score_source/attempt_01.json", {"operation_id": operation_id, "condition_geometry_checkpoint": components_record["sha256"], "role": "SCORE_ONLY"})
    reference_bytes, reference_input = capture_exact_once(reference_cells_path, expected_bytes=int(reference_spec["bytes"]), expected_sha256=reference_spec["sha256"])
    patch_bytes, patch_input = capture_exact_once(patch_summary_path, expected_bytes=int(patch_spec["bytes"]), expected_sha256=patch_spec["sha256"])
    reference_rows = _reference_rows(reference_bytes, int(reference_spec["expected_rows"]))
    patch_rows = list(csv.DictReader(io.StringIO(patch_bytes.decode("utf-8"), newline="")))
    if len(patch_rows) != int(patch_spec["expected_rows"]) or {row["patch_id"] for row in patch_rows} != {row["patch_id"] for row in reference_rows}:
        raise RuntimeError("reference patch summary does not match frozen score cells")
    mappings, dev_score_cells = associate_development(roster, association_rows, reference_rows, {"C1_L_upper": c1_map, "C2_MVS": c2_map})
    mapping_record = store.add("freeze/development_score_association_v1.jsonl", jsonl_bytes(mappings))
    score_record = store.add("freeze/development_score_cells_v1.jsonl", jsonl_bytes(dev_score_cells))
    jobs_by_unit = {row["operation_unit_id"]: row for row in job_records}
    required_units = sorted({row["operation_unit_id"] for row in mappings if row["operation_unit_id"]})
    execution_units = [jobs_by_unit[value] for value in required_units]
    if len(execution_units) != len(required_units):
        raise RuntimeError("associated component has no frozen Roofer job")
    execution_record = store.add("freeze/execution_units_v1.jsonl", jsonl_bytes(execution_units))
    execution_tsv = "operation_unit_id\twork_directory\n" + "".join(
        f"{row['operation_unit_id']}\t{row['work_directory']}\n" for row in execution_units
    )
    execution_tsv_record = store.add("freeze/execution_units_v1.tsv", execution_tsv.encode("utf-8"))
    duplicate_savings = sum(row["operation_unit_id"] is not None for row in mappings) - len(execution_units)
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
        "reference_inputs": {"cells": reference_input, "patch_summary": patch_input},
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
        output_dir = store.path(units[unit_id]["output_directory"])
        quarantine = output_dir.with_name("out.attempt_01.quarantine")
        if quarantine.exists():
            raise RuntimeError("attempt-1 output quarantine already exists")
        if output_dir.is_symlink() or not output_dir.is_dir():
            raise RuntimeError("attempt-1 output directory is missing/non-regular before retry")
        files = [path for path in output_dir.rglob("*") if path.is_file() and not path.is_symlink()]
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
        quarantine_state = {"path": quarantine.relative_to(store.root).as_posix(), "files": len(files), "bytes": sum(path.stat().st_size for path in files), "content_hashes": 0, "roofer_internal_log_moved": log_moved}
        output_dir.rename(quarantine)
        output_dir.mkdir()
        directory_fd = os.open(output_dir.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    marker = {"operation_unit_id": unit_id, "attempt_number": number, "started_unix": time.time(), "parameter_change_allowed": False, "quality_driven_retry_allowed": False, "quarantined_previous_output": quarantine_state}
    store.add_json(f"operation_records/{slug}/attempt_{number:02d}.started.json", marker)
    return {"action": "RUN", "attempt_number": number, "unit": units[unit_id]}


def record_attempt(store: AddOnceStore, unit_id: str, attempt_number: int, exit_code: int, runtime_seconds: float, peak_memory_bytes: int | None) -> dict[str, Any]:
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
    output_dir = store.path(unit["output_directory"])
    runtime_log = compact_file_record(store, store.path(unit["work_directory"]) / f"runtime.attempt_{attempt_number}.log")
    check: dict[str, Any] | None = None
    validation_error = None
    if exit_code == 0:
        try:
            check = provisional_output_check(output_dir)
        except (RuntimeError, ValueError, json.JSONDecodeError) as error:
            validation_error = str(error)
    attempt_body = {
        "operation_unit_id": unit_id,
        "attempt_number": attempt_number,
        "exit_code": exit_code,
        "runtime_seconds": runtime_seconds,
        "peak_memory_bytes": peak_memory_bytes,
        "runtime_log": runtime_log,
        "provisional_check": check,
        "validation_error": validation_error,
    }
    store.add_json(f"operation_records/{slug}/attempt_{attempt_number:02d}.result.json", attempt_body)
    retryable = exit_code in set(config["retries"]["retryable_exit_codes"]) and validation_error is None and attempt_number == 1
    total_retries = sum(1 for path in store.root.glob("operation_records/*/attempt_02.started.json"))
    if retryable and total_retries < int(config["retries"]["max_total_retry_attempts"]):
        return {"status": "RETRY_AUTHORIZED_INFRASTRUCTURE_ONLY", **attempt_body}
    succeeded = exit_code == 0 and validation_error is None and check is not None and bool(check["G0_generated"])
    output_bytes = output_tree_bytes(output_dir) if output_dir.exists() else 0
    runtime_logs = []
    for number in range(1, attempt_number + 1):
        result_path = store.path(f"operation_records/{slug}/attempt_{number:02d}.result.json")
        runtime_logs.append(json.loads(result_path.read_bytes())["runtime_log"])
    marker_body = json.loads(marker.read_bytes())
    final = {
        "operation_unit_id": unit_id,
        "condition_id": unit["condition_id"],
        "component_id": unit["component_id"],
        "status": "COMPLETE" if succeeded else "FAILED_G0",
        "attempt_count": attempt_number,
        "retry_count": max(0, attempt_number - 1),
        "runtime_seconds": runtime_seconds,
        "peak_memory_bytes": peak_memory_bytes,
        "output_bytes": output_bytes,
        "G0_generated": succeeded,
        "G1_schema_semantic": check["G1_schema_semantic"] if check else None,
        "G1_check_class": "PROVISIONAL_TECHNICAL_INTERNAL_SCHEMA_SEMANTIC",
        "G2_internal_screen": check["G2_internal_screen"] if check else None,
        "G2_check_class": "DIAGNOSTIC_INTERNAL_NOT_CANONICAL_VAL3DITY",
        "G2_geometry_topology_valid": None,
        "G2_null_reason": "CANONICAL_VALIDATOR_UNAVAILABLE",
        "failure_reasons": [] if succeeded else sorted({value for value in (validation_error, f"ROOFER_EXIT_{exit_code}" if exit_code else None) if value}),
        "quarantine_state": marker_body.get("quarantined_previous_output"),
        "runtime_logs": runtime_logs,
        "scientific_verdict": None,
    }
    store.add_json(f"operation_records/{slug}/final_v1.json", final)
    if output_tree_bytes(store.root) > int(config["caps"]["new_output_bytes_hard"]):
        raise RuntimeError("hard 100GB new-output cap exceeded")
    return final


def group_balanced_summary(rows: Sequence[Mapping[str, Any]], metric: str) -> dict[str, Any]:
    by_group: defaultdict[str, list[float]] = defaultdict(list)
    for row in rows:
        value = row.get("metrics", {}).get(metric)
        if isinstance(value, (int, float)) and math.isfinite(float(value)):
            by_group[row["group_id"]].append(float(value))
    group_means = {group: sum(values) / len(values) for group, values in sorted(by_group.items()) if values}
    return {
        "metric": metric,
        "group_means": group_means,
        "unweighted_group_mean": sum(group_means.values()) / len(group_means) if group_means else None,
        "groups_with_value": len(group_means),
        "inferential_statistics": None,
        "interpretation": "DESCRIPTIVE_ONLY_NO_INFERENCE_N51_FIVE_GROUPS",
    }


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
            "G1_check_class": "PROVISIONAL_TECHNICAL_INTERNAL_SCHEMA_SEMANTIC",
            "G2_internal_screen": operation["G2_internal_screen"] if operation else None,
            "G2_check_class": "DIAGNOSTIC_INTERNAL_NOT_CANONICAL_VAL3DITY",
            "G2_geometry_topology_valid": None, "G2_null_reason": "CANONICAL_VALIDATOR_UNAVAILABLE",
            "G3_roof_structure_acceptable": None, "G4_geometric_accuracy_acceptable": None, "PASS_usable": None,
            "threshold_null_reason": "THRESHOLD_NOT_FROZEN",
            "attempt_count": operation["attempt_count"] if operation else 0,
            "retry_count": operation["retry_count"] if operation else 0,
            "runtime_seconds": operation["runtime_seconds"] if operation else None,
            "peak_memory_bytes": operation["peak_memory_bytes"] if operation else None,
            "input_point_count": component["point_count"] if component else None,
            "roofer_input_point_count": roofer_points,
            "output_bytes": operation["output_bytes"] if operation else 0,
            "failure_reasons": operation["failure_reasons"] if operation else ["UNASSOCIATED_CONDITION_COMPONENT"],
            "metrics": metrics, "scientific_verdict": None,
        })
    if len(rows) != 102 or len({(row["building_id"], row["method_id"]) for row in rows}) != 102:
        raise RuntimeError("final result matrix is not exact 51x2")
    metrics_record = store.add("results/building_method_metrics_v1.jsonl", jsonl_bytes(rows))
    metric_names = ("reference_vertical_coverage", "height_error_mae_m", "RMSZ_m", "RMSXY_m", "surface_distance_rmse_m", "surface_distance_p95_m", "normal_angular_error_median_deg")
    summaries = [{"method_id": method, **group_balanced_summary([row for row in rows if row["method_id"] == method], name)} for method in CONDITIONS for name in metric_names]
    summary_record = store.add("results/group_balanced_descriptive_v1.jsonl", jsonl_bytes(summaries))
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
    report = (
        "# C1/C2 development feasibility pilot compact report\n\n"
        f"- Result rows: 102 (51 buildings x 2 conditions)\n"
        f"- Unique Roofer operations: {prepared['unique_execution_units']}\n"
        f"- Duplicate component calculations prevented: {prepared['duplicate_roofer_calculations_prevented']}\n"
        f"- C1 G0: {method_summary['C1_L_upper']['G0_generated']}/51 (self-reference upper baseline)\n"
        f"- C2 G0: {method_summary['C2_MVS']['G0_generated']}/51 (independent UAS score reference)\n"
        "- Canonical G2: null (`CANONICAL_VALIDATOR_UNAVAILABLE`)\n"
        "- G3/G4/PASS_usable: null (`THRESHOLD_NOT_FROZEN`)\n"
        "- Inference: prohibited; building and unweighted five-group descriptive summaries only\n"
        "- Validation/held-out access: 0/0\n"
        "- scientific_verdict: null\n"
    )
    report_record = store.add("results/C1_C2_DEVELOPMENT_REPORT_v1.md", report.encode("utf-8"))
    body = {
        "schema": "jointbuildgs.p2_c1_c2_finalized.v1", "status": "TECHNICAL_RESULTS_COMPLETE_FOR_WORK_HOST_REVIEW",
        "run_id": prepared["run_id"], "operation_id": prepared["operation_id"], "result_rows": 102,
        "unique_execution_units": prepared["unique_execution_units"],
        "duplicate_roofer_calculations_prevented": prepared["duplicate_roofer_calculations_prevented"],
        "method_summary": method_summary, "metrics": metrics_record, "group_balanced_descriptive": summary_record,
        "preselected_cases": case_record, "report": report_record,
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
    manifest_relative = "artifacts/manifests/p2_baselines/c1_c2_feasibility_pilot_v1/technical_result_manifest_v1.json"
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
    rows = parse_jsonl(store.read_verified(finalized["metrics"]))
    summaries = parse_jsonl(store.read_verified(finalized["group_balanced_descriptive"]))
    cases = parse_jsonl(store.read_verified(finalized["preselected_cases"]))
    if len(rows) != 102 or len(cases) != 10:
        raise RuntimeError("compact promotion inputs differ from exact 102 rows/5x2 cases")
    metrics_fields = [
        "building_id", "group_id", "split", "method_id", "reference_provenance", "component_id", "operation_unit_id",
        "G0_generated", "G1_schema_semantic", "G2_internal_screen", "G2_geometry_topology_valid", "G2_null_reason",
        "G3_roof_structure_acceptable", "G4_geometric_accuracy_acceptable", "PASS_usable", "threshold_null_reason",
        "attempt_count", "retry_count", "runtime_seconds", "peak_memory_bytes", "input_point_count", "roofer_input_point_count", "output_bytes",
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
        flat_rows.append(flat)
    summary_fields = ["method_id", "metric", "unweighted_group_mean", "groups_with_value", "inferential_statistics", "interpretation", "group_means_json"]
    flat_summaries = [{**{name: row.get(name) for name in summary_fields}, "group_means_json": json.dumps(row["group_means"], sort_keys=True, separators=(",", ":"))} for row in summaries]
    case_fields = ["building_id", "group_id", "method_id", "reference_provenance", "G0_generated", "G1_schema_semantic", "RMSZ_m", "RMSXY_m", "surface_distance_rmse_m", "reference_vertical_coverage", "operation_unit_id"]
    flat_cases = [{**{name: row.get(name) for name in case_fields}, **{name: row["metrics"].get(name) for name in case_fields if name in row["metrics"]}} for row in cases]
    method = finalized["method_summary"]
    metric_table = "\n".join(
        f"| {row['method_id']} | {row['metric']} | {row['unweighted_group_mean']} | {row['groups_with_value']} |"
        for row in summaries
    )
    case_table = "\n".join(
        f"| {row['building_id']} | {row['group_id']} | {row['method_id']} | {row['metrics'].get('RMSZ_m')} | {row['metrics'].get('surface_distance_rmse_m')} | {row['G0_generated']} |"
        for row in cases
    )
    report = f"""# C1/C2 development feasibility pilot v1

## Answer first

The exact 51-building development roster produced 102 descriptive score rows using
{finalized['unique_execution_units']} unique condition-component Roofer operations;
{finalized['duplicate_roofer_calculations_prevented']} duplicate calculations were prevented.
C1 is a self-reference upper baseline and C2 alone uses the independent UAS reference.
No validation or held-out result was accessed. This is feasibility evidence, not an
inferential or population claim.

## Technical gates

| condition | denominator | G0 | provisional internal G1 | canonical G2 | G3/G4/PASS |
|---|---:|---:|---:|---|---|
| C1_L_upper | 51 | {method['C1_L_upper']['G0_generated']} | {method['C1_L_upper']['G1_provisional_true']} | null (validator unavailable) | null (threshold not frozen) |
| C2_MVS | 51 | {method['C2_MVS']['G0_generated']} | {method['C2_MVS']['G1_provisional_true']} | null (validator unavailable) | null (threshold not frozen) |

## Group-balanced descriptive metrics

| condition | metric | unweighted five-group mean | groups with value |
|---|---|---:|---:|
{metric_table}

No confidence interval, p-value or other n=51 inferential statistic is reported.

## Preselected qualitative cases

| stable ID | group | condition | RMSZ (m) | surface RMSE (m) | G0 |
|---|---|---|---:|---:|---|
{case_table}

The five representatives were selected by the frozen hash rule before outcomes.

## Limitations

- development only; five groups with one group containing 47/51 buildings;
- C1 accuracy is self-reference and must not be compared as independent accuracy;
- canonical G2 is unavailable because val3dity is not callable in this task;
- G3, G4 and PASS_usable remain null (`THRESHOLD_NOT_FROZEN`);
- no conclusion about C3-C5, validation, held-out or population generalization;
- `scientific_verdict` remains null.
"""
    prefix = "docs/experiments/p2/c1_c2_feasibility_pilot_v1"
    promoted = [
        git_store.add(f"{prefix}/C1_C2_DEVELOPMENT_REPORT_v1.md", report.encode("utf-8")),
        git_store.add(f"{prefix}/building_method_metrics_v1.csv", _csv_bytes(metrics_fields, flat_rows)),
        git_store.add(f"{prefix}/group_balanced_descriptive_v1.csv", _csv_bytes(summary_fields, flat_summaries)),
        git_store.add(f"{prefix}/preselected_case_metrics_v1.csv", _csv_bytes(case_fields, flat_cases)),
    ]
    manifest = {
        "schema": "jointbuildgs.p2_c1_c2_feasibility_technical_result_manifest.v1",
        "task_id": TASK_ID,
        "promotion_parent_commit": promotion_parent_commit,
        "run_id": finalized["run_id"],
        "operation_id": finalized["operation_id"],
        "external_namespace": "artifact://JointBuildGS/phase-payloads/p2-baselines/c1_c2_feasibility_pilot_v1/P2-C1-C2-FEASIBILITY-PILOT-v1/",
        "external_records": {
            "metrics": finalized["metrics"], "group_balanced_descriptive": finalized["group_balanced_descriptive"],
            "preselected_cases": finalized["preselected_cases"], "report": finalized["report"],
        },
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
