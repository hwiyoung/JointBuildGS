#!/usr/bin/env python3
"""Pinned aggregate-only wrapper for the P1W dense-overlay round-trip bug.

The ten sealed per-run score CSVs already contain the dense/ALS overlay.  The
committed aggregate path validates those marker-bound rows, applies the same
overlay a second time, and then requires exact equality with the score marker.
Only the nonlinear ``als_gap_closed_fraction`` changes, because its operands
have already crossed the nine-decimal CSV boundary.

This wrapper imports the exact committed scorer and makes that aggregate step
idempotent.  It independently runs the original second overlay, fails closed
unless its drift is the exactly observed last-decimal pattern, and returns the
original marker-bound rows unchanged.  It does not alter scoring, Roofer,
training, controls, metrics, or winner logic.
"""
from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Mapping, Sequence
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
from typing import Any

sys.dont_write_bytecode = True


EXPECTED_SCORING_SHA256 = (
    "7e40371708ab580c132b08e2ba411a3de530feddf35e908af74e4a086c102dcf"
)
EXPECTED_DRIFT_FIELD = "als_gap_closed_fraction"
MAX_ABS_DRIFT = 3.0e-8
EXPECTED_DRIFT_COUNTS = {
    "01_seed1001": 9,
    "01_seed1002": 6,
    "02_seed1001": 9,
    "02_seed1002": 8,
    "03_seed1001": 8,
    "03_seed1002": 11,
    "04a_seed1001": 6,
    "04a_seed1002": 8,
    "04b_seed1001": 8,
    "04b_seed1002": 5,
}
EXPECTED_RUN_SCORE_SHA256 = {
    "01_seed1001":
        "a3a8311c3587e02ddea8bc272a1037c471bbe91471f746abfed7230bfd566ce0",
    "01_seed1002":
        "ff5f055410069c2d0bb6b98961be7de84ba79af1cd3a61067939fce1d33c28db",
    "02_seed1001":
        "746d0af3ec87862c4188addefbb2f7797676d5a879ebf35f8524af06a91916c2",
    "02_seed1002":
        "85e9e2dd7c19d69129c7d7112e6d8ae63bc67a1357f42eb2a206c8a0e0a7e6ca",
    "03_seed1001":
        "960ad75e686e9e629b05611cd220951bdaac98f3dabeaa4e05109b10ac8e955f",
    "03_seed1002":
        "bcf92d331b9a020490bd7dee789bd689d1beac42d71798b75a93212d5c61d02e",
    "04a_seed1001":
        "f1a7269e4c226716e9fa4a26b16a0efe73055646d80b61fcac69a91c48318c3c",
    "04a_seed1002":
        "367326fe5dbc305f3c7d6a7f481ea7ebd659e7aa614214d2a53263b06727d568",
    "04b_seed1001":
        "98a849becdd86bc87ec74e0bd7134178d4dbc78c00e29264326f0deb4cca1747",
    "04b_seed1002":
        "9f82abf45d9993322ddda01b9a43a6f16f388f97d53dc82814460add2d71640f",
}
EXPECTED_DRIFT_FINGERPRINT_SHA256 = (
    "e88e894612eb8207eb8cd4293105da2c947300ecc66b188cafc387a6e52dc1ce"
)
EXPECTED_TOTAL_CANDIDATE_ROWS = 300
EXPECTED_OUTPUT_ROWS = {
    "pilot_1wave_scores.csv": 390,
    "pilot_1wave_summary.csv": 234,
    "pilot_1wave_seg_upperbound_gap.csv": 60,
    "pilot_1wave_winner.csv": 4,
    "pilot_1wave_loss_shares.csv": 14_000,
}
RECONCILIATION_NAME = "aggregate_overlay_reconciliation.json"
RECONCILIATION_SCHEMA = (
    "jointbuildgs.pilot_1wave.aggregate_overlay_reconciliation.v1"
)


class AggregateRecoveryError(RuntimeError):
    """A fail-closed aggregate recovery contract violation."""


