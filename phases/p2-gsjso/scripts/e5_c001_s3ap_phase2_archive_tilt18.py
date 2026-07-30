#!/usr/bin/env python3
"""Freeze and attest the completed conditional S3-A-prime tilt-18 wave.

The Phase-2 runner intentionally reuses ``runner/status.csv`` for the base and
tilt inventories.  The base wave must therefore already have been frozen by
the base-42 archiver.  This stdlib-only controller then validates the exact
conditional tilt inventory, its machine trigger and score lineage, all final
runtime artifacts, and the locked training-image runner dry-run before it
writes exactly three immutable files.  Runtime payloads are hashed in place;
logs, checkpoints, bindings, and configs are never copied.
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import io
import json
import math
from pathlib import Path
import sys
from typing import Any, Callable, Mapping

import e5_c001_s3ap_phase2_archive_base42 as base


REPO = Path(__file__).resolve().parents[3]
DEFAULT_RUN_ROOT = base.DEFAULT_RUN_ROOT
DEFAULT_JOBS = DEFAULT_RUN_ROOT / "tilt_jobs.csv"
DEFAULT_STATUS = base.DEFAULT_STATUS
DEFAULT_OUTPUT_DIR = base.DEFAULT_OUTPUT_DIR
DEFAULT_TILT_MANIFEST = DEFAULT_RUN_ROOT / "tilt_manifest.json"
DEFAULT_TRIGGER = DEFAULT_RUN_ROOT / "return_signal.json"
DEFAULT_BASE_JOBS = base.DEFAULT_JOBS
DEFAULT_BASE_MANIFEST = DEFAULT_RUN_ROOT / "manifest.json"
DEFAULT_BASE_COMPLETION = DEFAULT_OUTPUT_DIR / base.COMPLETION_NAME
DEFAULT_BASE_SNAPSHOT = DEFAULT_OUTPUT_DIR / base.SNAPSHOT_NAME
DEFAULT_BASE_ARTIFACTS = DEFAULT_OUTPUT_DIR / base.ARTIFACTS_NAME
DEFAULT_PHASE3_LOCK = Path(
    "phases/p2-gsjso/configs/e5_c001_s3ap_phase3_lock.json"
)
DEFAULT_PHASE3_ARCHIVE_LOCK = Path(
    "phases/p2-gsjso/configs/e5_c001_s3ap_phase3_archive_lock.json"
)
DEFAULT_PHASE3_ARCHIVE_CONTROLLER = Path(
    "phases/p2-gsjso/scripts/e5_c001_s3ap_phase3_archive.py"
)
DEFAULT_PHASE3_ARCHIVE_WRAPPER = Path(
    "phases/p2-gsjso/scripts/run_e5_c001_s3ap_phase3_archive.sh"
)
DEFAULT_PHASE3_ARCHIVE_TEST = Path(
    "phases/p2-gsjso/scripts/test_e5_c001_s3ap_phase3_archive.py"
)
DEFAULT_PHASE3_BASE42_ARCHIVE = Path(
    "phases/p2-gsjso/runs/20260715_e5_c001_s3ap_phase3_archives/base42"
)
DEFAULT_PHASE3_BASE42_MANIFEST = (
    DEFAULT_PHASE3_BASE42_ARCHIVE / "archive_manifest.json"
)
DEFAULT_PHASE3_BASE42_COMPLETION = (
    DEFAULT_PHASE3_BASE42_ARCHIVE / "COMPLETED.json"
)
SNAPSHOT_NAME = "status_tilt18.csv"
ARTIFACTS_NAME = "artifacts_tilt18.sha256"
COMPLETION_NAME = "completion_tilt18.json"
COMPLETION_SCHEMA = "jointbuildgs.s3ap.phase2.tilt18_completion.v1"
ARCHIVE_LAUNCHER = (
    "phases/p2-gsjso/scripts/run_e5_c001_s3ap_phase2_archive_tilt18.sh"
)
ARCHIVE_SCRIPT = (
    "phases/p2-gsjso/scripts/e5_c001_s3ap_phase2_archive_tilt18.py"
)
PHASE3_SCRIPT = "phases/p2-gsjso/scripts/e5_c001_s3ap_phase3.py"
TILT_GRID = (
    ("5.0", "p05"), ("-5.0", "m05"),
    ("10.0", "p10"), ("-10.0", "m10"),
    ("20.0", "p20"), ("-20.0", "m20"),
)
EXPECTED_TILT_DELTAS = [5.0, -5.0, 10.0, -10.0, 20.0, -20.0]
EXPECTED_NONZERO_HEIGHT_ROWS = 24
EXPECTED_TRIGGER_RULE = (
    "return_signal=true iff at least one completed A1 r1 nonzero-height row "
    "has abs(post_GS signed median error) < abs(P0 signed median error + "
    "injected delta); equality is false; no tolerance"
)
PHASE3_ARCHIVE_LOCK_SCHEMA = "jointbuildgs.s3ap.phase3.archive.lock.v1"
PHASE3_ARCHIVE_MANIFEST_SCHEMA = (
    "jointbuildgs.s3ap.phase3.wave_archive.v1"
)
PHASE3_ARCHIVE_COMPLETION_SCHEMA = (
    "jointbuildgs.s3ap.phase3.wave_archive_completion.v1"
)
PHASE3_WAVE_RECONCILIATION_SCHEMA = (
    "jointbuildgs.s3ap.phase3.wave_reconciliation.v1"
)
PHASE3_ARCHIVE_STATIC_SHA256 = {
    str(DEFAULT_PHASE3_ARCHIVE_LOCK): (
        "8f2b5daa0805a4052561c5f886d146e3006eb4d68d73647c105aedffa1075cc0"
    ),
    str(DEFAULT_PHASE3_ARCHIVE_CONTROLLER): (
        "4ec77f5d3759a8401be813aeddc812e89aa62e3657f626d3a84d490de448e45e"
    ),
    str(DEFAULT_PHASE3_ARCHIVE_WRAPPER): (
        "3c915893be55a582dc86f13d07651caee5d5220a7c417844dfbe57dfbdf808e3"
    ),
    str(DEFAULT_PHASE3_ARCHIVE_TEST): (
        "dda3607e2ccc8fcaba29d4de7510362ae3284ef24119967272628f468c174d77"
    ),
}
COMPLETION_OBSERVATIONAL_KEYS = base.COMPLETION_OBSERVATIONAL_KEYS

PERTURB_FIELDS = (
    "run_id", "building_id", "arm", "replicate", "delta_m",
    "score_status", "p0_signed_median_error_m",
    "perturbed_p0_signed_median_error_m",
    "perturbed_p0_abs_signed_median_error_m",
    "post_gs_signed_median_error_m",
    "post_gs_abs_signed_median_error_m", "signed_error_reduction_m",
    "post_minus_perturbed_seed_signed_m", "return_condition_met",
    "trigger_candidate", "trigger_rule",
)
PERTURB_CELL_FIELDS = (
    "run_id", "building_id", "arm", "replicate", "delta_m", "cell_ix",
    "cell_iy", "cell_center_x", "cell_center_y", "region",
    "p0_base_signed_error_m", "perturbed_p0_signed_error_m",
    "perturbed_p0_abs_error_m", "post_gs_point_count",
    "post_gs_signed_error_m", "post_gs_abs_error_m", "return_amount_m",
    "return_condition_met", "coverage_grid_m", "score_status",
)
SCORE_REQUIRED_FIELDS = frozenset({
    "run_id", "building_id", "arm", "replicate", "perturbation_type",
    "perturbation_value", "score_status", "checkpoint",
    "height_error_signed_median_m", "p0_height_error_signed_median_m",
})

JOB_CSV_FIELDS = base.JOB_CSV_FIELDS
STATUS_CSV_FIELDS = base.STATUS_CSV_FIELDS
STATUS_HASH_FIELDS = base.STATUS_HASH_FIELDS
PER_JOB_ARTIFACTS = base.PER_JOB_ARTIFACTS

STATIC_PROVENANCE = (
    base.DEFAULT_LOCK,
    Path(base.HOST_LAUNCHER),
    Path("phases/p2-gsjso/scripts/e5_c001_s3ap_phase2_prepare.py"),
    Path("phases/p2-gsjso/scripts/e5_c001_s3ap_phase2_runner.py"),
    Path(base.PREWARM_SCRIPT),
    Path("phases/p2-gsjso/scripts/e5_c001_s3ap_phase2_archive_base42.py"),
    Path(base.ARCHIVE_LAUNCHER),
    Path(ARCHIVE_SCRIPT),
    Path(ARCHIVE_LAUNCHER),
    Path(PHASE3_SCRIPT),
    DEFAULT_PHASE3_LOCK,
    DEFAULT_PHASE3_ARCHIVE_LOCK,
    DEFAULT_PHASE3_ARCHIVE_CONTROLLER,
    DEFAULT_PHASE3_ARCHIVE_WRAPPER,
    DEFAULT_PHASE3_ARCHIVE_TEST,
    Path("src/stage2/train.py"),
)

BASE_COMPLETION_KEYS = frozenset({
    "schema", "created_utc", "status", "wave", "job_count",
    "job_status_counts", "returncode_counts", "iterations", "jobs_csv",
    "jobs_csv_sha256", "source_status_csv", "source_status_csv_sha256",
    "status_snapshot", "status_snapshot_sha256", "artifacts_manifest",
    "artifacts_manifest_sha256", "artifacts_manifest_entry_count",
    "final_checkpoint_count", "total_final_checkpoint_bytes",
    "final_n_prim_min", "final_n_prim_max", "phase2_lock_sha256",
    "prepare_manifest_sha256", "prepare_git_head", "docker_image_id",
    "archive_tools_image", "archive_tools_image_id", "prewarm_manifest",
    "prewarm_manifest_sha256", "prewarm_status",
    "runner_dry_run_attestation", "runner_dry_run_attestation_sha256",
    "runner_dry_run_status_counts", "runner_dry_run_training_started",
    "archive_git_head", "archive_git_branch", "raw_logs_copied",
    "raw_checkpoints_copied", "artifact_policy",
})

ArchiveError = base.ArchiveError


def expected_job_grid() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for building in base.BUILDINGS:
        for tilt, slug in TILT_GRID:
            job_id = f"gs_e5_C001_s3ap_b{building}_a1_tilt_{slug}_r1"
            data_root = (
                "results/tum_transfer/e5_s3ap_phase2/prepared/"
                f"DEBY_LOD2_{building}"
            )
            out_dir = f"results/tum_transfer/e5_s3ap_phase2/runs/{job_id}"
            rows.append({
                "job_id": job_id,
                "job_class": "tilt",
                "building_id": building,
                "arm": "a1",
                "replicate": "r1",
                "random_seed": "2001",
                "height_delta_m": "0.0",
                "tilt_deg": tilt,
                "config_path": str(
                    DEFAULT_RUN_ROOT / "configs" / f"{job_id}.yaml"
                ),
                "data_root": data_root,
                "surface_seed_npz": (
                    f"{data_root}/seeds/"
                    f"DEBY_LOD2_{building}_a1a2_surface_seed.npz"
                ),
                "out_dir": out_dir,
                "final_checkpoint": f"{out_dir}/ckpt/final.pt",
                "iterations": "30000",
            })
    return rows


def validate_jobs(rows: list[dict[str, str]]) -> list[str]:
    if len(rows) != 18:
        raise ArchiveError(
            f"tilt_jobs.csv must contain exactly 18 rows, got {len(rows)}"
        )
    ids = [row.get("job_id", "") for row in rows]
    if any(not value for value in ids) or len(set(ids)) != 18:
        raise ArchiveError(
            "tilt_jobs.csv must contain 18 nonempty unique job IDs"
        )
    sequences = [row.get("sequence", "") for row in rows]
    if sequences != [str(value) for value in range(1, 19)]:
        raise ArchiveError(
            "tilt_jobs.csv sequence must be exactly 1..18 in row order"
        )
    locked_fields = (
        "job_id", "job_class", "building_id", "arm", "replicate",
        "random_seed", "height_delta_m", "tilt_deg", "config_path",
        "data_root", "surface_seed_npz", "out_dir", "final_checkpoint",
        "iterations",
    )
    for sequence, (row, expected) in enumerate(
        zip(rows, expected_job_grid()), 1
    ):
        for field in locked_fields:
            if row.get(field) != expected[field]:
                raise ArchiveError(
                    "tilt_jobs.csv locked tuple drift at sequence "
                    f"{sequence}: {field}={row.get(field)!r}, "
                    f"expected {expected[field]!r}"
                )
        if row.get("status") != "prepared":
            raise ArchiveError(
                f"{row['job_id']}: inventory status must be prepared"
            )
        for field in ("gt_used", "lod2_used", "als_used"):
            base.require_csv_false(row.get(field, ""), f"{row['job_id']}:{field}")
        for field in ("config_sha256", "surface_seed_sha256"):
            base.require_hex64(row.get(field, ""), f"{row['job_id']}:{field}")
    return ids


def validate_lock_contract(
    repo: Path,
    lock: Mapping[str, Any],
    status_path: Path,
) -> None:
    """Validate the shared base lock plus all conditional-tilt fields."""

    base.validate_lock_contract(
        repo,
        lock,
        base.resolve(repo, DEFAULT_RUN_ROOT),
        base.resolve(repo, DEFAULT_BASE_JOBS),
        status_path,
    )
    if lock.get("crs") != "EPSG:25832":
        raise ArchiveError("Phase-2 CRS must be EPSG:25832")
    training = lock.get("training")
    if not isinstance(training, Mapping):
        raise ArchiveError("Phase-2 training contract absent")
    if not base.json_exact_equal(
        training.get("tilt_perturbation_deg"), EXPECTED_TILT_DELTAS
    ):
        raise ArchiveError("Phase-2 tilt perturbation grid/order drift")
    if training.get("tilt_trigger_schema") != (
        "jointbuildgs.s3ap.return_signal.v1"
    ):
        raise ArchiveError("Phase-2 tilt trigger schema lock drift")

    run_rel = base.relative(repo, DEFAULT_RUN_ROOT)
    expected_outputs = {
        "tilt_inventory": f"{run_rel}/tilt_jobs.csv",
        "tilt_trigger": f"{run_rel}/return_signal.json",
        "tilt_prepare_manifest": f"{run_rel}/tilt_manifest.json",
        "tilt_prepare_progress": f"{run_rel}/tilt_progress.csv",
    }
    outputs = lock.get("outputs")
    if not isinstance(outputs, Mapping):
        raise ArchiveError("Phase-2 outputs contract absent")
    for field, expected in expected_outputs.items():
        if outputs.get(field) != expected:
            raise ArchiveError(
                f"Phase-2 output {field} drift: "
                f"{outputs.get(field)!r} != {expected!r}"
            )
    source = lock.get("tilt_score_source")
    expected_source = {
        "scores_csv": "docs/experiments/input-and-alignment/e5_c001_s3ap/tables/e5_c001_s3ap_phase3_scores.csv",
        "perturbation_csv": "docs/experiments/input-and-alignment/e5_c001_s3ap/tables/e5_c001_s3ap_perturbation.csv",
        "expected_nonzero_height_rows": EXPECTED_NONZERO_HEIGHT_ROWS,
        "require_evaluation_complete": True,
    }
    if not base.json_exact_equal(source, expected_source):
        raise ArchiveError("Phase-2 tilt score-source lock drift")


def parse_csv_required_fields(
    payload: bytes,
    role: str,
    required_fields: set[str] | frozenset[str],
) -> tuple[list[str], list[dict[str, str]]]:
    """Parse a CSV while rejecting duplicate/missing required columns."""

    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ArchiveError(f"{role} is not UTF-8") from error
    reader = csv.DictReader(io.StringIO(text))
    fields = reader.fieldnames
    if fields is None:
        raise ArchiveError(f"{role} has no header")
    if len(fields) != len(set(fields)):
        raise ArchiveError(f"{role} has duplicate header fields")
    missing = sorted(set(required_fields) - set(fields))
    if missing:
        raise ArchiveError(f"{role} misses required fields: {missing!r}")
    return fields, list(reader)


def finite_csv_float(value: Any, role: str) -> float:
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError) as error:
        raise ArchiveError(f"{role} must be finite, got {value!r}") from error
    if not math.isfinite(number):
        raise ArchiveError(f"{role} must be finite, got {value!r}")
    return number


def exact_csv_bool(value: Any, role: str) -> bool:
    if value == "True":
        return True
    if value == "False":
        return False
    raise ArchiveError(
        f"{role} must be exact CSV boolean True/False, got {value!r}"
    )


def exact_float(actual: float, expected: float, role: str) -> None:
    if actual != expected:
        raise ArchiveError(f"{role} drift: {actual!r} != {expected!r}")


def phase3_job_contract(
    jobs: list[dict[str, str]],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Return exact Phase-3 sorted score and perturbation job contracts."""

    def delta(job: Mapping[str, str]) -> float:
        return float(job["height_delta_m"])

    score_jobs = sorted(
        jobs,
        key=lambda job: (
            job["building_id"], job["arm"], job["replicate"],
            delta(job), job["job_id"],
        ),
    )
    perturb_jobs = [
        job for job in jobs
        if job["arm"] == "a1" and job["replicate"] == "r1"
        and job["job_class"] in {"base", "height"}
    ]
    perturb_jobs.sort(
        key=lambda job: (
            job["building_id"], delta(job), job["job_id"]
        )
    )
    nonzero = [job for job in perturb_jobs if delta(job) != 0.0]
    if len(score_jobs) != 42 or len(perturb_jobs) != 27 or len(nonzero) != 24:
        raise ArchiveError(
            "base inventory does not yield exact 42 score/27 perturb/24 "
            "nonzero-height contracts"
        )
    return score_jobs, perturb_jobs


