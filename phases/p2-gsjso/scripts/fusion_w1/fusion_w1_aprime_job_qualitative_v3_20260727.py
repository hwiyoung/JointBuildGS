#!/usr/bin/env python3
"""Publish one measured A-prime job as a strict 3x3 qualitative bundle.

The readout ``complete.json`` is the authority.  A measured job must resolve
all A-I panel sources; no placeholder is emitted.  Canonical inputs are
read-only, rendering is CPU-only, and the job directory appears atomically
with ``complete.json`` written last.  Reference GML is opened only for the
evaluation-only overlay.  This adapter does not invent a CityJSON-to-CityGML
conversion when the pinned repository/image has no trusted serializer.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import importlib.util
import json
import math
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager, patches
import numpy as np
from PIL import Image
from matplotlib.collections import PolyCollection


REPO = Path(__file__).resolve().parents[4]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.artifact_paths import logical_display_path, resolve_existing_path  # noqa: E402

DEFAULT_CONFIG = (
    REPO
    / "phases/p2-gsjso/configs/fusion_w1/fusion_w1_aprime_job_qualitative_v3_20260727.json"
)
CONFIG_SCHEMA = "jointbuildgs.fusion_w1_aprime.job_qualitative.config.v3"
RECEIPT_SCHEMA = "jointbuildgs.fusion_w1_aprime.job_qualitative.complete.v3"
COMPONENT_KEYS = tuple("ABCDEFGHI")


class JobQualitativeError(RuntimeError):
    """A measured-job source or publication contract failed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise JobQualitativeError(message)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def repo_path(value: str | Path) -> Path:
    return resolve_existing_path(REPO, value)


def display_path(path: Path) -> str:
    return logical_display_path(REPO, path)


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise JobQualitativeError(f"cannot read JSON {display_path(path)}: {exc}") from exc
    require(isinstance(value, dict), f"JSON root is not an object: {display_path(path)}")
    return value


def read_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8", newline="") as stream:
            return [dict(row) for row in csv.DictReader(stream)]
    except OSError as exc:
        raise JobQualitativeError(f"cannot read CSV {display_path(path)}: {exc}") from exc


def file_record(path: Path, *, path_value: str | None = None) -> dict[str, Any]:
    require(path.is_file(), f"required file absent: {display_path(path)}")
    return {
        "path": path_value if path_value is not None else display_path(path),
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
    }


def verify_record(record: Mapping[str, Any], label: str) -> dict[str, Any]:
    require(isinstance(record.get("path"), str), f"{label} path absent")
    require(isinstance(record.get("sha256"), str), f"{label} sha256 absent")
    path = repo_path(str(record["path"]))
    actual = file_record(path)
    require(actual["sha256"] == record["sha256"], f"{label} sha256 drift")
    if "bytes" in record:
        require(actual["bytes"] == record["bytes"], f"{label} byte-size drift")
    return actual


def verify_large_locked_record(record: Mapping[str, Any], label: str) -> dict[str, Any]:
    """Rehash a large locked input and verify its complete path/size/hash lock."""
    path = repo_path(str(record["path"]))
    require(path.is_file(), f"{label} absent: {display_path(path)}")
    actual = file_record(path, path_value=str(record["path"]))
    require(actual["bytes"] == record["bytes"], f"{label} byte-size drift")
    require(actual["sha256"] == record["sha256"], f"{label} sha256 drift")
    actual.update({
        "path": str(record["path"]),
        "runtime_verification": str(record["runtime_verification"]),
    })
    return actual


def verify_projection_config_migration(
    source_hashes: Mapping[str, Any], migration: Mapping[str, Any]
) -> dict[str, Any]:
    """Verify one path-only projection-config migration against its source-lock."""

    bound_path = str(migration.get("preprocess_bound_path", ""))
    bound_sha = str(migration.get("preprocess_bound_sha256", ""))
    require(source_hashes.get(bound_path) == bound_sha, "preprocess projection lock drift")
    require(
        migration.get("allowed_json_pointer_difference") == "/a1_zeta_ls/updated_by",
        "projection migration difference scope drift",
    )
    current_path = repo_path(str(migration.get("current_path", "")))
    current_record = file_record(current_path)
    require(current_record["sha256"] == migration.get("current_sha256"), "current projection config drift")

    artifact_root = os.environ.get("JBGS_ARTIFACT_ROOT")
    require(bool(artifact_root), "JBGS_ARTIFACT_ROOT is required for projection migration verification")
    locked_path = Path(str(artifact_root)) / str(migration.get("source_lock_artifact_path", ""))
    locked_record = file_record(locked_path)
    require(locked_record["sha256"] == bound_sha, "source-lock projection config drift")

    locked = load_json(locked_path)
    current = load_json(current_path)
    locked_node = locked.get("a1_zeta_ls", {})
    current_node = current.get("a1_zeta_ls", {})
    require(locked_node.get("updated_by") == migration.get("locked_value"), "locked migration value drift")
    require(current_node.get("updated_by") == migration.get("current_value"), "current migration value drift")
    locked_node = dict(locked_node)
    current_node = dict(current_node)
    locked_node.pop("updated_by", None)
    current_node.pop("updated_by", None)
    locked["a1_zeta_ls"] = locked_node
    current["a1_zeta_ls"] = current_node
    require(locked == current, "projection config changed beyond the allowed path metadata")
    return {
        "preprocess_bound_path": bound_path,
        "preprocess_bound_sha256": bound_sha,
        "current_path": str(migration["current_path"]),
        "current_sha256": str(migration["current_sha256"]),
        "allowed_json_pointer_difference": str(migration["allowed_json_pointer_difference"]),
        "scientific_fields_equal": True,
    }


