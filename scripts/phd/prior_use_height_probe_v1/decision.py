"""Compare candidate scores with a bounded, discrete height compatibility test.

This module only aggregates supplied measurements.  It reads no files, evaluates
no reference geometry, and grants no current-use action.  The compatible runs
below describe sampled heights, not continuously verified height intervals.
"""
from __future__ import annotations

from collections import Counter
from itertools import product
from typing import Any

import numpy as np


BASELINE_STATES = ("UNTESTABLE", "SCORE_PASS", "SCORE_FAIL")
DECISION_STATES = (
    "UNTESTABLE",
    "MODEL_MISMATCH",
    "UNRESOLVED_BOUNDARY",
    "GRID_CONDITIONAL_SUPPORT",
    "GRID_OPPOSITION",
    "GRID_UNRESOLVED",
)


def _axis(values: Any, name: str, *, positive: bool = False) -> list[float]:
    axis = np.asarray(values, dtype=np.float64)
    if axis.ndim != 1 or not len(axis) or not np.isfinite(axis).all():
        raise ValueError(f"{name} must be a nonempty finite one-dimensional axis")
    if len(np.unique(axis)) != len(axis):
        raise ValueError(f"{name} must not contain duplicates")
    if positive and np.any(axis <= 0):
        raise ValueError(f"{name} must be positive")
    return [float(value) for value in axis]


def _height_index(heights: np.ndarray, height: float, label: str) -> int:
    matches = np.flatnonzero(np.isclose(heights, height, rtol=0, atol=1e-9))
    if len(matches) != 1:
        raise ValueError(f"{label} must match exactly one measured height")
    return int(matches[0])


def _compatible_runs(heights: np.ndarray, mask: np.ndarray) -> list[list[float]]:
    """Return endpoints of contiguous *sampled-index* runs, without interpolation."""
    indices = np.flatnonzero(mask)
    if not len(indices):
        return []
    runs = np.split(indices, np.flatnonzero(np.diff(indices) > 1) + 1)
    return [[float(heights[run[0]]), float(heights[run[-1]])] for run in runs]


def _classify(
    heights: np.ndarray,
    scores: np.ndarray,
    candidate_height: float,
    candidate_score: float | None,
    threshold: float,
    tolerance: float,
    testable: bool,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "baseline": "UNTESTABLE",
        "decision": "UNTESTABLE",
        "reason": "INSUFFICIENT_PAIRS_FINITE_AT_EVERY_MEASURED_HEIGHT",
        "B": None,
        "U": None,
        "compatible_heights_m": [],
        "intervals_m": [],
        "compatible_min_m": None,
        "compatible_max_m": None,
        "compatible_count": 0,
        "compatible_on_boundary": False,
        "full_current_use_action": None,
    }
    if not testable:
        return result
    if candidate_score is None or not np.isfinite(scores).all():
        raise ValueError("a testable curve must be finite at every measured height")
    result["baseline"] = "SCORE_PASS" if candidate_score >= threshold else "SCORE_FAIL"
    compatible = scores >= threshold
    values = heights[compatible]
    result["compatible_heights_m"] = [float(value) for value in values]
    result["intervals_m"] = _compatible_runs(heights, compatible)
    result["compatible_count"] = int(len(values))
    if not len(values):
        result.update(decision="MODEL_MISMATCH", reason="NO_TESTED_HEIGHT_MEETS_SCORE_THRESHOLD")
        return result
    errors = np.abs(values - candidate_height) / tolerance
    lower, upper = float(np.min(errors)), float(np.max(errors))
    boundary = bool(compatible[0] or compatible[-1])
    result.update(
        B=lower,
        U=upper,
        compatible_min_m=float(values[0]),
        compatible_max_m=float(values[-1]),
        compatible_on_boundary=boundary,
    )
    # A boundary explanation overrides support/opposition even if its B/U is
    # otherwise decisive.  The values remain available as bounded diagnostics.
    if boundary:
        result.update(decision="UNRESOLVED_BOUNDARY", reason="COMPATIBLE_HEIGHT_ON_TESTED_BOUNDARY")
    elif upper <= 1.0:
        result.update(decision="GRID_CONDITIONAL_SUPPORT", reason="ALL_COMPATIBLE_SAMPLED_HEIGHTS_WITHIN_TOLERANCE")
    elif lower > 1.0:
        result.update(decision="GRID_OPPOSITION", reason="ALL_COMPATIBLE_SAMPLED_HEIGHTS_OUTSIDE_TOLERANCE")
    else:
        result.update(decision="GRID_UNRESOLVED", reason="COMPATIBLE_SAMPLED_HEIGHTS_INSIDE_AND_OUTSIDE_TOLERANCE")
    return result