def validate_score_source(
    repo: Path,
    path: Path,
    jobs: list[dict[str, str]],
    perturb_by_id: Mapping[str, Mapping[str, Any]],
) -> None:
    payload = base.read_required(path, "Phase-3 source scores CSV")
    _, rows = parse_csv_required_fields(
        payload, "Phase-3 source scores CSV", SCORE_REQUIRED_FIELDS
    )
    score_jobs, _ = phase3_job_contract(jobs)
    if len(rows) != 42:
        raise ArchiveError(
            f"Phase-3 source scores must contain exactly 42 rows, got {len(rows)}"
        )
    actual_ids = [row.get("run_id", "") for row in rows]
    expected_ids = [job["job_id"] for job in score_jobs]
    if actual_ids != expected_ids or len(set(actual_ids)) != 42:
        raise ArchiveError(
            "Phase-3 source score run IDs/order differ from exact base42 grid"
        )
    by_id: dict[str, dict[str, str]] = {}
    for row, job in zip(rows, score_jobs):
        run_id = job["job_id"]
        expected_type = "height" if job["job_class"] == "height" else "none"
        expected_value = float(job["height_delta_m"])
        expected_values = {
            "building_id": f"DEBY_LOD2_{job['building_id']}",
            "arm": job["arm"],
            "replicate": job["replicate"],
            "perturbation_type": expected_type,
            "checkpoint": job["final_checkpoint"],
        }
        for field, expected in expected_values.items():
            if row.get(field) != expected:
                raise ArchiveError(
                    f"source score {run_id}:{field} drift: "
                    f"{row.get(field)!r} != {expected!r}"
                )
        exact_float(
            finite_csv_float(
                row.get("perturbation_value"),
                f"source score {run_id}:perturbation_value",
            ),
            expected_value,
            f"source score {run_id}:perturbation_value",
        )
        by_id[run_id] = row

    for run_id, perturb in perturb_by_id.items():
        score = by_id.get(run_id)
        if score is None:
            raise ArchiveError(f"source score misses perturbation run {run_id}")
        if score.get("score_status") != perturb["score_status"]:
            raise ArchiveError(f"source score/perturb status drift for {run_id}")
        if float(perturb["delta_m"]) == 0.0:
            continue
        score_post = finite_csv_float(
            score.get("height_error_signed_median_m"),
            f"source score {run_id}:height_error_signed_median_m",
        )
        score_p0 = finite_csv_float(
            score.get("p0_height_error_signed_median_m"),
            f"source score {run_id}:p0_height_error_signed_median_m",
        )
        exact_float(
            score_post,
            float(perturb["post"]),
            f"source score/perturb post {run_id}",
        )
        exact_float(
            score_p0,
            float(perturb["p0"]),
            f"source score/perturb P0 {run_id}",
        )


