"""Matched P1/P2/P3 update; validated v3 bookkeeping, unchanged sampled rays."""
from __future__ import annotations

import argparse
import inspect
import json
import os
from pathlib import Path
import time

import numpy as np

from scripts.phd.wu_vallet_p3_v2.update_points import build_old, build_new
from scripts.phd.wu_vallet_p3_v3.analyze_filtered_update import counts, ply, sha, write
from scripts.phd.wu_vallet_regions_v4.prepare_inputs import inside
from src.phd.wu_vallet_matched_v5.core import (
    SensorMesh, RuntimeConfig, classify_relations as classify_and_update,
    components, assemble_status,
)


def run(config_path, region_id, output):
    if not Path("/.dockerenv").exists():
        raise RuntimeError("Docker required")
    started = time.monotonic()
    cfg = json.loads(Path(config_path).read_text())
    region = cfg["regions"][region_id]
    output.mkdir(parents=True, exist_ok=False)
    write(output / "config.json", cfg)
    paths = dict(acquisition=Path(region["acquisition_root"]) / "acquisition.npz",
                 native=Path(region["common_root"]) / "native.npz",
                 origins=Path(region["trajectory_root"]) / "estimated_origins.npz",
                 master=Path(region["common_root"]) / "selected_master.json")
    acquisition = dict(np.load(paths["acquisition"]))
    for suffix in ("xyz", "original_row", "original_file_index", "context_row"):
        key = f"region_{suffix}"
        if key not in acquisition and f"p3_{suffix}" in acquisition:
            acquisition[key] = acquisition[f"p3_{suffix}"]
    native = np.load(paths["native"])
    origins = dict(np.load(paths["origins"]))
    if "region_valid" not in origins and "p3_valid" in origins:
        origins["region_valid"] = origins["p3_valid"]
    selected = json.loads(paths["master"].read_text())
    assert np.array_equal(acquisition["region_xyz"].astype(np.float32), native["als_xyz"])
    for key in ("original_row", "original_file_index"):
        assert np.array_equal(acquisition[f"region_{key}"], native[f"als_{key}"])
    old_region = native["als_xyz"].astype(np.float64)
    context_indices = np.flatnonzero(inside(acquisition["context_xyz"], region["context_domain"]))
    old_xyz, old_triangles, mesh_audit = build_old(acquisition, context_indices, cfg["als_mesh"])
    inverse = np.full(len(acquisition["context_xyz"]), -1, np.int64)
    inverse[context_indices] = np.arange(len(context_indices))
    old_lookup = inverse[acquisition["region_context_row"]]
    if not (old_lookup >= 0).all():
        raise ValueError("Frozen region row missing from configured acquisition context")
    old_xyz[old_lookup] = old_region
    context_origins = origins["context_origins"][context_indices]
    context_valid = origins["context_valid"][context_indices]
    assert np.array_equal(np.isfinite(context_origins).all(axis=1), context_valid)
    if not context_valid.any():
        raise ValueError("No audited estimated sensor origins supported in regional context")
    unsupported_faces = ~context_valid[old_triangles].all(axis=1)
    if unsupported_faces.any():
        write(output / "UNSUPPORTED_ORIGIN_TRIANGLES.json", dict(
            face_count=int(unsupported_faces.sum()), context_vertices=int((~context_valid).sum()),
            policy="No sensor origins guessed and no silent change to bidirectional scope. Regional candidate execution stops before ray classification.",
            scientific_verdict=None))
        raise ValueError("Unsupported estimated sensor origins are referenced by old triangles; explicit scope revision required")
    old_mesh = SensorMesh(old_xyz, old_triangles, context_origins, context_indices)
    image_cfg = dict(common_root=region["common_root"], image_id=selected["image_id"], image_mesh=cfg["image_mesh"])
    new_result, view, image_hashes = build_new(image_cfg)
    base = new_result["mesh"]
    new_mesh = SensorMesh(base.vertices, base.triangles, base.optical_origins, base.native_rows)
    new_lookup = np.flatnonzero(inside(new_mesh.vertices, region["domain"]))
    new_region = new_mesh.vertices[new_lookup]
    new_pixels = new_mesh.native_rows[new_lookup]
    np.savez_compressed(output / "common.npz", old_xyz=old_region, new_xyz=new_region,
                        new_pixel_id=new_pixels, old_original_row=native["als_original_row"],
                        old_original_file_index=native["als_original_file_index"])
    np.savez_compressed(output / "meshes.npz", old_xyz=old_xyz, old_triangles=old_triangles,
                        old_context_indices=context_indices, old_region_lookup=old_lookup,
                        new_xyz=new_mesh.vertices, new_triangles=new_mesh.triangles,
                        new_pixel_id=new_mesh.native_rows, new_optical_origins=new_mesh.optical_origins,
                        new_region_lookup=new_lookup)
    write(output / "selected_master.json", selected)
    algorithm = RuntimeConfig(cfg["distance_tolerance_m"], direction_mode="BIDIRECTIONAL", small_region_area_m2=0.)
    print(json.dumps({"phase": "meshes_ready", "region": region_id, "image_id": selected["image_id"],
                      "old_vertices": len(old_xyz), "old_faces": len(old_triangles),
                      "new_vertices": len(new_mesh.vertices), "new_faces": len(new_mesh.triangles),
                      "regional_old": len(old_region), "regional_new": len(new_region)}), flush=True)
    result = classify_and_update(old_mesh, new_mesh, algorithm)
    raw = {side: result[f"raw_{side}_face_labels"] for side in ("old", "new")}
    meshes = {"old": old_mesh, "new": new_mesh}
    lookup = {"old": old_lookup, "new": new_lookup}
    regions = {side: components(mesh.vertices, mesh.triangles, raw[side]) for side, mesh in meshes.items()}
    np.savez_compressed(output / "raw_face_decisions.npz", raw_old_face_labels=raw["old"], raw_new_face_labels=raw["new"],
                        conflict_pairs=result["conflict_pairs"])
    np.savez_compressed(output / "components.npz", **{f"{side}_{key}": value for side in ("old", "new")
                                                     for key, value in regions[side].items()})
    # Include area zero with identical corrected bookkeeping as a transparent reference arm.
    specs = [(f"corrected_area{value:g}", value, True) for value in [0.] + cfg["area_sensitivity_m2"]]
    if cfg.get("changed_only_sensitivity_area_m2") is not None:
        value = cfg["changed_only_sensitivity_area_m2"]
        specs.append((f"changed_only_area{value:g}", value, False))
    arms = []
    for name, area, keep_single in specs:
        dest = output / name
        dest.mkdir()
        selection = {side: assemble_status(len(mesh.vertices), mesh.triangles, raw[side], regions[side], area)
                     for side, mesh in meshes.items()}
        old_status = selection["old"]["status"][old_lookup]
        new_status = selection["new"]["status"][new_lookup]
        old_keep = selection["old"]["old_keep"][old_lookup]
        new_keep = selection["new"]["new_keep"][new_lookup]
        if not keep_single:
            new_keep = new_status == "accepted_changed"
        xyz = np.concatenate((old_region[old_keep], new_region[new_keep]))
        source = np.r_[np.zeros(old_keep.sum(), np.uint8), np.ones(new_keep.sum(), np.uint8)]
        label_names = {"consistent": "consistent", "accepted_changed": "changed", "raw_single": "single",
                       "filtered": "filtered", "unassessed": "unassessed"}
        old_labels = np.asarray([label_names[v] for v in old_status], dtype="U10")
        new_labels = np.asarray([label_names[v] for v in new_status], dtype="U10")
        payload = dict(updated_points=xyz, updated_source=source, old_keep_mask=old_keep, new_keep_mask=new_keep,
                       old_labels=old_labels, new_labels=new_labels, old_vertex_status=old_status, new_vertex_status=new_status,
                       old_original_row=native["als_original_row"], old_original_file_index=native["als_original_file_index"],
                       new_pixel_id=new_pixels,
                       updated_original_row=np.r_[native["als_original_row"][old_keep], np.full(new_keep.sum(), -1, np.int64)],
                       updated_original_file_index=np.r_[native["als_original_file_index"][old_keep], np.full(new_keep.sum(), -1, np.int16)],
                       updated_pixel_id=np.r_[np.full(old_keep.sum(), -1, np.int64), new_pixels[new_keep]])
        for side in ("old", "new"):
            for key, mask in selection[side]["incident"].items():
                payload[f"{side}_incident_{key}"] = mask[lookup[side]]
        np.savez_compressed(dest / "updated_points.npz", **payload)
        ply(dest / "updated_points.ply", xyz, source)
        np.savez_compressed(dest / "face_decisions.npz", raw_old_face_labels=raw["old"], raw_new_face_labels=raw["new"],
                            old_removed_small_changed_mask=selection["old"]["removed_face_mask"],
                            new_removed_small_changed_mask=selection["new"]["removed_face_mask"])
        row = dict(name=name, direction_mode="BIDIRECTIONAL", tolerance_m=cfg["distance_tolerance_m"], small_region_area_m2=area,
                   raw_single_retained=keep_single, scientific_verdict=None, reference_accessed=False,
                   counts=dict(old_total=len(old_keep), new_total=len(new_keep), old_retained=int(old_keep.sum()),
                               old_removed=int((~old_keep).sum()), new_admitted=int(new_keep.sum()),
                               new_excluded_consistent=int((new_status == "consistent").sum()),
                               new_excluded_filtered=int((new_status == "filtered").sum()),
                               new_excluded_raw_single=int(((new_status == "raw_single") & ~new_keep).sum()),
                               new_excluded_unassessed=int((new_status == "unassessed").sum()), updated_points=len(xyz),
                               old_labels=counts(old_labels), new_labels=counts(new_labels),
                               old_status=counts(old_status), new_status=counts(new_status)),
                   outputs={p.name: sha(p) for p in dest.iterdir()})
        write(dest / "result.json", row)
        arms.append(row)
        print(json.dumps({"phase": "arm_complete", "region": region_id, "name": name, "counts": row["counts"]}), flush=True)
    receipt = dict(status="MATCHED_REGIONAL_CORRECTED_WU_UPDATE_COMPLETE", task_id=cfg["task_id"], region_id=region_id,
                   scientific_verdict=None, reference_accessed=False, GS_executed=False, full_author_reproduction=False,
                   native_PSMNet_matching=False, matched_core_policy="v5_core_validated_v3_assembly_raw_v2_relations", image_id=selected["image_id"], domain=region["domain"],
                   working_crs=cfg["working_crs"], frame=cfg["frame"], context_domain=region["context_domain"], arms=arms,
                   primary_display_arm=f"corrected_area{cfg['primary_area_m2']:g}",
                   native_counts={"old": len(old_region), "new": len(new_region)},
                   mesh_audit=dict(old_layers=mesh_audit, new_preprocessing=new_result["diagnostics"],
                                   context_supported_origins=int(context_valid.sum()), context_total_origins=len(context_valid),
                                   region_supported_origins=int(origins["region_valid"].sum()), region_total_origins=len(origins["region_valid"])),
                   input_hashes={str(path): sha(path) for path in paths.values()} | image_hashes,
                   raw_decision_diagnostics=result["diagnostics"], reproduction_scope=result["reproduction_scope"],
                   corrected_small_region_policy="Full-context edge connected raw CHANGED area. Removed new regions excluded; removed old regions retained. Raw SINGLE incidence retained separately, not certified current or single-source.",
                   adaptations=["COLMAP instead of PSMNet", "Estimated ALS origins", "Finite sampled rays", "Declared area and vertex aggregation choices"],
                   implementation_hashes={str(path): sha(path) for path in dict.fromkeys([
                       Path(__file__), Path(inspect.getfile(classify_and_update)),
                       Path(inspect.getfile(RuntimeConfig)), Path(inspect.getfile(components)),
                       Path(inspect.getfile(build_old)), Path(inspect.getfile(inside))])},
                   source_git_head=os.environ.get("JBGS_SOURCE_GIT_HEAD"), container_image=os.environ.get("JBGS_CONTAINER_IMAGE_ID"),
                   source_snapshot_manifest=os.environ.get("JBGS_SOURCE_SNAPSHOT_MANIFEST"), elapsed_seconds=time.monotonic() - started,
                   outputs={p.name: sha(p) for p in output.iterdir() if p.is_file()})
    write(output / "receipt.json", receipt)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--region", choices=("P1", "P2", "P3"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.config, args.region, args.output)
