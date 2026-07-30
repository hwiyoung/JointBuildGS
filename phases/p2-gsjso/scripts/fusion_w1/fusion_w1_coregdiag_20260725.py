#!/usr/bin/env python3
"""Learning-zero diagnosis of the blocked FUS-W1 co-registration evidence.

The method is deliberately split into two commands:

``lock``
    Verify immutable inputs and write an exact-once method receipt before
    loading either point cloud.

``measure``
    Require the same script/config hashes, reuse one raw-frame point inventory
    for both transforms, and write the requested diagnostic tables/figures.

This program never writes ALS, photo, COLMAP, or learning inputs.  The
post-transform state is the rejected global diagnostic candidate and is never
published as an adopted camera pose.
"""

from __future__ import annotations

import argparse
import csv
import gc
import hashlib
import importlib.util
import json
import math
import os
import shutil
import subprocess
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np


ROOT = Path(__file__).resolve().parents[4]
DEFAULT_CONFIG = (
    ROOT / "phases/p2-gsjso/configs/fusion_w1/fusion_w1_coregdiag_20260725.json"
)
SELF_PATH = Path(__file__).resolve()


class DiagnosticError(RuntimeError):
    """Fail-closed diagnostic contract error."""


def repo_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def relative(path: str | Path) -> str:
    resolved = Path(path).resolve()
    try:
        return str(resolved.relative_to(ROOT.resolve()))
    except ValueError:
        return str(resolved)


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json_sha(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def now_kst() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: str | Path, payload: Any, *, exclusive: bool = False) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    mode = "x" if exclusive else "w"
    with target.open(mode, encoding="utf-8") as handle:
        json.dump(json_safe(payload), handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")


def json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, np.ndarray):
        return json_safe(value.tolist())
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, (np.bool_,)):
        return bool(value)
    return value


def read_csv(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(
    path: str | Path,
    rows: Sequence[Mapping[str, Any]],
    fields: Sequence[str] | None = None,
) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        ordered: list[str] = []
        seen: set[str] = set()
        for row in rows:
            for key in row:
                if key not in seen:
                    seen.add(key)
                    ordered.append(key)
        fields = ordered
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), extrasaction="raise")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    field: csv_value(row.get(field))
                    for field in fields
                }
            )


def csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (np.bool_, bool)):
        return str(bool(value)).lower()
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        number = float(value)
        return f"{number:.12g}" if math.isfinite(number) else ""
    return value


def load_config(path: str | Path) -> dict[str, Any]:
    resolved = repo_path(path).resolve()
    if resolved != DEFAULT_CONFIG.resolve():
        raise DiagnosticError("alternate diagnostic config is forbidden")
    payload = load_json(resolved)
    if payload.get("schema") != "jointbuildgs.fusion_w1.coregdiag.v1":
        raise DiagnosticError("unexpected diagnostic config schema")
    if payload.get("scope") != "learning_zero_diagnostic_only":
        raise DiagnosticError("diagnostic scope is not learning-zero")
    if payload["execution"].get("learning_forbidden") is not True:
        raise DiagnosticError("learning prohibition is not locked")
    return payload


def load_coreg_module(config: Mapping[str, Any]) -> Any:
    source = repo_path(config["inputs"]["coreg_implementation"])
    spec = importlib.util.spec_from_file_location("fusion_w1_coreg_lock1_locked", source)
    if spec is None or spec.loader is None:
        raise DiagnosticError("cannot load locked coreg implementation")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def git(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=ROOT, text=True, stderr=subprocess.STDOUT
    ).strip()


def active_learning_processes() -> list[str]:
    output = subprocess.check_output(
        ["ps", "-eo", "pid=,args="], text=True, stderr=subprocess.STDOUT
    )
    patterns = (
        "train.py",
        "p1w_train",
        "gs_train",
        "gaussian_splatting/train",
        "gaussian-splatting/train",
        "full_eval.py",
    )
    matches: list[str] = []
    for line in output.splitlines():
        lowered = line.lower()
        if any(pattern in lowered for pattern in patterns):
            matches.append(line.strip())
    return matches


def verify_inputs(config: Mapping[str, Any], *, include_clouds: bool) -> dict[str, str]:
    observed: dict[str, str] = {}
    cloud_paths = {
        config["inputs"]["source_als_laz"],
        config["inputs"]["materialized_als_npz"],
        config["inputs"]["photo_dense_npz"],
    }
    for raw_path, expected in config["input_sha256"].items():
        if not include_clouds and raw_path in cloud_paths:
            continue
        path = repo_path(raw_path)
        if not path.is_file():
            raise DiagnosticError(f"locked input missing: {raw_path}")
        actual = sha256_file(path)
        if actual != expected:
            raise DiagnosticError(f"locked input hash mismatch: {raw_path}")
        observed[raw_path] = actual
    return observed


def output_paths(config: Mapping[str, Any]) -> dict[str, Path]:
    output = config["outputs"]
    run_dir = repo_path(output["run_dir"])
    return {
        key: run_dir / value
        for key, value in output.items()
        if key != "run_dir"
    }


def lock_method(config: Mapping[str, Any]) -> dict[str, Any]:
    if git("rev-parse", "--abbrev-ref", "HEAD") != config["branch"]:
        raise DiagnosticError("wrong branch for diagnostic lock")
    head = git("rev-parse", "HEAD")
    parent = git("rev-parse", "HEAD^")
    if parent != config["base_head"]:
        raise DiagnosticError(f"diagnostic implementation parent drift: {parent}")
    status = git("status", "--porcelain", "--untracked-files=all")
    if status:
        raise DiagnosticError("worktree must be clean before method lock")
    implementation_sha256: dict[str, str] = {}
    for logical in config["implementation_files"]:
        path = repo_path(logical)
        if git("ls-files", "--error-unmatch", logical) != logical:
            raise DiagnosticError(f"implementation is not tracked: {logical}")
        head_blob = subprocess.check_output(
            ["git", "show", f"HEAD:{logical}"], cwd=ROOT
        )
        if head_blob != path.read_bytes():
            raise DiagnosticError(f"implementation differs from HEAD: {logical}")
        implementation_sha256[logical] = sha256_file(path)
    running = active_learning_processes()
    if running:
        raise DiagnosticError(f"active learning-like process found: {running}")
    observed = verify_inputs(config, include_clouds=False)
    paths = output_paths(config)
    method_lock = paths["method_lock"]
    if method_lock.exists():
        raise DiagnosticError(f"exact-once method lock exists: {relative(method_lock)}")
    for key, path in paths.items():
        if key != "method_lock" and path.exists():
            raise DiagnosticError(f"diagnostic output exists before lock: {relative(path)}")
    receipt = {
        "schema": "jointbuildgs.fusion_w1.coregdiag_method_lock.v1",
        "task_id": config["task_id"],
        "locked_at": now_kst(),
        "branch": config["branch"],
        "base_head": parent,
        "predecessor_head": parent,
        "implementation_head": head,
        "implementation_sha256": implementation_sha256,
        "config_path": relative(DEFAULT_CONFIG),
        "config_sha256": sha256_file(DEFAULT_CONFIG),
        "script_path": relative(SELF_PATH),
        "script_sha256": sha256_file(SELF_PATH),
        "method_sha256": canonical_json_sha(
            {
                "population": config["population"],
                "sampling": config["sampling"],
                "states": config["states"],
                "correspondence": config["correspondence"],
                "correspondence_capability": config["correspondence_capability"],
                "low_support": config["low_support"],
                "tail": config["tail"],
                "offsets": config["offsets"],
            }
        ),
        "small_input_sha256": observed,
        "point_clouds_opened": 0,
        "new_residuals_read": 0,
        "learning_runs_started": 0,
        "source_data_modified": False,
        "result_dependent_retuning_forbidden": True,
    }
    write_json(method_lock, receipt, exclusive=True)
    return receipt


def verify_method_lock(config: Mapping[str, Any]) -> dict[str, Any]:
    path = output_paths(config)["method_lock"]
    if not path.is_file():
        raise DiagnosticError("method lock is missing; run lock first")
    receipt = load_json(path)
    if receipt.get("schema") != "jointbuildgs.fusion_w1.coregdiag_method_lock.v1":
        raise DiagnosticError("unexpected method-lock schema")
    if receipt.get("predecessor_head") != config["base_head"]:
        raise DiagnosticError("method lock predecessor HEAD mismatch")
    if receipt.get("config_sha256") != sha256_file(DEFAULT_CONFIG):
        raise DiagnosticError("diagnostic config changed after method lock")
    if receipt.get("script_sha256") != sha256_file(SELF_PATH):
        raise DiagnosticError("diagnostic script changed after method lock")
    if set(receipt.get("implementation_sha256", {})) != set(
        config["implementation_files"]
    ):
        raise DiagnosticError("method lock implementation inventory mismatch")
    for logical, expected in receipt.get("implementation_sha256", {}).items():
        path = repo_path(logical)
        if not path.is_file() or sha256_file(path) != expected:
            raise DiagnosticError(f"locked implementation changed: {logical}")
    if int(receipt.get("point_clouds_opened", -1)) != 0:
        raise DiagnosticError("method lock does not precede point-cloud opening")
    return receipt


def nearest_rank(values: Sequence[float | int], q: float) -> float:
    array = np.sort(np.asarray(values, dtype=np.float64))
    if len(array) == 0:
        raise DiagnosticError("nearest-rank quantile requires non-empty values")
    if not 0.0 <= float(q) <= 1.0:
        raise DiagnosticError("nearest-rank q outside [0,1]")
    rank = max(1, int(math.ceil(float(q) * len(array))))
    return float(array[rank - 1])