def validate_cell_source(
    path: Path,
    perturb_by_id: Mapping[str, Mapping[str, Any]],
) -> None:
    rows = base.parse_csv_bytes(
        base.read_required(path, "Phase-3 perturbation cells CSV"),
        "Phase-3 perturbation cells CSV",
        PERTURB_CELL_FIELDS,
    )
    if not rows:
        raise ArchiveError("Phase-3 perturbation cells CSV is empty")
    seen: set[tuple[str, int, int]] = set()
    seen_runs: set[str] = set()
    order: list[tuple[str, float, int, int]] = []
    for row in rows:
        run_id = row.get("run_id", "")
        perturb = perturb_by_id.get(run_id)
        if perturb is None:
            raise ArchiveError(
                f"perturbation cells contain unexpected run_id {run_id!r}"
            )
        expected_values = {
            "building_id": f"DEBY_LOD2_{perturb['building_id']}",
            "arm": "a1",
            "replicate": "r1",
            "score_status": "complete",
        }
        for field, expected in expected_values.items():
            if row.get(field) != expected:
                raise ArchiveError(
                    f"perturbation cell {run_id}:{field} drift"
                )
        delta = finite_csv_float(row.get("delta_m"), f"cell {run_id}:delta_m")
        exact_float(delta, float(perturb["delta_m"]), f"cell {run_id}:delta_m")
        grid = finite_csv_float(
            row.get("coverage_grid_m"), f"cell {run_id}:coverage_grid_m"
        )
        exact_float(grid, 0.5, f"cell {run_id}:coverage_grid_m")
        try:
            ix_float = finite_csv_float(row.get("cell_ix"), f"cell {run_id}:cell_ix")
            iy_float = finite_csv_float(row.get("cell_iy"), f"cell {run_id}:cell_iy")
            ix, iy = int(ix_float), int(iy_float)
        except (TypeError, ValueError) as error:
            raise ArchiveError(f"cell {run_id} indices are invalid") from error
        if float(ix) != ix_float or float(iy) != iy_float:
            raise ArchiveError(f"cell {run_id} indices must be integers")
        center_x = finite_csv_float(
            row.get("cell_center_x"), f"cell {run_id}:cell_center_x"
        )
        center_y = finite_csv_float(
            row.get("cell_center_y"), f"cell {run_id}:cell_center_y"
        )
        if not (
            ix * grid <= center_x <= (ix + 1) * grid
            and iy * grid <= center_y <= (iy + 1) * grid
        ):
            raise ArchiveError(
                f"cell {run_id} representative lies outside its grid cell"
            )
        region = row.get("region")
        if region not in {"edge", "interior"}:
            raise ArchiveError(
                f"cell {run_id}:region must be exact edge/interior"
            )

        p0 = finite_csv_float(
            row.get("p0_base_signed_error_m"),
            f"cell {run_id}:p0_base_signed_error_m",
        )
        perturbed = finite_csv_float(
            row.get("perturbed_p0_signed_error_m"),
            f"cell {run_id}:perturbed_p0_signed_error_m",
        )
        perturbed_abs = finite_csv_float(
            row.get("perturbed_p0_abs_error_m"),
            f"cell {run_id}:perturbed_p0_abs_error_m",
        )
        exact_float(
            perturbed, p0 + delta, f"cell {run_id}:P0+delta"
        )
        exact_float(
            perturbed_abs, abs(perturbed),
            f"cell {run_id}:perturbed absolute value",
        )
        count_float = finite_csv_float(
            row.get("post_gs_point_count"),
            f"cell {run_id}:post_gs_point_count",
        )
        count = int(count_float)
        if count_float != float(count) or count < 0:
            raise ArchiveError(
                f"cell {run_id}:post_gs_point_count must be nonnegative integer"
            )
        return_condition = exact_csv_bool(
            row.get("return_condition_met"),
            f"cell {run_id}:return_condition_met",
        )
        post_fields = (
            "post_gs_signed_error_m", "post_gs_abs_error_m",
            "return_amount_m",
        )
        if count == 0:
            if any(row.get(field, "") != "" for field in post_fields):
                raise ArchiveError(
                    f"cell {run_id}:zero post count must have empty post fields"
                )
            if return_condition:
                raise ArchiveError(
                    f"cell {run_id}:zero post count cannot satisfy return"
                )
        else:
            post = finite_csv_float(
                row.get("post_gs_signed_error_m"),
                f"cell {run_id}:post_gs_signed_error_m",
            )
            post_abs = finite_csv_float(
                row.get("post_gs_abs_error_m"),
                f"cell {run_id}:post_gs_abs_error_m",
            )
            reduction = finite_csv_float(
                row.get("return_amount_m"),
                f"cell {run_id}:return_amount_m",
            )
            exact_float(
                post_abs, abs(post), f"cell {run_id}:post absolute value"
            )
            exact_float(
                reduction, perturbed_abs - post_abs,
                f"cell {run_id}:return amount",
            )
            expected_return = bool(
                delta != 0.0 and abs(post) < abs(perturbed)
            )
            if return_condition != expected_return:
                raise ArchiveError(
                    f"cell {run_id}:return condition formula drift"
                )
        key = (run_id, ix, iy)
        if key in seen:
            raise ArchiveError(f"duplicate perturbation cell: {key!r}")
        seen.add(key)
        order.append((str(perturb["building_id"]), delta, ix, iy))
        seen_runs.add(run_id)
    if order != sorted(order):
        raise ArchiveError("perturbation cell rows violate locked Phase-3 order")
    if seen_runs != set(perturb_by_id):
        raise ArchiveError(
            "perturbation cells do not cover every exact A1-r1 perturbation run"
        )


def validate_phase3_rule_contract(
    repo: Path,
    artifacts: dict[str, str],
) -> tuple[dict[str, Any], str]:
    lock_path = base.resolve(repo, DEFAULT_PHASE3_LOCK)
    phase3 = base.load_json_object(lock_path, "Phase-3 lock")
    if phase3.get("schema") != "jointbuildgs.s3ap.phase3.lock.v1":
        raise ArchiveError("Phase-3 lock schema drift")
    if phase3.get("training_runs_allowed") != 0:
        raise ArchiveError("Phase-3 lock permits training")
    base.require_json_false(
        phase3.get("new_mast3r_inference_allowed"),
        "Phase-3 new_mast3r_inference_allowed",
    )
    perturbation = phase3.get("perturbation")
    if not isinstance(perturbation, Mapping):
        raise ArchiveError("Phase-3 perturbation contract absent")
    rule = perturbation.get("trigger_rule")
    if rule != EXPECTED_TRIGGER_RULE:
        raise ArchiveError(
            "Phase-3 immutable trigger-rule text/formula drift"
        )
    if not base.json_exact_equal(
        perturbation.get("tilt_deltas_deg"), EXPECTED_TILT_DELTAS
    ):
        raise ArchiveError("Phase-3 tilt grid/order drift")
    base.add_artifact(repo, artifacts, lock_path)
    base.add_artifact(repo, artifacts, PHASE3_SCRIPT)
    return phase3, str(rule)


def _load_phase3_archive_controller(repo: Path) -> Any:
    """Load the exact repository-bound verifier used to make the root archive."""

    controller_path = base.resolve(repo, DEFAULT_PHASE3_ARCHIVE_CONTROLLER)
    module_name = (
        "_s3ap_phase3_archive_contract_"
        + base.sha256_bytes(str(controller_path.resolve()).encode("utf-8"))[:16]
    )
    spec = importlib.util.spec_from_file_location(module_name, controller_path)
    if spec is None or spec.loader is None:
        raise ArchiveError(
            f"cannot load Phase-3 archive controller: {controller_path}"
        )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as error:
        sys.modules.pop(module_name, None)
        raise ArchiveError(
            f"cannot execute Phase-3 archive controller: {controller_path}"
        ) from error
    return module


def _phase3_archive_row_current(
    *,
    repo: Path,
    archive_root: Path,
    row: Mapping[str, Any],
    artifacts: dict[str, str],
    require_current: bool,
    role: str,
) -> str:
    """Cross-check one archive mapping row and add its immutable bytes."""

    source_text = str(row.get("source_path", ""))
    if not source_text:
        raise ArchiveError(f"Phase-3 base42 {role} source path is empty")
    try:
        size = int(row.get("size_bytes", -1))
    except (TypeError, ValueError) as error:
        raise ArchiveError(
            f"Phase-3 base42 {role} size is invalid"
        ) from error
    if size < 0:
        raise ArchiveError(f"Phase-3 base42 {role} size is negative")
    expected_hash = str(row.get("sha256", ""))
    base.require_hex64(expected_hash, f"Phase-3 base42 {role} hash")
    if require_current:
        current = base.resolve(repo, source_text)
        if not current.is_file() or current.stat().st_size != size:
            raise ArchiveError(
                f"Phase-3 base42 {role} current source size drift: "
                f"{source_text}"
            )
        base.add_artifact(
            repo, artifacts, current, expected_hash=expected_hash
        )
    disposition = row.get("disposition")
    if disposition == "copied":
        archive_text = str(row.get("archive_path", ""))
        expected_archive = f"snapshot/{source_text}"
        if archive_text != expected_archive:
            raise ArchiveError(
                f"Phase-3 base42 {role} archive path drift"
            )
        archived = archive_root / archive_text
        if not archived.is_file() or archived.stat().st_size != size:
            raise ArchiveError(
                f"Phase-3 base42 {role} archived source size drift"
            )
        base.add_artifact(
            repo, artifacts, archived, expected_hash=expected_hash
        )
    elif disposition != "sha256_only":
        raise ArchiveError(
            f"Phase-3 base42 {role} disposition is invalid"
        )
    return expected_hash


