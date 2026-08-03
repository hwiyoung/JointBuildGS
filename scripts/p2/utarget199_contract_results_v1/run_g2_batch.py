#!/usr/bin/env python3
"""Run pinned val3dity once per unique Roofer output in one tools container."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess


COMMAND = [
    "val3dity",
    "--overlap_tol", "-1.0",
    "--planarity_d2p_tol", "0.01",
    "--planarity_n_tol", "20.0",
    "--snap_tol", "0.001",
    "stdin",
]


def feature_ids(data: bytes) -> list[str]:
    rows = [json.loads(line) for line in data.decode("utf-8").splitlines() if line.strip()]
    if not rows or rows[0].get("type") != "CityJSON":
        raise RuntimeError("not CityJSONSeq")
    ids = [row.get("id") for row in rows[1:] if row.get("type") == "CityJSONFeature"]
    if not ids or any(not isinstance(value, str) or not value for value in ids):
        raise RuntimeError("CityJSONSeq feature IDs invalid")
    return ids


def parse_stdout(text: str, expected: list[str]) -> tuple[bool, list[dict[str, object]]]:
    lines = text.splitlines()
    names = ["1st-line", *expected]
    if len(lines) != len(names):
        raise RuntimeError("val3dity stdout line count differs")
    decoder = json.JSONDecoder()
    parsed: list[dict[str, object]] = []
    for line, expected_name in zip(lines, names):
        name, offset = decoder.raw_decode(line)
        codes, consumed = decoder.raw_decode(line[offset:].lstrip())
        if line[offset:].lstrip()[consumed:].strip() or name != expected_name:
            raise RuntimeError("val3dity stdout identity differs")
        if not isinstance(codes, list) or any(not isinstance(code, int) for code in codes):
            raise RuntimeError("val3dity error list invalid")
        parsed.append({"feature_id": name, "error_codes": codes, "valid": not codes})
    return all(bool(row["valid"]) for row in parsed[1:]), parsed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-root", type=Path, required=True)
    parser.add_argument("--units", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    units = [json.loads(line) for line in args.units.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows: list[dict[str, object]] = []
    for unit in units:
        output_dir = args.task_root / unit["output_directory"]
        city = sorted(path for path in output_dir.glob("*") if path.is_file() and path.suffix in (".json", ".jsonl")) if output_dir.is_dir() else []
        row: dict[str, object] = {
            "operation_unit_id": unit["operation_unit_id"],
            "validator": "val3dity",
            "version": "2.6.0",
            "command": COMMAND,
            "completed": False,
            "unit_valid": False,
            "scientific_verdict": None,
        }
        if len(city) != 1:
            row["missing_reason"] = "EXACT_ONE_CITYJSONSEQ_OUTPUT_NOT_FOUND"
            rows.append(row)
            continue
        data = city[0].read_bytes()
        row["input"] = {
            "path": city[0].relative_to(args.task_root).as_posix(),
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
        try:
            ids = feature_ids(data)
            process = subprocess.run(COMMAND, input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            stdout = process.stdout.decode("utf-8")
            valid, parsed = parse_stdout(stdout, ids)
            row.update({
                "completed": True,
                "exit_code": process.returncode,
                "unit_valid": valid,
                "features": parsed[1:],
                "metadata": parsed[0],
                "stderr": process.stderr.decode("utf-8", errors="replace")[-4000:],
            })
        except Exception as error:
            row.update({"missing_reason": f"VAL3DITY_BATCH_PARSE_FAILURE:{type(error).__name__}:{error}"})
        rows.append(row)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        raise RuntimeError("G2 batch output is add-once")
    args.output.write_bytes(b"".join((json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8") for row in rows))
    print(json.dumps({"units": len(rows), "completed": sum(bool(row["completed"]) for row in rows), "valid": sum(bool(row["unit_valid"]) for row in rows)}, sort_keys=True))


if __name__ == "__main__":
    main()
