#!/usr/bin/env python3
"""Add the completed full-scene E3 30k result to the live 8876 viewer."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
from typing import Any

import laspy
import numpy as np

from scripts.p2.c1_c2_shared_footprint_199_v3.build_cloudcompare_review10 import (
    lod22_triangles,
    triangles_obj,
)


REPO = Path(__file__).resolve().parents[3]
CONFIG = REPO / "configs/p2/viewer_8876_new_e3_fullscene_30k_v1/run_v1.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def record(path: Path, relative_to: Path | None = None) -> dict[str, Any]:
    return {
        "path": path.relative_to(relative_to).as_posix() if relative_to else path.as_posix(),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def exact(path: Path, expected: dict[str, Any]) -> None:
    if not path.is_file() or path.stat().st_size != expected["bytes"] or sha256(path) != expected["sha256"]:
        raise RuntimeError(f"exact input drift: {path}")


def atomic_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(data)
    os.replace(temporary, path)


def canonical_json(data: Any) -> bytes:
    return (json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def load_config(path: Path) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    if config.get("schema") != "jointbuildgs.p2.viewer_8876_new_e3_fullscene_30k.v1":
        raise RuntimeError("unexpected config schema")
    if config.get("status") != "USER_APPROVED_FOR_EXECUTION":
        raise RuntimeError("viewer update is not approved")
    if config.get("scientific_verdict", "missing") is not None or config.get("official_PASS_usable", "missing") is not None:
        raise RuntimeError("verdict fields must remain null")
    if any(int(config["execution"][key]) != 0 for key in ("gs_training_invocations", "roofer_invocations", "reconstruction_invocations")):
        raise RuntimeError("viewer-only task must not execute an experiment")
    return config


def point_assets(source: Path, output: Path, shift: np.ndarray, cap: int) -> tuple[dict[str, Any], dict[str, Path]]:
    counts = {2: 0, 6: 0}
    with laspy.open(source) as reader:
        for chunk in reader.chunk_iterator(2_000_000):
            classes = np.asarray(chunk.classification, dtype=np.uint8)
            for code in counts:
                counts[code] += int(np.count_nonzero(classes == code))
    stride = max(1, int(math.ceil(sum(counts.values()) / cap)))
    temporary_paths = {name: output / f"E3_FULLSCENE_30K_roofer_{name}_xyz_f32.bin" for name in ("ground", "building")}
    streams = {name: path.open("wb") for name, path in temporary_paths.items()}
    offsets = {2: 0, 6: 0}
    display_counts = {2: 0, 6: 0}
    try:
        with laspy.open(source) as reader:
            for chunk in reader.chunk_iterator(1_000_000):
                classes = np.asarray(chunk.classification, dtype=np.uint8)
                xyz = np.column_stack((np.asarray(chunk.x), np.asarray(chunk.y), np.asarray(chunk.z))).astype(np.float64)
                for code, name in ((2, "ground"), (6, "building")):
                    indices = np.flatnonzero(classes == code)
                    if not len(indices):
                        continue
                    keep = ((np.arange(len(indices), dtype=np.int64) + offsets[code]) % stride) == 0
                    selected = np.ascontiguousarray(xyz[indices[keep]] - shift, dtype="<f4")
                    streams[name].write(selected.tobytes())
                    display_counts[code] += int(len(selected))
                    offsets[code] += int(len(indices))
    finally:
        for stream in streams.values():
            stream.close()
    metadata = {
        "exact_source": source.as_posix(),
        "exact_source_sha256": sha256(source),
        "exact_class_counts": {str(code): value for code, value in counts.items()},
        "display_classes": [2, 6],
        "display_decimation": f"DETERMINISTIC_CLASS_STREAM_EVERY_{stride}TH_POINT",
        "display_class_counts": {str(code): value for code, value in display_counts.items()},
        "display_point_count": sum(display_counts.values()),
    }
    return metadata, temporary_paths


def roofer_obj(source: Path, output: Path, shift: np.ndarray) -> tuple[dict[str, Any], Path]:
    cityjson = json.loads(source.read_text(encoding="utf-8"))
    triangles: list[np.ndarray] = []
    building_count = 0
    for stable_id, city_object in cityjson["CityObjects"].items():
        if city_object.get("type") != "Building":
            continue
        selected = lod22_triangles(cityjson, stable_id)
        if selected:
            building_count += 1
            triangles.extend(selected)
    path = output / "E3_FULLSCENE_30K.obj"
    path.write_bytes(triangles_obj("E3_FULLSCENE_30K", "viewer.mtl", "E3", triangles, shift))
    return {"building_count_with_lod22": building_count, "triangle_count": len(triangles)}, path


def patch_app(text: str) -> str:
    marker = "function setRooferWireframe(object, enabled) {"
    helper = """function rooferObjectVisible(spec) {
  return rooferMeshesVisible || (surfaceMeshesVisible && spec.surface_fallback_to_roofer === true);
}

