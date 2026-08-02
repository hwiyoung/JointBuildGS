"""Run exactly six pinned val3dity CityJSONSeq stdin validations, add-once."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

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
UNIT_RECEIPT_SCHEMA = "jointbuildgs.c1_c2_dev_g2_unit_receipt.v1"
UNIT_RECEIPT_STATUS = "COMPLETED_PINNED_VALIDATION_UNIT"
FINAL_RECEIPT_SCHEMA = "jointbuildgs.c1_c2_dev_g2_receipts.v1"
FINAL_RECEIPT_STATUS = "COMPLETED_PINNED_VALIDATION"

_UNIT_RECEIPT_KEYS = {
    "schema",
    "status",
    "task_id",
    "validator",
    "validator_version",
    "container_image_ref",
    "container_image_id",
    "input_mode",
    "command",
    "unit",
    "sealed_cityjson_read_and_hash_count",
    "validator_invocation_count",
    "reconstruction_invocation_count",
    "roofer_invocation_count",
    "validation_access_count",
    "held_out_access_count",
    "scientific_verdict",
}
_UNIT_KEYS = {
    "operation_unit_id",
    "source",
    "cityjsonseq_feature_ids",
    "process_exit_code",
    "runtime_exit_anomaly",
    "completion_class",
    "stdout",
    "stderr",
    "result",
}
_STREAM_KEYS = {"bytes", "sha256", "text"}


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


def _decode_utf8(data: bytes, label: str) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ClosureError(f"{label} is not UTF-8") from error


def _parse_stdout(data: bytes, expected_feature_ids: Sequence[str]) -> dict[str, Any]:
    try:
        return parse_val3dity_cjseq_stdout(data, expected_feature_ids)
    except UnicodeDecodeError as error:
        raise ClosureError("val3dity stdin output is not UTF-8") from error


def _completion_metadata(process_exit_code: Any, result: Mapping[str, Any]) -> tuple[bool, str]:
    """Classify only completed validator outcomes after stdout has been parsed."""

    unit_valid = result.get("unit_valid")
    if unit_valid is not True and unit_valid is not False:
        raise ClosureError("val3dity parsed aggregate is not boolean")
    if isinstance(process_exit_code, bool) or not isinstance(process_exit_code, int):
        raise ClosureError("val3dity process exit code is malformed")
    if process_exit_code == 0:
        completion_class = (
            "VALIDATION_COMPLETED_EXIT_0_VALID"
            if unit_valid
            else "VALIDATION_COMPLETED_EXIT_0_INVALID_GEOMETRY"
        )
        return False, completion_class
    if process_exit_code == 1 and unit_valid is False:
        return True, "VALIDATION_COMPLETED_EXIT_1_INVALID_GEOMETRY"
    if process_exit_code == 1:
        raise ClosureError("val3dity exit 1 is unexplained by invalid geometry")
    raise ClosureError(f"val3dity process exit is not an accepted validation completion: {process_exit_code}")


def _path_lexists(path: Path) -> bool:
    return os.path.lexists(os.fspath(path))


def _publish_add_once(path: Path, payload: bytes) -> None:
    """Atomically publish a regular file without replacing an existing name."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent,
            prefix=f".{path.name}.pending.",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError as error:
            raise ClosureError(f"add-once output already exists: {path}") from error
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def _unit_receipt_name(index: int, unit_id: str) -> str:
    identity = sha256_bytes(unit_id.encode("utf-8"))[:16]
    return f"{index:02d}_{identity}.json"


def _prepare_progress_directory(progress_dir: Path, expected_names: set[str]) -> None:
    if _path_lexists(progress_dir):
        if progress_dir.is_symlink() or not progress_dir.is_dir():
            raise ClosureError("G2 progress path is not a real directory")
    else:
        progress_dir.mkdir(parents=True, exist_ok=False)
    for entry in progress_dir.iterdir():
        if entry.name not in expected_names:
            raise ClosureError(f"unexpected G2 progress entry: {entry.name}")
        if entry.is_symlink() or not entry.is_file():
            raise ClosureError(f"G2 progress entry is not a regular file: {entry.name}")


def _stream_record(data: bytes, label: str) -> dict[str, Any]:
    return {
        "bytes": len(data),
        "sha256": sha256_bytes(data),
        "text": _decode_utf8(data, label),
    }


