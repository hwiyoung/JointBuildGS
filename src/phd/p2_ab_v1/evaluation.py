"""Evaluation-only geometry diagnostics on a frozen common domain.

These point-to-point diagnostics do not certify current usability, source
authority, temporal change, roof semantics, or a continuous surface. Reference
points are never supplied to the decision or reconstruction optimizers.
"""
from __future__ import annotations

import numpy as np
from scipy.spatial import cKDTree


def _points(value):
    result = np.asarray(value, dtype=np.float64)
    if result.ndim != 2 or result.shape[1] != 3:
        raise ValueError("points must have shape [N, 3]")
    if not np.isfinite(result).all():
        raise ValueError("points must be finite; record exclusions before evaluation")
    return result


def distance_summary(values):
    values = np.asarray(values, dtype=float)
    finite = values[np.isfinite(values)]
    if not len(finite):
        return {"count": 0, "mean_m": None, "median_m": None,
                "p90_m": None, "rmse_m": None, "max_m": None}
    return {"count": int(len(finite)), "mean_m": float(finite.mean()),
            "median_m": float(np.median(finite)),
            "p90_m": float(np.quantile(finite, .9)),
            "rmse_m": float(np.sqrt(np.mean(finite ** 2))),
            "max_m": float(finite.max())}


def geometry_metrics(predicted, reference, tolerances=(.25, .5, 1.0), xy_radius=.5,
                     forward_reference=None):
    """Return both directions, retaining missing prediction in reference recall.

    Forward precision is source/renderer-sampled; reverse recall has the fixed
    native UAS sampling denominator. Neither is physical surface area. XY nearest
    vertical error is supplemental and can match another layer; report it with
    XY support, never silently substitute it for the Euclidean measurement.
    """
    p, r = _points(predicted), _points(reference)
    rf = r if forward_reference is None else _points(forward_reference)
    eps = np.asarray(tolerances, dtype=float)
    if eps.ndim != 1 or not len(eps) or not np.isfinite(eps).all() or (eps <= 0).any():
        raise ValueError("positive finite tolerance sweep required")
    if not np.isfinite(xy_radius) or xy_radius <= 0:
        raise ValueError("positive finite xy_radius required")
    forward = np.full(len(p), np.nan)
    reverse = np.full(len(r), np.inf)
    xy = np.full(len(p), np.inf)
    dz = np.full(len(p), np.nan)
    if len(p) and len(rf):
        forward = cKDTree(rf).query(p, workers=1)[0]
        xy, index = cKDTree(rf[:, :2]).query(p[:, :2], workers=1)
        supported = xy <= xy_radius
        dz[supported] = p[supported, 2] - rf[index[supported], 2]
    if len(p) and len(r):
        reverse = cKDTree(p).query(r, workers=1)[0]
    result = {
        "prediction_count": len(p), "reference_count": len(r),
        "forward_reference_count": len(rf),
        "reference_status": "AVAILABLE" if len(r) else "REFERENCE_ABSENT",
        "prediction_status": "PRESENT" if len(p) else "MISSING",
        "prediction_to_reference": distance_summary(forward),
        "reference_to_prediction": distance_summary(reverse),
        "xy_nearest_abs_dz": distance_summary(np.abs(dz)),
        "xy_nearest_signed_dz_median_m": float(np.nanmedian(dz)) if np.isfinite(dz).any() else None,
        "xy_correspondence_radius_m": float(xy_radius),
        "xy_supported_count": int(np.isfinite(dz).sum()),
        "xy_support_fraction": float(np.isfinite(dz).mean()) if len(p) and len(r) else None,
        "sampling_denominator": "native/reference or rendered/prediction points; not surface area",
        "reference_accuracy_m": None,
        "scientific_verdict": None,
        "tolerance_sweep": [],
    }
    for e in eps:
        nprecision = int(np.sum(forward <= e))
        nrecall = int(np.sum(reverse <= e))
        result["tolerance_sweep"].append({
            "tolerance_m": float(e), "predicted_inlier_count": nprecision,
            "prediction_precision": nprecision / len(p) if len(p) and len(r) else None,
            "reference_recovered_count": nrecall,
            "reference_recall": nrecall / len(r) if len(r) else None,
            "missing_reference_point_count": len(r) - nrecall if len(r) else None,
        })
    return result, {"prediction_to_reference_m": forward,
                    "reference_to_prediction_m": reverse,
                    "xy_nearest_distance_m": xy, "xy_nearest_signed_dz_m": dz}


def decision_accounting(rows):
    """Aggregate explicit candidate error labels without choosing one true source.

    Each row supplies action and candidate_ok mapping with boolean/null labels.
    Missing evaluation labels remain unknown. Refusal of a known-usable candidate
    is counted even when another candidate is unknown. No acceptance has null risk.
    """
    count = dict(total_units=0, accepted_units=0, evaluated_accepted_units=0,
                 false_accept_units=0, accepted_evaluation_unknown_units=0,
                 abstained_units=0, abstained_known_usable_units=0,
                 known_usable_units=0, both_original_candidates_bad_units=0,
                 abstained_both_original_bad_units=0)
    for row in rows:
        action, labels = row["action"], row["candidate_ok"]
        if action not in {"IMAGE", "PRIOR", "FUSION", "ABSTAIN"}:
            raise ValueError(f"unknown action: {action}")
        if any(x is not None and not isinstance(x, (bool, np.bool_)) for x in labels.values()):
            raise ValueError("candidate labels must be boolean or null")
        count["total_units"] += 1
        usable = any(x is True or isinstance(x, np.bool_) and bool(x) for x in labels.values())
        count["known_usable_units"] += int(usable)
        both_bad = all(labels.get(s) is not None and not bool(labels[s]) for s in ('IMAGE', 'PRIOR'))
        count["both_original_candidates_bad_units"] += int(both_bad)
        if action == "ABSTAIN":
            count["abstained_units"] += 1
            count["abstained_known_usable_units"] += int(usable)
            count["abstained_both_original_bad_units"] += int(both_bad)
        else:
            count["accepted_units"] += 1
            label = labels.get(action)
            if label is None:
                count["accepted_evaluation_unknown_units"] += 1
            else:
                count["evaluated_accepted_units"] += 1
                count["false_accept_units"] += int(not label)
    count["coverage"] = count["accepted_units"] / count["total_units"] if count["total_units"] else None
    count["false_accept_rate_evaluated"] = (count["false_accept_units"] / count["evaluated_accepted_units"]
                                               if count["evaluated_accepted_units"] else None)
    count["usable_abstention_rate"] = (count["abstained_known_usable_units"] / count["known_usable_units"]
                                         if count["known_usable_units"] else None)
    return count