def validate_phase3_base42_archive(
    *,
    repo: Path,
    phase3: Mapping[str, Any],
    trigger: Mapping[str, Any],
    artifacts: dict[str, str],
) -> dict[str, Any]:
    """Bind the prior Phase-3 base42 archive as an external immutable root."""

    lock_path = base.resolve(repo, DEFAULT_PHASE3_ARCHIVE_LOCK)
    archive_lock = base.load_json_object(
        lock_path, "Phase-3 archive lock"
    )
    if archive_lock.get("schema") != PHASE3_ARCHIVE_LOCK_SCHEMA:
        raise ArchiveError("Phase-3 archive lock schema drift")
    exact_lock_values = {
        "archive_root": str(DEFAULT_PHASE3_BASE42_ARCHIVE.parent),
        "phase3_lock": str(DEFAULT_PHASE3_LOCK),
        "phase3_script": PHASE3_SCRIPT,
        "phase3_aggregate_schema": "jointbuildgs.s3ap.phase3.aggregate.v2",
    }
    for field, expected in exact_lock_values.items():
        if archive_lock.get(field) != expected:
            raise ArchiveError(
                f"Phase-3 archive lock {field} drift: "
                f"{archive_lock.get(field)!r} != {expected!r}"
            )
    schemas = archive_lock.get("schemas")
    if not isinstance(schemas, Mapping):
        raise ArchiveError("Phase-3 archive schemas are absent")
    expected_schemas = {
        "archive_manifest": PHASE3_ARCHIVE_MANIFEST_SCHEMA,
        "archive_completion": PHASE3_ARCHIVE_COMPLETION_SCHEMA,
        "wave_reconciliation": PHASE3_WAVE_RECONCILIATION_SCHEMA,
    }
    for field, expected in expected_schemas.items():
        if schemas.get(field) != expected:
            raise ArchiveError(f"Phase-3 archive {field} schema drift")
    policy = archive_lock.get("policy")
    if not isinstance(policy, Mapping):
        raise ArchiveError("Phase-3 archive policy is absent")
    policy_expected = {
        "copy_prefix": "snapshot",
        "training_runs_started": 0,
        "new_mast3r_inference_runs": 0,
        "interpretation_or_verdict": None,
        "raw_gt_copy_allowed": False,
        "overwrite_existing_different_bytes": False,
    }
    for field, expected in policy_expected.items():
        if not base.json_exact_equal(policy.get(field), expected):
            raise ArchiveError(f"Phase-3 archive policy {field} drift")
    waves = archive_lock.get("waves")
    base42_spec = waves.get("base42") if isinstance(waves, Mapping) else None
    expected_base42_spec = {
        "total_jobs": 42,
        "base_jobs": 18,
        "height_nonzero_jobs": 24,
        "tilt_jobs": 0,
        "complete_scores": 42,
        "perturbation_rows": 27,
        "nonzero_height_rows": 24,
        "require_return_signal": None,
    }
    if not base.json_exact_equal(base42_spec, expected_base42_spec):
        raise ArchiveError("Phase-3 archive base42 wave contract drift")
    containers = archive_lock.get("containers")
    if (
        not isinstance(containers, Mapping)
        or containers.get("tools_image") != base.TOOLS_IMAGE
        or containers.get("tools_image_id") != base.TOOLS_IMAGE_ID
    ):
        raise ArchiveError("Phase-3 archive tools image contract drift")

    outputs = phase3.get("outputs")
    if not isinstance(outputs, Mapping):
        raise ArchiveError("Phase-3 output contract is absent")
    expected_outputs = {
        "scores": str(outputs.get("scores_csv", "")),
        "perturbation": str(outputs.get("perturbation_csv", "")),
        "cells": str(outputs.get("perturbation_cells_csv", "")),
        "trigger": str(outputs.get("tilt_trigger", "")),
    }
    exact_core_paths = {
        "scores": "docs/experiments/input-and-alignment/e5_c001_s3ap/tables/e5_c001_s3ap_phase3_scores.csv",
        "perturbation": "docs/experiments/input-and-alignment/e5_c001_s3ap/tables/e5_c001_s3ap_perturbation.csv",
        "cells": "docs/experiments/input-and-alignment/e5_c001_s3ap/tables/e5_c001_s3ap_perturbation_cells.csv",
        "trigger": str(DEFAULT_TRIGGER),
    }
    if expected_outputs != exact_core_paths:
        raise ArchiveError("Phase-3 core output paths drift")
    if trigger.get("scores_csv") != expected_outputs["scores"]:
        raise ArchiveError("Phase-3 trigger score path/archive path drift")
    if trigger.get("perturbation_csv") != expected_outputs["perturbation"]:
        raise ArchiveError("Phase-3 trigger perturbation path/archive path drift")
    if trigger.get("perturbation_cells_csv") != expected_outputs["cells"]:
        raise ArchiveError("Phase-3 trigger cell path/archive path drift")
    if trigger.get("return_signal") is not True:
        raise ArchiveError("tilt18 requires true archived base42 return signal")

    controller_sources = archive_lock.get("archive_controller_sources")
    expected_controller_sources = [
        str(DEFAULT_PHASE3_ARCHIVE_LOCK),
        str(DEFAULT_PHASE3_ARCHIVE_CONTROLLER),
        str(DEFAULT_PHASE3_ARCHIVE_WRAPPER),
        str(DEFAULT_PHASE3_ARCHIVE_TEST),
    ]
    if controller_sources != expected_controller_sources:
        raise ArchiveError("Phase-3 archive controller source list drift")
    for source_text, expected_hash in PHASE3_ARCHIVE_STATIC_SHA256.items():
        base.add_artifact(
            repo,
            artifacts,
            source_text,
            expected_hash=expected_hash,
        )
    controller = _load_phase3_archive_controller(repo)
    archive_root = base.resolve(repo, DEFAULT_PHASE3_BASE42_ARCHIVE)
    if archive_root.resolve() != (
        base.resolve(repo, archive_lock["archive_root"]) / "base42"
    ).resolve():
        raise ArchiveError("Phase-3 base42 archive path is not canonical")
    try:
        verified = controller.verify_archive_directory(
            archive_root,
            False,
            repo,
            expected_wave="base42",
            archive=archive_lock,
        )
    except Exception as error:
        if isinstance(error, ArchiveError):
            raise
        raise ArchiveError(
            f"Phase-3 base42 archive verification failed: {error}"
        ) from error

    manifest_path = base.resolve(repo, DEFAULT_PHASE3_BASE42_MANIFEST)
    completion_path = base.resolve(repo, DEFAULT_PHASE3_BASE42_COMPLETION)
    manifest = base.load_json_object(
        manifest_path, "Phase-3 base42 archive manifest"
    )
    completion = base.load_json_object(
        completion_path, "Phase-3 base42 archive completion"
    )
    if not base.json_exact_equal(manifest, verified):
        raise ArchiveError(
            "Phase-3 base42 archive verifier/manifest bytes disagree"
        )
    completion_keys = {
        "schema", "status", "created_utc", "wave",
        "archive_manifest_sha256", "source_mapping_digest",
        "archive_payload_digest", "copied_file_count",
        "sha256_only_file_count",
    }
    if set(completion) != completion_keys:
        raise ArchiveError("Phase-3 base42 completion key-set drift")
    if (
        completion.get("schema") != PHASE3_ARCHIVE_COMPLETION_SCHEMA
        or completion.get("status") != "complete"
        or completion.get("wave") != "base42"
    ):
        raise ArchiveError("Phase-3 base42 completion contract drift")
    manifest_hash = base.add_artifact(repo, artifacts, manifest_path)
    completion_hash = base.add_artifact(repo, artifacts, completion_path)
    if completion.get("archive_manifest_sha256") != manifest_hash:
        raise ArchiveError("Phase-3 base42 completion manifest hash drift")

    mapping = manifest.get("source_mapping")
    if not isinstance(mapping, list) or not mapping:
        raise ArchiveError("Phase-3 base42 source mapping is empty")
    mapping_lookup = {
        str(row.get("source_path", "")): row
        for row in mapping if isinstance(row, Mapping)
    }
    if len(mapping_lookup) != len(mapping):
        raise ArchiveError("Phase-3 base42 source mapping is malformed")
    # Re-hash every copied byte again at the final write boundary.  SHA-only
    # runtime payloads are not an input to the tilt trigger; their immutable
    # path/size/hash records remain bound by the archive manifest itself.
    for source_text, mapped in mapping_lookup.items():
        if mapped.get("disposition") == "copied":
            _phase3_archive_row_current(
                repo=repo,
                archive_root=archive_root,
                row=mapped,
                artifacts=artifacts,
                require_current=False,
                role=f"copied archive source {source_text}",
            )
    reconciliation = manifest.get("wave_reconciliation")
    if not isinstance(reconciliation, Mapping):
        raise ArchiveError("Phase-3 base42 reconciliation is absent")
    expected_reconciliation_keys = {
        "schema", "wave", "inventory_job_contract_digest",
        "phase3_aggregate_manifest", "phase3_aggregate_manifest_sha256",
        "source_mapping_digest", "complete_score_count",
        "nonzero_height_rows", "evaluation_complete", "return_signal",
        "outputs",
    }
    if set(reconciliation) != expected_reconciliation_keys:
        raise ArchiveError("Phase-3 base42 reconciliation key-set drift")
    if (
        reconciliation.get("schema") != PHASE3_WAVE_RECONCILIATION_SCHEMA
        or reconciliation.get("wave") != "base42"
        or reconciliation.get("complete_score_count") != 42
        or reconciliation.get("nonzero_height_rows") != 24
        or reconciliation.get("evaluation_complete") is not True
        or reconciliation.get("return_signal") is not True
    ):
        raise ArchiveError("Phase-3 base42 reconciliation values drift")
    inventory_digest = str(
        reconciliation.get("inventory_job_contract_digest", "")
    )
    base.require_hex64(
        inventory_digest,
        "Phase-3 base42 inventory job contract digest",
    )
    if reconciliation.get("source_mapping_digest") != manifest.get(
        "source_mapping_digest"
    ):
        raise ArchiveError("Phase-3 base42 reconciliation mapping drift")
    reconciled_outputs = reconciliation.get("outputs")
    if (
        not isinstance(reconciled_outputs, Mapping)
        or set(reconciled_outputs) != set(expected_outputs)
    ):
        raise ArchiveError("Phase-3 base42 reconciliation outputs drift")
    for label, expected_source in expected_outputs.items():
        output = reconciled_outputs[label]
        if not isinstance(output, Mapping):
            raise ArchiveError(
                f"Phase-3 base42 reconciliation output malformed: {label}"
            )
        mapped = mapping_lookup.get(expected_source)
        if mapped is None or mapped.get("disposition") != "copied":
            raise ArchiveError(
                f"Phase-3 base42 core source is not copied: {label}"
            )
        expected_output = {
            "source_path": expected_source,
            "archive_path": mapped.get("archive_path"),
            "size_bytes": mapped.get("size_bytes"),
            "sha256": mapped.get("sha256"),
        }
        if not base.json_exact_equal(output, expected_output):
            raise ArchiveError(
                f"Phase-3 base42 reconciliation output drift: {label}"
            )
        actual_hash = _phase3_archive_row_current(
            repo=repo,
            archive_root=archive_root,
            row=mapped,
            artifacts=artifacts,
            require_current=True,
            role=f"core {label}",
        )
        trigger_hash_field = {
            "scores": "source_score_sha256",
            "perturbation": "source_perturbation_sha256",
            "cells": "source_perturbation_cells_sha256",
            "trigger": None,
        }[label]
        if (
            trigger_hash_field is not None
            and trigger.get(trigger_hash_field) != actual_hash
        ):
            raise ArchiveError(
                f"Phase-3 base42 trigger/archive hash drift: {label}"
            )

    static_expectations = {
        str(DEFAULT_PHASE3_LOCK): "copied",
        PHASE3_SCRIPT: "copied",
        str(DEFAULT_PHASE3_ARCHIVE_LOCK): "copied",
        str(DEFAULT_PHASE3_ARCHIVE_CONTROLLER): "sha256_only",
        str(DEFAULT_PHASE3_ARCHIVE_WRAPPER): "sha256_only",
        str(DEFAULT_PHASE3_ARCHIVE_TEST): "sha256_only",
    }
    for source_text, disposition in static_expectations.items():
        mapped = mapping_lookup.get(source_text)
        if mapped is None or mapped.get("disposition") != disposition:
            raise ArchiveError(
                f"Phase-3 base42 static provenance is unbound: {source_text}"
            )
        _phase3_archive_row_current(
            repo=repo,
            archive_root=archive_root,
            row=mapped,
            artifacts=artifacts,
            require_current=True,
            role=f"static {source_text}",
        )

    aggregate_source = str(
        reconciliation.get("phase3_aggregate_manifest", "")
    )
    aggregate_hash = str(
        reconciliation.get("phase3_aggregate_manifest_sha256", "")
    )
    base.require_hex64(
        aggregate_hash, "Phase-3 base42 aggregate manifest hash"
    )
    aggregate_row = mapping_lookup.get(aggregate_source)
    if (
        aggregate_row is None
        or aggregate_row.get("disposition") != "copied"
        or aggregate_row.get("sha256") != aggregate_hash
    ):
        raise ArchiveError("Phase-3 base42 aggregate archive binding drift")
    _phase3_archive_row_current(
        repo=repo,
        archive_root=archive_root,
        row=aggregate_row,
        artifacts=artifacts,
        require_current=False,
        role="aggregate manifest",
    )
    return {
        "archive": base.relative(repo, archive_root),
        "manifest": base.relative(repo, manifest_path),
        "manifest_sha256": manifest_hash,
        "completion": base.relative(repo, completion_path),
        "completion_sha256": completion_hash,
        "source_mapping_digest": manifest["source_mapping_digest"],
        "archive_payload_digest": manifest["archive_payload_digest"],
        "inventory_job_contract_digest": inventory_digest,
        "aggregate_manifest": aggregate_source,
        "aggregate_manifest_sha256": aggregate_hash,
    }


