"""Lossless P3 schema adapter with dtype-aware equality verification."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil

import numpy as np



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


def adapt_p3(config_path, kind, output, resume=False):
    isolation = require_isolation()
    cfg = json.loads(Path(config_path).read_text())
    spec = cfg["regions"]["P3"]
    filename = "acquisition.npz" if kind == "acquisition" else "estimated_origins.npz"
    source_root = Path(spec[f"original_{kind}_root"])
    source = source_root / filename
    if sha(source) != spec[f"original_{kind}_sha256"]:
        raise ValueError("Original P3 acquisition/origin payload hash differs")
    if resume:
        if not output.is_dir() or (output / "receipt.json").exists():
            raise ValueError("Resume only an unfinished adapter; never replace a sealed receipt")
    else:
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
    if resume:
        if not destination.is_file():
            raise ValueError("No completed adapter payload to validate")
    else:
        np.savez_compressed(destination, **arrays)
    with np.load(source) as original, np.load(destination) as adapted:
        assert len(original.files) == len(adapted.files)
        for key, entry in mapping.items():
            actual = array_record(adapted[entry["target_key"]])
            assert all(actual[field] == entry[field] for field in actual)
            if original[key].dtype.kind in "fc":
                assert np.array_equal(original[key], adapted[entry["target_key"]], equal_nan=True)
            else:
                assert np.array_equal(original[key], adapted[entry["target_key"]])
            entry["exact_array_equal_including_nan"] = True
    for name in ("receipt.json", "config.json"):
        shutil.copy2(source_root / name, output / f"original_{name}")
    receipt = dict(status="LOSSLESS_REGION_SCHEMA_ADAPTER_COMPLETE", region_id="P3", kind=kind,
        scientific_verdict=None, reference_accessed=False, source_npz=str(source), source_sha256=sha(source),
        original_receipt_sha256=sha(source_root / "receipt.json"), new_npz_sha256=sha(destination),
        operation="Replace lowercase p3 tokens in array keys with region; arrays retain exact dtype/shape/bytes and NaN positions",
        coordinates_reestimated_or_modified=False, fitting_or_registration_executed=False,
        resumed_validation_of_existing_npz=resume,
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
    parser.add_argument("--mode", choices=("acquisition", "trajectory"), required=True)
    parser.add_argument("--region", choices=("P3",), default="P3")
    parser.add_argument("--resume-adapter", action="store_true")
    args = parser.parse_args()
    adapt_p3(args.config, args.mode, args.output, args.resume_adapter)