def _build_unit(
    unit_id: str,
    record: Mapping[str, Any],
    payload: bytes,
    process: subprocess.CompletedProcess[bytes],
) -> dict[str, Any]:
    expected_ids = cityjsonseq_feature_ids(payload)
    # Parse the complete stdout first.  Exit status is only runtime telemetry
    # after the exact metadata/feature-id contract has been established.
    result = _parse_stdout(process.stdout, expected_ids)
    anomaly, completion_class = _completion_metadata(process.returncode, result)
    return {
        "operation_unit_id": unit_id,
        "source": {key: record[key] for key in ("path", "bytes", "sha256")},
        "cityjsonseq_feature_ids": expected_ids,
        "process_exit_code": process.returncode,
        "runtime_exit_anomaly": anomaly,
        "completion_class": completion_class,
        "stdout": _stream_record(process.stdout, "val3dity stdout"),
        "stderr": _stream_record(process.stderr, "val3dity stderr"),
        "result": result,
    }


def _unit_receipt(config: Mapping[str, Any], unit: Mapping[str, Any]) -> dict[str, Any]:
    g2 = config["gates"]["G2"]
    return {
        "schema": UNIT_RECEIPT_SCHEMA,
        "status": UNIT_RECEIPT_STATUS,
        "task_id": config["task_id"],
        "validator": g2["validator"],
        "validator_version": g2["version"],
        "container_image_ref": g2["container_image_ref"],
        "container_image_id": g2["container_image_id"],
        "input_mode": g2["input_mode"],
        "command": g2["command"],
        "unit": dict(unit),
        "sealed_cityjson_read_and_hash_count": 1,
        "validator_invocation_count": 1,
        "reconstruction_invocation_count": 0,
        "roofer_invocation_count": 0,
        "validation_access_count": 0,
        "held_out_access_count": 0,
        "scientific_verdict": None,
    }


def _verify_stream(value: Any, label: str) -> bytes:
    if not isinstance(value, Mapping) or set(value) != _STREAM_KEYS:
        raise ClosureError(f"resumed {label} record is malformed")
    text = value.get("text")
    if not isinstance(text, str):
        raise ClosureError(f"resumed {label} text is malformed")
    data = text.encode("utf-8")
    if value.get("bytes") != len(data) or value.get("sha256") != sha256_bytes(data):
        raise ClosureError(f"resumed {label} byte identity differs")
    return data


def _verify_unit_receipt(
    path: Path,
    config: Mapping[str, Any],
    expected_unit_id: str,
    expected_record: Mapping[str, Any],
) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ClosureError("G2 unit progress receipt is missing or non-regular")
    raw = path.read_bytes()
    try:
        data = json.loads(_decode_utf8(raw, "G2 unit progress receipt"))
    except json.JSONDecodeError as error:
        raise ClosureError("G2 unit progress receipt is malformed JSON") from error
    if not isinstance(data, dict) or raw != canonical_json_bytes(data):
        raise ClosureError("G2 unit progress receipt is not canonical JSON")
    g2 = config["gates"]["G2"]
    expected_header = {
        "schema": UNIT_RECEIPT_SCHEMA,
        "status": UNIT_RECEIPT_STATUS,
        "task_id": config["task_id"],
        "validator": g2["validator"],
        "validator_version": g2["version"],
        "container_image_ref": g2["container_image_ref"],
        "container_image_id": g2["container_image_id"],
        "input_mode": g2["input_mode"],
        "command": g2["command"],
        "sealed_cityjson_read_and_hash_count": 1,
        "validator_invocation_count": 1,
        "reconstruction_invocation_count": 0,
        "roofer_invocation_count": 0,
        "validation_access_count": 0,
        "held_out_access_count": 0,
        "scientific_verdict": None,
    }
    if set(data) != _UNIT_RECEIPT_KEYS or any(data.get(key) != value for key, value in expected_header.items()):
        raise ClosureError("G2 unit progress receipt authority differs")
    unit = data.get("unit")
    if not isinstance(unit, dict) or set(unit) != _UNIT_KEYS:
        raise ClosureError("G2 resumed unit record is malformed")
    expected_source = {key: expected_record[key] for key in ("path", "bytes", "sha256")}
    if unit.get("operation_unit_id") != expected_unit_id or unit.get("source") != expected_source:
        raise ClosureError("G2 resumed unit source identity differs")
    expected_ids = unit.get("cityjsonseq_feature_ids")
    if (
        not isinstance(expected_ids, list)
        or not expected_ids
        or any(not isinstance(value, str) or not value for value in expected_ids)
        or len(expected_ids) != len(set(expected_ids))
    ):
        raise ClosureError("G2 resumed CityJSONSeq feature identities are malformed")
    stdout = _verify_stream(unit.get("stdout"), "stdout")
    _verify_stream(unit.get("stderr"), "stderr")
    result = _parse_stdout(stdout, expected_ids)
    if unit.get("result") != result:
        raise ClosureError("G2 resumed parsed result differs from stdout")
    anomaly, completion_class = _completion_metadata(unit.get("process_exit_code"), result)
    if unit.get("runtime_exit_anomaly") is not anomaly or unit.get("completion_class") != completion_class:
        raise ClosureError("G2 resumed runtime completion classification differs")
    return unit


