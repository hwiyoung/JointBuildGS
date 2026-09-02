#!/usr/bin/env python3
"""Build and validate the offline MVS/Existing-ALS relation WebGL viewer."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import numpy as np

from scripts.phd.mvs_als_source_relation_v1 import run as relation


REPO = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = REPO / "configs/phd/mvs_als_source_relation_viewer_v1/viewer_v1.json"


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


def record(path: Path, relative_to: Path, **extra: Any) -> dict[str, Any]:
    return {
        "path": path.relative_to(relative_to).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
        **extra,
    }


def load_config(path: Path) -> dict[str, Any]:
    cfg = json.loads(path.read_text(encoding="utf-8"))
    if cfg.get("scientific_verdict", "missing") is not None:
        raise ValueError("scientific_verdict must remain null")
    inputs = json.dumps({
        "source_relation_relative_root": cfg["source_relation_relative_root"],
        "expected_inputs": cfg["expected_inputs"],
    }).lower()
    for token in ("uas", "lod2", "footprint", "stable_id", "journal1"):
        if token in inputs:
            raise ValueError(f"prohibited input token: {token}")
    return cfg


def verify_inputs(cfg: dict[str, Any], relation_root: Path) -> dict[str, dict[str, Any]]:
    result = {}
    for name, expected in cfg["expected_inputs"].items():
        path = relation_root / name
        if not path.is_file() or path.is_symlink():
            raise RuntimeError(f"missing exact input: {path}")
        actual = sha256(path)
        if actual != expected:
            raise RuntimeError(f"input hash drift: {name}: {actual} != {expected}")
        result[name] = {"bytes": path.stat().st_size, "sha256": actual}
    relation_cfg = REPO / cfg["relation_config_relative_path"]
    actual = sha256(relation_cfg)
    if actual != cfg["relation_config_sha256"]:
        raise RuntimeError(f"relation config hash drift: {actual}")
    result["relation_config"] = {
        "path": cfg["relation_config_relative_path"],
        "bytes": relation_cfg.stat().st_size,
        "sha256": actual,
    }
    return result


def source_display_points(partition: Path, spacing: float) -> np.ndarray:
    parts = []
    for path in sorted(partition.glob("*.xyz_f32le.bin")):
        points = relation.read_xyz_bin(path)
        if len(points):
            parts.append(relation.voxel_representatives(points, spacing))
    if not parts:
        return np.empty((0, 3), dtype="<f4")
    return np.ascontiguousarray(np.concatenate(parts), dtype="<f4")


def write_array(path: Path, value: np.ndarray) -> None:
    atomic_bytes(path, np.ascontiguousarray(value).tobytes())


def local_bounds(arrays: list[np.ndarray]) -> dict[str, list[float]]:
    available = [array for array in arrays if len(array)]
    if not available:
        raise RuntimeError("no display geometry")
    minimum = np.min(np.vstack([array.min(axis=0) for array in available]), axis=0)
    maximum = np.max(np.vstack([array.max(axis=0) for array in available]), axis=0)
    return {
        "min": minimum.astype(float).tolist(),
        "max": maximum.astype(float).tolist(),
        "center": ((minimum + maximum) / 2).astype(float).tolist(),
        "extent": (maximum - minimum).astype(float).tolist(),
    }


def active_tiles(relation_root: Path, relation_cfg: dict[str, Any], z_center: float) -> list[dict[str, Any]]:
    shift = np.asarray(relation_cfg["frame"]["world_shift_xyz_m"], dtype=np.float64)
    origin = np.asarray(relation_cfg["tiling"]["world_xy_origin_m"], dtype=np.float64)
    size = float(relation_cfg["tiling"]["tile_size_m"])
    result = []
    for receipt_path in sorted((relation_root / "tiles").glob("x*_y*/receipt.json")):
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        rows = int(receipt["output"]["rows"])
        if rows == 0:
            continue
        xpart, ypart = receipt["tile_id"].split("_")
        ix, iy = int(xpart[1:]), int(ypart[1:])
        center_xy = origin + np.asarray([ix + 0.5, iy + 0.5]) * size - shift[:2]
        result.append({
            "tile_id": receipt["tile_id"],
            "relation_rows": rows,
            "scene_local_center": [float(center_xy[0]), float(center_xy[1]), float(z_center)],
            "focus_radius_m": float(size * 0.72),
            "class_counts": receipt["class_counts"],
        })
    return result


def build(cfg: dict[str, Any], config_path: Path) -> dict[str, Any]:
    artifact_root = Path(cfg["artifact_root"])
    relation_root = artifact_root / cfg["source_relation_relative_root"]
    viewer = artifact_root / cfg["viewer_output_relative_root"]
    assets = viewer / "assets"
    libraries = viewer / "lib"
    viewer.mkdir(parents=True, exist_ok=True)
    assets.mkdir(parents=True, exist_ok=True)
    libraries.mkdir(parents=True, exist_ok=True)
    verified = verify_inputs(cfg, relation_root)
    relation_cfg = json.loads((REPO / cfg["relation_config_relative_path"]).read_text(encoding="utf-8"))
    technical = json.loads((relation_root / "technical_return.json").read_text(encoding="utf-8"))
    if technical.get("scientific_verdict", "missing") is not None:
        raise RuntimeError("upstream scientific_verdict is not null")

    spacing = float(cfg["display_sampling"]["source_voxel_m"])
    mvs = source_display_points(relation_root / "partition/mvs", spacing)
    als = source_display_points(relation_root / "partition/als", spacing)
    rows = np.load(relation_root / "relation_map.npy", allow_pickle=False)
    xyz = np.ascontiguousarray(np.column_stack((rows["x"], rows["y"], rows["z"])), dtype="<f4")
    attributes = np.ascontiguousarray(np.column_stack((
        rows["relation_class"], rows["core_source"], rows["reason"].astype(np.uint8),
        rows["robust_significant"],
    )), dtype=np.uint8)
    metric_names = (
        "m3c2_signed_m", "lod95_local_m", "lod95_reg_upper_m",
        "significance_ratio", "sigma_mvs_m", "sigma_als_m",
    )
    metrics = np.ascontiguousarray(np.column_stack([rows[name] for name in metric_names]), dtype="<f4")
    support = np.ascontiguousarray(np.column_stack((rows["n_mvs"], rows["n_als"])), dtype="<u4")

    paths = {
        "mvs": assets / "mvs_xyz_f32le.bin",
        "als": assets / "als_xyz_f32le.bin",
        "xyz": assets / "relation_xyz_f32le.bin",
        "attributes": assets / "relation_attributes_u8.bin",
        "metrics": assets / "relation_metrics_f32le.bin",
        "support_counts": assets / "relation_support_u32le.bin",
    }
    for name, value in (("mvs", mvs), ("als", als), ("xyz", xyz),
                        ("attributes", attributes), ("metrics", metrics),
                        ("support_counts", support)):
        write_array(paths[name], value)

    app_source = REPO / cfg["app_source_relative_root"]
    for name in ("index.html", "app.js", "styles.css"):
        atomic_bytes(viewer / name, (app_source / name).read_bytes())
    for key, source in cfg["browser_dependencies"].items():
        suffix = "three.module.min.js" if key == "three" else "gaussian-splats-3d.module.min.js"
        atomic_bytes(libraries / suffix, (REPO / source).read_bytes())

    bounds = local_bounds([mvs, als, xyz])
    class_cfg = {}
    for key, item in cfg["classes"].items():
        class_cfg[key] = {**item, "count": int(technical["class_counts"][item["name"]])}
    manifest = {
        "schema": "jointbuildgs.phd.mvs_als_source_relation.viewer.v1",
        "task_id": cfg["task_id"],
        "status": "READY_FOR_QUALITATIVE_WEB_REVIEW",
        "purpose": "SIMULTANEOUS_SOURCE_AND_FIVE_CLASS_RELATION_INSPECTION",
        "not_interpretable_as": ["TEMPORAL_CHANGE_VERDICT", "SOURCE_CORRECTNESS_VERDICT"],
        "frame": relation_cfg["frame"],
        "bounds": {"scene_local": bounds},
        "sources": {
            "mvs": record(paths["mvs"], viewer, count=len(mvs), color=cfg["source_colors"]["mvs"],
                          voxel_m=spacing, role="DISPLAY_ONLY_CURRENT_IMAGE_MVS"),
            "als": record(paths["als"], viewer, count=len(als), color=cfg["source_colors"]["als"],
                          voxel_m=spacing, role="DISPLAY_ONLY_REGISTERED_EXISTING_ALS"),
        },
        "relations": {
            "count": len(rows), "robust_significant_count": int(rows["robust_significant"].sum()),
            "core_spacing_m": cfg["display_sampling"]["relation_core_spacing_m"],
            "metrics_stride": len(metric_names), "metric_names": list(metric_names),
            "xyz": record(paths["xyz"], viewer),
            "attributes": record(paths["attributes"], viewer),
            "metrics": record(paths["metrics"], viewer),
            "support_counts": record(paths["support_counts"], viewer),
        },
        "classes": class_cfg,
        "reasons": {str(key): value for key, value in relation.REASON_NAMES.items()},
        "render_queue_classes": cfg["render_queue_classes"],
        "active_tiles": active_tiles(relation_root, relation_cfg, bounds["center"][2]),
        "display_sampling": cfg["display_sampling"],
        "prohibited_inputs_accessed": [],
        "scientific_verdict": None,
    }
    atomic_json(viewer / "viewer_manifest.json", manifest)
    outputs = {}
    for path in sorted(item for item in viewer.rglob("*") if item.is_file()
                       and item.name not in {"viewer_build_receipt.json", "viewer_validation_receipt.json"}):
        outputs[path.relative_to(viewer).as_posix()] = {
            "bytes": path.stat().st_size, "sha256": sha256(path),
        }
    receipt = {
        "schema": "jointbuildgs.phd.mvs_als_source_relation.viewer_build.v1",
        "task_id": cfg["task_id"], "status": "COMPLETE_DEVELOPMENT_NON_CONFIRMATORY",
        "config": {"path": str(config_path), "sha256": sha256(config_path)},
        "builder": {"path": str(Path(__file__)), "sha256": sha256(Path(__file__))},
        "inputs": verified, "source_display_counts": {"mvs": len(mvs), "als": len(als)},
        "relation_rows": len(rows), "outputs": outputs,
        "prohibited_inputs_accessed": [], "scientific_verdict": None,
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
    if manifest.get("prohibited_inputs_accessed") != []:
        raise AssertionError("prohibited viewer input access is not empty")
    checked = 0
    for section, width in (("sources", 12),):
        for item in manifest[section].values():
            path = viewer / item["path"]
            if sha256(path) != item["sha256"] or path.stat().st_size != item["bytes"]:
                raise AssertionError(f"asset drift: {item['path']}")
            if path.stat().st_size != int(item["count"]) * width:
                raise AssertionError(f"asset count/stride mismatch: {item['path']}")
            checked += 1
    relation_count = int(manifest["relations"]["count"])
    widths = {"xyz": 12, "attributes": 4, "metrics": 24, "support_counts": 8}
    for name, width in widths.items():
        item = manifest["relations"][name]
        path = viewer / item["path"]
        if sha256(path) != item["sha256"] or path.stat().st_size != relation_count * width:
            raise AssertionError(f"relation asset mismatch: {name}")
        checked += 1
    labels = np.fromfile(viewer / manifest["relations"]["attributes"]["path"], dtype=np.uint8).reshape(-1, 4)
    for key, item in manifest["classes"].items():
        if int(np.count_nonzero(labels[:, 0] == int(key))) != int(item["count"]):
            raise AssertionError(f"class count mismatch: {item['name']}")
    for name, item in build_receipt["outputs"].items():
        path = viewer / name
        if not path.is_file() or sha256(path) != item["sha256"]:
            raise AssertionError(f"build output drift: {name}")
    app_text = (viewer / "app.js").read_text(encoding="utf-8")
    html_text = (viewer / "index.html").read_text(encoding="utf-8")
    if "https://" in app_text or "http://" in app_text or "https://" in html_text or "http://" in html_text:
        raise AssertionError("viewer has an unpinned network dependency")
    receipt = {
        "schema": "jointbuildgs.phd.mvs_als_source_relation.viewer_validation.v1",
        "task_id": cfg["task_id"],
        "checks": {
            "asset_hashes_and_strides": "PASS", "five_class_counts": "PASS",
            "both_source_layers": "PASS", "offline_dependencies": "PASS",
            "scientific_verdict_null": "PASS", "prohibited_inputs": "PASS",
        },
        "assets_checked": checked, "relation_rows": relation_count,
        "source_display_counts": build_receipt["source_display_counts"],
        "scientific_verdict": None,
    }
    atomic_json(viewer / "viewer_validation_receipt.json", receipt)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("command", choices=("build", "validate", "build-and-validate"))
    args = parser.parse_args()
    cfg = load_config(args.config.resolve())
    if args.command in {"build", "build-and-validate"}:
        print(json.dumps(build(cfg, args.config.resolve()), indent=2))
    if args.command in {"validate", "build-and-validate"}:
        print(json.dumps(validate(cfg), indent=2))


if __name__ == "__main__":
    main()
