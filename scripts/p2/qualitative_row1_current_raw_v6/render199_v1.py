#!/usr/bin/env python3
"""Lift the frozen v6-v4 row renderer from its reviewed 10 buildings to ordered 199."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

import PIL

from scripts.evidence_and_attributes.population_analysis import population_aux_v3 as projection
from scripts.p2.qualitative_199_cloudcompare_scene_v1.build_scene import canonical_json_bytes, file_record, sha256_file, write_new
from scripts.p2.qualitative_row1_current_raw_v3.preview import image_inventory, verify_file
from scripts.p2.qualitative_row1_current_raw_v4 import preview10 as v4
from scripts.p2.qualitative_row1_current_raw_v5.preview10 import ordered_boundary_loops
from scripts.p2.qualitative_row1_current_raw_v6 import preview10 as frozen_v6
from scripts.p2.qualitative_row1_current_raw_v6 import preview10_v2 as frozen_v6_v2
from scripts.p2.qualitative_row1_current_raw_v6 import preview10_v3 as frozen_v6_v3
from scripts.p2.qualitative_row1_current_raw_v6 import preview10_v4 as frozen_v6_v4
from scripts.p2.utarget199_presentation_v5.render import load_references


REPO = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = REPO / "configs/p2/qualitative_row1_current_raw_v6/render199_v1.json"
FALLBACK_SOURCE = frozen_v6_v3.GEOMETRY_FALLBACK_SOURCE


def load_config(path: Path) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    if config.get("schema") != "jointbuildgs.p2.qualitative_row1_current_raw.render199_contract.v1":
        raise RuntimeError("unexpected render199 config schema")
    if config.get("status") != "USER_APPROVED_FROZEN_V6_V4_FULL_199_EXECUTION":
        raise RuntimeError("frozen v6-v4 full199 execution is not approved")
    if config.get("scientific_verdict", "missing") is not None:
        raise RuntimeError("scientific_verdict must remain null")
    if config["population"] != {
        "building_count": 199, "indices": "INCLUSIVE_1_TO_199",
        "roles": ["TOP", "RANDOM_1", "RANDOM_2", "RANDOM_3"],
    }:
        raise RuntimeError("ordered 199 x 4 population contract drifted")
    if config["extension_boundary"]["changed"] != "ONLY_PREVIEW_MEMBERSHIP_FROM_FIXED_10_TO_ORDERED_199":
        raise RuntimeError("full199 extension boundary drifted")
    if config["extension_boundary"]["web_consumption"] != "COPY_EXACT_RENDERED_ROW_PNG_BYTES_NO_REDRAW":
        raise RuntimeError("web must consume exact rendered row PNG bytes")
    if any(int(config["execution"].get(key, -1)) != 0 for key in (
        "roofer_invocations", "reconstruction_invocations", "gs_training_invocations", "metric_recomputations"
    )):
        raise RuntimeError("row rendering must not invoke reconstruction")
    return config


def comparable_view(view: Mapping[str, Any]) -> dict[str, Any]:
    camera = view.get("camera")
    return {
        "role": view["role"], "status": view["status"], "source": view.get("source"),
        "camera_name": camera.get("camera_name") if camera else None,
        "crop_xyxy": camera.get("crop_xyxy") if camera else None,
    }


def load_frozen_contract(config: Mapping[str, Any], repo_root: Path, artifact_root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    entry = config["frozen_entrypoint"]
    verify_file(repo_root / entry["git_path"], entry["sha256"], "frozen v6-v4 entrypoint", int(entry["bytes"]))
    contract_record = config["frozen_contract"]
    contract_path = repo_root / contract_record["git_path"]
    verify_file(contract_path, contract_record["sha256"], "frozen v6-v4 contract", int(contract_record["bytes"]))
    for index, dependency in enumerate(config["frozen_dependencies"], start=1):
        verify_file(repo_root / dependency["git_path"], dependency["sha256"], f"frozen v6 dependency {index}", int(dependency["bytes"]))
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    v5_path = repo_root / contract["base_contract"]["git_path"]
    verify_file(v5_path, contract["base_contract"]["sha256"], "frozen v5 contract", int(contract["base_contract"]["bytes"]))
    v5 = json.loads(v5_path.read_text(encoding="utf-8"))
    v4_path = repo_root / v5["base_contract"]["git_path"]
    verify_file(v4_path, v5["base_contract"]["sha256"], "frozen v4 contract", int(v5["base_contract"]["bytes"]))
    base = json.loads(v4_path.read_text(encoding="utf-8"))
    anchor = config["anchor_preview10"]
    anchor_root = artifact_root / anchor["relative_root"]
    for label, key in (("selection", "selection"), ("preview manifest", "preview_manifest"), ("artifact manifest", "artifact_manifest")):
        verify_file(anchor_root / anchor[f"{key}_path"], anchor[f"{key}_sha256"], f"anchor {label}", int(anchor[f"{key}_bytes"]))
    return contract, v5, base, {"root": anchor_root, **anchor}


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
        bindings[f"lod2_{index + 1}"] = verify_file(artifact_root / relative, inputs["lod2_sha256"][index], f"LoD2 {index + 1}")
    return bindings


def run(config_path: Path, repo_root: Path, artifact_root: Path, output_root: Path, source_commit: str, image_id: str) -> dict[str, Any]:
    config = load_config(config_path)
    if output_root.exists() or output_root.with_name(output_root.name + ".partial").exists():
        raise RuntimeError(f"fresh add-once output namespace required: {output_root}")
    partial = output_root.with_name(output_root.name + ".partial")
    partial.mkdir(parents=True)
    contract, v5, base, anchor = load_frozen_contract(config, repo_root, artifact_root)
    bindings = verify_inputs(base, repo_root, artifact_root)
    if PIL.__version__ != base["render"]["pillow_version"]:
        raise RuntimeError("Pillow version drifted")
    inputs = base["inputs"]
    building_path = artifact_root / inputs["common_manifest_relative_root"] / inputs["building_manifest_relative_path"]
    population = [json.loads(line) for line in building_path.read_text(encoding="utf-8").splitlines() if line]
    if len(population) != 199 or [int(row["population_index"]) for row in population] != list(range(1, 200)):
        raise RuntimeError("population is not exact ordered 1..199")
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

    selections, candidate_audit = [], []
    runtime_by_id: dict[str, dict[str, dict[str, Any]]] = {}
    topology_by_id: dict[str, dict[str, Any]] = {}
    components_by_id: dict[str, list[dict[str, Any]]] = {}
    representative_by_id: dict[str, int] = {}
    selection_status_counts: Counter[str] = Counter()
    rejection_counts: Counter[str] = Counter()
    for building in population:
        stable_id = str(building["building_id"])
        loops, topology = ordered_boundary_loops(
            references[stable_id].roof_rings_xyz,
            float(v5["boundary_topology"]["edge_snap_tolerance_m"]),
            bool(v5["boundary_topology"]["require_even_boundary_graph_degree"]),
        )
        components, representative_id = frozen_v6.component_records(loops)
        public_components = [v4.public_candidate(row) for row in components]
        topology = {
            **topology,
            "component_xy_area_m2": {str(row["component_id"]): row["xy_area_m2"] for row in public_components},
            "component_source_edge_count": {str(row["component_id"]): row["source_edge_count"] for row in public_components},
            "representative_component_id": representative_id,
            "representative_selection_rule": contract["representative_component"]["selection_rule"],
        }
        candidates = []
        for image_id_value, rows in support[stable_id]["image_observations"].items():
            name = image_id_to_name[int(image_id_value)]
            candidate = v4.candidate_record(int(image_id_value), name, rows, observed, cameras[name], building, model, scene_reference, base["selection"], base["crop"])
            candidate["building_sparse_track_linked"] = bool(rows)
            frozen_v6.enrich_candidate(candidate, components, representative_id, cameras[name], model, scene_reference, contract["representative_component"], contract["crop"])
            candidates.append(candidate)
        has_validated = any(row["eligible"] for row in candidates)
        if not has_validated:
            existing = {int(row["image_id"]) for row in candidates}
            for image_id_value, name in image_id_to_name.items():
                if image_id_value in existing:
                    continue
                candidate = v4.candidate_record(image_id_value, name, [], observed, cameras[name], building, model, scene_reference, base["selection"], base["crop"])
                candidate["building_sparse_track_linked"] = False
                frozen_v6.enrich_candidate(candidate, components, representative_id, cameras[name], model, scene_reference, contract["representative_component"], contract["crop"])
                candidates.append(candidate)
        chooser = frozen_v6_v2.choose_views if has_validated else frozen_v6_v3.choose_views
        views, top_status, seed, pool_hash = chooser(stable_id, candidates, base["selection"])
        selection_status_counts[top_status] += 1
        for candidate in candidates:
            rejection_counts.update(map(str, candidate["rejection_reasons"]))
            candidate_audit.append({
                "schema": "jointbuildgs.p2.qualitative_row1_current_raw.camera_candidate_audit.render199.v1",
                "population_index": int(building["population_index"]), "building_id": stable_id,
                **v4.public_candidate(candidate), "scientific_verdict": None,
            })
        selections.append({
            "schema": "jointbuildgs.p2.qualitative_row1_current_raw.camera_selection.render199.v1",
            "population_index": int(building["population_index"]), "building_id": stable_id,
            "topology": topology,
            "track_confirmed_image_count": sum(bool(row["building_sparse_track_linked"]) for row in candidates),
            "representative_validated_image_count": sum(bool(row["eligible"]) for row in candidates),
            "eligible_candidate_pool_sha256": pool_hash, "seed_uint64": seed, "top_status": top_status,
            "views": views, "keypoints_rendered": False, "scientific_verdict": None,
        })
        runtime_by_id[stable_id] = {str(row["camera_name"]): row for row in candidates}
        topology_by_id[stable_id] = topology
        components_by_id[stable_id] = components
        representative_by_id[stable_id] = representative_id

    anchor_selection = {row["building_id"]: row for row in (json.loads(line) for line in (anchor["root"] / anchor["selection_path"]).read_text(encoding="utf-8").splitlines() if line)}
    selection_by_id = {row["building_id"]: row for row in selections}
    for stable_id, expected in anchor_selection.items():
        if [comparable_view(row) for row in selection_by_id[stable_id]["views"]] != [comparable_view(row) for row in expected["views"]]:
            raise RuntimeError(f"selection drift against frozen v6-v4 anchor: {stable_id}")
    write_new(partial / "selection/camera_candidate_audit_render199_v1.jsonl", b"".join(canonical_json_bytes(row) for row in candidate_audit))
    write_new(partial / "selection/row1_camera_selection_render199_v1.jsonl", b"".join(canonical_json_bytes(row) for row in selections))

    inventory = image_inventory(repo_root / inputs["image_inventory_git_path"])
    image_dir = artifact_root / inputs["image_directory_relative_path"]
    selected_names = sorted({view["camera"]["camera_name"] for row in selections for view in row["views"] if view["status"] == "SELECTED"})
    image_bindings = []
    for name in selected_names:
        expected = inventory[name]
        image_bindings.append({"basename": name, **verify_file(image_dir / name, expected["sha256"], f"raw image {name}", int(expected["bytes"]))})

    anchor_preview = json.loads((anchor["root"] / anchor["preview_manifest_path"]).read_text(encoding="utf-8"))
    anchor_rows = {row["building_id"]: row for row in anchor_preview["rows"]}
    output_rows = []
    anchor_png_match_count = 0
    for building in population:
        stable_id = str(building["building_id"])
        payload, diagnostics = frozen_v6_v4.render_building(
            building, selection_by_id[stable_id], runtime_by_id[stable_id], topology_by_id[stable_id],
            components_by_id[stable_id], representative_by_id[stable_id], image_dir, base["render"], contract["render"],
        )
        filename = f"{int(building['population_index']):03d}_{stable_id}.png"
        digest = hashlib.sha256(payload).hexdigest()
        if stable_id in anchor_rows:
            if digest != anchor_rows[stable_id]["output_sha256"]:
                raise RuntimeError(f"rendered PNG bytes drift against frozen v6-v4 anchor: {stable_id}")
            anchor_png_match_count += 1
        write_new(partial / "preview/rows" / filename, payload)
        output_rows.append({
            "population_index": int(building["population_index"]), "building_id": stable_id,
            "filename": filename, "output_sha256": digest, "topology": topology_by_id[stable_id],
            "panels": diagnostics, "renderer": "FROZEN_PREVIEW10_V4", "keypoints_rendered": False,
            "scientific_verdict": None,
        })
    if anchor_png_match_count != 10:
        raise RuntimeError("not all ten frozen anchor PNGs were byte-identical")
    write_new(partial / "preview/preview_manifest_render199_v1.json", canonical_json_bytes({
        "schema": "jointbuildgs.p2.qualitative_row1_current_raw.preview_manifest.render199.v1",
        "task_id": config["task_id"], "rows": output_rows,
        "anchor_preview10_png_byte_match_count": anchor_png_match_count, "scientific_verdict": None,
    }))
    write_new(partial / "preview/index.html", frozen_v6.html_page(output_rows))
    write_new(partial / "control/source_bindings_render199_v1.json", canonical_json_bytes({
        "schema": "jointbuildgs.p2.qualitative_row1_current_raw.source_bindings.render199.v1",
        **bindings, "selected_raw_images": image_bindings, "scientific_verdict": None,
    }))
    selected_panel_count = sum(view["status"] == "SELECTED" for row in selections for view in row["views"])
    summary = {
        "schema": "jointbuildgs.p2.qualitative_row1_current_raw.summary.render199.v1",
        "task_id": config["task_id"], "building_count": 199, "panel_slot_count": 796,
        "selected_panel_count": selected_panel_count, "missing_panel_count": 796 - selected_panel_count,
        "selected_unique_raw_image_count": len(selected_names),
        "selection_status_counts": dict(sorted(selection_status_counts.items())),
        "camera_rejection_reason_counts": dict(sorted(rejection_counts.items())),
        **sparse_summary, **observation_summary,
        "frozen_preview10_selection_match_count": 10, "frozen_preview10_png_byte_match_count": 10,
        "renderer": "scripts/p2/qualitative_row1_current_raw_v6/preview10_v4.py",
        "web_consumption": "COPY_EXACT_RENDERED_ROW_PNG_BYTES_NO_REDRAW",
        "keypoints_rendered": False, "scientific_verdict": None,
    }
    write_new(partial / "control/summary_render199_v1.json", canonical_json_bytes(summary))
    config_size, config_sha = sha256_file(config_path)
    script_size, script_sha = sha256_file(Path(__file__))
    write_new(partial / "control/run_receipt_render199_v1.json", canonical_json_bytes({
        "schema": "jointbuildgs.p2.qualitative_row1_current_raw.receipt.render199.v1",
        "task_id": config["task_id"], "state": "complete", "generated_utc": datetime.now(timezone.utc).isoformat(),
        "repository_base_commit": source_commit, "runtime_image_id": image_id,
        "config": {"bytes": config_size, "sha256": config_sha}, "script": {"bytes": script_size, "sha256": script_sha},
        "summary": summary, "scientific_verdict": None,
    }))
    material = sorted(path for path in partial.rglob("*") if path.is_file())
    manifest = {
        "schema": "jointbuildgs.p2.qualitative_row1_current_raw.artifact_manifest.render199.v1",
        "task_id": config["task_id"], "records": [file_record(path, partial) for path in material], "scientific_verdict": None,
    }
    manifest["record_count"] = len(manifest["records"])
    write_new(partial / "control/artifact_manifest_render199_v1.json", canonical_json_bytes(manifest))
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