def validate_trigger_contract(
    repo: Path,
    trigger_path: Path,
    trigger: Mapping[str, Any],
    lock: Mapping[str, Any],
    base_jobs: list[dict[str, str]],
    artifacts: dict[str, str],
) -> dict[str, str]:
    source = lock["tilt_score_source"]
    phase3, authoritative_rule = validate_phase3_rule_contract(repo, artifacts)
    expected_values: dict[str, Any] = {
        "schema": lock["training"]["tilt_trigger_schema"],
        "evaluation_complete": True,
        "expected_nonzero_height_rows": EXPECTED_NONZERO_HEIGHT_ROWS,
        "observed_nonzero_height_rows": EXPECTED_NONZERO_HEIGHT_ROWS,
        "complete_nonzero_height_rows": EXPECTED_NONZERO_HEIGHT_ROWS,
        "scores_csv": source["scores_csv"],
        "perturbation_csv": source["perturbation_csv"],
        "perturbation_cells_csv": "docs/experiments/input-and-alignment/e5_c001_s3ap/tables/e5_c001_s3ap_perturbation_cells.csv",
        "tilt_deltas_deg": EXPECTED_TILT_DELTAS,
        "equality_counts_as_return": False,
        "numeric_tolerance": None,
    }
    for field, expected in expected_values.items():
        actual = trigger.get(field)
        if not base.json_exact_equal(actual, expected):
            raise ArchiveError(
                f"conditional tilt trigger {field} drift: "
                f"{actual!r} != {expected!r}"
            )

    bound: dict[str, str] = {}
    source_fields = (
        ("scores_csv", "source_score_sha256"),
        ("perturbation_csv", "source_perturbation_sha256"),
        ("perturbation_cells_csv", "source_perturbation_cells_sha256"),
    )
    for path_field, hash_field in source_fields:
        expected_hash = trigger.get(hash_field)
        base.require_hex64(expected_hash, f"tilt trigger:{hash_field}")
        actual = base.add_artifact(
            repo,
            artifacts,
            trigger[path_field],
            expected_hash=str(expected_hash),
        )
        bound[hash_field] = actual

    _, expected_perturb_jobs = phase3_job_contract(base_jobs)
    perturb_path = base.resolve(repo, trigger["perturbation_csv"])
    perturb_rows = base.parse_csv_bytes(
        base.read_required(perturb_path, "Phase-3 perturbation CSV"),
        "Phase-3 perturbation CSV",
        PERTURB_FIELDS,
    )
    if len(perturb_rows) != 27:
        raise ArchiveError(
            "Phase-3 perturbation CSV must contain exact 27 rows "
            f"(3 zero + 24 nonzero), got {len(perturb_rows)}"
        )
    actual_ids = [row.get("run_id", "") for row in perturb_rows]
    expected_ids = [job["job_id"] for job in expected_perturb_jobs]
    if actual_ids != expected_ids or len(set(actual_ids)) != 27:
        raise ArchiveError(
            "Phase-3 perturbation run IDs/order differ from base42 A1-r1 grid"
        )

    rule = trigger.get("rule")
    if rule != authoritative_rule:
        raise ArchiveError(
            "tilt trigger rule differs from immutable Phase-3 contract"
        )
    expected_candidates: list[dict[str, Any]] = []
    perturb_by_id: dict[str, dict[str, Any]] = {}
    for row, job in zip(perturb_rows, expected_perturb_jobs):
        run_id = job["job_id"]
        expected_delta = float(job["height_delta_m"])
        expected_values = {
            "building_id": f"DEBY_LOD2_{job['building_id']}",
            "arm": "a1",
            "replicate": "r1",
            "trigger_rule": rule,
        }
        for field, expected in expected_values.items():
            if row.get(field) != expected:
                raise ArchiveError(
                    f"perturbation source {run_id}:{field} drift: "
                    f"{row.get(field)!r} != {expected!r}"
                )
        delta = finite_csv_float(
            row.get("delta_m"), f"perturbation source {run_id}:delta_m"
        )
        exact_float(delta, expected_delta, f"perturbation source {run_id}:delta_m")
        score_status = row.get("score_status", "")
        if score_status != "complete":
            raise ArchiveError(
                f"perturbation source {run_id}:score_status must be complete"
            )
        return_condition = exact_csv_bool(
            row.get("return_condition_met"),
            f"perturbation source {run_id}:return_condition_met",
        )
        trigger_candidate = exact_csv_bool(
            row.get("trigger_candidate"),
            f"perturbation source {run_id}:trigger_candidate",
        )
        expected_candidate = bool(delta != 0.0 and score_status == "complete")
        if trigger_candidate != expected_candidate:
            raise ArchiveError(
                f"perturbation source {run_id}:trigger_candidate formula drift"
            )
        record: dict[str, Any] = {
            "building_id": job["building_id"],
            "delta_m": delta,
            "score_status": score_status,
            "candidate": expected_candidate,
        }
        if delta == 0.0:
            if return_condition:
                raise ArchiveError(
                    f"zero-height perturbation {run_id} cannot return true"
                )
        p0 = finite_csv_float(
            row.get("p0_signed_median_error_m"),
            f"perturbation source {run_id}:p0_signed",
        )
        perturbed = finite_csv_float(
            row.get("perturbed_p0_signed_median_error_m"),
            f"perturbation source {run_id}:perturbed_p0_signed",
        )
        perturbed_abs = finite_csv_float(
            row.get("perturbed_p0_abs_signed_median_error_m"),
            f"perturbation source {run_id}:perturbed_p0_abs",
        )
        post = finite_csv_float(
            row.get("post_gs_signed_median_error_m"),
            f"perturbation source {run_id}:post_gs_signed",
        )
        post_abs = finite_csv_float(
            row.get("post_gs_abs_signed_median_error_m"),
            f"perturbation source {run_id}:post_gs_abs",
        )
        reduction = finite_csv_float(
            row.get("signed_error_reduction_m"),
            f"perturbation source {run_id}:signed_error_reduction",
        )
        post_minus_seed = finite_csv_float(
            row.get("post_minus_perturbed_seed_signed_m"),
            f"perturbation source {run_id}:post_minus_seed",
        )
        exact_float(
            perturbed, p0 + delta,
            f"perturbation source {run_id}:P0+delta",
        )
        exact_float(
            perturbed_abs, abs(perturbed),
            f"perturbation source {run_id}:perturbed abs",
        )
        exact_float(
            post_abs, abs(post),
            f"perturbation source {run_id}:post abs",
        )
        exact_float(
            reduction, abs(perturbed) - abs(post),
            f"perturbation source {run_id}:reduction",
        )
        exact_float(
            post_minus_seed, post - perturbed,
            f"perturbation source {run_id}:post minus seed",
        )
        condition = bool(abs(post) < abs(perturbed))
        if return_condition != condition:
            raise ArchiveError(
                f"perturbation source {run_id}:return condition formula drift"
            )
        if delta != 0.0:
            candidate = {
                "run_id": run_id,
                "building_id": f"DEBY_LOD2_{job['building_id']}",
                "delta_m": delta,
                "post_gs_abs_signed_median_error_m": abs(post),
                "perturbed_p0_abs_signed_median_error_m": abs(perturbed),
                "condition_met": condition,
            }
            expected_candidates.append(candidate)
        record.update({
            "p0": p0,
            "perturbed": perturbed,
            "post": post,
            "condition": condition,
        })
        perturb_by_id[run_id] = record

    if len(expected_candidates) != EXPECTED_NONZERO_HEIGHT_ROWS:
        raise ArchiveError("reconstructed trigger candidate count is not 24")
    expected_qualifying = [
        candidate for candidate in expected_candidates
        if candidate["condition_met"]
    ]
    expected_signal = bool(expected_qualifying)
    for field in ("raw_return_signal", "return_signal"):
        if not base.json_exact_equal(trigger.get(field), expected_signal):
            raise ArchiveError(
                f"tilt trigger {field} differs from reconstructed candidates"
            )
    base.require_json_int(
        trigger.get("candidate_count"), len(expected_candidates),
        "tilt trigger candidate_count",
    )
    base.require_json_int(
        trigger.get("qualifying_count"), len(expected_qualifying),
        "tilt trigger qualifying_count",
    )
    candidates = trigger.get("candidates")
    qualifying = trigger.get("qualifying")
    if not base.json_exact_equal(candidates, expected_candidates):
        raise ArchiveError(
            "tilt trigger candidates schema/order/values differ from source CSV"
        )
    if not base.json_exact_equal(qualifying, expected_qualifying):
        raise ArchiveError(
            "tilt trigger qualifying rows differ from true source candidates"
        )
    if not expected_signal:
        raise ArchiveError(
            "conditional tilt archive requires at least one reconstructed return"
        )

    validate_score_source(
        repo,
        base.resolve(repo, trigger["scores_csv"]),
        base_jobs,
        perturb_by_id,
    )
    validate_cell_source(
        base.resolve(repo, trigger["perturbation_cells_csv"]),
        perturb_by_id,
    )
    trigger_hash = base.add_artifact(repo, artifacts, trigger_path)
    bound["trigger_sha256"] = trigger_hash
    bound.update(validate_phase3_base42_archive(
        repo=repo,
        phase3=phase3,
        trigger=trigger,
        artifacts=artifacts,
    ))
    return bound