def run_g2(
    source_root: Path,
    output_path: Path,
    config_path: Path = DEFAULT_CONFIG,
    process_runner: ProcessRunner = subprocess.run,
    progress_dir: Path | None = None,
) -> dict[str, Any]:
    config = load_config(config_path)
    g2 = config["gates"]["G2"]
    if _path_lexists(output_path):
        raise ClosureError("G2 receipt output is add-once and already exists")
    inspect = process_runner(
        ["docker", "image", "inspect", "--format", "{{.Id}}", g2["container_image_ref"]],
        capture_output=True,
        check=False,
    )
    if inspect.returncode != 0 or _decode_utf8(inspect.stdout, "docker image identity").strip() != g2["container_image_id"]:
        raise ClosureError("local val3dity image identity differs from the pinned image")
    manifest = json.loads(_read_bound_file(config["inputs"]["source_manifest"]))
    records = _c2_cityjson_records(manifest)
    ordered_records = sorted(records.items())
    progress_dir = progress_dir or output_path.with_name(f"{output_path.name}.progress")
    progress_paths = {
        unit_id: progress_dir / _unit_receipt_name(index, unit_id)
        for index, (unit_id, _) in enumerate(ordered_records, start=1)
    }
    _prepare_progress_directory(progress_dir, {path.name for path in progress_paths.values()})
    verified_units: dict[str, dict[str, Any]] = {}
    for unit_id, record in ordered_records:
        progress_path = progress_paths[unit_id]
        if _path_lexists(progress_path):
            verified_units[unit_id] = _verify_unit_receipt(
                progress_path, config, unit_id, record
            )
    units: list[dict[str, Any]] = []
    reused_count = len(verified_units)
    new_count = 0
    docker_command = [
        "docker", "run", "--rm", "-i", g2["container_image_ref"], *g2["command"]
    ]
    for unit_id, record in ordered_records:
        progress_path = progress_paths[unit_id]
        if unit_id in verified_units:
            unit = verified_units[unit_id]
        else:
            payload = _read_source_record(source_root, record)
            process = process_runner(docker_command, input=payload, capture_output=True, check=False)
            unit = _build_unit(unit_id, record, payload, process)
            _publish_add_once(progress_path, canonical_json_bytes(_unit_receipt(config, unit)))
            new_count += 1
        units.append(unit)
    receipt = {
        "schema": FINAL_RECEIPT_SCHEMA,
        "status": FINAL_RECEIPT_STATUS,
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
        "resumption": {
            "reused_exact_unit_receipts": reused_count,
            "new_source_reads_and_hashes": new_count,
            "new_validator_invocations": new_count,
        },
        "reconstruction_invocation_count": 0,
        "roofer_invocation_count": 0,
        "validation_access_count": 0,
        "held_out_access_count": 0,
        "scientific_verdict": None,
    }
    payload = canonical_json_bytes(receipt)
    _publish_add_once(output_path, payload)
    return {"path": str(output_path), "bytes": len(payload), "sha256": sha256_bytes(payload), **receipt}


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--progress-dir",
        type=Path,
        help="Add-once per-unit progress directory (default: <output>.progress)",
    )
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    print(
        json.dumps(
            run_g2(args.source_root, args.output, args.config, progress_dir=args.progress_dir),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
