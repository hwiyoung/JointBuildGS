#!/usr/bin/env python3
"""Re-aggregate the A-wave score inventory by one fixed GS condition at a time.

This is a learning-zero correction layer over ``docs/qs_rescore_scores.csv``.
It never switches GS conditions between buildings.  The prior per-building
minimum-RMS selection is retained only as an explicitly labelled oracle audit.
No CityJSON, point cloud, checkpoint, or reference geometry is opened here.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp")

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


REPO = Path(__file__).resolve().parents[3]
DOCS = REPO / "docs"
RUN_DIR = REPO / "phases/p2-gsjso/runs/20260717_qs_rescore_fixed_conditions"
SCORES = DOCS / "qs_rescore_scores.csv"
PAIRS = DOCS / "qs_rescore_pairs.csv"
SOURCE_MANIFEST = REPO / "phases/p2-gsjso/runs/20260716_qs_rescore/manifest.json"
CONDITIONS = DOCS / "qs_rescore_fixed_conditions.csv"
ORACLE_AUDIT = DOCS / "qs_rescore_oracle_audit.csv"
FIGURE = DOCS / "figs/qs_rescore/qs_rescore_fixed_condition_scatter.png"
MANIFEST = RUN_DIR / "manifest.json"
LOG = RUN_DIR / "run.log"

CONDITION_FIELDS = [
    "condition_id",
    "role",
    "wave",
    "setting",
    "arm",
    "run",
    "lineage",
    "cityjson_path",
    "cityjson_sha256",
    "payload_group_size",
    "payload_canonical",
    "scope",
    "n_population",
    "n_rows",
    "coverage_fraction",
    "complete_population",
    "measurable_count",
    "val3dity_valid_count",
    "val3dity_valid_rate_population",
    "lod2_count",
    "lod2_rate_population",
    "lod1_fallback_count",
    "median_face_count_ratio",
    "median_roof_rms_m",
    "p90_roof_rms_m",
    "condition_selection_scope",
    "learning_runs_started",
]

ORACLE_FIELDS = [
    "building_id",
    "population_role",
    "gs_total_count",
    "gs_valid_count",
    "gs_lod2_count",
    "oracle_model_id",
    "oracle_wave",
    "oracle_arm",
    "oracle_run",
    "oracle_roof_rms_m",
    "oracle_selection_scope",
    "learning_runs_started",
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def rel(path: Path) -> str:
    return str(path.resolve().relative_to(REPO.resolve()))


def sha256_file(path: Path, block_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def atomic_csv(path: Path, rows: Sequence[dict[str, Any]], fields: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def truth(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def finite_values(rows: Iterable[dict[str, str]], field: str) -> list[float]:
    values = [number(row.get(field)) for row in rows]
    return [value for value in values if value is not None]


def preferred_payload_model(rows: Sequence[dict[str, str]]) -> str:
    """Prefer an original path over a repaired copy, then use lexical order."""
    return min(
        {row["model_id"] for row in rows},
        key=lambda model_id: (
            all(
                row.get("lineage") != "original_assembled"
                for row in rows
                if row["model_id"] == model_id
            ),
            model_id,
        ),
    )


def aggregate() -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    scores = read_csv(SCORES)
    pairs = read_csv(PAIRS)
    if not scores or len(pairs) != 18:
        raise RuntimeError(f"A source cardinality drift scores={len(scores)} pairs={len(pairs)}")
    if any(row.get("learning_runs_started") != "0" for row in scores + pairs):
        raise RuntimeError("learning_runs_started drift in A source rows")

    populations = {
        "all_c001": {row["building_id"] for row in pairs},
        "dense_success": {
            row["building_id"] for row in pairs if row["population_role"] == "dense_success"
        },
    }
    if len(populations["all_c001"]) != 18 or len(populations["dense_success"]) != 10:
        raise RuntimeError(f"population drift: { {k: len(v) for k, v in populations.items()} }")

    model_rows: dict[str, list[dict[str, str]]] = defaultdict(list)
    payload_rows: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in scores:
        if row["role"] not in {"gs", "canonical_dense", "dense_sensitivity", "als_upper"}:
            continue
        model_rows[row["model_id"]].append(row)
        if row.get("cityjson_sha256"):
            payload_rows[row["cityjson_sha256"]].append(row)
    payload_canonical = {
        digest: preferred_payload_model(rows) for digest, rows in payload_rows.items()
    }
    payload_group_size = {
        digest: len({row["model_id"] for row in rows}) for digest, rows in payload_rows.items()
    }

    output: list[dict[str, Any]] = []
    for model_id in sorted(model_rows):
        rows = model_rows[model_id]
        first = rows[0]
        digest = first.get("cityjson_sha256", "")
        for scope, population in populations.items():
            subset = [row for row in rows if row["building_id"] in population]
            measurable = [
                row for row in subset if number(row.get("roof_rms_m")) is not None
            ]
            ratios = finite_values(subset, "face_count_ratio")
            rms = finite_values(subset, "roof_rms_m")
            n_population = len(population)
            n_rows = len(subset)
            output.append(
                {
                    "condition_id": model_id,
                    "role": first["role"],
                    "wave": first["wave"],
                    "setting": first["setting"],
                    "arm": first["arm"],
                    "run": first["run"],
                    "lineage": first["lineage"],
                    "cityjson_path": first["cityjson_path"],
                    "cityjson_sha256": digest,
                    "payload_group_size": payload_group_size.get(digest, 1),
                    "payload_canonical": model_id == payload_canonical.get(digest, model_id),
                    "scope": scope,
                    "n_population": n_population,
                    "n_rows": n_rows,
                    "coverage_fraction": n_rows / n_population,
                    "complete_population": n_rows == n_population,
                    "measurable_count": len(measurable),
                    "val3dity_valid_count": sum(
                        truth(row.get("val3dity_valid")) for row in subset
                    ),
                    "val3dity_valid_rate_population": (
                        sum(truth(row.get("val3dity_valid")) for row in subset)
                        / n_population
                    ),
                    "lod2_count": sum(truth(row.get("has_lod22")) for row in subset),
                    "lod2_rate_population": (
                        sum(truth(row.get("has_lod22")) for row in subset) / n_population
                    ),
                    "lod1_fallback_count": sum(
                        truth(row.get("lod1_fallback")) for row in subset
                    ),
                    "median_face_count_ratio": (
                        float(np.median(ratios)) if ratios else None
                    ),
                    "median_roof_rms_m": float(np.median(rms)) if rms else None,
                    "p90_roof_rms_m": float(np.quantile(rms, 0.9)) if rms else None,
                    "condition_selection_scope": (
                        "one_fixed_model_condition_no_per_building_switching"
                    ),
                    "learning_runs_started": 0,
                }
            )

    oracle = [
        {
            "building_id": row["building_id"],
            "population_role": row["population_role"],
            "gs_total_count": row["gs_total_count"],
            "gs_valid_count": row["gs_valid_count"],
            "gs_lod2_count": row["gs_lod2_count"],
            "oracle_model_id": row["gs_best_model_id"],
            "oracle_wave": row["gs_best_wave"],
            "oracle_arm": row["gs_best_arm"],
            "oracle_run": row["gs_best_run"],
            "oracle_roof_rms_m": row["gs_best_roof_rms_m"],
            "oracle_selection_scope": (
                "per_building_oracle_upper_bound_not_fixed_condition"
            ),
            "learning_runs_started": 0,
        }
        for row in pairs
    ]
    diversity = {
        "model_ids": len({row["oracle_model_id"] for row in oracle}),
        "waves": len({row["oracle_wave"] for row in oracle}),
        "wave_arm": len({(row["oracle_wave"], row["oracle_arm"]) for row in oracle}),
        "wave_arm_run": len(
            {
                (row["oracle_wave"], row["oracle_arm"], row["oracle_run"])
                for row in oracle
            }
        ),
    }
    return output, oracle, diversity


def make_figure(rows: Sequence[dict[str, Any]]) -> None:
    colors = {
        "sparse": "#4C78A8",
        "dense": "#F58518",
        "acmp": "#54A24B",
        "arm1": "#B279A2",
        "arm2": "#E45756",
        "arm3": "#72B7B2",
        "a1": "#9D755D",
        "a2": "#BAB0AC",
    }
    figure, axes = plt.subplots(1, 2, figsize=(13.5, 5.8), dpi=180)
    for axis, scope in zip(axes, ("all_c001", "dense_success")):
        subset = [
            row
            for row in rows
            if row["scope"] == scope
            and row["role"] == "gs"
            and row["payload_canonical"]
            and row["complete_population"]
            and row["median_roof_rms_m"] is not None
        ]
        for arm in sorted({row["arm"] for row in subset}):
            arm_rows = [row for row in subset if row["arm"] == arm]
            axis.scatter(
                [row["lod2_count"] for row in arm_rows],
                [row["median_roof_rms_m"] for row in arm_rows],
                s=28,
                alpha=0.68,
                color=colors.get(arm, "#777777"),
                label=arm,
            )
        baseline = next(
            (
                row
                for row in rows
                if row["scope"] == scope and row["role"] == "canonical_dense"
            ),
            None,
        )
        if baseline and baseline["median_roof_rms_m"] is not None:
            axis.scatter(
                [baseline["lod2_count"]],
                [baseline["median_roof_rms_m"]],
                s=150,
                marker="*",
                color="black",
                label="dense w2_1",
                zorder=5,
            )
        axis.set_xlabel(f"LoD2 count / {len(subset) and subset[0]['n_population'] or 0}")
        axis.set_ylabel("median roof RMS [m]")
        axis.set_title(
            f"{scope}: one point = one fixed condition\n"
            f"complete canonical payloads n={len(subset)}"
        )
        axis.grid(alpha=0.2)
        axis.legend(fontsize=7, ncol=2)
    figure.suptitle(
        "C001 fixed-condition GS inventory (no per-building condition switching)",
        fontsize=12,
    )
    figure.tight_layout(rect=[0, 0, 1, 0.96])
    FIGURE.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(FIGURE)
    plt.close(figure)


def main() -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    rows, oracle, diversity = aggregate()
    atomic_csv(CONDITIONS, rows, CONDITION_FIELDS)
    atomic_csv(ORACLE_AUDIT, oracle, ORACLE_FIELDS)
    make_figure(rows)

    counts = Counter(
        (
            row["scope"],
            row["role"],
            bool(row["payload_canonical"]),
            bool(row["complete_population"]),
        )
        for row in rows
    )
    log_lines = [
        f"{now()} start learning_runs_started=0",
        f"{now()} conditions rows={len(rows)} unique={len({row['condition_id'] for row in rows})}",
        f"{now()} oracle diversity={json.dumps(diversity, sort_keys=True)}",
        f"{now()} finish learning_runs_started=0",
    ]
    atomic_text(LOG, "\n".join(log_lines) + "\n")
    outputs = [CONDITIONS, ORACLE_AUDIT, FIGURE, LOG]
    sources = [SCORES, PAIRS, SOURCE_MANIFEST, Path(__file__)]
    payload = {
        "schema": "jointbuildgs.qs_rescore.fixed_conditions.v1",
        "created_utc": now(),
        "git_head_at_measurement": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO, text=True
        ).strip(),
        "branch": subprocess.check_output(
            ["git", "branch", "--show-current"], cwd=REPO, text=True
        ).strip(),
        "source_score_rows": len(read_csv(SCORES)),
        "fixed_condition_rows": len(rows),
        "unique_conditions": len({row["condition_id"] for row in rows}),
        "unique_gs_conditions": len(
            {row["condition_id"] for row in rows if row["role"] == "gs"}
        ),
        "unique_gs_payloads": len(
            {
                row["cityjson_sha256"]
                for row in rows
                if row["role"] == "gs" and row["cityjson_sha256"]
            }
        ),
        "complete_canonical_gs_conditions": {
            scope: counts[(scope, "gs", True, True)]
            for scope in ("all_c001", "dense_success")
        },
        "oracle_selection_scope": (
            "per_building_oracle_upper_bound_not_fixed_condition"
        ),
        "oracle_diversity": diversity,
        "fixed_condition_selection_scope": (
            "one_fixed_model_condition_no_per_building_switching"
        ),
        "learning_runs_started": 0,
        "new_inference_runs": 0,
        "gt_role": "no reference geometry opened; existing A score rows only",
        "interpretation_or_verdict": None,
        "source_sha256": {rel(path): sha256_file(path) for path in sources},
        "output_sha256": {rel(path): sha256_file(path) for path in outputs},
    }
    atomic_text(MANIFEST, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "fixed_condition_rows": len(rows),
                "oracle_rows": len(oracle),
                "oracle_diversity": diversity,
                "learning_runs_started": 0,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