def validate_tilt_prepare_contract(
    repo: Path,
    run_root: Path,
    jobs_path: Path,
    status_path: Path,
    jobs: list[dict[str, str]],
    jobs_bytes: bytes,
    artifacts: dict[str, str],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, str]]:
    """Validate base preparation, tilt preparation, and trigger lineage."""

    base_jobs_path = base.resolve(repo, DEFAULT_BASE_JOBS)
    base_jobs_bytes = base.read_required(base_jobs_path, "base jobs.csv")
    base_jobs = base.parse_csv_bytes(
        base_jobs_bytes, "base jobs.csv", base.JOB_CSV_FIELDS
    )
    base.validate_jobs(base_jobs)
    base_prepare, lock, prewarm = base.validate_prepare_contract(
        repo,
        run_root,
        base_jobs_path,
        status_path,
        base_jobs,
        base_jobs_bytes,
        artifacts,
    )
    validate_lock_contract(repo, lock, status_path)

    manifest_path = base.resolve(repo, DEFAULT_TILT_MANIFEST)
    manifest = base.load_json_object(manifest_path, "tilt prepare manifest")
    if (
        manifest.get("schema")
        != "jointbuildgs.s3ap.phase2.prepare_manifest.v1"
        or manifest.get("status") != "complete"
        or manifest.get("mode") != "tilt"
    ):
        raise ArchiveError("Phase-2 tilt prepare manifest contract drift")
    base.require_json_false(
        manifest.get("training_started"), "tilt prepare training_started"
    )
    base.require_json_false(
        manifest.get("prepared_data_rewritten"),
        "tilt prepare prepared_data_rewritten",
    )
    base.require_json_int(manifest.get("job_count"), 18, "tilt job_count")
    for field in ("gt_used", "lod2_used", "als_used"):
        base.require_json_false(manifest.get(field), f"tilt prepare:{field}")
    if manifest.get("lock_path") != str(base.DEFAULT_LOCK):
        raise ArchiveError("tilt prepare lock path drift")
    lock_hash = base.sha256_file(base.resolve(repo, base.DEFAULT_LOCK))
    if manifest.get("lock_sha256") != lock_hash:
        raise ArchiveError("tilt prepare lock hash drift")
    base.validate_prepare_runtime_attestation(manifest.get("runtime_attestation"))

    jobs_hash = base.sha256_bytes(jobs_bytes)
    if (
        manifest.get("inventory") != base.relative(repo, jobs_path)
        or manifest.get("inventory_sha256") != jobs_hash
    ):
        raise ArchiveError("tilt prepare inventory path/hash drift")
    manifest_jobs = manifest.get("jobs")
    if not isinstance(manifest_jobs, list) or len(manifest_jobs) != 18:
        raise ArchiveError("tilt prepare jobs must contain exactly 18 entries")
    for job, manifest_job in zip(jobs, manifest_jobs):
        expected = {
            "job_id": job["job_id"],
            "config_path": job["config_path"],
            "config_sha256": job["config_sha256"],
            "final_checkpoint": job["final_checkpoint"],
        }
        base.require_exact_keys(
            manifest_job, expected, f"tilt prepare job:{job['job_id']}"
        )
        if not base.json_exact_equal(manifest_job, expected):
            raise ArchiveError(
                f"tilt prepare job contract drift: {job['job_id']}"
            )

    if not base.json_exact_equal(
        manifest.get("prepared_buildings"),
        base_prepare.get("prepared_buildings"),
    ):
        raise ArchiveError(
            "tilt prepared_buildings differ from immutable base preparation"
        )
    expected_base_reference = {
        "path": base.relative(repo, DEFAULT_BASE_MANIFEST),
        "sha256": base.sha256_file(base.resolve(repo, DEFAULT_BASE_MANIFEST)),
        "inventory": base.relative(repo, DEFAULT_BASE_JOBS),
        "inventory_sha256": base.sha256_file(base_jobs_path),
    }
    reference = manifest.get("base_prepare_reference")
    base.require_exact_keys(
        reference, expected_base_reference, "tilt base_prepare_reference"
    )
    if not base.json_exact_equal(reference, expected_base_reference):
        raise ArchiveError("tilt base prepare reference path/hash drift")

    trigger_entry = manifest.get("tilt_trigger")
    base.require_exact_keys(
        trigger_entry, ("path", "sha256", "payload"), "tilt trigger entry"
    )
    trigger_path = base.resolve(repo, DEFAULT_TRIGGER)
    trigger = base.load_json_object(trigger_path, "conditional tilt trigger")
    trigger_hash = base.sha256_file(trigger_path)
    if (
        trigger_entry.get("path") != base.relative(repo, trigger_path)
        or trigger_entry.get("sha256") != trigger_hash
        or not base.json_exact_equal(trigger_entry.get("payload"), trigger)
    ):
        raise ArchiveError("tilt prepare trigger path/hash/payload drift")
    trigger_hashes = validate_trigger_contract(
        repo, trigger_path, trigger, lock, base_jobs, artifacts
    )
    base.add_artifact(repo, artifacts, jobs_path, expected_hash=jobs_hash)
    base.add_artifact(repo, artifacts, manifest_path)
    return manifest, lock, prewarm, trigger_hashes


def validate_runner_dry_run_attestation(
    payload: Mapping[str, Any],
    *,
    repo: Path,
    jobs_path: Path,
    tilt_manifest_sha256: str,
    lock: Mapping[str, Any],
) -> str:
    expected_keys = (
        "inventory", "jobs", "status_counts", "gpu_ids", "timeout_s",
        "runtime_attestation", "prepare_manifest_sha256",
        "training_started",
    )
    base.require_exact_keys(payload, expected_keys, "tilt runner dry-run attestation")
    if payload.get("inventory") != base.relative(repo, jobs_path):
        raise ArchiveError("tilt runner dry-run inventory path drift")
    base.require_json_int(payload.get("jobs"), 18, "tilt runner dry-run jobs")
    if not base.json_exact_equal(
        payload.get("status_counts"), {"skipped_final_exists": 18}
    ):
        raise ArchiveError(
            "tilt runner dry-run must attest skipped_final_exists=18 only"
        )
    runtime = lock.get("runtime")
    if not base.json_exact_equal(
        payload.get("gpu_ids"), runtime.get("gpu_ids")
    ):
        raise ArchiveError("tilt runner dry-run GPU IDs drift")
    if payload.get("timeout_s") != runtime.get("default_run_timeout_s"):
        raise ArchiveError("tilt runner dry-run timeout drift")
    if payload.get("prepare_manifest_sha256") != tilt_manifest_sha256:
        raise ArchiveError("tilt runner dry-run prepare manifest hash drift")
    base.require_json_false(
        payload.get("training_started"),
        "tilt runner dry-run training_started",
    )
    base.validate_runner_runtime_attestation(
        payload.get("runtime_attestation"),
        "tilt runner dry-run runtime attestation",
    )
    return base.sha256_bytes(base.canonical_json_bytes(payload))


def _require_int_summary(value: Any, expected: int, role: str) -> None:
    base.require_json_int(value, expected, role)


def parse_hash_manifest(payload: bytes, role: str) -> dict[str, str]:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ArchiveError(f"{role} is not UTF-8") from error
    rows: dict[str, str] = {}
    previous = ""
    for number, line in enumerate(text.splitlines(), 1):
        if len(line) < 67 or line[64:66] != "  ":
            raise ArchiveError(f"{role} malformed line {number}")
        digest, path = line[:64], line[66:]
        base.require_hex64(digest, f"{role} line {number}")
        if not path or path in rows or (previous and path <= previous):
            raise ArchiveError(
                f"{role} paths must be nonempty, unique, and sorted"
            )
        rows[path] = digest
        previous = path
    if not rows:
        raise ArchiveError(f"{role} is empty")
    return rows


def validate_base42_completion(
    repo: Path,
    lock: Mapping[str, Any],
    artifacts: dict[str, str],
) -> tuple[dict[str, Any], str]:
    completion_path = base.resolve(repo, DEFAULT_BASE_COMPLETION)
    completion = base.load_json_object(
        completion_path, "base-42 completion manifest"
    )
    base.require_exact_keys(
        completion, BASE_COMPLETION_KEYS, "base-42 completion manifest"
    )
    base.validate_observational_completion_fields(completion)
    base.validate_embedded_runner_attestation(completion)
    exact_values: dict[str, Any] = {
        "schema": base.COMPLETION_SCHEMA,
        "status": "complete",
        "wave": "base42",
        "job_count": 42,
        "job_status_counts": {"complete": 42},
        "returncode_counts": {"0": 42},
        "iterations": 30000,
        "final_checkpoint_count": 42,
        "jobs_csv": base.relative(repo, DEFAULT_BASE_JOBS),
        "source_status_csv": base.relative(repo, DEFAULT_STATUS),
        "status_snapshot": base.relative(repo, DEFAULT_BASE_SNAPSHOT),
        "artifacts_manifest": base.relative(repo, DEFAULT_BASE_ARTIFACTS),
        "phase2_lock_sha256": base.sha256_file(
            base.resolve(repo, base.DEFAULT_LOCK)
        ),
        "prepare_manifest_sha256": base.sha256_file(
            base.resolve(repo, DEFAULT_BASE_MANIFEST)
        ),
        "docker_image_id": base.TRAINING_IMAGE_ID,
        "archive_tools_image": base.TOOLS_IMAGE,
        "archive_tools_image_id": base.TOOLS_IMAGE_ID,
        "prewarm_manifest": base.PREWARM_MANIFEST,
        "prewarm_status": "complete",
        "runner_dry_run_status_counts": {"skipped_final_exists": 42},
        "runner_dry_run_training_started": False,
        "raw_logs_copied": False,
        "raw_checkpoints_copied": False,
    }
    for field, expected in exact_values.items():
        if not base.json_exact_equal(completion.get(field), expected):
            raise ArchiveError(
                f"base-42 completion {field} drift: "
                f"{completion.get(field)!r} != {expected!r}"
            )
    for field in (
        "total_final_checkpoint_bytes", "final_n_prim_min",
        "final_n_prim_max", "artifacts_manifest_entry_count",
    ):
        value = completion.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ArchiveError(f"base-42 completion {field} must be positive")
    jobs_hash = base.add_artifact(repo, artifacts, DEFAULT_BASE_JOBS)
    if completion.get("jobs_csv_sha256") != jobs_hash:
        raise ArchiveError("base-42 completion jobs hash drift")
    snapshot_hash = base.add_artifact(repo, artifacts, DEFAULT_BASE_SNAPSHOT)
    if (
        completion.get("status_snapshot_sha256") != snapshot_hash
        or completion.get("source_status_csv_sha256") != snapshot_hash
    ):
        raise ArchiveError("base-42 completion status snapshot hash drift")
    snapshot_rows = base.parse_csv_bytes(
        base.read_required(base.resolve(repo, DEFAULT_BASE_SNAPSHOT), "base status snapshot"),
        "base status snapshot",
        base.STATUS_CSV_FIELDS,
    )
    if (
        len(snapshot_rows) != 42
        or any(row.get("status") != "complete" for row in snapshot_rows)
        or any(row.get("returncode") != "0" for row in snapshot_rows)
        or any(row.get("final_checkpoint_it") != "30000" for row in snapshot_rows)
    ):
        raise ArchiveError("base-42 immutable status snapshot is not 42 complete")

    manifest_path = base.resolve(repo, DEFAULT_BASE_ARTIFACTS)
    manifest_bytes = base.read_required(manifest_path, "base artifact manifest")
    manifest_hash = base.sha256_bytes(manifest_bytes)
    if completion.get("artifacts_manifest_sha256") != manifest_hash:
        raise ArchiveError("base-42 artifact manifest hash drift")
    manifest_rows = parse_hash_manifest(manifest_bytes, "base artifact manifest")
    if len(manifest_rows) != completion["artifacts_manifest_entry_count"]:
        raise ArchiveError("base-42 artifact manifest entry-count drift")
    snapshot_rel = base.relative(repo, DEFAULT_BASE_SNAPSHOT)
    if manifest_rows.get(snapshot_rel) != snapshot_hash:
        raise ArchiveError("base-42 artifact manifest misses bound snapshot")
    # The shared prewarm manifest is intentionally regenerated before later
    # Phase-3 and tilt runners.  Bind the base-era bytes through the immutable
    # base artifact manifest instead of incorrectly requiring the mutable
    # shared path to retain those older bytes.
    if manifest_rows.get(base.PREWARM_MANIFEST) != completion.get(
        "prewarm_manifest_sha256"
    ):
        raise ArchiveError("base-42 artifact manifest misses bound prewarm")
    base.add_artifact(
        repo, artifacts, manifest_path, expected_hash=manifest_hash
    )
    completion_hash = base.add_artifact(repo, artifacts, completion_path)

    base.validate_runner_dry_run_attestation(
        completion["runner_dry_run_attestation"],
        repo=repo,
        jobs_path=base.resolve(repo, DEFAULT_BASE_JOBS),
        prepare_manifest_sha256=completion["prepare_manifest_sha256"],
        lock=lock,
    )
    return completion, completion_hash