def load_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    config = load_json(path)
    require(config.get("schema") == CONFIG_SCHEMA, "job qualitative config schema drift")
    require(config.get("run_id") == "20260726_fusion_w1_aprime", "run ID drift")
    require(config.get("branch") == "exp/fusion-w1", "branch lock drift")
    implementation = config.get("implementation_files")
    require(isinstance(implementation, list) and len(implementation) == 5, "implementation file set drift")
    for value in implementation:
        require(not Path(str(value)).is_absolute(), "implementation path must be repo-relative")
        require(repo_path(str(value)).is_file(), f"implementation absent: {value}")

    locked = config.get("locked_inputs", {})
    require(
        set(locked) == {
            "targets",
            "report_module",
            "requirements",
            "stage3_cityjson_exporter",
            "reference_gml",
        },
        "locked input set drift",
    )
    for name in ("targets", "report_module", "requirements", "stage3_cityjson_exporter"):
        verify_record(locked[name], name)
    references = locked["reference_gml"]
    require(isinstance(references, list) and len(references) == 2, "reference GML lock drift")
    for index, record in enumerate(references):
        verify_large_locked_record(record, f"reference_gml[{index}]")

    visual = config.get("visual_contract", {})
    require(visual.get("rows") == 3 and visual.get("columns") == 3, "panel grid drift")
    require(tuple(visual.get("component_order", [])) == COMPONENT_KEYS, "A-I order drift")
    require(visual.get("placeholders_allowed_for_measured") is False, "placeholder policy drift")
    require(int(visual.get("maximum_mesh_faces", 0)) > 0, "mesh face render limit drift")
    components = visual.get("components")
    require(isinstance(components, list) and len(components) == 9, "component contract drift")
    require(tuple(item.get("key") for item in components) == COMPONENT_KEYS, "component key drift")
    for item in components:
        require(bool(item.get("title_ko")), f"{item.get('key')} Korean title absent")
        require(bool(item.get("title_en")), f"{item.get('key')} English title absent")
        require("범례/Legend:" in str(item.get("legend_bilingual", "")), f"{item.get('key')} legend drift")
    panel_a = components[0]
    require("지붕 실루엣" in panel_a["title_ko"], "panel A roof-silhouette meaning absent")
    require("roof silhouette" in panel_a["title_en"], "panel A English roof-silhouette meaning absent")
    require("평면 footprint 아님" in panel_a["legend_bilingual"], "panel A non-footprint warning absent")
    require(
        panel_a.get("geometry_semantics") == "target roof silhouette M_j; not a planimetric footprint",
        "panel A geometry semantics drift",
    )

    serialization = config.get("serialization_audit", {})
    require(serialization.get("canonical_roofer_cityjson_required") is True, "CityJSON requirement drift")
    require(serialization.get("trusted_cityjson_to_citygml_converter_available") is False, "converter audit drift")
    require(serialization.get("arbitrary_citygml_conversion_allowed") is False, "arbitrary GML conversion enabled")
    require(serialization.get("citygml_unavailable_state") == "CENSORED", "CityGML state drift")
    require(serialization.get("citygml_unavailable_availability") == "UNAVAILABLE", "CityGML availability drift")

    publication = config.get("publication", {})
    require(publication.get("measured_jobs_only") is True, "measured-only policy drift")
    require(publication.get("placeholder_count_required") == 0, "placeholder count drift")
    require(publication.get("job_directory_atomic_publish") is True, "atomic publish drift")
    require(publication.get("overwrite_allowed") is False, "overwrite policy drift")
    require(publication.get("receipt_written_last") is True, "receipt-last policy drift")
    require(publication.get("scientific_verdict") is None, "scientific verdict must be null")

    outputs = config.get("outputs", {})
    expected_root = "phases/p2-gsjso/runs/fusion_w1/20260726_fusion_w1_aprime/review_v3"
    require(outputs.get("root") == expected_root, "review v3 root drift")
    require(outputs.get("complete") == "complete.json", "receipt name drift")
    execution = config.get("execution", {})
    require(execution.get("network") == "none", "network contract drift")
    require(execution.get("gpus_required") is False, "qualitative renderer must be CPU-only")
    require(execution.get("nonroot") is True, "nonroot contract drift")
    return config


