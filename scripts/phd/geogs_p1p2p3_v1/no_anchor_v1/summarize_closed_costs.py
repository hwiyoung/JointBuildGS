"""Reconcile a frozen union of producer costs without counting history twice.

Run in Docker with /task read-only and an additive /out. No geometry, model,
reference, service or training input is opened. Decimal preserves producer times.
"""
from __future__ import annotations

import argparse
import csv
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import platform
import sys
import traceback


def digest(data):
    return hashlib.sha256(data).hexdigest()


def number(value):
    if isinstance(value, bool):
        raise ValueError("Boolean is not a time measurement")
    try:
        value = Decimal(str(value))
    except InvalidOperation as error:
        raise ValueError("Invalid time measurement") from error
    if not value.is_finite() or value < 0:
        raise ValueError("Time measurement must be finite and nonnegative")
    return value


def text_number(value):
    return format(value, "f")


def write_json(path, value):
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def write_csv(path, rows, fields):
    with path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


class Evidence:
    def __init__(self, task):
        self.task = task.resolve()
        self.records = {}

    def read(self, source, expected):
        path = PurePosixPath(source)
        if path.is_absolute():
            if not path.is_relative_to("/task"):
                raise ValueError(f"Unexpected source mount: {source}")
            path = path.relative_to("/task")
        if not path.parts or ".." in path.parts:
            raise ValueError(f"Uncontained source: {source}")
        actual = self.task.joinpath(*path.parts)
        if actual.resolve() != actual or not actual.is_file():
            raise ValueError(f"Source is not an immutable direct file: {source}")
        data = actual.read_bytes()
        actual_sha = digest(data)
        if actual_sha != expected:
            raise ValueError(f"Source digest differs: {source}")
        canonical = "/task/" + path.as_posix()
        record = dict(source_path=canonical, source_sha256=actual_sha,
                      source_bytes=len(data))
        if canonical in self.records and self.records[canonical] != record:
            raise ValueError(f"Source changed: {source}")
        self.records[canonical] = record
        return data, record

    def json(self, source, expected):
        data, record = self.read(source, expected)
        return json.loads(data, parse_float=Decimal), record

    def csv(self, source, expected):
        data, record = self.read(source, expected)
        return list(csv.DictReader(io.StringIO(data.decode("utf-8")))), record