"""
    if "function rooferObjectVisible" not in text:
        if marker not in text:
            raise RuntimeError("8876 app visibility marker drifted")
        text = text.replace(marker, helper + marker)
    text = text.replace("  object.visible = rooferMeshesVisible;", "  object.visible = rooferObjectVisible(spec);", 1)
    text = text.replace("    viewer.object.visible = rooferMeshesVisible;", "    viewer.object.visible = rooferObjectVisible(next.spec);")
    text = text.replace(
        "  for (const viewer of viewers) viewer.surface.visible = surfaceMeshesVisible;",
        "  for (const viewer of viewers) { viewer.surface.visible = surfaceMeshesVisible; viewer.object.visible = rooferObjectVisible(viewer.spec); }",
    )
    text = text.replace(
        "  for (const viewer of viewers) viewer.object.visible = rooferMeshesVisible;",
        "  for (const viewer of viewers) viewer.object.visible = rooferObjectVisible(viewer.spec);",
    )
    text = text.replace(
        "? 'E1 UAS LiDAR 전체 범위 + E2 OpenMVS + E3-E6 TSDF 표면 mesh 표시'",
        "? '표면 mesh 표시 · 새 E3 30k는 surface 미생성으로 Roofer LoD fallback 표시'",
    )
    return text


def updated_manifest(manifest: dict[str, Any], variant: dict[str, Any], receipt_path: str) -> dict[str, Any]:
    panels = manifest["panels"]
    panel = next(item for item in panels if str(item.get("condition", "")).startswith("E3"))
    variants = panel.setdefault("variants", [])
    if any(item.get("id") == variant["id"] for item in variants):
        raise RuntimeError("new E3 variant id already exists")
    variants.append(variant)
    for key, value in variant.items():
        if key != "variants":
            panel[key] = value
    panel["variants"] = variants
    panel["variant_selection_rule"] = "NEW_FULLSCENE_30K_DEFAULT_WITH_ALL_PREVIOUS_VARIANTS_PRESERVED"
    manifest["e3_default_variant"] = variant["id"]
    manifest["e3_default_update_receipt"] = receipt_path
    manifest["scientific_verdict"] = None
    return manifest


def build(config_path: Path, artifact_root: Path) -> dict[str, Any]:
    config = load_config(config_path)
    viewer = artifact_root / config["viewer_relative_root"]
    task = artifact_root / config["task_relative_root"]
    partial = task.with_name(task.name + ".partial")
    if task.exists():
        raise RuntimeError("fresh add-once task namespace required")
    for name, expected in config["prestate"].items():
        exact(viewer / name, expected)
    for item in config["source"].values():
        exact(artifact_root / item["path"], item)

    partial.mkdir(parents=True, exist_ok=True)
    prestate = partial / "prestate"
    prestate.mkdir(exist_ok=True)
    for name in config["prestate"]:
        backup = prestate / name
        if backup.exists():
            exact(backup, config["prestate"][name])
        else:
            shutil.copy2(viewer / name, backup)
    staging = partial / "staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir()
    shift = np.asarray(config["variant"]["world_shift_epsg25832"], dtype=np.float64)
    classified = artifact_root / config["source"]["classified_scene"]["path"]
    cityjson = artifact_root / config["source"]["assembled_cityjson"]["path"]
    point_metadata, point_paths = point_assets(classified, staging, shift, int(config["variant"]["maximum_display_points"]))
    roofer_metadata, obj_path = roofer_obj(cityjson, staging, shift)

    live_assets = viewer / "assets"
    promoted: dict[str, dict[str, Any]] = {}
    for name, staged in {"ground": point_paths["ground"], "building": point_paths["building"], "roofer": obj_path}.items():
        destination = live_assets / staged.name
        if destination.exists():
            if destination.stat().st_size != staged.stat().st_size or sha256(destination) != sha256(staged):
                raise RuntimeError(f"cache-distinct live asset collision: {destination}")
            staged.unlink()
        else:
            os.replace(staged, destination)
        promoted[name] = record(destination, viewer)

    variant = {
        "id": config["variant"]["id"],
        "label": config["variant"]["label"],
        "type": "mesh",
        "asset": promoted["roofer"]["path"],
        "color": "#8b5cf6",
        "condition": "E3",
        "step": config["variant"]["step"],
        "validation_selected": False,
        "selection_role": "USER_SELECTED_NEW_E3_TECHNICAL_BASE",
        "lineage_label": "NEW_E3_30K_FUSED_NORMAL_CONFIDENCE",
        "roofer_pointcloud": {
            **point_metadata,
            "assets": {"ground": promoted["ground"]["path"], "building": promoted["building"]["path"]},
            "asset_sha256": {"ground": promoted["ground"]["sha256"], "building": promoted["building"]["sha256"]},
        },
        "surface_mesh": None,
        "surface_mesh_status": config["variant"]["surface_mesh_status"],
        "surface_fallback_to_roofer": True,
        "official_PASS_usable": None,
        "scientific_verdict": None,
    }
    manifest_path = viewer / "viewer_manifest.json"
    manifest = updated_manifest(
        json.loads(manifest_path.read_text(encoding="utf-8")),
        variant,
        f"{config['task_relative_root']}/receipt_v1.json",
    )
    app_text = patch_app((viewer / "app.js").read_text(encoding="utf-8"))
    index_text = (viewer / "index.html").read_text(encoding="utf-8")
    old_script = "app.js?v=e1e6-20260811-final-rectilinear-common-v4"
    if old_script not in index_text:
        raise RuntimeError("8876 index cache marker drifted")
    index_text = index_text.replace(old_script, "app.js?v=e3-fullscene-30k-20260811-v1")
    atomic_bytes(manifest_path, canonical_json(manifest))
    atomic_bytes(viewer / "app.js", app_text.encode("utf-8"))
    atomic_bytes(viewer / "index.html", index_text.encode("utf-8"))

    receipt = {
        "schema": "jointbuildgs.p2.viewer_8876_new_e3_fullscene_30k.receipt.v1",
        "task_id": config["task_id"],
        "status": "TECHNICAL_COMPLETE",
        "source": {name: record(artifact_root / item["path"], artifact_root) for name, item in config["source"].items()},
        "prestate": {name: record(prestate / name, partial) for name in config["prestate"]},
        "promoted_assets": promoted,
        "roofer_display": roofer_metadata,
        "pointcloud_display": point_metadata,
        "viewer_poststate": {name: record(viewer / name, viewer) for name in config["prestate"]},
        "previous_variants_preserved": True,
        "default_variant": variant["id"],
        "surface_mesh_status": variant["surface_mesh_status"],
        "execution": config["execution"],
        "official_PASS_usable": None,
        "scientific_verdict": None,
    }
    atomic_bytes(partial / "receipt_v1.json", canonical_json(receipt))
    shutil.rmtree(staging)
    os.rename(partial, task)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--artifact-root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.config, args.artifact_root), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