def finite_quantile(values: np.ndarray, q: float) -> float | None:
    array = np.asarray(values, dtype=np.float64)
    array = array[np.isfinite(array)]
    return float(np.quantile(array, q)) if len(array) else None


def median_or_none(values: np.ndarray) -> float | None:
    return finite_quantile(values, 0.5)


def p90_or_none(values: np.ndarray) -> float | None:
    return finite_quantile(values, 0.9)


@dataclass
class DiagnosticGroup:
    building_id: str
    tier: str
    surface: str
    fixed: np.ndarray
    moving: np.ndarray
    fixed_normals: np.ndarray
    moving_normals: np.ndarray
    block_id: str = "raw_dense_no_block_provenance"


def load_population(config: Mapping[str, Any]) -> tuple[list[dict[str, str]], dict[str, dict[str, str]]]:
    targets = read_csv(repo_path(config["inputs"]["targets_csv"]))
    ladder = read_csv(repo_path(config["inputs"]["boundary_ladder_csv"]))
    expected = int(config["population"]["expected_buildings"])
    target_ids = [row["building_id"] for row in targets]
    ladder_ids = [row["building_id"] for row in ladder]
    if len(targets) != expected or len(set(target_ids)) != expected:
        raise DiagnosticError("targets are not exactly 178 unique buildings")
    if len(ladder) != expected or len(set(ladder_ids)) != expected:
        raise DiagnosticError("boundary ladder is not exactly 178 unique buildings")
    if set(target_ids) != set(ladder_ids):
        raise DiagnosticError("target/boundary ID join is not one-to-one complete")
    by_id = {row["building_id"]: row for row in ladder}
    cell_to_tier = {
        "cell_1_assembled": "surface",
        "cell_2_anchored": "height",
        "cell_3_outline_only": "outline",
    }
    for row in targets:
        ladder_row = by_id[row["building_id"]]
        tier = cell_to_tier.get(ladder_row["cell_label"])
        if tier != row["tier"]:
            raise DiagnosticError(f"tier join mismatch for {row['building_id']}")
    return targets, by_id


def build_inventory(
    config: Mapping[str, Any],
    coreg: Any,
    targets: Sequence[Mapping[str, str]],
) -> tuple[
    dict[str, list[DiagnosticGroup]],
    dict[str, dict[str, Any]],
    dict[str, Any],
]:
    materialized = repo_path(config["inputs"]["materialized_als_npz"])
    receipt = load_json(repo_path(config["inputs"]["materialized_als_receipt"]))
    if receipt.get("output_sha256") != sha256_file(materialized):
        raise DiagnosticError("materialized ALS receipt mismatch")
    if receipt.get("source_sha256") != config["input_sha256"][
        config["inputs"]["source_als_laz"]
    ]:
        raise DiagnosticError("materialized ALS source lineage mismatch")
    with np.load(materialized) as payload:
        als_xyz = np.asarray(payload["xyz"], dtype=np.float64)
        als_cls = np.asarray(payload["classification"], dtype=np.uint8)
    dense_path = repo_path(config["inputs"]["photo_dense_npz"])
    with np.load(dense_path) as payload:
        dense_xyz = np.asarray(payload["P_utm"], dtype=np.float64)
    als_index = coreg.XIndex(als_xyz, als_cls)
    dense_index = coreg.XIndex(dense_xyz)
    del als_xyz, als_cls, dense_xyz
    gc.collect()

    footprints = coreg._load_footprints(config["inputs"]["footprints_geojson"])
    sampling = config["sampling"]
    groups: dict[str, list[DiagnosticGroup]] = defaultdict(list)
    inventory: dict[str, dict[str, Any]] = {}
    ground_class = 2
    building_class = 6
    minimum = int(sampling["minimum_points_per_building_surface"])
    for position, target in enumerate(targets, start=1):
        bid = target["building_id"]
        polygon = footprints.get(bid)
        if polygon is None:
            raise DiagnosticError(f"target footprint missing: {bid}")
        roof_geometry = polygon.buffer(-float(sampling["roof_inner_buffer_m"]))
        if roof_geometry.is_empty:
            roof_geometry = polygon
        definitions = {
            "roof": roof_geometry,
            "ground": polygon.buffer(
                float(sampling["ground_outer_buffer_m"])
            ).difference(
                polygon.buffer(float(sampling["ground_inner_exclusion_buffer_m"]))
            ),
        }
        row: dict[str, Any] = {
            "building_id": bid,
            "tier": target["tier"],
            "cohort": target["cohort"],
            "processing_order": int(target["processing_order"]),
            "source_cell_label": target["source_cell_label"],
        }
        for surface, geometry in definitions.items():
            class_value = building_class if surface == "roof" else ground_class
            fixed = als_index.query_bounds(geometry.bounds, class_value)
            fixed = fixed[coreg.polygon_mask(geometry, fixed)]
            moving = dense_index.query_bounds(geometry.bounds)
            moving = moving[coreg.polygon_mask(geometry, moving)]
            row[f"{surface}_fixed_crop_n"] = len(fixed)
            row[f"{surface}_moving_crop_n"] = len(moving)
            if len(fixed) and len(moving):
                if surface == "roof":
                    low, high = np.quantile(fixed[:, 2], [0.01, 0.99])
                    margin = float(sampling["dense_roof_vertical_margin_m"])
                else:
                    low, high = np.quantile(fixed[:, 2], [0.02, 0.98])
                    margin = float(sampling["dense_ground_vertical_margin_m"])
                moving = moving[
                    (moving[:, 2] >= low - margin)
                    & (moving[:, 2] <= high + margin)
                ]
            fixed = coreg.deterministic_voxel(
                fixed,
                float(sampling["voxel_m"]),
                int(sampling["maximum_points_per_building_surface"]),
            )
            moving = coreg.deterministic_voxel(
                moving,
                float(sampling["voxel_m"]),
                int(sampling["maximum_points_per_building_surface"]),
            )
            row[f"{surface}_fixed_voxel_n"] = len(fixed)
            row[f"{surface}_moving_voxel_n"] = len(moving)
            if len(fixed) >= minimum:
                fixed_normals, fixed_valid = coreg.estimate_normals(
                    fixed,
                    int(sampling["normal_knn"]),
                    float(sampling["normal_radius_m"]),
                    int(sampling["minimum_normal_neighbors"]),
                    float(sampling["maximum_surface_variation"]),
                )
                fixed = fixed[fixed_valid]
                fixed_normals = fixed_normals[fixed_valid]
            else:
                fixed = np.empty((0, 3), dtype=np.float64)
                fixed_normals = np.empty((0, 3), dtype=np.float64)
            if len(moving) >= minimum:
                moving_normals, moving_valid = coreg.estimate_normals(
                    moving,
                    int(sampling["normal_knn"]),
                    float(sampling["normal_radius_m"]),
                    int(sampling["minimum_normal_neighbors"]),
                    float(sampling["maximum_surface_variation"]),
                )
                moving = moving[moving_valid]
                moving_normals = moving_normals[moving_valid]
            else:
                moving = np.empty((0, 3), dtype=np.float64)
                moving_normals = np.empty((0, 3), dtype=np.float64)
            row[f"{surface}_fixed_valid_n"] = len(fixed)
            row[f"{surface}_moving_valid_n"] = len(moving)
            usable = len(fixed) >= minimum and len(moving) >= minimum
            row[f"{surface}_usable"] = usable
            if usable:
                groups[bid].append(
                    DiagnosticGroup(
                        building_id=bid,
                        tier=target["tier"],
                        surface=surface,
                        fixed=fixed,
                        moving=moving,
                        fixed_normals=fixed_normals,
                        moving_normals=moving_normals,
                    )
                )
        row["usable_surface_count"] = len(groups[bid])
        row["inventory_status"] = (
            "roof_and_ground"
            if len(groups[bid]) == 2
            else "one_surface"
            if len(groups[bid]) == 1
            else "no_usable_surface"
        )
        inventory[bid] = row
        if position % 20 == 0 or position == len(targets):
            print(f"[inventory] {position}/{len(targets)} buildings", flush=True)
    audit = {
        "target_count": len(targets),
        "group_count": sum(len(value) for value in groups.values()),
        "building_with_group_count": sum(bool(groups[row["building_id"]]) for row in targets),
        "source_als_sha256": receipt["source_sha256"],
        "materialized_als_sha256": receipt["output_sha256"],
        "photo_dense_sha256": sha256_file(dense_path),
        "inventory_reused_across_states": True,
    }
    return dict(groups), inventory, {"footprints": footprints, "audit": audit}


def transform_points(points: np.ndarray, matrix: np.ndarray, pivot: np.ndarray) -> np.ndarray:
    local = np.asarray(points, dtype=np.float64) - pivot
    return (matrix[:3, :3] @ local.T).T + matrix[:3, 3] + pivot


