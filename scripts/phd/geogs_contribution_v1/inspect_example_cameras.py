#!/usr/bin/env python3
"""Inspect only COLMAP camera headers in the already downloaded GeoGS archive.

The large images.txt observation lines are streamed past without interpreting or
retaining their point observations. No archive extraction or model execution.
"""

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import platform
import time
import zipfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--image-id", required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    start = time.monotonic()
    source_receipt = json.loads((args.source / "receipt.json").read_text())
    source_manifest = json.loads((args.source / "input_manifest.json").read_text())
    receipt = {
        "task_id": "PHD-GEOGS-CONTRIBUTION-v1-EXAMPLE-CAMERA-INSPECTION-r2",
        "started_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "container_image_id": args.image_id,
        "python": platform.python_version(),
        "upstream_commit": source_receipt["upstream_commit"],
        "source_download_receipt_sha256": hashlib.sha256((args.source / "receipt.json").read_bytes()).hexdigest(),
        "source_download_script_sha256": source_receipt["script_sha256"],
        "source_archive_sha256_recorded_at_download": source_receipt["download_sha256"],
        "source_archive_rehashed": False,
        "source_receipt_modified": False,
        "archive_extracted": False,
        "training_or_inference_executed": False,
        "scientific_verdict": None,
    }
    code = 0
    try:
        member = "example_scene/sparse_lod/0/images.txt"
        cameras = []
        digest = hashlib.sha256()
        consumed = 0
        with zipfile.ZipFile(args.source / "example_scene.zip") as archive:
            info = archive.getinfo(member)
            if info.file_size > 32_000_000:
                raise ValueError("Camera text exceeds the 32 MB metadata-stream bound")
            with archive.open(info) as stream:
                while True:
                    if time.monotonic() - start > 60:
                        raise TimeoutError("Camera metadata inspection exceeds 60 seconds")
                    line = stream.readline(32_000_001 - consumed)
                    if not line:
                        break
                    digest.update(line)
                    consumed += len(line)
                    if consumed > 32_000_000:
                        raise ValueError("Metadata stream exceeds the authorized bound")
                    if line.startswith(b"#") or not line.strip():
                        continue
                    if len(line) > 65536:
                        raise ValueError("Camera header exceeds the header-only parsing limit")
                    fields = line.decode("utf-8").strip().split()
                    if len(fields) < 10:
                        raise ValueError("Invalid COLMAP image header")
                    cameras.append({"id": int(fields[0]), "qvec": list(map(float, fields[1:5])),
                                    "tvec": list(map(float, fields[5:8])),
                                    "camera_id": int(fields[8]), "name": " ".join(fields[9:])})
                    # Consume the COLMAP point-observation row without parsing it.
                    observations = stream.readline(32_000_001 - consumed)
                    digest.update(observations)
                    consumed += len(observations)
                    if consumed > 32_000_000:
                        raise ValueError("Metadata stream exceeds the authorized bound")
            if consumed != info.file_size:
                raise ValueError("Camera metadata stream length differs from ZIP directory")
        reference = next(record for record in source_manifest["camera_records"]
                         if record["path"] == "example_scene/sparse/0/images.bin")
        original = {record["name"]: record for record in reference["images"]}
        lod = {record["name"]: record for record in cameras}
        shared = sorted(set(original) & set(lod))
        max_q = max((abs(original[name]["qvec"][i] - lod[name]["qvec"][i]) for name in shared for i in range(4)), default=None)
        max_t = max((abs(original[name]["tvec"][i] - lod[name]["tvec"][i]) for name in shared for i in range(3)), default=None)
        ordered = sorted(cameras, key=lambda record: record["name"].split("/")[-1].split(".")[0])
        train = [record["name"] for i, record in enumerate(ordered) if i % 8 != 0]
        test = [record["name"] for i, record in enumerate(ordered) if i % 8 == 0]
        receipt.update({
            "status": "CAMERA_HEADER_INSPECTION_COMPLETE",
            "inspected_member": member, "streamed_metadata_bytes": consumed,
            "member_sha256": digest.hexdigest(), "camera_headers": cameras,
            "point_observation_rows_parsed_or_retained": False,
            "sparse_lod_view_count": len(cameras),
            "sparse_view_count": len(original),
            "same_image_name_set": set(original) == set(lod),
            "duplicate_lod_image_names": len(cameras) != len(lod),
            "all_shared_image_ids_equal": all(original[name]["id"] == lod[name]["id"] for name in shared),
            "all_shared_camera_ids_equal": all(original[name]["camera_id"] == lod[name]["camera_id"] for name in shared),
            "max_abs_qvec_difference": max_q, "max_abs_tvec_difference": max_t,
            "pose_values_exactly_equal": set(original) == set(lod) and max_q == 0.0 and max_t == 0.0,
            "default_split": {
                "status": "DERIVED_FROM_UPSTREAM_EVAL_TRUE_LLFFHOLD_8_NOT_AUTHOR_EXPERIMENT_RECEIPT",
                "train_count": len(train), "test_count": len(test), "train": train, "test": test},
            "parameter_provenance_files": source_manifest["parameter_provenance_files"],
            "author_actual_training_run_parameters_verified": False,
            "da3_inference_input_lineage_verified": False,
        })
    except Exception as error:
        receipt["status"] = "CAMERA_HEADER_INSPECTION_FAILED"
        receipt["error"] = f"{type(error).__name__}: {error}"
        code = 1
    receipt["elapsed_seconds"] = time.monotonic() - start
    with (args.output / "receipt.json").open("x", encoding="utf-8") as handle:
        json.dump(receipt, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({key: receipt.get(key) for key in (
        "status", "sparse_lod_view_count", "same_image_name_set", "pose_values_exactly_equal",
        "max_abs_qvec_difference", "max_abs_tvec_difference", "default_split", "error")}, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
