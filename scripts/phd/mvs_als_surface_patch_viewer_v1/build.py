#!/usr/bin/env python3
"""Build and validate the offline raw-relation versus surface-patch viewer."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
from typing import Any, Iterable

import numpy as np


REPO = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = REPO / "configs/phd/mvs_als_surface_patch_viewer_v1/viewer_v1.json"


def sha256(path: Path, chunk_bytes: int = 8 << 20) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(chunk_bytes), b""):
            value.update(block)
    return value.hexdigest()


def atomic_bytes(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(value)
    os.replace(temporary, path)


def atomic_json(path: Path, value: Any) -> None:
    atomic_bytes(path, (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8"))


def atomic_copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    shutil.copyfile(source, temporary)
    os.replace(temporary, target)


def write_array(path: Path, value: np.ndarray) -> None:
    atomic_bytes(path, np.ascontiguousarray(value).tobytes())


def record(path: Path, relative_to: Path, **extra: Any) -> dict[str, Any]:
    return {
        "path": path.relative_to(relative_to).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
        **extra,
    }


def require_file(root: Path, item: dict[str, Any]) -> Path:
    path = root / item["path"]
    if not path.is_file() or path.is_symlink():
        raise RuntimeError(f"missing exact upstream file: {path}")
    if path.stat().st_size != int(item["bytes"]) or sha256(path) != item["sha256"]:
        raise RuntimeError(f"upstream file hash/size drift: {path}")
    return path


def load_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    cfg = json.loads(path.read_text(encoding="utf-8"))
    if cfg.get("schema") != "jointbuildgs.phd.mvs_als_surface_patch_viewer.run.v1":
        raise ValueError("surface-patch viewer config schema drift")
    if cfg.get("status") != "USER_APPROVED_DEVELOPMENT_NON_CONFIRMATORY":
        raise ValueError("surface-patch viewer build is not user-approved")
    if cfg.get("scientific_verdict", "missing") is not None:
        raise ValueError("scientific_verdict must remain null")
    if cfg.get("default_port") != 8892:
        raise ValueError("surface-patch viewer must use its separate port 8892")
    if set(cfg.get("classes", {})) != {"1", "2", "3", "4", "5"}:
        raise ValueError("exactly five frozen source-relation classes are required")
    if len(cfg.get("source_relation_viewer_manifest_sha256", "")) != 64:
        raise ValueError("source relation viewer manifest hash is not frozen")
    if len(cfg.get("surface_patch_artifact_manifest_sha256", "")) != 64:
        raise ValueError("surface-patch artifact manifest hash is not frozen")
    if len(cfg.get("surface_patch_validation_receipt_sha256", "")) != 64:
        raise ValueError("surface-patch validation receipt hash is not frozen")
    if len(cfg.get("region_unit_artifact_manifest_sha256", "")) != 64:
        raise ValueError("region-unit artifact manifest hash is not frozen")
    if len(cfg.get("region_unit_validation_receipt_sha256", "")) != 64:
        raise ValueError("region-unit validation receipt hash is not frozen")
    serialized = json.dumps({
        "relation": cfg["source_relation_viewer_relative_root"],
        "patch": cfg["surface_patch_relative_root"],
        "unit": cfg["region_unit_relative_root"],
        "viewer": cfg["viewer_output_relative_root"],
    }).lower()
    for token in ("uas", "lod2", "footprint", "stable_id", "journal1"):
        if token in serialized:
            raise ValueError(f"prohibited input token: {token}")
    return cfg


def _require_names(dtype: np.dtype, names: Iterable[str], label: str) -> None:
    available = set(dtype.names or ())
    missing = set(names) - available
    if missing:
        raise RuntimeError(f"{label} missing fields: {sorted(missing)}")


def verify_relation_upstream(cfg: dict[str, Any], root: Path) -> tuple[dict[str, Any], dict[str, Path]]:
    manifest_path = root / "viewer_manifest.json"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise RuntimeError(f"missing frozen relation viewer manifest: {manifest_path}")
    actual = sha256(manifest_path)
    if actual != cfg["source_relation_viewer_manifest_sha256"]:
        raise RuntimeError(f"source relation viewer manifest drift: {actual}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("scientific_verdict", "missing") is not None:
        raise RuntimeError("upstream relation viewer scientific_verdict is not null")
    if manifest.get("prohibited_inputs_accessed") != []:
        raise RuntimeError("upstream relation viewer prohibited-input access is not empty")
    files = {
        "mvs": require_file(root, manifest["sources"]["mvs"]),
        "als": require_file(root, manifest["sources"]["als"]),
        "xyz": require_file(root, manifest["relations"]["xyz"]),
        "attributes": require_file(root, manifest["relations"]["attributes"]),
        "metrics": require_file(root, manifest["relations"]["metrics"]),
        "support_counts": require_file(root, manifest["relations"]["support_counts"]),
    }
    return manifest, files


def verify_patch_upstream(cfg: dict[str, Any], root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Path]]:
    manifest_path = root / "artifact_manifest.json"
    validation_path = root / "validation_receipt.json"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise RuntimeError(f"missing patch artifact manifest: {manifest_path}")
    if not validation_path.is_file() or validation_path.is_symlink():
        raise RuntimeError(f"missing patch validation receipt: {validation_path}")
    if sha256(manifest_path) != cfg["surface_patch_artifact_manifest_sha256"]:
        raise RuntimeError("surface-patch artifact manifest hash drift")
    if sha256(validation_path) != cfg["surface_patch_validation_receipt_sha256"]:
        raise RuntimeError("surface-patch validation receipt hash drift")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    if manifest.get("task_id") != cfg["surface_patch_task_id"]:
        raise RuntimeError("surface-patch task ID drift")
    if manifest.get("schema") != "jointbuildgs.phd.mvs_als_surface_patch.artifact_manifest.v1":
        raise RuntimeError("surface-patch artifact manifest schema drift")
    if manifest.get("scientific_verdict", "missing") is not None:
        raise RuntimeError("upstream patch scientific_verdict is not null")
    if validation.get("scientific_verdict", "missing") is not None:
        raise RuntimeError("upstream patch validation scientific_verdict is not null")
    if any(value != "PASS" for value in validation.get("checks", {}).values()):
        raise RuntimeError("upstream patch validation contains a non-PASS check")
    files = {}
    for name in ("patch_membership.npy", "surface_patch_summary.npy", "technical_return.json"):
        if name not in manifest.get("outputs", {}):
            raise RuntimeError(f"patch artifact manifest omits {name}")
        files[name] = require_file(root, manifest["outputs"][name])
    technical = json.loads(files["technical_return.json"].read_text(encoding="utf-8"))
    if technical.get("scientific_verdict", "missing") is not None:
        raise RuntimeError("upstream patch technical scientific_verdict is not null")
    if technical.get("prohibited_inputs_accessed") != []:
        raise RuntimeError("upstream patch prohibited-input access is not empty")
    if technical.get("interpretation", {}).get("candidate_evidence_is_never_smoothed_to_compatible") is not True:
        raise RuntimeError("upstream patch candidate-safe aggregation contract is not true")
    if technical.get("selected_metrics", {}).get("candidate_to_compatible_core_count") != 0:
        raise RuntimeError("upstream patch candidate evidence was smoothed to compatible")
    files["artifact_manifest.json"] = manifest_path
    files["validation_receipt.json"] = validation_path
    return manifest, technical, files


def verify_region_unit_upstream(cfg: dict[str, Any], root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Path]]:
    manifest_path = root / "artifact_manifest.json"
    validation_path = root / "validation_receipt.json"
    for path in (manifest_path, validation_path):
        if not path.is_file() or path.is_symlink():
            raise RuntimeError(f"missing region-unit receipt: {path}")
    if sha256(manifest_path) != cfg["region_unit_artifact_manifest_sha256"]:
        raise RuntimeError("region-unit artifact manifest hash drift")
    if sha256(validation_path) != cfg["region_unit_validation_receipt_sha256"]:
        raise RuntimeError("region-unit validation receipt hash drift")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    if manifest.get("task_id") != cfg["region_unit_task_id"]:
        raise RuntimeError("region-unit task ID drift")
    if manifest.get("schema") != "jointbuildgs.phd.region_unit.artifact_manifest.v1":
        raise RuntimeError("region-unit artifact manifest schema drift")
    for item in (manifest, validation):
        if item.get("scientific_verdict", "missing") is not None:
            raise RuntimeError("upstream region-unit scientific_verdict is not null")
    if any(value != "PASS" for value in validation.get("checks", {}).values()):
        raise RuntimeError("upstream region-unit validation contains a non-PASS check")
    if validation.get("artifact_manifest_sha256") != sha256(manifest_path):
        raise RuntimeError("region-unit validation receipt is not bound to this artifact manifest")
    files = {}
    for name in ("cells.npy", "units.npy", "unit_adjacency.npy", "technical_return.json"):
        if name not in manifest.get("outputs", {}):
            raise RuntimeError(f"region-unit artifact manifest omits {name}")
        files[name] = require_file(root, manifest["outputs"][name])
    technical = json.loads(files["technical_return.json"].read_text(encoding="utf-8"))
    if technical.get("scientific_verdict", "missing") is not None or technical.get("prohibited_inputs_accessed") != []:
        raise RuntimeError("upstream region-unit technical return contract drift")
    interpretation = technical.get("interpretation", {})
    if interpretation.get("units_are_defined_on_frozen_source_data_only") is not True:
        raise RuntimeError("region units must be defined on frozen source data only")
    if interpretation.get("source_authority_decided") or interpretation.get("temporal_change_decided"):
        raise RuntimeError("region units must not carry a source or change verdict")
    files["artifact_manifest.json"] = manifest_path
    files["validation_receipt.json"] = validation_path
    return manifest, technical, files


def validate_region_unit_arrays(cells: np.ndarray, units: np.ndarray, adjacency: np.ndarray) -> None:
    _require_names(cells.dtype, (
        "cell_index", "source", "x", "y", "z", "point_count", "nx", "ny", "nz",
        "surface_variation", "normal_valid", "segment_id", "unit_id", "role", "pair_distance_m", "pair_rule",
    ), "region-unit cells")
    _require_names(units.dtype, (
        "unit_id", "unit_uid", "primary_source", "kind", "small", "split_child", "split_reason", "mixed_prior",
        "absorbed_cell_count", "prior_segment_count", "prior_offset_median_m", "prior_offset_spread_m",
        "prior_plane_rmse_m", "core_count_total", "core_count_class_1", "core_count_class_2",
        "core_count_class_3", "core_count_class_4", "core_count_class_5",
        "mvs_cell_count", "mvs_point_count", "als_cell_count", "als_point_count", "area_m2",
        "cx", "cy", "cz", "nx", "ny", "nz", "plane_d", "plane_rmse_m", "plane_p95_abs_residual_m",
        "extent_e1_m", "extent_e2_m", "tilt_from_up_deg", "prior_support_fraction",
        "paired_als_segment_count", "component_count",
        "bbox_min_x", "bbox_min_y", "bbox_min_z", "bbox_max_x", "bbox_max_y", "bbox_max_z",
    ), "region-unit units")
    _require_names(adjacency.dtype, ("unit_a", "unit_b", "contact_pairs", "same_primary",
                                     "contact_mvs_mvs", "contact_als_als", "contact_cross"), "region-unit adjacency")
    if not np.array_equal(units["unit_id"], np.arange(1, len(units) + 1, dtype=np.uint32)):
        raise RuntimeError("region-unit ids are not contiguous")
    if np.any(cells["unit_id"] == 0) or np.any(cells["unit_id"] > len(units)):
        raise RuntimeError("region-unit coverage drift: a cell has no unit")
    if not set(np.unique(cells["source"])).issubset({0, 1}) or not set(np.unique(units["kind"])).issubset({0, 1}):
        raise RuntimeError("unknown region-unit source or kind")
    uids = [bytes(value).rstrip(b"\0") for value in units["unit_uid"]]
    if any(not uid for uid in uids) or len(set(uids)) != len(uids):
        raise RuntimeError("region-unit uid is empty or non-unique")
    if len(adjacency) and (np.any(adjacency["unit_a"] >= adjacency["unit_b"]) or np.any(adjacency["unit_b"] > len(units))):
        raise RuntimeError("region-unit adjacency drift")


def validate_patch_arrays(
    membership: np.ndarray,
    summaries: np.ndarray,
    relation_attributes: np.ndarray,
) -> None:
    _require_names(membership.dtype, (
        "core_index", "patch_id", "raw_relation_class", "patch_relation_class",
        "core_source", "patch_status", "unassigned_reason", "patch_core_count",
        "patch_purity", "patch_radius_m",
    ), "patch membership")
    _require_names(summaries.dtype, (
        "patch_id", "patch_uid", "core_source", "patch_relation_class",
        "patch_status", "dominant_raw_class", "core_count", "cx", "cy", "cz",
        "nx", "ny", "nz", "radius_m", "bbox_diagonal_m", "support_area_proxy_m2",
        "plane_rmse_m", "plane_p95_abs_residual_m", "plane_max_abs_residual_m",
        "normal_p95_deg", "normal_max_deg",
        "relation_purity", "robust_fraction", "median_surface_variation",
        "count_class_1", "count_class_2", "count_class_3", "count_class_4", "count_class_5",
    ), "patch summary")
    count = len(membership)
    if relation_attributes.shape != (count, 4):
        raise RuntimeError("relation attribute count/stride does not match membership")
    if not np.array_equal(membership["core_index"], np.arange(count, dtype=np.uint32)):
        raise RuntimeError("patch membership core order drift")
    if not np.array_equal(membership["raw_relation_class"], relation_attributes[:, 0]):
        raise RuntimeError("raw five-class provenance drift")
    if not np.array_equal(membership["core_source"], relation_attributes[:, 1]):
        raise RuntimeError("source-family provenance drift")
    if not set(np.unique(membership["raw_relation_class"])).issubset({1, 2, 3, 4, 5}):
        raise RuntimeError("unknown raw relation class")
    if not set(np.unique(membership["patch_relation_class"])).issubset({1, 2, 3, 4, 5}):
        raise RuntimeError("unknown patch relation class")
    if not set(np.unique(membership["unassigned_reason"])).issubset({0, 1, 2, 3}):
        raise RuntimeError("unknown unassigned reason")
    referenced = set(map(int, np.unique(membership["patch_id"]))) - {0}
    available = set(map(int, summaries["patch_id"]))
    if referenced != available or len(available) != len(summaries):
        raise RuntimeError("patch ID referential integrity failure")
    uids = [bytes(value).rstrip(b"\0") for value in summaries["patch_uid"]]
    if any(not uid for uid in uids) or len(set(uids)) != len(uids):
        raise RuntimeError("patch UID is empty or non-unique")


def _class_counts(values: np.ndarray) -> dict[str, int]:
    return {str(class_id): int(np.count_nonzero(values == class_id)) for class_id in range(1, 6)}


def _status_counts(values: np.ndarray) -> dict[str, int]:
    return {str(status): int(np.count_nonzero(values == status)) for status in range(5)}


def build(cfg: dict[str, Any], config_path: Path) -> dict[str, Any]:
    artifact_root = Path(cfg["artifact_root"])
    relation_root = artifact_root / cfg["source_relation_viewer_relative_root"]
    patch_root = artifact_root / cfg["surface_patch_relative_root"]
    viewer = artifact_root / cfg["viewer_output_relative_root"]
    assets = viewer / "assets"
    libraries = viewer / "lib"
    viewer.mkdir(parents=True, exist_ok=True)
    assets.mkdir(parents=True, exist_ok=True)
    libraries.mkdir(parents=True, exist_ok=True)

    relation_manifest, relation_files = verify_relation_upstream(cfg, relation_root)
    patch_manifest, patch_technical, patch_files = verify_patch_upstream(cfg, patch_root)
    membership = np.load(patch_files["patch_membership.npy"], allow_pickle=False)
    summaries = np.load(patch_files["surface_patch_summary.npy"], allow_pickle=False)
    relation_attributes = np.fromfile(relation_files["attributes"], dtype=np.uint8).reshape(-1, 4)
    validate_patch_arrays(membership, summaries, relation_attributes)

    copied = {}
    for key, source in relation_files.items():
        suffix = source.name
        target = assets / suffix
        atomic_copy(source, target)
        copied[key] = target

    patch_arrays = {
        "ids": np.ascontiguousarray(membership["patch_id"], dtype="<u4"),
        "attributes": np.ascontiguousarray(np.column_stack((
            membership["patch_relation_class"], membership["core_source"],
            membership["patch_status"], membership["unassigned_reason"],
        )), dtype=np.uint8),
        "core_counts": np.ascontiguousarray(membership["patch_core_count"], dtype="<u4"),
        "metrics": np.ascontiguousarray(np.column_stack((
            membership["patch_purity"], membership["patch_radius_m"],
        )), dtype="<f4"),
        "summary_ids": np.ascontiguousarray(np.column_stack((
            summaries["patch_id"], summaries["core_count"],
            summaries["count_class_1"], summaries["count_class_2"], summaries["count_class_3"],
            summaries["count_class_4"], summaries["count_class_5"],
        )), dtype="<u4"),
        "summary_attributes": np.ascontiguousarray(np.column_stack((
            summaries["core_source"], summaries["patch_relation_class"],
            summaries["patch_status"], summaries["dominant_raw_class"],
        )), dtype=np.uint8),
        "summary_pose": np.ascontiguousarray(np.column_stack((
            summaries["cx"], summaries["cy"], summaries["cz"],
            summaries["nx"], summaries["ny"], summaries["nz"],
        )), dtype="<f4"),
        "summary_metrics": np.ascontiguousarray(np.column_stack((
            summaries["radius_m"], summaries["bbox_diagonal_m"],
            summaries["plane_rmse_m"], summaries["plane_p95_abs_residual_m"],
            summaries["plane_max_abs_residual_m"], summaries["normal_p95_deg"],
            summaries["normal_max_deg"], summaries["support_area_proxy_m2"],
            summaries["relation_purity"], summaries["robust_fraction"],
            summaries["median_surface_variation"],
        )), dtype="<f4"),
        "summary_uids": np.ascontiguousarray(summaries["patch_uid"].astype("S20", copy=False)),
    }
    patch_paths = {
        "ids": assets / "patch_ids_u32le.bin",
        "attributes": assets / "patch_attributes_u8.bin",
        "core_counts": assets / "patch_core_counts_u32le.bin",
        "metrics": assets / "patch_metrics_f32le.bin",
        "summary_ids": assets / "patch_summary_ids_u32le.bin",
        "summary_attributes": assets / "patch_summary_attributes_u8.bin",
        "summary_pose": assets / "patch_summary_pose_f32le.bin",
        "summary_metrics": assets / "patch_summary_metrics_f32le.bin",
        "summary_uids": assets / "patch_summary_uids_s20.bin",
    }
    for name, array in patch_arrays.items():
        write_array(patch_paths[name], array)

    unit_root = artifact_root / cfg["region_unit_relative_root"]
    unit_manifest, unit_technical, unit_files = verify_region_unit_upstream(cfg, unit_root)
    cells = np.load(unit_files["cells.npy"], allow_pickle=False)
    units = np.load(unit_files["units.npy"], allow_pickle=False)
    adjacency = np.load(unit_files["unit_adjacency.npy"], allow_pickle=False)
    validate_region_unit_arrays(cells, units, adjacency)
    if unit_technical.get("frame") != relation_manifest["frame"]:
        raise RuntimeError("region-unit frame drift versus relation viewer")
    unit_kind_of_cell = units["kind"][cells["unit_id"] - 1]
    unit_primary_of_cell = units["primary_source"][cells["unit_id"] - 1]
    unit_arrays = {
        "cells_xyz": np.ascontiguousarray(np.column_stack((cells["x"], cells["y"], cells["z"])), dtype="<f4"),
        "cells_attributes": np.ascontiguousarray(np.column_stack((
            cells["source"], cells["role"], unit_kind_of_cell, unit_primary_of_cell, cells["pair_rule"])), dtype=np.uint8),
        "cells_unit": np.ascontiguousarray(cells["unit_id"], dtype="<u4"),
        "cells_metrics": np.ascontiguousarray(np.column_stack((
            cells["surface_variation"], cells["pair_distance_m"])), dtype="<f4"),
        "units_ids": np.ascontiguousarray(np.column_stack((
            units["unit_id"], units["mvs_cell_count"], units["mvs_point_count"], units["als_cell_count"],
            units["als_point_count"], units["absorbed_cell_count"], units["paired_als_segment_count"],
            units["component_count"], units["core_count_total"], units["core_count_class_1"],
            units["core_count_class_2"], units["core_count_class_3"], units["core_count_class_4"],
            units["core_count_class_5"])), dtype="<u4"),
        "units_attributes": np.ascontiguousarray(np.column_stack((
            units["primary_source"], units["kind"], units["small"], units["split_child"],
            units["split_reason"], units["mixed_prior"])), dtype=np.uint8),
        "units_pose": np.ascontiguousarray(np.column_stack((
            units["cx"], units["cy"], units["cz"], units["nx"], units["ny"], units["nz"], units["plane_d"])), dtype="<f4"),
        "units_metrics": np.ascontiguousarray(np.column_stack((
            units["area_m2"], units["plane_rmse_m"], units["plane_p95_abs_residual_m"],
            units["extent_e1_m"], units["extent_e2_m"], units["tilt_from_up_deg"], units["prior_support_fraction"],
            units["bbox_min_x"], units["bbox_min_y"], units["bbox_min_z"],
            units["bbox_max_x"], units["bbox_max_y"], units["bbox_max_z"],
            units["prior_offset_median_m"], units["prior_offset_spread_m"], units["prior_plane_rmse_m"])), dtype="<f4"),
        "units_uids": np.ascontiguousarray(units["unit_uid"].astype("S16", copy=False)),
        "adjacency": np.ascontiguousarray(np.column_stack((
            adjacency["unit_a"], adjacency["unit_b"], adjacency["contact_pairs"], adjacency["same_primary"],
            adjacency["contact_mvs_mvs"], adjacency["contact_als_als"], adjacency["contact_cross"])), dtype="<u4"),
    }
    unit_paths = {name: assets / f"t0_{name}.bin" for name in unit_arrays}
    for name, array in unit_arrays.items():
        write_array(unit_paths[name], array)

    app_source = REPO / cfg["app_source_relative_root"]
    for name in ("index.html", "app.js", "styles.css"):
        atomic_copy(app_source / name, viewer / name)
    for key, source in cfg["browser_dependencies"].items():
        target_name = "three.module.min.js" if key == "three" else "gaussian-splats-3d.module.min.js"
        atomic_copy(REPO / source, libraries / target_name)

    count = len(membership)
    patch_count = len(summaries)
    relations = {
        **relation_manifest["relations"],
        "xyz": record(copied["xyz"], viewer),
        "attributes": record(copied["attributes"], viewer),
        "metrics": record(copied["metrics"], viewer),
        "support_counts": record(copied["support_counts"], viewer),
        "raw_class_counts": _class_counts(membership["raw_relation_class"]),
    }
    sources = {}
    for key in ("mvs", "als"):
        upstream = relation_manifest["sources"][key]
        sources[key] = record(
            copied[key], viewer, count=int(upstream["count"]), color=cfg["source_colors"][key],
            voxel_m=upstream["voxel_m"], role=upstream["role"],
        )
    patch_assets = {
        "ids": record(patch_paths["ids"], viewer, stride_bytes=4),
        "attributes": record(patch_paths["attributes"], viewer, stride_bytes=4,
                             names=["patch_relation_class", "core_source", "patch_status", "unassigned_reason"]),
        "core_counts": record(patch_paths["core_counts"], viewer, stride_bytes=4),
        "metrics": record(patch_paths["metrics"], viewer, stride_bytes=8,
                          names=["patch_purity", "patch_radius_m"]),
        "summary_ids": record(patch_paths["summary_ids"], viewer, stride_bytes=28,
                              names=["patch_id", "core_count", "count_class_1", "count_class_2",
                                     "count_class_3", "count_class_4", "count_class_5"]),
        "summary_attributes": record(patch_paths["summary_attributes"], viewer, stride_bytes=4,
                                     names=["core_source", "patch_relation_class", "patch_status", "dominant_raw_class"]),
        "summary_pose": record(patch_paths["summary_pose"], viewer, stride_bytes=24,
                               names=["cx", "cy", "cz", "nx", "ny", "nz"]),
        "summary_metrics": record(patch_paths["summary_metrics"], viewer, stride_bytes=44,
                                  names=["radius_m", "bbox_diagonal_m", "plane_rmse_m",
                                         "plane_p95_abs_residual_m", "plane_max_abs_residual_m",
                                         "normal_p95_deg", "normal_max_deg", "support_area_proxy_m2",
                                         "relation_purity", "robust_fraction", "median_surface_variation"]),
        "summary_uids": record(patch_paths["summary_uids"], viewer, stride_bytes=20),
    }
    status_names = patch_technical.get("patch_status_names", {})
    statuses = {
        str(key): {
            "name": status_names.get(str(key), f"STATUS_{key}"),
            "color": cfg["patch_status_colors"][str(key)],
            "core_count": _status_counts(membership["patch_status"])[str(key)],
        }
        for key in range(5)
    }
    unit_assets = {
        "cells_xyz": record(unit_paths["cells_xyz"], viewer, stride_bytes=12),
        "cells_attributes": record(unit_paths["cells_attributes"], viewer, stride_bytes=5,
                                   names=["source", "role", "unit_kind", "unit_primary_source", "pair_rule"]),
        "cells_unit": record(unit_paths["cells_unit"], viewer, stride_bytes=4),
        "cells_metrics": record(unit_paths["cells_metrics"], viewer, stride_bytes=8,
                                names=["surface_variation", "pair_distance_m"]),
        "units_ids": record(unit_paths["units_ids"], viewer, stride_bytes=56,
                            names=["unit_id", "mvs_cell_count", "mvs_point_count", "als_cell_count",
                                   "als_point_count", "absorbed_cell_count", "paired_als_segment_count",
                                   "component_count", "core_count_total", "core_count_class_1", "core_count_class_2",
                                   "core_count_class_3", "core_count_class_4", "core_count_class_5"]),
        "units_attributes": record(unit_paths["units_attributes"], viewer, stride_bytes=6,
                                   names=["primary_source", "kind", "small", "split_child", "split_reason", "mixed_prior"]),
        "units_pose": record(unit_paths["units_pose"], viewer, stride_bytes=28,
                             names=["cx", "cy", "cz", "nx", "ny", "nz", "plane_d"]),
        "units_metrics": record(unit_paths["units_metrics"], viewer, stride_bytes=64,
                                names=["area_m2", "plane_rmse_m", "plane_p95_abs_residual_m", "extent_e1_m",
                                       "extent_e2_m", "tilt_from_up_deg", "prior_support_fraction",
                                       "bbox_min_x", "bbox_min_y", "bbox_min_z", "bbox_max_x", "bbox_max_y",
                                       "bbox_max_z", "prior_offset_median_m", "prior_offset_spread_m",
                                       "prior_plane_rmse_m"]),
        "units_uids": record(unit_paths["units_uids"], viewer, stride_bytes=16),
        "adjacency": record(unit_paths["adjacency"], viewer, stride_bytes=28,
                            names=["unit_a", "unit_b", "contact_pairs", "same_primary",
                                   "contact_mvs_mvs", "contact_als_als", "contact_cross"]),
    }
    region_units = {
        "task_id": cfg["region_unit_task_id"],
        "role": "T0_DATA_DEFINED_DECISION_UNITS_DISPLAY_ONLY",
        "design_reference": unit_technical.get("design_reference"),
        "domain": unit_technical["domain"],
        "selected_profile": unit_technical["selected_profile"],
        "profile": unit_technical["profile"],
        "accounting": unit_technical["accounting"],
        "cell_count": int(len(cells)),
        "unit_count": int(len(units)),
        "adjacency_count": int(len(adjacency)),
        "source_names": unit_technical["source_names"],
        "kind_names": unit_technical["kind_names"],
        "role_names": unit_technical["role_names"],
        "pair_rule_names": unit_technical["pair_rule_names"],
        "split_reason_names": unit_technical["split_reason_names"],
        "unit_set_sha256": unit_technical["unit_set_sha256"],
        "colors": cfg["region_unit_colors"],
        "not_decided_here": unit_technical["not_decided_here"],
        "assets": unit_assets,
    }
    manifest = {
        "schema": "jointbuildgs.phd.mvs_als_surface_patch.viewer.v1",
        "task_id": cfg["task_id"],
        "status": "READY_FOR_QUALITATIVE_WEB_REVIEW",
        "purpose": "RAW_FIVE_CLASS_VERSUS_LOCALLY_CONNECTED_SOURCE_SURFACE_PATCH_COMPARISON",
        "comparison_contract": {
            "before": "FROZEN_ONE_PASS_M3C2_SUPPORT_RELATION_CORE_LABELS",
            "after": "GEOMETRY_CONNECTED_PATCH_AGGREGATED_RELATION_LABELS",
            "m3c2_recomputed": False,
            "candidate_evidence_never_smoothed_to_compatible": True,
            "display_only_no_method_feedback": True,
        },
        "not_interpretable_as": [
            "TEMPORAL_CHANGE_VERDICT", "SOURCE_CORRECTNESS_VERDICT",
            "SOURCE_AUTHORITY_DECISION", "SCIENTIFIC_PERFORMANCE_VERDICT",
        ],
        "upstreams": {
            "source_relation_viewer_manifest": record(relation_root / "viewer_manifest.json", relation_root),
            "surface_patch_artifact_manifest": record(patch_files["artifact_manifest.json"], patch_root),
            "surface_patch_validation_receipt": record(patch_files["validation_receipt.json"], patch_root),
            "region_unit_artifact_manifest": record(unit_files["artifact_manifest.json"], unit_root),
            "region_unit_validation_receipt": record(unit_files["validation_receipt.json"], unit_root),
        },
        "region_units": region_units,
        "frame": relation_manifest["frame"],
        "bounds": relation_manifest["bounds"],
        "sources": sources,
        "relations": relations,
        "classes": cfg["classes"],
        "reasons": relation_manifest["reasons"],
        "render_queue_classes": cfg["render_queue_classes"],
        "patches": {
            "core_count": count,
            "patch_count": patch_count,
            "selected_profile": patch_technical["selected_profile"],
            "raw_class_counts": _class_counts(membership["raw_relation_class"]),
            "patch_class_counts": _class_counts(membership["patch_relation_class"]),
            "status_counts": _status_counts(membership["patch_status"]),
            "assigned_core_count": int(np.count_nonzero(membership["patch_id"])),
            "unassigned_core_count": int(np.count_nonzero(membership["patch_id"] == 0)),
            "assets": patch_assets,
        },
        "patch_statuses": statuses,
        "unassigned_reasons": patch_technical.get("unassigned_reason_names", cfg["unassigned_reason_names"]),
        "source_family_colors": {"0": cfg["source_colors"]["mvs"], "1": cfg["source_colors"]["als"]},
        "active_tiles": relation_manifest["active_tiles"],
        "display_sampling": cfg["display_sampling"],
        "prohibited_inputs_accessed": [],
        "scientific_verdict": None,
    }
    atomic_json(viewer / "viewer_manifest.json", manifest)
    outputs = {}
    excluded = {"viewer_build_receipt.json", "viewer_validation_receipt.json"}
    for path in sorted(item for item in viewer.rglob("*") if item.is_file() and item.name not in excluded):
        outputs[path.relative_to(viewer).as_posix()] = {
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
    receipt = {
        "schema": "jointbuildgs.phd.mvs_als_surface_patch.viewer_build.v1",
        "task_id": cfg["task_id"],
        "status": "COMPLETE_DEVELOPMENT_NON_CONFIRMATORY",
        "config": {"path": str(config_path), "sha256": sha256(config_path)},
        "builder": {"path": str(Path(__file__)), "sha256": sha256(Path(__file__))},
        "inputs": {
            "source_relation_viewer_manifest": record(relation_root / "viewer_manifest.json", relation_root),
            "surface_patch_artifact_manifest": record(patch_files["artifact_manifest.json"], patch_root),
            "surface_patch_validation_receipt": record(patch_files["validation_receipt.json"], patch_root),
            "region_unit_artifact_manifest": record(unit_files["artifact_manifest.json"], unit_root),
            "region_unit_validation_receipt": record(unit_files["validation_receipt.json"], unit_root),
        },
        "relation_core_count": count,
        "patch_count": patch_count,
        "region_unit_count": int(len(units)),
        "region_unit_cell_count": int(len(cells)),
        "outputs": outputs,
        "prohibited_inputs_accessed": [],
        "scientific_verdict": None,
    }
    atomic_json(viewer / "viewer_build_receipt.json", receipt)
    return receipt


def validate(cfg: dict[str, Any]) -> dict[str, Any]:
    artifact_root = Path(cfg["artifact_root"])
    viewer = artifact_root / cfg["viewer_output_relative_root"]
    manifest = json.loads((viewer / "viewer_manifest.json").read_text(encoding="utf-8"))
    build_receipt = json.loads((viewer / "viewer_build_receipt.json").read_text(encoding="utf-8"))
    if manifest.get("scientific_verdict", "missing") is not None:
        raise AssertionError("viewer scientific_verdict must remain null")
    # re-verify the upstream pins so a standalone validate detects stale T0/patch/relation assets
    verify_relation_upstream(cfg, artifact_root / cfg["source_relation_viewer_relative_root"])
    verify_patch_upstream(cfg, artifact_root / cfg["surface_patch_relative_root"])
    unit_root = artifact_root / cfg["region_unit_relative_root"]
    verify_region_unit_upstream(cfg, unit_root)
    for key, root in (("region_unit_artifact_manifest", unit_root / "artifact_manifest.json"),
                      ("region_unit_validation_receipt", unit_root / "validation_receipt.json")):
        if manifest["upstreams"][key]["sha256"] != sha256(root):
            raise AssertionError(f"viewer assets are stale relative to the current {key}")
    if manifest.get("prohibited_inputs_accessed") != []:
        raise AssertionError("prohibited viewer input access is not empty")
    if manifest.get("comparison_contract", {}).get("m3c2_recomputed") is not False:
        raise AssertionError("viewer contract must not recompute M3C2")
    if manifest.get("comparison_contract", {}).get("candidate_evidence_never_smoothed_to_compatible") is not True:
        raise AssertionError("viewer candidate-safe aggregation contract drift")
    count = int(manifest["relations"]["count"])
    if count != int(manifest["patches"]["core_count"]):
        raise AssertionError("relation/patch core count mismatch")
    checks = 0
    for item in manifest["sources"].values():
        path = viewer / item["path"]
        if path.stat().st_size != int(item["count"]) * 12 or sha256(path) != item["sha256"]:
            raise AssertionError(f"source asset mismatch: {item['path']}")
        checks += 1
    relation_widths = {"xyz": 12, "attributes": 4, "metrics": 24, "support_counts": 8}
    for name, width in relation_widths.items():
        item = manifest["relations"][name]
        path = viewer / item["path"]
        if path.stat().st_size != count * width or sha256(path) != item["sha256"]:
            raise AssertionError(f"relation asset mismatch: {name}")
        checks += 1
    patch_count = int(manifest["patches"]["patch_count"])
    for name, item in manifest["patches"]["assets"].items():
        rows = patch_count if name.startswith("summary_") else count
        path = viewer / item["path"]
        if path.stat().st_size != rows * int(item["stride_bytes"]) or sha256(path) != item["sha256"]:
            raise AssertionError(f"patch asset mismatch: {name}")
        checks += 1
    units_block = manifest["region_units"]
    unit_rows = {"cells": int(units_block["cell_count"]), "units": int(units_block["unit_count"]),
                 "adjacency": int(units_block["adjacency_count"])}
    for name, item in units_block["assets"].items():
        rows = unit_rows["adjacency"] if name == "adjacency" else unit_rows["cells"] if name.startswith("cells_") else unit_rows["units"]
        path = viewer / item["path"]
        if path.stat().st_size != rows * int(item["stride_bytes"]) or sha256(path) != item["sha256"]:
            raise AssertionError(f"region-unit asset mismatch: {name}")
        checks += 1
    unit_ids = np.fromfile(viewer / units_block["assets"]["cells_unit"]["path"], dtype="<u4")
    if np.any(unit_ids == 0) or np.any(unit_ids > unit_rows["units"]):
        raise AssertionError("region-unit coverage drift in viewer assets")
    raw = np.fromfile(viewer / manifest["relations"]["attributes"]["path"], dtype=np.uint8).reshape(-1, 4)[:, 0]
    patch = np.fromfile(viewer / manifest["patches"]["assets"]["attributes"]["path"], dtype=np.uint8).reshape(-1, 4)[:, 0]
    if _class_counts(raw) != manifest["patches"]["raw_class_counts"]:
        raise AssertionError("raw five-class count drift")
    if _class_counts(patch) != manifest["patches"]["patch_class_counts"]:
        raise AssertionError("patch five-class count drift")
    uids = np.fromfile(viewer / manifest["patches"]["assets"]["summary_uids"]["path"], dtype="S20")
    if len(set(map(bytes, uids))) != patch_count or np.any(uids == b""):
        raise AssertionError("patch UID integrity drift")
    for name, item in build_receipt["outputs"].items():
        path = viewer / name
        if not path.is_file() or path.stat().st_size != int(item["bytes"]) or sha256(path) != item["sha256"]:
            raise AssertionError(f"build output drift: {name}")
    for name in ("index.html", "app.js", "styles.css"):
        text = (viewer / name).read_text(encoding="utf-8")
        if "https://" in text or "http://" in text:
            raise AssertionError(f"viewer has an unpinned remote dependency: {name}")
    receipt = {
        "schema": "jointbuildgs.phd.mvs_als_surface_patch.viewer_validation.v1",
        "task_id": cfg["task_id"],
        "checks": {
            "upstream_hashes_and_validation": "PASS",
            "asset_hashes_and_strides": "PASS",
            "raw_five_class_preserved": "PASS",
            "patch_five_class_and_uid_integrity": "PASS",
            "both_source_layers": "PASS",
            "region_unit_assets_and_full_coverage": "PASS",
            "offline_dependencies": "PASS",
            "m3c2_not_recomputed": "PASS",
            "candidate_evidence_never_smoothed_to_compatible": "PASS",
            "scientific_verdict_null": "PASS",
            "prohibited_inputs": "PASS"
        },
        "assets_checked": checks,
        "relation_core_count": count,
        "patch_count": patch_count,
        "region_unit_count": unit_rows["units"],
        "scientific_verdict": None,
    }
    atomic_json(viewer / "viewer_validation_receipt.json", receipt)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("command", choices=("build", "validate", "build-and-validate"))
    args = parser.parse_args()
    config_path = args.config.resolve()
    cfg = load_config(config_path)
    if args.command in {"build", "build-and-validate"}:
        print(json.dumps(build(cfg, config_path), indent=2))
    if args.command in {"validate", "build-and-validate"}:
        print(json.dumps(validate(cfg), indent=2))


if __name__ == "__main__":
    main()
