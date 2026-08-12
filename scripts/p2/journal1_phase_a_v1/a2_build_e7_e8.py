#!/usr/bin/env python3
"""A2 fuse-step adapters: E7 (Existing-ALS-only) and E8 (E2 ∪ ALS) → sealed Stage-3 chain.

Journal1 Phase A / A2 (task P2-JOURNAL1-PHASE-A-v1, non-confirmatory technical
development). The sealed 199-building Stage-3 read-out — AOI+context crop →
SMRF → shared-standard-footprint overlay → Roofer defaults → per-building
status rows — is bound byte-identically to the sealed C2/C3 rendered-depth
chain configuration; only the fuse step is replaced by training-free source
adapters (JOURNAL1_EXPERIMENT_DESIGN_ko_v1.md §3, arms E7/E8):

  E7 — registered Existing ALS alone (negative control, no learning): the
       exact 4-tile raw ALS bytes of the C4/S2c prior lineage, fixed
       +45.7 m orthometric→ellipsoidal datum shift, no re-registration.
       The frozen alignment is re-verified with the same registration gate
       (C4 `registration_gate`), with the sealed C2_MVS current-image scene
       as the current-side support.
  E8 — simple union E2 ∪ ALS (key counterfactual, same registration bytes):
       the sealed C2_MVS classified-scene points (geometry only, class labels
       dropped) unioned with the exact same ALS points; SMRF re-decides
       ground/building on the union.

LoD2 Z / RoofSurface / roof type / semantic labels are never inputs; the
shared footprint supplies XY support and identity only (DEC-P1-019).
`scientific_verdict` stays null in every receipt.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

REPO = Path(__file__).resolve().parents[3]
TASK_ID = "P2-JOURNAL1-PHASE-A-v1"
STAGE = "A2"
CONDITIONS = ("E7", "E8")
BASE_CONFIG = REPO / "configs/p2/c2_c3_rendered_depth_shared_footprint_199_v1/run_v1.json"
JOURNAL1_CONFIG = REPO / "configs/p2/journal1_phase_a_v1/run_v1.json"

# Sealed sources (relative to the artifact root).
E2_CLASSIFIED_REL = (
    "phase-payloads/p2/c1_c2_shared_footprint_199_v3/"
    "P2-C1-C2-SHARED-FOOTPRINT-199-ORIGINAL-GLOBAL-v3/work/C2_MVS/classified_scene.laz"
)
E2_CLASSIFIED_SHA256 = "0326c0982dc1512317b4e7eeb7d28fc86581372e326fd6eb5acf1fdc2a6d9912"
FOOTPRINTS_REL = (
    "phase-payloads/p2/c1_c2_shared_footprint_199_v3/"
    "P2-C1-C2-SHARED-FOOTPRINT-199-ORIGINAL-GLOBAL-v3-replay-20260806a/freeze/"
    "shared_footprints_199.geojson"
)
ALS_ROOT_REL = "phase-payloads/p0-audit/data/raw/als"

SEED_CAP = 2_000_000
ALS_GATE_VOXEL_M = 0.75
CHUNK = 2_000_000
ALS_GRAY = np.uint16(32768)

LINEAGE = {
    "E7": "Existing ALS alone (no training): exact C4/S2c prior 4-tile raw ALS, +45.7 m datum, frozen registration, sealed SMRF→footprint-overlay→Roofer chain",
    "E8": "Simple union E2 ∪ ALS (no training): sealed C2_MVS classified-scene geometry ∪ exact same ALS bytes, SMRF re-decides classes, sealed chain",
}


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=1) + "\n").encode("utf-8")


def write_new(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(payload)


def file_record(path: Path, root: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(root).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def load_sealed_base() -> dict[str, Any]:
    """Bind A2 to the sealed Stage-3 chain configuration (drift-guarded)."""
    from scripts.p2.c2_c3_rendered_depth_shared_footprint_199_v1.run import (
        load_config,
        validate_config,
    )

    config = load_config(BASE_CONFIG)
    validate_config(config)
    return config


def crop_bounds(scene: dict[str, Any]) -> tuple[float, float, float, float]:
    x0, y0, x1, y1 = map(float, scene["roofer_aoi_bbox"])
    buffer_m = float(scene["classification_context_buffer_m"])
    return x0 - buffer_m, y0 - buffer_m, x1 + buffer_m, y1 + buffer_m


# ---------------------------------------------------------------- prepare


def prepare(output_root: Path, artifact_root: Path) -> dict[str, Any]:
    marker = output_root / "control/prepared_a2_v1.json"
    if marker.is_file():
        return json.loads(marker.read_text(encoding="utf-8"))
    from scripts.p2.c4_existing_als_v1.prepare_prior import ALS_HASHES
    from src.stage3.common_classification_adapter_v1 import pipeline as classification_pipeline

    config = load_sealed_base()
    als_records = []
    for name, expected in ALS_HASHES.items():
        path = artifact_root / ALS_ROOT_REL / name
        actual = sha256_file(path)
        if actual != expected:
            raise RuntimeError(f"raw ALS hash drift: {name} {actual}")
        als_records.append({"path": str(path), "sha256": actual, "bytes": path.stat().st_size})
    e2_path = artifact_root / E2_CLASSIFIED_REL
    e2_actual = sha256_file(e2_path)
    if e2_actual != E2_CLASSIFIED_SHA256:
        raise RuntimeError(f"sealed C2_MVS classified-scene hash drift: {e2_actual}")

    footprint_source = artifact_root / FOOTPRINTS_REL
    footprint_body = json.loads(footprint_source.read_text(encoding="utf-8"))
    if len(footprint_body["features"]) != 199:
        raise RuntimeError("shared footprint population drifted")
    footprint_target = output_root / "freeze/shared_footprints.geojson"
    if not footprint_target.is_file():
        footprint_target.parent.mkdir(parents=True, exist_ok=True)
        footprint_target.write_bytes(footprint_source.read_bytes())
    if sha256_file(footprint_target) != sha256_file(footprint_source):
        raise RuntimeError("frozen footprint copy drifted")

    for condition in CONDITIONS:
        work = output_root / "work" / condition
        work.mkdir(parents=True, exist_ok=True)
        pipeline_path = work / "classification_pipeline.json"
        if pipeline_path.is_file():
            continue
        body = classification_pipeline(
            source_stages=[{"type": "readers.las", "filename": (work / "fused_surface.laz").as_posix()}],
            scene=config["scene"],
            classification=config["classification"],
            footprint_path=footprint_target,
            output_path=work / "classified_scene.laz",
        )
        write_new(pipeline_path, canonical_json_bytes(body))

    receipt = {
        "schema": "jointbuildgs.p2.journal1_phase_a_v1.a2_prepared.v1",
        "task_id": TASK_ID,
        "stage": STAGE,
        "status": "PREPARED_FOR_TRAINING_FREE_FUSE_ADAPTERS",
        "created_utc": now_utc(),
        "conditions": list(CONDITIONS),
        "condition_lineage": LINEAGE,
        "sealed_chain_config": {
            "path": str(BASE_CONFIG.relative_to(REPO)),
            "sha256": sha256_file(BASE_CONFIG),
            "scene": config["scene"],
            "classification": config["classification"],
            "roofer": config["roofer"],
        },
        "raw_als_sources": als_records,
        "e2_classified_source": {"path": str(e2_path), "sha256": e2_actual, "bytes": e2_path.stat().st_size},
        "shared_footprints": file_record(footprint_target, output_root),
        "lod2_training_use": False,
        "official_PASS_usable": None,
        "scientific_verdict": None,
    }
    write_new(marker, canonical_json_bytes(receipt))
    return receipt


# ---------------------------------------------------------------- fuse


def _voxel_centroid(points: np.ndarray, voxel_m: float) -> np.ndarray:
    keys = np.floor(points / voxel_m).astype(np.int64)
    order = np.lexsort((keys[:, 2], keys[:, 1], keys[:, 0]))
    keys, points = keys[order], points[order]
    starts = np.r_[0, np.flatnonzero(np.any(np.diff(keys, axis=0) != 0, axis=1)) + 1]
    counts = np.diff(np.r_[starts, len(keys)]).astype(np.float64)
    sums = np.add.reduceat(points, starts, axis=0)
    return sums / counts[:, None]


def _load_als_world(artifact_root: Path, bounds: tuple[float, float, float, float]) -> tuple[np.ndarray, list[dict[str, Any]]]:
    """Raw ALS tiles → EPSG:25832 world points inside the sealed crop bounds.

    z_world = z_raw + 45.7 m (frozen 2022-orthometric → 2024-ellipsoidal datum
    bridge, identical constant to the C4/S2c prior and the sealed LoD2 shift).
    """
    import laspy

    from scripts.p2.c4_existing_als_v1.prepare_prior import ALS_DATUM_SHIFT_M, ALS_HASHES

    x0, y0, x1, y1 = bounds
    parts: list[np.ndarray] = []
    rows = []
    for name, expected in ALS_HASHES.items():
        path = artifact_root / ALS_ROOT_REL / name
        actual = sha256_file(path)
        if actual != expected:
            raise RuntimeError(f"raw ALS hash drift: {name} {actual}")
        selected = 0
        with laspy.open(path) as reader:
            source_count = int(reader.header.point_count)
            for chunk in reader.chunk_iterator(CHUNK):
                x = np.asarray(chunk.x)
                y = np.asarray(chunk.y)
                keep = (x >= x0) & (x <= x1) & (y >= y0) & (y <= y1)
                if bool(keep.any()):
                    z = np.asarray(chunk.z)[keep] + ALS_DATUM_SHIFT_M
                    parts.append(np.column_stack((x[keep], y[keep], z)))
                    selected += int(keep.sum())
        rows.append({"path": str(path), "sha256": actual, "source_point_count": source_count, "crop_selected_point_count": selected})
    if not parts:
        raise RuntimeError("raw ALS has no points inside the sealed crop bounds")
    return np.concatenate(parts), rows


def _als_registration_gate(als_world: np.ndarray, artifact_root: Path) -> dict[str, Any]:
    """Re-verify the frozen ALS↔current alignment with the C4 gate (no re-registration)."""
    import laspy

    from scripts.p2.c4_existing_als_v1.prepare_prior import WORLD_SHIFT, registration_gate

    e2_path = artifact_root / E2_CLASSIFIED_REL
    seed_parts: list[np.ndarray] = []
    with laspy.open(e2_path) as reader:
        total = int(reader.header.point_count)
        stride = max(1, int(np.ceil(total / SEED_CAP)))
        for chunk in reader.chunk_iterator(CHUNK):
            xyz = np.column_stack((np.asarray(chunk.x), np.asarray(chunk.y), np.asarray(chunk.z)))
            seed_parts.append(xyz[::stride])
    seed_local = np.concatenate(seed_parts) - WORLD_SHIFT
    als_local = als_world - WORLD_SHIFT
    als_gate = _voxel_centroid(als_local, ALS_GATE_VOXEL_M)
    receipt = registration_gate(seed_local, als_gate)
    receipt.update({
        "seed_source": "sealed C2_MVS classified_scene xyz (current-image lineage)",
        "seed_stride": stride,
        "seed_point_count": int(len(seed_local)),
        "als_gate_voxel_m": ALS_GATE_VOXEL_M,
        "als_gate_point_count": int(len(als_gate)),
        "re_registration_applied": False,
    })
    return receipt


def _open_fused_writer(path: Path):
    import laspy

    from scripts.p2.c2_c3_rendered_depth_shared_footprint_199_v1.run import EPSG25832_WKT

    header = laspy.LasHeader(point_format=3, version="1.4")
    from laspy.vlrs.known import WktCoordinateSystemVlr

    header.vlrs.append(WktCoordinateSystemVlr(EPSG25832_WKT))
    header.global_encoding.wkt = True
    header.scales = np.asarray([0.001, 0.001, 0.001])
    header.offsets = np.asarray([690000.0, 5335000.0, 0.0])
    path.parent.mkdir(parents=True, exist_ok=True)
    return laspy.open(path, mode="w", header=header, do_compress=True), header


def _write_block(writer, header, xyz: np.ndarray, rgb: np.ndarray) -> None:
    import laspy

    points = laspy.ScaleAwarePointRecord.zeros(len(xyz), header=header)
    points.x = xyz[:, 0]
    points.y = xyz[:, 1]
    points.z = xyz[:, 2]
    points.red = rgb[:, 0]
    points.green = rgb[:, 1]
    points.blue = rgb[:, 2]
    points.classification = np.ones(len(xyz), dtype=np.uint8)
    writer.write_points(points)


def fuse(output_root: Path, artifact_root: Path, condition: str) -> dict[str, Any]:
    import laspy

    work = output_root / "work" / condition
    receipt_path = work / "fused_surface_receipt.json"
    if receipt_path.is_file():
        return json.loads(receipt_path.read_text(encoding="utf-8"))
    fused_path = work / "fused_surface.laz"
    if fused_path.exists():
        raise RuntimeError(f"unsealed fused output refuses overwrite: {fused_path}")
    config = load_sealed_base()
    bounds = crop_bounds(config["scene"])
    als_world, als_rows = _load_als_world(artifact_root, bounds)
    gate = _als_registration_gate(als_world, artifact_root)

    writer, header = _open_fused_writer(fused_path)
    e2_count = 0
    try:
        if condition == "E8":
            e2_path = artifact_root / E2_CLASSIFIED_REL
            with laspy.open(e2_path) as reader:
                for chunk in reader.chunk_iterator(CHUNK):
                    xyz = np.column_stack((np.asarray(chunk.x), np.asarray(chunk.y), np.asarray(chunk.z)))
                    rgb = np.column_stack((
                        np.asarray(chunk.red, dtype=np.uint16),
                        np.asarray(chunk.green, dtype=np.uint16),
                        np.asarray(chunk.blue, dtype=np.uint16),
                    ))
                    _write_block(writer, header, xyz, rgb)
                    e2_count += len(xyz)
        elif condition != "E7":
            raise RuntimeError(f"unknown condition: {condition}")
        for start in range(0, len(als_world), CHUNK):
            block = als_world[start:start + CHUNK]
            _write_block(writer, header, block, np.full((len(block), 3), ALS_GRAY, dtype=np.uint16))
    finally:
        writer.close()

    receipt = {
        "schema": "jointbuildgs.p2.journal1_phase_a_v1.a2_fused_surface.v1",
        "task_id": TASK_ID,
        "stage": STAGE,
        "condition_id": condition,
        "status": "FUSED_SURFACE_READY",
        "created_utc": now_utc(),
        "lineage": LINEAGE[condition],
        "source_kind": "TRAINING_FREE_POINT_SOURCE_ADAPTER",
        "training_executed": False,
        "raw_als_sources": als_rows,
        "datum_transform": {"source": "2022_ALS_ORTHOMETRIC", "target": "2024_CAMERA_ELLIPSOIDAL", "z_shift_m": 45.7},
        "registration": gate,
        "e2_union_source": (
            {"path": str(artifact_root / E2_CLASSIFIED_REL), "sha256": E2_CLASSIFIED_SHA256,
             "geometry_only": True, "class_labels_dropped": True}
            if condition == "E8" else None
        ),
        "crop_bounds_world_xy": list(bounds),
        "point_count": {
            "als": int(len(als_world)),
            "e2": int(e2_count),
            "total": int(len(als_world) + e2_count),
        },
        "als_display_rgb": "NEUTRAL_GRAY_32768",
        "semantic_audit_dims": "ABSENT_NON_GS_SOURCE",
        "fused_surface": file_record(fused_path, output_root),
        "official_PASS_usable": None,
        "scientific_verdict": None,
    }
    write_new(receipt_path, canonical_json_bytes(receipt))
    return receipt


# ---------------------------------------------------------------- classify / roofer


def verify_classified(output_root: Path, condition: str) -> dict[str, Any]:
    import laspy

    work = output_root / "work" / condition
    receipt_path = work / "classified_scene_receipt.json"
    if receipt_path.is_file():
        return json.loads(receipt_path.read_text(encoding="utf-8"))
    path = work / "classified_scene.laz"
    counts: Counter[int] = Counter()
    with laspy.open(path) as reader:
        total = int(reader.header.point_count)
        crs = reader.header.parse_crs()
        epsg = crs.to_epsg() if crs is not None else None
        for chunk in reader.chunk_iterator(CHUNK):
            values, numbers = np.unique(np.asarray(chunk.classification), return_counts=True)
            counts.update({int(v): int(n) for v, n in zip(values, numbers)})
    if total <= 0 or counts[2] <= 0 or counts[6] <= 0 or epsg != 25832:
        raise RuntimeError(f"classified scene invariant failed: total={total} counts={counts} epsg={epsg}")
    receipt = {
        "schema": "jointbuildgs.p2.journal1_phase_a_v1.a2_classified_scene.v1",
        "task_id": TASK_ID,
        "stage": STAGE,
        "condition_id": condition,
        "status": "CLASSIFIED_SCENE_READY",
        "classified_scene": file_record(path, output_root),
        "point_count": total,
        "class_counts": {str(key): counts[key] for key in sorted(counts)},
        "epsg": epsg,
        "classification_adapter": "src/stage3/common_classification_adapter_v1.py",
        "semantic_used_for_classification": False,
        "semantic_audit_dims": "ABSENT_NON_GS_SOURCE",
        "official_PASS_usable": None,
        "scientific_verdict": None,
    }
    write_new(receipt_path, canonical_json_bytes(receipt))
    return receipt


def record_roofer(output_root: Path, condition: str, exit_code: int, runtime_seconds: int) -> dict[str, Any]:
    work = output_root / "work" / condition
    files = sorted((work / "roofer_output").glob("*.city.jsonl"))
    receipt = {
        "schema": "jointbuildgs.p2.journal1_phase_a_v1.a2_roofer_terminal.v1",
        "task_id": TASK_ID,
        "stage": STAGE,
        "condition_id": condition,
        "status": "COMPLETED" if int(exit_code) == 0 and files else "FAILED",
        "exit_code": int(exit_code),
        "runtime_seconds": int(runtime_seconds),
        "roofer_invocation_count": 1,
        "quality_parameters": "defaults",
        "quality_driven_retry": False,
        "outputs": [file_record(path, output_root) for path in files],
        "official_PASS_usable": None,
        "scientific_verdict": None,
    }
    write_new(work / "roofer_terminal.json", canonical_json_bytes(receipt))
    return receipt


# ---------------------------------------------------------------- finalize


def finalize(output_root: Path) -> dict[str, Any]:
    from scripts.p2.c1_c2_shared_footprint_199_v3.run import (
        _parse_features,
        _status,
        _val_by_id,
        combine_cityjsonseq,
    )

    marker = output_root / "control/finalized_a2_v1.json"
    if marker.is_file():
        return json.loads(marker.read_text(encoding="utf-8"))
    footprints = json.loads((output_root / "freeze/shared_footprints.geojson").read_text(encoding="utf-8"))
    ordered = sorted(
        (int(f["properties"]["population_index"]), str(f["properties"]["stable_id"]))
        for f in footprints["features"]
    )
    rows: list[dict[str, Any]] = []
    summaries: dict[str, dict[str, int]] = {}
    for condition in CONDITIONS:
        work = output_root / "work" / condition
        raw_files = sorted((work / "roofer_output").glob("*.city.jsonl"))
        features = _parse_features(raw_files) if raw_files else {}
        valid_by_id: dict[str, bool] = {}
        val_exit_code = None
        if raw_files:
            assembled = work / "assembled.city.json"
            if not assembled.is_file():
                combine_cityjsonseq(raw_files, assembled)
            report = work / "val3dity_report.json"
            process = subprocess.run(
                ["val3dity", assembled.as_posix(), "--report", report.as_posix()],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False,
            )
            (work / "val3dity.log").write_text(process.stdout or "", encoding="utf-8")
            val_exit_code = int(process.returncode)
            if report.is_file():
                valid_by_id = _val_by_id(json.loads(report.read_text(encoding="utf-8")))
        reasons: Counter[str] = Counter()
        for population_index, stable_id in ordered:
            feature = features.get(stable_id)
            valid = valid_by_id.get(stable_id)
            status, reason = _status(feature, valid)
            reasons[reason] += 1
            attrs = feature["attributes"] if feature else {}
            rows.append({
                "population_index": population_index, "stable_id": stable_id,
                "condition_id": condition, "status": status, "reason": reason,
                "lods": feature["lods"] if feature else [],
                "has_lod22": bool(feature and "2.2" in feature["lods"]),
                "val3dity_valid": valid, "rf_success": attrs.get("rf_success"),
                "rf_pointcloud_unusable": attrs.get("rf_pointcloud_unusable"),
                "rf_extrusion_mode": attrs.get("rf_extrusion_mode"),
                "rf_roof_type": attrs.get("rf_roof_type"),
                "rf_pt_density": attrs.get("rf_pt_density"),
                "rf_nodata_frac": attrs.get("rf_nodata_frac"),
                "rf_rmse_lod22": attrs.get("rf_rmse_lod22"),
                "rf_roof_planes": attrs.get("rf_roof_planes"),
                "official_PASS_usable": None, "scientific_verdict": None,
            })
        summaries[condition] = dict(reasons)
        write_new(work / "postprocess_receipt.json", canonical_json_bytes({
            "condition_id": condition, "feature_count": len(features),
            "val3dity_feature_count": len(valid_by_id), "val3dity_exit_code": val_exit_code,
            "reason_counts": dict(reasons),
            "official_PASS_usable": None, "scientific_verdict": None,
        }))
    jsonl_path = output_root / "results/building_method_results_a2_v1.jsonl"
    write_new(jsonl_path, b"".join(canonical_json_bytes(row) for row in rows))
    fields = ["population_index", "stable_id", "condition_id", "status", "reason", "has_lod22",
              "val3dity_valid", "rf_success", "rf_pointcloud_unusable", "rf_extrusion_mode",
              "rf_roof_type", "rf_pt_density", "rf_nodata_frac", "rf_rmse_lod22", "rf_roof_planes"]
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows({key: row.get(key) for key in fields} for row in rows)
    csv_path = output_root / "results/building_method_status_a2_v1.csv"
    write_new(csv_path, stream.getvalue().encode("utf-8"))
    receipt = {
        "schema": "jointbuildgs.p2.journal1_phase_a_v1.a2_finalized.v1",
        "task_id": TASK_ID,
        "stage": STAGE,
        "status": "TECHNICAL_COMPLETE_WITH_EXPLICIT_MISSINGNESS",
        "completed_utc": now_utc(),
        "building_count": len(ordered),
        "building_method_rows": len(rows),
        "roofer_invocation_count": len(CONDITIONS),
        "counts_by_condition": summaries,
        "result_jsonl": file_record(jsonl_path, output_root),
        "result_csv": file_record(csv_path, output_root),
        "official_PASS_usable": None,
        "scientific_verdict": None,
    }
    write_new(marker, canonical_json_bytes(receipt))
    return receipt


# ---------------------------------------------------------------- crops


def crops(output_root: Path, condition: str) -> dict[str, Any]:
    import laspy
    from shapely import contains_xy
    from shapely.geometry import shape

    from scripts.p2.e4_e6_redesign_s3_v1.build_viewer_assets import write_ply

    out_root = output_root / "assets_roofer_input" / condition
    receipt_path = out_root / "receipt.json"
    if receipt_path.is_file():
        return json.loads(receipt_path.read_text(encoding="utf-8"))
    journal1 = json.loads(JOURNAL1_CONFIG.read_text(encoding="utf-8"))
    origin = np.asarray(journal1["origin"], dtype=np.float64)
    footprints = json.loads((output_root / "freeze/shared_footprints.geojson").read_text(encoding="utf-8"))
    entries = sorted(
        (int(f["properties"]["population_index"]), str(f["properties"]["stable_id"]), shape(f["geometry"]).buffer(3.0))
        for f in footprints["features"]
    )
    las = laspy.read(output_root / "work" / condition / "classified_scene.laz")
    xyz = np.column_stack((np.asarray(las.x), np.asarray(las.y), np.asarray(las.z)))
    rgb = np.column_stack((np.asarray(las.red), np.asarray(las.green), np.asarray(las.blue)))
    rgb = (rgb / 257.0).clip(0, 255).astype(np.uint8)
    cls = np.asarray(las.classification).astype(np.uint8)
    class_ok = np.isin(cls, (2, 6))
    receipt_rows = []
    for population_index, stable_id, poly in entries:
        x0, y0, x1, y1 = poly.bounds
        keep = class_ok & (xyz[:, 0] >= x0) & (xyz[:, 0] <= x1) & (xyz[:, 1] >= y0) & (xyz[:, 1] <= y1)
        idx_in = np.flatnonzero(keep)
        if len(idx_in):
            inside = contains_xy(poly, xyz[idx_in, 0], xyz[idx_in, 1])
            idx_in = idx_in[inside]
        base = out_root / f"B{population_index:03d}_{stable_id}"
        write_ply(base.with_suffix(".points.ply"), xyz[idx_in] - origin, rgb[idx_in], cls[idx_in])
        receipt_rows.append({"stable_id": stable_id, "points": int(len(idx_in))})
    receipt = {
        "schema": "jointbuildgs.p2.journal1_phase_a_v1.a2_condition_roofer_inputs.v1",
        "task_id": TASK_ID,
        "stage": STAGE,
        "condition_id": condition,
        "created_utc": now_utc(),
        "definition": "footprint+3m class-2/6 crop of the A2 classified scene (viewer-local frame)",
        "scene_local_origin_xyz": origin.tolist(),
        "source": file_record(output_root / "work" / condition / "classified_scene.laz", output_root),
        "rows": receipt_rows,
        "scientific_verdict": None,
    }
    write_new(receipt_path, canonical_json_bytes(receipt))
    return receipt


# ---------------------------------------------------------------- main


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="mode", required=True)
    for name in ("prepare", "finalize"):
        p = sub.add_parser(name)
        p.add_argument("--output-root", type=Path, required=True)
        if name == "prepare":
            p.add_argument("--artifact-root", type=Path, required=True)
    for name in ("fuse", "verify-classified", "record-roofer", "crops"):
        p = sub.add_parser(name)
        p.add_argument("--output-root", type=Path, required=True)
        p.add_argument("--condition", choices=CONDITIONS, required=True)
        if name == "fuse":
            p.add_argument("--artifact-root", type=Path, required=True)
        if name == "record-roofer":
            p.add_argument("--exit-code", type=int, required=True)
            p.add_argument("--runtime-seconds", type=int, required=True)
    args = parser.parse_args()
    if args.mode == "prepare":
        result = prepare(args.output_root, args.artifact_root)
    elif args.mode == "fuse":
        result = fuse(args.output_root, args.artifact_root, args.condition)
    elif args.mode == "verify-classified":
        result = verify_classified(args.output_root, args.condition)
    elif args.mode == "record-roofer":
        result = record_roofer(args.output_root, args.condition, args.exit_code, args.runtime_seconds)
    elif args.mode == "crops":
        result = crops(args.output_root, args.condition)
    else:
        result = finalize(args.output_root)
    print(json.dumps({k: v for k, v in result.items() if k not in ("rows", "raw_als_sources", "outputs")},
                     ensure_ascii=False, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