def validate_status_and_collect(
    repo: Path,
    run_root: Path,
    jobs: list[dict[str, str]],
    status_rows: list[dict[str, str]],
    tilt_manifest: Mapping[str, Any],
    artifacts: dict[str, str],
) -> dict[str, Any]:
    if len(status_rows) != 18:
        raise ArchiveError(
            f"runner status.csv must contain exactly 18 tilt rows, got {len(status_rows)}"
        )
    job_ids = [row["job_id"] for row in jobs]
    status_ids = [row.get("job_id", "") for row in status_rows]
    if status_ids != job_ids or len(set(status_ids)) != 18:
        raise ArchiveError(
            "runner status.csv job IDs/order must exactly equal tilt_jobs.csv"
        )

    total_final_bytes = 0
    n_primitives: dict[str, int] = {}
    validated_data_hashes: dict[str, str] = {}
    for job, status in zip(jobs, status_rows):
        job_id = job["job_id"]
        if status.get("sequence") != job.get("sequence"):
            raise ArchiveError(f"{job_id}: status sequence differs from inventory")
        if status.get("status") != "complete":
            raise ArchiveError(f"{job_id}: runner status must be complete")
        if status.get("returncode") != "0":
            raise ArchiveError(f"{job_id}: runner returncode must be 0")
        if status.get("final_checkpoint_it") != "30000":
            raise ArchiveError(
                f"{job_id}: final checkpoint iteration must be 30000"
            )
        n_primitives[job_id] = base.parse_positive_int(
            status.get("final_checkpoint_n_prim", ""),
            f"{job_id}:final_checkpoint_n_prim",
        )
        if status.get("gpu_id") not in {"0", "1"}:
            raise ArchiveError(f"{job_id}: completed GPU ID must be 0 or 1")
        for field in STATUS_HASH_FIELDS:
            base.require_hex64(status.get(field, ""), f"{job_id}:{field}")
        for status_field, job_field in (
            ("config_path", "config_path"),
            ("config_sha256", "config_sha256"),
            ("out_dir", "out_dir"),
            ("final_checkpoint", "final_checkpoint"),
            ("surface_seed_sha256", "surface_seed_sha256"),
        ):
            if status.get(status_field) != job.get(job_field):
                raise ArchiveError(
                    f"{job_id}: {status_field} differs from tilt_jobs.csv"
                )

        base.add_artifact(
            repo,
            artifacts,
            job["config_path"],
            expected_hash=status["config_sha256"],
        )
        base.add_artifact(
            repo,
            artifacts,
            job["surface_seed_npz"],
            expected_hash=status["surface_seed_sha256"],
        )
        building = job["building_id"]
        if building not in validated_data_hashes:
            validated_data_hashes[building] = base.validate_prepared_data_manifest(
                repo,
                tilt_manifest,
                building,
                job["data_root"],
                status["data_manifest_sha256"],
                artifacts,
            )
        elif status["data_manifest_sha256"] != validated_data_hashes[building]:
            raise ArchiveError(
                f"{job_id}: data manifest hash differs within building"
            )

        out_dir = base.resolve(repo, job["out_dir"])
        binding_path = out_dir / "phase2_job_binding.json"
        base.add_artifact(
            repo,
            artifacts,
            binding_path,
            expected_hash=status["job_binding_sha256"],
        )
        binding = base.load_json_object(binding_path, f"{job_id} binding")
        binding_expected: dict[str, Any] = {
            "schema": "jointbuildgs.s3ap.phase2.job_binding.v1",
            "job_id": job_id,
            "config_path": job["config_path"],
            "config_sha256": job["config_sha256"],
            "data_root": job["data_root"],
            "surface_seed_npz": job["surface_seed_npz"],
            "surface_seed_sha256": job["surface_seed_sha256"],
            "iterations": 30000,
        }
        base.require_exact_keys(binding, binding_expected, f"{job_id}:binding")
        if not base.json_exact_equal(binding, binding_expected):
            raise ArchiveError(f"{job_id}: binding differs from inventory/lock")

        for suffix in PER_JOB_ARTIFACTS[1:-1]:
            base.add_artifact(repo, artifacts, out_dir / suffix)
        final_path = base.resolve(repo, job["final_checkpoint"])
        base.add_artifact(
            repo,
            artifacts,
            final_path,
            expected_hash=status["final_checkpoint_sha256"],
        )
        total_final_bytes += final_path.stat().st_size
        expected_log = run_root / "runner/logs" / f"{job_id}.log"
        if status.get("log_path") != base.relative(repo, expected_log):
            raise ArchiveError(f"{job_id}: runner log path drift")
        base.add_artifact(repo, artifacts, expected_log)

    prepare_hashes = {
        row["prepare_manifest_sha256"] for row in status_rows
    }
    if len(prepare_hashes) != 1:
        raise ArchiveError("tilt status rows disagree on prepare manifest hash")
    return {
        "complete_jobs": 18,
        "total_final_checkpoint_bytes": total_final_bytes,
        "final_n_prim_min": min(n_primitives.values()),
        "final_n_prim_max": max(n_primitives.values()),
        "prepare_manifest_sha256": next(iter(prepare_hashes)),
    }


def validate_observational_completion_fields(
    completion: Mapping[str, Any],
) -> None:
    base.validate_observational_completion_fields(completion)


def validate_embedded_runner_attestation(
    completion: Mapping[str, Any],
) -> None:
    payload = completion.get("runner_dry_run_attestation")
    if not isinstance(payload, Mapping):
        raise ArchiveError(
            "completion_tilt18.json runner dry-run attestation is absent"
        )
    actual_hash = base.sha256_bytes(base.canonical_json_bytes(payload))
    if completion.get("runner_dry_run_attestation_sha256") != actual_hash:
        raise ArchiveError(
            "completion_tilt18.json embedded runner attestation hash mismatch"
        )


def reconcile_existing_completion(
    existing: Mapping[str, Any],
    recomputed: Mapping[str, Any],
) -> dict[str, Any]:
    if set(existing) != set(recomputed):
        raise ArchiveError(
            "immutable completion_tilt18.json key-set differs from recomputed contract"
        )
    validate_observational_completion_fields(existing)
    validate_embedded_runner_attestation(existing)
    expected = dict(recomputed)
    for key in COMPLETION_OBSERVATIONAL_KEYS:
        expected[key] = existing[key]
    differing = [
        key for key in expected
        if not base.json_exact_equal(existing.get(key), expected[key])
    ]
    if differing:
        raise ArchiveError(
            "immutable completion_tilt18.json fields differ from validated "
            f"sources: {sorted(differing)!r}"
        )
    return dict(existing)


def final_revalidate_collected_artifacts(
    *,
    repo: Path,
    jobs_path: Path,
    jobs_bytes: bytes,
    status_path: Path,
    status_bytes: bytes,
    artifacts: Mapping[str, str],
) -> tuple[bytes, bytes, dict[str, str]]:
    """Close the collection-to-manifest TOCTOU window before any write."""

    current_jobs = base.read_required(jobs_path, "final tilt_jobs.csv")
    if current_jobs != jobs_bytes:
        raise ArchiveError("final jobs source drift after validation")
    current_status = base.read_required(
        status_path, "final tilt runner status.csv"
    )
    if current_status != status_bytes:
        raise ArchiveError("final status source drift after validation")
    refreshed: dict[str, str] = {}
    for rel_path in sorted(artifacts):
        expected_hash = artifacts[rel_path]
        base.require_hex64(
            expected_hash, f"final collected artifact:{rel_path}"
        )
        path = base.resolve(repo, rel_path)
        if not path.is_file():
            raise ArchiveError(
                f"final collected artifact disappeared: {rel_path}"
            )
        actual_hash = base.sha256_file(path)
        if actual_hash != expected_hash:
            raise ArchiveError(
                "final artifact drift after validation: "
                f"{rel_path}: {actual_hash} != {expected_hash}"
            )
        refreshed[rel_path] = actual_hash
    return current_jobs, current_status, refreshed


