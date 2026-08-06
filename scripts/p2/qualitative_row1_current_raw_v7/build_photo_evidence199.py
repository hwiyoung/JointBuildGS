#!/usr/bin/env python3
"""Build deterministic four-view photo evidence for the frozen 199-building population."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import PIL
from PIL import Image

from scripts.evidence_and_attributes.population_analysis import population_aux_v3 as projection
from scripts.p2.c1_c2_shared_footprint_199_v3.build_cloudcompare_review10 import (
    descendant_ids,
    transformed_vertices,
)
from scripts.p2.qualitative_199_cloudcompare_scene_v1.build_scene import (
    canonical_json_bytes,
    file_record,
    sha256_file,
    write_new,
)
from scripts.p2.qualitative_row1_current_raw_v3.preview import image_inventory, verify_file
from scripts.p2.qualitative_row1_current_raw_v4 import preview10 as v4
from scripts.p2.qualitative_row1_current_raw_v5.preview10 import ordered_boundary_loops
from scripts.p2.qualitative_row1_current_raw_v6 import preview10 as v6
from scripts.p2.qualitative_row1_current_raw_v6 import preview10_v2 as v6_v2
from scripts.p2.qualitative_row1_current_raw_v6 import preview10_v3 as v6_v3
from scripts.p2.utarget199_presentation_v5.render import load_references


REPO = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = REPO / "configs/p2/qualitative_row1_current_raw_v7/photo_evidence199_v1.json"
FALLBACK_SOURCE = v6_v3.GEOMETRY_FALLBACK_SOURCE


def load_config(path: Path) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    if config.get("schema") != "jointbuildgs.p2.qualitative_row1_current_raw.photo_evidence199.v1":
        raise RuntimeError("unexpected photo evidence config schema")
    if config.get("status") != "USER_APPROVED_FULL_199_PHOTO_EVIDENCE_EXECUTION":
        raise RuntimeError("full 199 photo evidence execution is not approved")
    if config.get("scientific_verdict", "missing") is not None:
        raise RuntimeError("scientific_verdict must remain null")
    if config["population"] != {
        "building_count": 199,
        "population_indices": "INCLUSIVE_1_TO_199",
        "panels_per_building": 4,
        "roles": ["TOP", "RANDOM_1", "RANDOM_2", "RANDOM_3"],
    }:
        raise RuntimeError("199-building four-view population contract drifted")
    if config["overlays"]["keypoints_rendered"] or config["overlays"]["partial_loops_rendered"]:
        raise RuntimeError("keypoints and partial loops are prohibited")
    if config["overlays"]["terminal_geometry_fallback"] != "PHOTO_ONLY_NO_OVERLAY":
        raise RuntimeError("terminal fallback must remain photo-only")
    if config["reference_temporal_review"]["labels"] != [
        "", "CURRENT_MATCH_VERIFIED", "TEMPORAL_CHANGE_SUSPECTED", "UNDECIDABLE", "REFERENCE_MISSING"
    ]:
        raise RuntimeError("reference temporal labels drifted")
    if any(int(config["execution"].get(key, -1)) != 0 for key in (
        "roofer_invocations", "reconstruction_invocations", "gs_training_invocations", "metric_recomputations"
    )):
        raise RuntimeError("photo evidence must not invoke reconstruction")
    return config


def load_contract_chain(config: Mapping[str, Any], repo_root: Path, artifact_root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    frozen = config["selection_contract"]
    v6_path = repo_root / frozen["git_path"]
    verify_file(v6_path, frozen["sha256"], "v6-v4 selection contract", int(frozen["bytes"]))
    anchor = artifact_root / frozen["anchor_relative_root"]
    verify_file(anchor / frozen["anchor_selection_relative_path"], frozen["anchor_selection_sha256"], "v6-v4 anchor selection")
    verify_file(anchor / frozen["anchor_manifest_relative_path"], frozen["anchor_manifest_sha256"], "v6-v4 anchor manifest", int(frozen["anchor_manifest_bytes"]))
    v6_contract = json.loads(v6_path.read_text(encoding="utf-8"))
    v5_path = repo_root / v6_contract["base_contract"]["git_path"]
    verify_file(v5_path, v6_contract["base_contract"]["sha256"], "v5 contract", int(v6_contract["base_contract"]["bytes"]))
    v5_contract = json.loads(v5_path.read_text(encoding="utf-8"))
    v4_path = repo_root / v5_contract["base_contract"]["git_path"]
    verify_file(v4_path, v5_contract["base_contract"]["sha256"], "v4 contract", int(v5_contract["base_contract"]["bytes"]))
    return v6_contract, v5_contract, json.loads(v4_path.read_text(encoding="utf-8"))


def verify_inputs(base: Mapping[str, Any], repo_root: Path, artifact_root: Path) -> dict[str, Any]:
    inputs = base["inputs"]
    common = artifact_root / inputs["common_manifest_relative_root"]
    bindings = {
        "building_manifest": verify_file(common / inputs["building_manifest_relative_path"], inputs["building_manifest_sha256"], "building manifest"),
        "image_inventory": verify_file(repo_root / inputs["image_inventory_git_path"], inputs["image_inventory_sha256"], "image inventory"),
        "exact_937_crosswalk": verify_file(repo_root / inputs["exact_937_crosswalk_git_path"], inputs["exact_937_crosswalk_sha256"], "exact crosswalk"),
        "cameras": verify_file(artifact_root / inputs["cameras_relative_path"], inputs["cameras_sha256"], "cameras"),
        "images": verify_file(artifact_root / inputs["images_relative_path"], inputs["images_sha256"], "images"),
        "points3D": verify_file(artifact_root / inputs["points3d_relative_path"], inputs["points3d_sha256"], "points3D", int(inputs["points3d_bytes"])),
        "scene_reference": verify_file(artifact_root / inputs["scene_reference_relative_path"], inputs["scene_reference_sha256"], "scene reference"),
    }
    for index, relative in enumerate(inputs["lod2_relative_paths"]):
        bindings[f"independent_lod2_{index + 1}"] = verify_file(artifact_root / relative, inputs["lod2_sha256"][index], f"LoD2 {index + 1}")
    return bindings


def cityjson_roof_rings(cityjson: Mapping[str, Any], stable_id: str) -> list[np.ndarray]:
    vertices = transformed_vertices(cityjson)
    objects = cityjson["CityObjects"]
    rings: list[np.ndarray] = []
    for object_id in descendant_ids(objects, stable_id):
        for geometry in objects[object_id].get("geometry", []):
            if str(geometry.get("lod")) != "2.2" or geometry.get("type") != "Solid":
                continue
            semantics = geometry.get("semantics", {})
            roof_ids = {
                index for index, surface in enumerate(semantics.get("surfaces", []))
                if surface.get("type") == "RoofSurface"
            }
            values = semantics.get("values", [])
            for shell_index, shell in enumerate(geometry.get("boundaries", [])):
                shell_values = values[shell_index] if shell_index < len(values) else []
                for surface_index, surface_rings in enumerate(shell):
                    semantic_id = shell_values[surface_index] if surface_index < len(shell_values) else None
                    if semantic_id not in roof_ids or not surface_rings:
                        continue
                    ring = np.asarray([vertices[int(vertex_id)] for vertex_id in surface_rings[0]], dtype=np.float64)
                    if len(ring) and not np.allclose(ring[0], ring[-1], atol=1e-8):
                        ring = np.vstack((ring, ring[0]))
                    rings.append(ring)
    return rings


def boundary_loops(rings: Sequence[np.ndarray], tolerance: float) -> tuple[list[np.ndarray], dict[str, Any]]:
    if not rings:
        return [], {"status": "OUTPUT_MISSING", "boundary_loop_count": 0}
    try:
        loops, topology = ordered_boundary_loops(rings, tolerance, True)
        return loops, {"status": "AVAILABLE", **topology}
    except RuntimeError as exc:
        return [], {"status": "BOUNDARY_EXTRACTION_FAILED", "reason": str(exc), "boundary_loop_count": 0}


def complete_polygon_rings(rings: Sequence[np.ndarray]) -> tuple[list[np.ndarray], dict[str, Any]]:
    complete = [np.asarray(ring, dtype=np.float64) for ring in rings if len(ring) >= 4 and np.allclose(ring[0], ring[-1], atol=1e-8)]
    return complete, {
        "status": "AVAILABLE" if complete else "OUTPUT_MISSING",
        "complete_roof_surface_polygon_ring_count": len(complete),
    }


def project_overlay(
    loops: Sequence[np.ndarray], camera: Any, model: tuple[int, int, np.ndarray],
    scene_reference: Mapping[str, Any], crop: Sequence[int], output_size: Sequence[int],
    source_status: Mapping[str, Any], omit: bool, input_datum: str,
) -> dict[str, Any]:
    if omit:
        return {"status": "OMITTED_NO_BUILDING_SPARSE_CONFIRMATION", "polylines": [], "source": source_status}
    if not loops:
        return {"status": source_status["status"], "polylines": [], "source": source_status}
    width, height, params = model
    scale_x = float(output_size[0]) / max(1, int(crop[2]) - int(crop[0]))
    scale_y = float(output_size[1]) / max(1, int(crop[3]) - int(crop[1]))
    polylines = []
    rejected = 0
    for loop in loops:
        uv, front = projection.project(loop, camera, width, height, params, scene_reference, input_datum=input_datum)
        valid = front & np.isfinite(uv).all(axis=1)
        inside = valid & (uv[:, 0] >= crop[0]) & (uv[:, 0] < crop[2]) & (uv[:, 1] >= crop[1]) & (uv[:, 1] < crop[3])
        if not bool(np.all(inside)):
            rejected += 1
            continue
        polylines.append([[round((float(point[0]) - crop[0]) * scale_x, 3), round((float(point[1]) - crop[1]) * scale_y, 3)] for point in uv])
    return {
        "status": "PROJECTED" if polylines else "CLIPPED_OR_OUTSIDE",
        "polylines": polylines,
        "projected_complete_loop_count": len(polylines),
        "rejected_partial_or_outside_loop_count": rejected,
        "source": source_status,
    }


def jpeg_crop(path: Path, crop: Sequence[int], spec: Mapping[str, Any]) -> tuple[bytes, list[int]]:
    with Image.open(path) as opened:
        image = opened.convert("RGB").crop(tuple(map(int, crop)))
    maximum = (int(spec["maximum_width_px"]), int(spec["maximum_height_px"]))
    image.thumbnail(maximum, Image.Resampling.LANCZOS)
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=int(spec["quality"]), subsampling=int(spec["subsampling"]), optimize=bool(spec["optimize"]), progressive=bool(spec["progressive"]))
    return buffer.getvalue(), [image.width, image.height]


def comparable_view(view: Mapping[str, Any]) -> dict[str, Any]:
    camera = view.get("camera")
    return {
        "role": view["role"], "status": view["status"], "source": view.get("source"),
        "camera_name": camera.get("camera_name") if camera else None,
        "crop_xyxy": camera.get("crop_xyxy") if camera else None,
    }


def run(config_path: Path, repo_root: Path, artifact_root: Path, output_root: Path, source_commit: str, image_id: str) -> dict[str, Any]:
    config = load_config(config_path)
    if output_root.exists() or output_root.with_name(output_root.name + ".partial").exists():
        raise RuntimeError(f"fresh add-once output namespace required: {output_root}")
    partial = output_root.with_name(output_root.name + ".partial")
    partial.mkdir(parents=True)
    v6_contract, v5_contract, base = load_contract_chain(config, repo_root, artifact_root)
    bindings = verify_inputs(base, repo_root, artifact_root)
    if PIL.__version__ != base["render"]["pillow_version"]:
        raise RuntimeError("Pillow version drifted")
    inputs = base["inputs"]
    building_path = artifact_root / inputs["common_manifest_relative_root"] / inputs["building_manifest_relative_path"]
    population = [json.loads(line) for line in building_path.read_text(encoding="utf-8").splitlines() if line]
    if len(population) != 199 or [int(row["population_index"]) for row in population] != list(range(1, 200)):
        raise RuntimeError("building population is not exact ordered 1..199")
    building_ids = [str(row["building_id"]) for row in population]
    exact = json.loads((repo_root / inputs["exact_937_crosswalk_git_path"]).read_text(encoding="utf-8"))
    image_id_to_name = {int(row["colmap_image_id"]): str(row["basename"]) for row in exact["rows"]}
    scene_reference = json.loads((artifact_root / inputs["scene_reference_relative_path"]).read_text(encoding="utf-8"))
    model = projection.parse_cam_model(artifact_root / inputs["cameras_relative_path"])
    images_path = artifact_root / inputs["images_relative_path"]
    cameras = {camera.name: camera for camera in projection.parse_cameras(images_path, scene_reference)}
    support, sparse_summary = v4.scan_sparse_observations(
        artifact_root / inputs["points3d_relative_path"], population, set(image_id_to_name),
        base["frame"]["sparse_local_shift_xyz"], int(inputs["points3d_count"]),
    )
    observed, observation_summary = v4.load_actual_point2d_observations(images_path, support)
    references = load_references([artifact_root / path for path in inputs["lod2_relative_paths"]], building_ids)

    freeze_spec = config["frozen_roofer"]
    freeze_path = repo_root / freeze_spec["manifest_git_path"]
    verify_file(freeze_path, freeze_spec["manifest_sha256"], "frozen Roofer replay manifest")
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    if freeze["freeze_id"] != freeze_spec["required_freeze_id"]:
        raise RuntimeError("frozen Roofer replay identity drifted")
    frozen_root = artifact_root / freeze["artifact_relative_root"]
    cityjson = {}
    for method, relative in freeze_spec["condition_cityjson"].items():
        record = next(row for row in freeze["records"] if row["path"] == relative)
        bindings[f"{method}_roofer_cityjson"] = verify_file(frozen_root / relative, record["sha256"], f"{method} Roofer CityJSON", int(record["bytes"]))
        cityjson[method] = json.loads((frozen_root / relative).read_text(encoding="utf-8"))

    tolerance = float(v5_contract["boundary_topology"]["edge_snap_tolerance_m"])
    boundary_by_id: dict[str, dict[str, tuple[list[np.ndarray], dict[str, Any]]]] = {}
    topology_counts: dict[str, Counter[str]] = {key: Counter() for key in ("reference", "lidar", "mvs")}
    for stable_id in building_ids:
        source = {
            "reference": boundary_loops(references[stable_id].roof_rings_xyz, tolerance),
            "lidar": complete_polygon_rings(cityjson_roof_rings(cityjson["lidar"], stable_id)),
            "mvs": complete_polygon_rings(cityjson_roof_rings(cityjson["mvs"], stable_id)),
        }
        boundary_by_id[stable_id] = source
        for method, (_, status) in source.items():
            topology_counts[method][str(status["status"])] += 1

    selection_records = []
    candidate_records = []
    runtimes: dict[str, dict[str, dict[str, Any]]] = {}
    rejection_counts: Counter[str] = Counter()
    selection_status_counts: Counter[str] = Counter()
    for building in population:
        stable_id = str(building["building_id"])
        reference_loops = boundary_by_id[stable_id]["reference"][0]
        components, representative_id = v6.component_records(reference_loops)
        candidates = []
        for sparse_image_id, rows in support[stable_id]["image_observations"].items():
            name = image_id_to_name[int(sparse_image_id)]
            candidate = v4.candidate_record(int(sparse_image_id), name, rows, observed, cameras[name], building, model, scene_reference, base["selection"], base["crop"])
            candidate["building_sparse_track_linked"] = bool(rows)
            v6.enrich_candidate(candidate, components, representative_id, cameras[name], model, scene_reference, v6_contract["representative_component"], v6_contract["crop"])
            candidates.append(candidate)
        has_validated = any(row["eligible"] for row in candidates)
        if not has_validated:
            existing = {int(row["image_id"]) for row in candidates}
            for image_id_value, name in image_id_to_name.items():
                if image_id_value in existing:
                    continue
                candidate = v4.candidate_record(image_id_value, name, [], observed, cameras[name], building, model, scene_reference, base["selection"], base["crop"])
                candidate["building_sparse_track_linked"] = False
                v6.enrich_candidate(candidate, components, representative_id, cameras[name], model, scene_reference, v6_contract["representative_component"], v6_contract["crop"])
                candidates.append(candidate)
        chooser = v6_v2.choose_views if has_validated else v6_v3.choose_views
        views, top_status, seed, pool_hash = chooser(stable_id, candidates, base["selection"])
        selection_status_counts[top_status] += 1
        for candidate in candidates:
            for reason in candidate["rejection_reasons"]:
                rejection_counts[str(reason)] += 1
            candidate_records.append({
                "schema": "jointbuildgs.p2.qualitative_row1_current_raw.camera_candidate_audit.v7",
                "population_index": int(building["population_index"]), "building_id": stable_id,
                **v4.public_candidate(candidate), "scientific_verdict": None,
            })
        runtimes[stable_id] = {str(row["camera_name"]): row for row in candidates}
        selection_records.append({
            "schema": "jointbuildgs.p2.qualitative_row1_current_raw.camera_selection.v7",
            "population_index": int(building["population_index"]), "building_id": stable_id,
            "track_confirmed_image_count": sum(bool(row["building_sparse_track_linked"]) for row in candidates),
            "representative_validated_image_count": sum(bool(row["eligible"]) for row in candidates),
            "eligible_candidate_pool_sha256": pool_hash, "seed_uint64": seed, "top_status": top_status,
            "views": views, "keypoints_rendered": False, "scientific_verdict": None,
        })

    anchor_path = artifact_root / config["selection_contract"]["anchor_relative_root"] / config["selection_contract"]["anchor_selection_relative_path"]
    anchor = {row["building_id"]: row for row in (json.loads(line) for line in anchor_path.read_text(encoding="utf-8").splitlines() if line)}
    by_id = {row["building_id"]: row for row in selection_records}
    for stable_id, expected in anchor.items():
        if [comparable_view(row) for row in by_id[stable_id]["views"]] != [comparable_view(row) for row in expected["views"]]:
            raise RuntimeError(f"selection drift against frozen 10-building anchor: {stable_id}")

    write_new(partial / "selection/camera_candidate_audit_v7.jsonl", b"".join(canonical_json_bytes(row) for row in candidate_records))
    write_new(partial / "selection/row1_camera_selection_v7.jsonl", b"".join(canonical_json_bytes(row) for row in selection_records))
    inventory = image_inventory(repo_root / inputs["image_inventory_git_path"])
    image_dir = artifact_root / inputs["image_directory_relative_path"]
    selected_names = sorted({view["camera"]["camera_name"] for row in selection_records for view in row["views"] if view["status"] == "SELECTED"})
    image_bindings = []
    for name in selected_names:
        expected = inventory[name]
        image_bindings.append({"basename": name, **verify_file(image_dir / name, expected["sha256"], f"raw image {name}", int(expected["bytes"]))})

    evidence_rows = []
    overlay_status_counts: dict[str, Counter[str]] = {key: Counter() for key in ("reference", "lidar", "mvs")}
    selected_panel_count = 0
    for selection in selection_records:
        stable_id = str(selection["building_id"])
        panels = []
        for view in selection["views"]:
            if view["status"] != "SELECTED":
                panels.append({"role": view["role"], "status": view["status"], "photo": None, "overlays": {}, "scientific_verdict": None})
                continue
            selected_panel_count += 1
            camera_record = view["camera"]
            camera_name = str(camera_record["camera_name"])
            crop = list(map(int, camera_record["crop_xyxy"]))
            payload, output_size = jpeg_crop(image_dir / camera_name, crop, config["photo"])
            relative = f"photos/{int(selection['population_index']):03d}_{stable_id}/{view['role']}.jpg"
            write_new(partial / relative, payload)
            omit = view.get("source") == FALLBACK_SOURCE
            overlays = {}
            for key in ("reference", "lidar", "mvs"):
                loops, source_status = boundary_by_id[stable_id][key]
                datum = "orthometric" if key == "reference" else "ellipsoidal"
                overlay = project_overlay(loops, cameras[camera_name], model, scene_reference, crop, output_size, source_status, omit, datum)
                overlay["input_datum"] = datum
                if key == "reference" and not omit and overlay["status"] != "PROJECTED":
                    raise RuntimeError(f"validated panel lost its frozen independent reference projection: {stable_id} {view['role']}")
                overlays[key] = overlay
                overlay_status_counts[key][str(overlay["status"])] += 1
            panels.append({
                "role": view["role"], "status": "SELECTED", "selection_source": view.get("source"),
                "camera_name": camera_name, "nadir_deg": camera_record["nadir_deg"], "crop_xyxy": crop,
                "photo": {"path": relative, "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest(), "size_px": output_size},
                "building_sparse_confirmation": not omit, "overlays": overlays, "keypoints_rendered": False,
                "scientific_verdict": None,
            })
        reference_missing = boundary_by_id[stable_id]["reference"][1]["status"] != "AVAILABLE"
        evidence_rows.append({
            "population_index": int(selection["population_index"]), "stable_id": stable_id, "panels": panels,
            "reference_temporal_default": "REFERENCE_MISSING" if reference_missing else "",
            "reference_is_candidate_until_current_match_verified": True, "scientific_verdict": None,
        })

    write_new(partial / "photo_evidence_manifest_v1.json", canonical_json_bytes({
        "schema": "jointbuildgs.p2.qualitative_row1_current_raw.photo_evidence_manifest.v1",
        "task_id": config["task_id"], "overlay_styles": config["overlays"],
        "reference_temporal_review": config["reference_temporal_review"], "buildings": evidence_rows,
        "scientific_verdict": None,
    }))
    write_new(partial / "control/source_bindings_v1.json", canonical_json_bytes({
        "schema": "jointbuildgs.p2.qualitative_row1_current_raw.photo_evidence_source_bindings.v1",
        **bindings, "selected_raw_images": image_bindings, "scientific_verdict": None,
    }))
    summary = {
        "schema": "jointbuildgs.p2.qualitative_row1_current_raw.photo_evidence_summary.v1",
        "task_id": config["task_id"], "building_count": len(evidence_rows), "panel_slot_count": 199 * 4,
        "selected_panel_count": selected_panel_count, "missing_panel_count": 199 * 4 - selected_panel_count,
        "selected_unique_raw_image_count": len(selected_names), "selection_status_counts": dict(sorted(selection_status_counts.items())),
        "boundary_source_status_counts": {key: dict(sorted(value.items())) for key, value in topology_counts.items()},
        "overlay_panel_status_counts": {key: dict(sorted(value.items())) for key, value in overlay_status_counts.items()},
        "camera_rejection_reason_counts": dict(sorted(rejection_counts.items())), **sparse_summary, **observation_summary,
        "keypoints_rendered": False, "partial_loops_rendered": False, "scientific_verdict": None,
    }
    write_new(partial / "control/summary_v1.json", canonical_json_bytes(summary))
    config_size, config_sha = sha256_file(config_path)
    script_size, script_sha = sha256_file(Path(__file__))
    write_new(partial / "control/run_receipt_v1.json", canonical_json_bytes({
        "schema": "jointbuildgs.p2.qualitative_row1_current_raw.photo_evidence_receipt.v1",
        "task_id": config["task_id"], "state": "complete", "generated_utc": datetime.now(timezone.utc).isoformat(),
        "repository_base_commit": source_commit, "runtime_image_id": image_id,
        "config": {"bytes": config_size, "sha256": config_sha}, "script": {"bytes": script_size, "sha256": script_sha},
        "summary": summary, "scientific_verdict": None,
    }))
    material = sorted(path for path in partial.rglob("*") if path.is_file())
    manifest = {
        "schema": "jointbuildgs.p2.qualitative_row1_current_raw.photo_evidence_artifact_manifest.v1",
        "task_id": config["task_id"], "records": [file_record(path, partial) for path in material], "scientific_verdict": None,
    }
    manifest["record_count"] = len(manifest["records"])
    write_new(partial / "control/artifact_manifest_v1.json", canonical_json_bytes(manifest))
    os.rename(partial, output_root)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--repo-root", type=Path, default=REPO)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--image-id", required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.config, args.repo_root, args.artifact_root, args.output_root, args.source_commit, args.image_id), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