def load_report_module(config: Mapping[str, Any]) -> Any:
    record = config["locked_inputs"]["report_module"]
    verify_record(record, "report_module")
    path = repo_path(record["path"])
    spec = importlib.util.spec_from_file_location("fusion_w1_aprime_report_v3_locked", path)
    require(spec is not None and spec.loader is not None, "cannot load report helper module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def identity_key(building_id: str, arm: str, replicate: str) -> str:
    return f"{building_id}/arm_{arm}/{replicate}"


def validate_identity(
    config: Mapping[str, Any], building_id: str, arm: str, replicate: str
) -> dict[str, str]:
    contract = config["identity_contract"]
    require(re.fullmatch(contract["building_id_pattern"], building_id) is not None, "invalid building ID")
    require(arm in contract["arms"], f"unsupported arm: {arm}")
    require(replicate in contract["replicates"], f"unsupported replicate: {replicate}")
    targets = read_csv(repo_path(config["locked_inputs"]["targets"]["path"]))
    target = next((row for row in targets if row.get("building_id") == building_id), None)
    require(target is not None, f"building is not in locked A-prime targets: {building_id}")
    if arm == "Aprime":
        require(replicate in contract["aprime_replicates"], "A-prime replicate not allowed")
    else:
        require(replicate in contract["B_replicates"], "arm-B replicate not allowed")
        require(building_id in contract["B_buildings"], "building is not in locked arm-B subset")
    return dict(target)


def resolve_readout_complete(
    config: Mapping[str, Any], building_id: str, arm: str, replicate: str
) -> Path:
    values = {"building_id": building_id, "arm": arm, "replicate": replicate}
    canonical = repo_path(config["sources"]["canonical_readout_complete_template"].format(**values))
    if canonical.is_file():
        return canonical
    override = config["sources"]["readout_complete_overrides"].get(
        identity_key(building_id, arm, replicate)
    )
    require(override is not None, f"readout complete absent: {display_path(canonical)}")
    path = repo_path(override)
    require(path.is_file(), f"readout complete override absent: {display_path(path)}")
    return path


def ledger_records(readout: Mapping[str, Any]) -> list[dict[str, Any]]:
    ledger = readout.get("artifact_ledger")
    require(isinstance(ledger, list) and bool(ledger), "readout artifact ledger absent")
    records: list[dict[str, Any]] = []
    for record in ledger:
        require(isinstance(record, dict), "artifact ledger item is not an object")
        require(set(record) == {"path", "sha256", "bytes"}, "artifact ledger record drift")
        records.append(dict(record))
    require(readout.get("artifact_count") == len(records), "artifact ledger count drift")
    return records


def select_ledger_record(
    records: Sequence[Mapping[str, Any]], label: str, predicate: Any
) -> dict[str, Any]:
    matches = [dict(record) for record in records if predicate(str(record["path"]))]
    require(len(matches) == 1, f"{label} ledger resolution expected 1, found {len(matches)}")
    verify_record(matches[0], label)
    return matches[0]


def recursive_record_match(value: Any, record: Mapping[str, Any]) -> bool:
    if isinstance(value, Mapping):
        if value.get("path") == record["path"] and value.get("sha256") == record["sha256"]:
            return True
        return any(recursive_record_match(child, record) for child in value.values())
    if isinstance(value, list):
        return any(recursive_record_match(child, record) for child in value)
    return False


def require_binding(payload: Mapping[str, Any], record: Mapping[str, Any], label: str) -> None:
    require(recursive_record_match(payload, record), f"provenance binding absent: {label}")


def coordinate_stats(xyz: np.ndarray, label: str, *, vertical: bool = False) -> dict[str, Any]:
    values = np.asarray(xyz, dtype=np.float64)
    require(values.ndim == 2 and values.shape[1] == 3, f"{label} coordinates are not N x 3")
    require(len(values) >= 3 and np.isfinite(values).all(), f"{label} is empty or non-finite")
    minimum = values.min(axis=0)
    maximum = values.max(axis=0)
    span = maximum - minimum
    require(max(float(span[0]), float(span[1])) > 1e-6, f"{label} has no XY extent")
    if vertical:
        require(float(span[2]) > 1e-6, f"{label} has no Z extent")
    return {
        "points_n": int(len(values)),
        "minimum_xyz": [float(value) for value in minimum],
        "maximum_xyz": [float(value) for value in maximum],
        "span_xyz": [float(value) for value in span],
    }


def ring_stats(rings: Sequence[np.ndarray], label: str) -> dict[str, Any]:
    require(bool(rings), f"{label} has no rings")
    vertices = 0
    for ring in rings:
        values = np.asarray(ring, dtype=np.float64)
        require(values.ndim == 2 and values.shape[1] >= 3, f"{label} ring shape invalid")
        require(len(values) >= 3 and np.isfinite(values[:, :3]).all(), f"{label} ring invalid")
        vertices += len(values)
    return {"rings_n": len(rings), "vertices_n": int(vertices)}


def png_stats(path: Path, minimum: Sequence[int]) -> dict[str, Any]:
    require(path.is_file(), f"panel absent: {display_path(path)}")
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
    except (OSError, ValueError) as exc:
        raise JobQualitativeError(f"invalid panel PNG: {exc}") from exc
    height, width = rgb.shape[:2]
    require(width >= int(minimum[0]) and height >= int(minimum[1]), "panel dimensions too small")
    stride = max(1, int(math.sqrt((width * height) / 120000)))
    sample = rgb[::stride, ::stride].reshape(-1, 3)
    unique = int(len(np.unique(sample, axis=0)))
    deviation = float(sample.astype(np.float64).std())
    require(unique >= 64 and deviation >= 5.0, "panel is blank or placeholder-like")
    return {
        "width": width,
        "height": height,
        "sampled_unique_colors": unique,
        "sampled_rgb_std": deviation,
    }


def selected_image_and_mask(preprocess_root: Path) -> dict[str, Any]:
    index_path = preprocess_root / "supervision_index.csv"
    rows = read_csv(index_path)
    require(bool(rows), "supervision index is empty")
    row = max(rows, key=lambda item: int(item.get("mask_pixels_n", "0")))
    prior_path = repo_path(row["class6_npz_path"])
    image_path = preprocess_root / "images" / row["image_name"]
    require(image_path.is_file(), f"selected image absent: {display_path(image_path)}")
    require(prior_path.is_file(), f"selected M_j prior absent: {display_path(prior_path)}")
    with np.load(prior_path, allow_pickle=False) as archive:
        require("valid_M_j" in archive.files, "selected prior has no valid_M_j")
        mask = np.asarray(archive["valid_M_j"]).astype(bool)
    with Image.open(image_path) as source:
        image = source.convert("RGB")
        image.load()
    require(mask.shape == (image.height, image.width), "M_j/image shape mismatch")
    y, x = np.nonzero(mask)
    require(len(x) > 0, "selected M_j is empty")
    require(len(x) == int(row["mask_pixels_n"]), "selected M_j cardinality drift")
    x0, x1 = int(x.min()), int(x.max()) + 1
    y0, y1 = int(y.min()), int(y.max()) + 1
    padding = 0.2
    pad_x = max(8, int((x1 - x0) * padding))
    pad_y = max(8, int((y1 - y0) * padding))
    crop_box = (
        max(0, x0 - pad_x),
        max(0, y0 - pad_y),
        min(image.width, x1 + pad_x),
        min(image.height, y1 + pad_y),
    )
    return {
        "row": row,
        "image": image,
        "mask": mask,
        "crop_box": crop_box,
        "image_record": file_record(image_path),
        "prior_record": file_record(prior_path),
        "index_record": file_record(index_path),
    }


def serialization_capability(config: Mapping[str, Any]) -> dict[str, Any]:
    audit = config["serialization_audit"]
    version = importlib.metadata.version("cjio")
    require(version == audit["cjio"]["required_version"], f"cjio version drift: {version}")
    from cjio import cityjson

    methods = sorted(
        name.removeprefix("export2")
        for name in dir(cityjson.CityJSON)
        if name.startswith("export2")
    )
    require(methods == sorted(audit["cjio"]["observed_export_formats"]), "cjio export format drift")
    require("gml" not in methods and "citygml" not in methods, "unexpected trusted GML exporter appeared")
    return {
        "state": audit["citygml_unavailable_state"],
        "availability": audit["citygml_unavailable_availability"],
        "reason_code": audit["citygml_unavailable_reason_code"],
        "generation_attempted": False,
        "generated_artifact": None,
        "arbitrary_conversion_prohibited": True,
        "cjio": {
            "version": version,
            "observed_export_formats": methods,
            "citygml_or_gml_export_supported": False,
        },
        "repo_exporter": {
            **verify_record(
                config["locked_inputs"]["stage3_cityjson_exporter"],
                "stage3_cityjson_exporter",
            ),
            "observed_role": audit["repo_exporter_audit"]["observed_role"],
            "cityjson_to_citygml_serializer_present": False,
        },
        "derived_export_rule": audit["derived_gml_copy_rule"],
    }


def resolve_evidence(
    config: Mapping[str, Any], report: Any, building_id: str, arm: str, replicate: str
) -> dict[str, Any]:
    target = validate_identity(config, building_id, arm, replicate)
    complete_path = resolve_readout_complete(config, building_id, arm, replicate)
    readout = load_json(complete_path)
    contract = config["identity_contract"]
    require(readout.get("schema") == contract["readout_complete_schema"], "readout complete schema drift")
    require(readout.get("state") == contract["required_readout_state"], "readout is not COMPLETE")
    identity = readout.get("identity", {})
    require(identity.get("building_id") == building_id, "readout building drift")
    require(identity.get("arm") == arm, "readout arm drift")
    require(identity.get("replicate") == replicate, "readout replicate drift")
    primary = readout.get("primary", {})
    require(
        primary.get("measurement_status") == contract["required_primary_measurement_status"],
        "qualitative publication requires primary MEASURED",
    )
    require(primary.get("assembly_status") == "MEASURED", "primary assembly is not measured")
    require(readout.get("interpretation_or_verdict") is None, "readout contains interpretation or verdict")

    ledger = ledger_records(readout)
    attempt_record = dict(readout.get("attempt_materialization") or {})
    verify_record(attempt_record, "attempt materialization")
    require(any(record == attempt_record for record in ledger), "attempt materialization is absent from ledger")
    attempt = load_json(repo_path(attempt_record["path"]))
    require(attempt.get("schema") == "jointbuildgs.fusion_w1_aprime.readout.attempt.v1", "attempt schema drift")
    attempt_identity = attempt.get("identity", {})
    require(attempt_identity.get("building_id") == building_id, "attempt building drift")
    require(attempt_identity.get("arm") == arm, "attempt arm drift")
    require(attempt_identity.get("replicate") == replicate, "attempt replicate drift")

    mesh_record = select_ledger_record(
        ledger,
        "TSDF orthometric filtered mesh",
        lambda path: path.endswith("/tsdf/tsdf_mesh_filtered_epsg25832_orthometric.ply"),
    )
    samples_record = select_ledger_record(
        ledger,
        "TSDF surface samples",
        lambda path: path.endswith("/tsdf/tsdf_surface_samples.npz"),
    )
    cityjson_record = select_ledger_record(
        ledger,
        "canonical Roofer CityJSON",
        lambda path: path.endswith(".city.json") and "/primary/engine/" in path and "/cityjson/" in path,
    )
    tsdf_record = select_ledger_record(
        ledger,
        "TSDF receipt",
        lambda path: path.endswith("/tsdf/tsdf_receipt.json"),
    )
    for record, label in (
        (mesh_record, "mesh"),
        (samples_record, "surface samples"),
        (cityjson_record, "CityJSON"),
        (tsdf_record, "TSDF receipt"),
    ):
        require_binding(readout, record, f"readout complete to {label}")

    training_record = dict(attempt.get("training", {}).get("completed") or {})
    verify_record(training_record, "training complete")
    training = load_json(repo_path(training_record["path"]))
    require(training.get("schema") == "jointbuildgs.fusion_w1_aprime.training_completed.v1", "training schema drift")
    require(training.get("status") == "COMPLETED", "training is not completed")
    require(training.get("building_id") == building_id, "training building drift")
    require(training.get("arm") == arm and training.get("replicate") == replicate, "training identity drift")
    require(training.get("training_completion", {}).get("status") == "PASSED", "training completion gate failed")
    require_binding(attempt, training_record, "attempt to training complete")

    data_root_value = attempt.get("training", {}).get("data_root")
    require(isinstance(data_root_value, str), "attempt training data_root absent")
    preprocess_root = repo_path(data_root_value)
    require(preprocess_root.is_dir(), "preprocess root absent")
    preprocess_path = preprocess_root / "preprocess_manifest.json"
    preprocess_record = file_record(preprocess_path)
    preprocess = load_json(preprocess_path)
    require(preprocess.get("schema") == "jointbuildgs.fusion_w1_aprime.preprocess_building.v1", "preprocess schema drift")
    require(preprocess.get("status") == "PASSED", "preprocess did not pass")
    require(preprocess.get("building", {}).get("building_id") == building_id, "preprocess building drift")
    require(
        preprocess.get("supervision", {}).get("mask_normalization_denominator") == "cardinality_M_j",
        "M_j normalization drift",
    )

    image_mask = selected_image_and_mask(preprocess_root)
    seed_path = preprocess_root / "seed_class6_filtered_canonical.npz"
    seed_record = file_record(seed_path)
    seed_xyz, seed_rgb = report.npz_xyz_rgb(
        seed_path, ("xyz_base_epsg25832_orthometric", "xyz")
    )
    seed_stats = coordinate_stats(seed_xyz, "pre-training ALS seed")
    require(seed_rgb is not None and seed_rgb.shape == (len(seed_xyz), 3), "seed RGB absent")

    mesh_xyz, mesh_faces = load_triangle_mesh(repo_path(mesh_record["path"]))
    mesh_stats = coordinate_stats(mesh_xyz, "TSDF mesh", vertical=True)
    mesh_stats.update({"faces_n": len(mesh_faces), "rendered_as": "triangle_faces_top_view"})
    samples_xyz, samples_rgb = report.npz_xyz_rgb(
        repo_path(samples_record["path"]),
        ("xyz_epsg25832_orthometric", "xyz_canonical_ellipsoidal", "xyz"),
    )
    samples_stats = coordinate_stats(samples_xyz, "TSDF surface samples", vertical=True)
    if samples_rgb is not None:
        require(samples_rgb.shape == (len(samples_xyz), 3), "surface sample RGB malformed")

    cityjson_payload = load_json(repo_path(cityjson_record["path"]))
    require(cityjson_payload.get("type") == "CityJSON", "canonical Roofer artifact is not CityJSON")
    cityjson_rings = report.cityjson_rings(repo_path(cityjson_record["path"]))
    cityjson_stats = ring_stats(cityjson_rings, "canonical Roofer CityJSON")
    reference_records = [
        verify_large_locked_record(record, f"reference_gml[{index}]")
        for index, record in enumerate(config["locked_inputs"]["reference_gml"])
    ]
    reference_rings = report.gml_rings_by_building(
        [repo_path(record["path"]) for record in reference_records], [building_id]
    )[building_id]
    reference_stats = ring_stats(reference_rings, "evaluation-only reference GML")

    job = report.Job(1, building_id, arm, replicate, target)
    training_logical_root = Path(str(training_record["path"])).parent
    opacity_lineage = repo_path(training_logical_root / "audit/seed_lineage.csv")
    opacity_rows, opacity_state, opacity_scope = report.load_opacity_rows(
        job, opacity_lineage.parent.parent
    )
    require(opacity_state == "measured", f"opacity trajectory is {opacity_state}: {opacity_scope}")
    initial_phase = config["visual_contract"]["opacity_initial_observation_phase"]
    line_phase = config["visual_contract"]["opacity_line_observation_phase"]
    initial = [row for row in opacity_rows if row.get("observation_phase") == initial_phase]
    dynamics = [row for row in opacity_rows if row.get("observation_phase") == line_phase]
    require(bool(initial) and len(dynamics) >= 2, "opacity initial/dynamics observations incomplete")
    require(all(math.isfinite(float(row["opacity_median"])) for row in opacity_rows), "opacity non-finite")
    iterations = sorted({int(row["iteration"]) for row in dynamics})
    require(iterations[0] <= 15000 and iterations[-1] >= 20000, "opacity trajectory misses schedule phases")

    training_completion = training["training_completion"]
    lineage = training_completion["seed_lineage_audit"]
    lineage_record = verify_record(
        {"path": lineage["path"], "sha256": lineage["sha256"]}, "seed lineage"
    )
    initialization_record = verify_record(
        lineage["initialization_receipt"], "seed initialization"
    )
    source_records = {
        "readout_complete": file_record(complete_path),
        "attempt": verify_record(attempt_record, "attempt materialization"),
        "training_complete": verify_record(training_record, "training complete"),
        "preprocess_manifest": preprocess_record,
        "supervision_index": image_mask["index_record"],
        "selected_full_image": image_mask["image_record"],
        "selected_M_j": image_mask["prior_record"],
        "pretraining_seed": seed_record,
        "tsdf_mesh": verify_record(mesh_record, "TSDF mesh"),
        "tsdf_surface_samples": verify_record(samples_record, "TSDF samples"),
        "tsdf_receipt": verify_record(tsdf_record, "TSDF receipt"),
        "canonical_roofer_cityjson": verify_record(cityjson_record, "canonical Roofer CityJSON"),
        "seed_lineage": lineage_record,
        "seed_initialization": initialization_record,
    }
    return {
        "identity": {
            "run_id": config["run_id"],
            "building_id": building_id,
            "arm": arm,
            "replicate": replicate,
        },
        "target": target,
        "readout": readout,
        "source_readout_complete": source_records["readout_complete"],
        "source_records": source_records,
        "reference_records": reference_records,
        "image_mask": image_mask,
        "seed_xyz": seed_xyz,
        "seed_rgb": seed_rgb,
        "mesh_xyz": mesh_xyz,
        "mesh_faces": mesh_faces,
        "samples_xyz": samples_xyz,
        "samples_rgb": samples_rgb,
        "cityjson_rings": cityjson_rings,
        "reference_rings": reference_rings,
        "opacity_rows": opacity_rows,
        "opacity_scope": opacity_scope,
        "cityjson_path": repo_path(cityjson_record["path"]),
        "inspection": {
            "input_view": {
                "image_name": image_mask["row"]["image_name"],
                "mask_pixels_n": int(image_mask["row"]["mask_pixels_n"]),
                "image_size": [image_mask["image"].width, image_mask["image"].height],
                "crop_box_xyxy": list(image_mask["crop_box"]),
            },
            "seed": seed_stats,
            "tsdf_mesh": mesh_stats,
            "tsdf_surface_samples": samples_stats,
            "canonical_roofer_cityjson": cityjson_stats,
            "evaluation_only_reference_gml": reference_stats,
            "opacity": {
                "state": opacity_state,
                "scope": opacity_scope,
                "rows_n": len(opacity_rows),
                "initial_rows_n": len(initial),
                "dynamics_rows_n": len(dynamics),
                "minimum_iteration": iterations[0],
                "maximum_iteration": iterations[-1],
            },
        },
        "serialization_capability": serialization_capability(config),
    }


def current_source_snapshot(evidence: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        role: verify_record(record, role)
        for role, record in evidence["source_records"].items()
    }


def rgb_colors(rgb: np.ndarray | None, count: int, fallback: str) -> Any:
    if rgb is None or rgb.shape != (count, 3):
        return fallback
    values = np.asarray(rgb, dtype=np.float64)
    if float(np.nanmax(values)) > 1.0:
        values = values / 255.0
    return np.clip(values, 0.0, 1.0)


def downsample_xyz_rgb(
    xyz: np.ndarray, rgb: np.ndarray | None, limit: int
) -> tuple[np.ndarray, np.ndarray | None]:
    if len(xyz) <= limit:
        return xyz, rgb
    indices = np.linspace(0, len(xyz) - 1, limit, dtype=np.int64)
    return xyz[indices], rgb[indices] if rgb is not None and len(rgb) == len(xyz) else None


def load_triangle_mesh(path: Path) -> tuple[np.ndarray, np.ndarray]:
    try:
        import open3d as o3d
    except ImportError as exc:  # pragma: no cover - pinned image includes Open3D
        raise JobQualitativeError("Open3D is required to render TSDF mesh faces") from exc
    mesh = o3d.io.read_triangle_mesh(str(path))
    xyz = np.asarray(mesh.vertices, dtype=np.float64)
    faces = np.asarray(mesh.triangles, dtype=np.int64)
    require(xyz.ndim == 2 and xyz.shape[1] == 3 and len(xyz) > 2, "TSDF mesh vertices malformed")
    require(faces.ndim == 2 and faces.shape[1] == 3 and len(faces) > 0, "TSDF mesh triangle faces absent")
    require(int(faces.min()) >= 0 and int(faces.max()) < len(xyz), "TSDF mesh face index out of range")
    require(np.isfinite(xyz).all(), "TSDF mesh vertices contain non-finite values")
    return xyz, faces


def mesh_top(
    ax: plt.Axes,
    xyz: np.ndarray,
    faces: np.ndarray,
    config: Mapping[str, Any],
) -> None:
    limit = int(config["visual_contract"]["maximum_mesh_faces"])
    selected = faces
    if len(selected) > limit:
        indices = np.linspace(0, len(selected) - 1, limit, dtype=np.int64)
        selected = selected[indices]
    xy = np.asarray(xyz, dtype=np.float64)[:, :2]
    triangles = xy[np.asarray(selected, dtype=np.int64)]
    palette = config["visual_contract"]["palette"]
    collection = PolyCollection(
        triangles,
        facecolors=palette["blue_light"],
        edgecolors=palette["blue"],
        linewidths=0.08,
        alpha=0.82,
        rasterized=True,
    )
    ax.add_collection(collection)
    ax.update_datalim(xy)
    ax.autoscale_view()
    ax.set_xlabel("E / X (m)", fontsize=7)
    ax.set_ylabel("N / Y (m)", fontsize=7)
    ax.set_aspect("equal", adjustable="datalim")


def scatter_top(
    ax: plt.Axes,
    xyz: np.ndarray,
    rgb: np.ndarray | None,
    config: Mapping[str, Any],
) -> None:
    values, colors = downsample_xyz_rgb(
        np.asarray(xyz), rgb, int(config["visual_contract"]["maximum_scatter_points"])
    )
    ax.scatter(
        values[:, 0],
        values[:, 1],
        s=1.1,
        c=rgb_colors(colors, len(values), config["visual_contract"]["palette"]["blue"]),
        linewidths=0,
        rasterized=True,
    )
    ax.set_xlabel("E / X (m)", fontsize=7)
    ax.set_ylabel("N / Y (m)", fontsize=7)
    ax.set_aspect("equal", adjustable="datalim")


def scatter_section(
    ax: plt.Axes,
    xyz: np.ndarray,
    rgb: np.ndarray | None,
    config: Mapping[str, Any],
) -> None:
    values, colors = downsample_xyz_rgb(
        np.asarray(xyz), rgb, int(config["visual_contract"]["maximum_scatter_points"])
    )
    centered = values[:, :2] - np.median(values[:, :2], axis=0)
    _, _, vt = np.linalg.svd(centered, full_matrices=False)
    horizontal = centered @ vt[0]
    ax.scatter(
        horizontal,
        values[:, 2],
        s=1.1,
        c=rgb_colors(colors, len(values), config["visual_contract"]["palette"]["blue"]),
        linewidths=0,
        rasterized=True,
    )
    ax.set_xlabel("principal XY axis (m)", fontsize=7)
    ax.set_ylabel("orthometric Z (m)", fontsize=7)
    ax.set_aspect("equal", adjustable="datalim")


def plot_rings(
    ax: plt.Axes,
    rings: Sequence[np.ndarray],
    *,
    color: str,
    linestyle: str = "-",
    linewidth: float = 0.9,
) -> None:
    for ring in rings:
        values = np.asarray(ring)
        closed = np.vstack([values, values[0]]) if not np.array_equal(values[0], values[-1]) else values
        ax.plot(closed[:, 0], closed[:, 1], color=color, linestyle=linestyle, linewidth=linewidth)
    ax.set_xlabel("E (m)", fontsize=7)
    ax.set_ylabel("N (m)", fontsize=7)
    ax.set_aspect("equal", adjustable="datalim")


def component_contract(config: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [dict(item) for item in config["visual_contract"]["components"]]


def label_component(
    ax: plt.Axes, spec: Mapping[str, Any], font: font_manager.FontProperties
) -> None:
    ax.set_title(
        f"{spec['key']}. {spec['title_ko']}\n{spec['title_en']}",
        fontproperties=font,
        fontsize=9.2,
        color="#252a31",
        pad=7,
    )
    ax.text(
        0.5,
        -0.17,
        spec["legend_bilingual"],
        transform=ax.transAxes,
        ha="center",
        va="top",
        fontsize=5.6,
        color="#252a31",
        fontproperties=font,
        wrap=False,
    )
    ax.tick_params(labelsize=6)
    ax.grid(True, color="#e3e7eb", linewidth=0.45)


def load_cjk_font(config: Mapping[str, Any]) -> tuple[font_manager.FontProperties, dict[str, Any]]:
    record = config["visual_contract"]["cjk_font"]
    override = os.environ.get("APRIME_JOB_QUALITATIVE_FONT")
    path = Path(override or record["container_path"])
    require(path.is_file(), f"CJK font absent: {path}")
    actual = file_record(path, path_value=str(path))
    require(actual["sha256"] == record["sha256"], "CJK font sha256 drift")
    require(actual["bytes"] == record["bytes"], "CJK font byte-size drift")
    font_manager.fontManager.addfont(str(path))
    return font_manager.FontProperties(fname=str(path)), actual


def render_panel(
    staging: Path,
    config: Mapping[str, Any],
    evidence: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, bool], dict[str, Any]]:
    font, font_record = load_cjk_font(config)
    visual = config["visual_contract"]
    palette = visual["palette"]
    specs = component_contract(config)
    fig, axes = plt.subplots(3, 3, figsize=tuple(visual["panel_inches"]))
    fig.subplots_adjust(left=0.045, right=0.985, bottom=0.06, top=0.91, wspace=0.24, hspace=0.42)
    identity = evidence["identity"]
    fig.suptitle(
        f"{identity['building_id']} | arm {identity['arm']} | {identity['replicate']}\n"
        "동별 정성 검토 패널 / Per-job qualitative review panel",
        fontproperties=font,
        fontsize=13,
        color=palette["charcoal"],
    )

    image_mask = evidence["image_mask"]
    image = np.asarray(image_mask["image"])
    mask = np.asarray(image_mask["mask"])
    crop_box = image_mask["crop_box"]

    ax = axes[0, 0]
    ax.imshow(image)
    ax.contour(mask.astype(np.uint8), levels=[0.5], colors=[palette["orange"]], linewidths=1.3)
    x0, y0, x1, y1 = crop_box
    ax.add_patch(
        patches.Rectangle(
            (x0, y0), x1 - x0, y1 - y0, fill=False, edgecolor="black", linewidth=2.5
        )
    )
    ax.add_patch(
        patches.Rectangle(
            (x0, y0),
            x1 - x0,
            y1 - y0,
            fill=False,
            edgecolor="white",
            linewidth=1.6,
            linestyle="--",
        )
    )
    ax.axis("off")
    label_component(ax, specs[0], font)

    ax = axes[0, 1]
    crop = image[y0:y1, x0:x1]
    crop_mask = mask[y0:y1, x0:x1]
    ax.imshow(crop)
    overlay = np.zeros((*crop_mask.shape, 4), dtype=np.float32)
    overlay[crop_mask] = (0.0, 0.71, 0.85, 0.38)
    ax.imshow(overlay)
    ax.contour(crop_mask.astype(np.uint8), levels=[0.5], colors=[palette["orange"]], linewidths=1.0)
    ax.axis("off")
    label_component(ax, specs[1], font)

    scatter_top(axes[0, 2], evidence["seed_xyz"], evidence["seed_rgb"], config)
    label_component(axes[0, 2], specs[2], font)

    mesh_top(axes[1, 0], evidence["mesh_xyz"], evidence["mesh_faces"], config)
    label_component(axes[1, 0], specs[3], font)

    scatter_top(axes[1, 1], evidence["samples_xyz"], evidence["samples_rgb"], config)
    label_component(axes[1, 1], specs[4], font)

    scatter_section(axes[1, 2], evidence["samples_xyz"], evidence["samples_rgb"], config)
    label_component(axes[1, 2], specs[5], font)

    plot_rings(axes[2, 0], evidence["cityjson_rings"], color=palette["blue"])
    label_component(axes[2, 0], specs[6], font)

    plot_rings(axes[2, 1], evidence["cityjson_rings"], color=palette["blue"], linewidth=1.1)
    plot_rings(
        axes[2, 1],
        evidence["reference_rings"],
        color=palette["orange"],
        linestyle="--",
        linewidth=0.9,
    )
    label_component(axes[2, 1], specs[7], font)

    ax = axes[2, 2]
    rows = evidence["opacity_rows"]
    initial_phase = visual["opacity_initial_observation_phase"]
    line_phase = visual["opacity_line_observation_phase"]
    initial = [row for row in rows if row.get("observation_phase") == initial_phase]
    dynamics = [row for row in rows if row.get("observation_phase") == line_phase]
    ax.plot(
        [int(row["iteration"]) for row in dynamics],
        [float(row["opacity_median"]) for row in dynamics],
        color=palette["blue"],
        marker="o",
        markersize=2.1,
        linewidth=1.4,
    )
    ax.scatter(
        [int(row["iteration"]) for row in initial],
        [float(row["opacity_median"]) for row in initial],
        marker="D",
        s=28,
        facecolors="white",
        edgecolors=palette["charcoal"],
        linewidths=1.0,
        zorder=4,
    )
    ax.axvline(int(visual["transition_iteration"]), color=palette["orange"], linestyle="--", linewidth=1.2)
    ax.axvline(int(visual["surface_ramp_end_iteration"]), color=palette["gold"], linestyle=":", linewidth=1.2)
    ax.set_ylim(bottom=0.0)
    ax.set_xlabel("optimizer iteration", fontsize=7)
    ax.set_ylabel("median opacity", fontsize=7)
    label_component(ax, specs[8], font)

    path = staging / config["outputs"]["panel"]
    fig.savefig(
        path,
        dpi=int(visual["panel_dpi"]),
        facecolor="white",
        metadata={"Software": "JointBuildGS A-prime job qualitative v3"},
    )
    plt.close(fig)
    quality = png_stats(path, visual["minimum_panel_pixels"])
    return quality, {key: True for key in COMPONENT_KEYS}, font_record


def write_opacity_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fields = [
        "building_id",
        "arm",
        "run",
        "iteration",
        "observation_phase",
        "scope",
        "gaussians_total",
        "seed_lineage_count",
        "opacity_median",
        "cum_prune_candidates",
        "cum_pruned",
        "cum_prune_seed_protected",
        "seed_protect_active",
        "source_path",
    ]
    with path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in fields})
        stream.flush()
        os.fsync(stream.fileno())


