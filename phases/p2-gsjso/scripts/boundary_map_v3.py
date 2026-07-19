#!/usr/bin/env python3
"""Boundary-map v3 learning-zero preparation, rule fit, and reporting.

The two commands in this module are deliberately separated from MASt3R:

``prepare-fit``
    Reconstruct the locked 158-label calibration/validation inventory, fit the
    sign-constrained depth<=2 rule on the 79 calibration records, and emit the
    FM dense-dial queue.

``finalize``
    Read the completed dense-dial measurements, select its count threshold on
    calibration records only, and write the public v3 CSV/manifest/figure
    bundle.  Budget-limited or prerequisite-missing rows are retained as an
    explicit incomplete list; their primary assignment is retained and the
    threshold is selected only from completed calibration-candidate rows.

No optimizer or training entry point is imported or invoked here.  The LoD2
projection products already present in v2 are read only for address generation
and map rendering.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import itertools
import json
import math
import os
import random
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp")

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402


REPO = Path(__file__).resolve().parents[3]
DOCS = REPO / "docs"
RUN_DIR = REPO / "phases/p2-gsjso/runs/20260719_boundary_map_v3"

SNAPSHOT = DOCS / "regression_input_snapshot.csv"
MANUAL = DOCS / "manual_review_judgments.csv"
V2_METRICS = DOCS / "boundary_map_v2_metrics.csv"
V2_LADDER = DOCS / "boundary_map_v2_ladder.csv"
V2_MANIFEST = DOCS / "boundary_map_v2_manifest.json"
V2_ALL_PROJECTION_JOBS = (
    REPO
    / "phases/p2-gsjso/runs/20260718_boundary_map_v2/all_projection_jobs.json"
)
V2_SCRIPT = Path(__file__).with_name("boundary_map_v2.py")
DENSE_SCRIPT = Path(__file__).with_name("boundary_map_v3_dense.py")
DRIVER_SCRIPT = Path(__file__).with_name(
    "run_boundary_map_v3_20260719.sh"
)
ENV_MANIFEST = DOCS / "e5_c001_s3ap_fm_env_manifest.json"
S3AP_DIAL_CONFIG = (
    REPO / "phases/p2-gsjso/configs/e5_c001_s3ap_fm_dense_dial.json"
)
S3AP_DIAL_CSV = DOCS / "e5_c001_s3ap_fm_dense_dial.csv"
S3AP_PJPL = (
    REPO
    / "results/tum_transfer/e5_s3_semantic_guided/C001/runs"
    / "gs_e5_C001_s3a_semantic_guided_gate/audit/pjpl_depth_anchor_views.csv"
)
C001_REGION_DIR = REPO / "results/tum_transfer/e5_s3/C001/semantic_regions"

PRIMARY_CSV = RUN_DIR / "primary_predictions.csv"
RULE_JSON = RUN_DIR / "decision_rule.json"
LABEL_INVENTORY = RUN_DIR / "label_inventory.json"
FM_JOBS = RUN_DIR / "fm_dense_jobs.json"
FM_MEASUREMENTS = RUN_DIR / "fm_dense_measurements.csv"
FM_PAIRS = RUN_DIR / "fm_dense_pairs.csv"
FM_PROGRESS = RUN_DIR / "fm_dense_progress.json"
FM_RUN_MANIFEST = RUN_DIR / "fm_dense_manifest.json"
PARTIAL_MANIFEST = RUN_DIR / "partial_manifest.json"
PARTIAL_SUMMARY = RUN_DIR / "partial_summary.md"

METRICS = DOCS / "boundary_map_v3_metrics.csv"
LADDER = DOCS / "boundary_map_v3_ladder.csv"
CONFUSION = DOCS / "boundary_map_v3_confusion.csv"
CONDITIONAL = DOCS / "boundary_map_v3_conditional_targets.csv"
MANIFEST = DOCS / "boundary_map_v3_manifest.json"
SUMMARY = DOCS / "W_boundary_map_v3_summary_20260719.md"
FIGURE = DOCS / "figs/boundary_map_v3/boundary_map_v3_map.png"

MANUAL_SPLIT_SEED = 20260718
DENSE_SPLIT_SEED = 20260719
SMALL_AREA_M2 = 50.0
FM_MIN_COUNT = 1
MAX_PAIRS = 10
CROP_MARGIN_PX = 32
CROP_MIN_WIDTH = 256

WELL = "well_textured"
TEXTURELESS = "textureless_correspondence_anchored"
OUTLINE = "outline_only"
UNOBSERVABLE = "unobservable"
SMALL = "indeterminate_small"
EXPECTED_LABELS = (WELL, TEXTURELESS, OUTLINE)
MAP_LABELS = (WELL, TEXTURELESS, OUTLINE, UNOBSERVABLE, SMALL)
NEW_INFERENCE_TYPE = "R1prime-3_FM_dense_dial_2px"

RULE_FEATURES = (
    "texture_low_gradient_fraction",
    "texture_grad_p10",
    "dense_point_count",
    "dense_point_density_m2",
    "coverage_frac",
    "n_views_nadir",
    "frac_views_incidence_le60",
    "recon_score_median",
)
FEATURES_WITH_SMALL = (*RULE_FEATURES, "footprint_area_m2")
WELL_DIRECTION = {
    "texture_low_gradient_fraction": "smaller",
    "texture_grad_p10": "larger",
    "dense_point_count": "larger",
    "dense_point_density_m2": "larger",
    "coverage_frac": "larger",
    "n_views_nadir": "larger",
    "frac_views_incidence_le60": "larger",
    "recon_score_median": "larger",
}

MANUAL_TEXTURELESS_ORDER = (
    "DEBY_LOD2_4907199",
    "DEBY_LOD2_8568391",
    "DEBY_LOD2_4908049",
    "DEBY_LOD2_4908162",
)
OVERRIDE_IDS = (
    "DEBY_LOD2_4907199",
    "DEBY_LOD2_8568391",
)
OVERRIDE_EVIDENCE = (
    "B-1_measured_flat_seed(FM 앵커 373·456점·"
    "W_밤샘3과제_검수_20260717 §3-1)"
)
C001_IDS = (
    "DEBY_LOD2_108247349",
    "DEBY_LOD2_108247350",
    "DEBY_LOD2_108247351",
    "DEBY_LOD2_4907184",
    "DEBY_LOD2_4907185",
    "DEBY_LOD2_4907186",
    "DEBY_LOD2_4907188",
    "DEBY_LOD2_4907194",
    "DEBY_LOD2_4907195",
    "DEBY_LOD2_4907198",
    "DEBY_LOD2_4907199",
    "DEBY_LOD2_4907202",
    "DEBY_LOD2_4908168",
    "DEBY_LOD2_4908178",
    "DEBY_LOD2_4908179",
    "DEBY_LOD2_60098",
    "DEBY_LOD2_8568391",
    "DEBY_LOD2_8568392",
)
LOCKED_S3AP_PAIR_IDS = {
    "DEBY_LOD2_4907199",
    "DEBY_LOD2_8568391",
}

PRIMARY_FIELDS = [
    "building_id",
    "label_source",
    "manual_split",
    "dense_split",
    "combined_split",
    "expected_tier",
    "primary_assignment",
    "primary_rule_path",
    "primary_nonwell_candidate",
    "learning_runs_started",
    "new_inference_type",
]

CONFUSION_FIELDS = [
    "record_type",
    "comparison",
    "subset",
    "actual_label",
    "recorded_label",
    "count",
    "n_records",
    "correct_count",
    "accuracy",
    "constant_correct_count",
    "constant_accuracy",
    "accuracy_gain",
    "metric_label",
    "tp",
    "actual_support",
    "predicted_support",
    "recall",
    "precision",
    "metric_status",
    "manual_split_seed",
    "dense_split_seed",
    "rule_sha256",
    "evaluation_status",
    "rule_status",
    "learning_runs_started",
]

CONDITIONAL_FIELDS = [
    "building_id",
    "primary_assignment",
    "formula_assignment",
    "size_rule_assignment",
    "override_assignment",
    "override_evidence",
    "override_applied",
    "map_assignment",
    "fm_dense_footprint_inside_point_count",
    "fm_dense_inside_z_median_m",
    "conditional_generation_target",
    "learning_runs_started",
    "new_inference_type",
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def rel(path: Path | str) -> str:
    value = Path(path)
    try:
        return str(value.resolve().relative_to(REPO.resolve()))
    except ValueError:
        return str(value.resolve())


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_csv_fields(path: Path) -> list[str]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        return next(reader)


def sha256_file(path: Path, block_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_json(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def set_sha256(values: Iterable[str]) -> str:
    return hashlib.sha256(
        ("\n".join(sorted(values)) + "\n").encode("utf-8")
    ).hexdigest()


def fmt(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (bool, np.bool_)):
        return "true" if bool(value) else "false"
    if isinstance(value, (float, np.floating)):
        return "" if not math.isfinite(float(value)) else f"{float(value):.9f}"
    return value


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def atomic_json(path: Path, payload: Any) -> None:
    atomic_text(
        path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    )


def atomic_csv(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
    fields: Sequence[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(fields),
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(
            {field: fmt(row.get(field)) for field in fields}
            for row in rows
        )
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def as_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def as_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(float(value))


def as_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def git_value(*args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", *args], cwd=REPO, text=True
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def expected_tier(label: str) -> str:
    if label == "무텍스처":
        return TEXTURELESS
    if "재질" in label or "저조도" in label:
        return OUTLINE
    return WELL


def locked_manual_split(
    manual_rows: Sequence[Mapping[str, str]],
) -> tuple[set[str], set[str], dict[str, str], dict[str, dict[str, int]]]:
    expected = {
        row["building_id"]: expected_tier(row["label"])
        for row in manual_rows
    }
    grouped: dict[str, list[str]] = defaultdict(list)
    for building_id, label in expected.items():
        grouped[label].append(building_id)
    observed = {label: len(grouped[label]) for label in EXPECTED_LABELS}
    if observed != {WELL: 34, TEXTURELESS: 4, OUTLINE: 6}:
        raise RuntimeError(f"manual label distribution drift: {observed}")
    calibration: set[str] = set()
    validation: set[str] = set()
    inventory: dict[str, dict[str, int]] = {}
    for index, label in enumerate(EXPECTED_LABELS):
        identifiers = sorted(grouped[label])
        random.Random(MANUAL_SPLIT_SEED + index).shuffle(identifiers)
        cut = len(identifiers) // 2
        calibration.update(identifiers[:cut])
        validation.update(identifiers[cut:])
        inventory[label] = {
            "calibration": cut,
            "validation": len(identifiers) - cut,
        }
    if len(calibration) != 22 or len(validation) != 22:
        raise RuntimeError("manual split is not 22/22")
    return calibration, validation, expected, inventory


def dense_split(
    dense_success: set[str],
) -> tuple[set[str], set[str], list[str]]:
    shuffled = sorted(dense_success)
    random.Random(DENSE_SPLIT_SEED).shuffle(shuffled)
    calibration = set(shuffled[:57])
    validation = set(shuffled[57:])
    if (
        len(calibration) != 57
        or len(validation) != 57
        or calibration & validation
        or calibration | validation != dense_success
    ):
        raise RuntimeError("dense success split is not an exact 57/57 partition")
    return calibration, validation, shuffled


def reconstruct_label_inventory() -> dict[str, Any]:
    snapshot_rows = read_csv(SNAPSHOT)
    lidar_rows = [row for row in snapshot_rows if row["arm"] == "raw_lidar"]
    dense_rows = [row for row in snapshot_rows if row["arm"] == "raw_dense"]
    if len(lidar_rows) != 199 or len(dense_rows) != 199:
        raise RuntimeError("snapshot raw_lidar/raw_dense population drift")
    if len({row["building_id"] for row in lidar_rows}) != 199:
        raise RuntimeError("raw_lidar building identifier duplication")
    if len({row["building_id"] for row in dense_rows}) != 199:
        raise RuntimeError("raw_dense building identifier duplication")
    canonical = {
        row["building_id"] for row in lidar_rows if as_bool(row["assembled"])
    }
    dense_success_all = {
        row["building_id"] for row in dense_rows if as_bool(row["assembled"])
    }
    dense_success = dense_success_all & canonical
    if len(canonical) != 178 or len(dense_success) != 114:
        raise RuntimeError("canonical 178 or dense success 114 invariant failed")

    v2_rows = read_csv(V2_METRICS)
    v2_ids = {row["building_id"] for row in v2_rows}
    v2_dense = {
        row["building_id"] for row in v2_rows
        if as_bool(row.get("dense_assembled"))
    }
    if len(v2_rows) != 178 or len(v2_ids) != 178 or v2_ids != canonical:
        raise RuntimeError("v2 metric population differs from canonical 178")
    if v2_dense != dense_success:
        raise RuntimeError("v2 dense_assembled differs from dense success formula")
    for row in v2_rows:
        missing = [
            feature for feature in FEATURES_WITH_SMALL
            if as_float(row.get(feature)) is None
        ]
        if missing:
            raise RuntimeError(
                f"{row['building_id']} missing v3 feature values: {missing}"
            )

    manual_rows = read_csv(MANUAL)
    if (
        len(manual_rows) != 44
        or len({row["building_id"] for row in manual_rows}) != 44
    ):
        raise RuntimeError("manual review is not 44 unique records")
    manual_ids = {row["building_id"] for row in manual_rows}
    if not manual_ids <= canonical:
        raise RuntimeError("manual 44 is not a subset of canonical 178")
    if manual_ids & dense_success:
        raise RuntimeError("manual 44 intersects dense success 114")
    (
        manual_calibration,
        manual_validation,
        manual_expected,
        manual_distribution,
    ) = locked_manual_split(manual_rows)

    v2_manifest = json.loads(V2_MANIFEST.read_text(encoding="utf-8"))
    v2_population = v2_manifest["population"]
    if int(v2_population["manual_split_seed"]) != MANUAL_SPLIT_SEED:
        raise RuntimeError("v2 manual split seed drift")
    if set(v2_population["manual_calibration_buildings"]) != manual_calibration:
        raise RuntimeError("v2 manual calibration membership drift")
    if set(v2_population["manual_validation_buildings"]) != manual_validation:
        raise RuntimeError("v2 manual validation membership drift")
    if v2_population["manual_split_inventory"] != manual_distribution:
        raise RuntimeError("v2 manual split inventory drift")

    dense_calibration, dense_validation, dense_shuffle = dense_split(
        dense_success
    )
    calibration = manual_calibration | dense_calibration
    validation = manual_validation | dense_validation
    if (
        len(calibration) != 79
        or len(validation) != 79
        or calibration & validation
        or len(calibration | validation) != 158
    ):
        raise RuntimeError("combined label split is not 79/79 over 158 records")
    expected = dict(manual_expected)
    expected.update({building_id: WELL for building_id in dense_success})
    calibration_distribution = Counter(expected[item] for item in calibration)
    validation_distribution = Counter(expected[item] for item in validation)
    locked_distribution = Counter(
        {WELL: 74, TEXTURELESS: 2, OUTLINE: 3}
    )
    if (
        calibration_distribution != locked_distribution
        or validation_distribution != locked_distribution
    ):
        raise RuntimeError("combined split expected-tier distribution drift")

    return {
        "schema": "jointbuildgs.boundary_map_v3.label_inventory.v1",
        "created_utc": now(),
        "canonical": canonical,
        "dense_success": dense_success,
        "manual_ids": manual_ids,
        "manual_calibration": manual_calibration,
        "manual_validation": manual_validation,
        "dense_calibration": dense_calibration,
        "dense_validation": dense_validation,
        "dense_shuffle": dense_shuffle,
        "calibration": calibration,
        "validation": validation,
        "expected": expected,
        "manual_expected": manual_expected,
        "manual_distribution": manual_distribution,
        "calibration_distribution": calibration_distribution,
        "validation_distribution": validation_distribution,
        "v2_rows": v2_rows,
        "json": {
            "schema": "jointbuildgs.boundary_map_v3.label_inventory.v1",
            "created_utc": now(),
            "population_formula": (
                "docs/regression_input_snapshot.csv arm=raw_lidar "
                "and assembled=true"
            ),
            "canonical_count": 178,
            "canonical_buildings": sorted(canonical),
            "canonical_set_sha256": set_sha256(canonical),
            "dense_success_formula": (
                "raw_dense assembled=true intersect canonical raw_lidar "
                "assembled=true"
            ),
            "raw_dense_assembled_true_count": len(dense_success_all),
            "dense_success_count": 114,
            "dense_failure_count": 64,
            "dense_success_buildings": sorted(dense_success),
            "dense_success_set_sha256": set_sha256(dense_success),
            "manual_count": 44,
            "manual_dense_success_intersection_count": 0,
            "manual_dense_success_intersection_buildings": [],
            "manual_split_seed": MANUAL_SPLIT_SEED,
            "manual_split_source": "v2 exact membership retained",
            "manual_split_inventory": manual_distribution,
            "manual_calibration_buildings": sorted(manual_calibration),
            "manual_validation_buildings": sorted(manual_validation),
            "manual_calibration_set_sha256": set_sha256(manual_calibration),
            "manual_validation_set_sha256": set_sha256(manual_validation),
            "dense_split_seed": DENSE_SPLIT_SEED,
            "dense_split_algorithm": (
                "sorted identifiers; random.Random(20260719).shuffle; "
                "first 57 calibration, remaining 57 validation"
            ),
            "dense_shuffle_sha256": set_sha256(
                f"{index:03d}:{building_id}"
                for index, building_id in enumerate(dense_shuffle)
            ),
            "dense_calibration_buildings": sorted(dense_calibration),
            "dense_validation_buildings": sorted(dense_validation),
            "dense_calibration_set_sha256": set_sha256(dense_calibration),
            "dense_validation_set_sha256": set_sha256(dense_validation),
            "combined_calibration_count": 79,
            "combined_validation_count": 79,
            "combined_labeled_count": 158,
            "unlabeled_canonical_count": 20,
            "combined_calibration_buildings": sorted(calibration),
            "combined_validation_buildings": sorted(validation),
            "combined_calibration_distribution": {
                label: calibration_distribution[label]
                for label in EXPECTED_LABELS
            },
            "combined_validation_distribution": {
                label: validation_distribution[label]
                for label in EXPECTED_LABELS
            },
            "constant_well_validation_correct": 74,
            "constant_well_validation_n": 79,
            "constant_well_validation_accuracy": 74 / 79,
            "source_sha256": {
                rel(SNAPSHOT): sha256_file(SNAPSHOT),
                rel(MANUAL): sha256_file(MANUAL),
                rel(V2_METRICS): sha256_file(V2_METRICS),
                rel(V2_MANIFEST): sha256_file(V2_MANIFEST),
            },
            "learning_runs_started": 0,
            "new_inference_runs": 0,
            "interpretation_or_verdict": None,
        },
    }


@dataclass(frozen=True)
class Candidate:
    tree: dict[str, Any]
    correct: int
    depth: int
    predicate_count: int
    serial: str
    well_range: tuple[int, int]

    @property
    def key(self) -> tuple[Any, ...]:
        return (
            -self.correct,
            self.depth,
            self.predicate_count,
            self.serial,
        )


def tree_serial(tree: Mapping[str, Any]) -> str:
    def tie_payload(node: Mapping[str, Any]) -> dict[str, Any]:
        if "label" in node:
            label = str(node["label"])
            return {
                "label": (
                    f"{EXPECTED_LABELS.index(label):02d}:{label}"
                )
            }
        return {
            "predicate": dict(node["predicate"]),
            "le": tie_payload(node["le"]),
            "gt": tie_payload(node["gt"]),
        }

    return json.dumps(
        tie_payload(tree),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def leaf_candidate(
    label: str,
    rows: Sequence[Mapping[str, Any]],
    expected: Mapping[str, str],
) -> Candidate:
    tree = {"label": label}
    well = 1 if label == WELL else 0
    return Candidate(
        tree=tree,
        correct=sum(
            expected[row["building_id"]] == label for row in rows
        ),
        depth=0,
        predicate_count=0,
        serial=tree_serial(tree),
        well_range=(well, well),
    )


def predicate_candidates(
    calibration_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for feature in RULE_FEATURES:
        values = sorted({float(row[feature]) for row in calibration_rows})
        for left, right in zip(values, values[1:]):
            output.append(
                {
                    "feature": feature,
                    "op": "<=",
                    "threshold": (left + right) / 2.0,
                    "well_direction": WELL_DIRECTION[feature],
                }
            )
    return output


def predicate_value(
    row: Mapping[str, Any], predicate: Mapping[str, Any]
) -> bool:
    return float(row[predicate["feature"]]) <= float(predicate["threshold"])


def sign_valid(
    feature: str,
    le_range: tuple[int, int],
    gt_range: tuple[int, int],
) -> bool:
    if WELL_DIRECTION[feature] == "larger":
        adverse, favorable = le_range, gt_range
    else:
        adverse, favorable = gt_range, le_range
    return adverse[1] <= favorable[0]


def combine_candidate(
    predicate: Mapping[str, Any],
    le: Candidate,
    gt: Candidate,
) -> Candidate:
    tree_predicate = {
        "feature": predicate["feature"],
        "op": "<=",
        "threshold": float(predicate["threshold"]),
        "well_direction": predicate["well_direction"],
    }
    tree = {"predicate": tree_predicate, "le": le.tree, "gt": gt.tree}
    return Candidate(
        tree=tree,
        correct=le.correct + gt.correct,
        depth=1 + max(le.depth, gt.depth),
        predicate_count=1 + le.predicate_count + gt.predicate_count,
        serial=tree_serial(tree),
        well_range=(
            min(le.well_range[0], gt.well_range[0]),
            max(le.well_range[1], gt.well_range[1]),
        ),
    )


def update_state_best(
    best: dict[tuple[int, int], Candidate], candidate: Candidate
) -> None:
    current = best.get(candidate.well_range)
    if current is None or candidate.key < current.key:
        best[candidate.well_range] = candidate


def best_depth1_by_range(
    rows: Sequence[Mapping[str, Any]],
    expected: Mapping[str, str],
    predicates: Sequence[Mapping[str, Any]],
    counters: Counter[str],
) -> dict[tuple[int, int], Candidate]:
    best: dict[tuple[int, int], Candidate] = {}
    leaf_by_range: dict[tuple[int, int], Candidate] = {}
    for label in EXPECTED_LABELS:
        candidate = leaf_candidate(label, rows, expected)
        counters["leaf_candidates_evaluated"] += 1
        update_state_best(leaf_by_range, candidate)
        update_state_best(best, candidate)

    for predicate in predicates:
        le_rows = [
            row for row in rows if predicate_value(row, predicate)
        ]
        gt_rows = [
            row for row in rows if not predicate_value(row, predicate)
        ]
        if not le_rows or not gt_rows:
            counters["empty_split_candidates_rejected"] += 1
            continue
        le_leaves: dict[tuple[int, int], Candidate] = {}
        gt_leaves: dict[tuple[int, int], Candidate] = {}
        for label in EXPECTED_LABELS:
            update_state_best(
                le_leaves, leaf_candidate(label, le_rows, expected)
            )
            update_state_best(
                gt_leaves, leaf_candidate(label, gt_rows, expected)
            )
        for le in le_leaves.values():
            for gt in gt_leaves.values():
                counters["node_range_combinations_evaluated"] += 1
                if not sign_valid(
                    predicate["feature"], le.well_range, gt.well_range
                ):
                    counters["sign_invalid_combinations_rejected"] += 1
                    continue
                counters["sign_valid_node_candidates"] += 1
                update_state_best(
                    best, combine_candidate(predicate, le, gt)
                )
    return best


def fit_monotone_tree(
    calibration_rows: Sequence[Mapping[str, Any]],
    expected: Mapping[str, str],
) -> tuple[Candidate, list[dict[str, Any]], dict[str, int]]:
    predicates = predicate_candidates(calibration_rows)
    counters: Counter[str] = Counter()
    global_candidates: list[Candidate] = []
    for label in EXPECTED_LABELS:
        global_candidates.append(
            leaf_candidate(label, calibration_rows, expected)
        )
        counters["leaf_candidates_evaluated"] += 1

    for predicate in predicates:
        le_rows = [
            row for row in calibration_rows
            if predicate_value(row, predicate)
        ]
        gt_rows = [
            row for row in calibration_rows
            if not predicate_value(row, predicate)
        ]
        if not le_rows or not gt_rows:
            counters["empty_root_candidates_rejected"] += 1
            continue
        le_candidates = best_depth1_by_range(
            le_rows, expected, predicates, counters
        )
        gt_candidates = best_depth1_by_range(
            gt_rows, expected, predicates, counters
        )
        for le in le_candidates.values():
            for gt in gt_candidates.values():
                counters["root_range_combinations_evaluated"] += 1
                if not sign_valid(
                    predicate["feature"], le.well_range, gt.well_range
                ):
                    counters["sign_invalid_root_combinations_rejected"] += 1
                    continue
                counters["sign_valid_root_candidates"] += 1
                global_candidates.append(
                    combine_candidate(predicate, le, gt)
                )
    best = min(global_candidates, key=lambda item: item.key)
    if best.depth > 2:
        raise RuntimeError("monotone rule depth exceeds two")
    return best, predicates, dict(counters)


def apply_tree(
    row: Mapping[str, Any], tree: Mapping[str, Any]
) -> tuple[str, str]:
    node = tree
    path: list[str] = []
    while "label" not in node:
        predicate = node["predicate"]
        branch = "le" if predicate_value(row, predicate) else "gt"
        path.append(
            f"{predicate['feature']}<=%"
            f"{float(predicate['threshold']):.9g}:{branch}"
        )
        node = node[branch]
    return str(node["label"]), "|".join(path).replace("<=%", "<=")


def active_predicates(tree: Mapping[str, Any]) -> list[dict[str, Any]]:
    if "label" in tree:
        return []
    output = [dict(tree["predicate"])]
    output.extend(active_predicates(tree["le"]))
    output.extend(active_predicates(tree["gt"]))
    return output


def verify_tree_contract(tree: Mapping[str, Any]) -> None:
    def walk(node: Mapping[str, Any]) -> tuple[int, int, int]:
        if "label" in node:
            if node["label"] not in EXPECTED_LABELS:
                raise RuntimeError(f"unknown tree leaf: {node['label']}")
            well = 1 if node["label"] == WELL else 0
            return 0, well, well
        predicate = node["predicate"]
        feature = predicate.get("feature")
        if feature not in RULE_FEATURES or feature == "footprint_area_m2":
            raise RuntimeError(f"forbidden primary predicate: {feature}")
        if predicate.get("op") != "<=":
            raise RuntimeError("primary predicate operator is not <=")
        if predicate.get("well_direction") != WELL_DIRECTION[feature]:
            raise RuntimeError(f"predicate direction drift: {feature}")
        left_depth, left_min, left_max = walk(node["le"])
        right_depth, right_min, right_max = walk(node["gt"])
        if not sign_valid(
            feature, (left_min, left_max), (right_min, right_max)
        ):
            raise RuntimeError(f"tree sign contract failed at {feature}")
        return (
            1 + max(left_depth, right_depth),
            min(left_min, right_min),
            max(left_max, right_max),
        )

    depth, _minimum, _maximum = walk(tree)
    if depth > 2:
        raise RuntimeError(f"primary tree depth {depth} exceeds two")


def load_v2_module() -> Any:
    spec = importlib.util.spec_from_file_location(
        "boundary_map_v2_for_v3_address", V2_SCRIPT
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {V2_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def crop_box_4x3(
    mask: np.ndarray, image_width: int, image_height: int
) -> list[int]:
    y_coord, x_coord = np.nonzero(mask[:image_height, :image_width])
    if not len(x_coord):
        raise RuntimeError("semantic address lies outside its source image")
    target_width = int(
        x_coord.max() - x_coord.min() + 1 + 2 * CROP_MARGIN_PX
    )
    target_height = int(
        y_coord.max() - y_coord.min() + 1 + 2 * CROP_MARGIN_PX
    )
    width = max(
        CROP_MIN_WIDTH,
        target_width,
        int(math.ceil(target_height * 4.0 / 3.0)),
    )
    width = int(math.ceil(width / 16.0) * 16)
    maximum_width = min(
        image_width, int(math.floor(image_height * 4.0 / 3.0))
    )
    maximum_width = max(16, maximum_width - (maximum_width % 16))
    width = min(width, maximum_width)
    height = int(width * 3 // 4)
    centre_x = float(x_coord.min() + x_coord.max()) / 2.0
    centre_y = float(y_coord.min() + y_coord.max()) / 2.0
    x0 = int(round(centre_x - width / 2.0))
    y0 = int(round(centre_y - height / 2.0))
    x0 = min(max(0, x0), image_width - width)
    y0 = min(max(0, y0), image_height - height)
    return [x0, y0, x0 + width, y0 + height]


def semantic_addresses(
    wanted: set[str],
) -> dict[str, list[dict[str, Any]]]:
    output: dict[str, list[dict[str, Any]]] = {
        building_id: [] for building_id in wanted
    }
    if not wanted:
        return output
    for path in sorted(C001_REGION_DIR.glob("*.npz")):
        with np.load(path, allow_pickle=False) as archive:
            region_ids = np.asarray(archive["region_ids"], dtype=np.int32)
            metadata = json.loads(str(archive["metadata_json"]))
        region_lookup: dict[str, list[int]] = defaultdict(list)
        for region_id, record in metadata.get("regions", {}).items():
            building_id = str(record.get("building_id", ""))
            if building_id in wanted:
                region_lookup[building_id].append(int(region_id))
        for building_id, identifiers in region_lookup.items():
            mask = np.isin(
                region_ids, np.asarray(identifiers, dtype=np.int32)
            )
            support = int(np.count_nonzero(mask))
            if not support:
                continue
            height, width = region_ids.shape
            output[building_id].append(
                {
                    "stem": path.stem,
                    "view": f"{path.stem}.JPG",
                    "support": support,
                    "crop_xyxy": crop_box_4x3(mask, width, height),
                }
            )
    return output


def select_semantic_pairs(
    views: Sequence[Mapping[str, Any]],
    crop_source: str,
) -> list[dict[str, Any]]:
    pairs: list[dict[str, Any]] = []
    for left, right in itertools.combinations(views, 2):
        pairs.append(
            {
                "view_a_record": left,
                "view_b_record": right,
                "minimum_support": min(
                    int(left["support"]), int(right["support"])
                ),
                "support_sum": int(left["support"]) + int(right["support"]),
            }
        )
    pairs.sort(
        key=lambda item: (
            -item["minimum_support"],
            -item["support_sum"],
            item["view_a_record"]["stem"],
            item["view_b_record"]["stem"],
        )
    )
    return [
        {
            "pair_rank": rank,
            "view_a": pair["view_a_record"]["view"],
            "view_b": pair["view_b_record"]["view"],
            "crop_source": crop_source,
            "crop_a_xyxy": list(pair["view_a_record"]["crop_xyxy"]),
            "crop_b_xyxy": list(pair["view_b_record"]["crop_xyxy"]),
        }
        for rank, pair in enumerate(pairs[:MAX_PAIRS], start=1)
    ]


def locked_pjpl_pairs(
    building_id: str,
    addresses: Mapping[str, Sequence[Mapping[str, Any]]],
) -> list[dict[str, Any]]:
    short = building_id.removeprefix("DEBY_LOD2_")
    pjpl_rows = [
        row for row in read_csv(S3AP_PJPL)
        if row["building_id"] == short
    ]
    by_stem = {
        str(row["stem"]): row for row in addresses.get(building_id, [])
    }
    views: list[dict[str, Any]] = []
    for row in pjpl_rows:
        stem = row["view_stem"]
        if stem not in by_stem:
            raise RuntimeError(
                f"{building_id} locked PJPL view has no semantic address: {stem}"
            )
        address = by_stem[stem]
        views.append(
            {
                "stem": stem,
                "view": row["view"],
                "support": int(row["address_pixel_count"]),
                "crop_xyxy": address["crop_xyxy"],
            }
        )
    expected_count = 6 if short == "4907199" else 3
    if len(views) != expected_count:
        raise RuntimeError(
            f"{building_id} locked PJPL count {len(views)} != {expected_count}"
        )
    return select_semantic_pairs(
        views, "s3ap_locked_pjpl_semantic_region"
    )


def projected_pairs_for(
    queue_ids: set[str],
) -> dict[str, list[dict[str, Any]]]:
    non_c001 = queue_ids - set(C001_IDS)
    if not non_c001:
        return {}
    v2 = load_v2_module()
    old = v2._load_old()  # noqa: SLF001 - locked v2 address implementation
    geometries, _areas = old.load_footprints()
    heights = old.load_reference_heights(non_c001)
    scene_reference = json.loads(
        old.SCENE_REF.read_text(encoding="utf-8")
    )
    width, height, parameters = old.aux.parse_cam_model(old.CAMERAS)
    cameras = [
        camera
        for camera in old.aux.parse_cameras(old.IMAGES, scene_reference)
        if (old.IMAGE_DIR / camera.name).is_file()
    ]
    output: dict[str, list[dict[str, Any]]] = {}
    for building_id in sorted(non_c001):
        pairs = v2.fm_projection_pairs(
            old,
            building_id,
            geometries[building_id],
            heights[building_id],
            cameras,
            width,
            height,
            parameters,
            scene_reference,
        )
        output[building_id] = [
            {
                "pair_rank": int(pair["pair_rank"]),
                "view_a": pair["view_a"],
                "view_b": pair["view_b"],
                "crop_source": (
                    "v2_projected_footprint_at_LoD2_height_"
                    "projection_classification_only"
                ),
                "crop_a_xyxy": list(pair["crop_a_xyxy"]),
                "crop_b_xyxy": list(pair["crop_b_xyxy"]),
            }
            for pair in pairs
        ]
    return output


def model_contract() -> dict[str, Any]:
    environment = json.loads(ENV_MANIFEST.read_text(encoding="utf-8"))
    config = json.loads(S3AP_DIAL_CONFIG.read_text(encoding="utf-8"))
    runtime = environment["runtime_lock"]
    model = environment["model"]
    code = environment["code"]
    locked_runtime = config["runtime_lock"]
    checks = {
        "model_revision": model["revision"] == locked_runtime["model_revision"],
        "weights_sha256": (
            model["weights_sha256"] == locked_runtime["weights_sha256"]
        ),
        "weights_bytes": (
            int(model["weights_bytes"]) == int(locked_runtime["weights_bytes"])
        ),
        "docker_image_id": (
            runtime["docker_image_id"] == locked_runtime["docker_image_id"]
        ),
        "mast3r_commit": (
            code["mast3r_commit"] == locked_runtime["mast3r_commit"]
        ),
        "dust3r_commit": (
            code["dust3r_commit"] == locked_runtime["dust3r_commit"]
        ),
        "croco_commit": (
            code["croco_commit"] == locked_runtime["croco_commit"]
        ),
    }
    if not all(checks.values()):
        raise RuntimeError(f"S3Ap environment/config lock mismatch: {checks}")
    return {
        "model_id": model["id"],
        "model_revision": model["revision"],
        "weights_sha256": model["weights_sha256"],
        "weights_bytes": int(model["weights_bytes"]),
        "model_config_sha256": model["config_sha256"],
        "docker_image_tag": runtime["docker_image_tag"],
        "docker_image_id": runtime["docker_image_id"],
        "mast3r_commit": code["mast3r_commit"],
        "dust3r_commit": code["dust3r_commit"],
        "croco_commit": code["croco_commit"],
        "environment_manifest": rel(ENV_MANIFEST),
        "environment_manifest_sha256": sha256_file(ENV_MANIFEST),
        "dense_dial_config": rel(S3AP_DIAL_CONFIG),
        "dense_dial_config_sha256": sha256_file(S3AP_DIAL_CONFIG),
        "raw_definition": config["raw_definition"],
        "reprojection_threshold_px": 2.0,
        "summary_pair_rule": config["summary_pair_rule"],
        "coverage_rule": config["coverage"],
        "lock_checks": checks,
        "learning_runs_started": 0,
        "new_inference_type": NEW_INFERENCE_TYPE,
    }


def build_jobs(
    primary_rows: Sequence[Mapping[str, Any]],
    metric_rows: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], list[str]]:
    primary = {row["building_id"]: row for row in primary_rows}
    areas = {
        row["building_id"]: float(row["footprint_area_m2"])
        for row in metric_rows
    }
    primary_nonwell = {
        building_id for building_id, row in primary.items()
        if row["primary_assignment"] != WELL
    }
    queue_ids = primary_nonwell | set(MANUAL_TEXTURELESS_ORDER)
    ordered: list[str] = []
    for building_id in MANUAL_TEXTURELESS_ORDER:
        if building_id in queue_ids and building_id not in ordered:
            ordered.append(building_id)
    for building_id in C001_IDS:
        if building_id in queue_ids and building_id not in ordered:
            ordered.append(building_id)
    remaining = sorted(
        queue_ids - set(ordered),
        key=lambda building_id: (-areas[building_id], building_id),
    )
    ordered.extend(remaining)
    if set(ordered) != queue_ids or len(ordered) != len(queue_ids):
        raise RuntimeError("FM dense queue ordering lost or duplicated identifiers")

    semantic_wanted = queue_ids & set(C001_IDS)
    addresses = semantic_addresses(semantic_wanted)
    projected = projected_pairs_for(queue_ids)
    jobs: list[dict[str, Any]] = []
    no_pairs: list[str] = []
    for priority_rank, building_id in enumerate(ordered, start=1):
        if building_id in LOCKED_S3AP_PAIR_IDS:
            pairs = locked_pjpl_pairs(building_id, addresses)
        elif building_id in set(C001_IDS):
            pairs = select_semantic_pairs(
                addresses.get(building_id, []),
                "c001_frozen_semantic_region",
            )
        else:
            pairs = projected.get(building_id, [])
        if not pairs:
            no_pairs.append(building_id)
        manual_mandatory = building_id in set(MANUAL_TEXTURELESS_ORDER)
        primary_flag = building_id in primary_nonwell
        reasons: list[str] = []
        if primary_flag:
            reasons.append("primary_nonwell")
        if manual_mandatory:
            reasons.append("manual_textureless_mandatory")
        if manual_mandatory:
            group = "manual_textureless"
        elif building_id in set(C001_IDS):
            group = "canonical_C001"
        else:
            group = "remaining_area_desc"
        jobs.append(
            {
                "building_id": building_id,
                "priority_rank": priority_rank,
                "priority_group": group,
                "primary_assignment": primary[building_id][
                    "primary_assignment"
                ],
                "queue_inclusion_reason": "+".join(reasons),
                "pairs": pairs,
            }
        )
    return {"model": model_contract(), "jobs": jobs}, no_pairs


def prepare_fit() -> None:
    inventory = reconstruct_label_inventory()
    canonical_c001 = inventory["canonical"] & set(C001_IDS)
    excluded_c001 = set(C001_IDS) - inventory["canonical"]
    if len(canonical_c001) != 15 or excluded_c001 != {
        "DEBY_LOD2_108247349",
        "DEBY_LOD2_4907194",
        "DEBY_LOD2_4908179",
    }:
        raise RuntimeError(
            "canonical C001 priority inventory is not locked 15/18"
        )
    metric_rows = inventory["v2_rows"]
    typed_rows = [
        {
            **row,
            **{
                feature: float(row[feature])
                for feature in FEATURES_WITH_SMALL
            },
        }
        for row in metric_rows
    ]
    row_by_id = {row["building_id"]: row for row in typed_rows}
    calibration_rows = [
        row_by_id[building_id]
        for building_id in sorted(inventory["calibration"])
    ]
    best, predicates, search_counters = fit_monotone_tree(
        calibration_rows, inventory["expected"]
    )
    verify_tree_contract(best.tree)

    primary_rows: list[dict[str, Any]] = []
    for row in sorted(typed_rows, key=lambda item: item["building_id"]):
        building_id = row["building_id"]
        assignment, path = apply_tree(row, best.tree)
        if building_id in inventory["manual_ids"]:
            label_source = "manual_review_judgments"
        elif building_id in inventory["dense_success"]:
            label_source = "dense_success_positive"
        else:
            label_source = "unlabeled"
        manual_split = (
            "calibration"
            if building_id in inventory["manual_calibration"]
            else (
                "validation"
                if building_id in inventory["manual_validation"]
                else "not_manual"
            )
        )
        dense_membership = (
            "calibration"
            if building_id in inventory["dense_calibration"]
            else (
                "validation"
                if building_id in inventory["dense_validation"]
                else "not_dense_success"
            )
        )
        combined_split = (
            "calibration"
            if building_id in inventory["calibration"]
            else (
                "validation"
                if building_id in inventory["validation"]
                else "unlabeled"
            )
        )
        primary_rows.append(
            {
                "building_id": building_id,
                "label_source": label_source,
                "manual_split": manual_split,
                "dense_split": dense_membership,
                "combined_split": combined_split,
                "expected_tier": inventory["expected"].get(building_id, ""),
                "primary_assignment": assignment,
                "primary_rule_path": path,
                "primary_nonwell_candidate": assignment != WELL,
                "learning_runs_started": 0,
                "new_inference_type": "none; rule fit from frozen attributes",
            }
        )

    calibration_correct = sum(
        row["primary_assignment"] == row["expected_tier"]
        for row in primary_rows if row["combined_split"] == "calibration"
    )
    validation_rows = [
        row for row in primary_rows if row["combined_split"] == "validation"
    ]
    validation_correct = sum(
        row["primary_assignment"] == row["expected_tier"]
        for row in validation_rows
    )
    constant_correct = sum(
        row["expected_tier"] == WELL for row in validation_rows
    )
    validation_accuracy = validation_correct / 79
    constant_accuracy = constant_correct / 79
    gain = validation_accuracy - constant_accuracy
    rule_status = "passed_gain" if gain >= 0 else "failed_gain"
    active = active_predicates(best.tree)
    if any(item["feature"] == "footprint_area_m2" for item in active):
        raise RuntimeError("footprint area entered the primary rule")

    rule_payload = {
        "schema": "jointbuildgs.boundary_map_v3.depth2_monotone_rule.v1",
        "created_utc": now(),
        "maximum_depth": 2,
        "objective": "calibration79 exact expected-tier agreement",
        "tie_break": (
            "higher exact count; shallower depth; fewer predicates; "
            "lexicographic serialized rule; leaf-count ties use "
            "well_textured, textureless_correspondence_anchored, "
            "outline_only order"
        ),
        "threshold_source": (
            "midpoints of calibration79-only unique feature values"
        ),
        "rule_features": list(RULE_FEATURES),
        "feature_sources": {
            feature: f"docs/boundary_map_v2_metrics.csv::{feature}"
            for feature in FEATURES_WITH_SMALL
        },
        "footprint_area_role": (
            "post-rule indeterminate_small assignment only; no primary "
            "predicate candidates generated"
        ),
        "feature_well_direction": WELL_DIRECTION,
        "monotone_candidate_contract": (
            "at every node, max(binary well indicator in the adverse child "
            "subtree) <= min(binary well indicator in the favorable child "
            "subtree); textureless and outline both have binary indicator 0"
        ),
        "excluded_candidate_rules": {
            "footprint_area_m2": (
                "not generated for the primary rule; used only by the "
                "post-rule indeterminate_small assignment"
            ),
            "larger_is_well_features": (
                "reject any node combination whose <= child is more "
                "well-oriented than its > child"
            ),
            "texture_low_gradient_fraction": (
                "reject any node combination whose > child is more "
                "well-oriented than its <= child"
            ),
        },
        "predicate_candidate_count": len(predicates),
        "predicate_candidate_count_by_feature": dict(
            sorted(Counter(item["feature"] for item in predicates).items())
        ),
        "search_counters": search_counters,
        "manual_split_seed": MANUAL_SPLIT_SEED,
        "dense_split_seed": DENSE_SPLIT_SEED,
        "calibration_buildings": sorted(inventory["calibration"]),
        "validation_buildings_locked_not_used_for_fit": sorted(
            inventory["validation"]
        ),
        "calibration_n": 79,
        "calibration_correct": calibration_correct,
        "validation_n": 79,
        "validation_correct_primary_pre_fm": validation_correct,
        "validation_accuracy_primary_pre_fm": validation_accuracy,
        "constant_classifier": WELL,
        "constant_correct": constant_correct,
        "constant_accuracy": constant_accuracy,
        "accuracy_gain": gain,
        "rule_status": rule_status,
        "tree": best.tree,
        "tree_sha256": sha256_json(best.tree),
        "active_predicates": active,
        "footprint_area_primary_predicate_count": 0,
        "learning_runs_started": 0,
        "new_inference_runs": 0,
        "interpretation_or_verdict": None,
    }

    jobs_payload, no_pairs = build_jobs(primary_rows, typed_rows)
    queue_ids = {job["building_id"] for job in jobs_payload["jobs"]}
    expected_queue = {
        row["building_id"] for row in primary_rows
        if row["primary_assignment"] != WELL
    } | set(MANUAL_TEXTURELESS_ORDER)
    if queue_ids != expected_queue:
        raise RuntimeError("FM dense queue set differs from primary-nonwell union")
    if no_pairs:
        raise RuntimeError(
            f"FM dense queue has buildings without address pairs: {no_pairs}"
        )
    inventory["json"].update(
        {
            "primary_rule_sha256": rule_payload["tree_sha256"],
            "primary_calibration_correct": calibration_correct,
            "primary_validation_correct": validation_correct,
            "primary_validation_accuracy": validation_accuracy,
            "constant_validation_accuracy": constant_accuracy,
            "primary_accuracy_gain": gain,
            "rule_status": rule_status,
            "primary_nonwell_count": sum(
                row["primary_assignment"] != WELL for row in primary_rows
            ),
            "fm_dense_queue_formula": (
                "primary_assignment!=well_textured union exact manual "
                "textureless four"
            ),
            "fm_dense_queue_count": len(queue_ids),
            "fm_dense_queue_buildings": sorted(queue_ids),
            "fm_dense_queue_no_pair_buildings": [],
            "canonical_c001_priority_count": len(canonical_c001),
            "canonical_c001_priority_buildings": sorted(canonical_c001),
            "noncanonical_c001_excluded_count": len(excluded_c001),
            "noncanonical_c001_excluded_buildings": sorted(excluded_c001),
        }
    )

    atomic_csv(PRIMARY_CSV, primary_rows, PRIMARY_FIELDS)
    atomic_json(RULE_JSON, rule_payload)
    atomic_json(LABEL_INVENTORY, inventory["json"])
    atomic_json(FM_JOBS, jobs_payload)


def outline_observable(row: Mapping[str, Any]) -> bool:
    return (
        (as_int(row.get("representative_view_count")) or 0) >= 2
        and (as_float(row.get("outline_inframe_frac_max")) or 0.0) > 0.0
        and (as_int(row.get("outline_valid_pixel_count_max")) or 0) >= 3
    )


def dense_complete(row: Mapping[str, Any] | None) -> bool:
    if row is None or row.get("status") != "complete":
        return False
    if row.get("measurement_complete") not in (None, ""):
        return as_bool(row.get("measurement_complete"))
    return True


def prerequisite_missing_row(row: Mapping[str, Any] | None) -> bool:
    if row is None:
        return False
    text = " ".join(
        str(row.get(field, ""))
        for field in ("status", "failure_reason")
    ).lower()
    return "prerequisite" in text or "locked_frame" in text


def validate_dense_row(row: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    building_id = row.get("building_id", "")
    if not dense_complete(row):
        errors.append(f"{building_id}:status={row.get('status') or 'missing'}")
        return errors
    selected = as_int(row.get("selected_dlt_point_count"))
    inside = as_int(row.get("footprint_inside_point_count"))
    selected_pairs = as_int(row.get("selected_pair_count"))
    completed_pairs = as_int(row.get("completed_pair_count"))
    coverage = as_float(row.get("coverage_ratio"))
    elapsed = as_float(row.get("elapsed_seconds"))
    if selected is None or selected < 0:
        errors.append(f"{building_id}:selected_dlt_point_count")
    if inside is None or inside < 0:
        errors.append(f"{building_id}:footprint_inside_point_count")
    if (
        selected is not None
        and inside is not None
        and inside > selected
    ):
        errors.append(f"{building_id}:inside_gt_selected")
    if selected_pairs is None or selected_pairs < 1:
        errors.append(f"{building_id}:selected_pair_count")
    if (
        completed_pairs is None
        or completed_pairs < 1
        or (
            selected_pairs is not None
            and completed_pairs != selected_pairs
        )
    ):
        errors.append(f"{building_id}:completed_pair_count")
    if coverage is None or not 0.0 <= coverage <= 1.0:
        errors.append(f"{building_id}:coverage_ratio")
    if elapsed is None or elapsed < 0:
        errors.append(f"{building_id}:elapsed_seconds")
    z_median = as_float(row.get("inside_z_median_m"))
    z_mad = as_float(row.get("inside_z_mad_m"))
    if inside is not None and inside > 0:
        if z_median is None:
            errors.append(f"{building_id}:inside_z_median_m")
        if z_mad is None or z_mad < 0:
            errors.append(f"{building_id}:inside_z_mad_m")
    if row.get("learning_runs_started") != "0":
        errors.append(f"{building_id}:learning_runs_started")
    if row.get("new_inference_type") != NEW_INFERENCE_TYPE:
        errors.append(f"{building_id}:new_inference_type")
    if (as_int(row.get("new_mast3r_inference_runs")) or 0) < 0:
        errors.append(f"{building_id}:new_mast3r_inference_runs")
    return errors


def write_partial(
    expected_ids: set[str],
    measured_by_id: Mapping[str, Mapping[str, Any]],
    reasons: Sequence[str],
) -> None:
    incomplete = sorted(
        building_id for building_id in expected_ids
        if not dense_complete(measured_by_id.get(building_id))
    )
    missing = sorted(expected_ids - set(measured_by_id))
    unexpected = sorted(set(measured_by_id) - expected_ids)
    payload = {
        "schema": "jointbuildgs.boundary_map_v3.partial.v1",
        "created_utc": now(),
        "status": "partial_dense_measurements",
        "expected_building_count": len(expected_ids),
        "recorded_building_count": len(measured_by_id),
        "complete_building_count": sum(
            dense_complete(measured_by_id.get(building_id))
            for building_id in expected_ids
        ),
        "missing_buildings": missing,
        "incomplete_buildings": incomplete,
        "unexpected_buildings": unexpected,
        "reasons": list(reasons),
        "source_sha256": {
            rel(path): sha256_file(path)
            for path in (
                PRIMARY_CSV,
                RULE_JSON,
                LABEL_INVENTORY,
                FM_JOBS,
                FM_MEASUREMENTS,
                FM_PROGRESS,
                FM_RUN_MANIFEST,
            )
            if path.is_file()
        },
        "learning_runs_started": 0,
        "new_inference_type": NEW_INFERENCE_TYPE,
        "interpretation_or_verdict": None,
    }
    atomic_json(PARTIAL_MANIFEST, payload)
    lines = [
        "# Boundary map v3 partial measurement record",
        "",
        f"- status: `{payload['status']}`",
        f"- expected buildings: {payload['expected_building_count']}",
        f"- recorded buildings: {payload['recorded_building_count']}",
        f"- complete buildings: {payload['complete_building_count']}",
        f"- missing buildings: {len(missing)}",
        f"- incomplete buildings: {len(incomplete)}",
        f"- unexpected buildings: {len(unexpected)}",
        "",
        "## Recorded reasons",
        "",
        *[f"- {reason}" for reason in reasons],
        "",
        "Public boundary_map_v3 outputs were not written by this invocation.",
        "All recorded rows retain `learning_runs_started=0`.",
    ]
    atomic_text(PARTIAL_SUMMARY, "\n".join(lines) + "\n")


def load_dense_results(
    expected_ids: set[str],
) -> tuple[
    dict[str, dict[str, str]],
    list[str],
    str,
    list[str],
]:
    notes: list[str] = []
    if not FM_MEASUREMENTS.is_file():
        rows: list[dict[str, str]] = []
        notes.append("fm_dense_measurements.csv missing")
    else:
        rows = read_csv(FM_MEASUREMENTS)
    identifiers = [row.get("building_id", "") for row in rows]
    duplicates = sorted(
        building_id for building_id, count in Counter(identifiers).items()
        if building_id and count > 1
    )
    if duplicates:
        raise RuntimeError(f"duplicate FM dense building rows: {duplicates}")
    measured_by_id = {
        row["building_id"]: row for row in rows if row.get("building_id")
    }
    missing = sorted(expected_ids - set(measured_by_id))
    unexpected = sorted(set(measured_by_id) - expected_ids)
    if missing:
        notes.append(f"missing building rows: {missing}")
    if unexpected:
        raise RuntimeError(f"unexpected FM dense building rows: {unexpected}")
    for building_id in sorted(expected_ids & set(measured_by_id)):
        if dense_complete(measured_by_id[building_id]):
            row_errors = validate_dense_row(measured_by_id[building_id])
            if row_errors:
                notes.extend(row_errors)
                measured_by_id[building_id]["status"] = "invalid_contract"
    if not FM_PROGRESS.is_file():
        progress: dict[str, Any] = {}
        notes.append("fm_dense_progress.json missing")
    else:
        progress = json.loads(FM_PROGRESS.read_text(encoding="utf-8"))
        if int(progress.get("learning_runs_started", -1)) != 0:
            raise RuntimeError("fm_dense_progress learning_runs_started drift")
    if not FM_RUN_MANIFEST.is_file():
        run_manifest: dict[str, Any] = {}
        notes.append("fm_dense_manifest.json missing")
    else:
        run_manifest = json.loads(
            FM_RUN_MANIFEST.read_text(encoding="utf-8")
        )
        if int(run_manifest.get("learning_runs_started", -1)) != 0:
            raise RuntimeError("fm_dense_manifest learning_runs_started drift")
        if run_manifest.get("new_inference_type") != NEW_INFERENCE_TYPE:
            raise RuntimeError("fm_dense_manifest inference-type drift")
        fingerprint = str(run_manifest.get("input_fingerprint", ""))
        if not fingerprint:
            raise RuntimeError("fm_dense_manifest input fingerprint missing")
        if progress.get("input_fingerprint") != fingerprint:
            raise RuntimeError("FM dense progress/manifest fingerprint drift")
        for row in rows:
            if row.get("input_fingerprint") != fingerprint:
                raise RuntimeError(
                    f"{row.get('building_id')} FM dense fingerprint drift"
                )
            if row.get("new_inference_type") != NEW_INFERENCE_TYPE:
                raise RuntimeError(
                    f"{row.get('building_id')} FM dense inference-type drift"
                )
        pair_rows = read_csv(FM_PAIRS) if FM_PAIRS.is_file() else []
        if not pair_rows:
            raise RuntimeError("fm_dense_pairs.csv missing or empty")
        for row in pair_rows:
            if (
                row.get("input_fingerprint") != fingerprint
                or row.get("new_inference_type") != NEW_INFERENCE_TYPE
                or row.get("learning_runs_started") != "0"
            ):
                raise RuntimeError(
                    "FM dense pair fingerprint/inference/learning drift"
                )
        output_hashes = run_manifest.get("output_sha256", {})
        required_hashed = {
            rel(FM_MEASUREMENTS),
            rel(FM_PAIRS),
            rel(FM_PROGRESS),
        }
        if not required_hashed <= set(output_hashes):
            raise RuntimeError("FM dense manifest required output hashes missing")
        for relative, expected_sha in output_hashes.items():
            output_path = (REPO / relative).resolve()
            try:
                output_path.relative_to(REPO.resolve())
            except ValueError as exc:
                raise RuntimeError(
                    f"FM dense output hash path escapes repository: {relative}"
                ) from exc
            if not output_path.is_file():
                raise RuntimeError(
                    f"FM dense hashed output missing: {relative}"
                )
            if sha256_file(output_path) != expected_sha:
                raise RuntimeError(
                    f"FM dense output SHA256 drift: {relative}"
                )
    accepted_statuses = {
        "complete",
        "budget_exhausted",
        "partial",
        "time_budget_reached",
    }
    progress_status = str(progress.get("status", "partial"))
    manifest_status = str(run_manifest.get("status", progress_status))
    if progress_status not in accepted_statuses:
        raise RuntimeError(
            f"unsupported fm_dense_progress status={progress_status}"
        )
    if manifest_status not in accepted_statuses:
        raise RuntimeError(
            f"unsupported fm_dense_manifest status={manifest_status}"
        )
    reproduction = measured_by_id.get("DEBY_LOD2_4907199")
    if dense_complete(reproduction) and reproduction.get(
        "reproduction_check_passed"
    ) not in (
        "true",
        "1",
    ):
        raise RuntimeError(
            "4907199 complete locked S3Ap reproduction check is not true"
        )
    incomplete = sorted(
        building_id for building_id in expected_ids
        if not dense_complete(measured_by_id.get(building_id))
    )
    prerequisite_missing = sorted(
        building_id for building_id in incomplete
        if prerequisite_missing_row(measured_by_id.get(building_id))
    )
    budget_incomplete = sorted(
        set(incomplete) - set(prerequisite_missing)
    )
    complete_count = len(expected_ids) - len(incomplete)
    overall_status = (
        "complete"
        if not incomplete
        and not notes
        and progress_status == "complete"
        and manifest_status == "complete"
        else (
            "mixed_prerequisite_and_budget_incomplete"
            if prerequisite_missing and budget_incomplete
            else (
                "prerequisite_missing"
                if prerequisite_missing
                else (
                    "budget_exhausted"
                    if "budget_exhausted"
                    in {progress_status, manifest_status}
                    or "time_budget_reached"
                    in {progress_status, manifest_status}
                    else "partial"
                )
            )
        )
    )
    if incomplete or notes:
        write_partial(expected_ids, measured_by_id, notes)
    notes.append(
        f"complete_buildings={complete_count}/{len(expected_ids)}"
    )
    notes.append(
        f"prerequisite_missing_buildings={len(prerequisite_missing)}"
    )
    notes.append(f"budget_incomplete_buildings={len(budget_incomplete)}")
    return measured_by_id, incomplete, overall_status, notes


def fm_candidate_set(
    primary_rows: Sequence[Mapping[str, Any]],
) -> set[str]:
    return {
        row["building_id"] for row in primary_rows
        if row["primary_assignment"] != WELL
    } | set(MANUAL_TEXTURELESS_ORDER)


def formula_assignment(
    building_id: str,
    primary_assignment: str,
    metric_row: Mapping[str, Any],
    dense_row: Mapping[str, Any] | None,
    threshold: int,
    candidates: set[str],
) -> str:
    if building_id not in candidates:
        return primary_assignment
    if not dense_complete(dense_row):
        return primary_assignment
    count = as_int(dense_row.get("footprint_inside_point_count"))
    if count is not None and count >= threshold:
        return TEXTURELESS
    if outline_observable(metric_row):
        return OUTLINE
    return UNOBSERVABLE


def threshold_candidates(
    measured_by_id: Mapping[str, Mapping[str, Any]],
    calibration_candidates: set[str],
) -> list[int]:
    counts = sorted(
        {
            as_int(measured_by_id[building_id].get(
                "footprint_inside_point_count"
            ))
            for building_id in calibration_candidates
            if dense_complete(measured_by_id.get(building_id))
        }
    )
    if any(value is None for value in counts):
        raise RuntimeError("calibration dense count missing")
    return sorted(
        {
            FM_MIN_COUNT,
            *[
                int(value) for value in counts
                if value is not None and value >= FM_MIN_COUNT
            ],
            *[
                int(value) + 1 for value in counts
                if value is not None
            ],
        }
    )


def choose_dense_threshold(
    metric_by_id: Mapping[str, Mapping[str, Any]],
    primary_by_id: Mapping[str, Mapping[str, Any]],
    measured_by_id: Mapping[str, Mapping[str, Any]],
    expected: Mapping[str, str],
    calibration: set[str],
    candidates: set[str],
) -> tuple[int, list[dict[str, Any]]]:
    calibration_candidates = calibration & candidates
    completed_calibration_candidates = {
        building_id for building_id in calibration_candidates
        if dense_complete(measured_by_id.get(building_id))
    }
    choices = threshold_candidates(
        measured_by_id, calibration_candidates
    )
    evaluations: list[dict[str, Any]] = []
    for threshold in choices:
        recorded: dict[str, str] = {}
        for building_id in sorted(calibration):
            recorded[building_id] = formula_assignment(
                building_id,
                primary_by_id[building_id]["primary_assignment"],
                metric_by_id[building_id],
                measured_by_id.get(building_id),
                threshold,
                candidates,
            )
        correct = sum(
            recorded[building_id] == expected[building_id]
            for building_id in calibration
        )
        actual_textureless = {
            building_id for building_id in calibration_candidates
            if expected[building_id] == TEXTURELESS
        }
        completed_actual_textureless = (
            actual_textureless & completed_calibration_candidates
        )
        predicted_textureless = {
            building_id for building_id in completed_calibration_candidates
            if recorded[building_id] == TEXTURELESS
        }
        above = {
            building_id for building_id in completed_calibration_candidates
            if (
                as_int(
                    measured_by_id[building_id].get(
                        "footprint_inside_point_count"
                    )
                )
                or 0
            )
            >= threshold
        }
        evaluations.append(
            {
                "threshold": threshold,
                "calibration_n": len(calibration),
                "calibration_correct": correct,
                "calibration_accuracy": correct / len(calibration),
                "calibration_candidate_support_n": len(
                    calibration_candidates
                ),
                "completed_calibration_candidate_support_n": len(
                    completed_calibration_candidates
                ),
                "incomplete_calibration_candidate_support_n": (
                    len(calibration_candidates)
                    - len(completed_calibration_candidates)
                ),
                "actual_textureless_total_n": len(actual_textureless),
                "actual_textureless_support_n": len(
                    completed_actual_textureless
                ),
                "predicted_textureless_n": len(predicted_textureless),
                "textureless_true_positive_n": len(
                    completed_actual_textureless & predicted_textureless
                ),
                "count_at_or_above_threshold_n": len(above),
                "count_below_threshold_n": (
                    len(completed_calibration_candidates) - len(above)
                ),
            }
        )
    selected = min(
        evaluations,
        key=lambda row: (
            -int(row["calibration_correct"]),
            int(row["threshold"]),
        ),
    )
    return int(selected["threshold"]), evaluations


def confusion_cells(
    comparison: str,
    subset: str,
    actual_labels: Sequence[str],
    recorded_labels: Sequence[str],
    pairs: Sequence[tuple[str, str]],
    rule_sha: str,
) -> list[dict[str, Any]]:
    counts = Counter(pairs)
    return [
        {
            "record_type": "confusion_cell",
            "comparison": comparison,
            "subset": subset,
            "actual_label": actual,
            "recorded_label": recorded,
            "count": counts[(actual, recorded)],
            "n_records": len(pairs),
            "manual_split_seed": MANUAL_SPLIT_SEED,
            "dense_split_seed": DENSE_SPLIT_SEED,
            "rule_sha256": rule_sha,
            "evaluation_status": "complete",
            "learning_runs_started": 0,
        }
        for actual in actual_labels
        for recorded in recorded_labels
    ]


def primary_validation_rows(
    primary_rows: Sequence[Mapping[str, Any]],
    rule_sha: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    validation = [
        row for row in primary_rows if row["combined_split"] == "validation"
    ]
    if len(validation) != 79:
        raise RuntimeError("primary validation is not 79 records")
    pairs = [
        (str(row["expected_tier"]), str(row["primary_assignment"]))
        for row in validation
    ]
    correct = sum(actual == recorded for actual, recorded in pairs)
    constant_correct = sum(actual == WELL for actual, _recorded in pairs)
    accuracy = correct / len(pairs)
    constant_accuracy = constant_correct / len(pairs)
    gain = accuracy - constant_accuracy
    rule_status = "passed_gain" if gain >= 0 else "failed_gain"
    output = confusion_cells(
        "primary_rule_validation",
        "combined_validation_79_pre_fm_pre_override_pre_small",
        EXPECTED_LABELS,
        EXPECTED_LABELS,
        pairs,
        rule_sha,
    )
    output.append(
        {
            "record_type": "validation_accuracy",
            "comparison": "primary_rule_validation",
            "subset": "combined_validation_79_pre_fm_pre_override_pre_small",
            "n_records": len(pairs),
            "correct_count": correct,
            "accuracy": accuracy,
            "manual_split_seed": MANUAL_SPLIT_SEED,
            "dense_split_seed": DENSE_SPLIT_SEED,
            "rule_sha256": rule_sha,
            "evaluation_status": "complete",
            "rule_status": rule_status,
            "learning_runs_started": 0,
        }
    )
    output.append(
        {
            "record_type": "constant_gain",
            "comparison": "primary_rule_vs_constant_well_textured",
            "subset": "combined_validation_79_pre_fm_pre_override_pre_small",
            "n_records": len(pairs),
            "correct_count": correct,
            "accuracy": accuracy,
            "constant_correct_count": constant_correct,
            "constant_accuracy": constant_accuracy,
            "accuracy_gain": gain,
            "manual_split_seed": MANUAL_SPLIT_SEED,
            "dense_split_seed": DENSE_SPLIT_SEED,
            "rule_sha256": rule_sha,
            "evaluation_status": "complete",
            "rule_status": rule_status,
            "learning_runs_started": 0,
        }
    )
    for label in EXPECTED_LABELS:
        true_positive = sum(
            actual == label and recorded == label
            for actual, recorded in pairs
        )
        actual_support = sum(actual == label for actual, _ in pairs)
        predicted_support = sum(
            recorded == label for _, recorded in pairs
        )
        recall = (
            true_positive / actual_support if actual_support else None
        )
        precision = (
            true_positive / predicted_support
            if predicted_support else None
        )
        output.append(
            {
                "record_type": "class_metric",
                "comparison": "primary_rule_validation",
                "subset": (
                    "combined_validation_79_pre_fm_pre_override_pre_small"
                ),
                "metric_label": label,
                "tp": true_positive,
                "actual_support": actual_support,
                "predicted_support": predicted_support,
                "recall": recall,
                "precision": precision,
                "metric_status": (
                    "complete"
                    if predicted_support
                    else "precision_undefined_zero_predicted_support"
                ),
                "n_records": len(pairs),
                "manual_split_seed": MANUAL_SPLIT_SEED,
                "dense_split_seed": DENSE_SPLIT_SEED,
                "rule_sha256": rule_sha,
                "evaluation_status": "complete",
                "rule_status": rule_status,
                "learning_runs_started": 0,
            }
        )
    return output, {
        "n": len(pairs),
        "correct": correct,
        "accuracy": accuracy,
        "constant_correct": constant_correct,
        "constant_accuracy": constant_accuracy,
        "accuracy_gain": gain,
        "rule_status": rule_status,
        "class_metrics": {
            row["metric_label"]: {
                "tp": row["tp"],
                "actual_support": row["actual_support"],
                "predicted_support": row["predicted_support"],
                "recall": row["recall"],
                "precision": row["precision"],
                "metric_status": row["metric_status"],
            }
            for row in output if row["record_type"] == "class_metric"
        },
    }


def add_inventory_confusion_rows(
    output: list[dict[str, Any]],
    inventory: Mapping[str, Any],
    rule_sha: str,
) -> None:
    for source, split, count in (
        ("manual44", "calibration", 22),
        ("manual44", "validation", 22),
        ("dense_success114", "calibration", 57),
        ("dense_success114", "validation", 57),
        ("combined158", "calibration", 79),
        ("combined158", "validation", 79),
    ):
        output.append(
            {
                "record_type": "split_inventory",
                "comparison": source,
                "subset": source,
                "recorded_label": split,
                "count": count,
                "manual_split_seed": MANUAL_SPLIT_SEED,
                "dense_split_seed": DENSE_SPLIT_SEED,
                "rule_sha256": rule_sha,
                "evaluation_status": "complete",
                "learning_runs_started": 0,
            }
        )
    output.append(
        {
            "record_type": "integrity_check",
            "comparison": "manual44_intersect_dense_success114",
            "subset": "canonical_178",
            "count": int(
                inventory["manual_dense_success_intersection_count"]
            ),
            "n_records": 158,
            "metric_status": "measured_zero",
            "manual_split_seed": MANUAL_SPLIT_SEED,
            "dense_split_seed": DENSE_SPLIT_SEED,
            "rule_sha256": rule_sha,
            "evaluation_status": "complete",
            "learning_runs_started": 0,
        }
    )


def dense_cross_tab_rows(
    ladder: Sequence[Mapping[str, Any]], rule_sha: str
) -> tuple[list[dict[str, Any]], dict[str, dict[str, int]]]:
    output: list[dict[str, Any]] = []
    summaries: dict[str, dict[str, int]] = {}
    contracts = (
        ("primary_rule_vs_dense_success", "primary_assignment"),
        ("final_map_vs_dense_success", "map_assignment"),
    )
    for comparison, field in contracts:
        pairs = [
            (
                "dense_success"
                if int(row["dense_assembled"]) == 1
                else "dense_failure",
                "well_textured"
                if row[field] == WELL
                else "not_well_textured",
            )
            for row in ladder
        ]
        output.extend(
            confusion_cells(
                comparison,
                "canonical_178",
                ("dense_success", "dense_failure"),
                ("well_textured", "not_well_textured"),
                pairs,
                rule_sha,
            )
        )
        counts = Counter(pairs)
        summaries[comparison] = {
            f"{actual}|{recorded}": counts[(actual, recorded)]
            for actual in ("dense_success", "dense_failure")
            for recorded in ("well_textured", "not_well_textured")
        }
        if sum(
            count for key, count in summaries[comparison].items()
            if key.startswith("dense_success|")
        ) != 114:
            raise RuntimeError(f"{comparison} dense success count drift")
        if sum(
            count for key, count in summaries[comparison].items()
            if key.startswith("dense_failure|")
        ) != 64:
            raise RuntimeError(f"{comparison} dense failure count drift")
    return output, summaries


def load_footprint_geometries() -> dict[str, Any]:
    v2 = load_v2_module()
    old = v2._load_old()  # noqa: SLF001 - frozen map geometry reader
    geometries, _areas = old.load_footprints()
    return geometries


def make_map(ladder: Sequence[Mapping[str, Any]]) -> None:
    geometries = load_footprint_geometries()
    colors = {
        WELL: "#2ca25f",
        TEXTURELESS: "#3182bd",
        OUTLINE: "#fdae6b",
        UNOBSERVABLE: "#de2d26",
        SMALL: "#969696",
    }
    counts = Counter(row["map_assignment"] for row in ladder)
    figure, axis = plt.subplots(figsize=(13, 10), dpi=190)
    for row in sorted(ladder, key=lambda item: item["building_id"]):
        geometry = geometries[row["building_id"]]
        polygons = (
            [geometry] if geometry.geom_type == "Polygon"
            else list(geometry.geoms)
        )
        for polygon in polygons:
            x_coord, y_coord = polygon.exterior.xy
            axis.fill(
                x_coord,
                y_coord,
                facecolor=colors[row["map_assignment"]],
                edgecolor="white",
                linewidth=0.18,
            )
    axis.set_aspect("equal", adjustable="box")
    axis.set_xlabel("Easting (m), EPSG:25832")
    axis.set_ylabel("Northing (m), EPSG:25832")
    axis.set_title("Boundary map v3 — canonical 178 final assignments")
    axis.grid(alpha=0.12)
    axis.legend(
        handles=[
            Patch(
                facecolor=colors[label],
                edgecolor="none",
                label=f"{label} (n={counts[label]})",
            )
            for label in MAP_LABELS
        ],
        loc="best",
        fontsize=8,
        framealpha=0.94,
    )
    figure.tight_layout()
    FIGURE.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(FIGURE)
    plt.close(figure)


def metric_output_fields() -> list[str]:
    base = read_csv_fields(V2_METRICS)
    additions = [
        "label_source",
        "combined_split",
        "expected_tier",
        "fm_dense_status",
        "fm_dense_selected_dlt_point_count",
        "fm_dense_footprint_inside_point_count",
        "fm_dense_inside_z_median_m",
        "fm_dense_inside_z_mad_m",
        "fm_dense_coverage_ratio",
        "fm_dense_selected_pair_count",
        "fm_dense_completed_pair_count",
        "fm_dense_elapsed_seconds",
        "fm_dense_new_mast3r_inference_runs",
        "fm_dense_count_role",
    ]
    return [field for field in base if field != "new_inference_type"] + [
        field for field in additions if field not in base
    ] + ["new_inference_type"]


def ladder_fields() -> list[str]:
    return [
        "building_id",
        *FEATURES_WITH_SMALL,
        "label_source",
        "manual_split",
        "dense_split",
        "combined_split",
        "expected_tier",
        "primary_assignment",
        "primary_rule_path",
        "primary_nonwell_candidate",
        "queue_inclusion_reason",
        "fm_dense_status",
        "fm_dense_selected_dlt_point_count",
        "fm_dense_footprint_inside_point_count",
        "fm_dense_inside_z_median_m",
        "fm_dense_inside_z_mad_m",
        "fm_dense_coverage_ratio",
        "fm_dense_selected_pair_count",
        "fm_dense_completed_pair_count",
        "fm_dense_elapsed_seconds",
        "fm_dense_count_threshold",
        "fm_sparse_status_reference",
        "fm_sparse_selected_dlt_point_count_reference",
        "fm_sparse_footprint_inside_point_count_reference",
        "fm_sparse_inside_z_median_m_reference",
        "fm_sparse_inside_z_mad_m_reference",
        "outline_observable",
        "formula_assignment",
        "size_rule_assignment",
        "override_assignment",
        "override_evidence",
        "override_applied",
        "map_assignment",
        "conditional_generation_target",
        "dense_assembled",
        "manual_split_seed",
        "dense_split_seed",
        "learning_runs_started",
        "new_inference_type",
    ]


def dense_value(
    dense_row: Mapping[str, Any] | None, field: str
) -> Any:
    return "" if dense_row is None else dense_row.get(field, "")


def build_public_rows(
    metric_rows: Sequence[Mapping[str, Any]],
    primary_rows: Sequence[Mapping[str, Any]],
    measured_by_id: Mapping[str, Mapping[str, Any]],
    threshold: int,
    candidates: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    primary_by_id = {
        row["building_id"]: row for row in primary_rows
    }
    jobs = json.loads(FM_JOBS.read_text(encoding="utf-8"))["jobs"]
    job_by_id = {job["building_id"]: job for job in jobs}
    metrics: list[dict[str, Any]] = []
    ladder: list[dict[str, Any]] = []
    for source in sorted(metric_rows, key=lambda item: item["building_id"]):
        building_id = source["building_id"]
        primary = primary_by_id[building_id]
        dense = measured_by_id.get(building_id)
        formula = formula_assignment(
            building_id,
            primary["primary_assignment"],
            source,
            dense,
            threshold,
            candidates,
        )
        size_assignment = (
            SMALL
            if float(source["footprint_area_m2"]) < SMALL_AREA_M2
            else formula
        )
        override_assignment = (
            TEXTURELESS if building_id in OVERRIDE_IDS else ""
        )
        override_evidence = (
            OVERRIDE_EVIDENCE if building_id in OVERRIDE_IDS else ""
        )
        map_assignment = override_assignment or size_assignment
        conditional_target = map_assignment in {TEXTURELESS, OUTLINE}
        new_inference = (
            NEW_INFERENCE_TYPE
            if dense is not None
            else "none; existing measurements reused read-only"
        )
        metric = dict(source)
        metric.update(
            {
                "label_source": primary["label_source"],
                "combined_split": primary["combined_split"],
                "expected_tier": primary["expected_tier"],
                "fm_dense_status": dense_value(dense, "status"),
                "fm_dense_selected_dlt_point_count": dense_value(
                    dense, "selected_dlt_point_count"
                ),
                "fm_dense_footprint_inside_point_count": dense_value(
                    dense, "footprint_inside_point_count"
                ),
                "fm_dense_inside_z_median_m": dense_value(
                    dense, "inside_z_median_m"
                ),
                "fm_dense_inside_z_mad_m": dense_value(
                    dense, "inside_z_mad_m"
                ),
                "fm_dense_coverage_ratio": dense_value(
                    dense, "coverage_ratio"
                ),
                "fm_dense_selected_pair_count": dense_value(
                    dense, "selected_pair_count"
                ),
                "fm_dense_completed_pair_count": dense_value(
                    dense, "completed_pair_count"
                ),
                "fm_dense_elapsed_seconds": dense_value(
                    dense, "elapsed_seconds"
                ),
                "fm_dense_new_mast3r_inference_runs": dense_value(
                    dense, "new_mast3r_inference_runs"
                ),
                "fm_dense_count_role": (
                    "assignment_channel"
                    if building_id in candidates
                    else "not_measured"
                ),
                "learning_runs_started": 0,
                "new_inference_type": new_inference,
            }
        )
        metrics.append(metric)
        job = job_by_id.get(building_id)
        ladder.append(
            {
                "building_id": building_id,
                **{
                    feature: as_float(source.get(feature))
                    for feature in FEATURES_WITH_SMALL
                },
                "label_source": primary["label_source"],
                "manual_split": primary["manual_split"],
                "dense_split": primary["dense_split"],
                "combined_split": primary["combined_split"],
                "expected_tier": primary["expected_tier"],
                "primary_assignment": primary["primary_assignment"],
                "primary_rule_path": primary["primary_rule_path"],
                "primary_nonwell_candidate": as_bool(
                    primary["primary_nonwell_candidate"]
                ),
                "queue_inclusion_reason": (
                    job["queue_inclusion_reason"] if job else ""
                ),
                "fm_dense_status": dense_value(dense, "status"),
                "fm_dense_selected_dlt_point_count": dense_value(
                    dense, "selected_dlt_point_count"
                ),
                "fm_dense_footprint_inside_point_count": dense_value(
                    dense, "footprint_inside_point_count"
                ),
                "fm_dense_inside_z_median_m": dense_value(
                    dense, "inside_z_median_m"
                ),
                "fm_dense_inside_z_mad_m": dense_value(
                    dense, "inside_z_mad_m"
                ),
                "fm_dense_coverage_ratio": dense_value(
                    dense, "coverage_ratio"
                ),
                "fm_dense_selected_pair_count": dense_value(
                    dense, "selected_pair_count"
                ),
                "fm_dense_completed_pair_count": dense_value(
                    dense, "completed_pair_count"
                ),
                "fm_dense_elapsed_seconds": dense_value(
                    dense, "elapsed_seconds"
                ),
                "fm_dense_count_threshold": threshold,
                "fm_sparse_status_reference": source.get("fm_status", ""),
                "fm_sparse_selected_dlt_point_count_reference": source.get(
                    "fm_reprojection_pass_count", ""
                ),
                "fm_sparse_footprint_inside_point_count_reference": (
                    source.get("fm_correspondence_count", "")
                ),
                "fm_sparse_inside_z_median_m_reference": source.get(
                    "fm_z_median_m", ""
                ),
                "fm_sparse_inside_z_mad_m_reference": source.get(
                    "fm_z_mad_m", ""
                ),
                "outline_observable": outline_observable(source),
                "formula_assignment": formula,
                "size_rule_assignment": size_assignment,
                "override_assignment": override_assignment,
                "override_evidence": override_evidence,
                "override_applied": bool(override_assignment),
                "map_assignment": map_assignment,
                "conditional_generation_target": conditional_target,
                "dense_assembled": as_int(source["dense_assembled"]),
                "manual_split_seed": MANUAL_SPLIT_SEED,
                "dense_split_seed": DENSE_SPLIT_SEED,
                "learning_runs_started": 0,
                "new_inference_type": new_inference,
            }
        )
    if len(metrics) != 178 or len(ladder) != 178:
        raise RuntimeError("public v3 rows are not 178/178")
    return metrics, ladder


def build_conditional(
    ladder: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    output = [
        {
            "building_id": row["building_id"],
            "primary_assignment": row["primary_assignment"],
            "formula_assignment": row["formula_assignment"],
            "size_rule_assignment": row["size_rule_assignment"],
            "override_assignment": row["override_assignment"],
            "override_evidence": row["override_evidence"],
            "override_applied": row["override_applied"],
            "map_assignment": row["map_assignment"],
            "fm_dense_footprint_inside_point_count": row[
                "fm_dense_footprint_inside_point_count"
            ],
            "fm_dense_inside_z_median_m": row[
                "fm_dense_inside_z_median_m"
            ],
            "conditional_generation_target": True,
            "learning_runs_started": 0,
            "new_inference_type": row["new_inference_type"],
        }
        for row in ladder
        if row["map_assignment"] in {TEXTURELESS, OUTLINE}
    ]
    if not set(OVERRIDE_IDS) <= {
        row["building_id"] for row in output
    }:
        raise RuntimeError("override identifiers are missing from targets")
    return output


def summary_markdown(
    ladder: Sequence[Mapping[str, Any]],
    validation: Mapping[str, Any],
    threshold: int,
    threshold_evaluations: Sequence[Mapping[str, Any]],
    dense_tabs: Mapping[str, Mapping[str, int]],
    conditional_count: int,
    dense_measurement_status: str,
    incomplete_dense: Sequence[str],
    threshold_status: str,
) -> str:
    tier_counts = Counter(row["map_assignment"] for row in ladder)
    selected_threshold = next(
        row for row in threshold_evaluations
        if int(row["threshold"]) == threshold
    )
    by_id = {row["building_id"]: row for row in ladder}
    lines = [
        "# Boundary map v3 measurement summary (2026-07-19)",
        "",
        "## Population and label inventory",
        "",
        "| measurement | count |",
        "|---|---:|",
        "| canonical raw_lidar assembled=true | 178 |",
        "| canonical dense assembled=true | 114 |",
        "| canonical dense assembled=false | 64 |",
        "| manual labels | 44 |",
        "| manual ∩ dense-success | 0 |",
        "| calibration labels | 79 |",
        "| validation labels | 79 |",
        "",
        "The manual 22/22 membership is the v2 set at seed 20260718. "
        "Dense-success labels use seed 20260719 and a 57/57 split.",
        "",
        "## Final map assignment counts",
        "",
        "| assignment | count |",
        "|---|---:|",
        *[
            f"| `{label}` | {tier_counts[label]} |"
            for label in MAP_LABELS
        ],
        f"| conditional generation targets | {conditional_count} |",
        "",
        "## Primary rule validation (pre-FM, pre-override, pre-small)",
        "",
        "| measurement | value |",
        "|---|---:|",
        f"| validation records | {validation['n']} |",
        f"| exact records | {validation['correct']} |",
        f"| accuracy | {validation['accuracy']:.9f} |",
        f"| constant well_textured exact records | "
        f"{validation['constant_correct']} |",
        f"| constant accuracy | {validation['constant_accuracy']:.9f} |",
        f"| accuracy gain | {validation['accuracy_gain']:.9f} |",
        f"| rule_status | `{validation['rule_status']}` |",
        "",
        "| expected tier | support | predicted support | recall | precision |",
        "|---|---:|---:|---:|---:|",
    ]
    for label in EXPECTED_LABELS:
        metric = validation["class_metrics"][label]
        recall = (
            f"{metric['recall']:.9f}"
            if metric["recall"] is not None else "NA"
        )
        precision = (
            f"{metric['precision']:.9f}"
            if metric["precision"] is not None else "NA"
        )
        lines.append(
            f"| `{label}` | {metric['actual_support']} | "
            f"{metric['predicted_support']} | {recall} | {precision} |"
        )
    lines.extend(
        [
            "",
        "## FM dense-dial count threshold",
        "",
            f"- measurement status: {dense_measurement_status}",
            f"- incomplete buildings: {len(incomplete_dense)}",
            f"- threshold status: {threshold_status}",
            f"- selected footprint-inside count threshold: {threshold}",
            f"- calibration candidate total: "
            f"{selected_threshold['calibration_candidate_support_n']}",
            f"- completed calibration candidate support: "
            f"{selected_threshold['completed_calibration_candidate_support_n']}",
            f"- incomplete calibration candidate support: "
            f"{selected_threshold['incomplete_calibration_candidate_support_n']}",
            f"- actual textureless support in calibration candidates: "
            f"{selected_threshold['actual_textureless_support_n']}",
            f"- candidates at or above threshold: "
            f"{selected_threshold['count_at_or_above_threshold_n']}",
            f"- candidates below threshold: "
            f"{selected_threshold['count_below_threshold_n']}",
            "",
            "The threshold candidate set contains 1, every observed positive "
            "calibration-candidate count, and each observed count plus one. "
            "Selection maximizes calibration79 exact agreement; ties use the "
            "smallest integer threshold.",
            "",
            "Incomplete FM candidates retain their primary assignment; the "
            "fixed override is then applied after the small-area rule.",
            "",
            "Incomplete building identifiers:",
            "",
            *(
                [f"- `{building_id}`" for building_id in incomplete_dense]
                if incomplete_dense else ["- none"]
            ),
            "",
            "## Dense outcome cross-tabulations",
            "",
        ]
    )
    for comparison in (
        "primary_rule_vs_dense_success",
        "final_map_vs_dense_success",
    ):
        lines.extend(
            [
                f"### {comparison}",
                "",
                "| dense outcome | recorded group | count |",
                "|---|---|---:|",
            ]
        )
        table = dense_tabs[comparison]
        for actual in ("dense_success", "dense_failure"):
            for recorded in ("well_textured", "not_well_textured"):
                lines.append(
                    f"| {actual} | {recorded} | "
                    f"{table[f'{actual}|{recorded}']} |"
                )
        lines.append("")
    lines.extend(
        [
            "## Fixed override records (full identifiers)",
            "",
            "| building_id | primary | formula | size rule | override | "
            "final map | dense inside count | dense inside z median (m) |",
            "|---|---|---|---|---|---|---:|---:|",
        ]
    )
    for building_id in OVERRIDE_IDS:
        row = by_id[building_id]
        count = row["fm_dense_footprint_inside_point_count"]
        z_median = row["fm_dense_inside_z_median_m"]
        lines.append(
            f"| `{building_id}` | `{row['primary_assignment']}` | "
            f"`{row['formula_assignment']}` | "
            f"`{row['size_rule_assignment']}` | "
            f"`{row['override_assignment']}` | "
            f"`{row['map_assignment']}` | {count} | "
            f"{z_median if z_median not in (None, '') else 'NA'} |"
        )
    lines.extend(
        [
            "",
            f"Override evidence for both rows: `{OVERRIDE_EVIDENCE}`.",
            "",
            "All output rows record `learning_runs_started=0`. New inference "
            "is limited to the R1′-3 FM dense-dial reciprocal-matching queue. "
            "The v2 sparse FM fields are retained as reference columns only. "
            "LoD2 remains projection/classification-only.",
        ]
    )
    return "\n".join(lines) + "\n"


def validate_public_bundle(
    metrics: Sequence[Mapping[str, Any]],
    ladder: Sequence[Mapping[str, Any]],
    confusion: Sequence[Mapping[str, Any]],
    conditional: Sequence[Mapping[str, Any]],
    validation: Mapping[str, Any],
) -> None:
    if len(metrics) != 178 or len(ladder) != 178:
        raise RuntimeError("v3 public population cardinality drift")
    if len({row["building_id"] for row in metrics}) != 178:
        raise RuntimeError("v3 metric identifier duplication")
    if len({row["building_id"] for row in ladder}) != 178:
        raise RuntimeError("v3 ladder identifier duplication")
    if any(int(row["learning_runs_started"]) != 0 for row in metrics):
        raise RuntimeError("v3 metric learning flag drift")
    if any(int(row["learning_runs_started"]) != 0 for row in ladder):
        raise RuntimeError("v3 ladder learning flag drift")
    if any(int(row["learning_runs_started"]) != 0 for row in confusion):
        raise RuntimeError("v3 confusion learning flag drift")
    if any(int(row["learning_runs_started"]) != 0 for row in conditional):
        raise RuntimeError("v3 target learning flag drift")
    allowed = set(MAP_LABELS)
    if any(row["map_assignment"] not in allowed for row in ladder):
        raise RuntimeError("v3 map assignment vocabulary drift")
    by_id = {row["building_id"]: row for row in ladder}
    for building_id in OVERRIDE_IDS:
        row = by_id[building_id]
        if (
            row["override_assignment"] != TEXTURELESS
            or row["override_evidence"] != OVERRIDE_EVIDENCE
            or row["map_assignment"] != TEXTURELESS
        ):
            raise RuntimeError(f"{building_id} override contract drift")
    if validation["n"] != 79:
        raise RuntimeError("v3 validation metric n is not 79")
    metric_rows = [
        row for row in confusion
        if row["record_type"] == "class_metric"
    ]
    if {row["metric_label"] for row in metric_rows} != set(EXPECTED_LABELS):
        raise RuntimeError("v3 class precision/recall rows incomplete")
    for comparison in (
        "primary_rule_vs_dense_success",
        "final_map_vs_dense_success",
    ):
        cells = [
            row for row in confusion
            if row["record_type"] == "confusion_cell"
            and row["comparison"] == comparison
        ]
        if len(cells) != 4 or sum(int(row["count"]) for row in cells) != 178:
            raise RuntimeError(f"{comparison} is not a complete 2x2 table")
    target_ids = {row["building_id"] for row in conditional}
    expected_targets = {
        row["building_id"] for row in ladder
        if row["map_assignment"] in {TEXTURELESS, OUTLINE}
    }
    if target_ids != expected_targets:
        raise RuntimeError("conditional target set differs from final map tiers")


def finalize() -> None:
    required_intermediate = (
        PRIMARY_CSV,
        RULE_JSON,
        LABEL_INVENTORY,
        FM_JOBS,
    )
    missing_intermediate = [
        rel(path) for path in required_intermediate if not path.is_file()
    ]
    if missing_intermediate:
        raise RuntimeError(
            f"run prepare-fit before finalize; missing {missing_intermediate}"
        )
    primary_rows = read_csv(PRIMARY_CSV)
    if (
        len(primary_rows) != 178
        or len({row["building_id"] for row in primary_rows}) != 178
    ):
        raise RuntimeError("primary prediction population is not 178 unique")
    rule = json.loads(RULE_JSON.read_text(encoding="utf-8"))
    verify_tree_contract(rule["tree"])
    inventory = json.loads(LABEL_INVENTORY.read_text(encoding="utf-8"))
    metric_rows = read_csv(V2_METRICS)
    metric_by_id = {row["building_id"]: row for row in metric_rows}
    primary_by_id = {row["building_id"]: row for row in primary_rows}
    candidates = fm_candidate_set(primary_rows)
    jobs = json.loads(FM_JOBS.read_text(encoding="utf-8"))
    if set(jobs) != {"model", "jobs"}:
        raise RuntimeError("fm_dense_jobs top-level schema is not model/jobs")
    job_ids = {job["building_id"] for job in jobs["jobs"]}
    if job_ids != candidates or len(jobs["jobs"]) != len(candidates):
        raise RuntimeError("FM dense job identifiers differ from candidate set")

    (
        measured_by_id,
        incomplete_dense,
        dense_measurement_status,
        dense_measurement_notes,
    ) = load_dense_results(candidates)
    expected = {
        building_id: label
        for building_id, label in zip(
            inventory["combined_calibration_buildings"],
            [
                primary_by_id[building_id]["expected_tier"]
                for building_id in inventory["combined_calibration_buildings"]
            ],
        )
    }
    expected.update(
        {
            building_id: primary_by_id[building_id]["expected_tier"]
            for building_id in inventory["combined_validation_buildings"]
        }
    )
    calibration = set(inventory["combined_calibration_buildings"])
    threshold, threshold_evaluations = choose_dense_threshold(
        metric_by_id,
        primary_by_id,
        measured_by_id,
        expected,
        calibration,
        candidates,
    )
    selected_threshold_evaluation = next(
        row for row in threshold_evaluations
        if int(row["threshold"]) == threshold
    )
    completed_threshold_support = int(
        selected_threshold_evaluation[
            "completed_calibration_candidate_support_n"
        ]
    )
    total_threshold_support = int(
        selected_threshold_evaluation["calibration_candidate_support_n"]
    )
    if completed_threshold_support == 0:
        threshold_status = (
            "unavailable_no_completed_calibration_candidates_default_1"
        )
    elif completed_threshold_support < total_threshold_support:
        threshold_status = "selected_on_partial_calibration_support"
    else:
        threshold_status = "selected_on_complete_calibration_support"
    prerequisite_missing_dense = sorted(
        building_id for building_id in incomplete_dense
        if prerequisite_missing_row(measured_by_id.get(building_id))
    )
    budget_or_pending_dense = sorted(
        set(incomplete_dense) - set(prerequisite_missing_dense)
    )
    metrics, ladder = build_public_rows(
        metric_rows,
        primary_rows,
        measured_by_id,
        threshold,
        candidates,
    )
    conditional = build_conditional(ladder)
    rule_sha = rule["tree_sha256"]
    confusion, validation = primary_validation_rows(
        primary_rows, rule_sha
    )
    add_inventory_confusion_rows(confusion, inventory, rule_sha)
    dense_confusion, dense_tabs = dense_cross_tab_rows(ladder, rule_sha)
    confusion.extend(dense_confusion)
    validate_public_bundle(
        metrics, ladder, confusion, conditional, validation
    )

    atomic_csv(METRICS, metrics, metric_output_fields())
    atomic_csv(LADDER, ladder, ladder_fields())
    atomic_csv(CONFUSION, confusion, CONFUSION_FIELDS)
    atomic_csv(CONDITIONAL, conditional, CONDITIONAL_FIELDS)
    make_map(ladder)
    atomic_text(
        SUMMARY,
        summary_markdown(
            ladder,
            validation,
            threshold,
            threshold_evaluations,
            dense_tabs,
            len(conditional),
            dense_measurement_status,
            incomplete_dense,
            threshold_status,
        ),
    )

    tier_counts = Counter(row["map_assignment"] for row in ladder)
    dense_run_manifest = (
        json.loads(FM_RUN_MANIFEST.read_text(encoding="utf-8"))
        if FM_RUN_MANIFEST.is_file() else {}
    )
    if dense_measurement_status == "complete":
        if PARTIAL_MANIFEST.exists():
            PARTIAL_MANIFEST.unlink()
        if PARTIAL_SUMMARY.exists():
            PARTIAL_SUMMARY.unlink()
    sources = (
        SNAPSHOT,
        MANUAL,
        V2_METRICS,
        V2_LADDER,
        V2_MANIFEST,
        V2_ALL_PROJECTION_JOBS,
        V2_SCRIPT,
        DENSE_SCRIPT,
        DRIVER_SCRIPT,
        ENV_MANIFEST,
        S3AP_DIAL_CONFIG,
        S3AP_DIAL_CSV,
        S3AP_PJPL,
        Path(__file__).resolve(),
        PRIMARY_CSV,
        RULE_JSON,
        LABEL_INVENTORY,
        FM_JOBS,
        FM_MEASUREMENTS,
        FM_PAIRS,
        FM_PROGRESS,
        FM_RUN_MANIFEST,
    )
    outputs = (
        METRICS,
        LADDER,
        CONFUSION,
        CONDITIONAL,
        FIGURE,
        SUMMARY,
        PRIMARY_CSV,
        RULE_JSON,
        LABEL_INVENTORY,
        FM_JOBS,
        FM_MEASUREMENTS,
        FM_PAIRS,
        FM_PROGRESS,
        FM_RUN_MANIFEST,
        PARTIAL_MANIFEST,
        PARTIAL_SUMMARY,
    )
    manifest_payload = {
        "schema": "jointbuildgs.boundary_map_v3.v1",
        "created_utc": now(),
        "git_head_at_measurement": git_value("rev-parse", "HEAD"),
        "branch": git_value("branch", "--show-current"),
        "population": {
            "canonical_count": 178,
            "dense_success_count": 114,
            "dense_failure_count": 64,
            "manual_label_count": 44,
            "manual_dense_success_intersection_count": 0,
            "combined_calibration_count": 79,
            "combined_validation_count": 79,
        },
        "label_inventory": inventory,
        "tier_names": list(MAP_LABELS),
        "primary_rule": rule,
        "primary_validation": validation,
        "rule_status": validation["rule_status"],
        "fm_dense": {
            "candidate_formula": (
                "primary_assignment!=well_textured union exact manual "
                "textureless four"
            ),
            "candidate_count": len(candidates),
            "candidate_buildings": sorted(candidates),
            "model": jobs["model"],
            "measurement_manifest": dense_run_manifest,
            "measurement_status": dense_measurement_status,
            "measurement_recorded_count": len(
                set(measured_by_id) & candidates
            ),
            "measurement_complete_count": (
                len(candidates) - len(incomplete_dense)
            ),
            "measurement_incomplete_buildings": incomplete_dense,
            "measurement_prerequisite_missing_buildings": (
                prerequisite_missing_dense
            ),
            "measurement_budget_or_pending_buildings": (
                budget_or_pending_dense
            ),
            "measurement_notes": dense_measurement_notes,
            "sparse_channel_role": "reference columns only",
            "assignment_count_role": (
                "only fm_dense_footprint_inside_point_count is used for "
                "textureless_correspondence_anchored"
            ),
        },
        "fm_dense_count_threshold": threshold,
        "fm_dense_count_threshold_selection": {
            "status": threshold_status,
            "available": completed_threshold_support > 0,
            "completed_calibration_candidate_support_n": (
                completed_threshold_support
            ),
            "calibration_candidate_total_n": total_threshold_support,
            "objective": (
                "maximize calibration79 exact expected-tier agreement "
                "after primary candidate selection"
            ),
            "tie_break": "smallest integer threshold",
            "candidate_rule": (
                "1, every observed positive calibration-candidate count, "
                "and every observed calibration-candidate count plus one"
            ),
            "evaluations": threshold_evaluations,
            "selected": selected_threshold_evaluation,
        },
        "small_rule": (
            f"footprint_area_m2<{SMALL_AREA_M2} -> {SMALL}; "
            "primary predicate use prohibited"
        ),
        "overrides": {
            "priority": (
                "override_assignment, else footprint small rule, else "
                "formula_assignment"
            ),
            "assignment": TEXTURELESS,
            "buildings": list(OVERRIDE_IDS),
            "evidence": OVERRIDE_EVIDENCE,
            "records": {
                building_id: {
                    "primary_assignment": next(
                        row["primary_assignment"] for row in ladder
                        if row["building_id"] == building_id
                    ),
                    "formula_assignment": next(
                        row["formula_assignment"] for row in ladder
                        if row["building_id"] == building_id
                    ),
                    "map_assignment": next(
                        row["map_assignment"] for row in ladder
                        if row["building_id"] == building_id
                    ),
                }
                for building_id in OVERRIDE_IDS
            },
        },
        "assignment_counts": {
            label: tier_counts[label] for label in MAP_LABELS
        },
        "conditional_generation_buildings": [
            row["building_id"] for row in conditional
        ],
        "dense_check": {
            "canonical_success": 114,
            "canonical_failure": 64,
            "primary_rule_confusion": dense_tabs[
                "primary_rule_vs_dense_success"
            ],
            "final_map_confusion": dense_tabs[
                "final_map_vs_dense_success"
            ],
        },
        "source_sha256": {
            rel(path): sha256_file(path)
            for path in sources if path.is_file()
        },
        "output_sha256": {
            rel(path): sha256_file(path)
            for path in outputs if path.is_file()
        },
        "learning_runs_started": 0,
        "new_inference_type": [
            NEW_INFERENCE_TYPE
        ],
        "reference_lod2_role": "projection and classification only",
        "interpretation_or_verdict": None,
    }
    atomic_json(MANIFEST, manifest_payload)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare-fit", "finalize"))
    args = parser.parse_args()
    if args.command == "prepare-fit":
        prepare_fit()
    else:
        finalize()


if __name__ == "__main__":
    main()
