#!/usr/bin/env python3
"""Resumable per-building Roofer isolation for degradation-curve recovery.

This module changes orchestration scope only: every isolated invocation uses
the same stage LAZ, footprint source, pinned Roofer image, AOI box, and default
reconstruction parameters as the original batch invocation.  It validates and
copies one CityJSONSeq payload per canonical building into the ordinary stage
output directory so the unchanged scorer can consume the recovered stage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Mapping

import degradation_curve_v3 as dc


RECOVERY_ROOT = dc.RUNTIME / "recovery"
INCIDENT = dc.RUN_DIR / "degradation_curve_recovery_incident.json"
PLAN_FIELDS = [
    "order",
    "stage_id",
    "building_id",
    "source_point_count",
    "degraded_point_count",
    "stage_input_path",
    "stage_input_sha256",
    "ogr_filter",
    "accepted_output_path",
    "part_meta_path",
    "learning_runs_started",
    "new_inference_runs",
]
MEASUREMENT_FIELDS = [
    "order",
    "stage_id",
    "building_id",
    "status",
    "attempt",
    "timeout_seconds",
    "wall_seconds",
    "ogr_filter",
    "source_output_path",
    "source_output_sha256",
    "accepted_output_path",
    "accepted_output_sha256",
    "log_path",
    "roofer_image",
    "roofer_parameters",
    "execution_mode",
    "learning_runs_started",
    "new_inference_runs",
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def recovery_dir(stage_id: str) -> Path:
    if stage_id not in dc.STAGE_BY_ID or stage_id == "baseline":
        raise KeyError(stage_id)
    return RECOVERY_ROOT / stage_id


def plan_path(stage_id: str) -> Path:
    return recovery_dir(stage_id) / "plan.csv"


def part_meta_path(stage_id: str, building_id: str) -> Path:
    return recovery_dir(stage_id) / "parts" / f"{building_id}.json"


def accepted_output_path(stage_id: str, building_id: str) -> Path:
    return dc.ROOFER_DIR / stage_id / f"{building_id}.city.jsonl"


def relative_or_absolute(path: Path) -> str:
    resolved = path.resolve()
    return dc.rel(resolved) if resolved.is_relative_to(dc.REPO) else str(resolved)


def feature_ids(path: Path) -> list[str]:
    identifiers: list[str] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"invalid CityJSONSeq JSON path={path} line={line_number}"
                ) from exc
            if payload.get("type") == "CityJSONFeature":
                identifier = str(payload.get("id", ""))
                if not identifier:
                    raise RuntimeError(
                        f"CityJSONFeature without id path={path} line={line_number}"
                    )
                identifiers.append(identifier)
    if not identifiers:
        raise RuntimeError(f"CityJSONFeature missing path={path}")
    return identifiers


def build_plan(stage_id: str) -> dict[str, Any]:
    stage_dir = recovery_dir(stage_id)
    stage_dir.mkdir(parents=True, exist_ok=True)
    population, _ = dc.load_population()
    point_path = dc.POINT_DIR / f"{stage_id}.csv"
    input_path = dc.INPUT_DIR / stage_id / "aoi.laz"
    input_meta_path = dc.STAGE_META_DIR / f"{stage_id}.input.json"
    for required in (point_path, input_path, input_meta_path):
        if not required.is_file():
            raise FileNotFoundError(required)
    point_rows = dc.read_csv(point_path)
    points = {row["building_id"]: row for row in point_rows}
    if len(point_rows) != dc.EXPECTED_POPULATION or set(points) != set(population):
        raise RuntimeError(f"recovery point population drift stage={stage_id}")
    input_meta = json.loads(input_meta_path.read_text(encoding="utf-8"))
    input_sha = dc.sha256_file(input_path)
    if input_meta["input_sha256"] != input_sha:
        raise RuntimeError(f"recovery stage input hash drift stage={stage_id}")
    rows = []
    for order, building_id in enumerate(population, start=1):
        rows.append(
            {
                "order": order,
                "stage_id": stage_id,
                "building_id": building_id,
                "source_point_count": points[building_id]["source_point_count"],
                "degraded_point_count": points[building_id]["degraded_point_count"],
                "stage_input_path": dc.rel(input_path),
                "stage_input_sha256": input_sha,
                "ogr_filter": f"building_id = '{building_id}'",
                "accepted_output_path": dc.rel(
                    accepted_output_path(stage_id, building_id)
                ),
                "part_meta_path": dc.rel(part_meta_path(stage_id, building_id)),
                "learning_runs_started": 0,
                "new_inference_runs": 0,
            }
        )
    dc.atomic_csv(plan_path(stage_id), rows, PLAN_FIELDS)
    payload = {
        "schema": "jointbuildgs.degradation_curve.recovery_plan.v3",
        "created_utc": now(),
        "stage": dc.stage_payload(dc.STAGE_BY_ID[stage_id]),
        "population_count": len(population),
        "population_sha256": hashlib.sha256(
            ("\n".join(population) + "\n").encode("utf-8")
        ).hexdigest(),
        "stage_input_path": dc.rel(input_path),
        "stage_input_sha256": input_sha,
        "plan_csv": dc.rel(plan_path(stage_id)),
        "plan_csv_sha256": dc.sha256_file(plan_path(stage_id)),
        "execution_mode": "isolated_per_building_same_parameters",
        "scope_change_only": True,
        "roofer_image": dc.ROOFER_IMAGE,
        "roofer_parameters": dc.ROOFER_PARAMETERS,
        "reconstruction_parameter_change_count": 0,
        "recovery_script": dc.rel(Path(__file__)),
        "recovery_script_sha256": dc.sha256_file(Path(__file__)),
        "incident_record": dc.rel(INCIDENT) if INCIDENT.is_file() else None,
        "incident_record_sha256": (
            dc.sha256_file(INCIDENT) if INCIDENT.is_file() else None
        ),
        "learning_runs_started": 0,
        "new_inference_runs": 0,
    }
    manifest = stage_dir / "plan_manifest.json"
    dc.atomic_text(manifest, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return payload


def load_part_meta(stage_id: str, building_id: str) -> dict[str, Any]:
    path = part_meta_path(stage_id, building_id)
    if not path.is_file():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def part_ready(stage_id: str, building_id: str) -> bool:
    try:
        meta = load_part_meta(stage_id, building_id)
        output = accepted_output_path(stage_id, building_id)
        return bool(
            meta.get("status") == "success"
            and meta.get("building_id") == building_id
            and output.is_file()
            and dc.sha256_file(output) == meta.get("accepted_output_sha256")
            and feature_ids(output) == [building_id]
            and meta.get("learning_runs_started") == 0
            and meta.get("new_inference_runs") == 0
        )
    except (FileNotFoundError, KeyError, RuntimeError, ValueError, json.JSONDecodeError):
        return False


def accept_part(
    stage_id: str,
    building_id: str,
    source_dir: Path,
    wall_seconds: float,
    log_path: Path,
    attempt: int,
    timeout_seconds: int,
) -> dict[str, Any]:
    population, _ = dc.load_population()
    if building_id not in set(population):
        raise RuntimeError(f"non-canonical recovery id {building_id}")
    sources = sorted(source_dir.glob("*.city.jsonl"))
    if len(sources) != 1:
        raise RuntimeError(
            f"isolated Roofer output count stage={stage_id} "
            f"building={building_id} count={len(sources)}"
        )
    source = sources[0]
    identifiers = feature_ids(source)
    if identifiers != [building_id]:
        raise RuntimeError(
            f"isolated Roofer identifier drift expected={building_id} "
            f"observed={identifiers}"
        )
    destination = accepted_output_path(stage_id, building_id)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(f"{destination}.tmp")
    shutil.copyfile(source, temporary)
    temporary.replace(destination)
    accepted_sha = dc.sha256_file(destination)
    payload = {
        "schema": "jointbuildgs.degradation_curve.recovery_part.v3",
        "created_utc": now(),
        "stage_id": stage_id,
        "building_id": building_id,
        "status": "success",
        "attempt": int(attempt),
        "timeout_seconds": int(timeout_seconds),
        "wall_seconds": float(wall_seconds),
        "ogr_filter": f"building_id = '{building_id}'",
        "source_output_path": relative_or_absolute(source),
        "source_output_sha256": dc.sha256_file(source),
        "accepted_output_path": dc.rel(destination),
        "accepted_output_sha256": accepted_sha,
        "feature_ids": identifiers,
        "log_path": relative_or_absolute(log_path),
        "log_sha256": dc.sha256_file(log_path),
        "roofer_image": dc.ROOFER_IMAGE,
        "roofer_parameters": dc.ROOFER_PARAMETERS,
        "execution_mode": "isolated_per_building_same_parameters",
        "scope_change_only": True,
        "reconstruction_parameter_change_count": 0,
        "learning_runs_started": 0,
        "new_inference_runs": 0,
    }
    meta_path = part_meta_path(stage_id, building_id)
    dc.atomic_text(meta_path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return payload


def record_failure(
    stage_id: str,
    building_id: str,
    exit_code: int,
    wall_seconds: float,
    log_path: Path,
    attempt: int,
    timeout_seconds: int,
) -> dict[str, Any]:
    payload = {
        "schema": "jointbuildgs.degradation_curve.recovery_attempt.v3",
        "created_utc": now(),
        "stage_id": stage_id,
        "building_id": building_id,
        "status": "timeout" if int(exit_code) in {124, 137} else "error",
        "exit_code": int(exit_code),
        "attempt": int(attempt),
        "timeout_seconds": int(timeout_seconds),
        "wall_seconds": float(wall_seconds),
        "ogr_filter": f"building_id = '{building_id}'",
        "log_path": relative_or_absolute(log_path),
        "log_sha256": dc.sha256_file(log_path) if log_path.is_file() else None,
        "roofer_image": dc.ROOFER_IMAGE,
        "roofer_parameters": dc.ROOFER_PARAMETERS,
        "execution_mode": "isolated_per_building_same_parameters",
        "learning_runs_started": 0,
        "new_inference_runs": 0,
    }
    path = (
        recovery_dir(stage_id)
        / "attempts"
        / f"{building_id}.attempt{attempt}.failure.json"
    )
    dc.atomic_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return payload


def finalize_stage(stage_id: str) -> dict[str, Any]:
    population, _ = dc.load_population()
    plan_rows = dc.read_csv(plan_path(stage_id))
    if (
        len(plan_rows) != dc.EXPECTED_POPULATION
        or [row["building_id"] for row in plan_rows] != population
    ):
        raise RuntimeError(f"recovery plan population/order drift stage={stage_id}")
    missing = [bid for bid in population if not part_ready(stage_id, bid)]
    if missing:
        raise RuntimeError(
            f"recovery parts incomplete stage={stage_id} n={len(missing)} "
            f"first={missing[:10]}"
        )
    expected_files = {
        accepted_output_path(stage_id, building_id).name
        for building_id in population
    }
    actual_files = {
        path.name
        for path in (dc.ROOFER_DIR / stage_id).glob("*.city.jsonl")
    }
    if actual_files != expected_files:
        raise RuntimeError(
            f"recovery accepted output set drift stage={stage_id} "
            f"missing={sorted(expected_files - actual_files)[:10]} "
            f"extra={sorted(actual_files - expected_files)[:10]}"
        )
    rows = []
    for order, building_id in enumerate(population, start=1):
        meta = load_part_meta(stage_id, building_id)
        rows.append({"order": order, **meta})
    measurement_path = recovery_dir(stage_id) / "isolated_measurements.csv"
    dc.atomic_csv(measurement_path, rows, MEASUREMENT_FIELDS)
    failure_paths = sorted((recovery_dir(stage_id) / "attempts").glob("*.json"))
    wall_values = [float(row["wall_seconds"]) for row in rows]
    output_hashes = {
        row["accepted_output_path"]: row["accepted_output_sha256"]
        for row in rows
    }
    input_path = dc.INPUT_DIR / stage_id / "aoi.laz"
    payload = {
        "schema": "jointbuildgs.degradation_curve.recovery_stage.v3",
        "created_utc": now(),
        "stage": dc.stage_payload(dc.STAGE_BY_ID[stage_id]),
        "status": "complete",
        "population_count": len(population),
        "successful_parts": len(rows),
        "failed_attempt_records": len(failure_paths),
        "failed_attempt_sha256": {
            dc.rel(path): dc.sha256_file(path) for path in failure_paths
        },
        "execution_mode": "isolated_per_building_same_parameters",
        "scope_change_only": True,
        "reconstruction_parameter_change_count": 0,
        "stage_input_path": dc.rel(input_path),
        "stage_input_sha256": dc.sha256_file(input_path),
        "roofer_image": dc.ROOFER_IMAGE,
        "roofer_parameters": dc.ROOFER_PARAMETERS,
        "wall_seconds_sum": sum(wall_values),
        "wall_seconds_median": median(wall_values),
        "wall_seconds_max": max(wall_values),
        "isolated_measurements_csv": dc.rel(measurement_path),
        "isolated_measurements_sha256": dc.sha256_file(measurement_path),
        "accepted_output_sha256": output_hashes,
        "accepted_output_aggregate_sha256": dc.aggregate_sha(
            sorted(output_hashes.items())
        ),
        "plan_manifest": dc.rel(recovery_dir(stage_id) / "plan_manifest.json"),
        "plan_manifest_sha256": dc.sha256_file(
            recovery_dir(stage_id) / "plan_manifest.json"
        ),
        "incident_record": dc.rel(INCIDENT) if INCIDENT.is_file() else None,
        "incident_record_sha256": (
            dc.sha256_file(INCIDENT) if INCIDENT.is_file() else None
        ),
        "learning_runs_started": 0,
        "new_inference_runs": 0,
    }
    manifest = recovery_dir(stage_id) / "manifest.json"
    dc.atomic_text(manifest, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    plan = subparsers.add_parser("plan")
    plan.add_argument("--stage", required=True, choices=sorted(dc.STAGE_BY_ID))
    ready = subparsers.add_parser("part-ready")
    ready.add_argument("--stage", required=True, choices=sorted(dc.STAGE_BY_ID))
    ready.add_argument("--building-id", required=True)
    accept = subparsers.add_parser("accept")
    accept.add_argument("--stage", required=True, choices=sorted(dc.STAGE_BY_ID))
    accept.add_argument("--building-id", required=True)
    accept.add_argument("--source-dir", type=Path, required=True)
    accept.add_argument("--wall-seconds", type=float, required=True)
    accept.add_argument("--log-path", type=Path, required=True)
    accept.add_argument("--attempt", type=int, required=True)
    accept.add_argument("--timeout-seconds", type=int, required=True)
    failure = subparsers.add_parser("record-failure")
    failure.add_argument("--stage", required=True, choices=sorted(dc.STAGE_BY_ID))
    failure.add_argument("--building-id", required=True)
    failure.add_argument("--exit-code", type=int, required=True)
    failure.add_argument("--wall-seconds", type=float, required=True)
    failure.add_argument("--log-path", type=Path, required=True)
    failure.add_argument("--attempt", type=int, required=True)
    failure.add_argument("--timeout-seconds", type=int, required=True)
    finalize = subparsers.add_parser("finalize")
    finalize.add_argument("--stage", required=True, choices=sorted(dc.STAGE_BY_ID))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "plan":
        payload = build_plan(args.stage)
    elif args.command == "part-ready":
        if not part_ready(args.stage, args.building_id):
            raise SystemExit(1)
        payload = {
            "stage_id": args.stage,
            "building_id": args.building_id,
            "ready": True,
        }
    elif args.command == "accept":
        payload = accept_part(
            args.stage,
            args.building_id,
            args.source_dir,
            args.wall_seconds,
            args.log_path,
            args.attempt,
            args.timeout_seconds,
        )
    elif args.command == "record-failure":
        payload = record_failure(
            args.stage,
            args.building_id,
            args.exit_code,
            args.wall_seconds,
            args.log_path,
            args.attempt,
            args.timeout_seconds,
        )
    elif args.command == "finalize":
        payload = finalize_stage(args.stage)
    else:
        raise AssertionError(args.command)
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
