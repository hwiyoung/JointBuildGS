"""Run exactly six pinned val3dity CityJSONSeq stdin validations, add-once."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable

from .evaluator import (
    DEFAULT_CONFIG,
    ClosureError,
    _read_bound_file,
    _read_source_record,
    canonical_json_bytes,
    cityjsonseq_feature_ids,
    load_config,
    parse_val3dity_cjseq_stdout,
    sha256_bytes,
)


ProcessRunner = Callable[..., subprocess.CompletedProcess[bytes]]


def _c2_cityjson_records(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for record in manifest["records"]:
        path = str(record["path"])
        parts = path.split("/")
        if len(parts) >= 6 and parts[0:2] == ["operations", "C2_MVS"] and path.endswith(".jsonl"):
            unit_id = f"C2_MVS|{parts[2]}"
            if unit_id in output:
                raise ClosureError("multiple sealed CityJSONSeq records for one C2 unit")
            output[unit_id] = record
    if len(output) != 6:
        raise ClosureError("expected exactly six sealed C2 CityJSONSeq units")
    return output


def run_g2(
    source_root: Path,
    output_path: Path,
    config_path: Path = DEFAULT_CONFIG,
    process_runner: ProcessRunner = subprocess.run,
) -> dict[str, Any]:
    config = load_config(config_path)
    g2 = config["gates"]["G2"]
    if output_path.exists():
        raise ClosureError("G2 receipt output is add-once and already exists")
    inspect = process_runner(
        ["docker", "image", "inspect", "--format", "{{.Id}}", g2["container_image_ref"]],
        capture_output=True,
        check=False,
    )
    if inspect.returncode != 0 or inspect.stdout.decode("utf-8").strip() != g2["container_image_id"]:
        raise ClosureError("local val3dity image identity differs from the pinned image")
    manifest = json.loads(_read_bound_file(config["inputs"]["source_manifest"]))
    records = _c2_cityjson_records(manifest)
    units: list[dict[str, Any]] = []
    docker_command = [
        "docker", "run", "--rm", "-i", g2["container_image_ref"], *g2["command"]
    ]
    for unit_id, record in sorted(records.items()):
        payload = _read_source_record(source_root, record)
        expected_ids = cityjsonseq_feature_ids(payload)
        process = process_runner(docker_command, input=payload, capture_output=True, check=False)
        if process.returncode != 0:
            raise ClosureError(f"val3dity process failed for {unit_id}: {process.returncode}")
        result = parse_val3dity_cjseq_stdout(process.stdout, expected_ids)
        units.append(
            {
                "operation_unit_id": unit_id,
                "source": {key: record[key] for key in ("path", "bytes", "sha256")},
                "process_exit_code": process.returncode,
                "stdout": {
                    "bytes": len(process.stdout),
                    "sha256": sha256_bytes(process.stdout),
                    "lines": process.stdout.decode("utf-8").splitlines(),
                },
                "stderr": {
                    "bytes": len(process.stderr),
                    "sha256": sha256_bytes(process.stderr),
                    "text": process.stderr.decode("utf-8"),
                },
                "result": result,
            }
        )
    receipt = {
        "schema": "jointbuildgs.c1_c2_dev_g2_receipts.v1",
        "status": "COMPLETED_PINNED_VALIDATION",
        "task_id": config["task_id"],
        "validator": g2["validator"],
        "validator_version": g2["version"],
        "container_image_ref": g2["container_image_ref"],
        "container_image_id": g2["container_image_id"],
        "input_mode": g2["input_mode"],
        "command": g2["command"],
        "unit_count": len(units),
        "units": units,
        "sealed_cityjson_read_and_hash_count": len(units),
        "validator_invocation_count": len(units),
        "reconstruction_invocation_count": 0,
        "roofer_invocation_count": 0,
        "validation_access_count": 0,
        "held_out_access_count": 0,
        "scientific_verdict": None,
    }
    payload = canonical_json_bytes(receipt)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=output_path.parent, prefix=f".{output_path.name}.", delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, output_path)
    return {"path": str(output_path), "bytes": len(payload), "sha256": sha256_bytes(payload), **receipt}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    print(json.dumps(run_g2(args.source_root, args.output, args.config), sort_keys=True))


if __name__ == "__main__":
    main()