def write_json_exclusive(path: Path, payload: Mapping[str, Any]) -> None:
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    try:
        with path.open("x", encoding="utf-8") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as exc:
        raise JobQualitativeError(f"refusing overwrite: {display_path(path)}") from exc


def output_job_dir(
    config: Mapping[str, Any], building_id: str, arm: str, replicate: str, output_root: Path | None
) -> Path:
    if output_root is None:
        root = repo_path(config["outputs"]["root"])
    else:
        root = output_root.resolve()
    return root / "by_building" / building_id / f"arm_{arm}" / replicate


def output_record(path: Path) -> dict[str, Any]:
    return file_record(path, path_value=display_path(path))


def implementation_records(config: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [file_record(repo_path(value)) for value in config["implementation_files"]]


def verify_bundle(
    config: Mapping[str, Any], building_id: str, arm: str, replicate: str, output_root: Path | None
) -> dict[str, Any]:
    validate_identity(config, building_id, arm, replicate)
    root = output_job_dir(config, building_id, arm, replicate, output_root)
    receipt_path = root / config["outputs"]["complete"]
    receipt = load_json(receipt_path)
    expected_identity = {
        "run_id": config["run_id"],
        "building_id": building_id,
        "arm": arm,
        "replicate": replicate,
    }
    require(receipt.get("schema") == RECEIPT_SCHEMA, "job qualitative receipt schema drift")
    require(receipt.get("state") == "COMPLETE", "job qualitative receipt is not COMPLETE")
    require(receipt.get("measurement_state") == "MEASURED", "job qualitative receipt is not MEASURED")
    require(receipt.get("identity") == expected_identity, "job qualitative receipt identity drift")
    require(receipt.get("placeholder_count") == 0, "job qualitative receipt contains placeholders")
    require(receipt.get("components") == {key: True for key in COMPONENT_KEYS}, "A-I component receipt drift")
    require(receipt.get("component_contract") == component_contract(config), "component title/legend receipt drift")
    require(receipt.get("scientific_verdict") is None, "receipt contains a scientific verdict")
    require(receipt.get("interpretation") is None, "receipt contains interpretation")

    source_records = receipt.get("source_records")
    require(isinstance(source_records, dict) and bool(source_records), "source record receipt absent")
    require("readout_complete" in source_records, "readout complete source record absent")
    current_sources = {
        role: verify_record(record, f"receipt source {role}")
        for role, record in source_records.items()
    }
    require(current_sources == source_records, "receipt source records do not match current source hashes")
    source_readout = receipt.get("source_readout_complete")
    require(source_readout == source_records["readout_complete"], "source readout duplicate record drift")
    current_readout_path = resolve_readout_complete(config, building_id, arm, replicate)
    current_readout = file_record(current_readout_path)
    require(source_readout == current_readout, "receipt source readout is not the current readout complete")

    receipt_implementation = receipt.get("implementation")
    require(isinstance(receipt_implementation, list), "implementation receipt absent")
    require(
        receipt_implementation == implementation_records(config),
        "receipt implementation does not match current implementation hashes",
    )
    locked_references = [
        verify_large_locked_record(record, f"reference_gml[{index}]")
        for index, record in enumerate(config["locked_inputs"]["reference_gml"])
    ]
    reference_receipt = receipt.get("reference_gml")
    require(isinstance(reference_receipt, dict), "reference GML receipt absent")
    require(reference_receipt.get("role") == "evaluation_only", "reference GML role drift")
    require(reference_receipt.get("records") == locked_references, "reference GML receipt/hash drift")

    expected_files = {
        config["outputs"]["panel"],
        config["outputs"]["opacity_csv"],
        config["outputs"]["canonical_roofer_cityjson"],
        config["outputs"]["complete"],
    }
    require({path.name for path in root.iterdir()} == expected_files, "job bundle file set drift")
    for role, filename in (
        ("panel", config["outputs"]["panel"]),
        ("opacity_csv", config["outputs"]["opacity_csv"]),
        ("canonical_roofer_cityjson", config["outputs"]["canonical_roofer_cityjson"]),
    ):
        require(receipt.get("outputs", {}).get(role) == output_record(root / filename), f"{role} output drift")
    png_stats(root / config["outputs"]["panel"], config["visual_contract"]["minimum_panel_pixels"])
    source_cityjson = source_records["canonical_roofer_cityjson"]
    require(
        receipt["outputs"]["canonical_roofer_cityjson"]["sha256"] == source_cityjson["sha256"],
        "bundled Roofer CityJSON is not byte-identical to canonical source",
    )
    citygml = receipt.get("citygml_export", {})
    require(citygml.get("state") == "CENSORED", "CityGML export state drift")
    require(citygml.get("availability") == "UNAVAILABLE", "CityGML export availability drift")
    require(citygml.get("generation_attempted") is False, "untrusted CityGML generation attempted")
    require(receipt.get("publication", {}).get("receipt_written_last") is True, "receipt-last flag absent")
    require(receipt.get("publication", {}).get("source_inputs_unchanged") is True, "source immutability flag absent")
    return receipt


def publish_job(
    config: Mapping[str, Any],
    report: Any,
    building_id: str,
    arm: str,
    replicate: str,
    output_root: Path | None = None,
) -> dict[str, Any]:
    destination = output_job_dir(config, building_id, arm, replicate, output_root)
    receipt_path = destination / config["outputs"]["complete"]
    if receipt_path.is_file():
        return verify_bundle(config, building_id, arm, replicate, output_root)
    require(not destination.exists(), f"refusing incomplete/nonempty job bundle: {display_path(destination)}")

    evidence = resolve_evidence(config, report, building_id, arm, replicate)
    source_before = current_source_snapshot(evidence)
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{replicate}.staging-", dir=destination.parent))
    try:
        render_quality, components, font_record = render_panel(staging, config, evidence)
        opacity_path = staging / config["outputs"]["opacity_csv"]
        write_opacity_csv(opacity_path, evidence["opacity_rows"])
        cityjson_copy = staging / config["outputs"]["canonical_roofer_cityjson"]
        shutil.copyfile(evidence["cityjson_path"], cityjson_copy)
        with cityjson_copy.open("rb") as stream:
            os.fsync(stream.fileno())
        source_after = current_source_snapshot(evidence)
        require(source_after == source_before, "source inputs changed during render")
        require(
            sha256_file(cityjson_copy)
            == evidence["source_records"]["canonical_roofer_cityjson"]["sha256"],
            "canonical Roofer CityJSON copy drift",
        )

        outputs = {
            "panel": output_record(staging / config["outputs"]["panel"]),
            "opacity_csv": output_record(opacity_path),
            "canonical_roofer_cityjson": output_record(cityjson_copy),
        }
        for record in outputs.values():
            record["path"] = display_path(
                destination / Path(str(record["path"])).name
            )
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "task_id": config["task_id"],
            "state": "COMPLETE",
            "measurement_state": "MEASURED",
            "created_at": utc_now(),
            "identity": evidence["identity"],
            "source_readout_complete": evidence["source_readout_complete"],
            "components": components,
            "component_contract": component_contract(config),
            "placeholder_count": 0,
            "inspection": evidence["inspection"],
            "render_quality": render_quality,
            "font": font_record,
            "source_records": source_before,
            "reference_gml": {
                "role": "evaluation_only",
                "records": evidence["reference_records"],
                "opened_after_primary_readout_complete": True,
            },
            "canonical_roofer_cityjson": {
                "required": True,
                "source": source_before["canonical_roofer_cityjson"],
                "bundle_copy": outputs["canonical_roofer_cityjson"],
                "byte_identical_copy": True,
            },
            "citygml_export": evidence["serialization_capability"],
            "implementation": implementation_records(config),
            "outputs": outputs,
            "publication": {
                "measured_job_only": True,
                "all_A_to_I_components_present": True,
                "placeholder_count": 0,
                "job_directory_atomic_publish": True,
                "overwrite_allowed": False,
                "source_inputs_rehashed_after_render": True,
                "source_inputs_unchanged": True,
                "receipt_written_last": True,
            },
            "scientific_verdict": None,
            "interpretation": None,
        }
        write_json_exclusive(staging / config["outputs"]["complete"], receipt)
        require(not destination.exists(), "job destination appeared during staging")
        os.rename(staging, destination)
        return verify_bundle(config, building_id, arm, replicate, output_root)
    except Exception:
        if staging.exists() and is_within(staging, destination.parent):
            shutil.rmtree(staging)
        raise