def sha256_file(path: Path, block_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def require_equal(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        raise AggregateRecoveryError(
            f"{label} mismatch: {actual!r} != {expected!r}"
        )


def verify_sidecar(path: Path) -> str:
    sidecar = path.with_suffix(".sha256")
    if not sidecar.is_file() or sidecar.is_symlink():
        raise AggregateRecoveryError(f"SHA sidecar missing/non-regular: {sidecar}")
    fields = sidecar.read_text(encoding="ascii").strip().split()
    require_equal(len(fields), 2, "SHA sidecar field count")
    require_equal(fields[1], path.name, "SHA sidecar filename")
    actual = sha256_file(path)
    require_equal(fields[0], actual, "source SHA256")
    return actual


def find_repo(path: Path) -> Path:
    for candidate in (path, *path.parents):
        scoring = (
            candidate
            / "phases/p2-gsjso/scripts/pilot_1wave_scoring.py"
        )
        if scoring.is_file() and (candidate / ".git").exists():
            return candidate
    raise AggregateRecoveryError(f"repository not found above {path}")


WRAPPER_PATH = Path(__file__).resolve()
REPO = find_repo(WRAPPER_PATH.parent)
SCORING_PATH = REPO / "phases/p2-gsjso/scripts/pilot_1wave_scoring.py"
CONTROLLER_PATH = WRAPPER_PATH.parent / "p1w_same_head_aggregate_recovery.py"


def import_committed_scoring() -> Any:
    require_equal(
        sha256_file(SCORING_PATH),
        EXPECTED_SCORING_SHA256,
        "committed scoring source SHA256",
    )
    spec = importlib.util.spec_from_file_location(
        "p1w_committed_scoring_for_aggregate_recovery", SCORING_PATH
    )
    if spec is None or spec.loader is None:
        raise AggregateRecoveryError(
            f"cannot import committed scorer: {SCORING_PATH}"
        )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def audit_candidate_groups(
    scoring: Any,
    score_paths: Sequence[Path],
    *,
    deep_validate: bool,
) -> dict[str, Any]:
    require_equal(len(score_paths), 10, "run-score path count")
    lock = scoring.load_pilot_lock()
    controls = scoring.load_control_rows(lock)
    all_rows: list[dict[str, str]] = []
    source_paths: list[dict[str, Any]] = []
    for path in score_paths:
        if path.is_symlink() or not path.is_file():
            raise AggregateRecoveryError(
                f"run score missing/non-regular: {path}"
            )
        resolved = path.resolve()
        rows = scoring.read_csv(resolved)
        require_equal(len(rows), 30, f"run score rows {resolved}")
        source_ids = {str(row.get("source_id", "")) for row in rows}
        if len(source_ids) != 1:
            raise AggregateRecoveryError(
                f"run score source IDs are not unique: {resolved}: {source_ids}"
            )
        source_id = next(iter(source_ids))
        if source_id not in EXPECTED_RUN_SCORE_SHA256:
            raise AggregateRecoveryError(
                f"unexpected run score source ID: {source_id}"
            )
        actual_sha = sha256_file(resolved)
        require_equal(
            actual_sha,
            EXPECTED_RUN_SCORE_SHA256[source_id],
            f"{source_id} locked run score SHA",
        )
        all_rows.extend(rows)
        source_paths.append(
            {
                "source_id": source_id,
                "path": scoring.rel(resolved),
                "size": resolved.stat().st_size,
                "sha256": actual_sha,
            }
        )
    require_equal(
        [record["source_id"] for record in source_paths],
        list(EXPECTED_RUN_SCORE_SHA256),
        "canonical run score input order",
    )
    require_equal(
        len(all_rows), EXPECTED_TOTAL_CANDIDATE_ROWS, "candidate input rows"
    )
    groups = scoring._group_candidate_rows(all_rows, lock)
    require_equal(
        set(groups),
        {
            (condition, seed)
            for condition in scoring.ALL_CONDITIONS
            for seed in scoring.EXPECTED_SEEDS
        },
        "candidate condition/seed groups",
    )

    observed: dict[str, int] = {}
    changed_fields: Counter[str] = Counter()
    max_abs_drift = 0.0
    min_abs_drift: float | None = None
    drift_fingerprint_records: list[dict[str, str]] = []
    unchanged_rows = 0
    affected_rows = 0
    original_attach = scoring.attach_dense_controls
    for condition in scoring.ALL_CONDITIONS:
        for seed in scoring.EXPECTED_SEEDS:
            group = groups[(condition, seed)]
            if deep_validate:
                scoring._validate_candidate_group(
                    condition, seed, group, lock
                )
            reoverlaid = original_attach(group, controls)
            run_id = f"{condition}_seed{seed}"
            run_affected = 0
            for original, second in zip(group, reoverlaid, strict=True):
                before = scoring._csv_normalized(original)
                after = scoring._csv_normalized(second)
                fields = [
                    field
                    for field in scoring.SCORE_FIELDS
                    if before[field] != after[field]
                ]
                if not fields:
                    unchanged_rows += 1
                    continue
                require_equal(
                    fields,
                    [EXPECTED_DRIFT_FIELD],
                    f"{run_id}/{original.get('building_id')} drift fields",
                )
                try:
                    difference = abs(
                        float(after[EXPECTED_DRIFT_FIELD])
                        - float(before[EXPECTED_DRIFT_FIELD])
                    )
                except (TypeError, ValueError) as exc:
                    raise AggregateRecoveryError(
                        f"{run_id}/{original.get('building_id')} "
                        "non-numeric aggregate drift"
                    ) from exc
                if (
                    not math.isfinite(difference)
                    or difference <= 0.0
                    or difference > MAX_ABS_DRIFT
                ):
                    raise AggregateRecoveryError(
                        f"{run_id}/{original.get('building_id')} drift "
                        f"{difference} is outside (0,{MAX_ABS_DRIFT}]"
                    )
                drift_fingerprint_records.append(
                    {
                        "run_id": run_id,
                        "building_id": str(original.get("building_id")),
                        "before": before[EXPECTED_DRIFT_FIELD],
                        "after": after[EXPECTED_DRIFT_FIELD],
                    }
                )
                max_abs_drift = max(max_abs_drift, difference)
                min_abs_drift = (
                    difference
                    if min_abs_drift is None
                    else min(min_abs_drift, difference)
                )
                changed_fields.update(fields)
                affected_rows += 1
                run_affected += 1
            require_equal(
                run_affected,
                EXPECTED_DRIFT_COUNTS[run_id],
                f"{run_id} affected row count",
            )
            observed[run_id] = run_affected

    require_equal(observed, EXPECTED_DRIFT_COUNTS, "per-run drift counts")
    require_equal(affected_rows, 78, "total affected rows")
    require_equal(unchanged_rows, 222, "total unchanged rows")
    require_equal(
        set(changed_fields), {EXPECTED_DRIFT_FIELD}, "aggregate drift fields"
    )
    drift_fingerprint = hashlib.sha256(
        json.dumps(
            drift_fingerprint_records,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    require_equal(
        drift_fingerprint,
        EXPECTED_DRIFT_FINGERPRINT_SHA256,
        "affected building/delta fingerprint",
    )
    return {
        "state": "pass",
        "candidate_rows": len(all_rows),
        "unchanged_rows": unchanged_rows,
        "affected_rows": affected_rows,
        "affected_rows_by_run": observed,
        "changed_fields": sorted(changed_fields),
        "max_abs_drift": max_abs_drift,
        "min_abs_drift": min_abs_drift,
        "max_allowed_abs_drift": MAX_ABS_DRIFT,
        "affected_building_delta_fingerprint_sha256": drift_fingerprint,
        "deep_score_marker_validation": deep_validate,
        "run_scores": source_paths,
    }


def make_idempotent_attach(
    scoring: Any,
    expected_audit: Mapping[str, Any],
) -> Any:
    """Return an aggregate-only attach that verifies, then preserves, rows."""

    original_attach = scoring.attach_dense_controls
    calls: dict[str, int] = {}

    def marker_bound_attach(
        candidate_rows: Sequence[Mapping[str, Any]],
        controls: Sequence[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        rows = [dict(row) for row in candidate_rows]
        require_equal(len(rows), 30, "aggregate attach group rows")
        source_ids = {str(row.get("source_id", "")) for row in rows}
        if len(source_ids) != 1:
            raise AggregateRecoveryError(
                f"aggregate attach source IDs are not unique: {source_ids}"
            )
        run_id = next(iter(source_ids))
        if run_id not in EXPECTED_DRIFT_COUNTS:
            raise AggregateRecoveryError(
                f"unexpected aggregate attach source ID: {run_id}"
            )
        require_equal(calls.get(run_id, 0), 0, f"{run_id} attach call count")
        second = original_attach(rows, controls)
        affected = 0
        for original, reoverlaid in zip(rows, second, strict=True):
            before = scoring._csv_normalized(original)
            after = scoring._csv_normalized(reoverlaid)
            fields = [
                field
                for field in scoring.SCORE_FIELDS
                if before[field] != after[field]
            ]
            if not fields:
                continue
            require_equal(
                fields,
                [EXPECTED_DRIFT_FIELD],
                f"{run_id}/{original.get('building_id')} aggregate drift fields",
            )
            difference = abs(
                float(after[EXPECTED_DRIFT_FIELD])
                - float(before[EXPECTED_DRIFT_FIELD])
            )
            if (
                not math.isfinite(difference)
                or difference <= 0.0
                or difference > MAX_ABS_DRIFT
            ):
                raise AggregateRecoveryError(
                    f"{run_id}/{original.get('building_id')} aggregate drift "
                    f"{difference} is outside (0,{MAX_ABS_DRIFT}]"
                )
            affected += 1
        require_equal(
            affected,
            EXPECTED_DRIFT_COUNTS[run_id],
            f"{run_id} aggregate affected rows",
        )
        require_equal(
            affected,
            int(
                (expected_audit.get("affected_rows_by_run") or {}).get(
                    run_id, -1
                )
            ),
            f"{run_id} audit/aggregate affected rows",
        )
        calls[run_id] = 1
        return rows

    marker_bound_attach.calls = calls
    return marker_bound_attach


def verify_fresh_aggregate_output_dir(
    scoring: Any,
    output_dir: Path,
) -> None:
    """Fail before mutation unless the driver-created aggregate dir is fresh."""

    if output_dir.is_symlink() or not output_dir.is_dir():
        raise AggregateRecoveryError(
            f"aggregate output directory missing/non-regular: {output_dir}"
        )
    expected_files = {
        "pilot_1wave_scores.csv",
        "pilot_1wave_summary.csv",
        "pilot_1wave_seg_upperbound_gap.csv",
        "pilot_1wave_loss_shares.csv",
        "pilot_1wave_winner.csv",
        "pilot_1wave_manifest.json",
    }
    entries = list(output_dir.iterdir())
    actual_files = {path.name for path in entries}
    require_equal(
        actual_files, expected_files, "fresh aggregate output file set"
    )
    if any(path.is_symlink() or not path.is_file() for path in entries):
        raise AggregateRecoveryError(
            "fresh aggregate output directory contains a symlink/non-file"
        )
    if (output_dir / RECONCILIATION_NAME).exists():
        raise AggregateRecoveryError(
            "aggregate reconciliation exists before aggregate execution"
        )
    expected_rows = {
        "pilot_1wave_scores.csv": 0,
        "pilot_1wave_summary.csv": 0,
        "pilot_1wave_seg_upperbound_gap.csv": 0,
        "pilot_1wave_winner.csv": 0,
        "pilot_1wave_loss_shares.csv": 14_000,
    }
    for name, expected in expected_rows.items():
        require_equal(
            count_csv_rows(output_dir / name),
            expected,
            f"fresh aggregate {name} rows",
        )
    manifest = json.loads(
        (output_dir / "pilot_1wave_manifest.json").read_text(encoding="utf-8")
    )
    require_equal(
        manifest.get("state"),
        "schema_initialized",
        "fresh aggregate manifest state",
    )
    if "aggregate_recovery" in manifest:
        raise AggregateRecoveryError(
            "fresh aggregate manifest already has recovery provenance"
        )
    if RECONCILIATION_NAME in (manifest.get("outputs") or {}):
        raise AggregateRecoveryError(
            "fresh aggregate manifest already has reconciliation output"
        )


def count_csv_rows(path: Path) -> int:
    import csv

    with path.open(newline="", encoding="utf-8") as stream:
        return len(list(csv.DictReader(stream)))


def verify_aggregate_outputs(
    scoring: Any,
    output_dir: Path,
    score_paths: Sequence[Path],
) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for name, expected_rows in EXPECTED_OUTPUT_ROWS.items():
        path = output_dir / name
        if not path.is_file() or path.is_symlink():
            raise AggregateRecoveryError(
                f"aggregate output missing/non-regular: {path}"
            )
        rows = count_csv_rows(path)
        require_equal(rows, expected_rows, f"{name} row count")
        records[name] = {
            "path": scoring.rel(path),
            "row_count": rows,
            "size": path.stat().st_size,
            "sha256": sha256_file(path),
        }

    incoming: dict[tuple[str, str, str], dict[str, str]] = {}
    for path in score_paths:
        for row in scoring.read_csv(path):
            key = (
                str(row.get("condition_id")),
                str(row.get("seed")),
                str(row.get("building_id")),
            )
            if key in incoming:
                raise AggregateRecoveryError(
                    f"duplicate incoming candidate row: {key}"
                )
            incoming[key] = scoring._csv_normalized(row)
    output_rows = scoring.read_csv(output_dir / "pilot_1wave_scores.csv")
    output_candidates = {
        (
            str(row.get("condition_id")),
            str(row.get("seed")),
            str(row.get("building_id")),
        ): scoring._csv_normalized(row)
        for row in output_rows
        if row.get("condition_id") in scoring.ALL_CONDITIONS
    }
    require_equal(
        len(output_candidates),
        EXPECTED_TOTAL_CANDIDATE_ROWS,
        "aggregate output candidate rows",
    )
    require_equal(
        output_candidates,
        incoming,
        "aggregate marker-bound candidate row preservation",
    )
    return records


def bind_reconciliation_into_scoring_manifest(
    scoring: Any,
    output_dir: Path,
    receipt_path: Path,
    receipt: Mapping[str, Any],
) -> dict[str, Any]:
    """Embed recovery provenance in the manifest that is later published."""

    manifest_path = output_dir / "pilot_1wave_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise AggregateRecoveryError("scoring manifest root is not an object")
    outputs = manifest.get("outputs")
    if not isinstance(outputs, dict):
        raise AggregateRecoveryError("scoring manifest outputs are missing")
    receipt_record = {
        "path": scoring.rel(receipt_path),
        "record_type": "json_provenance",
        "size": receipt_path.stat().st_size,
        "sha256": sha256_file(receipt_path),
    }
    if RECONCILIATION_NAME in outputs:
        raise AggregateRecoveryError(
            "scoring manifest already has aggregate reconciliation provenance"
        )
    outputs[RECONCILIATION_NAME] = receipt_record
    manifest["aggregate_recovery"] = {
        "schema": RECONCILIATION_SCHEMA,
        "state": "pass",
        "reason": receipt["reason"],
        "committed_scoring": dict(receipt["committed_scoring"]),
        "wrapper": dict(receipt["wrapper"]),
        "controller": dict(receipt["controller"]),
        "reconciliation": receipt_record,
        "patch_scope": receipt["patch_scope"],
        "row_action": receipt["row_action"],
        "candidate_scientific_scores_recomputed": False,
        "aggregate_outputs_computed": True,
        "committed_aggregate_deep_validation_executed": True,
        "candidate_rows": int((receipt.get("audit") or {})["candidate_rows"]),
        "unchanged_rows": int((receipt.get("audit") or {})["unchanged_rows"]),
        "affected_rows": int((receipt.get("audit") or {})["affected_rows"]),
        "affected_rows_by_run": dict(
            (receipt.get("audit") or {})["affected_rows_by_run"]
        ),
        "changed_fields": list(
            (receipt.get("audit") or {})["changed_fields"]
        ),
        "max_abs_drift": float(
            (receipt.get("audit") or {})["max_abs_drift"]
        ),
        "max_allowed_abs_drift": MAX_ABS_DRIFT,
        "affected_building_delta_fingerprint_sha256": (
            (receipt.get("audit") or {})[
                "affected_building_delta_fingerprint_sha256"
            ]
        ),
        "run_score_inputs": [
            dict(record)
            for record in (receipt.get("audit") or {})["run_scores"]
        ],
        "training_started": 0,
        "roofer_started": 0,
        "score_started": 0,
    }
    scoring.atomic_json(manifest_path, manifest)
    rebound = json.loads(manifest_path.read_text(encoding="utf-8"))
    require_equal(
        rebound.get("aggregate_recovery"),
        manifest["aggregate_recovery"],
        "scoring manifest aggregate recovery provenance",
    )
    require_equal(
        (rebound.get("outputs") or {}).get(RECONCILIATION_NAME),
        receipt_record,
        "scoring manifest reconciliation output",
    )
    return {
        "path": scoring.rel(manifest_path),
        "size": manifest_path.stat().st_size,
        "sha256": sha256_file(manifest_path),
        "aggregate_recovery": manifest["aggregate_recovery"],
    }


def parse_recovery_cli(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    audit = sub.add_parser("audit-only")
    audit.add_argument("--run-score", action="append", type=Path, required=True)
    return parser.parse_args(list(argv))


def aggregate_arguments(argv: Sequence[str]) -> tuple[Path, list[Path]]:
    values = list(argv)
    if not values or values[0] != "aggregate-scores":
        raise AggregateRecoveryError("aggregate argument parser used incorrectly")
    output_dir: Path | None = None
    scores: list[Path] = []
    index = 1
    while index < len(values):
        token = values[index]
        if token == "--output-dir" and index + 1 < len(values):
            output_dir = Path(values[index + 1])
            index += 2
        elif token == "--run-score" and index + 1 < len(values):
            scores.append(Path(values[index + 1]))
            index += 2
        else:
            raise AggregateRecoveryError(
                f"unexpected aggregate wrapper argument: {token!r}"
            )
    if output_dir is None:
        raise AggregateRecoveryError("aggregate output directory is missing")
    require_equal(len(scores), 10, "aggregate run-score argument count")
    return output_dir, scores


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    wrapper_sha = verify_sidecar(WRAPPER_PATH)
    controller_sha = verify_sidecar(CONTROLLER_PATH)
    scoring = import_committed_scoring()
    if arguments and arguments[0] == "audit-only":
        parsed = parse_recovery_cli(arguments)
        audit = audit_candidate_groups(
            scoring, parsed.run_score, deep_validate=False
        )
        result = {
            "schema": RECONCILIATION_SCHEMA,
            "state": "pass",
            "mode": "audit-only",
            "committed_scoring": {
                "path": scoring.rel(SCORING_PATH),
                "sha256": EXPECTED_SCORING_SHA256,
            },
            "wrapper": {
                "path": scoring.rel(WRAPPER_PATH),
                "sha256": wrapper_sha,
            },
            "controller": {
                "path": scoring.rel(CONTROLLER_PATH),
                "sha256": controller_sha,
            },
            "audit": audit,
            "persistent_scientific_mutations": 0,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0

    if not arguments or arguments[0] not in {
        "init-schemas",
        "aggregate-scores",
    }:
        raise AggregateRecoveryError(
            "wrapper permits init-schemas, aggregate-scores, or audit-only only"
        )
    if arguments[0] == "init-schemas":
        scoring.main()
        return 0

    output_dir, score_paths = aggregate_arguments(arguments)
    verify_fresh_aggregate_output_dir(scoring, output_dir)
    # The committed write_numeric_outputs path immediately performs its own
    # deep score/Roofer/full-state validation both before and after the
    # idempotent attach.  This pre-audit is deliberately limited to the exact
    # round-trip drift so those large bound inputs are not hashed a third time.
    audit = audit_candidate_groups(scoring, score_paths, deep_validate=False)
    patched_attach = make_idempotent_attach(scoring, audit)
    original_attach = scoring.attach_dense_controls
    scoring.attach_dense_controls = patched_attach
    try:
        scoring.main()
    finally:
        scoring.attach_dense_controls = original_attach
    require_equal(
        patched_attach.calls,
        {run_id: 1 for run_id in EXPECTED_DRIFT_COUNTS},
        "aggregate idempotent attach call ledger",
    )
    outputs = verify_aggregate_outputs(scoring, output_dir, score_paths)
    receipt = {
        "schema": RECONCILIATION_SCHEMA,
        "state": "pass",
        "mode": "aggregate-scores",
        "reason": "marker_bound_dense_overlay_csv_roundtrip_idempotency",
        "committed_scoring": {
            "path": scoring.rel(SCORING_PATH),
            "sha256": EXPECTED_SCORING_SHA256,
        },
        "wrapper": {
            "path": scoring.rel(WRAPPER_PATH),
            "sha256": wrapper_sha,
        },
        "controller": {
            "path": scoring.rel(CONTROLLER_PATH),
            "sha256": controller_sha,
        },
        "patch_scope": "aggregate_attach_dense_controls_only",
        "row_action": "preserve_exact_marker_bound_candidate_rows",
        "candidate_scientific_scores_recomputed": False,
        "aggregate_outputs_computed": True,
        "committed_aggregate_deep_validation_executed": True,
        "training_started": 0,
        "roofer_started": 0,
        "score_started": 0,
        "audit": audit,
        "outputs": outputs,
    }
    receipt_path = output_dir / RECONCILIATION_NAME
    if receipt_path.exists():
        raise AggregateRecoveryError(
            f"aggregate reconciliation already exists: {receipt_path}"
        )
    scoring.atomic_json(receipt_path, receipt)
    scoring_manifest = bind_reconciliation_into_scoring_manifest(
        scoring, output_dir, receipt_path, receipt
    )
    receipt["receipt"] = {
        "path": scoring.rel(receipt_path),
        "sha256": sha256_file(receipt_path),
    }
    receipt["published_scoring_manifest_provenance"] = scoring_manifest
    print(json.dumps(receipt, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
