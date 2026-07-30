#!/usr/bin/env python3
"""Recompute Wave-1 roof-distance metrics with the canonical GS datum shift.

This is a read-only audit of the published CityJSON products.  It neither
changes the canonical readout package nor reruns training, extraction, Roofer,
val3dity, or the binding audit.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np


REPO = Path(__file__).resolve().parents[4]
PUBLISHED_DIR = REPO / "phases/p2-gsjso/runs/20260722_pilot_1wave_readout"
SCORING_SCRIPT = REPO / "phases/p2-gsjso/scripts/pilot_1wave_scoring.py"
PUBLISHED_SCORES = PUBLISHED_DIR / "pilot_1wave_scores.csv"
CANONICAL_SHIFT_M = -45.7
RNG_SEED = 20260707


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise RuntimeError(f"refusing to write empty CSV: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(rows[0]),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def finite(values: list[float | None]) -> list[float]:
    return [float(value) for value in values if value is not None and math.isfinite(float(value))]


def median(values: list[float | None]) -> float | None:
    selected = finite(values)
    return statistics.median(selected) if selected else None


def evaluate_run(
    metric: Any,
    ids: tuple[str, ...],
    references: dict[str, list[Any]],
    parsed: dict[str, list[Any]],
    shift_m: float,
) -> dict[str, dict[str, Any]]:
    metric.RNG = np.random.default_rng(RNG_SEED)
    output: dict[str, dict[str, Any]] = {}
    for building_id in ids:
        prediction = list(parsed.get(building_id, []))
        shifted = metric.shift_surface_z(prediction, shift_m)
        output[building_id] = metric.compare_building(
            list(references[building_id]),
            shifted,
        )
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()

    scoring = load_module("pilot_1wave_scoring_datum_audit", SCORING_SCRIPT)
    lock = scoring.load_pilot_lock()
    metric = scoring.get_metric_module()
    if not math.isclose(
        float(metric.ELLIP_TO_REF_SHIFT_M),
        CANONICAL_SHIFT_M,
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        raise RuntimeError("canonical metric datum shift drift")
    references = scoring.load_locked_references(lock)
    rows = read_csv(PUBLISHED_SCORES)

    candidate_rows: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        if row["source_role"] in {"honest", "seg_upperbound"}:
            candidate_rows[row["source_id"]].append(row)
    if len(candidate_rows) != 10:
        raise RuntimeError(f"expected 10 candidate runs, got {len(candidate_rows)}")

    building_output: list[dict[str, Any]] = []
    run_output: list[dict[str, Any]] = []
    for source_id in sorted(candidate_rows):
        published = candidate_rows[source_id]
        if len(published) != 30:
            raise RuntimeError(f"{source_id}: expected 30 published rows")
        first = published[0]
        cityjson_paths = {row["cityjson_path"] for row in published}
        if len(cityjson_paths) != 1:
            raise RuntimeError(f"{source_id}: multiple CityJSON paths")
        cityjson_path = REPO / next(iter(cityjson_paths))
        parsed = metric.parse_cityjson_roofs(cityjson_path, set(lock.ids))
        zero = evaluate_run(metric, lock.ids, references, parsed, 0.0)
        shifted = evaluate_run(metric, lock.ids, references, parsed, CANONICAL_SHIFT_M)
        published_by_id = {row["building_id"]: row for row in published}

        for building_id in lock.ids:
            published_row = published_by_id[building_id]
            published_rms = (
                float(published_row["roof_rms_m"]) if published_row["roof_rms_m"] else None
            )
            published_haus = (
                float(published_row["roof_hausdorff_m"])
                if published_row["roof_hausdorff_m"]
                else None
            )
            building_output.append(
                {
                    "source_id": source_id,
                    "source_role": first["source_role"],
                    "condition_id": first["condition_id"],
                    "seed": int(first["seed"]),
                    "building_id": building_id,
                    "prediction_roof_surface_count": len(parsed.get(building_id, [])),
                    "published_score_time_z_shift_m": float(
                        published_row["score_time_z_shift_m"]
                    ),
                    "published_rms_m": published_rms,
                    "recomputed_zero_shift_rms_m": zero[building_id]["ref_rms_m"],
                    "canonical_shift_m": CANONICAL_SHIFT_M,
                    "datum_corrected_rms_m": shifted[building_id]["ref_rms_m"],
                    "published_hausdorff_m": published_haus,
                    "recomputed_zero_shift_hausdorff_m": zero[building_id][
                        "ref_hausdorff_m"
                    ],
                    "datum_corrected_hausdorff_m": shifted[building_id][
                        "ref_hausdorff_m"
                    ],
                }
            )

        published_rms_values = [
            float(row["roof_rms_m"]) if row["roof_rms_m"] else None for row in published
        ]
        zero_rms_values = [zero[building_id]["ref_rms_m"] for building_id in lock.ids]
        shifted_rms_values = [
            shifted[building_id]["ref_rms_m"] for building_id in lock.ids
        ]
        published_haus_values = [
            float(row["roof_hausdorff_m"]) if row["roof_hausdorff_m"] else None
            for row in published
        ]
        zero_haus_values = [
            zero[building_id]["ref_hausdorff_m"] for building_id in lock.ids
        ]
        shifted_haus_values = [
            shifted[building_id]["ref_hausdorff_m"] for building_id in lock.ids
        ]
        published_rms_finite = finite(published_rms_values)
        zero_rms_finite = finite(zero_rms_values)
        if len(published_rms_finite) != len(zero_rms_finite):
            raise RuntimeError(f"{source_id}: zero-shift measurable count drift")
        max_zero_delta = max(
            (
                abs(lhs - rhs)
                for lhs, rhs in zip(published_rms_finite, zero_rms_finite, strict=True)
            ),
            default=0.0,
        )
        run_output.append(
            {
                "source_id": source_id,
                "source_role": first["source_role"],
                "condition_id": first["condition_id"],
                "seed": int(first["seed"]),
                "cityjson_path": next(iter(cityjson_paths)),
                "prediction_buildings_with_roofs": sum(
                    bool(parsed.get(building_id)) for building_id in lock.ids
                ),
                "published_rms_n": len(published_rms_finite),
                "published_rms_median_m": median(published_rms_values),
                "recomputed_zero_shift_rms_median_m": median(zero_rms_values),
                "max_published_vs_recomputed_zero_shift_rms_delta_m": max_zero_delta,
                "canonical_shift_m": CANONICAL_SHIFT_M,
                "datum_corrected_rms_n": len(finite(shifted_rms_values)),
                "datum_corrected_rms_median_m": median(shifted_rms_values),
                "published_hausdorff_median_m": median(published_haus_values),
                "recomputed_zero_shift_hausdorff_median_m": median(zero_haus_values),
                "datum_corrected_hausdorff_median_m": median(shifted_haus_values),
                "datum_corrected_rms_lt_dense_bar": (
                    median(shifted_rms_values) < float(scoring.DENSE_BAR_MEDIAN_M)
                    if median(shifted_rms_values) is not None
                    else False
                ),
                "datum_corrected_rms_lt_2m": (
                    median(shifted_rms_values) < 2.0
                    if median(shifted_rms_values) is not None
                    else False
                ),
            }
        )

    write_csv(output_dir / "datum_shift_building_audit.csv", building_output)
    write_csv(output_dir / "datum_shift_run_audit.csv", run_output)


if __name__ == "__main__":
    main()