def aggregate_height_sweep(result: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """Return ``summary``, ``rows``, ``curves``, and ``pair_masks``.

    Required measurements: ``rho[H,P,G]``, increasing ``heights[H]``, and
    ``pair_angles[P]``.  Optional ``count[P,G]`` supplies native-point support
    counts.  Each angle band uses only pairs finite across ALL H, including
    heights outside a smaller reported extent.  The same median curve supplies
    every threshold, tolerance, and extent in that band.

    Summary and rows are JSON-safe (missing numbers are None).  Curves are float
    arrays [H,G] and pair_masks are bool arrays [P,G], keyed by ``format(band,'g')``.
    A curve with insufficient common pairs is NaN and yields UNTESTABLE rows.
    Rows follow config order: threshold, tolerance, angle maximum, extent, group.
    Extents are symmetric around zero in the original height-offset coordinates;
    candidate_height_offset_m selects the fixed output candidate on that grid.
    """
    rho = np.asarray(result["rho"], dtype=np.float64)
    heights = np.asarray(result["heights"], dtype=np.float64)
    angles = np.asarray(result["pair_angles"], dtype=np.float64)
    if rho.ndim != 3:
        raise ValueError("rho must have shape [H,P,G]")
    nh, npairs, ngroups = rho.shape
    if heights.shape != (nh,) or nh < 3 or not np.isfinite(heights).all():
        raise ValueError("heights must contain at least three finite measured heights")
    if np.any(np.diff(heights) <= 0):
        raise ValueError("heights must be strictly increasing")
    if ngroups < 1:
        raise ValueError("rho must contain at least one group")
    if angles.shape != (npairs,) or not np.isfinite(angles).all():
        raise ValueError("pair_angles must be finite with shape [P]")
    if np.any((angles < 0) | (angles > 180)):
        raise ValueError("pair angles must lie in [0,180] degrees")
    finite = np.isfinite(rho)
    if np.isinf(rho).any() or np.any(np.abs(rho[finite]) > 1.0 + 1e-6):
        raise ValueError("rho must contain correlations in [-1,1] or NaN")
    point_counts = None
    if "count" in result:
        point_counts = np.asarray(result["count"])
        if (point_counts.shape != (npairs, ngroups)
                or not np.isfinite(point_counts).all()
                or np.any(point_counts < 0)
                or np.any(point_counts != np.floor(point_counts))):
            raise ValueError("count must contain nonnegative integers with shape [P,G]")

    measurement, comparison = config["measurement"], config["comparison"]
    minimum = float(measurement["min_common_pairs"])
    if not np.isfinite(minimum) or minimum < 1 or not minimum.is_integer():
        raise ValueError("min_common_pairs must be a positive integer")
    min_pairs = int(minimum)
    min_angle = float(measurement.get("min_pair_angle_deg", 0.0))
    if not np.isfinite(min_angle) or not 0 <= min_angle <= 180:
        raise ValueError("min_pair_angle_deg must lie in [0,180]")
    thresholds = _axis(comparison["score_thresholds"], "score_thresholds")
    tolerances = _axis(comparison["height_tolerances_m"], "height_tolerances_m", positive=True)
    bands = _axis(comparison["pair_angle_maxima_deg"], "pair_angle_maxima_deg")
    extents = _axis(comparison["tested_extents_m"], "tested_extents_m", positive=True)
    if any(not -1 <= threshold <= 1 for threshold in thresholds):
        raise ValueError("score_thresholds must lie in [-1,1]")
    if any(not min_angle <= band <= 180 for band in bands):
        raise ValueError("angle bands must be between the measurement minimum and 180")
    candidate_height = float(comparison.get("candidate_height_offset_m", 0.0))
    if not np.isfinite(candidate_height):
        raise ValueError("candidate_height_offset_m must be finite")
    candidate_index = _height_index(heights, candidate_height, "candidate height")
    extent_indices: dict[float, np.ndarray] = {}
    for extent in extents:
        first = _height_index(heights, -extent, "negative extent boundary")
        last = _height_index(heights, extent, "positive extent boundary")
        if not first <= candidate_index <= last:
            raise ValueError("candidate height must be inside every reported extent")
        extent_indices[extent] = np.arange(first, last + 1)

    curves: dict[str, np.ndarray] = {}
    pair_masks: dict[str, np.ndarray] = {}
    band_diagnostics: dict[str, list[dict[str, Any]]] = {}
    band_summaries: list[dict[str, Any]] = []
    for band in bands:
        key = format(band, "g")
        eligible = (angles >= min_angle) & (angles <= band)
        common = np.all(finite, axis=0) & eligible[:, None]
        any_finite = np.any(finite, axis=0) & eligible[:, None]
        partial = any_finite & ~common
        count_common = np.sum(common, axis=0)
        finite_per_height = np.sum(finite & eligible[None, :, None], axis=1)
        curve = np.full((nh, ngroups), np.nan, dtype=np.float64)
        diagnostics: list[dict[str, Any]] = []
        for group in range(ngroups):
            mask = common[:, group]
            if count_common[group] >= min_pairs:
                curve[:, group] = np.median(rho[:, mask, group], axis=1)
            n_angle = int(np.sum(eligible))
            n_any = int(np.sum(any_finite[:, group]))
            n_common = int(count_common[group])
            sample_counts = (None if point_counts is None else
                             [int(value) for value in point_counts[mask, group]])
            diagnostics.append({
                "common_pairs": n_common,
                "angle_pairs": n_angle,
                "any_finite_pairs": n_any,
                "partial_pairs": int(np.sum(partial[:, group])),
                "no_finite_pairs": n_angle - n_any,
                "candidate_finite_pairs": int(finite_per_height[candidate_index, group]),
                "finite_pairs_by_height": [int(value) for value in finite_per_height[:, group]],
                "common_pair_indices": [int(value) for value in np.flatnonzero(mask)],
                "common_sample_counts": sample_counts,
                "common_sample_min": min(sample_counts) if sample_counts else None,
                "common_sample_max": max(sample_counts) if sample_counts else None,
                "common_sample_pair_sum": sum(sample_counts) if sample_counts else None,
            })
        curves[key], pair_masks[key] = curve, common
        band_diagnostics[key] = diagnostics
        band_summaries.append({
            "angle_max_deg": band,
            "groups": ngroups,
            "angle_pairs": int(np.sum(eligible)),
            "testable_groups": int(np.sum(count_common >= min_pairs)),
            "untestable_groups": int(np.sum(count_common < min_pairs)),
            "common_pair_group_count": int(np.sum(common)),
            "partial_pair_group_count": int(np.sum(partial)),
            "no_finite_pair_group_count": int(np.sum(eligible) * ngroups - np.sum(any_finite)),
        })

    rows: list[dict[str, Any]] = []
    settings: list[dict[str, Any]] = []
    for setting_index, (threshold, tolerance, band, extent) in enumerate(
        product(thresholds, tolerances, bands, extents)
    ):
        key = format(band, "g")
        indices = extent_indices[extent]
        tested_heights = heights[indices]
        baseline_counts: Counter[str] = Counter()
        decision_counts: Counter[str] = Counter()
        transitions: Counter[str] = Counter()
        for group in range(ngroups):
            diagnostic = band_diagnostics[key][group]
            testable = diagnostic["common_pairs"] >= min_pairs
            candidate_score = float(curves[key][candidate_index, group]) if testable else None
            scores = curves[key][indices, group]
            decision = _classify(tested_heights, scores, candidate_height, candidate_score,
                                 threshold, tolerance, testable)
            row = {
                "setting_index": setting_index,
                "group_index": group,
                "angle_max_deg": band,
                "threshold": threshold,
                "tolerance_m": tolerance,
                "extent_m": extent,
                "candidate_height_offset_m": candidate_height,
                "candidate_score": candidate_score,
                "tested_height_count": int(len(indices)),
                "tested_min_m": float(tested_heights[0]),
                "tested_max_m": float(tested_heights[-1]),
                "score_min": float(np.min(scores)) if testable else None,
                "score_max": float(np.max(scores)) if testable else None,
                "score_range": float(np.max(scores) - np.min(scores)) if testable else None,
                **diagnostic,
                **decision,
            }
            rows.append(row)
            baseline_counts[row["baseline"]] += 1
            decision_counts[row["decision"]] += 1
            transitions[f'{row["baseline"]}->{row["decision"]}'] += 1
        settings.append({
            "setting_index": setting_index,
            "angle_max_deg": band,
            "threshold": threshold,
            "tolerance_m": tolerance,
            "extent_m": extent,
            "groups": ngroups,
            "baseline_counts": {state: baseline_counts[state] for state in BASELINE_STATES},
            "decision_counts": {state: decision_counts[state] for state in DECISION_STATES},
            "transition_counts": dict(sorted(transitions.items())),
        })

    summary = {
        "schema": "jointbuildgs.phd.prior_use_height_probe.decision.v1",
        "task_id": config.get("task_id"),
        "scientific_verdict": None,
        "full_current_use_action": None,
        "baseline": comparison.get("baseline", "CANDIDATE_SCORE_GATE"),
        "proposal_component": comparison.get("proposal_component", "DISCRETE_ALT_RANGE_GATE"),
        "groups": ngroups,
        "measured_pairs": npairs,
        "measured_heights_m": [float(value) for value in heights],
        "candidate_height_offset_m": candidate_height,
        "min_common_pairs": min_pairs,
        "setting_count": len(settings),
        "row_count": len(rows),
        "calibration_status": comparison.get("calibration_status", "UNVALIDATED"),
        "scope": "DISCRETE_VERTICAL_HEIGHTS_WITH_FIXED_CAMERA_AND_REGISTRATION",
        "accuracy_evaluated": False,
        "pair_support_rule": "finite at ALL measured heights, before restricting reported extent",
        "interval_semantics": "contiguous sampled-index runs; no interpolation or continuous coverage claim",
        "denominator_note": "pair/group counts and point-pair sums are not independent observations or unique area",
        "angle_bands": band_summaries,
        "settings": settings,
    }
    return {"summary": summary, "rows": rows, "curves": curves, "pair_masks": pair_masks}


def validate_decision_logic() -> dict[str, Any]:
    """Check deterministic analytical edge cases; do not measure scene accuracy.

    Raises AssertionError on a mismatch and returns a JSON-safe check receipt.
    The tiny arrays exercise inequalities, missingness, common denominators, and
    boundary precedence.  They are not a synthetic reconstruction benchmark.
    """
    import json

    heights = np.arange(-1.0, 1.0001, 0.25)
    base_config = {
        "measurement": {"min_common_pairs": 3, "min_pair_angle_deg": 3.0},
        "comparison": {
            "score_thresholds": [0.5],
            "height_tolerances_m": [0.5],
            "pair_angle_maxima_deg": [20.0],
            "tested_extents_m": [1.0],
            "candidate_height_offset_m": 0.0,
        },
    }
    cases: list[dict[str, Any]] = []

    def check(name: str, values: list[float], expected_baseline: str,
              expected_decision: str, *, modify: Any = None,
              assertion: Any = None) -> dict[str, Any]:
        rho = np.repeat(np.asarray(values, dtype=np.float64)[:, None, None], 3, axis=1)
        measurement = {"rho": rho, "heights": heights, "pair_angles": np.full(3, 10.0),
                       "count": np.full((3, 1), 30, dtype=np.int64)}
        if modify is not None:
            modify(measurement)
        aggregated = aggregate_height_sweep(measurement, base_config)
        row = aggregated["rows"][0]
        assert row["baseline"] == expected_baseline, (name, row)
        assert row["decision"] == expected_decision, (name, row)
        assert row["full_current_use_action"] is None
        if assertion is not None:
            assertion(aggregated)
        json.dumps({"summary": aggregated["summary"], "rows": aggregated["rows"]}, allow_nan=False)
        cases.append({"name": name, "passed": True, "baseline": row["baseline"],
                      "decision": row["decision"]})
        return aggregated

    check("flat_high_curve_reaches_boundary", [0.8] * 9, "SCORE_PASS", "UNRESOLVED_BOUNDARY")
    check("low_candidate_nearby_compatible_support", [0, 0, 0, 0.8, 0.1, 0.8, 0, 0, 0],
          "SCORE_FAIL", "GRID_CONDITIONAL_SUPPORT")
    check("only_distant_interior_height", [0, 0, 0, 0, 0, 0, 0, 0.8, 0],
          "SCORE_FAIL", "GRID_OPPOSITION")
    check("near_and_far_compatible_heights", [0, 0, 0, 0, 0.8, 0, 0, 0.8, 0],
          "SCORE_PASS", "GRID_UNRESOLVED")
    check("all_scores_below_threshold", [0.1] * 9, "SCORE_FAIL", "MODEL_MISMATCH")
    check("threshold_and_tolerance_inclusive", [0, 0, 0.5, 0, 0.5, 0, 0.5, 0, 0],
          "SCORE_PASS", "GRID_CONDITIONAL_SUPPORT")
    check("boundary_precedes_opposition", [0, 0, 0, 0, 0, 0, 0, 0, 0.8],
          "SCORE_FAIL", "UNRESOLVED_BOUNDARY")
    check("all_measurements_missing", [float("nan")] * 9, "UNTESTABLE", "UNTESTABLE")

    def drop_one_height(measurement: dict[str, Any]) -> None:
        measurement["rho"][0, 0, 0] = np.nan

    partial = check("partial_pair_not_heightwise_replaced", [0.8] * 9,
                    "UNTESTABLE", "UNTESTABLE", modify=drop_one_height)
    assert partial["rows"][0]["partial_pairs"] == 1
    assert partial["rows"][0]["common_pairs"] == 2
    assert partial["rows"][0]["candidate_finite_pairs"] == 3

    runs = check("disconnected_sample_runs_preserved", [0, 0, 0.8, 0.8, 0, 0.8, 0.8, 0, 0],
                 "SCORE_FAIL", "GRID_CONDITIONAL_SUPPORT")
    assert runs["rows"][0]["intervals_m"] == [[-0.5, -0.25], [0.25, 0.5]]

    empty_pairs = {"rho": np.empty((9, 0, 1)), "heights": heights, "pair_angles": np.empty(0)}
    empty_output = aggregate_height_sweep(empty_pairs, base_config)
    assert empty_output["rows"][0]["decision"] == "UNTESTABLE"
    cases.append({"name": "zero_pairs_retained_as_untestable", "passed": True})

    # A missing observation outside the smaller extent still invalidates that
    # pair, since every setting must consume the same full-sweep denominator.
    wide_heights = np.arange(-2.0, 2.0001, 0.25)
    wide_rho = np.full((len(wide_heights), 3, 1), 0.8)
    wide_rho[0, 0, 0] = np.nan
    wide = aggregate_height_sweep(
        {"rho": wide_rho, "heights": wide_heights, "pair_angles": np.full(3, 10.0)},
        base_config,
    )
    assert wide["rows"][0]["decision"] == "UNTESTABLE"
    assert wide["rows"][0]["common_pairs"] == 2
    cases.append({"name": "full_sweep_support_precedes_extent_restriction", "passed": True})

    # Test that all sensitivity combinations are returned, without selecting a
    # winning setting or conflating angular eligibility with finite support.
    complete = {
        "measurement": base_config["measurement"],
        "comparison": {**base_config["comparison"],
                       "score_thresholds": [0.3, 0.5, 0.7, 0.9],
                       "height_tolerances_m": [0.25, 0.5, 1.0],
                       "pair_angle_maxima_deg": [20.0, 60.0],
                       "tested_extents_m": [1.0, 2.0]},
    }
    all_settings = aggregate_height_sweep(
        {"rho": np.full((len(wide_heights), 3, 1), 0.8), "heights": wide_heights,
         "pair_angles": np.asarray([10.0, 20.0, 60.0])}, complete,
    )
    assert all_settings["summary"]["setting_count"] == 48
    assert len(all_settings["rows"]) == 48
    assert set(all_settings["curves"]) == {"20", "60"}
    assert not np.any(all_settings["pair_masks"]["20"][2])
    assert all_settings["rows"][0]["decision"] == "UNTESTABLE"
    assert all_settings["rows"][2]["decision"] == "UNRESOLVED_BOUNDARY"
    json.dumps({"summary": all_settings["summary"], "rows": all_settings["rows"]}, allow_nan=False)
    cases.append({"name": "all_48_settings_and_inclusive_angle_bands", "passed": True})
    return {"passed": True, "case_count": len(cases), "cases": cases,
            "scope": "ANALYTICAL_IMPLEMENTATION_CHECKS_NOT_AN_ACCURACY_BENCHMARK",
            "scientific_verdict": None, "full_current_use_action": None}