def archive_tilt18(
    *,
    repo: Path,
    jobs_path: Path,
    status_path: Path,
    output_dir: Path,
    runner_dry_run_attestation: Mapping[str, Any],
    tools_image_id: str,
    dry_run: bool = False,
    _before_final_revalidation_hook: Callable[[], None] | None = None,
) -> dict[str, Any]:
    repo = repo.resolve()
    jobs_path = base.resolve(repo, jobs_path)
    status_path = base.resolve(repo, status_path)
    output_dir = base.resolve(repo, output_dir)
    run_root = jobs_path.parent
    if jobs_path != base.resolve(repo, DEFAULT_JOBS):
        raise ArchiveError(
            "tilt_jobs.csv must remain at the canonical locked path"
        )
    if run_root != base.resolve(repo, DEFAULT_RUN_ROOT):
        raise ArchiveError("tilt_jobs.csv must remain at the locked run root")
    if status_path != base.resolve(repo, DEFAULT_STATUS):
        raise ArchiveError("runner status.csv must remain at the locked path")
    if output_dir != status_path.parent:
        raise ArchiveError("tilt-18 archive outputs must remain in runner directory")
    validated_tools_image_id = base.validate_tools_image_id(tools_image_id)

    jobs_bytes = base.read_required(jobs_path, "tilt_jobs.csv")
    status_bytes = base.read_required(status_path, "tilt runner status.csv")
    jobs = base.parse_csv_bytes(
        jobs_bytes, "tilt_jobs.csv", JOB_CSV_FIELDS
    )
    status_rows = base.parse_csv_bytes(
        status_bytes, "tilt runner status.csv", STATUS_CSV_FIELDS
    )
    validate_jobs(jobs)

    artifacts: dict[str, str] = {}
    tilt_manifest, lock, prewarm, trigger_hashes = validate_tilt_prepare_contract(
        repo,
        run_root,
        jobs_path,
        status_path,
        jobs,
        jobs_bytes,
        artifacts,
    )
    base_completion, base_completion_hash = validate_base42_completion(
        repo, lock, artifacts
    )
    actual_tilt_manifest_hash = base.sha256_file(
        base.resolve(repo, DEFAULT_TILT_MANIFEST)
    )
    runner_attestation_hash = validate_runner_dry_run_attestation(
        runner_dry_run_attestation,
        repo=repo,
        jobs_path=jobs_path,
        tilt_manifest_sha256=actual_tilt_manifest_hash,
        lock=lock,
    )
    runner_attestation_canonical = base.parse_json_object_text(
        base.canonical_json_bytes(runner_dry_run_attestation).decode("utf-8"),
        "canonical tilt runner dry-run attestation",
    )
    status_summary = validate_status_and_collect(
        repo, run_root, jobs, status_rows, tilt_manifest, artifacts
    )
    if status_summary["prepare_manifest_sha256"] != actual_tilt_manifest_hash:
        raise ArchiveError(
            "tilt status rows' prepare manifest hash differs from actual file"
        )

    for rel_path in STATIC_PROVENANCE:
        base.add_artifact(repo, artifacts, rel_path)
    if _before_final_revalidation_hook is not None:
        _before_final_revalidation_hook()
    jobs_bytes, status_bytes, artifacts = final_revalidate_collected_artifacts(
        repo=repo,
        jobs_path=jobs_path,
        jobs_bytes=jobs_bytes,
        status_path=status_path,
        status_bytes=status_bytes,
        artifacts=artifacts,
    )
    snapshot_path = output_dir / SNAPSHOT_NAME
    snapshot_rel = base.relative(repo, snapshot_path)
    snapshot_hash = base.sha256_bytes(status_bytes)
    artifacts[snapshot_rel] = snapshot_hash
    artifacts_bytes = base.artifact_manifest_bytes(artifacts)
    artifacts_path = output_dir / ARTIFACTS_NAME
    artifacts_hash = base.sha256_bytes(artifacts_bytes)
    prewarm_hash = artifacts[base.PREWARM_MANIFEST]

    completion = {
        "schema": COMPLETION_SCHEMA,
        "created_utc": base.utc_now(),
        "status": "complete",
        "wave": "tilt18",
        "job_count": 18,
        "job_status_counts": {"complete": 18},
        "returncode_counts": {"0": 18},
        "iterations": 30000,
        "jobs_csv": base.relative(repo, jobs_path),
        "jobs_csv_sha256": base.sha256_bytes(jobs_bytes),
        "source_status_csv": base.relative(repo, status_path),
        "source_status_csv_sha256": base.sha256_bytes(status_bytes),
        "status_snapshot": snapshot_rel,
        "status_snapshot_sha256": snapshot_hash,
        "artifacts_manifest": base.relative(repo, artifacts_path),
        "artifacts_manifest_sha256": artifacts_hash,
        "artifacts_manifest_entry_count": len(artifacts),
        "final_checkpoint_count": 18,
        "total_final_checkpoint_bytes": status_summary[
            "total_final_checkpoint_bytes"
        ],
        "final_n_prim_min": status_summary["final_n_prim_min"],
        "final_n_prim_max": status_summary["final_n_prim_max"],
        "phase2_lock_sha256": tilt_manifest["lock_sha256"],
        "tilt_prepare_manifest": base.relative(repo, DEFAULT_TILT_MANIFEST),
        "tilt_prepare_manifest_sha256": actual_tilt_manifest_hash,
        "tilt_prepare_git_head": tilt_manifest.get("git_head", ""),
        "tilt_trigger": base.relative(repo, DEFAULT_TRIGGER),
        "tilt_trigger_sha256": trigger_hashes["trigger_sha256"],
        "source_scores_csv": lock["tilt_score_source"]["scores_csv"],
        "source_score_sha256": trigger_hashes["source_score_sha256"],
        "source_perturbation_csv": lock["tilt_score_source"]["perturbation_csv"],
        "source_perturbation_sha256": trigger_hashes[
            "source_perturbation_sha256"
        ],
        "source_perturbation_cells_csv": (
            "docs/experiments/input-and-alignment/e5_c001_s3ap/tables/e5_c001_s3ap_perturbation_cells.csv"
        ),
        "source_perturbation_cells_sha256": trigger_hashes[
            "source_perturbation_cells_sha256"
        ],
        "phase3_base42_archive": trigger_hashes["archive"],
        "phase3_base42_archive_manifest": trigger_hashes["manifest"],
        "phase3_base42_archive_manifest_sha256": trigger_hashes[
            "manifest_sha256"
        ],
        "phase3_base42_archive_completion": trigger_hashes["completion"],
        "phase3_base42_archive_completion_sha256": trigger_hashes[
            "completion_sha256"
        ],
        "phase3_base42_source_mapping_digest": trigger_hashes[
            "source_mapping_digest"
        ],
        "phase3_base42_archive_payload_digest": trigger_hashes[
            "archive_payload_digest"
        ],
        "phase3_base42_inventory_job_contract_digest": trigger_hashes[
            "inventory_job_contract_digest"
        ],
        "phase3_base42_aggregate_manifest": trigger_hashes[
            "aggregate_manifest"
        ],
        "phase3_base42_aggregate_manifest_sha256": trigger_hashes[
            "aggregate_manifest_sha256"
        ],
        "phase3_archive_lock_sha256": artifacts[
            str(DEFAULT_PHASE3_ARCHIVE_LOCK)
        ],
        "phase3_archive_controller_sha256": artifacts[
            str(DEFAULT_PHASE3_ARCHIVE_CONTROLLER)
        ],
        "phase3_archive_wrapper_sha256": artifacts[
            str(DEFAULT_PHASE3_ARCHIVE_WRAPPER)
        ],
        "phase3_archive_test_sha256": artifacts[
            str(DEFAULT_PHASE3_ARCHIVE_TEST)
        ],
        "base42_completion": base.relative(repo, DEFAULT_BASE_COMPLETION),
        "base42_completion_sha256": base_completion_hash,
        "base42_status_snapshot": base_completion["status_snapshot"],
        "base42_status_snapshot_sha256": base_completion[
            "status_snapshot_sha256"
        ],
        "docker_image_id": base.TRAINING_IMAGE_ID,
        "training_launcher": base.HOST_LAUNCHER,
        "training_launcher_sha256": artifacts[base.HOST_LAUNCHER],
        "archive_launcher": ARCHIVE_LAUNCHER,
        "archive_launcher_sha256": artifacts[ARCHIVE_LAUNCHER],
        "archive_tools_image": base.TOOLS_IMAGE,
        "archive_tools_image_id": validated_tools_image_id,
        "prewarm_manifest": base.PREWARM_MANIFEST,
        "prewarm_manifest_sha256": prewarm_hash,
        "prewarm_status": prewarm.get("status", ""),
        "runner_dry_run_attestation": runner_attestation_canonical,
        "runner_dry_run_attestation_sha256": runner_attestation_hash,
        "runner_dry_run_status_counts": {"skipped_final_exists": 18},
        "runner_dry_run_training_started": False,
        "gt_used": False,
        "lod2_used": False,
        "als_used": False,
        "archive_git_head": base.git_value(repo, "rev-parse", "HEAD"),
        "archive_git_branch": base.git_value(repo, "branch", "--show-current"),
        "raw_logs_copied": False,
        "raw_checkpoints_copied": False,
        "raw_bindings_copied": False,
        "raw_configs_copied": False,
        "artifact_policy": (
            "hashes only for runtime logs/checkpoints/bindings/config/data/seed "
            "audits; no raw runtime payload copied"
        ),
    }
    validate_observational_completion_fields(completion)
    validate_embedded_runner_attestation(completion)
    if dry_run:
        return {**completion, "dry_run": True, "outputs_written": False}

    completion_path = output_dir / COMPLETION_NAME
    base.require_existing_equal(snapshot_path, status_bytes)
    base.require_existing_equal(artifacts_path, artifacts_bytes)
    if completion_path.exists():
        existing = base.load_json_object(
            completion_path, "tilt-18 completion manifest"
        )
        completion = reconcile_existing_completion(existing, completion)
    completion_bytes = (
        json.dumps(completion, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    base.require_existing_equal(completion_path, completion_bytes)
    write_results = {
        SNAPSHOT_NAME: base.atomic_write_idempotent(snapshot_path, status_bytes),
        ARTIFACTS_NAME: base.atomic_write_idempotent(
            artifacts_path, artifacts_bytes
        ),
        COMPLETION_NAME: base.atomic_write_idempotent(
            completion_path, completion_bytes
        ),
    }
    return {
        **completion,
        "dry_run": False,
        "outputs_written": True,
        "write_results": write_results,
    }


def validate_live_static_contract(repo: Path = REPO) -> None:
    """Read-only validation usable before conditional tilt files exist."""

    repo = repo.resolve()
    lock = base.load_json_object(
        base.resolve(repo, base.DEFAULT_LOCK), "live Phase-2 lock"
    )
    validate_lock_contract(repo, lock, base.resolve(repo, DEFAULT_STATUS))
    for path in STATIC_PROVENANCE:
        if not base.resolve(repo, path).is_file():
            raise ArchiveError(f"missing live static provenance: {path}")
    for source_text, expected_hash in PHASE3_ARCHIVE_STATIC_SHA256.items():
        actual_hash = base.sha256_file(base.resolve(repo, source_text))
        if actual_hash != expected_hash:
            raise ArchiveError(
                "live final Phase-3 archive source hash drift: "
                f"{source_text}: {actual_hash} != {expected_hash}"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=str(REPO))
    parser.add_argument("--jobs", default=str(DEFAULT_JOBS))
    parser.add_argument("--status", default=str(DEFAULT_STATUS))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument(
        "--runner-dry-run-attestation-json",
        required=True,
        help=(
            "verbatim JSON emitted by the locked training-image runner for "
            "tilt_jobs.csv run --dry-run"
        ),
    )
    parser.add_argument(
        "--tools-image-id",
        required=True,
        help="host-inspected immutable ID of the locked archive tools image",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    attestation = base.parse_json_object_text(
        args.runner_dry_run_attestation_json,
        "tilt runner dry-run attestation",
    )
    result = archive_tilt18(
        repo=Path(args.repo),
        jobs_path=Path(args.jobs),
        status_path=Path(args.status),
        output_dir=Path(args.output_dir),
        runner_dry_run_attestation=attestation,
        tools_image_id=args.tools_image_id,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
