#!/usr/bin/env python3
"""Resolve the FUS-W1 178-building priority queue from committed sources.

This resolver intentionally does not infer GS4Buildings IDs.  The public-artifact
gap is carried into every CSV row and the sidecar manifest so absence cannot be
mistaken for a measured zero-overlap result.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import platform
import re
import subprocess
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_CONFIG = (
    REPO_ROOT / "phases/p2-gsjso/configs/fusion_w1/fusion_w1_targets_v1.json"
)
DEFAULT_OUTPUT = (
    REPO_ROOT / "phases/p2-gsjso/runs/fusion_w1/20260724_fusion_w1/w1_targets.csv"
)
DEFAULT_METADATA_OUTPUT = (
    REPO_ROOT
    / "phases/p2-gsjso/runs/fusion_w1/20260724_fusion_w1/w1_targets_manifest.json"
)
CANONICAL_ID_RE = re.compile(r"^DEBY_LOD2_([0-9]+)$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
PROVISIONAL_QUEUE_STATUS = "provisional_gs4_overlap_unresolved"

OUTPUT_FIELDS = [
    "building_id",
    "tier",
    "cohort",
    "cohort_resolution_status",
    "selection_reason",
    "processing_order",
    "queue_status",
    "priority_bucket",
    "source_cell_label",
    "texture_low_gradient_fraction",
    "selection_sources",
    "gs4buildings_overlap_status",
    "gs4buildings_overlap_reason",
]


class ResolutionError(RuntimeError):
    """Raised when a committed-source invariant is not satisfied."""


@dataclass(frozen=True)
class Selection:
    name: str
    building_ids: tuple[str, ...]
    reasons: Mapping[str, str]
    source_paths: tuple[str, ...]


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResolutionError(f"cannot read JSON source {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ResolutionError(f"JSON source is not an object: {path}")
    return value


def _read_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                raise ResolutionError(f"CSV has no header: {path}")
            return [dict(row) for row in reader]
    except OSError as exc:
        raise ResolutionError(f"cannot read CSV source {path}: {exc}") from exc


def _require_columns(
    rows: Sequence[Mapping[str, str]], required: Iterable[str], source: str
) -> None:
    if not rows:
        raise ResolutionError(f"source has no data rows: {source}")
    missing = sorted(set(required) - set(rows[0]))
    if missing:
        raise ResolutionError(f"source {source} missing columns: {missing}")


def _source_path(repo_root: Path, relative_path: str) -> Path:
    path = (repo_root / relative_path).resolve()
    try:
        path.relative_to(repo_root.resolve())
    except ValueError as exc:
        raise ResolutionError(f"source escapes repository root: {relative_path}") from exc
    if not path.is_file():
        raise ResolutionError(f"source file missing: {relative_path}")
    return path


def _canonical_id(value: str) -> str:
    value = str(value).strip()
    if value.isdigit():
        value = f"DEBY_LOD2_{value}"
    if not CANONICAL_ID_RE.fullmatch(value):
        raise ResolutionError(f"invalid canonical building ID: {value!r}")
    return value


def _numeric_id(building_id: str) -> int:
    match = CANONICAL_ID_RE.fullmatch(building_id)
    if not match:
        raise ResolutionError(f"invalid canonical building ID: {building_id!r}")
    return int(match.group(1))


def _finite_float(value: str, field: str, building_id: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ResolutionError(
            f"{building_id}: non-numeric {field}={value!r}"
        ) from exc
    if not math.isfinite(number):
        raise ResolutionError(f"{building_id}: non-finite {field}={value!r}")
    return number


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _manifest_path(path: Path, repo_root: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(repo_root.resolve()))
    except ValueError:
        return str(resolved)


def _require_exact_lock(actual: Any, expected: Any, field: str) -> None:
    if actual != expected:
        raise ResolutionError(
            f"unsupported lock value {field}={actual!r}; expected {expected!r}"
        )


def _locked_file_record(
    *,
    repo_root: Path,
    record: Mapping[str, Any],
    label: str,
) -> dict[str, Any]:
    relative_path = str(record["path"])
    expected_sha256 = str(record["sha256"])
    if not SHA256_RE.fullmatch(expected_sha256):
        raise ResolutionError(f"{label}: invalid locked SHA-256 {expected_sha256!r}")
    path = _source_path(repo_root, relative_path)
    actual_sha256 = _sha256(path)
    if actual_sha256 != expected_sha256:
        raise ResolutionError(
            f"{label}: SHA-256 mismatch for {relative_path}: "
            f"{actual_sha256} != {expected_sha256}"
        )
    return {
        "path": relative_path,
        "sha256": actual_sha256,
        "bytes": path.stat().st_size,
    }


def _run_git(
    repo_root: Path,
    *arguments: str,
) -> subprocess.CompletedProcess[str]:
    command = [
        "git",
        "-c",
        f"safe.directory={repo_root.resolve()}",
        "-C",
        str(repo_root.resolve()),
        *arguments,
    ]
    try:
        return subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise ResolutionError(f"cannot execute Git provenance check: {exc}") from exc


def _validate_generation_git_state(
    *,
    repo_root: Path,
    parent_commit: str,
    parent_branch: str,
) -> None:
    branch_result = _run_git(repo_root, "branch", "--show-current")
    if branch_result.returncode != 0:
        raise ResolutionError(
            "cannot resolve current Git branch for generation provenance: "
            f"{branch_result.stderr.strip()}"
        )
    current_branch = branch_result.stdout.strip()
    if current_branch != parent_branch:
        raise ResolutionError(
            f"current Git branch {current_branch!r} != locked "
            f"generation parent branch {parent_branch!r}"
        )

    exists_result = _run_git(
        repo_root,
        "cat-file",
        "-e",
        f"{parent_commit}^{{commit}}",
    )
    if exists_result.returncode != 0:
        raise ResolutionError(
            f"generation parent commit does not exist: {parent_commit}"
        )

    ancestor_result = _run_git(
        repo_root,
        "merge-base",
        "--is-ancestor",
        parent_commit,
        "HEAD",
    )
    if ancestor_result.returncode == 1:
        raise ResolutionError(
            f"generation parent commit is not an ancestor of HEAD: {parent_commit}"
        )
    if ancestor_result.returncode != 0:
        raise ResolutionError(
            "cannot verify generation parent ancestry: "
            f"{ancestor_result.stderr.strip()}"
        )


def _generation_provenance(
    *, repo_root: Path, config: Mapping[str, Any]
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    protocol_records = {
        name: _locked_file_record(
            repo_root=repo_root,
            record=record,
            label=f"protocol_locks.{name}",
        )
        for name, record in dict(config["protocol_locks"]).items()
    }

    lock = dict(config["generation_lock"])
    parent_commit = str(lock["generation_parent_commit"])
    parent_branch = str(lock["generation_parent_branch"])
    if not COMMIT_SHA_RE.fullmatch(parent_commit):
        raise ResolutionError(
            f"invalid generation_parent_commit: {parent_commit!r}"
        )
    if not parent_branch:
        raise ResolutionError("generation_parent_branch must not be empty")
    _validate_generation_git_state(
        repo_root=repo_root,
        parent_commit=parent_commit,
        parent_branch=parent_branch,
    )

    resolver_path = str(lock["resolver_path"])
    test_path = str(lock["test_path"])
    resolver = _source_path(repo_root, resolver_path)
    tests = _source_path(repo_root, test_path)
    runtime = dict(lock["runtime"])
    expected_python = str(runtime["python_version"])
    observed_python = platform.python_version()
    if observed_python != expected_python:
        raise ResolutionError(
            f"Python runtime {observed_python} != locked {expected_python}"
        )
    image_id = str(runtime["docker_image_id"])
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
        raise ResolutionError(f"invalid locked Docker image ID: {image_id!r}")

    return (
        protocol_records,
        {
            "generation_parent_commit": parent_commit,
            "generation_parent_branch": parent_branch,
            "source_state": "generated_against_parent_before_target_artifact_commit",
            "resolver": {
                "path": resolver_path,
                "sha256": _sha256(resolver),
                "bytes": resolver.stat().st_size,
            },
            "tests": {
                "path": test_path,
                "sha256": _sha256(tests),
                "bytes": tests.stat().st_size,
            },
            "runtime": {
                **runtime,
                "observed_python_version": observed_python,
            },
        },
    )


def _fraction_rank_index(fraction_text: str, population_count: int) -> int:
    if population_count <= 0:
        raise ResolutionError("cannot select a rank from an empty population")
    try:
        position = Fraction(fraction_text) * (population_count - 1)
    except (ValueError, ZeroDivisionError) as exc:
        raise ResolutionError(f"invalid rank fraction: {fraction_text}") from exc
    if position < 0 or position > population_count - 1:
        raise ResolutionError(f"rank fraction outside [0,1]: {fraction_text}")
    # Exact "nearest, halves away from zero" for non-negative rank positions.
    return int(position + Fraction(1, 2))


def _ordered_unique(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _validate_population(
    rows: list[dict[str, str]], config: Mapping[str, Any]
) -> tuple[dict[str, dict[str, str]], dict[str, str]]:
    population_lock = config["population_lock"]
    tier_mapping = dict(config["tier_mapping"])
    required = {
        "building_id",
        "cell_label",
        "texture_low_gradient_fraction",
        population_lock["population_scope_field"],
        population_lock["crs_field"],
    }
    _require_columns(rows, required, config["sources"]["population_ladder"])
    expected_count = int(config["expected_population_count"])
    if len(rows) != expected_count:
        raise ResolutionError(
            f"population row count {len(rows)} != expected {expected_count}"
        )

    by_id: dict[str, dict[str, str]] = {}
    tiers: dict[str, str] = {}
    allowed = set(population_lock["allowed_cell_labels"])
    for row in rows:
        building_id = _canonical_id(row["building_id"])
        if building_id in by_id:
            raise ResolutionError(f"duplicate population building ID: {building_id}")
        scope_field = population_lock["population_scope_field"]
        if row[scope_field] != population_lock["population_scope_value"]:
            raise ResolutionError(
                f"{building_id}: unexpected population scope {row[scope_field]!r}"
            )
        crs_field = population_lock["crs_field"]
        if row[crs_field] != population_lock["crs_value"]:
            raise ResolutionError(f"{building_id}: unexpected CRS {row[crs_field]!r}")
        cell_label = row["cell_label"]
        if cell_label not in allowed or cell_label not in tier_mapping:
            raise ResolutionError(
                f"{building_id}: unsupported cell label {cell_label!r}"
            )
        _finite_float(
            row["texture_low_gradient_fraction"],
            "texture_low_gradient_fraction",
            building_id,
        )
        row = dict(row)
        row["building_id"] = building_id
        by_id[building_id] = row
        tiers[building_id] = tier_mapping[cell_label]
    return by_id, tiers


def _select_filtered_csv(
    *,
    rows: Sequence[Mapping[str, str]],
    filters: Mapping[str, str],
    id_field: str,
    source: str,
    name: str,
    expected_count: int,
    population_ids: set[str],
    reason: str,
) -> Selection:
    _require_columns(rows, {id_field, *filters.keys()}, source)
    selected: list[str] = []
    for row in rows:
        if all(str(row[field]).strip().lower() == expected.lower() for field, expected in filters.items()):
            selected.append(_canonical_id(row[id_field]))
    selected_ids = _ordered_unique(selected)
    if len(selected_ids) != len(selected):
        raise ResolutionError(f"{name}: duplicate selected IDs in {source}")
    if len(selected_ids) != expected_count:
        raise ResolutionError(
            f"{name}: selected {len(selected_ids)} != expected {expected_count}"
        )
    outside = sorted(set(selected_ids) - population_ids, key=_numeric_id)
    if outside:
        raise ResolutionError(f"{name}: IDs outside population: {outside}")
    return Selection(
        name=name,
        building_ids=selected_ids,
        reasons={building_id: reason for building_id in selected_ids},
        source_paths=(source,),
    )


def _select_height_primary(
    *,
    path: Path,
    relative_path: str,
    rule: Mapping[str, Any],
    expected_count: int,
    population_ids: set[str],
    tiers: Mapping[str, str],
) -> Selection:
    source = _read_json(path)
    field = str(rule["json_field"])
    raw_ids = source.get(field)
    if not isinstance(raw_ids, list):
        raise ResolutionError(f"{relative_path}#{field} is not a list")
    selected_ids = _ordered_unique(_canonical_id(value) for value in raw_ids)
    if len(selected_ids) != len(raw_ids):
        raise ResolutionError(f"height_primary: duplicate IDs in {relative_path}#{field}")
    if len(selected_ids) != expected_count:
        raise ResolutionError(
            f"height_primary: selected {len(selected_ids)} != expected {expected_count}"
        )
    outside = sorted(set(selected_ids) - population_ids, key=_numeric_id)
    if outside:
        raise ResolutionError(f"height_primary: IDs outside population: {outside}")
    required_tier = str(rule["required_tier"])
    wrong_tier = [value for value in selected_ids if tiers[value] != required_tier]
    if wrong_tier:
        raise ResolutionError(
            f"height_primary: locked IDs not in tier {required_tier}: {wrong_tier}"
        )
    reason = f"height_observed_primary4_lock:{relative_path}#{field}"
    return Selection(
        name="height_primary",
        building_ids=selected_ids,
        reasons={building_id: reason for building_id in selected_ids},
        source_paths=(relative_path,),
    )


def _select_textured_controls(
    *,
    population_rows: Mapping[str, Mapping[str, str]],
    tiers: Mapping[str, str],
    rule: Mapping[str, Any],
    source: str,
    expected_count: int,
) -> Selection:
    _require_exact_lock(
        rule["anchor_rule"],
        "minimum_numeric_id_in_locked_shortlist",
        "textured_control.anchor_rule",
    )
    _require_exact_lock(
        rule["second_rule"],
        "minimum_texture_low_gradient_fraction_excluding_anchor",
        "textured_control.second_rule",
    )
    _require_exact_lock(
        rule["tie_break"],
        "canonical_building_id_numeric_ascending",
        "textured_control.tie_break",
    )
    low = int(rule["shortlist_numeric_id_min"])
    high = int(rule["shortlist_numeric_id_max"])
    shortlist = [
        row
        for building_id, row in population_rows.items()
        if low <= _numeric_id(building_id) <= high
    ]
    shortlist.sort(key=lambda row: _numeric_id(row["building_id"]))
    required_shortlist_count = int(rule["required_shortlist_count"])
    if len(shortlist) != required_shortlist_count:
        raise ResolutionError(
            f"textured shortlist has {len(shortlist)} rows != "
            f"expected {required_shortlist_count}"
        )
    required_tier = str(rule["required_tier"])
    wrong_tier = [
        row["building_id"]
        for row in shortlist
        if tiers[row["building_id"]] != required_tier
    ]
    if wrong_tier:
        raise ResolutionError(
            f"textured shortlist IDs not in tier {required_tier}: {wrong_tier}"
        )
    score_field = str(rule["score_field"])
    anchor = shortlist[0]
    remaining = shortlist[1:]
    second = min(
        remaining,
        key=lambda row: (
            _finite_float(row[score_field], score_field, row["building_id"]),
            _numeric_id(row["building_id"]),
        ),
    )
    selected_ids = (anchor["building_id"], second["building_id"])
    if len(selected_ids) != expected_count:
        raise ResolutionError(
            f"textured_control: selected {len(selected_ids)} != expected {expected_count}"
        )
    shortlist_text = f"{low}-{high}"
    reasons = {
        anchor["building_id"]: (
            "textured_positive_control_anchor:"
            f"shortlist={shortlist_text};rule={rule['anchor_rule']}"
        ),
        second["building_id"]: (
            "textured_positive_control_best:"
            f"shortlist={shortlist_text};metric={score_field};direction=min;"
            f"value={second[score_field]}"
        ),
    }
    return Selection(
        name="textured_control",
        building_ids=selected_ids,
        reasons=reasons,
        source_paths=(source,),
    )


def _select_outline_rank_spread(
    *,
    population_rows: Mapping[str, Mapping[str, str]],
    tiers: Mapping[str, str],
    previously_selected: set[str],
    rule: Mapping[str, Any],
    source: str,
    expected_count: int,
) -> tuple[Selection, dict[str, Any]]:
    if not rule.get("exclude_all_previously_selected_core", False):
        raise ResolutionError(
            "outline_rank_spread must exclude all previously selected core IDs"
        )
    required_tier = str(rule["required_tier"])
    score_field = str(rule["score_field"])
    if rule["score_order"] != "ascending":
        raise ResolutionError("only ascending outline score order is supported")
    _require_exact_lock(
        rule["rank_rounding"],
        "nearest_half_up",
        "outline_rank_spread.rank_rounding",
    )
    _require_exact_lock(
        rule["tie_break"],
        "canonical_building_id_numeric_ascending",
        "outline_rank_spread.tie_break",
    )
    candidates = [
        row
        for building_id, row in population_rows.items()
        if tiers[building_id] == required_tier
        and building_id not in previously_selected
    ]
    candidates.sort(
        key=lambda row: (
            _finite_float(row[score_field], score_field, row["building_id"]),
            _numeric_id(row["building_id"]),
        )
    )
    fractions = [str(value) for value in rule["rank_fractions"]]
    if len(fractions) != expected_count:
        raise ResolutionError(
            f"outline rank fraction count {len(fractions)} != expected {expected_count}"
        )
    indices = [
        _fraction_rank_index(fraction, len(candidates)) for fraction in fractions
    ]
    if len(set(indices)) != len(indices):
        raise ResolutionError(f"outline rank rule produced duplicate indices: {indices}")
    selected_rows = [candidates[index] for index in indices]
    selected_ids = tuple(row["building_id"] for row in selected_rows)
    reasons = {
        row["building_id"]: (
            "outline_observed_rank_spread:"
            f"score={score_field};rank={index + 1}/{len(candidates)};"
            f"fraction={fraction};value={row[score_field]};"
            "existing_core_excluded=true"
        )
        for row, index, fraction in zip(selected_rows, indices, fractions, strict=True)
    }
    audit = {
        "candidate_count_after_core_exclusion": len(candidates),
        "score_field": score_field,
        "score_order": rule["score_order"],
        "rank_fractions": fractions,
        "rank_indices_zero_based": indices,
        "rank_rounding": rule["rank_rounding"],
        "selected": [
            {
                "building_id": row["building_id"],
                "score": row[score_field],
                "rank_one_based": index + 1,
            }
            for row, index in zip(selected_rows, indices, strict=True)
        ],
    }
    return (
        Selection(
            name="outline_rank_spread",
            building_ids=selected_ids,
            reasons=reasons,
            source_paths=(source,),
        ),
        audit,
    )


def _round_robin_extension(
    *,
    remaining_ids: Iterable[str],
    tiers: Mapping[str, str],
    tier_order: Sequence[str],
) -> list[str]:
    queues: dict[str, deque[str]] = {}
    remaining_set = set(remaining_ids)
    for tier in tier_order:
        queues[tier] = deque(
            sorted(
                (building_id for building_id in remaining_set if tiers[building_id] == tier),
                key=_numeric_id,
            )
        )
    represented = set().union(*(set(queue) for queue in queues.values()))
    missing = sorted(remaining_set - represented, key=_numeric_id)
    if missing:
        raise ResolutionError(
            f"extension IDs have tiers absent from round-robin order: {missing}"
        )
    output: list[str] = []
    while any(queues.values()):
        for tier in tier_order:
            if queues[tier]:
                output.append(queues[tier].popleft())
    return output


def resolve_targets(
    *,
    repo_root: Path,
    config_path: Path,
    generated_utc: str | None = None,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    repo_root = repo_root.resolve()
    config_path = config_path.resolve()
    config = _read_json(config_path)
    sources = dict(config["sources"])
    source_files = {
        name: _source_path(repo_root, relative_path)
        for name, relative_path in sources.items()
    }
    protocol_records, generation = _generation_provenance(
        repo_root=repo_root,
        config=config,
    )

    population_source = sources["population_ladder"]
    population_rows_list = _read_csv(source_files["population_ladder"])
    population_rows, tiers = _validate_population(population_rows_list, config)
    population_ids = set(population_rows)
    counts = config["expected_core_source_counts"]

    p0_filters = config["p0_dim_failure"]["filters"]
    p0_selection = _select_filtered_csv(
        rows=_read_csv(source_files["p0_paired_status"]),
        filters=p0_filters,
        id_field="building_id",
        source=sources["p0_paired_status"],
        name="p0_dim_failure",
        expected_count=int(counts["p0_dim_failure"]),
        population_ids=population_ids,
        reason=(
            "p0_dim_reconstruction_failure:"
            + ";".join(f"{key}={value}" for key, value in p0_filters.items())
        ),
    )

    dense_filters = config["c001_dense_success"]["filters"]
    dense_selection = _select_filtered_csv(
        rows=_read_csv(source_files["c001_quality_pairs"]),
        filters=dense_filters,
        id_field="building_id",
        source=sources["c001_quality_pairs"],
        name="c001_dense_success",
        expected_count=int(counts["c001_dense_success"]),
        population_ids=population_ids,
        reason=(
            "c001_dense_success_pair:"
            + ";".join(f"{key}={value}" for key, value in dense_filters.items())
        ),
    )

    height_selection = _select_height_primary(
        path=source_files["height_primary_lock"],
        relative_path=sources["height_primary_lock"],
        rule=config["height_primary"],
        expected_count=int(counts["height_primary"]),
        population_ids=population_ids,
        tiers=tiers,
    )

    textured_selection = _select_textured_controls(
        population_rows=population_rows,
        tiers=tiers,
        rule=config["textured_control"],
        source=population_source,
        expected_count=int(counts["textured_control"]),
    )

    pre_outline_ids = set().union(
        p0_selection.building_ids,
        dense_selection.building_ids,
        height_selection.building_ids,
        textured_selection.building_ids,
    )
    outline_selection, outline_audit = _select_outline_rank_spread(
        population_rows=population_rows,
        tiers=tiers,
        previously_selected=pre_outline_ids,
        rule=config["outline_rank_spread"],
        source=population_source,
        expected_count=int(counts["outline_rank_spread"]),
    )

    gs4 = dict(config["gs4buildings"])
    if gs4["status"] != "unresolvable_public_artifact_missing":
        raise ResolutionError("unexpected GS4Buildings resolution status")
    if gs4.get("id_inference_allowed") is not False:
        raise ResolutionError("GS4Buildings ID inference must remain disabled")
    if gs4.get("overlap_resolution") != "unknown":
        raise ResolutionError(
            "GS4Buildings overlap resolution must remain unknown while unresolved"
        )
    if gs4.get("overlap_count") is not None:
        raise ResolutionError(
            "GS4Buildings overlap count must be null while unresolved"
        )
    if gs4.get("overlap_ids") is not None:
        raise ResolutionError(
            "GS4Buildings overlap IDs must be null while unresolved"
        )
    if gs4.get("checked_ref") != "refs/heads/main":
        raise ResolutionError("GS4Buildings evidence must pin refs/heads/main")
    if not COMMIT_SHA_RE.fullmatch(str(gs4.get("checked_commit", ""))):
        raise ResolutionError("GS4Buildings checked_commit is not a full commit SHA")
    if not str(gs4.get("repository_url", "")).startswith("https://github.com/"):
        raise ResolutionError("GS4Buildings repository URL is not an HTTPS GitHub URL")
    gs4_selection = Selection(
        name="gs4buildings_overlap",
        building_ids=(),
        reasons={},
        source_paths=(),
    )

    selections = {
        selection.name: selection
        for selection in (
            p0_selection,
            gs4_selection,
            dense_selection,
            height_selection,
            outline_selection,
            textured_selection,
        )
    }
    priority_order = list(config["core_priority_order"])
    if set(priority_order) != set(selections):
        raise ResolutionError(
            "core_priority_order must name every and only configured core selection"
        )

    membership: dict[str, list[str]] = defaultdict(list)
    reasons: dict[str, list[str]] = defaultdict(list)
    source_membership: dict[str, list[str]] = defaultdict(list)
    for name in priority_order:
        selection = selections[name]
        for building_id in selection.building_ids:
            membership[building_id].append(name)
            reasons[building_id].append(selection.reasons[building_id])
            source_membership[building_id].extend(selection.source_paths)

    core_ids = set(membership)
    core_order: list[str] = []
    for name in priority_order:
        for building_id in selections[name].building_ids:
            if building_id not in core_order:
                core_order.append(building_id)
    _require_exact_lock(
        config["extension_within_tier_order"],
        "canonical_building_id_numeric_ascending",
        "extension_within_tier_order",
    )
    extension_order = _round_robin_extension(
        remaining_ids=population_ids - core_ids,
        tiers=tiers,
        tier_order=list(config["extension_tier_round_robin"]),
    )
    queue = core_order + extension_order
    if len(queue) != int(config["expected_population_count"]):
        raise ResolutionError(
            f"queue count {len(queue)} != expected {config['expected_population_count']}"
        )
    if len(set(queue)) != len(queue) or set(queue) != population_ids:
        raise ResolutionError("queue is not an exact unique cover of the population")

    priority_numbers = {name: index + 1 for index, name in enumerate(priority_order)}
    output_rows: list[dict[str, str]] = []
    for order, building_id in enumerate(queue, start=1):
        population_row = population_rows[building_id]
        if building_id in core_ids:
            bucket_name = membership[building_id][0]
            cohort = "core"
            cohort_resolution_status = "resolved_core"
            selection_reason = "|".join(reasons[building_id])
            selected_sources = _ordered_unique(source_membership[building_id])
            priority_bucket = (
                f"{priority_numbers[bucket_name]:02d}_{bucket_name}"
            )
        else:
            cohort = "extension"
            cohort_resolution_status = (
                "provisional_extension_pending_gs4_overlap"
            )
            selection_reason = (
                "provisional_extension_remaining_population:"
                "tier_balanced_round_robin=surface>height>outline"
            )
            selected_sources = (population_source,)
            priority_bucket = "07_extension_round_robin"
        output_rows.append(
            {
                "building_id": building_id,
                "tier": tiers[building_id],
                "cohort": cohort,
                "cohort_resolution_status": cohort_resolution_status,
                "selection_reason": selection_reason,
                "processing_order": str(order),
                "queue_status": PROVISIONAL_QUEUE_STATUS,
                "priority_bucket": priority_bucket,
                "source_cell_label": population_row["cell_label"],
                "texture_low_gradient_fraction": population_row[
                    "texture_low_gradient_fraction"
                ],
                "selection_sources": "|".join(selected_sources),
                "gs4buildings_overlap_status": str(gs4["status"]),
                "gs4buildings_overlap_reason": (
                    f"{gs4['reason']};id_inference_allowed=false;"
                    "overlap_unknown_not_measured_as_zero"
                ),
            }
        )

    source_records = {
        relative_path: {
            "sha256": _sha256(source_files[name]),
            "bytes": source_files[name].stat().st_size,
        }
        for name, relative_path in sources.items()
    }
    by_tier_total = {
        tier: sum(row["tier"] == tier for row in output_rows)
        for tier in config["extension_tier_round_robin"]
    }
    by_tier_core = {
        tier: sum(
            row["tier"] == tier and row["cohort"] == "core" for row in output_rows
        )
        for tier in config["extension_tier_round_robin"]
    }
    if generated_utc is None:
        generated_utc = datetime.now(timezone.utc).isoformat()
    metadata = {
        "schema": "jointbuildgs.fusion_w1.targets.manifest.v1",
        "task_id": config["task_id"],
        "generated_utc": generated_utc,
        "status": "provisional_external_public_artifact_gap",
        "queue_status": PROVISIONAL_QUEUE_STATUS,
        "core_priority_complete": False,
        "population_count": len(output_rows),
        "unique_building_count": len({row["building_id"] for row in output_rows}),
        "final_core_count": None,
        "final_extension_count": None,
        "resolved_core_lower_bound_count": len(core_order),
        "provisional_extension_count": len(extension_order),
        "counts_by_tier": by_tier_total,
        "resolved_core_lower_bound_counts_by_tier": by_tier_core,
        "core_source_counts": {
            name: (
                None
                if name == "gs4buildings_overlap"
                else len(selections[name].building_ids)
            )
            for name in priority_order
        },
        "core_priority_order": priority_order,
        "extension_rule": {
            "tier_round_robin": list(config["extension_tier_round_robin"]),
            "within_tier_order": config["extension_within_tier_order"],
        },
        "outline_rank_spread": outline_audit,
        "gs4buildings": gs4,
        "source_records": source_records,
        "protocol_records": protocol_records,
        "generation": generation,
        "selected_ids_by_source": {
            name: (
                None
                if name == "gs4buildings_overlap"
                else list(selections[name].building_ids)
            )
            for name in priority_order
        },
        "verdict": None,
    }
    return output_rows, metadata


def _render_csv(rows: Sequence[Mapping[str, str]]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=OUTPUT_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _write_csv(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _validate_generated_utc(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ResolutionError("manifest generated_utc must be a non-empty string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ResolutionError(f"invalid manifest generated_utc: {value!r}") from exc
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ResolutionError("manifest generated_utc must use UTC")
    return value


def _finalize_metadata(
    *,
    metadata: Mapping[str, Any],
    repo_root: Path,
    config_path: Path,
    output_path: Path,
    metadata_output_path: Path,
    output_payload: bytes,
) -> dict[str, Any]:
    finalized = dict(metadata)
    generation = dict(finalized["generation"])
    runtime = dict(generation["runtime"])
    generation["command"] = {
        "mode": "docker_python_cli",
        "container_workdir": runtime["container_workdir"],
        "argv": [
            str(runtime["python_executable"]),
            str(generation["resolver"]["path"]),
            "--repo-root",
            _manifest_path(repo_root, repo_root),
            "--config",
            _manifest_path(config_path, repo_root),
            "--output",
            _manifest_path(output_path, repo_root),
            "--metadata-output",
            _manifest_path(metadata_output_path, repo_root),
        ],
    }
    finalized["generation"] = generation
    finalized["output"] = {
        "path": _manifest_path(output_path, repo_root),
        "sha256": _sha256_bytes(output_payload),
        "bytes": len(output_payload),
    }
    finalized["config"] = {
        "path": _manifest_path(config_path, repo_root),
        "sha256": _sha256(config_path),
        "bytes": config_path.stat().st_size,
    }
    return finalized


def build_outputs(
    *,
    repo_root: Path,
    config_path: Path,
    output_path: Path,
    metadata_output_path: Path,
    generated_utc: str | None = None,
) -> dict[str, Any]:
    rows, metadata = resolve_targets(
        repo_root=repo_root,
        config_path=config_path,
        generated_utc=generated_utc,
    )
    output_payload = _render_csv(rows)
    _write_csv(output_path, output_payload)
    metadata = _finalize_metadata(
        metadata=metadata,
        repo_root=repo_root,
        config_path=config_path,
        output_path=output_path,
        metadata_output_path=metadata_output_path,
        output_payload=output_payload,
    )
    _write_json(metadata_output_path, metadata)
    return metadata


def verify_outputs(
    *,
    repo_root: Path,
    config_path: Path,
    output_path: Path,
    metadata_output_path: Path,
) -> dict[str, Any]:
    actual_metadata = _read_json(metadata_output_path)
    generated_utc = _validate_generated_utc(actual_metadata.get("generated_utc"))
    rows, base_metadata = resolve_targets(
        repo_root=repo_root,
        config_path=config_path,
        generated_utc=generated_utc,
    )
    expected_payload = _render_csv(rows)
    try:
        actual_payload = output_path.read_bytes()
    except OSError as exc:
        raise ResolutionError(f"cannot read fixed CSV output {output_path}: {exc}") from exc
    if actual_payload != expected_payload:
        raise ResolutionError(
            f"fixed CSV output does not match deterministic regeneration: {output_path}"
        )
    expected_metadata = _finalize_metadata(
        metadata=base_metadata,
        repo_root=repo_root,
        config_path=config_path,
        output_path=output_path,
        metadata_output_path=metadata_output_path,
        output_payload=expected_payload,
    )
    if actual_metadata != expected_metadata:
        raise ResolutionError(
            "fixed target manifest does not match deterministic regeneration"
        )
    return actual_metadata


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--metadata-output", type=Path, default=DEFAULT_METADATA_OUTPUT
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="verify the fixed CSV and manifest without writing either file",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    operation = "verify" if args.verify_only else "generate"
    if args.verify_only:
        metadata = verify_outputs(
            repo_root=args.repo_root,
            config_path=args.config,
            output_path=args.output,
            metadata_output_path=args.metadata_output,
        )
    else:
        metadata = build_outputs(
            repo_root=args.repo_root,
            config_path=args.config,
            output_path=args.output,
            metadata_output_path=args.metadata_output,
        )
    print(
        json.dumps(
            {
                "operation": operation,
                "status": metadata["status"],
                "queue_status": metadata["queue_status"],
                "population_count": metadata["population_count"],
                "unique_building_count": metadata["unique_building_count"],
                "resolved_core_lower_bound_count": metadata[
                    "resolved_core_lower_bound_count"
                ],
                "provisional_extension_count": metadata[
                    "provisional_extension_count"
                ],
                "gs4buildings_status": metadata["gs4buildings"]["status"],
                "output": metadata["output"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
