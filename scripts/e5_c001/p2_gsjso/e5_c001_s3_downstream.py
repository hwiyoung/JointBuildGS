#!/usr/bin/env python3
"""S3-A downstream evidence adapter.

This task-scoped adapter reuses the established S2p readout/evaluation helpers
without ever writing into an S2p result, docs, figure, or P0 run directory.
It owns three classes of work:

* the non-blocking Wave-2 read of the r1 ``step_005000`` checkpoint;
* final checkpoint/audit summaries;
* canonical base pointcloudification -> Roofer -> val3dity -> ring-only 405
  overlay -> repaired evaluation and observation tables.

The 405 operation is deliberately described as a *post-Roofer overlay*.  It
cannot precede Roofer because error 405 belongs to the assembled CityJSON
shell.  No canonical S0--S2p artifact is mutated.

All scientific processing is expected to run in the repository Docker images.
The ``readout``/``assemble``/``evaluate`` commands are host-side orchestration
entrypoints whose workers are the existing Docker/Compose tools.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp")

import numpy as np


SCRIPT_DIR = Path(__file__).resolve().parent
REPO = Path(__file__).resolve().parents[3]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import e5_c001_s2p_interaction as s2p  # noqa: E402
from e5_pilot_gate_tools import DEV_IMAGE, P0_RUNS, sha256_file  # noqa: E402


RUN_ID = "20260713_e5_c001_s3_semantic_guided"
RUN_DIR = REPO / "phases/p2-gsjso/runs" / RUN_ID
SCRIPT_PATH = Path(__file__).resolve()
CHECKPOINT_GRADIENT_PAIRING_SCRIPT = (
    SCRIPT_DIR / "e5_c001_s3_checkpoint_gradient_pairing.py"
)

CONFIG_DIR = REPO / "configs/tum_mob/e5_s3_semantic_guided"
RESULTS_ROOT = REPO / "results/tum_transfer/e5_s3_semantic_guided/C001"
CKPT_ROOT = RESULTS_ROOT / "runs"
TRAIN_LOG_ROOT = RESULTS_ROOT / "train_logs"
READOUT_ROOT = RESULTS_ROOT / "readout"
TORCH_EXTENSIONS = RESULTS_ROOT / "torch_extensions"
DATA_ROOT = REPO / "results/tum_transfer/e5_pilot/C001/data_geoidfix_C001_buf20"

P0_RUN_ID = "e5p_s3a_semantic_guided_20260713_C001"
P0_RUN_DIR = P0_RUNS / P0_RUN_ID
REPAIR_RUN_ID = "e5p_s3a_405_repair_20260713_C001"
REPAIR_ROOT = P0_RUNS / REPAIR_RUN_ID
REPAIRED_P0_RUN_DIR = REPAIR_ROOT / P0_RUN_ID

FULL_RUNS = [
    "gs_e5_C001_s3a_semantic_guided_r1",
    "gs_e5_C001_s3a_semantic_guided_r2",
]
RUN_TO_REPLICATE = {FULL_RUNS[0]: "r1", FULL_RUNS[1]: "r2"}
ARM1P_BASE_RUNS = {
    "r1": "gs_e5_C001_s2p_arm1p_dense_r1",
    "r2": "gs_e5_C001_s2p_arm1p_dense_r2",
}
ARM1P_CKPT_ROOT = REPO / "results/tum_transfer/e5_s2p_interaction/C001/runs"
ARM1P_REPAIRED_ROOT = (
    REPO
    / "phases/p0-audit/runs/e5p_s2p_405_repair_20260710_C001"
    / "e5p_s2p_interaction_20260710_C001/base"
)

TEXTURELESS3 = ["4907199", "8568391", "8568392"]
CORE4 = ["4907202", "4908168", "4908178", "4907184"]
TIMELINE_IDS = TEXTURELESS3 + CORE4
TIMELINE_FULL_IDS = [f"DEBY_LOD2_{value}" for value in TIMELINE_IDS]
GOOD6 = ["4907184", "4907185", "4907198", "4907202", "4908168", "4908178"]
PK_TARGETS = ["4907185", "60098"]
PANEL_IDS = ["4907202", "4908168", "4907185", "4907184", "60098", "8568392"]
TIMELINE_STEPS: list[int | str] = [5000, 10000, 15000, 20000, 25000, "final"]
FULL_AUDIT_STEPS = {5000, 10000, 15000, 20000, 25000, 29999}
DISTORT_DENOMINATOR = 1453.9804734849022
GAUSSIAN_COUNT_THRESHOLD = 1_150_636

FIG_DIR = REPO / "docs/figs/e5_c001_s3"
CSV_TIMELINE = REPO / "docs/experiments/joint-optimization/e5_c001_s3/tables/e5_c001_s3_timeline_roofcrop.csv"
CSV_DENSIFY = REPO / "docs/experiments/joint-optimization/e5_c001_s3/tables/e5_c001_s3_densify_log.csv"
CSV_ARM_CELLS = REPO / "docs/experiments/joint-optimization/e5_c001_s3/tables/e5_c001_s3_arm_cells.csv"
CSV_405_BUILDING = REPO / "docs/experiments/joint-optimization/e5_c001_s3/tables/e5_c001_s3_405_rescore_building.csv"
CSV_405_REPAIR = REPO / "docs/experiments/joint-optimization/e5_c001_s3/tables/e5_c001_s3_405_rescore.csv"
CSV_405_REPAIR_STATUS = REPO / "docs/experiments/joint-optimization/e5_c001_s3/tables/e5_c001_s3_405_repair_status_building.csv"
CSV_GABLE_MODE = REPO / "docs/experiments/joint-optimization/e5_c001_s3/tables/e5_c001_s3_gable_mode.csv"
CSV_REND_DIST = REPO / "docs/experiments/joint-optimization/e5_c001_s3/tables/e5_c001_s3_rend_dist.csv"
CSV_GLOBAL_Z = REPO / "docs/experiments/joint-optimization/e5_c001_s3/tables/e5_c001_s3_global_z_hist.csv"
CSV_SHEET_OPACITY = REPO / "docs/experiments/joint-optimization/e5_c001_s3/tables/e5_c001_s3_sheet_opacity_dist.csv"
CSV_PANEL_INVENTORY = REPO / "docs/experiments/joint-optimization/e5_c001_s3/tables/e5_c001_s3_8way_panel_inventory.csv"
CSV_INVENTORY = REPO / "docs/experiments/joint-optimization/e5_c001_s3/tables/e5_c001_s3_inventory.csv"
CSV_ISSUES = REPO / "docs/experiments/joint-optimization/e5_c001_s3/tables/e5_c001_s3_issues.csv"
CSV_GATE_AUDIT = REPO / "docs/experiments/joint-optimization/e5_c001_s3/tables/e5_c001_s3_loss_gate_audit.csv"
CSV_CHECKPOINT_GRADIENT_PAIRING = (
    REPO / "docs/experiments/joint-optimization/e5_c001_s3/tables/e5_c001_s3_checkpoint_gradient_pairing.csv"
)
FIG_SURVIVAL_GRADIENT_PAIRING = (
    FIG_DIR / "timeline/survival_gradient_pairing.png"
)
FIG_ORGANIZATION_PLANE_RESIDUAL = (
    FIG_DIR / "timeline/organization_plane_residual.png"
)

CHECKPOINT_GRADIENT_STEPS = (5000, 10000, 15000, 20000, 25000, 30000)
CHECKPOINT_GRADIENT_COLLAPSE_TARGETS = ("4907202", "4908168", "4908178")
CHECKPOINT_GRADIENT_ORGANIZATION_TARGETS = ("4907199",)
CHECKPOINT_GRADIENT_ALL_TARGETS = (
    CHECKPOINT_GRADIENT_COLLAPSE_TARGETS
    + CHECKPOINT_GRADIENT_ORGANIZATION_TARGETS
)
CHECKPOINT_GRADIENT_CLAIM_SCOPE = (
    "posthoc checkpoint gradient potential; fixed-view read-only measurement; "
    "not exact online optimizer-time gradient; no FM/paper claim"
)
CHECKPOINT_GRADIENT_VIEW_SELECTION_SCOPE = (
    "preexecution_committed_oracle_cache_top3_by_address_pixels"
)

# Extra task-scoped tables used by the canonical readout harness.  They are
# intentionally S3-prefixed even though only the required final tables are
# listed in the order.
CSV_COVERAGE = REPO / "docs/experiments/joint-optimization/e5_c001_s3/tables/e5_c001_s3_coverage.csv"
CSV_FILTER = REPO / "docs/experiments/joint-optimization/e5_c001_s3/tables/e5_c001_s3_filter_contrib.csv"
CSV_READOUT_SUMMARY = REPO / "docs/experiments/joint-optimization/e5_c001_s3/tables/e5_c001_s3_summary.csv"
CSV_READOUT_TRADEOFF = REPO / "docs/experiments/joint-optimization/e5_c001_s3/tables/e5_c001_s3_tradeoff.csv"
CSV_READOUT_CASES = REPO / "docs/experiments/joint-optimization/e5_c001_s3/tables/e5_c001_s3_representative_buildings.csv"
CSV_READOUT_INVENTORY = REPO / "docs/experiments/joint-optimization/e5_c001_s3/tables/e5_c001_s3_readout_inventory.csv"
CSV_READOUT_ISSUES = REPO / "docs/experiments/joint-optimization/e5_c001_s3/tables/e5_c001_s3_readout_issues.csv"
CSV_REPAIR_ISSUES = REPO / "docs/experiments/joint-optimization/e5_c001_s3/tables/e5_c001_s3_405_repair_issues.csv"

BASE_405_BUILDING = REPO / "docs/experiments/joint-optimization/e5_c001_s2p/tables/e5_c001_s2p_405_rescore_building.csv"
BASE_405_REPAIR = REPO / "docs/experiments/joint-optimization/e5_c001_s2p/tables/e5_c001_s2p_405_rescore.csv"
S1_BUILDING = REPO / "docs/experiments/joint-optimization/e5_c001_3b_s1/tables/e5_c001_3b_s1_metrics.csv"
SEMANTIC_GATE = REPO / "docs/experiments/joint-optimization/e5_c001_s3/tables/e5_c001_s3_semantic_gate.csv"
SEED_INVENTORY = REPO / "docs/experiments/joint-optimization/e5_c001_s3/tables/e5_c001_s3_seed_inventory.csv"
NORMAL_MULTIVIEW = REPO / "docs/experiments/joint-optimization/e5_c001_s3/tables/e5_c001_s3_normal_multiview.csv"

PIPELINE_ORDER = (
    "final checkpoint -> canonical base pointcloudification -> Roofer assembly "
    "-> original val3dity -> ring-only 405 overlay -> repaired val3dity/evaluation"
)
COUNT_DEFINITION = (
    "all Gaussian centers inside exact footprint; no semantic-class or roof-height filter"
)

TIMELINE_FIELDS = [
    "arm", "replicate", "run_name", "step", "ckpt", "building_id",
    "n_gaussians_in_footprint", "z_p50", "z_std", "opacity_p50",
    "count_definition",
]
DENSIFY_FIELDS = [
    "arm", "replicate", "run_name", "interval_start_exclusive",
    "interval_end_inclusive", "building_id", "duplicate_events",
    "split_events", "total_events", "audit_steps", "source",
]


def rel(path: Path | str | None) -> str:
    if path is None:
        return ""
    value = Path(path)
    for root in (REPO, Path("/workspace/JointBuildGS")):
        try:
            return str(value.relative_to(root))
        except ValueError:
            pass
    text = str(value)
    prefix = "/workspace/JointBuildGS/"
    return text[len(prefix):] if text.startswith(prefix) else text


def full_id(value: str) -> str:
    return value if value.startswith("DEBY_LOD2_") else f"DEBY_LOD2_{value}"


def short_id(value: str) -> str:
    return value.replace("DEBY_LOD2_", "")


def fmt(value: Any, digits: int = 4) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    if isinstance(value, (float, np.floating)):
        number = float(value)
        return f"{number:.{digits}f}" if math.isfinite(number) else ""
    return str(value)


def number(value: Any) -> float | None:
    try:
        result = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def truth(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _union_fields(rows: Iterable[dict[str, Any]], preferred: Iterable[str] = ()) -> list[str]:
    fields = list(preferred)
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    return fields


def _allowed_write(path: Path) -> bool:
    resolved = path.resolve()
    exact_docs = {
        CSV_TIMELINE, CSV_DENSIFY, CSV_ARM_CELLS, CSV_405_BUILDING,
        CSV_405_REPAIR, CSV_405_REPAIR_STATUS, CSV_GABLE_MODE,
        CSV_REND_DIST, CSV_GLOBAL_Z, CSV_SHEET_OPACITY,
        CSV_PANEL_INVENTORY, CSV_INVENTORY, CSV_ISSUES, CSV_GATE_AUDIT,
        CSV_CHECKPOINT_GRADIENT_PAIRING,
        CSV_COVERAGE, CSV_FILTER, CSV_READOUT_SUMMARY, CSV_READOUT_TRADEOFF,
        CSV_READOUT_CASES, CSV_READOUT_INVENTORY, CSV_READOUT_ISSUES,
        CSV_REPAIR_ISSUES,
    }
    if resolved in {item.resolve() for item in exact_docs}:
        return True
    allowed_roots = [RESULTS_ROOT, RUN_DIR, P0_RUN_DIR, REPAIR_ROOT, FIG_DIR]
    return any(resolved == root.resolve() or resolved.is_relative_to(root.resolve()) for root in allowed_roots)


def guard_write(path: Path | str) -> Path:
    candidate = Path(path)
    text = rel(candidate).lower()
    forbidden = [
        "e5_s2p_interaction", "e5_c001_s2p", "e5p_s2p_interaction_20260710_c001",
        "e5p_s2p_405_repair_20260710_c001",
    ]
    if any(token in text for token in forbidden) or not _allowed_write(candidate):
        raise RuntimeError(f"S3 downstream write-path guard rejected: {candidate}")
    return candidate


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str] | None = None) -> None:
    path = guard_write(path)
    fields = fields or _union_fields(rows)
    if not fields:
        raise RuntimeError(f"refusing to write a headerless CSV: {rel(path)}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def validate_csv_schema(path: Path, required: Iterable[str], exact: bool = False) -> None:
    if not path.exists() or path.stat().st_size == 0:
        raise RuntimeError(f"CSV missing or empty: {rel(path)}")
    with path.open(newline="", encoding="utf-8") as handle:
        fields = next(csv.reader(handle), [])
    required_list = list(required)
    missing = [field for field in required_list if field not in fields]
    if missing or (exact and fields != required_list):
        raise RuntimeError(
            f"CSV schema mismatch for {rel(path)}: missing={missing}, "
            f"exact={exact}, observed={fields}"
        )


def validate_run_name(run_name: str, *, wave2: bool = False) -> str:
    allowed = [FULL_RUNS[0]] if wave2 else FULL_RUNS
    if run_name not in allowed:
        raise RuntimeError(f"run outside locked S3-A cells: {run_name}; allowed={allowed}")
    return run_name


def checkpoint_path(run_name: str, step: int | str) -> Path:
    validate_run_name(run_name)
    if step == "final" or step == 30000:
        return CKPT_ROOT / run_name / "ckpt/final.pt"
    return CKPT_ROOT / run_name / "ckpt" / f"step_{int(step):06d}.pt"


def _torch_load_safely(
    path: Path,
    expected_it: int,
    *,
    attempts: int = 12,
    retry_seconds: float = 0.5,
) -> dict[str, Any]:
    """Load a checkpoint only after a complete, iteration-matching read.

    ``torch.save`` writes the final path directly.  A Wave-2 poll can therefore
    see the filename before the zip stream is complete; transient EOF/zip
    errors are retried, but a completely loaded checkpoint with the wrong
    iteration is a hard provenance error.
    """

    import torch

    last_error: Exception | None = None
    for attempt in range(max(1, attempts)):
        try:
            if not path.exists() or path.stat().st_size <= 0:
                raise FileNotFoundError(path)
            payload = torch.load(path, map_location="cpu", weights_only=False)
            if not isinstance(payload, dict) or "state_dict" not in payload:
                raise RuntimeError(f"checkpoint payload contract missing state_dict: {rel(path)}")
            observed_it = int(payload.get("it", -1))
            if observed_it != int(expected_it):
                raise RuntimeError(
                    f"checkpoint iteration mismatch: expected={expected_it}, "
                    f"observed={observed_it}, path={rel(path)}"
                )
            return payload
        except RuntimeError as exc:
            # A successfully decoded but iteration-mismatched checkpoint must
            # never be retried as if it were a partial file.
            if "iteration mismatch" in str(exc) or "payload contract" in str(exc):
                raise
            last_error = exc
        except (FileNotFoundError, EOFError, OSError, ValueError) as exc:
            last_error = exc
        if attempt + 1 < max(1, attempts):
            time.sleep(max(0.0, retry_seconds))
    raise RuntimeError(
        f"checkpoint did not become readable after {attempts} attempts: {rel(path)}; "
        f"last_error={last_error!r}"
    )


def gaussian_stats_from_payload(
    payload: dict[str, Any],
    footprints: dict[str, dict[str, Any]],
    target_ids: list[str],
) -> list[dict[str, Any]]:
    import torch

    state = payload["state_dict"]
    if "means" not in state or "opacities_raw" not in state:
        raise RuntimeError("checkpoint lacks means/opacities_raw required by roofcrop audit")
    means_tensor = state["means"]
    opacity_tensor = state["opacities_raw"]
    means = means_tensor.detach().cpu().numpy().astype(np.float64) + s2p.s2.SHIFT_UTM
    opacity = torch.sigmoid(opacity_tensor.detach().cpu().float()).numpy().reshape(-1)
    if len(means) != len(opacity):
        raise RuntimeError("means/opacity length mismatch")
    rows: list[dict[str, Any]] = []
    for value in target_ids:
        building_id = full_id(value)
        footprint = footprints.get(building_id)
        if footprint is None:
            raise RuntimeError(f"footprint missing for Wave-2 target: {building_id}")
        x0, y0, x1, y1 = footprint["bbox"]
        prefilter = (
            (means[:, 0] >= x0 - 2.0) & (means[:, 0] <= x1 + 2.0)
            & (means[:, 1] >= y0 - 2.0) & (means[:, 1] <= y1 + 2.0)
        )
        indices = np.empty(0, dtype=np.int64)
        if np.any(prefilter):
            candidate = means[prefilter]
            inside = np.zeros(len(candidate), dtype=bool)
            for polygon_path in footprint["paths"]:
                inside |= polygon_path.contains_points(candidate[:, :2])
            indices = np.flatnonzero(prefilter)[inside]
        z = means[indices, 2]
        op = opacity[indices]
        rows.append(
            {
                "building_id": building_id,
                "n_gaussians_in_footprint": int(len(indices)),
                "z_p50": float(np.median(z)) if len(z) else None,
                "z_std": float(np.std(z)) if len(z) else None,
                "opacity_p50": float(np.median(op)) if len(op) else None,
            }
        )
    return rows


def _timeline_rows(run_name: str, step: int | str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    footprints = s2p.s2.load_footprints(TIMELINE_IDS)
    stats = gaussian_stats_from_payload(payload, footprints, TIMELINE_IDS)
    if [short_id(row["building_id"]) for row in stats] != TIMELINE_IDS:
        raise RuntimeError("Wave-2 target ordering/coverage contract failed")
    replicate = RUN_TO_REPLICATE[run_name]
    checkpoint = checkpoint_path(run_name, step)
    numeric_step = 30000 if step == "final" else int(step)
    return [
        {
            "arm": "s3a",
            "replicate": replicate,
            "run_name": run_name,
            "step": numeric_step,
            "ckpt": rel(checkpoint),
            **{key: fmt(value) for key, value in row.items()},
            "count_definition": COUNT_DEFINITION,
        }
        for row in stats
    ]


def _merge_timeline_rows(new_rows: list[dict[str, Any]], force: bool) -> list[dict[str, Any]]:
    existing = read_csv(CSV_TIMELINE)
    foreign = sorted({row.get("run_name", "") for row in existing} - set(FULL_RUNS))
    if foreign:
        raise RuntimeError(f"S3 timeline contains out-of-scope run names: {foreign}")
    key_fields = ("run_name", "step", "building_id")
    by_key: dict[tuple[str, str, str], dict[str, Any]] = {
        tuple(str(row.get(field, "")) for field in key_fields): row for row in existing
    }
    for row in new_rows:
        key = tuple(str(row.get(field, "")) for field in key_fields)
        previous = by_key.get(key)
        if previous is not None and not force:
            comparable = {field: str(row.get(field, "")) for field in TIMELINE_FIELDS}
            observed = {field: str(previous.get(field, "")) for field in TIMELINE_FIELDS}
            if comparable != observed:
                raise RuntimeError(f"timeline row collision with changed values: {key}")
            continue
        by_key[key] = row
    return sorted(
        by_key.values(),
        key=lambda row: (
            FULL_RUNS.index(str(row["run_name"])) if row.get("run_name") in FULL_RUNS else 99,
            int(row["step"]),
            TIMELINE_FULL_IDS.index(str(row["building_id"]))
            if row.get("building_id") in TIMELINE_FULL_IDS else 99,
        ),
    )


def wave2_roofcrop(args: argparse.Namespace) -> None:
    run_name = validate_run_name(args.run_name, wave2=True)
    if int(args.step) != 5000:
        raise RuntimeError("Wave-2 command is locked to r1 step_005000")
    checkpoint = checkpoint_path(run_name, 5000)
    payload = _torch_load_safely(
        checkpoint,
        5000,
        attempts=args.load_attempts,
        retry_seconds=args.retry_seconds,
    )
    rows = _timeline_rows(run_name, 5000, payload)
    if len(rows) != 7 or {row["building_id"] for row in rows} != set(TIMELINE_FULL_IDS):
        raise RuntimeError("Wave-2 must produce exactly the locked seven buildings")
    merged = _merge_timeline_rows(rows, args.force)
    write_csv(CSV_TIMELINE, merged, TIMELINE_FIELDS)
    validate_csv_schema(CSV_TIMELINE, TIMELINE_FIELDS, exact=True)
    counts = {short_id(row["building_id"]): int(row["n_gaussians_in_footprint"]) for row in rows}
    one_line = " ".join(f"{value}={counts[value]}" for value in TIMELINE_IDS)
    print(
        json.dumps(
            {
                "stage": "wave2_step_005000",
                "run_name": run_name,
                "checkpoint": rel(checkpoint),
                "checkpoint_sha256": sha256_file(checkpoint),
                "count_definition": COUNT_DEFINITION,
                "counts": counts,
                "wave_report": one_line,
                "output": rel(CSV_TIMELINE),
            },
            ensure_ascii=False,
        )
    )


def timeline_roofcrop(args: argparse.Namespace) -> None:
    new_rows: list[dict[str, Any]] = []
    for run_name in FULL_RUNS:
        for step in TIMELINE_STEPS:
            expected_it = 30000 if step == "final" else int(step)
            payload = _torch_load_safely(checkpoint_path(run_name, step), expected_it)
            new_rows.extend(_timeline_rows(run_name, step, payload))
    if len(new_rows) != 2 * len(TIMELINE_STEPS) * len(TIMELINE_IDS):
        raise RuntimeError("final timeline row-count contract failed")
    merged = _merge_timeline_rows(new_rows, args.force)
    s3_rows = [row for row in merged if row.get("run_name") in FULL_RUNS]
    if len(s3_rows) != len(new_rows):
        raise RuntimeError("timeline contains rows outside the two locked S3-A cells")
    write_csv(CSV_TIMELINE, merged, TIMELINE_FIELDS)
    validate_csv_schema(CSV_TIMELINE, TIMELINE_FIELDS, exact=True)
    _plot_timeline(merged)
    print(json.dumps({"timeline": rel(CSV_TIMELINE), "rows": len(merged)}, ensure_ascii=False))


def _plot_timeline(rows: list[dict[str, Any]]) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output_dir = guard_write(FIG_DIR / "timeline")
    output_dir.mkdir(parents=True, exist_ok=True)
    for building in TIMELINE_IDS:
        building_id = full_id(building)
        figure, axes = plt.subplots(2, 1, figsize=(7.8, 6.2), sharex=True, constrained_layout=True)
        for run_name in FULL_RUNS:
            part = sorted(
                [
                    row for row in rows
                    if row.get("run_name") == run_name and row.get("building_id") == building_id
                ],
                key=lambda row: int(row["step"]),
            )
            if len(part) != len(TIMELINE_STEPS):
                raise RuntimeError(f"timeline plot coverage incomplete for {run_name}/{building_id}")
            x = [int(row["step"]) / 1000.0 for row in part]
            counts = [int(row["n_gaussians_in_footprint"]) for row in part]
            z_values = [number(row.get("z_p50")) for row in part]
            label = f"S3-A {RUN_TO_REPLICATE[run_name]}"
            axes[0].plot(x, counts, marker="o", linewidth=1.5, label=label)
            axes[1].plot(
                [value for value, z in zip(x, z_values) if z is not None],
                [z for z in z_values if z is not None],
                marker="o", linewidth=1.5, label=label,
            )
        axes[0].set_ylabel("Gaussians in footprint")
        axes[1].set_ylabel("Median Z (m)")
        axes[1].set_xlabel("Training step (k)")
        axes[0].set_yscale("symlog", linthresh=10)
        for axis in axes:
            axis.grid(alpha=0.25)
            axis.legend(fontsize=8)
        figure.suptitle(f"S3-A roof-crop timeline: {building_id}", fontsize=11)
        figure.savefig(guard_write(output_dir / f"timeline_{building}.png"), dpi=180)
        plt.close(figure)


def densify_log(_args: argparse.Namespace) -> None:
    aggregated: dict[tuple[str, str, int, str], dict[str, int]] = defaultdict(
        lambda: {"duplicate_events": 0, "split_events": 0, "total_events": 0, "audit_steps": 0}
    )
    for run_name in FULL_RUNS:
        replicate = RUN_TO_REPLICATE[run_name]
        source = CKPT_ROOT / run_name / "audit/densify_events.csv"
        raw = read_csv(source)
        if not raw:
            raise RuntimeError(f"densify audit missing: {rel(source)}")
        seen: set[tuple[int, str]] = set()
        buildings_by_iteration: dict[int, set[str]] = defaultdict(set)
        for row in raw:
            iteration = int(row["iteration"])
            building_id = str(row["building_id"])
            key_raw = (iteration, building_id)
            if key_raw in seen:
                raise RuntimeError(f"duplicate densify audit key: {run_name}:{key_raw}")
            seen.add(key_raw)
            buildings_by_iteration[iteration].add(building_id)
            if building_id not in TIMELINE_FULL_IDS:
                continue
            interval_end = max(5000, int(math.ceil(iteration / 5000.0) * 5000))
            key = (run_name, replicate, interval_end, building_id)
            for field in ("duplicate_events", "split_events", "total_events"):
                aggregated[key][field] += int(row[field])
            aggregated[key]["audit_steps"] += 1
        incomplete = {
            iteration: sorted(set(TIMELINE_FULL_IDS) - buildings)
            for iteration, buildings in buildings_by_iteration.items()
            if set(TIMELINE_FULL_IDS) - buildings
        }
        if incomplete:
            preview = list(incomplete.items())[:3]
            raise RuntimeError(f"densify seven-building coverage incomplete for {run_name}: {preview}")
    rows: list[dict[str, Any]] = []
    for (run_name, replicate, interval_end, building_id), values in sorted(aggregated.items()):
        rows.append(
            {
                "arm": "s3a",
                "replicate": replicate,
                "run_name": run_name,
                "interval_start_exclusive": interval_end - 5000,
                "interval_end_inclusive": interval_end,
                "building_id": building_id,
                **values,
                "source": rel(CKPT_ROOT / run_name / "audit/densify_events.csv"),
            }
        )
    write_csv(CSV_DENSIFY, rows, DENSIFY_FIELDS)
    validate_csv_schema(CSV_DENSIFY, DENSIFY_FIELDS, exact=True)
    print(json.dumps({"densify_log": rel(CSV_DENSIFY), "rows": len(rows)}, ensure_ascii=False))


def _parse_train_log(path: Path) -> dict[str, str]:
    result = {"start_utc": "", "end_utc": "", "host_gpu": "", "return_code": "", "elapsed_min": ""}
    if not path.exists():
        return result
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        for source, target in [
            ("START_UTC=", "start_utc"),
            ("END_UTC=", "end_utc"),
            ("HOST_GPU=", "host_gpu"),
            ("RETURN_CODE=", "return_code"),
        ]:
            if line.startswith(source):
                result[target] = line.split("=", 1)[1].strip()
        if "[done]" in line and " iter in " in line:
            result["elapsed_min"] = line.split(" iter in ", 1)[1].split(" min", 1)[0].strip()
    return result


def fingerprint_training(_args: argparse.Namespace) -> None:
    rows: list[dict[str, Any]] = []
    for run_name in FULL_RUNS:
        replicate = RUN_TO_REPLICATE[run_name]
        config = CONFIG_DIR / f"{run_name}.yaml"
        effective = CKPT_ROOT / run_name / "effective_config.json"
        checkpoint = checkpoint_path(run_name, "final")
        log = TRAIN_LOG_ROOT / f"{run_name}.log"
        for required in (config, effective, checkpoint, log):
            if not required.exists():
                raise RuntimeError(f"training fingerprint input missing: {rel(required)}")
        payload = _torch_load_safely(checkpoint, 30000)
        config_payload = s2p.s2.yaml_load(config)
        effective_payload = json.loads(effective.read_text(encoding="utf-8"))
        log_info = _parse_train_log(log)
        if str(log_info.get("return_code")) != "0":
            raise RuntimeError(f"full training did not record RETURN_CODE=0: {rel(log)}")
        rows.append(
            {
                "record_type": "training_fingerprint",
                "arm": "s3a",
                "replicate": replicate,
                "run_name": run_name,
                "seed": config_payload.get("seed", ""),
                "config": rel(config),
                "config_sha256": sha256_file(config),
                "effective_config": rel(effective),
                "effective_config_sha256": sha256_file(effective),
                "ckpt": rel(checkpoint),
                "ckpt_sha256": sha256_file(checkpoint),
                **log_info,
                "max_iter": payload.get("it"),
                "final_n_gaussians": payload.get("n_prim", len(payload["state_dict"]["means"])),
                "w_normal": config_payload.get("w_normal", ""),
                "w_distort": config_payload.get("w_distort", ""),
                "prune_opa": config_payload.get("prune_opa", ""),
                "final_prune_opa": config_payload.get("final_prune_opa", ""),
                "w_semdepth_smooth": config_payload.get("w_semdepth_smooth", ""),
                "w_semdepth_plane": config_payload.get("w_semdepth_plane", ""),
                "w_boundary_normal": config_payload.get("w_boundary_normal", ""),
                "distort_norm_denominator": effective_payload.get("distort_norm_denominator", ""),
                "audit_csv": rel(CKPT_ROOT / run_name / "audit/loss_grad_norms.csv"),
                "semantic_audit": rel(CKPT_ROOT / run_name / "audit/semantic_geometry.csv"),
                "densify_audit": rel(CKPT_ROOT / run_name / "audit/densify_events.csv"),
            }
        )
    output = RUN_DIR / "train_fingerprints.csv"
    write_csv(output, rows)
    validate_csv_schema(
        output,
        ["record_type", "arm", "replicate", "run_name", "ckpt", "ckpt_sha256", "final_n_gaussians"],
    )
    print(json.dumps({"train_fingerprints": rel(output), "rows": len(rows)}, ensure_ascii=False))


def _rend_dist_from_audit(run_name: str) -> dict[str, Any]:
    audit_path = CKPT_ROOT / run_name / "audit/loss_grad_norms.csv"
    effective_path = CKPT_ROOT / run_name / "effective_config.json"
    if not audit_path.exists() or not effective_path.exists():
        raise RuntimeError(f"rend_dist inputs missing for {run_name}")
    effective = json.loads(effective_path.read_text(encoding="utf-8"))
    denominator = float(effective.get("distort_norm_denominator", 0.0) or 0.0)
    if denominator <= 0 or not math.isfinite(denominator):
        raise RuntimeError(f"invalid distort_norm_denominator for {run_name}: {denominator}")
    if not math.isclose(denominator, DISTORT_DENOMINATOR, rel_tol=1e-9, abs_tol=1e-6):
        raise RuntimeError(
            f"locked distort denominator drift for {run_name}: "
            f"expected={DISTORT_DENOMINATOR}, observed={denominator}"
        )
    values = [
        float(row["raw_loss"]) * denominator
        for row in read_csv(audit_path)
        if row.get("component") == "distort" and number(row.get("raw_loss")) is not None
    ][-10:]
    if len(values) != 10:
        raise RuntimeError(f"rend_dist requires ten tail audit rows for {run_name}; got {len(values)}")
    return {
        "rend_dist_mean_tail_m": fmt(float(np.mean(values))),
        "rend_dist_p50_tail_m": fmt(float(np.median(values))),
        "audit_rows_tail": len(values),
        "denominator": fmt(denominator),
        "audit_csv": rel(audit_path),
    }


def rend_dist(_args: argparse.Namespace) -> None:
    rows = [
        {
            "arm": "s3a",
            "replicate": RUN_TO_REPLICATE[run_name],
            "run_name": run_name,
            **_rend_dist_from_audit(run_name),
            "reconstruction": "tail raw_loss * effective distort_norm_denominator",
        }
        for run_name in FULL_RUNS
    ]
    fields = [
        "arm", "replicate", "run_name", "rend_dist_mean_tail_m",
        "rend_dist_p50_tail_m", "audit_rows_tail", "denominator", "audit_csv",
        "reconstruction",
    ]
    write_csv(CSV_REND_DIST, rows, fields)
    validate_csv_schema(CSV_REND_DIST, fields, exact=True)
    print(json.dumps({"rend_dist": rel(CSV_REND_DIST), "rows": len(rows)}, ensure_ascii=False))


def global_z_hist(_args: argparse.Namespace) -> None:
    import torch

    rows: list[dict[str, Any]] = []
    edges = np.arange(520.0, 702.0, 2.0)
    for run_name in FULL_RUNS:
        checkpoint = checkpoint_path(run_name, "final")
        payload = _torch_load_safely(checkpoint, 30000)
        state = payload["state_dict"]
        z = state["means"].detach().cpu().numpy()[:, 2].astype(np.float64) + s2p.s2.SHIFT_UTM[2]
        opacity = torch.sigmoid(state["opacities_raw"].detach().cpu().float()).numpy().reshape(-1)
        histogram, _ = np.histogram(z, bins=edges)
        for index, count in enumerate(histogram):
            selected = (z >= edges[index]) & (z < edges[index + 1])
            rows.append(
                {
                    "arm": "s3a",
                    "replicate": RUN_TO_REPLICATE[run_name],
                    "run_name": run_name,
                    "z_min": fmt(edges[index]),
                    "z_max": fmt(edges[index + 1]),
                    "n_gaussians": int(count),
                    "fraction_of_all": fmt(int(count) / len(z) if len(z) else None, 8),
                    "opacity_p50": fmt(float(np.median(opacity[selected])) if np.any(selected) else None),
                    "ckpt": rel(checkpoint),
                }
            )
    fields = [
        "arm", "replicate", "run_name", "z_min", "z_max", "n_gaussians",
        "fraction_of_all", "opacity_p50", "ckpt",
    ]
    write_csv(CSV_GLOBAL_Z, rows, fields)
    validate_csv_schema(CSV_GLOBAL_Z, fields, exact=True)
    _plot_global_z(rows)
    print(json.dumps({"global_z_hist": rel(CSV_GLOBAL_Z), "rows": len(rows)}, ensure_ascii=False))


def _plot_global_z(rows: list[dict[str, Any]]) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axis = plt.subplots(figsize=(9.2, 4.6), constrained_layout=True)
    for run_name in FULL_RUNS:
        part = [row for row in rows if row["run_name"] == run_name]
        centers = [(float(row["z_min"]) + float(row["z_max"])) / 2.0 for row in part]
        counts = [int(row["n_gaussians"]) for row in part]
        axis.plot(centers, counts, linewidth=1.4, label=f"S3-A {RUN_TO_REPLICATE[run_name]}")
    axis.set_yscale("symlog", linthresh=10)
    axis.set_xlabel("Global ellipsoidal Z (m)")
    axis.set_ylabel("Gaussian count / 2 m bin")
    axis.set_title("S3-A global Z distribution")
    axis.grid(alpha=0.25)
    axis.legend()
    output = guard_write(FIG_DIR / "summary/global_z_hist.png")
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=180)
    plt.close(figure)


def _sheet_sources() -> list[tuple[str, str, str, str, Path]]:
    sources: list[tuple[str, str, str, str, Path]] = []
    for replicate, base_run in ARM1P_BASE_RUNS.items():
        sources.append(("base", "arm1p", replicate, base_run, ARM1P_CKPT_ROOT / base_run / "ckpt/final.pt"))
    for run_name in FULL_RUNS:
        sources.append(("s3a", "s3a", RUN_TO_REPLICATE[run_name], run_name, checkpoint_path(run_name, "final")))
    return sources


def sheet_opacity_dist(_args: argparse.Namespace) -> None:
    import torch

    rows: list[dict[str, Any]] = []
    for family, cell, replicate, run_name, checkpoint in _sheet_sources():
        payload = _torch_load_safely(checkpoint, 30000)
        state = payload["state_dict"]
        z = state["means"].detach().cpu().numpy()[:, 2].astype(np.float64) + s2p.s2.SHIFT_UTM[2]
        opacity = torch.sigmoid(state["opacities_raw"].detach().cpu().float()).numpy().reshape(-1)
        for band, z_min, z_max in [("floater_595_615", 595.0, 615.0), ("high_655_670", 655.0, 670.0)]:
            in_band = (z >= z_min) & (z <= z_max)
            values = opacity[in_band]
            bins = [
                ("gt_0p5", values > 0.5),
                ("0p1_to_0p5", (values >= 0.1) & (values <= 0.5)),
                ("lt_0p1", values < 0.1),
            ]
            for opacity_bin, mask in bins:
                count = int(np.count_nonzero(mask))
                rows.append(
                    {
                        "family": family,
                        "cell": cell,
                        "replicate": replicate,
                        "run_name": run_name,
                        "band": band,
                        "z_min": z_min,
                        "z_max": z_max,
                        "opacity_bin": opacity_bin,
                        "n_gaussians": count,
                        "fraction_of_band": fmt(count / len(values) if len(values) else None, 8),
                        "band_total": len(values),
                        "opacity_p50": fmt(float(np.median(values)) if len(values) else None),
                        "high_opacity_core_present": str(bool(np.any(values > 0.5))).lower(),
                        "ckpt": rel(checkpoint),
                    }
                )
    fields = [
        "family", "cell", "replicate", "run_name", "band", "z_min", "z_max",
        "opacity_bin", "n_gaussians", "fraction_of_band", "band_total",
        "opacity_p50", "high_opacity_core_present", "ckpt",
    ]
    write_csv(CSV_SHEET_OPACITY, rows, fields)
    validate_csv_schema(CSV_SHEET_OPACITY, fields, exact=True)
    _plot_sheet_opacity(rows)
    print(json.dumps({"sheet_opacity_dist": rel(CSV_SHEET_OPACITY), "rows": len(rows)}, ensure_ascii=False))


def _plot_sheet_opacity(rows: list[dict[str, Any]]) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    order = [("arm1p", "r1"), ("arm1p", "r2"), ("s3a", "r1"), ("s3a", "r2")]
    labels = [f"{family} {replicate}" for family, replicate in order]
    x = np.arange(len(order))
    figure, axes = plt.subplots(1, 2, figsize=(10.2, 4.2), constrained_layout=True)
    for axis, band in zip(axes, ["floater_595_615", "high_655_670"]):
        values = []
        for family, replicate in order:
            matches = [
                row for row in rows
                if row.get("family") == ("base" if family == "arm1p" else "s3a")
                and row.get("replicate") == replicate
                and row.get("band") == band
                and row.get("opacity_bin") == "gt_0p5"
            ]
            if len(matches) != 1:
                raise RuntimeError(f"sheet plot source coverage mismatch: {family}/{replicate}/{band}")
            values.append(int(matches[0]["n_gaussians"]))
        axis.bar(x, values, color=["#8796A5", "#657786", "#2F6B4F", "#64A078"])
        axis.set_xticks(x)
        axis.set_xticklabels(labels, rotation=25, ha="right")
        axis.set_yscale("symlog", linthresh=10)
        axis.set_ylabel("Gaussians with opacity > 0.5")
        axis.set_title(band.replace("_", " "))
        axis.grid(axis="y", alpha=0.25)
    figure.suptitle("S3-A layer-band opacity distribution", fontsize=11)
    output = guard_write(FIG_DIR / "summary/sheet_opacity_bands.png")
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=180)
    plt.close(figure)


def full_loss_audit(_args: argparse.Namespace) -> None:
    existing = [
        row for row in read_csv(CSV_GATE_AUDIT)
        if not (
            row.get("record_type") in {"full_loss", "full_region"}
            and row.get("run_name") in FULL_RUNS
        )
    ]
    additions: list[dict[str, Any]] = []
    for run_name in FULL_RUNS:
        replicate = RUN_TO_REPLICATE[run_name]
        loss_path = CKPT_ROOT / run_name / "audit/loss_grad_norms.csv"
        semantic_path = CKPT_ROOT / run_name / "audit/semantic_geometry.csv"
        loss_rows = read_csv(loss_path)
        semantic_rows = read_csv(semantic_path)
        if not loss_rows or not semantic_rows:
            raise RuntimeError(f"full semantic audit inputs missing for {run_name}")
        observed_loss_steps = {
            int(row["step"]) for row in loss_rows
            if int(row["step"]) in FULL_AUDIT_STEPS and row.get("component") == "semdepth"
        }
        observed_semantic_steps = {
            int(row["step"]) for row in semantic_rows if int(row["step"]) in FULL_AUDIT_STEPS
        }
        if observed_loss_steps != FULL_AUDIT_STEPS or observed_semantic_steps != FULL_AUDIT_STEPS:
            raise RuntimeError(
                f"full 5k/final audit coverage mismatch for {run_name}: "
                f"loss={sorted(observed_loss_steps)}, semantic={sorted(observed_semantic_steps)}"
            )
        for row in loss_rows:
            step = int(row["step"])
            if step not in FULL_AUDIT_STEPS or row.get("component") not in {
                "semdepth", "semdepth_smooth", "semdepth_plane", "boundary_normal"
            }:
                continue
            additions.append(
                {
                    "record_type": "full_loss",
                    "arm": "s3a",
                    "replicate": replicate,
                    "run_name": run_name,
                    **row,
                    "source_csv": rel(loss_path),
                }
            )
        for row in semantic_rows:
            step = int(row["step"])
            if step not in FULL_AUDIT_STEPS:
                continue
            additions.append(
                {
                    "record_type": "full_region",
                    "arm": "s3a",
                    "replicate": replicate,
                    "run_name": run_name,
                    **row,
                    "source_csv": rel(semantic_path),
                }
            )
    combined = existing + additions
    fields = _union_fields(
        combined,
        ["record_type", "arm", "replicate", "run_name", "step", "component"],
    )
    write_csv(CSV_GATE_AUDIT, combined, fields)
    validate_csv_schema(
        CSV_GATE_AUDIT,
        ["record_type", "run_name", "step", "render_valid_fraction", "depth_anchor_fraction"],
    )
    print(json.dumps({"loss_gate_audit": rel(CSV_GATE_AUDIT), "appended_rows": len(additions)}, ensure_ascii=False))


def _selected_runs(args: argparse.Namespace) -> list[str]:
    selected = list(getattr(args, "runs", None) or FULL_RUNS)
    unknown = sorted(set(selected) - set(FULL_RUNS))
    if unknown:
        raise RuntimeError(f"unknown/out-of-scope S3-A runs: {unknown}")
    return [run_name for run_name in FULL_RUNS if run_name in set(selected)]


def _normalize_arm_fields(path: Path) -> None:
    rows = read_csv(path)
    if not rows:
        return
    changed = False
    for row in rows:
        run_name = row.get("run_name", "")
        if run_name in RUN_TO_REPLICATE:
            row["arm"] = "s3a"
            row["replicate"] = RUN_TO_REPLICATE[run_name]
            if row.get("input") == f"GS-guided-{RUN_TO_REPLICATE[run_name]}-base":
                row["input"] = f"GS-s3a-{RUN_TO_REPLICATE[run_name]}-base"
            changed = True
    if changed:
        write_csv(path, rows, list(rows[0]))


def _assert_readout_namespace() -> None:
    guarded_paths = [
        READOUT_ROOT, P0_RUN_DIR, REPAIR_ROOT, FIG_DIR,
        CSV_COVERAGE, CSV_FILTER, CSV_405_BUILDING, CSV_READOUT_SUMMARY,
        CSV_READOUT_TRADEOFF, CSV_READOUT_CASES, CSV_READOUT_INVENTORY,
        CSV_READOUT_ISSUES,
    ]
    for path in guarded_paths:
        guard_write(path)
    if P0_RUN_ID == s2p.P0_RUN_ID or REPAIR_RUN_ID == s2p.REPAIR_RUN_ID:
        raise RuntimeError("S3 P0/repair run IDs collide with S2p")


def configure_readout() -> None:
    """Bind the generic readout harness to an isolated S3-A namespace."""

    _assert_readout_namespace()
    ab = s2p.s2.ab
    eight = ab.load_eight_module()
    ab.RUN_ID = RUN_ID
    ab.P2_RUN_DIR = RUN_DIR
    ab.P0_RUN_ID = P0_RUN_ID
    ab.P0_RUN_DIR = P0_RUN_DIR
    ab.RESULTS_ROOT = READOUT_ROOT
    ab.CKPT_ROOT = CKPT_ROOT
    ab.TRAIN_RUN_DIR = RUN_DIR
    ab.CANON_GATE_DIR = REPO / "phases/p0-audit/runs/e5p_gate_20260707_C001"
    ab.DATA_ROOT = rel(DATA_ROOT)
    ab.TORCH_EXTENSIONS = rel(TORCH_EXTENSIONS)
    ab.FIG_DIR = FIG_DIR / "readout"
    ab.REPORT_PATH = RUN_DIR / "readout_tmp.md"
    ab.COVERAGE_CSV = CSV_COVERAGE
    ab.FILTER_CSV = CSV_FILTER
    ab.METRICS_CSV = CSV_405_BUILDING
    ab.SUMMARY_CSV = CSV_READOUT_SUMMARY
    ab.TRADEOFF_CSV = CSV_READOUT_TRADEOFF
    ab.CASE_CSV = CSV_READOUT_CASES
    ab.INVENTORY_CSV = CSV_READOUT_INVENTORY
    ab.ISSUES_CSV = CSV_READOUT_ISSUES
    ab.RENDER_COVERAGE = REPO / "docs/e5_c001_s3_render_readout_coverage.csv"
    ab.SETTINGS = [
        ab.Setting("base", "S3-A canonical base readout", min_obs=3, voxel=0.05, alpha=0.5, sor="on", sor_std=2.0)
    ]

    def selected_run_names(args: argparse.Namespace) -> list[str]:
        return _selected_runs(args)

    def run_names() -> list[str]:
        # The reusable harness otherwise parses its original S0/S1 run list.
        # Binding the exact S3-A names also prevents ``..._guided_r1`` from
        # being mistaken for an arm named ``guided`` in helper loops.
        return list(FULL_RUNS)

    def source_for(setting: Any, run_name: str) -> Any:
        validate_run_name(run_name)
        repaired_root = REPAIRED_P0_RUN_DIR / setting.key
        original_root = P0_RUN_DIR / setting.key
        repaired_status = repaired_root / "status" / f"{run_name}_run_1.csv"
        repaired_cityjson = repaired_root / "cityjson" / f"{run_name}_run_1.city.json"
        use_repaired = repaired_status.exists() and repaired_cityjson.exists()
        return eight.Source(
            source_group="gs_s3a",
            source_run=f"{setting.key}__{run_name}",
            display_label=f"S3-A {RUN_TO_REPLICATE[run_name]}",
            status_role="gs",
            status_path=(
                repaired_status
                if use_repaired
                else original_root / "status" / f"{run_name}_run_1.csv"
            ),
            status_input=None,
            cityjson_path=(
                repaired_cityjson
                if use_repaired
                else original_root / "cityjson" / f"{run_name}_run_1.city.json"
            ),
            pointcloud_path=None,
            pointcloud_template=str(
                original_root / "roofer" / run_name / "run_1" / "{bid}_run_1_classified.las"
            ),
            pair_raw=None,
            run_name=run_name,
            seed="2001",
            replicate=RUN_TO_REPLICATE[run_name],
            readout=(
                setting.readout_label
                + ("; 405 winding repair overlay" if use_repaired else "; original Roofer shell")
            ),
            source_badge=f"{setting.key}_{'405repair' if use_repaired else 'original'}",
            z_shift_to_reference_m=-45.7,
        )

    def readout_fingerprint(setting: Any, run_name: str, paths: dict[str, Path]) -> dict[str, Any]:
        metrics: dict[str, Any] = {}
        if paths["metrics"].exists():
            metrics = json.loads(paths["metrics"].read_text(encoding="utf-8"))
        return {
            "setting": setting.key,
            "run_name": run_name,
            "arm": "s3a",
            "replicate": RUN_TO_REPLICATE[run_name],
            "tsdf_npz": rel(paths["npz"]),
            "tsdf_sha256": sha256_file(paths["npz"]) if paths["npz"].exists() else "missing",
            "coverage_csv": rel(paths["coverage"]),
            "metrics_json": rel(paths["metrics"]),
            "log": rel(paths["log"]),
            "min_obs": setting.min_obs,
            "voxel": setting.voxel,
            "alpha": setting.alpha,
            "sor": setting.sor,
            "sor_std": setting.sor_std,
            "surf_backproj": metrics.get("surf_backproj", ""),
            "fused_all": metrics.get("fused_all", ""),
            "minobs_kept": metrics.get("minobs_kept", ""),
            "sor_kept": metrics.get("sor_kept", ""),
            "readout": setting.readout_label,
        }

    def write_readout_report(*_args: Any, **_kwargs: Any) -> None:
        path = guard_write(ab.REPORT_PATH)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "# S3-A readout temporary material\n\n"
            f"Pipeline order: {PIPELINE_ORDER}.\n",
            encoding="utf-8",
        )

    ab.selected_run_names = selected_run_names
    ab.run_names = run_names
    ab.source_for = source_for
    ab.readout_fingerprint = readout_fingerprint
    ab.write_report = write_readout_report


def _evaluation_container(args: argparse.Namespace) -> None:
    configure_readout()
    if os.environ.get("E5_S3A_EVAL_CONTAINER") == "1":
        s2p.s2.ab.evaluate(args)
        for path in [CSV_405_BUILDING, CSV_COVERAGE, CSV_FILTER, CSV_READOUT_CASES]:
            _normalize_arm_fields(path)
        validate_csv_schema(
            CSV_405_BUILDING,
            ["building_id", "run_name", "replicate", "has_lod22", "val3dity_valid", "completeness", "ref_rms_m"],
        )
        return
    command = [
        "docker", "run", "--rm", "-i", "--user", f"{os.getuid()}:{os.getgid()}",
        "-e", "HOME=/tmp", "-e", "MPLCONFIGDIR=/tmp/matplotlib",
        "-e", "XDG_CACHE_HOME=/tmp", "-e", "E5_S3A_EVAL_CONTAINER=1",
        "-v", f"{REPO}:/workspace/JointBuildGS", "-w", "/workspace/JointBuildGS",
        "jointbuildgs-p0-tools:t0", "python3", rel(SCRIPT_PATH), "evaluate",
        "--settings", *args.settings,
    ]
    if args.force:
        command.append("--force")
    if args.runs:
        command.extend(["--runs", *args.runs])
    s2p.s2.ab.run(command, log_path=RUN_DIR / "evaluate_container.log", check=True, quiet=False)


def readout_like(args: argparse.Namespace) -> None:
    configure_readout()
    ab = s2p.s2.ab
    if args.cmd == "readout":
        ab.run_readout(args)
        _normalize_arm_fields(RUN_DIR / "readout_fingerprints.csv")
    elif args.cmd == "assemble":
        ab.run_assemble(args)
        for setting in args.settings:
            for run_name in _selected_runs(args):
                _normalize_arm_fields(
                    P0_RUN_DIR / setting / "status" / f"{run_name}_run_1.csv"
                )
        _normalize_arm_fields(P0_RUN_DIR / "building_reconstruction_status.csv")
    elif args.cmd == "evaluate":
        _evaluation_container(args)
    else:
        raise RuntimeError(f"unsupported readout stage: {args.cmd}")


def repair_405(args: argparse.Namespace) -> None:
    if os.environ.get("E5_S3A_REPAIR_CONTAINER") != "1":
        raise RuntimeError(
            "repair-405 must run inside jointbuildgs-p0-tools:t0 with "
            "E5_S3A_REPAIR_CONTAINER=1"
        )
    _assert_readout_namespace()
    import e5_c001_405_repair as repair

    repair.RUN_ID = REPAIR_RUN_ID
    repair.REPAIR_ROOT = REPAIR_ROOT
    repair.CSV_SUMMARY = CSV_405_REPAIR
    repair.CSV_BUILDING = CSV_405_REPAIR_STATUS
    repair.CSV_ISSUES = CSV_REPAIR_ISSUES
    repair.process(
        argparse.Namespace(
            source_run_id=[P0_RUN_ID],
            settings=["base"],
            include_factor=False,
            append=False,
            force=args.force,
        )
    )
    validate_csv_schema(
        CSV_405_REPAIR,
        ["run_name", "error_405_original", "error_405_repaired", "error_302_repaired", "vertices_same"],
    )
    print(
        json.dumps(
            {
                "repair_405": rel(CSV_405_REPAIR),
                "pipeline_order": PIPELINE_ORDER,
                "canonical_mutated": False,
            },
            ensure_ascii=False,
        )
    )


def _circular_distance_deg(a: float, b: float) -> float:
    return abs((a - b + 180.0) % 360.0 - 180.0)


def _parse_azimuths(value: Any) -> list[float]:
    result: list[float] = []
    for token in str(value or "").split(";"):
        parsed = number(token)
        if parsed is not None:
            result.append(parsed % 360.0)
    return result


def azimuth_hit(predicted: Any, reference: Any, threshold_deg: float = 25.0) -> tuple[bool, float | None]:
    pred = _parse_azimuths(predicted)
    ref = _parse_azimuths(reference)
    if not pred or not ref:
        return False, None
    minimum = min(_circular_distance_deg(a, b) for a in pred for b in ref)
    return minimum <= threshold_deg, minimum


def _gable_sources() -> list[tuple[str, str, str, Path]]:
    sources: list[tuple[str, str, str, Path]] = []
    for replicate, run_name in ARM1P_BASE_RUNS.items():
        sources.append(
            (
                "arm1p_base",
                replicate,
                run_name,
                ARM1P_REPAIRED_ROOT / "cityjson" / f"{run_name}_run_1.city.json",
            )
        )
    for run_name in FULL_RUNS:
        sources.append(
            (
                "s3a",
                RUN_TO_REPLICATE[run_name],
                run_name,
                REPAIRED_P0_RUN_DIR / "base/cityjson" / f"{run_name}_run_1.city.json",
            )
        )
    return sources


def gable_mode(_args: argparse.Namespace) -> None:
    all_ids = list(s2p.s2.C001_IDS)
    references = s2p.s2.eight.parse_lod2_roofs(s2p.s2.eight.LOD2_DIR, set(all_ids))
    reference_summary = {
        building_id: s2p._roof_mode_summary(surfaces)
        for building_id, surfaces in references.items()
    }
    rows: list[dict[str, Any]] = []
    for family, replicate, run_name, cityjson in _gable_sources():
        if not cityjson.exists():
            raise RuntimeError(f"repaired CityJSON missing for gable audit: {rel(cityjson)}")
        predictions = s2p.s2.eight.parse_cityjson_roofs(cityjson, set(all_ids))
        for building_id in all_ids:
            predicted = s2p._roof_mode_summary(predictions.get(building_id, []))
            reference = reference_summary.get(building_id, s2p._roof_mode_summary([]))
            hit, minimum = azimuth_hit(
                predicted["direction_mode_azimuths_deg"],
                reference["direction_mode_azimuths_deg"],
            )
            mode_count = int(predicted["direction_mode_count"])
            rows.append(
                {
                    "family": family,
                    "arm": "s3a" if family == "s3a" else "arm1p",
                    "replicate": replicate,
                    "run_name": run_name,
                    "building_id": building_id,
                    "pk_target": str(short_id(building_id) in PK_TARGETS).lower(),
                    "has_lod22": str(bool(predictions.get(building_id))).lower(),
                    "pred_direction_mode_count": mode_count,
                    "ref_direction_mode_count": reference["direction_mode_count"],
                    "mode_count_delta": mode_count - int(reference["direction_mode_count"]),
                    "pred_mode_azimuths_deg": predicted["direction_mode_azimuths_deg"],
                    "ref_mode_azimuths_deg": reference["direction_mode_azimuths_deg"],
                    "azimuth_min_abs_delta_deg": fmt(minimum),
                    "azimuth_within_25deg": str(hit).lower(),
                    "mode_ge1_and_azimuth_within_25deg": str(mode_count >= 1 and hit).lower(),
                    "pred_roof_face_count": predicted["roof_face_count"],
                    "ref_roof_face_count": reference["roof_face_count"],
                    "pred_sloped_face_count": predicted["sloped_face_count"],
                    "ref_sloped_face_count": reference["sloped_face_count"],
                    "mode_definition": "3D roof normals; tilt>10deg; circular merge<=25deg; retain>=5% sloped area",
                    "cityjson": rel(cityjson),
                }
            )
    write_csv(CSV_GABLE_MODE, rows)
    validate_csv_schema(
        CSV_GABLE_MODE,
        [
            "family", "run_name", "building_id", "pk_target",
            "pred_direction_mode_count", "ref_mode_azimuths_deg",
            "azimuth_within_25deg", "mode_ge1_and_azimuth_within_25deg",
        ],
    )
    print(json.dumps({"gable_mode": rel(CSV_GABLE_MODE), "rows": len(rows)}, ensure_ascii=False))


def _s3_panel_sources() -> list[Any]:
    eight = s2p.s2.eight
    sources = list(s2p._panel_sources())
    for run_name in FULL_RUNS:
        replicate = RUN_TO_REPLICATE[run_name]
        sources.append(
            eight.Source(
                "gs_s3a",
                f"s3a_{replicate}",
                f"S3-A {replicate}",
                "gs",
                REPAIRED_P0_RUN_DIR / "base/status" / f"{run_name}_run_1.csv",
                None,
                REPAIRED_P0_RUN_DIR / "base/cityjson" / f"{run_name}_run_1.city.json",
                None,
                pointcloud_template=str(
                    P0_RUN_DIR / "base/roofer" / run_name / "run_1" / "{bid}_run_1_classified.las"
                ),
                run_name=run_name,
                seed="2001",
                replicate=replicate,
                readout="canonical base readout; 405 ring overlay",
                source_badge="base_405repair",
                z_shift_to_reference_m=s2p.s2.ELLIP_TO_REF_SHIFT_M,
            )
        )
    if len(sources) != 10:
        raise RuntimeError(f"legacy 8way + S3 r1/r2 must have ten sources, got {len(sources)}")
    return sources


def panels_8way(_args: argparse.Namespace) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    full_ids = [full_id(value) for value in PANEL_IDS]
    sources = _s3_panel_sources()
    polygons, footprints = s2p._footprint_polygons(PANEL_IDS)
    references = s2p.s2.eight.parse_lod2_roofs(s2p.s2.eight.LOD2_DIR, set(full_ids))
    predictions: dict[str, dict[str, list[Any]]] = {}
    for source in sources:
        if source.source_run == "reference":
            predictions[source.source_run] = references
        elif source.cityjson_path and source.cityjson_path.exists():
            parsed = s2p.s2.eight.parse_cityjson_roofs(source.cityjson_path, set(full_ids))
            predictions[source.source_run] = {
                building_id: s2p.s2.eight.shift_surface_z(surfaces, source.z_shift_to_reference_m)
                for building_id, surfaces in parsed.items()
            }
        else:
            raise RuntimeError(f"panel CityJSON missing: {source.display_label}: {source.cityjson_path}")
    point_cache = s2p.s2.eight.PointCloudCache(polygons)
    out_dir = guard_write(FIG_DIR / "8way_panels")
    out_dir.mkdir(parents=True, exist_ok=True)
    inventory: list[dict[str, Any]] = []
    for value in PANEL_IDS:
        building_id = full_id(value)
        footprint = footprints[building_id]
        axis = s2p._panel_axis(footprint)
        reference_surfaces = references.get(building_id, [])
        reference_points = s2p._reference_cloud(reference_surfaces)
        z_limits = (
            (float(np.percentile(reference_points[:, 2], 1)) - 3.0,
             float(np.percentile(reference_points[:, 2], 99)) + 3.0)
            if len(reference_points)
            else (560.0, 590.0)
        )
        clouds: dict[str, np.ndarray] = {}
        for source in sources:
            if source.source_run == "reference":
                points = reference_points
            else:
                points = point_cache.read_roof_points(source, building_id)
                if len(points) and source.z_shift_to_reference_m:
                    points = points.copy()
                    points[:, 2] += float(source.z_shift_to_reference_m)
            clouds[source.source_run] = points
        n_columns = len(sources)
        figure = plt.figure(figsize=(2.25 * n_columns, 8.0), constrained_layout=True)
        for column, source in enumerate(sources, start=1):
            points = clouds[source.source_run]
            surfaces = predictions[source.source_run].get(building_id, [])
            s2p._draw_panel_top(
                figure.add_subplot(3, n_columns, column), points, footprint, source.display_label
            )
            s2p._draw_panel_side(
                figure.add_subplot(3, n_columns, n_columns + column),
                points, footprint, axis, z_limits,
            )
            s2p.s2.eight.draw_model(
                figure.add_subplot(3, n_columns, 2 * n_columns + column, projection="3d"),
                surfaces,
                polygons[building_id],
                "assembled model" if source.source_run != "reference" else "reference LoD2",
                f"roof faces {len(surfaces)}",
            )
            inventory.append(
                {
                    "building_id": building_id,
                    "source_run": source.source_run,
                    "display_label": source.display_label,
                    "source_count": n_columns,
                    "legacy_panel_name": "8way",
                    "point_count_in_footprint": len(points),
                    "roof_face_count": len(surfaces),
                    "pointcloud_source": (
                        source.pointcloud_template
                        or (rel(source.pointcloud_path) if source.pointcloud_path else "reference samples")
                    ),
                    "cityjson": rel(source.cityjson_path) if source.cityjson_path else "reference LoD2",
                    "z_shift_to_reference_m": source.z_shift_to_reference_m,
                }
            )
        figure.suptitle(f"C001 S3-A legacy-8way plus r1/r2: {building_id}", fontsize=12)
        output = guard_write(out_dir / f"8way_{value}.png")
        figure.savefig(output, dpi=170)
        plt.close(figure)
        for row in inventory[-len(sources):]:
            row["figure"] = rel(output)
    write_csv(CSV_PANEL_INVENTORY, inventory)
    validate_csv_schema(
        CSV_PANEL_INVENTORY,
        ["building_id", "source_run", "source_count", "legacy_panel_name", "figure"],
    )
    print(json.dumps({"panel_inventory": rel(CSV_PANEL_INVENTORY), "rows": len(inventory), "sources": 10}, ensure_ascii=False))


def _metric_rows_by_run(path: Path, expected_runs: set[str]) -> dict[tuple[str, str], dict[str, str]]:
    rows = read_csv(path)
    if not rows:
        raise RuntimeError(f"building-score table missing or empty: {rel(path)}")
    selected = [
        row for row in rows
        if row.get("run_name") in expected_runs and row.get("setting", "base") == "base"
    ]
    by_key: dict[tuple[str, str], dict[str, str]] = {}
    for row in selected:
        key = (row.get("run_name", ""), row.get("building_id", ""))
        if key in by_key:
            raise RuntimeError(f"duplicate building score key in {rel(path)}: {key}")
        by_key[key] = row
    expected_ids = {full_id(value) for value in s2p.s2.C001_IDS}
    for run_name in sorted(expected_runs):
        observed = {building_id for run, building_id in by_key if run == run_name}
        if observed != expected_ids:
            raise RuntimeError(
                f"C00118 score coverage mismatch for {run_name} in {rel(path)}: "
                f"missing={sorted(expected_ids - observed)}, extra={sorted(observed - expected_ids)}"
            )
    return by_key


def _repair_by_run(path: Path, expected_runs: set[str]) -> dict[str, dict[str, str]]:
    rows = read_csv(path)
    if not rows:
        raise RuntimeError(f"405 summary missing or empty: {rel(path)}")
    selected = [
        row for row in rows
        if row.get("run_name") in expected_runs and row.get("setting", "base") == "base"
    ]
    by_run = {row["run_name"]: row for row in selected}
    if set(by_run) != expected_runs or len(selected) != len(expected_runs):
        raise RuntimeError(
            f"405 summary run coverage mismatch in {rel(path)}: "
            f"expected={sorted(expected_runs)}, observed={sorted(by_run)}"
        )
    for run_name, row in by_run.items():
        coordinate_delta = number(row.get("coordinate_rms_delta_m"))
        if (
            not truth(row.get("vertices_same"))
            or coordinate_delta is None
            or abs(coordinate_delta) > 1e-12
        ):
            raise RuntimeError(f"405 overlay changed coordinates for {run_name}")
    return by_run


def _score_value(row: dict[str, str], field: str) -> float | None:
    return number(row.get(field))


def _source_run_summary(
    metrics: dict[tuple[str, str], dict[str, str]], run_name: str
) -> dict[str, Any]:
    part = [row for (run, _building), row in metrics.items() if run == run_name]
    rms = [value for value in (_score_value(row, "ref_rms_m") for row in part) if value is not None]
    return {
        "assembled": sum(truth(row.get("has_lod22")) for row in part),
        "valid_assembled": sum(
            truth(row.get("has_lod22")) and truth(row.get("val3dity_valid")) for row in part
        ),
        "invalid_assembled": sum(
            truth(row.get("has_lod22")) and not truth(row.get("val3dity_valid")) for row in part
        ),
        "median_ref_rms_m": float(np.median(rms)) if rms else None,
    }


def arm_cells(_args: argparse.Namespace) -> None:
    """Build locked five-axis observation material for S3-A.

    This command performs only the preregistered mechanical comparisons.  It
    deliberately emits no GO/NO-GO or research verdict.
    """

    s3_metrics = _metric_rows_by_run(CSV_405_BUILDING, set(FULL_RUNS))
    base_runs = set(ARM1P_BASE_RUNS.values())
    base_metrics = _metric_rows_by_run(BASE_405_BUILDING, base_runs)
    s3_repairs = _repair_by_run(CSV_405_REPAIR, set(FULL_RUNS))
    base_repairs = _repair_by_run(BASE_405_REPAIR, base_runs)
    unrepaired_score_rows = [
        key for key, row in s3_metrics.items()
        if row.get("source_badge") != "base_405repair"
        or "405 winding repair overlay" not in row.get("readout", "")
    ]
    if unrepaired_score_rows:
        raise RuntimeError(
            "S3 building scores must be regenerated from the post-Roofer 405 overlay; "
            f"unrepaired_or_unmarked={unrepaired_score_rows[:3]}"
        )

    fingerprints = read_csv(RUN_DIR / "train_fingerprints.csv")
    fingerprint_by = {
        row.get("run_name", ""): row
        for row in fingerprints
        if row.get("run_name") in FULL_RUNS
    }
    if set(fingerprint_by) != set(FULL_RUNS):
        raise RuntimeError("training fingerprints must cover exactly S3-A r1/r2 before arm-cells")
    rend_by = {
        row.get("run_name", ""): row
        for row in read_csv(CSV_REND_DIST)
        if row.get("run_name") in FULL_RUNS
    }
    if set(rend_by) != set(FULL_RUNS):
        raise RuntimeError("rend_dist table must cover exactly S3-A r1/r2 before arm-cells")
    timeline_by = {
        (row.get("run_name", ""), int(row.get("step", -1)), row.get("building_id", "")): row
        for row in read_csv(CSV_TIMELINE)
        if row.get("run_name") in FULL_RUNS and str(row.get("step", "")).isdigit()
    }
    missing_timeline = [
        (run_name, step, full_id(building))
        for run_name in FULL_RUNS
        for step in (5000, 10000)
        for building in TIMELINE_IDS
        if (run_name, step, full_id(building)) not in timeline_by
    ]
    if missing_timeline:
        raise RuntimeError(f"timeline 5k/10k coverage incomplete before arm-cells: {missing_timeline[:5]}")
    gable_by = {
        (row.get("run_name", ""), short_id(row.get("building_id", ""))): row
        for row in read_csv(CSV_GABLE_MODE)
        if row.get("run_name") in FULL_RUNS
    }
    missing_gable = [
        (run_name, building_id)
        for run_name in FULL_RUNS
        for building_id in PK_TARGETS
        if (run_name, building_id) not in gable_by
    ]
    if missing_gable:
        raise RuntimeError(f"gable-mode target coverage incomplete: {missing_gable}")

    s1_rows = read_csv(S1_BUILDING)
    s1_by = {
        row.get("building_id", ""): row
        for row in s1_rows
        if row.get("source_run") == "base__gs_e5_C001_s1_dense_r1"
    }

    rows: list[dict[str, Any]] = []
    for run_name in FULL_RUNS:
        replicate = RUN_TO_REPLICATE[run_name]
        base_run = ARM1P_BASE_RUNS[replicate]
        source = _source_run_summary(s3_metrics, run_name)

        authentic_ids: list[str] = []
        textureless_detail: list[str] = []
        for building in TEXTURELESS3:
            metric = s3_metrics[(run_name, full_id(building))]
            rms = _score_value(metric, "ref_rms_m")
            completeness = _score_value(metric, "completeness")
            authentic = (
                truth(metric.get("has_lod22"))
                and truth(metric.get("val3dity_valid"))
                and rms is not None and rms <= 3.0
                and completeness is not None and completeness >= 0.5
            )
            if authentic:
                authentic_ids.append(building)
            textureless_detail.append(
                f"{building}:authentic={str(authentic).lower()},rms={fmt(rms)},"
                f"valid={str(truth(metric.get('val3dity_valid'))).lower()},"
                f"completeness={fmt(completeness)}"
            )
        axis1_met = len(authentic_ids) >= 1

        paired_deltas: list[float] = []
        s1_deltas: list[float] = []
        paired_detail: list[str] = []
        for building in GOOD6:
            building_id = full_id(building)
            s3_rms = _score_value(s3_metrics[(run_name, building_id)], "ref_rms_m")
            base_rms = _score_value(base_metrics[(base_run, building_id)], "ref_rms_m")
            delta = None if s3_rms is None or base_rms is None else s3_rms - base_rms
            if delta is not None:
                paired_deltas.append(delta)
            s1_rms = _score_value(s1_by.get(building_id, {}), "ref_rms_m")
            if s3_rms is not None and s1_rms is not None:
                s1_deltas.append(s3_rms - s1_rms)
            paired_detail.append(
                f"{building}:s3={fmt(s3_rms)},arm1p={fmt(base_rms)},delta={fmt(delta)}"
            )
        paired_median = float(np.median(paired_deltas)) if paired_deltas else None
        catastrophe_count = sum(delta > 1.5 for delta in paired_deltas)
        axis2_met = (
            len(paired_deltas) == len(GOOD6)
            and paired_median is not None and paired_median <= 0.3
            and catastrophe_count == 0
        )

        shape_fields: dict[str, Any] = {}
        pk_hits: list[str] = []
        for building in PK_TARGETS:
            shape = gable_by[(run_name, building)]
            if truth(shape.get("mode_ge1_and_azimuth_within_25deg")):
                pk_hits.append(building)
            shape_fields.update(
                {
                    f"shape_{building}_mode_count": shape.get("pred_direction_mode_count", ""),
                    f"shape_{building}_azimuths_deg": shape.get("pred_mode_azimuths_deg", ""),
                    f"shape_{building}_azimuth_min_delta_deg": shape.get("azimuth_min_abs_delta_deg", ""),
                    f"shape_{building}_mode_ge1_azimuth_within25": shape.get(
                        "mode_ge1_and_azimuth_within_25deg", ""
                    ),
                }
            )

        s3_repair = s3_repairs[run_name]
        base_repair = base_repairs[base_run]
        s3_302 = _score_value(s3_repair, "error_302_repaired")
        base_302 = _score_value(base_repair, "error_302_repaired")
        final_n = _score_value(fingerprint_by[run_name], "final_n_gaussians")
        rend = _score_value(rend_by[run_name], "rend_dist_mean_tail_m")
        count_within = final_n is not None and final_n <= GAUSSIAN_COUNT_THRESHOLD
        rend_within = rend is not None and rend <= 0.5
        watched_5k = _score_value(
            timeline_by[(run_name, 5000, full_id("4907202"))],
            "n_gaussians_in_footprint",
        )
        watched_10k = _score_value(
            timeline_by[(run_name, 10000, full_id("4907202"))],
            "n_gaussians_in_footprint",
        )
        watched_survival = (
            None
            if watched_5k is None or watched_10k is None or watched_5k <= 0
            else watched_10k / watched_5k
        )
        pj_counts = ";".join(
            f"{building}={timeline_by[(run_name, 5000, full_id(building))].get('n_gaussians_in_footprint', '')}"
            for building in TEXTURELESS3
        )

        rows.append(
            {
                "row_scope": "run",
                "arm": "s3a",
                "replicate": replicate,
                "run_name": run_name,
                "claim_scope": "oracle-label mechanism upper bound; not FM/paper claim",
                "axis1_completeness_threshold": "textureless3 authentic>=1; authentic=rms<=3m AND valid AND completeness>=0.5",
                "axis1_authentic_count": len(authentic_ids),
                "axis1_authentic_buildings": ";".join(authentic_ids),
                "axis1_textureless_detail": ";".join(textureless_detail),
                "axis1_locked_line_met": str(axis1_met).lower(),
                "axis2_accuracy_threshold": "good6 paired vs Arm1p same replicate: median<=+0.3m AND catastrophe(+1.5m)>0 count=0",
                "axis2_pair_count": len(paired_deltas),
                "axis2_expected_pair_count": len(GOOD6),
                "axis2_paired_median_delta_vs_arm1p_m": fmt(paired_median),
                "axis2_paired_max_delta_vs_arm1p_m": fmt(max(paired_deltas) if paired_deltas else None),
                "axis2_catastrophe_count": catastrophe_count,
                "axis2_pair_detail": ";".join(paired_detail),
                "axis2_locked_line_met": str(axis2_met).lower(),
                "axis2_observed_median_delta_vs_s1_dense_r1_m": fmt(
                    float(np.median(s1_deltas)) if s1_deltas else None
                ),
                "axis3_shape_scoring": "observation_only; RMS good with mode_count=0 is not shape success",
                "axis3_pk_mode_ge1_azimuth_within25_buildings": ";".join(pk_hits),
                "axis3_pk_any_mode_ge1_azimuth_within25": str(bool(pk_hits)).lower(),
                **shape_fields,
                "axis4_validity_scoring": "observation_only",
                "axis4_assembled_count": source["assembled"],
                "axis4_valid_assembled_count": source["valid_assembled"],
                "axis4_invalid_assembled_count": source["invalid_assembled"],
                "axis4_error302_repaired": fmt(s3_302),
                "axis4_error302_arm1p_same_replicate": fmt(base_302),
                "axis4_error302_delta_vs_arm1p": fmt(
                    None if s3_302 is None or base_302 is None else s3_302 - base_302
                ),
                "axis5_cleaning_scoring": "observation_only; N<=1150636 and rend_dist<=0.5 monitored",
                "axis5_final_n_gaussians": fmt(final_n),
                "axis5_n_threshold": GAUSSIAN_COUNT_THRESHOLD,
                "axis5_n_within_threshold": str(count_within).lower(),
                "axis5_rend_dist_mean_tail_m": fmt(rend),
                "axis5_rend_dist_threshold_m": 0.5,
                "axis5_rend_dist_within_threshold": str(rend_within).lower(),
                "axis5_both_observations_within": str(count_within and rend_within).lower(),
                "all18_median_ref_rms_m": fmt(source["median_ref_rms_m"]),
                "locked_i_and_ii_this_run": str(axis1_met and axis2_met).lower(),
                "prediction_pj_5k_textureless_counts": pj_counts,
                "watch_4907202_5k_count": fmt(watched_5k),
                "watch_4907202_10k_count": fmt(watched_10k),
                "watch_4907202_survival_ratio": fmt(watched_survival, 6),
                "watch_s2p_reference_survival_ratio": fmt(38 / 463, 6),
                "watch_survival_above_s2p_reference": str(
                    watched_survival is not None and watched_survival > 38 / 463
                ).lower(),
                "human_verdict": "not_assigned",
                "paired_base_run": base_run,
                "ckpt": fingerprint_by[run_name].get("ckpt", ""),
                "readout": "canonical base; post-Roofer ring-only 405 overlay; repaired evaluation",
            }
        )

    axis1_both = all(truth(row["axis1_locked_line_met"]) for row in rows)
    axis2_both = all(truth(row["axis2_locked_line_met"]) for row in rows)
    combined_both = axis1_both and axis2_both
    rows.append(
        {
            "row_scope": "two_run_aggregate",
            "arm": "s3a",
            "replicate": "r1+r2",
            "run_name": "s3a_two_run_aggregate",
            "claim_scope": "oracle-label mechanism upper bound; not FM/paper claim",
            "axis1_locked_line_met": str(axis1_both).lower(),
            "axis2_locked_line_met": str(axis2_both).lower(),
            "locked_i_and_ii_this_run": "not_applicable",
            "two_run_axis1_both_met": str(axis1_both).lower(),
            "two_run_axis2_both_met": str(axis2_both).lower(),
            "two_run_i_and_ii_both_met": str(combined_both).lower(),
            "mechanical_branch_material": (
                "both_locked_lines_observed_in_both_runs"
                if combined_both else "one_or_more_locked_lines_not_observed_in_both_runs"
            ),
            "human_verdict": "not_assigned",
            "readout": "aggregate of r1/r2 mechanical observations only",
        }
    )
    write_csv(CSV_ARM_CELLS, rows)
    validate_csv_schema(
        CSV_ARM_CELLS,
        [
            "row_scope", "arm", "replicate", "run_name",
            "axis1_locked_line_met", "axis2_locked_line_met",
            "two_run_i_and_ii_both_met", "human_verdict",
        ],
    )
    _plot_arm_cells(rows[:2])
    print(
        json.dumps(
            {
                "arm_cells": rel(CSV_ARM_CELLS),
                "run_rows": 2,
                "aggregate_rows": 1,
                "human_verdict": "not_assigned",
            },
            ensure_ascii=False,
        )
    )


def _plot_arm_cells(rows: list[dict[str, Any]]) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if len(rows) != 2:
        raise RuntimeError("five-axis plot requires exactly two S3-A run rows")
    x = np.arange(2)
    labels = [str(row["replicate"]) for row in rows]
    figure, axes = plt.subplots(1, 4, figsize=(13.2, 3.8), constrained_layout=True)
    axes[0].bar(x, [int(row["axis1_authentic_count"]) for row in rows], color="#2F6B4F")
    axes[0].axhline(1, color="#333333", linestyle="--", linewidth=1)
    axes[0].set_title("Authentic textureless roofs")
    axes[1].bar(
        x,
        [number(row["axis2_paired_median_delta_vs_arm1p_m"]) or 0.0 for row in rows],
        color="#496F9B",
    )
    axes[1].axhline(0.3, color="#333333", linestyle="--", linewidth=1)
    axes[1].set_title("Good6 paired median delta")
    axes[1].set_ylabel("m vs Arm1-prime")
    axes[2].bar(x, [int(row["axis4_valid_assembled_count"]) for row in rows], color="#7A6993")
    axes[2].set_title("Valid assembled / 18")
    axes[3].bar(
        x,
        [number(row["axis5_rend_dist_mean_tail_m"]) or 0.0 for row in rows],
        color="#B7831B",
    )
    axes[3].axhline(0.5, color="#333333", linestyle="--", linewidth=1)
    axes[3].set_title("rend_dist tail")
    axes[3].set_ylabel("m")
    for axis in axes:
        axis.set_xticks(x)
        axis.set_xticklabels(labels)
        axis.grid(axis="y", alpha=0.25)
    figure.suptitle("S3-A five-axis observation material (no human verdict)", fontsize=11)
    output = guard_write(FIG_DIR / "summary/five_axis_material.png")
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=180)
    plt.close(figure)


def _downstream_artifact_specs() -> list[tuple[str, Path, list[str]]]:
    return [
        ("semantic_gate_reference", SEMANTIC_GATE, ["row_type", "building_id", "iou"]),
        (
            "seed_inventory",
            SEED_INVENTORY,
            ["building_id", "sfm_seed_points_in_footprint", "initial_gaussians_in_footprint"],
        ),
        (
            "normal_multiview",
            NORMAL_MULTIVIEW,
            ["building_id", "view_rank", "building_angle_error_median_deg_absdot"],
        ),
        ("loss_gate_and_full_audit", CSV_GATE_AUDIT, ["record_type", "run_name"]),
        ("timeline_roofcrop", CSV_TIMELINE, TIMELINE_FIELDS),
        (
            "checkpoint_gradient_pairing",
            CSV_CHECKPOINT_GRADIENT_PAIRING,
            [
                "record_type",
                "claim_scope",
                "run_name",
                "step",
                "building_id",
                "semdepth_depth_grad_norm",
                "semdepth_depth_grad_rms",
                "semdepth_depth_grad_norm_share",
                "semdepth_depth_grad_nonzero_pixel_count",
                "alpha_valid_pixel_count",
                "depth_anchor_pixel_count",
                "plane_residual_huber_mean",
            ],
        ),
        ("densify_log", CSV_DENSIFY, DENSIFY_FIELDS),
        (
            "405_rescore_building",
            CSV_405_BUILDING,
            ["building_id", "run_name", "setting", "ref_rms_m", "completeness"],
        ),
        (
            "405_repair_summary",
            CSV_405_REPAIR,
            ["run_name", "error_405_original", "error_405_repaired", "vertices_same"],
        ),
        (
            "405_repair_status_building",
            CSV_405_REPAIR_STATUS,
            ["building_id", "run_name"],
        ),
        (
            "gable_mode",
            CSV_GABLE_MODE,
            ["run_name", "building_id", "pred_direction_mode_count", "azimuth_within_25deg"],
        ),
        ("rend_dist", CSV_REND_DIST, ["run_name", "rend_dist_mean_tail_m"]),
        ("global_z_hist", CSV_GLOBAL_Z, ["run_name", "z_min", "z_max", "n_gaussians"]),
        (
            "sheet_opacity_dist",
            CSV_SHEET_OPACITY,
            ["family", "run_name", "band", "opacity_bin", "n_gaussians"],
        ),
        (
            "legacy8way_plus_s3_panel_inventory",
            CSV_PANEL_INVENTORY,
            ["building_id", "source_run", "source_count", "figure"],
        ),
        (
            "five_axis_arm_cells",
            CSV_ARM_CELLS,
            ["row_scope", "run_name", "axis1_locked_line_met", "axis2_locked_line_met", "human_verdict"],
        ),
    ]


def _validate_final_artifact_contract(
    artifact: str, path: Path, rows: list[dict[str, str]]
) -> None:
    run_set = {row.get("run_name", "") for row in rows if row.get("run_name")}
    if artifact == "semantic_gate_reference":
        medians = {
            row.get("building_id", "")
            for row in rows if row.get("row_type") == "building_median"
        }
        expected = {full_id(value) for value in TEXTURELESS3 + GOOD6}
        if medians != expected or len(rows) != 4 * len(expected):
            raise RuntimeError(
                f"semantic-gate reference coverage mismatch: medians={sorted(medians)}, rows={len(rows)}"
            )
    elif artifact == "seed_inventory":
        expected = {full_id(value) for value in TEXTURELESS3 + CORE4[:3]}
        observed = {row.get("building_id", "") for row in rows}
        if observed != expected or len(rows) != len(expected):
            raise RuntimeError(f"seed inventory coverage mismatch: {sorted(observed)}")
    elif artifact == "normal_multiview":
        expected = {
            full_id(value)
            for value in TEXTURELESS3 + GOOD6 + ["60098", "4907186", "4907188", "4907194", "4907195"]
        }
        by_building: dict[str, int] = defaultdict(int)
        for row in rows:
            by_building[row.get("building_id", "")] += 1
        if set(by_building) != expected or any(count < 3 for count in by_building.values()):
            raise RuntimeError(f"normal multi-view coverage mismatch: {dict(sorted(by_building.items()))}")
    elif artifact == "loss_gate_and_full_audit":
        for run_name in FULL_RUNS:
            loss_steps = {
                int(row["step"]) for row in rows
                if row.get("run_name") == run_name and row.get("record_type") == "full_loss"
            }
            region_steps = {
                int(row["step"]) for row in rows
                if row.get("run_name") == run_name and row.get("record_type") == "full_region"
            }
            if loss_steps != FULL_AUDIT_STEPS or region_steps != FULL_AUDIT_STEPS:
                raise RuntimeError(
                    f"full loss/region audit coverage mismatch for {run_name}: "
                    f"loss={sorted(loss_steps)}, region={sorted(region_steps)}"
                )
    elif artifact == "timeline_roofcrop":
        expected_keys = {
            (run_name, 30000 if step == "final" else int(step), full_id(building))
            for run_name in FULL_RUNS for step in TIMELINE_STEPS for building in TIMELINE_IDS
        }
        observed = {
            (row.get("run_name", ""), int(row.get("step", -1)), row.get("building_id", ""))
            for row in rows
        }
        if observed != expected_keys:
            raise RuntimeError("timeline final key coverage mismatch")
    elif artifact == "checkpoint_gradient_pairing":
        allowed_types = {
            "fixed_view",
            "collapse_building_median",
            "organization_building_median",
            "collapse_timeline_pair",
        }
        observed_types = {row.get("record_type", "") for row in rows}
        if observed_types != allowed_types:
            raise RuntimeError(
                f"checkpoint-gradient record types mismatch: {sorted(observed_types)}"
            )
        if any(row.get("claim_scope") != CHECKPOINT_GRADIENT_CLAIM_SCOPE for row in rows):
            raise RuntimeError("checkpoint-gradient claim scope is missing or broadened")

        fixed_rows = [row for row in rows if row.get("record_type") == "fixed_view"]
        fixed_groups: dict[tuple[str, int, str], list[dict[str, str]]] = defaultdict(list)
        for row in fixed_rows:
            fixed_groups[
                (row.get("run_name", ""), int(row.get("step", -1)), row.get("building_id", ""))
            ].append(row)
        expected_fixed_groups = {
            (run_name, step, building_id)
            for run_name in FULL_RUNS
            for step in CHECKPOINT_GRADIENT_STEPS
            for building_id in CHECKPOINT_GRADIENT_ALL_TARGETS
        }
        if set(fixed_groups) != expected_fixed_groups:
            raise RuntimeError("checkpoint-gradient fixed-view target coverage is not exact 2x6x4")
        for key, group in fixed_groups.items():
            stems = {row.get("view_stem", "") for row in group}
            ranks = {row.get("view_rank", "") for row in group}
            if len(group) != 3 or len(stems) != 3 or "" in stems or ranks != {"1", "2", "3"}:
                raise RuntimeError(f"checkpoint-gradient fixed-view triplet mismatch: {key}")
            if any(
                row.get("view_selection_scope")
                != CHECKPOINT_GRADIENT_VIEW_SELECTION_SCOPE
                for row in group
            ):
                raise RuntimeError(f"checkpoint-gradient fixed-view selector drift: {key}")

        collapse_expected = {
            (run_name, step, building_id)
            for run_name in FULL_RUNS
            for step in CHECKPOINT_GRADIENT_STEPS
            for building_id in CHECKPOINT_GRADIENT_COLLAPSE_TARGETS
        }
        organization_expected = {
            (run_name, step, building_id)
            for run_name in FULL_RUNS
            for step in CHECKPOINT_GRADIENT_STEPS
            for building_id in CHECKPOINT_GRADIENT_ORGANIZATION_TARGETS
        }

        def keys_for(record_type: str) -> set[tuple[str, int, str]]:
            selected_rows = [row for row in rows if row.get("record_type") == record_type]
            keys = {
                (row.get("run_name", ""), int(row.get("step", -1)), row.get("building_id", ""))
                for row in selected_rows
            }
            if len(keys) != len(selected_rows):
                raise RuntimeError(f"checkpoint-gradient duplicate keys for {record_type}")
            return keys

        if keys_for("collapse_building_median") != collapse_expected:
            raise RuntimeError("checkpoint-gradient collapse medians are not exact 36")
        if keys_for("organization_building_median") != organization_expected:
            raise RuntimeError("checkpoint-gradient organization medians are not exact 12")
        if keys_for("collapse_timeline_pair") != collapse_expected:
            raise RuntimeError("checkpoint-gradient timeline pairs are not exact 36")
        if len(rows) != 144 + 36 + 12 + 36:
            raise RuntimeError(f"checkpoint-gradient row count mismatch: {len(rows)}")

        required_numeric = (
            "alpha_valid_pixel_count",
            "depth_anchor_pixel_count",
            "semdepth_depth_grad_norm",
            "semdepth_depth_grad_rms",
            "semdepth_depth_grad_norm_share",
            "semdepth_depth_grad_nonzero_pixel_count",
            "semdepth_depth_grad_nonzero_fraction",
        )
        for row_index, row in enumerate(rows, start=2):
            for field in required_numeric:
                if number(row.get(field)) is None:
                    raise RuntimeError(
                        f"checkpoint-gradient numeric field missing/nonfinite: row={row_index}, field={field}"
                    )
        for row in rows:
            if row.get("record_type") == "collapse_timeline_pair" and number(
                row.get("n_gaussians_in_footprint")
            ) is None:
                raise RuntimeError("checkpoint-gradient timeline pair lacks material count")
    elif artifact == "densify_log":
        expected = {(run_name, full_id(building)) for run_name in FULL_RUNS for building in TIMELINE_IDS}
        observed = {(row.get("run_name", ""), row.get("building_id", "")) for row in rows}
        if observed != expected:
            raise RuntimeError("densify final run/building coverage mismatch")
    elif artifact == "405_rescore_building":
        if run_set != set(FULL_RUNS) or len(rows) != 2 * len(s2p.s2.C001_IDS):
            raise RuntimeError(f"S3 repaired building-score coverage mismatch: runs={run_set}, rows={len(rows)}")
        if any(row.get("source_badge") != "base_405repair" for row in rows):
            raise RuntimeError("S3 building score contains a non-405-repaired source")
    elif artifact == "405_repair_summary":
        if run_set != set(FULL_RUNS) or len(rows) != 2:
            raise RuntimeError("S3 405 summary must contain exactly r1/r2")
        _repair_by_run(path, set(FULL_RUNS))
    elif artifact == "405_repair_status_building":
        if run_set != set(FULL_RUNS) or len(rows) != 2 * len(s2p.s2.C001_IDS):
            raise RuntimeError("S3 405 per-building status must contain exact C00118 x r1/r2")
    elif artifact == "gable_mode":
        s3_rows = [row for row in rows if row.get("run_name") in FULL_RUNS]
        if run_set != set(FULL_RUNS) | set(ARM1P_BASE_RUNS.values()) or len(s3_rows) != 36:
            raise RuntimeError("gable-mode comparison must contain Arm1p and S3 r1/r2")
    elif artifact == "rend_dist":
        if run_set != set(FULL_RUNS) or len(rows) != 2:
            raise RuntimeError("rend_dist must contain exactly S3 r1/r2")
    elif artifact == "global_z_hist":
        if run_set != set(FULL_RUNS) or len(rows) != 180:
            raise RuntimeError("global z histogram must contain 90 bins for each S3 run")
    elif artifact == "sheet_opacity_dist":
        expected_runs = set(FULL_RUNS) | set(ARM1P_BASE_RUNS.values())
        if run_set != expected_runs or len(rows) != 24:
            raise RuntimeError("sheet/opacity table must contain Arm1p+S3, two bands, three bins")
    elif artifact == "legacy8way_plus_s3_panel_inventory":
        if len(rows) != len(PANEL_IDS) * 10:
            raise RuntimeError("legacy-8way plus S3 panel inventory must contain six buildings x ten sources")
    elif artifact == "five_axis_arm_cells":
        scopes = [row.get("row_scope") for row in rows]
        if scopes.count("run") != 2 or scopes.count("two_run_aggregate") != 1:
            raise RuntimeError("five-axis table must contain two run rows plus one aggregate row")


def _merge_downstream_issues() -> int:
    preserved = [
        row for row in read_csv(CSV_ISSUES)
        if row.get("record_type") != "downstream_issue"
    ]
    additions: list[dict[str, Any]] = []
    for label, source in [
        ("readout", CSV_READOUT_ISSUES),
        ("405_repair", CSV_REPAIR_ISSUES),
    ]:
        for row_index, row in enumerate(read_csv(source), start=2):
            additions.append(
                {
                    **row,
                    "record_type": "downstream_issue",
                    "issue_source": label,
                    "source_csv": rel(source),
                    "source_row": row_index,
                }
            )
    combined = preserved + additions
    write_csv(
        CSV_ISSUES,
        combined,
        _union_fields(
            combined,
            ["record_type", "issue_id", "date", "task", "severity", "status", "summary"],
        ),
    )
    return len(additions)


def _git_output(*args: str) -> str:
    process = subprocess.run(
        ["git", *args], cwd=REPO, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, check=False,
    )
    return (process.stdout or "").strip()


def _validated_final_figures() -> list[tuple[str, Path]]:
    overlays = sorted((FIG_DIR / "semantic_gate").glob("*.png"))
    if len(overlays) < 27:
        raise RuntimeError(
            f"semantic overlay gallery requires at least 27 selected-view PNGs, got {len(overlays)}"
        )
    figures: list[tuple[str, Path]] = [("semantic_gate_overlay", path) for path in overlays]
    figures.extend(
        ("timeline", FIG_DIR / "timeline" / f"timeline_{building}.png")
        for building in TIMELINE_IDS
    )
    figures.extend(
        ("legacy8way_plus_s3_panel", FIG_DIR / "8way_panels" / f"8way_{building}.png")
        for building in PANEL_IDS
    )
    figures.extend(
        [
            ("global_z_hist", FIG_DIR / "summary/global_z_hist.png"),
            ("sheet_opacity_bands", FIG_DIR / "summary/sheet_opacity_bands.png"),
            ("five_axis_material", FIG_DIR / "summary/five_axis_material.png"),
            ("survival_gradient_pairing", FIG_SURVIVAL_GRADIENT_PAIRING),
            ("organization_plane_residual", FIG_ORGANIZATION_PLANE_RESIDUAL),
        ]
    )
    missing = [rel(path) for _kind, path in figures if not path.is_file() or path.stat().st_size == 0]
    if missing:
        raise RuntimeError(f"final figure contract missing/empty: {missing[:8]}")
    return figures


def inventory(_args: argparse.Namespace) -> None:
    existing = [
        row for row in read_csv(CSV_INVENTORY)
        if row.get("record_type") != "downstream_artifact"
    ]
    artifact_rows: list[dict[str, Any]] = []
    for artifact, path, required_fields in _downstream_artifact_specs():
        validate_csv_schema(path, required_fields)
        data_rows = read_csv(path)
        _validate_final_artifact_contract(artifact, path, data_rows)
        source_counts = {
            int(value)
            for value in (number(row.get("source_count")) for row in data_rows)
            if value is not None
        }
        if path == CSV_PANEL_INVENTORY and source_counts != {10}:
            raise RuntimeError(
                f"legacy 8way + S3 r1/r2 panel inventory must record source_count=10, got {source_counts}"
            )
        artifact_rows.append(
            {
                "record_type": "downstream_artifact",
                "phase": "final_readout",
                "artifact": artifact,
                "path": rel(path),
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
                "data_rows": len(data_rows),
                "required_fields": ";".join(required_fields),
                "schema_status": "pass",
                "canonical_mutated": "false",
                "claim_scope": "oracle-label mechanism upper bound; not FM/paper claim",
                "pipeline_order": PIPELINE_ORDER,
            }
        )
    for figure_kind, path in _validated_final_figures():
        artifact_rows.append(
            {
                "record_type": "downstream_artifact",
                "phase": "final_figure",
                "artifact": figure_kind,
                "path": rel(path),
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
                "data_rows": "",
                "required_fields": "PNG",
                "schema_status": "pass",
                "canonical_mutated": "false",
                "claim_scope": "oracle-label mechanism upper bound; not FM/paper claim",
                "pipeline_order": PIPELINE_ORDER,
            }
        )
    issue_count = _merge_downstream_issues()
    if not CSV_ISSUES.exists() or CSV_ISSUES.stat().st_size == 0:
        raise RuntimeError(f"issues artifact missing after aggregation: {rel(CSV_ISSUES)}")
    artifact_rows.append(
        {
            "record_type": "downstream_artifact",
            "phase": "final_readout",
            "artifact": "issues",
            "path": rel(CSV_ISSUES),
            "sha256": sha256_file(CSV_ISSUES),
            "bytes": CSV_ISSUES.stat().st_size,
            "data_rows": len(read_csv(CSV_ISSUES)),
            "required_fields": "task issue schema union; source preserved",
            "schema_status": "pass",
            "canonical_mutated": "false",
            "claim_scope": "oracle-label mechanism upper bound; not FM/paper claim",
            "pipeline_order": PIPELINE_ORDER,
        }
    )
    write_csv(CSV_INVENTORY, existing + artifact_rows)
    validate_csv_schema(CSV_INVENTORY, ["record_type"])

    versions = guard_write(RUN_DIR / "downstream_versions.txt")
    versions.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"run_id: {RUN_ID}",
        f"timestamp_utc: {datetime.now(timezone.utc).isoformat()}",
        f"git_head: {_git_output('rev-parse', 'HEAD')}",
        f"git_branch: {_git_output('branch', '--show-current')}",
        "crs: EPSG:25832",
        "canonical_changed: no",
        "human_verdict: not_assigned",
        "claim_scope: oracle-label mechanism upper bound; not FM/paper claim",
        f"pipeline_order: {PIPELINE_ORDER}",
        f"wave2_count_definition: {COUNT_DEFINITION}",
        f"dev_image: {DEV_IMAGE}",
        "evaluation_image: jointbuildgs-p0-tools:t0",
        f"adapter: {rel(SCRIPT_PATH)}",
        f"adapter_sha256: {sha256_file(SCRIPT_PATH)}",
        f"inventory: {rel(CSV_INVENTORY)}",
        f"issues: {rel(CSV_ISSUES)}",
    ]
    for row in artifact_rows:
        lines.append(f"artifact: {row['path']} sha256={row['sha256']}")
    versions.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "inventory": rel(CSV_INVENTORY),
                "artifact_rows": len(artifact_rows),
                "aggregated_downstream_issues": issue_count,
                "versions": rel(versions),
                "canonical_mutated": False,
            },
            ensure_ascii=False,
        )
    )


def check_contracts(_args: argparse.Namespace) -> None:
    _assert_readout_namespace()
    for run_name in FULL_RUNS:
        validate_run_name(run_name)
        if RUN_TO_REPLICATE[run_name] not in ARM1P_BASE_RUNS:
            raise RuntimeError(f"missing same-replicate Arm1-prime mapping for {run_name}")
    if len(TIMELINE_IDS) != 7 or len(set(TIMELINE_IDS)) != 7:
        raise RuntimeError("Wave-2/timeline target contract must contain seven unique buildings")
    if len(_s3_panel_sources()) != 10:
        raise RuntimeError("legacy 8way plus S3 source contract is not ten")
    print(
        json.dumps(
            {
                "status": "pass",
                "full_runs": FULL_RUNS,
                "wave2_run": FULL_RUNS[0],
                "timeline_buildings": TIMELINE_IDS,
                "panel_source_count": 10,
                "pipeline_order": PIPELINE_ORDER,
                "canonical_mutated": False,
            },
            ensure_ascii=False,
        )
    )


def repair_405_or_container(args: argparse.Namespace) -> None:
    if os.environ.get("E5_S3A_REPAIR_CONTAINER") == "1":
        repair_405(args)
        return
    command = [
        "docker", "run", "--rm", "-i", "--user", f"{os.getuid()}:{os.getgid()}",
        "-e", "HOME=/tmp", "-e", "MPLCONFIGDIR=/tmp/matplotlib",
        "-e", "XDG_CACHE_HOME=/tmp", "-e", "E5_S3A_REPAIR_CONTAINER=1",
        "-v", f"{REPO}:/workspace/JointBuildGS", "-w", "/workspace/JointBuildGS",
        "jointbuildgs-p0-tools:t0", "python3", rel(SCRIPT_PATH), "repair-405",
    ]
    if args.force:
        command.append("--force")
    s2p.s2.ab.run(command, log_path=RUN_DIR / "repair_405_container.log", check=True, quiet=False)


def checkpoint_gradient_pairing_or_container(args: argparse.Namespace) -> None:
    """Launch the read-only checkpoint sweep in the locked CUDA image.

    The worker never calls this adapter recursively and owns no training
    command.  It loads frozen checkpoints and differentiates only a detached
    rendered-depth leaf.
    """

    command = [
        "docker",
        "run",
        "--rm",
        "-i",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
    ]
    if not args.preflight_only:
        command.extend(["--gpus", "all"])
    command.extend([
        "-e",
        "HOME=/tmp",
        "-e",
        "MPLCONFIGDIR=/tmp/matplotlib",
        "-e",
        "XDG_CACHE_HOME=/tmp",
        "-e",
        "E5_S3A_GRADIENT_PAIRING_CONTAINER=1",
        "-e",
        f"TORCH_EXTENSIONS_DIR=/workspace/JointBuildGS/{rel(TORCH_EXTENSIONS)}",
        "-v",
        f"{REPO}:/workspace/JointBuildGS",
        "-w",
        "/workspace/JointBuildGS",
        DEV_IMAGE,
        "python3",
        rel(CHECKPOINT_GRADIENT_PAIRING_SCRIPT),
        "--views-per-building",
        str(args.views_per_building),
    ])
    if not args.preflight_only:
        image_index = command.index(DEV_IMAGE)
        command[image_index:image_index] = ["-e", f"CUDA_VISIBLE_DEVICES={args.gpu}"]
    else:
        command.append("--preflight-only")
    if args.force:
        command.append("--force")
    s2p.s2.ab.run(
        command,
        log_path=RUN_DIR / (
            "checkpoint_gradient_pairing_preflight_container.log"
            if args.preflight_only
            else "checkpoint_gradient_pairing_container.log"
        ),
        check=True,
        quiet=False,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    wave2 = sub.add_parser(
        "wave2-roofcrop",
        help="safely read only r1 step_005000 and emit the locked seven-building count",
    )
    wave2.add_argument("--run-name", default=FULL_RUNS[0], choices=[FULL_RUNS[0]])
    wave2.add_argument("--step", type=int, default=5000, choices=[5000])
    wave2.add_argument("--load-attempts", type=int, default=12)
    wave2.add_argument("--retry-seconds", type=float, default=0.5)
    wave2.add_argument("--force", action="store_true")

    timeline = sub.add_parser("timeline-roofcrop")
    timeline.add_argument("--force", action="store_true")
    gradient_pairing = sub.add_parser(
        "checkpoint-gradient-pairing",
        help="read-only fixed-view checkpoint gradient-potential pairing audit",
    )
    gradient_pairing.add_argument("--gpu", default="1")
    gradient_pairing.add_argument("--views-per-building", type=int, default=3, choices=[3])
    gradient_pairing.add_argument("--preflight-only", action="store_true")
    gradient_pairing.add_argument("--force", action="store_true")
    for command in [
        "densify-log", "fingerprint-training", "rend-dist", "global-z-hist",
        "sheet-opacity-dist", "full-loss-audit", "gable-mode", "panels-8way",
        "arm-cells", "inventory", "check-contracts",
    ]:
        sub.add_parser(command)

    for name in ["readout", "assemble", "evaluate", "all"]:
        stage = sub.add_parser(name)
        stage.add_argument("--settings", nargs="+", default=["base"], choices=["base"])
        stage.add_argument("--runs", nargs="+", default=None, choices=FULL_RUNS)
        stage.add_argument("--force", action="store_true")
        stage.add_argument("--data-root", default=rel(DATA_ROOT))
        stage.add_argument("--torch-extensions", default=rel(TORCH_EXTENSIONS))
        stage.add_argument("--gpu", default="0")
        stage.add_argument("--buffer-m", type=float, default=20.0)
    repair = sub.add_parser("repair-405")
    repair.add_argument("--force", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    actions = {
        "wave2-roofcrop": wave2_roofcrop,
        "timeline-roofcrop": timeline_roofcrop,
        "checkpoint-gradient-pairing": checkpoint_gradient_pairing_or_container,
        "densify-log": densify_log,
        "fingerprint-training": fingerprint_training,
        "rend-dist": rend_dist,
        "global-z-hist": global_z_hist,
        "sheet-opacity-dist": sheet_opacity_dist,
        "full-loss-audit": full_loss_audit,
        "gable-mode": gable_mode,
        "panels-8way": panels_8way,
        "arm-cells": arm_cells,
        "inventory": inventory,
        "check-contracts": check_contracts,
    }
    if args.cmd in actions:
        actions[args.cmd](args)
    elif args.cmd in {"readout", "assemble", "evaluate"}:
        readout_like(args)
    elif args.cmd == "all":
        for stage_name in ["readout", "assemble", "evaluate"]:
            stage_args = argparse.Namespace(**vars(args))
            stage_args.cmd = stage_name
            readout_like(stage_args)
    elif args.cmd == "repair-405":
        repair_405_or_container(args)
    else:
        raise RuntimeError(f"unsupported command: {args.cmd}")


if __name__ == "__main__":
    main()