def reconcile(task, config):
    evidence = Evidence(task)
    base = config["resource_profile"]
    summary, _ = evidence.json(base + "/summary.json", config["resource_summary_sha256"])
    if summary["status"] != config["expected_resource_summary_status"] or summary["included_regions"]:
        raise ValueError("The frozen resource profile no longer describes all failed main runs")
    if summary.get("scientific_verdict") is not None:
        raise ValueError("A scientific verdict is outside this cost summary")
    groups, input_counts, path_hashes = {}, {}, {}
    for table, expected in config["input_tables"].items():
        rows, _ = evidence.csv(base + "/" + table, expected)
        input_counts[table] = len(rows)
        summary_rows = summary["tables"][table.removesuffix(".csv")]
        if len(summary_rows) != len(rows):
            raise ValueError("Frozen JSON/CSV row counts differ")
        for i, row in enumerate(rows, 2):
            key = row["source_path"], row["source_sha256"]
            if key[0] in path_hashes and path_hashes[key[0]] != key[1]:
                raise ValueError("One producer path has conflicting source digests")
            path_hashes[key[0]] = key[1]
            if key[0] != "/task/" + PurePosixPath(key[0]).relative_to("/task").as_posix():
                raise ValueError("CSV identity is not a canonical /task path")
            sr = summary_rows[i - 2]
            if (sr["source_path"], sr["source_sha256"]) != key or number(sr["wall_seconds"]) != number(row["wall_seconds"]):
                raise ValueError("Frozen JSON/CSV producer identity or cost differs")
            producer, record = evidence.json(*key)
            if int(row["source_bytes"]) != record["source_bytes"]:
                raise ValueError("Producer byte count differs")
            if producer.get("scientific_verdict") is not None:
                raise ValueError("Unexpected producer scientific verdict")
            phase, region = producer["phase"], producer["region"]
            if phase not in config["phase_scope"] or region not in config["selected_attempts"]:
                raise ValueError("Producer phase/region outside fixed scope")
            if producer["condition_id"] != config["condition_id"] or producer["runtime_image_id"] != config["runtime_image_id"] or producer["config_sha256"] != config["science_config_sha256"]:
                raise ValueError("Producer condition/config/runtime identity differs")
            if producer["status"] not in ("PASS", "FAIL"):
                raise ValueError("Producer phase is not closed")
            for field in ["phase", "region", "status", "native_exit_code", "validated_exit_code", "child_peak_rss_bytes"]:
                if str(producer[field]) != row[field]:
                    raise ValueError(f"CSV/producer mismatch: {field}")
            if row["condition"] != producer["condition_id"]:
                raise ValueError("CSV condition differs")
            if table == "new_failed_training_attempts.csv" and (phase != "train" or producer["status"] != "FAIL"):
                raise ValueError("Failed training table contains an unexpected phase")
            wall = number(producer["wall_seconds"])
            if wall != number(row["wall_seconds"]):
                raise ValueError("CSV time differs from the original producer JSON number")
            interval = number(producer["finished_unix"]) - number(producer["started_unix"])
            if interval < 0 or abs(interval - wall) > number(config["timestamp_interval_tolerance_seconds"]):
                raise ValueError("Producer time is inconsistent with its closed timestamps")
            identity = dict(**record, region=region, phase=phase, status=producer["status"],
                            native_exit_code=producer["native_exit_code"],
                            validated_exit_code=producer["validated_exit_code"],
                            wall_seconds=text_number(wall),
                            started_unix=text_number(number(producer["started_unix"])),
                            finished_unix=text_number(number(producer["finished_unix"])),
                            timestamp_interval_minus_wall_seconds=text_number(interval - wall),
                            source_csv_cost_equal=True, scientific_verdict=None)
            group = groups.setdefault(key, dict(identity=identity, memberships=[]))
            if group["identity"] != identity:
                raise ValueError("Duplicate source identity has conflicting producer cost")
            group["memberships"].append(dict(table=table, csv_line=i,
                                             category=row.get("category", ""),
                                             termination_reason_as_reported=row.get("termination_reason", "")))

    availability, _ = evidence.csv(base + "/region_availability.csv", config["availability_sha256"])
    if len(availability) != len(config["selected_attempts"]) or {r["region"] for r in availability} != set(config["selected_attempts"]):
        raise ValueError("Main availability must contain exactly the three fixed regions")
    selected, main_status = set(), []
    for row in sorted(availability, key=lambda r: r["region"]):
        region = row["region"]
        root = "/task/" + config["selected_attempts"][region]
        path = root + "/runs/" + region + "/" + config["condition_id"] + "/receipt.json"
        if row["selected_experiment"] != root or row["training_receipt_path"] != path or row["training_status"] != "FAIL" or row["included"] != "False":
            raise ValueError("The availability row is not the fixed failed final attempt")
        keys = [key for key in groups if key[0] == path]
        if len(keys) != 1:
            raise ValueError("Final attempt is missing from the unique cost union")
        key = keys[0]
        producer = groups[key]["identity"]
        if producer["status"] != config["expected_selected_training_status"] or producer["native_exit_code"] != config["expected_selected_native_exit_code"] or producer["validated_exit_code"] != config["expected_selected_native_exit_code"]:
            raise ValueError("Actual final producer does not match the frozen failure state")
        selected.add(key)
        main_status.append(dict(region=region, training_status=producer["status"],
                                native_exit_code=producer["native_exit_code"],
                                source_path=key[0], source_sha256=key[1],
                                reconstruction_available=False, quality_score=None,
                                scientific_verdict=None))

    proofs, unique_rows = [], []
    for key, group in sorted(groups.items(), key=lambda pair: (pair[1]["identity"]["region"], pair[0])):
        proofs.append(dict(**group["identity"], memberships=group["memberships"]))
        unique_rows.append(dict(**{k: group["identity"][k] for k in
            ["region", "phase", "status", "native_exit_code", "validated_exit_code", "wall_seconds", "source_path", "source_sha256", "source_bytes"]},
            selected_for_main=key in selected, membership_count=len(group["memberships"]),
            source_memberships=json.dumps(group["memberships"], ensure_ascii=False),
            scientific_verdict=None))

    totals = []
    for region in [*sorted(config["selected_attempts"]), "ALL"]:
        rows = [r for r in unique_rows if region == "ALL" or r["region"] == region]
        work = sum((number(r["wall_seconds"]) for r in rows), Decimal(0))
        train = [r for r in rows if r["phase"] == "train"]
        exports = [r for r in rows if r["phase"] == "export"]
        selected_work = sum((number(r["wall_seconds"]) for r in rows if r["selected_for_main"]), Decimal(0))
        totals.append(dict(region=region, training_attempt_count=len(train),
                           export_phase_count=len(exports), unique_producer_phase_count=len(rows),
                           work_seconds=text_number(work), work_hours=text_number(work / Decimal(3600)),
                           training_work_seconds=text_number(sum((number(r["wall_seconds"]) for r in train), Decimal(0))),
                           export_work_seconds=text_number(sum((number(r["wall_seconds"]) for r in exports), Decimal(0))),
                           selected_final_training_work_seconds=text_number(selected_work),
                           earlier_training_work_seconds=text_number(work - selected_work - sum((number(r["wall_seconds"]) for r in exports), Decimal(0))),
                           calendar_wall_time=False, gpu_hours=False, scientific_verdict=None))
    if sum((number(r["work_seconds"]) for r in totals[:-1]), Decimal(0)) != number(totals[-1]["work_seconds"]):
        raise ValueError("Regional and global totals do not reconcile")
    result = dict(status="PASS_CLOSED_PRODUCER_COSTS_RECONCILED", scientific_verdict=None,
                  main_status="ALL_THREE_SELECTED_TRAINING_ATTEMPTS_FAILED",
                  unique_key=config["unique_key"], input_row_counts=input_counts,
                  unique_producer_phase_count=len(unique_rows),
                  duplicate_memberships_removed=sum(input_counts.values()) - len(unique_rows),
                  excluded_cost_views=config["excluded_cost_views"], scope=config["scope"],
                  totals=totals, source_proofs_count=len(proofs),
                  producer_json_time_sum_exact=True, regional_sum_equals_global=True)
    return result, unique_rows, proofs, main_status, evidence


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--runtime-image-id", required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if any(path.name != "execution" for path in args.out.iterdir()):
        raise FileExistsError("Cost output already contains results; preserve and select a new output")
    receipt = dict(schema="GEOGS_SFM_CLOSED_COST_RECEIPT_v1", status="FAIL",
                   scientific_verdict=None, command=sys.argv, python_version=platform.python_version(),
                   source_sha256=digest(Path(__file__).read_bytes()),
                   config_sha256=digest(args.config.read_bytes()), runtime_image_id=args.runtime_image_id,
                   gpu_requested=False)
    try:
        config = json.loads(args.config.read_text())
        if config["schema"] != "GEOGS_SFM_CLOSED_COST_POLICY_v1" or config["scientific_verdict"] is not None or args.runtime_image_id != config["runtime_image_id"]:
            raise ValueError("Cost policy/runtime identity differs")
        result, rows, proofs, main_status, evidence = reconcile(args.task, config)
        write_csv(args.out / "unique_producer_phases.csv", rows, list(rows[0]))
        write_csv(args.out / "regional_totals.csv", result["totals"], list(result["totals"][0]))
        write_json(args.out / "source_proofs.json", dict(inputs=list(evidence.records.values()), producers=proofs, scientific_verdict=None))
        write_json(args.out / "main_status.json", dict(status=result["main_status"], regions=main_status, scientific_verdict=None))
        write_json(args.out / "summary.json", result)
        receipt.update(status="PASS", result_status=result["status"],
                       sources=list(evidence.records.values()),
                       outputs=[dict(path=p.name, bytes=p.stat().st_size, sha256=digest(p.read_bytes())) for p in sorted(args.out.iterdir()) if p.is_file()])
        write_json(args.out / "receipt.json", receipt)
        print(json.dumps(dict(status=receipt["status"], totals=result["totals"])))
    except Exception as error:
        receipt.update(error_type=type(error).__name__, error=str(error), traceback=traceback.format_exc())
        write_json(args.out / "receipt.json", receipt)
        raise


if __name__ == "__main__":
    main()