def inspect_job(
    config: Mapping[str, Any], report: Any, building_id: str, arm: str, replicate: str
) -> dict[str, Any]:
    evidence = resolve_evidence(config, report, building_id, arm, replicate)
    return {
        "schema": "jointbuildgs.fusion_w1_aprime.job_qualitative.check.v3",
        "state": "READY",
        "measurement_state": "MEASURED",
        "identity": evidence["identity"],
        "source_readout_complete": evidence["source_readout_complete"],
        "components": {key: True for key in COMPONENT_KEYS},
        "component_contract": component_contract(config),
        "placeholder_count": 0,
        "inspection": evidence["inspection"],
        "citygml_export": evidence["serialization_capability"],
        "scientific_verdict": None,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=None,
        help="isolated review root for tests; production wrapper leaves this unset",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("one", "check", "verify"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("building_id")
        subparser.add_argument("arm")
        subparser.add_argument("replicate")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        config = load_config(args.config)
        if args.command == "verify":
            payload = verify_bundle(
                config, args.building_id, args.arm, args.replicate, args.output_root
            )
        else:
            report = load_report_module(config)
            if args.command == "check":
                payload = inspect_job(
                    config, report, args.building_id, args.arm, args.replicate
                )
            else:
                payload = publish_job(
                    config,
                    report,
                    args.building_id,
                    args.arm,
                    args.replicate,
                    args.output_root,
                )
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except JobQualitativeError as exc:
        print(f"JOB_QUALITATIVE_ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