def transform_normals(normals: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    return (matrix[:3, :3] @ np.asarray(normals, dtype=np.float64).T).T


def deterministic_indices(length: int, cap: int) -> np.ndarray:
    if length <= 0:
        return np.empty(0, dtype=np.int64)
    if length <= cap:
        return np.arange(length, dtype=np.int64)
    return np.linspace(0, length - 1, cap, dtype=np.int64)


def boundary_distance(polygon: Any, xy: np.ndarray) -> np.ndarray:
    if len(xy) == 0:
        return np.empty(0, dtype=np.float64)
    try:
        from shapely import distance, points

        return np.asarray(distance(points(xy[:, 0], xy[:, 1]), polygon.boundary))
    except (ImportError, TypeError):
        from shapely.geometry import Point

        return np.asarray(
            [polygon.boundary.distance(Point(float(x), float(y))) for x, y in xy],
            dtype=np.float64,
        )


def proxy_categories(
    config: Mapping[str, Any],
    polygon: Any,
    surface: str,
    photo_xyz: np.ndarray,
    als_xyz: np.ndarray,
) -> np.ndarray:
    count = max(len(photo_xyz), len(als_xyz))
    if count == 0:
        return np.empty(0, dtype=object)
    if surface == "roof":
        location = photo_xyz if len(photo_xyz) else als_xyz
        distances = boundary_distance(polygon, location[:, :2])
        threshold = float(config["tail"]["roof_boundary_distance_m"])
        return np.where(
            distances <= threshold,
            "roof_edge_or_facade_proxy",
            "roof_interior_class6_proxy",
        ).astype(object)
    if len(photo_xyz) and len(als_xyz):
        dz = photo_xyz[:, 2] - als_xyz[:, 2]
        above = float(config["tail"]["above_ground_clutter_dz_m"])
        below = float(config["tail"]["below_ground_or_occlusion_dz_m"])
        categories = np.full(len(dz), "ground_class2_proxy", dtype=object)
        categories[dz > above] = (
            "above_ground_vegetation_or_moving_clutter_proxy"
        )
        categories[dz < below] = "below_ground_or_occlusion_proxy"
        return categories
    return np.full(count, "ground_unmatched_unresolved_proxy", dtype=object)


def add_tail_counts(
    counter: Counter[tuple[str, ...]],
    *,
    source_population: str,
    state: str,
    building_id: str,
    population_role: str,
    tier: str,
    surface: str,
    direction: str,
    tail_kind: str,
    capture_block: str,
    categories: np.ndarray,
) -> None:
    for category, count in zip(*np.unique(categories.astype(str), return_counts=True)):
        counter[
            (
                source_population,
                state,
                building_id,
                population_role,
                tier,
                surface,
                direction,
                tail_kind,
                capture_block,
                str(category),
            )
        ] += int(count)


def make_samples(
    *,
    building_id: str,
    state: str,
    tier: str,
    surface: str,
    direction: str,
    tail_kind: str,
    categories: np.ndarray,
    photo_xyz: np.ndarray,
    als_xyz: np.ndarray,
    cap: int,
) -> list[dict[str, Any]]:
    count = len(categories)
    indices = deterministic_indices(count, cap)
    output: list[dict[str, Any]] = []
    for index in indices:
        photo = photo_xyz[index] if len(photo_xyz) else np.array([np.nan] * 3)
        als = als_xyz[index] if len(als_xyz) else np.array([np.nan] * 3)
        location = photo if np.all(np.isfinite(photo)) else als
        output.append(
            {
                "building_id": building_id,
                "state": state,
                "tier": tier,
                "surface": surface,
                "direction": direction,
                "tail_kind": tail_kind,
                "category": str(categories[index]),
                "x": float(location[0]),
                "y": float(location[1]),
                "photo_x": float(photo[0]),
                "photo_y": float(photo[1]),
                "als_x": float(als[0]),
                "als_y": float(als[1]),
            }
        )
    return output


def evaluate_building(
    config: Mapping[str, Any],
    groups: Sequence[Any],
    matrix: np.ndarray,
    state: str,
    polygon: Any,
    *,
    source_population: str,
    tier: str,
    population_role: str,
) -> tuple[
    dict[str, Any],
    dict[str, Any],
    Counter[tuple[str, ...]],
    Counter[tuple[str, ...]],
    list[dict[str, Any]],
]:
    from scipy.spatial import cKDTree

    radius = float(config["correspondence"]["radius_m"])
    pivot = np.asarray(config["states"]["rotation_pivot_global_m"], dtype=np.float64)
    batches: list[dict[str, Any]] = []
    for group in groups:
        moved = transform_points(group.moving, matrix, pivot)
        moved_normals = transform_normals(group.moving_normals, matrix)
        fixed_tree = cKDTree(group.fixed)
        f_distance, f_index = fixed_tree.query(moved, k=1)
        f_match = f_distance <= radius
        f_photo = moved[f_match]
        f_als = group.fixed[f_index[f_match]]
        f_displacement = f_photo - f_als
        f_normals = group.fixed_normals[f_index[f_match]]
        f_signed = np.einsum("ij,ij->i", f_normals, f_displacement)
        batches.append(
            {
                "surface": group.surface,
                "direction": "photo_to_als",
                "block_id": getattr(group, "block_id", "raw_dense_no_block_provenance"),
                "matched": f_match,
                "total": len(f_match),
                "photo": f_photo,
                "als": f_als,
                "displacement": f_displacement,
                "normals": f_normals,
                "signed": f_signed,
                "unmatched_photo": moved[~f_match],
                "unmatched_als": group.fixed[f_index[~f_match]],
            }
        )

        moving_tree = cKDTree(moved)
        r_distance, r_index = moving_tree.query(group.fixed, k=1)
        r_match = r_distance <= radius
        r_photo = moved[r_index[r_match]]
        r_als = group.fixed[r_match]
        r_displacement = r_photo - r_als
        r_normals = moved_normals[r_index[r_match]]
        r_signed = np.einsum("ij,ij->i", r_normals, r_displacement)
        batches.append(
            {
                "surface": group.surface,
                "direction": "als_to_photo",
                "block_id": getattr(group, "block_id", "raw_dense_no_block_provenance"),
                "matched": r_match,
                "total": len(r_match),
                "photo": r_photo,
                "als": r_als,
                "displacement": r_displacement,
                "normals": r_normals,
                "signed": r_signed,
                "unmatched_photo": moved[r_index[~r_match]],
                "unmatched_als": group.fixed[~r_match],
            }
        )

    matched_parts = [np.abs(batch["signed"]) for batch in batches if len(batch["signed"])]
    matched_abs = (
        np.concatenate(matched_parts)
        if matched_parts
        else np.empty(0, dtype=np.float64)
    )
    matched_p90 = p90_or_none(matched_abs)
    censored_parts: list[np.ndarray] = []
    for batch in batches:
        values = np.full(batch["total"], radius, dtype=np.float64)
        values[batch["matched"]] = np.abs(batch["signed"])
        censored_parts.append(values)
    censored_abs = (
        np.concatenate(censored_parts)
        if censored_parts
        else np.empty(0, dtype=np.float64)
    )

    forward = [batch for batch in batches if batch["direction"] == "photo_to_als"]
    reverse = [batch for batch in batches if batch["direction"] == "als_to_photo"]
    forward_matches = sum(int(np.sum(batch["matched"])) for batch in forward)
    reverse_matches = sum(int(np.sum(batch["matched"])) for batch in reverse)
    forward_total = sum(int(batch["total"]) for batch in forward)
    reverse_total = sum(int(batch["total"]) for batch in reverse)
    forward_support = forward_matches / forward_total if forward_total else None
    reverse_support = reverse_matches / reverse_total if reverse_total else None
    support = (
        min(forward_support, reverse_support)
        if forward_support is not None and reverse_support is not None
        else None
    )

    metric: dict[str, Any] = {
        "surface_count": len({batch["surface"] for batch in batches}),
        "forward_matches_n": forward_matches,
        "forward_total_n": forward_total,
        "reverse_matches_n": reverse_matches,
        "reverse_total_n": reverse_total,
        "pooled_matched_observations_n": forward_matches + reverse_matches,
        "correspondence_n": min(forward_matches, reverse_matches),
        "matched_median_m": median_or_none(matched_abs),
        "matched_p90_m": matched_p90,
        "censored_median_m": median_or_none(censored_abs),
        "censored_p90_m": p90_or_none(censored_abs),
        "forward_support": forward_support,
        "reverse_support": reverse_support,
        "bidirectional_support": support,
        "censor_radius_m": radius,
    }
    for surface in ("roof", "ground"):
        surface_batches = [batch for batch in batches if batch["surface"] == surface]
        surface_matched = [
            np.abs(batch["signed"]) for batch in surface_batches if len(batch["signed"])
        ]
        surface_censored: list[np.ndarray] = []
        for batch in surface_batches:
            values = np.full(batch["total"], radius, dtype=np.float64)
            values[batch["matched"]] = np.abs(batch["signed"])
            surface_censored.append(values)
        matched_values = (
            np.concatenate(surface_matched)
            if surface_matched
            else np.empty(0, dtype=np.float64)
        )
        censored_values = (
            np.concatenate(surface_censored)
            if surface_censored
            else np.empty(0, dtype=np.float64)
        )
        metric[f"{surface}_matched_median_m"] = median_or_none(matched_values)
        metric[f"{surface}_matched_p90_m"] = p90_or_none(matched_values)
        metric[f"{surface}_censored_median_m"] = median_or_none(censored_values)
        metric[f"{surface}_censored_p90_m"] = p90_or_none(censored_values)

    stratum_medians: list[float] = []
    for surface in ("roof", "ground"):
        for direction in ("photo_to_als", "als_to_photo"):
            values = [
                np.abs(batch["signed"])
                for batch in batches
                if batch["surface"] == surface
                and batch["direction"] == direction
                and len(batch["signed"])
            ]
            if values:
                stratum_medians.append(float(np.median(np.concatenate(values))))
    metric["residual_strata_observed_n"] = len(stratum_medians)
    metric["all_four_residual_strata_observed"] = len(stratum_medians) == 4
    metric["available_strata_equal_weight_median_m"] = (
        float(np.median(stratum_medians)) if stratum_medians else None
    )

    displacements = [
        batch["displacement"] for batch in batches if len(batch["displacement"])
    ]
    normals = [batch["normals"] for batch in batches if len(batch["normals"])]
    if displacements:
        displacement = np.vstack(displacements)
        normal = np.vstack(normals)
        r_horizontal = normal[:, 0] * displacement[:, 0] + normal[:, 1] * displacement[:, 1]
        r_vertical = normal[:, 2] * displacement[:, 2]
        offset: dict[str, Any] = {
            "matched_pair_n": len(displacement),
            "median_dE_m": float(np.median(displacement[:, 0])),
            "median_dN_m": float(np.median(displacement[:, 1])),
            "median_dZ_m": float(np.median(displacement[:, 2])),
            "horizontal_median_vector_norm_m": float(
                np.hypot(
                    np.median(displacement[:, 0]),
                    np.median(displacement[:, 1]),
                )
            ),
            "median_r_horizontal_m": float(np.median(r_horizontal)),
            "median_r_vertical_m": float(np.median(r_vertical)),
            "median_r_total_m": float(np.median(r_horizontal + r_vertical)),
        }
    else:
        offset = {
            "matched_pair_n": 0,
            "median_dE_m": None,
            "median_dN_m": None,
            "median_dZ_m": None,
            "horizontal_median_vector_norm_m": None,
            "median_r_horizontal_m": None,
            "median_r_vertical_m": None,
            "median_r_total_m": None,
        }
    surface_dz: dict[str, float | None] = {}
    for surface in ("roof", "ground"):
        parts = [
            batch["displacement"][:, 2]
            for batch in batches
            if batch["surface"] == surface and len(batch["displacement"])
        ]
        surface_dz[surface] = (
            float(np.median(np.concatenate(parts))) if parts else None
        )
        offset[f"{surface}_median_dZ_m"] = surface_dz[surface]
    if surface_dz["roof"] is not None and surface_dz["ground"] is not None:
        offset["roof_ground_common_dZ_m"] = (
            float(surface_dz["roof"]) + float(surface_dz["ground"])
        ) / 2.0
        offset["roof_minus_ground_dZ_m"] = (
            float(surface_dz["roof"]) - float(surface_dz["ground"])
        )
    else:
        offset["roof_ground_common_dZ_m"] = None
        offset["roof_minus_ground_dZ_m"] = None
    stratum_component_medians: dict[str, list[float]] = {
        "dE": [],
        "dN": [],
        "dZ": [],
    }
    observed_strata = 0
    for surface in ("roof", "ground"):
        for direction in ("photo_to_als", "als_to_photo"):
            label = f"{surface}_{direction}"
            selected = [
                batch
                for batch in batches
                if batch["surface"] == surface and batch["direction"] == direction
            ]
            matched_n = sum(int(np.sum(batch["matched"])) for batch in selected)
            total_n = sum(int(batch["total"]) for batch in selected)
            parts = [
                batch["displacement"]
                for batch in selected
                if len(batch["displacement"])
            ]
            values = np.vstack(parts) if parts else np.empty((0, 3), dtype=np.float64)
            offset[f"{label}_matched_n"] = matched_n
            offset[f"{label}_total_n"] = total_n
            offset[f"{label}_support"] = matched_n / total_n if total_n else None
            for index, component in enumerate(("dE", "dN", "dZ")):
                median = float(np.median(values[:, index])) if len(values) else None
                offset[f"{label}_median_{component}_m"] = median
                if median is not None:
                    stratum_component_medians[component].append(median)
            if len(values):
                observed_strata += 1
    offset["available_strata_observed_n"] = observed_strata
    offset["all_four_strata_observed"] = observed_strata == 4
    for component in ("dE", "dN", "dZ"):
        values = stratum_component_medians[component]
        offset[f"available_strata_equal_weight_median_{component}_m"] = (
            float(np.median(values)) if values else None
        )
    reliability_floor = int(config["offsets"]["reliability_floor_matches_per_direction"])
    reliability_fraction = float(
        config["offsets"]["reliability_min_fraction_per_direction"]
    )
    forward_needed = max(reliability_floor, int(math.ceil(reliability_fraction * forward_total)))
    reverse_needed = max(reliability_floor, int(math.ceil(reliability_fraction * reverse_total)))
    offset["forward_reliable_needed_n"] = forward_needed
    offset["reverse_reliable_needed_n"] = reverse_needed
    offset["offset_support_reliable"] = (
        forward_matches >= forward_needed and reverse_matches >= reverse_needed
    )

    counter: Counter[tuple[str, ...]] = Counter()
    exposure_counter: Counter[tuple[str, ...]] = Counter()
    samples: list[dict[str, Any]] = []
    for batch in batches:
        exposure_counter[
            (
                    source_population,
                    state,
                    groups[0].building_id if groups else "",
                    population_role,
                    tier,
                    batch["surface"],
                batch["direction"],
                batch["block_id"],
            )
        ] += int(batch["total"])
    if matched_p90 is not None:
        for batch in batches:
            tail_mask = np.abs(batch["signed"]) > float(matched_p90)
            tail_photo = batch["photo"][tail_mask]
            tail_als = batch["als"][tail_mask]
            categories = proxy_categories(
                config, polygon, batch["surface"], tail_photo, tail_als
            )
            if len(categories):
                add_tail_counts(
                    counter,
                    source_population=source_population,
                    state=state,
                    building_id=groups[0].building_id if groups else "",
                    population_role=population_role,
                    tier=tier,
                    surface=batch["surface"],
                    direction=batch["direction"],
                    tail_kind="matched_above_building_state_p90",
                    capture_block=batch["block_id"],
                    categories=categories,
                )
                samples.extend(
                    make_samples(
                        building_id=groups[0].building_id if groups else "",
                        state=state,
                        tier=tier,
                        surface=batch["surface"],
                        direction=batch["direction"],
                        tail_kind="matched_above_building_state_p90",
                        categories=categories,
                        photo_xyz=tail_photo,
                        als_xyz=tail_als,
                        cap=150,
                    )
                )
    for batch in batches:
        if len(batch["unmatched_photo"]):
            categories = proxy_categories(
                config,
                polygon,
                batch["surface"],
                batch["unmatched_photo"],
                batch["unmatched_als"],
            )
            add_tail_counts(
                counter,
                source_population=source_population,
                state=state,
                building_id=groups[0].building_id if groups else "",
                population_role=population_role,
                tier=tier,
                surface=batch["surface"],
                direction=batch["direction"],
                tail_kind="unmatched_censored_at_0p35m",
                capture_block=batch["block_id"],
                categories=categories,
            )
            samples.extend(
                make_samples(
                    building_id=groups[0].building_id if groups else "",
                    state=state,
                    tier=tier,
                    surface=batch["surface"],
                    direction=batch["direction"],
                    tail_kind="unmatched_censored_at_0p35m",
                    categories=categories,
                    photo_xyz=batch["unmatched_photo"],
                    als_xyz=batch["unmatched_als"],
                    cap=100,
                )
            )
    metric["matched_tail_n"] = sum(
        count for key, count in counter.items() if key[7].startswith("matched_")
    )
    metric["censored_unmatched_n"] = sum(
        count for key, count in counter.items() if key[7].startswith("unmatched_")
    )
    return metric, offset, counter, exposure_counter, samples


def fisher_exact(table: np.ndarray) -> tuple[float | None, float | None]:
    try:
        from scipy.stats import fisher_exact as scipy_fisher_exact

        result = scipy_fisher_exact(table, alternative="two-sided")
        if hasattr(result, "statistic"):
            return float(result.statistic), float(result.pvalue)
        return float(result[0]), float(result[1])
    except (ImportError, ValueError):
        return None, None


def add_prefixed(target: dict[str, Any], prefix: str, source: Mapping[str, Any]) -> None:
    for key, value in source.items():
        target[f"{prefix}_{key}"] = value


def add_paired_deltas(
    target: dict[str, Any],
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    keys: Iterable[str],
) -> None:
    for key in keys:
        left = before.get(key)
        right = after.get(key)
        target[f"delta_after_minus_before_{key}"] = (
            float(right) - float(left)
            if left is not None and right is not None
            else None
        )


def tier_summary_rows(
    building_rows: Sequence[Mapping[str, Any]],
    n_threshold: int,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for state in ("before", "after"):
        for tier in ("all", "surface", "height", "outline"):
            rows = [
                row
                for row in building_rows
                if tier == "all" or row["tier"] == tier
            ]
            capable = [row for row in rows if bool(row["correspondence_capable"])]
            observed = [
                row
                for row in capable
                if row[f"{state}_matched_median_m"] is not None
            ]
            le = [
                row
                for row in observed
                if float(row[f"{state}_matched_median_m"]) <= 0.3
            ]
            values = np.asarray(
                [float(row[f"{state}_matched_median_m"]) for row in observed],
                dtype=np.float64,
            )
            p90_values = np.asarray(
                [
                    float(row[f"{state}_matched_p90_m"])
                    for row in capable
                    if row[f"{state}_matched_p90_m"] is not None
                ],
                dtype=np.float64,
            )
            censored_medians = np.asarray(
                [
                    float(row[f"{state}_censored_median_m"])
                    for row in capable
                    if row[f"{state}_censored_median_m"] is not None
                ],
                dtype=np.float64,
            )
            censored_p90_values = np.asarray(
                [
                    float(row[f"{state}_censored_p90_m"])
                    for row in capable
                    if row[f"{state}_censored_p90_m"] is not None
                ],
                dtype=np.float64,
            )
            n_values = np.asarray(
                [int(row[f"{state}_correspondence_n"]) for row in capable],
                dtype=np.float64,
            )
            supports = np.asarray(
                [
                    float(row[f"{state}_bidirectional_support"])
                    for row in capable
                    if row[f"{state}_bidirectional_support"] is not None
                ],
                dtype=np.float64,
            )
            output.append(
                {
                    "state": (
                        "identity_before"
                        if state == "before"
                        else "diagnostic_global_candidate_not_adopted"
                    ),
                    "tier": tier,
                    "population_n": len(rows),
                    "correspondence_capable_n": len(capable),
                    "matched_median_observed_n": len(observed),
                    "matched_median_missing_n": len(capable) - len(observed),
                    "matched_median_le_0p3_n": len(le),
                    "matched_median_le_0p3_fraction": (
                        len(le) / len(capable) if capable else None
                    ),
                    "building_balanced_median_of_matched_medians_m": (
                        float(np.median(values)) if len(values) else None
                    ),
                    "building_balanced_p90_of_matched_medians_m": (
                        float(np.quantile(values, 0.9)) if len(values) else None
                    ),
                    "building_balanced_median_of_matched_p90_m": (
                        float(np.median(p90_values)) if len(p90_values) else None
                    ),
                    "building_balanced_median_of_censored_medians_m": (
                        float(np.median(censored_medians))
                        if len(censored_medians)
                        else None
                    ),
                    "building_balanced_median_of_censored_p90_m": (
                        float(np.median(censored_p90_values))
                        if len(censored_p90_values)
                        else None
                    ),
                    "median_correspondence_n": (
                        float(np.median(n_values)) if len(n_values) else None
                    ),
                    "median_bidirectional_support": (
                        float(np.median(supports)) if len(supports) else None
                    ),
                    "n_threshold": n_threshold,
                    "numeric_reference_m": 0.3,
                    "p90_support_used_for_gate": False,
                }
            )
    return output


def confusion_rows(
    building_rows: Sequence[dict[str, Any]],
    low_support_cutoff: float,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    capable = [row for row in building_rows if bool(row["correspondence_capable"])]
    for row in building_rows:
        support = row.get("before_bidirectional_support")
        row["low_support"] = (
            support is not None and float(support) <= low_support_cutoff
            if bool(row["correspondence_capable"])
            else None
        )
        row["support_classification"] = (
            "capable_low_support"
            if row["low_support"] is True
            else "capable_not_low_support"
            if row["low_support"] is False
            else "not_applicable_incapable"
        )
        row["tier_group"] = (
            "height_or_outline" if row["tier"] in {"height", "outline"} else "surface"
        )
    counts = Counter(
        (row["tier_group"], bool(row["low_support"])) for row in capable
    )
    table = np.asarray(
        [
            [
                counts[("height_or_outline", True)],
                counts[("height_or_outline", False)],
            ],
            [
                counts[("surface", True)],
                counts[("surface", False)],
            ],
        ],
        dtype=np.int64,
    )
    odds, pvalue = fisher_exact(table)
    rows: list[dict[str, Any]] = []
    for tier_group in ("height_or_outline", "surface"):
        row_total = counts[(tier_group, True)] + counts[(tier_group, False)]
        for low in (True, False):
            count = counts[(tier_group, low)]
            rows.append(
                {
                    "tier_group": tier_group,
                    "low_support": low,
                    "count": count,
                    "row_fraction": count / row_total if row_total else None,
                    "capable_population_n": len(capable),
                    "support_cutoff_q25": low_support_cutoff,
                    "odds_ratio_height_outline_vs_surface": odds,
                    "fisher_two_sided_p": pvalue,
                    "test_role": "auxiliary_observation_only",
                }
            )
    summary = {
        "table": table.tolist(),
        "odds_ratio": odds,
        "pvalue": pvalue,
        "capable_population_n": len(capable),
        "low_support_cutoff_q25": low_support_cutoff,
        "low_support_n": sum(bool(row["low_support"]) for row in capable),
        "height_outline_low_support_n": counts[("height_or_outline", True)],
    }
    return rows, summary


def tail_rows(
    counter: Counter[tuple[str, ...]],
    exposure_counter: Counter[tuple[str, ...]],
) -> list[dict[str, Any]]:
    totals: Counter[tuple[str, str, str]] = Counter()
    direction_totals: Counter[tuple[str, str, str, str]] = Counter()
    for key, count in counter.items():
        totals[(key[0], key[1], key[7])] += count
        direction_totals[(key[0], key[1], key[6], key[7])] += count
    rows: list[dict[str, Any]] = []
    for key, count in sorted(counter.items()):
        (
            source,
            state,
            building_id,
            role,
            tier,
            surface,
            direction,
            kind,
            block,
            category,
        ) = key
        denominator = totals[(source, state, kind)]
        exposure = exposure_counter[
            (
                source,
                state,
                building_id,
                role,
                tier,
                surface,
                direction,
                block,
            )
        ]
        rows.append(
            {
                "row_type": "proxy_category_detail",
                "source_population": source,
                "state": state,
                "building_id": building_id,
                "population_role": role,
                "tier": tier,
                "surface": surface,
                "direction": direction,
                "tail_kind": kind,
                "capture_block": block,
                "proxy_category": category,
                "count": count,
                "exposure_n": exposure,
                "tail_rate_per_source_observation": (
                    count / exposure if exposure else None
                ),
                "share_within_population_state_tail_kind": (
                    count / denominator if denominator else None
                ),
                "share_within_population_state_direction_tail_kind": (
                    count / direction_totals[(source, state, direction, kind)]
                    if direction_totals[(source, state, direction, kind)]
                    else None
                ),
                "block_concentration_eligible": (
                    source == "per_view_stride16_lock2_fit_trigger"
                    and direction == "photo_to_als"
                ),
                "reverse_block_duplication_caveat": (
                    source == "per_view_stride16_lock2_fit_trigger"
                    and direction == "als_to_photo"
                ),
                "tail_threshold": (
                    "building_state_measured_matched_p90_strictly_exceeded"
                    if kind.startswith("matched_")
                    else "unmatched_censored_at_0.35m"
                ),
                "censored_value_is_measurement": False,
            }
        )
    tail_kinds = (
        "matched_above_building_state_p90",
        "unmatched_censored_at_0p35m",
    )
    for exposure_key, exposure in sorted(exposure_counter.items()):
        source, state, building_id, role, tier, surface, direction, block = exposure_key
        for kind in tail_kinds:
            count = sum(
                value
                for key, value in counter.items()
                if key[:7]
                == (
                    source,
                    state,
                    building_id,
                    role,
                    tier,
                    surface,
                    direction,
                )
                and key[7] == kind
                and key[8] == block
            )
            denominator = totals[(source, state, kind)]
            direction_denominator = direction_totals[
                (source, state, direction, kind)
            ]
            rows.append(
                {
                    "row_type": "exposure_complete_aggregate",
                    "source_population": source,
                    "state": state,
                    "building_id": building_id,
                    "population_role": role,
                    "tier": tier,
                    "surface": surface,
                    "direction": direction,
                    "tail_kind": kind,
                    "capture_block": block,
                    "proxy_category": "__all__",
                    "count": count,
                    "exposure_n": exposure,
                    "tail_rate_per_source_observation": (
                        count / exposure if exposure else None
                    ),
                    "share_within_population_state_tail_kind": (
                        count / denominator if denominator else 0.0
                    ),
                    "share_within_population_state_direction_tail_kind": (
                        count / direction_denominator
                        if direction_denominator
                        else 0.0
                    ),
                    "block_concentration_eligible": (
                        source == "per_view_stride16_lock2_fit_trigger"
                        and direction == "photo_to_als"
                    ),
                    "reverse_block_duplication_caveat": (
                        source == "per_view_stride16_lock2_fit_trigger"
                        and direction == "als_to_photo"
                    ),
                    "tail_threshold": (
                        "building_state_measured_matched_p90_strictly_exceeded"
                        if kind.startswith("matched_")
                        else "unmatched_censored_at_0.35m"
                    ),
                    "censored_value_is_measurement": False,
                }
            )
    return rows


def block_inventory_rows(
    block_audit: Mapping[str, Any],
    controls: Sequence[Mapping[str, str]],
    target_by_id: Mapping[str, Mapping[str, str]],
    expected_blocks: Sequence[str],
) -> list[dict[str, Any]]:
    observed = {
        (row["block_id"], row["building_id"], row["surface"]): row
        for row in block_audit["rows"]
    }
    rows: list[dict[str, Any]] = []
    observed_blocks = set(block_audit["blocks"])
    if not observed_blocks.issubset(set(expected_blocks)):
        raise DiagnosticError("observed capture block is outside locked inventory")
    for block in expected_blocks:
        for control in sorted(controls, key=lambda row: row["building_id"]):
            bid = control["building_id"]
            for surface in ("roof", "ground"):
                source = observed.get((block, bid, surface), {})
                rows.append(
                    {
                        "row_type": "block_inventory_coverage",
                        "source_population": "per_view_stride16_lock2_fit_trigger",
                        "state": "inventory_before_transform",
                        "building_id": bid,
                        "population_role": control["role"],
                        "tier": target_by_id[bid]["tier"],
                        "surface": surface,
                        "direction": "photo_to_als",
                        "tail_kind": "not_applicable_inventory",
                        "capture_block": block,
                        "proxy_category": "__inventory__",
                        "count": 0,
                        "exposure_n": int(source.get("moving_points", 0)),
                        "tail_rate_per_source_observation": None,
                        "share_within_population_state_tail_kind": None,
                        "share_within_population_state_direction_tail_kind": None,
                        "block_concentration_eligible": False,
                        "reverse_block_duplication_caveat": False,
                        "tail_threshold": "not_applicable",
                        "censored_value_is_measurement": False,
                        "block_group_used": bool(source.get("used", False)),
                        "observation_views": int(source.get("observation_views", 0)),
                        "moving_points_after_normal_filter": int(
                            source.get("moving_points", 0)
                        ),
                    }
                )
    return rows


def plot_geometry(ax: Any, geometry: Any, **kwargs: Any) -> None:
    geoms = list(geometry.geoms) if geometry.geom_type == "MultiPolygon" else [geometry]
    for polygon in geoms:
        x, y = polygon.exterior.xy
        ax.plot(x, y, **kwargs)


def plot_tail_plan(
    path: Path,
    footprints: Mapping[str, Any],
    samples: Sequence[Mapping[str, Any]],
    n_threshold: int,
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, ax = plt.subplots(figsize=(12, 9), dpi=160)
    for geometry in footprints.values():
        plot_geometry(ax, geometry, color="#d4d4d4", linewidth=0.35, alpha=0.8)
    palette = {
        "roof_edge_or_facade_proxy": "#C23B22",
        "roof_interior_class6_proxy": "#2474B5",
        "above_ground_vegetation_or_moving_clutter_proxy": "#7A5195",
        "below_ground_or_occlusion_proxy": "#E07A1F",
        "ground_class2_proxy": "#2A9D6F",
        "ground_unmatched_unresolved_proxy": "#777777",
    }
    after = [
        row
        for row in samples
        if row["state"] == "after"
    ]
    for category in sorted({row["category"] for row in after}):
        rows = [row for row in after if row["category"] == category]
        x = [row["x"] for row in rows]
        y = [row["y"] for row in rows]
        ax.scatter(
            x,
            y,
            s=5,
            alpha=0.55,
            linewidths=0,
            color=palette.get(category, "#555555"),
            label=f"{category} (sample n={len(rows)})",
        )
    ax.set_title("Coreg diagnostic tail correspondences — plan view")
    ax.text(
        0.0,
        1.01,
        (
            "Diagnostic global candidate (not adopted); matched > building P90 "
            f"and censored unmatched shown; capability n threshold={n_threshold}"
        ),
        transform=ax.transAxes,
        fontsize=9,
        color="#444444",
    )
    ax.set_xlabel("Easting (m), EPSG:25832 numeric frame")
    ax.set_ylabel("Northing (m), EPSG:25832 numeric frame")
    ax.set_aspect("equal", adjustable="datalim")
    ax.grid(True, color="#eeeeee", linewidth=0.5)
    ax.legend(loc="best", fontsize=7, frameon=False)
    figure.tight_layout()
    figure.savefig(path, bbox_inches="tight")
    plt.close(figure)


def plot_tail_representative(
    path: Path,
    building_id: str,
    polygon: Any,
    samples: Sequence[Mapping[str, Any]],
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, ax = plt.subplots(figsize=(10, 8), dpi=180)
    plot_geometry(ax, polygon, color="#111111", linewidth=1.5)
    after = [
        row
        for row in samples
        if row["building_id"] == building_id and row["state"] == "after"
    ]
    matched = [
        row for row in after if row["tail_kind"].startswith("matched_")
    ]
    unmatched = [
        row for row in after if row["tail_kind"].startswith("unmatched_")
    ]
    for row in matched[:600]:
        if all(
            math.isfinite(float(row[key]))
            for key in ("photo_x", "photo_y", "als_x", "als_y")
        ):
            ax.plot(
                [row["als_x"], row["photo_x"]],
                [row["als_y"], row["photo_y"]],
                color="#C23B22",
                alpha=0.25,
                linewidth=0.6,
            )
    if matched:
        ax.scatter(
            [row["photo_x"] for row in matched],
            [row["photo_y"] for row in matched],
            s=14,
            color="#C23B22",
            alpha=0.65,
            label=f"matched > building P90 (sample n={len(matched)})",
        )
    if unmatched:
        ax.scatter(
            [row["x"] for row in unmatched],
            [row["y"] for row in unmatched],
            s=17,
            marker="x",
            linewidths=0.7,
            color="#5F6B7A",
            alpha=0.6,
            label=f"unmatched, censored at 0.35 m (sample n={len(unmatched)})",
        )
    ax.set_title(f"Coreg diagnostic tail correspondences — {building_id}")
    ax.text(
        0.0,
        1.01,
        "Diagnostic global candidate (not adopted); footprint used for crop/proxy only",
        transform=ax.transAxes,
        fontsize=9,
        color="#444444",
    )
    ax.set_xlabel("Easting (m)")
    ax.set_ylabel("Northing (m)")
    ax.set_aspect("equal", adjustable="datalim")
    ax.grid(True, color="#eeeeee", linewidth=0.5)
    ax.legend(loc="best", fontsize=8, frameon=False)
    figure.tight_layout()
    figure.savefig(path, bbox_inches="tight")
    plt.close(figure)


def output_hashes(paths: Mapping[str, Path], exclude: set[str]) -> dict[str, str]:
    return {
        relative(path): sha256_file(path)
        for key, path in paths.items()
        if key not in exclude and path.is_file()
    }


def measure(config: Mapping[str, Any]) -> dict[str, Any]:
    started = time.time()
    method_lock = verify_method_lock(config)
    paths = output_paths(config)
    running = active_learning_processes()
    if running:
        raise DiagnosticError(f"active learning-like process found: {running}")
    if git("rev-parse", "--abbrev-ref", "HEAD") != config["branch"]:
        raise DiagnosticError("wrong branch for diagnostic measurement")
    if git("rev-parse", "HEAD") != method_lock["implementation_head"]:
        raise DiagnosticError("measurement HEAD differs from committed method lock")
    expected_untracked = f"?? {relative(paths['method_lock'])}"
    status_lines = [
        line
        for line in git("status", "--porcelain", "--untracked-files=all").splitlines()
        if line
    ]
    if status_lines != [expected_untracked]:
        raise DiagnosticError(
            f"unexpected worktree state before measurement: {status_lines}"
        )
    for key, path in paths.items():
        if key not in {"method_lock"} and path.exists():
            raise DiagnosticError(f"exact-once output already exists: {relative(path)}")
    start_receipt = {
        "schema": "jointbuildgs.fusion_w1.coregdiag_measurement_start.v1",
        "task_id": config["task_id"],
        "started_at": now_kst(),
        "implementation_head": method_lock["implementation_head"],
        "method_lock_sha256": sha256_file(paths["method_lock"]),
        "script_sha256": method_lock["script_sha256"],
        "config_sha256": method_lock["config_sha256"],
        "point_clouds_opened_before_claim": 0,
        "new_residuals_read_before_claim": 0,
        "learning_runs_started": 0,
    }
    try:
        write_json(paths["measurement_start"], start_receipt, exclusive=True)
    except FileExistsError as exc:
        raise DiagnosticError("measurement start was already claimed") from exc
    observed_inputs = verify_inputs(config, include_clouds=True)

    global_selection = load_json(repo_path(config["inputs"]["global_selection"]))
    block_selection = load_json(repo_path(config["inputs"]["block_selection"]))
    if (
        global_selection.get("choice") != "none"
        or global_selection.get("status") != "BLOCK_REQUIRED"
    ):
        raise DiagnosticError("global candidate disposition drift")
    if (
        block_selection.get("choice") != "none"
        or block_selection.get("status") != "BLOCKED"
    ):
        raise DiagnosticError("block candidate disposition drift")
    candidate = np.asarray(config["states"]["after"]["matrix"], dtype=np.float64)
    observed_candidate = np.asarray(
        global_selection["block_base_photo_to_als_global_pivot_matrix"],
        dtype=np.float64,
    )
    if not np.array_equal(candidate, observed_candidate):
        raise DiagnosticError("diagnostic candidate matrix differs from lock2 evidence")
    if (
        global_selection.get("block_base_transform_sha256")
        != config["states"]["after"]["matrix_sha256"]
    ):
        raise DiagnosticError("diagnostic candidate matrix hash mismatch")

    targets, ladder_by_id = load_population(config)
    coreg = load_coreg_module(config)
    groups_by_id, inventory, context = build_inventory(config, coreg, targets)
    footprints = context["footprints"]
    matrices = {
        "before": np.asarray(config["states"]["before"]["matrix"], dtype=np.float64),
        "after": candidate,
    }
    metrics: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    offsets: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    global_counter: Counter[tuple[str, ...]] = Counter()
    global_exposure_counter: Counter[tuple[str, ...]] = Counter()
    all_samples: list[dict[str, Any]] = []
    for position, target in enumerate(targets, start=1):
        bid = target["building_id"]
        building_groups = groups_by_id.get(bid, [])
        for state, matrix in matrices.items():
            metric, offset, counter, exposure_counter, samples = evaluate_building(
                config,
                building_groups,
                matrix,
                state,
                footprints[bid],
                source_population="raw_dense_all_178",
                tier=target["tier"],
                population_role=target["cohort"],
            )
            metrics[bid][state] = metric
            offsets[bid][state] = offset
            global_counter.update(counter)
            global_exposure_counter.update(exposure_counter)
            all_samples.extend(samples)
        if position % 20 == 0 or position == len(targets):
            print(f"[residual] {position}/{len(targets)} buildings", flush=True)

    building_rows: list[dict[str, Any]] = []
    offset_rows: list[dict[str, Any]] = []
    for target in targets:
        bid = target["building_id"]
        row: dict[str, Any] = dict(inventory[bid])
        row["boundary_cell_label"] = ladder_by_id[bid]["cell_label"]
        for state in ("before", "after"):
            add_prefixed(row, state, metrics[bid][state])
        add_paired_deltas(
            row,
            metrics[bid]["before"],
            metrics[bid]["after"],
            (
                "matched_median_m",
                "matched_p90_m",
                "censored_median_m",
                "censored_p90_m",
                "correspondence_n",
                "bidirectional_support",
            ),
        )
        building_rows.append(row)
        offset_row: dict[str, Any] = {
            "building_id": bid,
            "tier": target["tier"],
            "cohort": target["cohort"],
            "inventory_status": inventory[bid]["inventory_status"],
            "sign_convention": "photo_minus_als",
            "after_state_disposition": "diagnostic_global_candidate_not_adopted",
        }
        for state in ("before", "after"):
            add_prefixed(offset_row, state, offsets[bid][state])
        add_paired_deltas(
            offset_row,
            offsets[bid]["before"],
            offsets[bid]["after"],
            (
                "median_dE_m",
                "median_dN_m",
                "median_dZ_m",
                "horizontal_median_vector_norm_m",
                "median_r_horizontal_m",
                "median_r_vertical_m",
                "median_r_total_m",
                "roof_median_dZ_m",
                "ground_median_dZ_m",
                "roof_ground_common_dZ_m",
                "roof_minus_ground_dZ_m",
                "available_strata_equal_weight_median_dE_m",
                "available_strata_equal_weight_median_dN_m",
                "available_strata_equal_weight_median_dZ_m",
            ),
        )
        offset_rows.append(offset_row)

    n_values = [int(row["before_correspondence_n"]) for row in building_rows]
    q10_n = int(nearest_rank(n_values, float(config["correspondence_capability"]["quantile"])))
    n_threshold = max(
        int(config["correspondence_capability"]["minimum_bidirectional_matches"]),
        q10_n,
    )
    for row in building_rows:
        row["n_distribution_q10_nearest_rank"] = q10_n
        row["n_threshold"] = n_threshold
        row["correspondence_capable"] = int(row["before_correspondence_n"]) >= n_threshold
        after_median = row.get("after_matched_median_m")
        row["after_matched_median_le_0p3"] = (
            bool(row["correspondence_capable"])
            and after_median is not None
            and float(after_median) <= 0.3
        )
        row["after_state_disposition"] = "diagnostic_global_candidate_not_adopted"
        row["gate_statistic_only"] = "matched_median_m_le_0.3"
        row["gate_statistic_scope"] = "conditional_matched_reference_only"
        row["capability_scope"] = "baseline_correspondence_conditioned"
        row["p90_support_gate_role"] = "auxiliary_only"

    capable_support = [
        float(row["before_bidirectional_support"])
        for row in building_rows
        if bool(row["correspondence_capable"])
        and row["before_bidirectional_support"] is not None
    ]
    if not capable_support:
        raise DiagnosticError("no correspondence-capable support values")
    low_support_cutoff = nearest_rank(
        capable_support, float(config["low_support"]["quantile"])
    )
    confusion, confusion_summary = confusion_rows(building_rows, low_support_cutoff)
    summary = tier_summary_rows(building_rows, n_threshold)

    # Capture-block tail evidence is a distinct, limited population because
    # raw_dense.npz has no point-to-view provenance.
    print("[blocks] regenerating locked-stride fit+trigger point provenance", flush=True)
    base_config = coreg.activate_recovery_lock2(coreg.load_config())
    block_groups, block_audit = coreg.build_block_surface_groups(
        base_config, {"fit", "trigger"}
    )
    block_by_id: dict[str, list[Any]] = defaultdict(list)
    for group in block_groups:
        block_by_id[group.building_id].append(group)
    target_by_id = {row["building_id"]: row for row in targets}
    for bid, building_groups in sorted(block_by_id.items()):
        target = target_by_id[bid]
        for state, matrix in matrices.items():
            _, _, counter, exposure_counter, _ = evaluate_building(
                config,
                building_groups,
                matrix,
                state,
                footprints[bid],
                source_population="per_view_stride16_lock2_fit_trigger",
                tier=target["tier"],
                population_role=str(building_groups[0].role),
            )
            global_counter.update(counter)
            global_exposure_counter.update(exposure_counter)

    tail_breakdown = tail_rows(global_counter, global_exposure_counter)
    block_controls = [
        row
        for row in read_csv(repo_path(base_config["inputs"]["splits_csv"]))
        if row["role"] in {"fit", "trigger"}
    ]
    expected_blocks = sorted(
        {
            row["block_id"]
            for row in read_csv(repo_path(base_config["inputs"]["camera_blocks_csv"]))
        }
    )
    if len(expected_blocks) != 3:
        raise DiagnosticError(f"locked capture block count is not three: {expected_blocks}")
    tail_breakdown.extend(
        block_inventory_rows(
            block_audit,
            block_controls,
            target_by_id,
            expected_blocks,
        )
    )
    representative_candidates = [
        row for row in building_rows if bool(row["correspondence_capable"])
    ]
    if not representative_candidates:
        raise DiagnosticError("no representative candidate building")
    representative = sorted(
        representative_candidates,
        key=lambda row: (
            -int(row["after_matched_tail_n"] + row["after_censored_unmatched_n"]),
            row["building_id"],
        ),
    )[0]["building_id"]

    staging = paths["manifest"].parent / ".coregdiag_staging"
    if staging.exists():
        raise DiagnosticError(f"staging path exists: {relative(staging)}")
    staging.mkdir()
    staged = {
        key: staging / path.name
        for key, path in paths.items()
        if key not in {"method_lock", "measurement_start"}
    }
    try:
        write_csv(staged["building_residuals"], building_rows)
        write_csv(staged["tier_summary"], summary)
        write_csv(staged["tail_breakdown"], tail_breakdown)
        write_csv(staged["support_tier_confusion"], confusion)
        write_csv(staged["building_offsets"], offset_rows)
        plot_tail_plan(
            staged["tail_plan_figure"],
            {row["building_id"]: footprints[row["building_id"]] for row in targets},
            all_samples,
            n_threshold,
        )
        plot_tail_representative(
            staged["tail_representative_figure"],
            representative,
            footprints[representative],
            all_samples,
        )
        manifest = {
            "schema": "jointbuildgs.fusion_w1.coregdiag_manifest.v1",
            "task_id": config["task_id"],
            "created_at": now_kst(),
            "branch": config["branch"],
            "measurement_head": git("rev-parse", "HEAD"),
            "method_lock_path": relative(paths["method_lock"]),
            "method_lock_sha256": sha256_file(paths["method_lock"]),
            "measurement_start_path": relative(paths["measurement_start"]),
            "measurement_start_sha256": sha256_file(paths["measurement_start"]),
            "method_sha256": method_lock["method_sha256"],
            "script_sha256": method_lock["script_sha256"],
            "config_sha256": method_lock["config_sha256"],
            "input_sha256": observed_inputs,
            "source_als_sha256_after": sha256_file(
                repo_path(config["inputs"]["source_als_laz"])
            ),
            "source_photo_sha256_after": sha256_file(
                repo_path(config["inputs"]["photo_dense_npz"])
            ),
            "population": {
                "buildings": len(building_rows),
                "tiers": dict(Counter(row["tier"] for row in building_rows)),
                "cohorts": dict(Counter(row["cohort"] for row in building_rows)),
                "correspondence_n_distribution": {
                    "minimum": min(n_values),
                    "q05_nearest_rank": nearest_rank(n_values, 0.05),
                    "q10_nearest_rank": q10_n,
                    "q25_nearest_rank": nearest_rank(n_values, 0.25),
                    "median_nearest_rank": nearest_rank(n_values, 0.5),
                    "maximum": max(n_values),
                    "threshold": n_threshold,
                    "threshold_rule": config["correspondence_capability"][
                        "threshold_rule"
                    ],
                },
                "correspondence_capable_n": sum(
                    bool(row["correspondence_capable"]) for row in building_rows
                ),
            },
            "low_support": confusion_summary,
            "representative_building": representative,
            "candidate": {
                "label": config["states"]["after"]["label"],
                "adopted_for_learning": False,
                "global_selection_choice": global_selection["choice"],
                "global_selection_status": global_selection["status"],
                "matrix": candidate,
                "translation_components_m": candidate[:3, 3],
            },
            "block_candidate_disposition": {
                "choice": block_selection["choice"],
                "status": block_selection["status"],
                "evaluated_by_this_diagnostic": False,
                "tail_state": (
                    "identity and rejected global candidate stratified by "
                    "locked capture block"
                ),
            },
            "inventory_audit": context["audit"],
            "capture_block_audit": {
                "source_population": "per_view_stride16_lock2_fit_trigger",
                "building_count": block_audit["buildings"],
                "group_count": block_audit["groups"],
                "blocks": block_audit["blocks"],
                "expected_blocks": expected_blocks,
                "depth_stride": block_audit["depth_stride"],
                "population_limit": "lock2 fit and trigger controls only",
                "population_tier_limit": "all 27 controls are surface tier",
                "role_counts": dict(Counter(row["role"] for row in block_controls)),
                "coverage_rows": block_audit["rows"],
                "complete_inventory_row_count": (
                    len(expected_blocks) * len(block_controls) * 2
                ),
                "template_audit": block_audit["template_audit"],
                "depth_set_lock": block_audit["depth_set_lock"],
                "reverse_direction_limitation": (
                    "The same fixed ALS template is conditioned once per visible "
                    "block; only photo_to_als rates are eligible for block "
                    "concentration observation."
                ),
            },
            "measurement_definitions": {
                "censored_value_m": config["correspondence"]["radius_m"],
                "censored_value_is_measured": False,
                "gate_statistic": config["correspondence_capability"][
                    "gate_statistic"
                ],
                "p90_support_are_auxiliary": True,
                "gate_statistic_scope": config["correspondence_capability"][
                    "statistic_scope"
                ],
                "capability_scope": config["correspondence_capability"][
                    "capability_scope"
                ],
                "offset_sign": config["offsets"]["sign"],
                "horizontal_offset_interpretation_limit": config["offsets"][
                    "horizontal_interpretation_limit"
                ],
                "horizontal_datum_caveat": config["coordinate_contract"][
                    "horizontal_datum_caveat"
                ],
            },
            "counters": {
                "new_diagnostic_residual_buildings": len(building_rows),
                "learning_runs_started": 0,
                "readout_runs_started": 0,
                "roofer_runs_started": 0,
                "scoring_runs_started": 0,
                "source_data_modified": False,
            },
            "elapsed_seconds": time.time() - started,
        }
        manifest["artifacts"] = {
            relative(paths[key]): sha256_file(path)
            for key, path in staged.items()
            if key != "manifest"
        }
        manifest["artifacts"][relative(paths["measurement_start"])] = sha256_file(
            paths["measurement_start"]
        )
        manifest["manifest_self_hash_omitted"] = True
        write_json(staged["manifest"], manifest)
        for key, path in staged.items():
            if key != "manifest":
                os.replace(path, paths[key])
        os.replace(staged["manifest"], paths["manifest"])
        shutil.rmtree(staging)
        return manifest
    except Exception:
        print(f"[error] staging retained at {relative(staging)}", file=sys.stderr)
        raise


def recover_publish(config: Mapping[str, Any]) -> dict[str, Any]:
    """Complete a manifest-last publish without reading residual inputs again."""

    method_lock = verify_method_lock(config)
    paths = output_paths(config)
    staging = paths["manifest"].parent / ".coregdiag_staging"
    staged_manifest = staging / paths["manifest"].name
    if not staged_manifest.is_file():
        raise DiagnosticError("recoverable staged manifest is missing")
    manifest = load_json(staged_manifest)
    if manifest.get("method_sha256") != method_lock["method_sha256"]:
        raise DiagnosticError("staged manifest method hash mismatch")
    for key, target in paths.items():
        if key in {"method_lock", "measurement_start", "manifest"}:
            continue
        logical = relative(target)
        expected = manifest["artifacts"].get(logical)
        if not expected:
            raise DiagnosticError(f"staged artifact hash missing: {logical}")
        source = staging / target.name
        if target.is_file():
            if sha256_file(target) != expected:
                raise DiagnosticError(f"partial published artifact differs: {logical}")
            if source.exists():
                source.unlink()
        else:
            if not source.is_file() or sha256_file(source) != expected:
                raise DiagnosticError(f"recoverable staged artifact differs: {logical}")
            os.replace(source, target)
    os.replace(staged_manifest, paths["manifest"])
    shutil.rmtree(staging)
    return {
        "status": "PUBLISH_RECOVERED_WITHOUT_NEW_MEASUREMENT",
        "manifest": relative(paths["manifest"]),
        "learning_runs_started": 0,
    }


def verify_outputs(config: Mapping[str, Any]) -> dict[str, Any]:
    method_lock = verify_method_lock(config)
    paths = output_paths(config)
    required = set(paths) - {"method_lock"}
    missing = [key for key in required if not paths[key].is_file()]
    if missing:
        raise DiagnosticError(f"diagnostic outputs missing: {missing}")
    manifest = load_json(paths["manifest"])
    if manifest.get("schema") != "jointbuildgs.fusion_w1.coregdiag_manifest.v1":
        raise DiagnosticError("unexpected diagnostic manifest schema")
    if manifest.get("task_id") != config["task_id"]:
        raise DiagnosticError("diagnostic manifest task mismatch")
    if manifest.get("method_sha256") != method_lock["method_sha256"]:
        raise DiagnosticError("diagnostic manifest method mismatch")
    if manifest.get("method_lock_sha256") != sha256_file(paths["method_lock"]):
        raise DiagnosticError("diagnostic manifest method-lock hash mismatch")
    start_receipt = load_json(paths["measurement_start"])
    if (
        start_receipt.get("schema")
        != "jointbuildgs.fusion_w1.coregdiag_measurement_start.v1"
        or int(start_receipt.get("point_clouds_opened_before_claim", -1)) != 0
        or int(start_receipt.get("learning_runs_started", -1)) != 0
    ):
        raise DiagnosticError("measurement start receipt is invalid")
    if manifest.get("measurement_start_sha256") != sha256_file(
        paths["measurement_start"]
    ):
        raise DiagnosticError("measurement start hash mismatch")
    for logical, expected in manifest.get("artifacts", {}).items():
        path = repo_path(logical)
        if not path.is_file() or sha256_file(path) != expected:
            raise DiagnosticError(f"diagnostic artifact hash mismatch: {logical}")
    rows = read_csv(paths["building_residuals"])
    if len(rows) != int(config["population"]["expected_buildings"]):
        raise DiagnosticError("building residual table is not 178 rows")
    if len({row["building_id"] for row in rows}) != len(rows):
        raise DiagnosticError("building residual IDs are not unique")
    targets = read_csv(repo_path(config["inputs"]["targets_csv"]))
    if {row["building_id"] for row in rows} != {
        row["building_id"] for row in targets
    }:
        raise DiagnosticError("building residual IDs differ from target population")
    building_required = {
        "building_id",
        "tier",
        "before_matched_median_m",
        "before_matched_p90_m",
        "before_correspondence_n",
        "before_bidirectional_support",
        "after_matched_median_m",
        "after_matched_p90_m",
        "after_correspondence_n",
        "after_bidirectional_support",
        "correspondence_capable",
        "n_threshold",
    }
    if not building_required.issubset(rows[0]):
        raise DiagnosticError("building residual schema is incomplete")
    summaries = read_csv(paths["tier_summary"])
    if len(summaries) != 8 or not {
        "matched_median_le_0p3_fraction",
        "building_balanced_median_of_matched_p90_m",
        "median_correspondence_n",
        "median_bidirectional_support",
    }.issubset(summaries[0]):
        raise DiagnosticError("tier summary schema/count is incomplete")
    offsets = read_csv(paths["building_offsets"])
    if len(offsets) != len(rows) or not {
        "before_median_dE_m",
        "before_median_dN_m",
        "before_median_dZ_m",
        "after_median_dE_m",
        "after_median_dN_m",
        "after_median_dZ_m",
        "delta_after_minus_before_median_dZ_m",
        "before_available_strata_observed_n",
    }.issubset(offsets[0]):
        raise DiagnosticError("building offset schema/count is incomplete")
    confusion = read_csv(paths["support_tier_confusion"])
    if len(confusion) != 4 or not {
        "tier_group",
        "low_support",
        "count",
        "fisher_two_sided_p",
    }.issubset(confusion[0]):
        raise DiagnosticError("support-tier confusion schema/count is incomplete")
    tails = read_csv(paths["tail_breakdown"])
    row_types = {row["row_type"] for row in tails}
    if not {
        "proxy_category_detail",
        "exposure_complete_aggregate",
        "block_inventory_coverage",
    }.issubset(row_types):
        raise DiagnosticError("tail breakdown lacks required evidence row types")
    if not any(
        row["source_population"] == "per_view_stride16_lock2_fit_trigger"
        and row["block_concentration_eligible"] == "true"
        for row in tails
    ):
        raise DiagnosticError("tail breakdown lacks block-attributable exposure")
    inventory_rows = [
        row for row in tails if row["row_type"] == "block_inventory_coverage"
    ]
    expected_blocks = set(
        manifest["capture_block_audit"].get("expected_blocks", [])
    )
    if expected_blocks != {
        "capture_block_01",
        "capture_block_02",
        "capture_block_03",
    }:
        raise DiagnosticError("manifest capture-block inventory differs from lock")
    if len(inventory_rows) != 3 * 27 * 2 or {
        row["capture_block"] for row in inventory_rows
    } != expected_blocks:
        raise DiagnosticError("tail block inventory is not complete 3x27x2")
    for key in ("tail_plan_figure", "tail_representative_figure"):
        payload = paths[key].read_bytes()
        if len(payload) < 1024 or not payload.startswith(b"\x89PNG\r\n\x1a\n"):
            raise DiagnosticError(f"invalid PNG output: {key}")
    if int(manifest["counters"]["learning_runs_started"]) != 0:
        raise DiagnosticError("manifest reports a learning run")
    if manifest["source_als_sha256_after"] != config["input_sha256"][
        config["inputs"]["source_als_laz"]
    ]:
        raise DiagnosticError("source ALS after-hash mismatch")
    if manifest["source_photo_sha256_after"] != config["input_sha256"][
        config["inputs"]["photo_dense_npz"]
    ]:
        raise DiagnosticError("source photo after-hash mismatch")
    return {
        "status": "VERIFIED",
        "building_rows": len(rows),
        "tier_summary_rows": len(summaries),
        "tail_rows": len(tails),
        "offset_rows": len(offsets),
        "artifacts": output_hashes(paths, set()),
        "learning_runs_started": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG),
        help="locked diagnostic config",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("lock")
    sub.add_parser("measure")
    sub.add_parser("recover-publish")
    sub.add_parser("verify")
    args = parser.parse_args()
    config = load_config(args.config)
    if args.command == "lock":
        payload = lock_method(config)
    elif args.command == "measure":
        payload = measure(config)
    elif args.command == "recover-publish":
        payload = recover_publish(config)
    else:
        payload = verify_outputs(config)
    print(json.dumps(json_safe(payload), indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except DiagnosticError as exc:
        print(f"[BLOCKED] {exc}", file=sys.stderr)
        raise SystemExit(2)
