"""Prepare all three regions with one frozen v5 input-selection protocol."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil

import numpy as np

from scripts.phd.wu_vallet_regions_v4.prepare_inputs import run as prepare_region


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def write(path, value):
    with Path(path).open("x") as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write("\n")


def array_record(array):
    return dict(dtype=str(array.dtype), shape=list(array.shape), bytes=array.nbytes,
                sha256=hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest())


def require_isolation():
    if not Path("/.dockerenv").exists():
        raise RuntimeError("Docker execution required")
    prohibited = ["/artifacts/JointBuildGS/phase-payloads/p0-audit/data/raw/tum2twin",
        "/artifacts/JointBuildGS/phase-payloads/phd/wu_vallet_p3_v1/PHD-WU-VALLET-P3-EVALUATION-v1-r2",
        "/artifacts/JointBuildGS/phase-payloads/phd/wu_vallet_regions_v4/PHD-WU-VALLET-REGIONS-EVALUATION-v4",
        "/artifacts/JointBuildGS/phase-payloads/phd/wu_vallet_regions_v4/PHD-WU-VALLET-VISIBLE-EVALUATION-v4"]
    if any(Path(p).exists() for p in prohibited):
        raise RuntimeError("Reference storage must be absent from candidate container mounts")
    return {p: False for p in prohibited}


def prepare(config_path, region_id, output):
    isolation = require_isolation()
    cfg = json.loads(Path(config_path).read_text())
    spec = cfg["regions"][region_id]
    camera = json.loads(Path(spec["camera_config"]).read_text())
    frozen_path = Path(cfg["artifact_root"]) / camera["output_relative_root"] / "evidence_views.json"
    frozen = json.loads(frozen_path.read_text())["views"]
    assert len(frozen) == spec["frozen_view_count"]
    assert cfg["view_selection"]["mode"] == "max_native_xy_cells"
    assert cfg["view_selection"]["decision_count"] == "ALL_FROZEN_REGIONAL_VIEWS"
    for key in ("x", "y"):
        expected = [spec["domain"][key][0] - cfg["context_rule"]["xy_padding_m"],
                    spec["domain"][key][1] + cfg["context_rule"]["xy_padding_m"]]
        assert spec["context_domain"][key] == expected
    assert spec["context_domain"]["z"] == cfg["context_rule"]["z"]
    resolved = copy.deepcopy(cfg)
    resolved["view_selection"]["decision_count"] = len(frozen)
    resolved_path = output.parent / "resolved_config.json"
    write(resolved_path, resolved)
    prepare_region(resolved_path, region_id, output)
    native_path = output / "common/native.npz"
    source_path = Path(spec["original_native_npz"])
    assert sha(source_path) == spec["original_native_sha256"]
    equal = {}
    with np.load(native_path) as actual, np.load(source_path) as previous:
        for key in actual.files:
            if key not in previous.files:
                raise ValueError(f"Original native array absent: {key}")
            a, b = actual[key], previous[key]
            assert a.dtype == b.dtype and a.shape == b.shape
            assert np.ascontiguousarray(a).tobytes() == np.ascontiguousarray(b).tobytes()
            equal[key] = dict(exact_original_array_bytes_equal=True, **array_record(a))
        source_only_fields = sorted(set(previous.files) - set(actual.files))
    coverage = json.loads((output / "coverage_audit.json").read_text())["views"]
    assert len(coverage) == len(frozen)
    eligible = [r for r in coverage if r["eligible"]]
    selected = min(eligible, key=lambda r: (-r["native_xy_occupied_cells"], r["hash_rank"]))
    master = json.loads((output / "common/selected_master.json").read_text())
    assert master["image_id"] == selected["image_id"]
    shared = {key: cfg[key] for key in ["view_selection", "image_mesh", "als_mesh", "context_rule",
                                       "distance_tolerance_m", "area_sensitivity_m2", "primary_area_m2",
                                       "changed_only_sensitivity_area_m2", "working_crs", "frame"]}
    shared_bytes = json.dumps(shared, sort_keys=True, separators=(",", ":")).encode()
    receipt = dict(status="MATCHED_INPUT_PROTOCOL_VERIFIED", region_id=region_id,
        scientific_verdict=None, reference_accessed=False, updated_candidate_executed=False,
        common_config_sha256=sha(config_path), shared_policy=shared,
        shared_policy_sha256=hashlib.sha256(shared_bytes).hexdigest(),
        input_receipt_sha256=sha(output / "receipt.json"), resolved_config_sha256=sha(resolved_path),
        selected_image_id=master["image_id"], selected_coverage=selected,
        audited_frozen_view_count=len(coverage), original_native_sha256=sha(source_path),
        new_native_sha256=sha(native_path), native_array_equality=equal,
        original_native_extra_fields_not_required_by_any_region=source_only_fields,
        reference_paths_absent=isolation,
        source_hashes={p: sha(p) for p in [__file__, "scripts/phd/wu_vallet_regions_v4/prepare_inputs.py",
                        "src/phd/wu_vallet_p3_v1/sensor_mesh.py", "scripts/phd/wu_vallet_p3_v1/preflight.py"]},
        source_snapshot_manifest=os.environ.get("JBGS_SOURCE_SNAPSHOT_MANIFEST"))
    write(output / "protocol_receipt.json", receipt)
    print(json.dumps({"phase": "matched_input_verified", "region": region_id,
                      "image_id": master["image_id"], "views": len(coverage),
                      "cells": selected["native_xy_occupied_cells"],
                      "shared_policy_sha256": receipt["shared_policy_sha256"]}), flush=True)


def adapt_p3(config_path, kind, output):
    isolation = require_isolation()
    cfg = json.loads(Path(config_path).read_text())
    spec = cfg["regions"]["P3"]
    filename = "acquisition.npz" if kind == "acquisition" else "estimated_origins.npz"
    source_root = Path(spec[f"original_{kind}_root"])
    source = source_root / filename
    if sha(source) != spec[f"original_{kind}_sha256"]:
        raise ValueError("Original P3 acquisition/origin payload hash differs")
    output.mkdir(parents=True, exist_ok=False)
    mapping, arrays = {}, {}
    with np.load(source) as original:
        for key in original.files:
            target = key.replace("p3", "region")
            if target in arrays:
                raise ValueError("P3 to region schema key collision")
            array = original[key]
            if array.dtype.hasobject:
                raise ValueError("Object arrays not permitted")
            arrays[target] = array
            mapping[key] = dict(target_key=target, **array_record(array))
    destination = output / filename
    np.savez_compressed(destination, **arrays)
    with np.load(source) as original, np.load(destination) as adapted:
        assert len(original.files) == len(adapted.files)
        for key, entry in mapping.items():
            actual = array_record(adapted[entry["target_key"]])
            assert all(actual[field] == entry[field] for field in actual)
            assert np.array_equal(original[key], adapted[entry["target_key"]], equal_nan=True)
            entry["exact_array_equal_including_nan"] = True
    for name in ("receipt.json", "config.json"):
        shutil.copy2(source_root / name, output / f"original_{name}")
    receipt = dict(status="LOSSLESS_REGION_SCHEMA_ADAPTER_COMPLETE", region_id="P3", kind=kind,
        scientific_verdict=None, reference_accessed=False, source_npz=str(source), source_sha256=sha(source),
        original_receipt_sha256=sha(source_root / "receipt.json"), new_npz_sha256=sha(destination),
        operation="Replace lowercase p3 tokens in array keys with region; arrays retain exact dtype/shape/bytes and NaN positions",
        coordinates_reestimated_or_modified=False, fitting_or_registration_executed=False,
        array_mapping=mapping, array_count=len(mapping), reference_paths_absent=isolation,
        source_snapshot_manifest=os.environ.get("JBGS_SOURCE_SNAPSHOT_MANIFEST"),
        outputs={p.name: sha(p) for p in output.iterdir() if p.is_file()})
    write(output / "receipt.json", receipt)
    print(json.dumps({"phase": "lossless_adapter_complete", "kind": kind, "arrays": len(mapping),
                      "source_sha256": receipt["source_sha256"], "new_sha256": receipt["new_npz_sha256"]}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=("input", "acquisition", "trajectory"), required=True)
    parser.add_argument("--region", choices=("P1", "P2", "P3"), default="P3")
    args = parser.parse_args()
    if args.mode == "input":
        prepare(args.config, args.region, args.output)
    else:
        adapt_p3(args.config, args.mode, args.output)
