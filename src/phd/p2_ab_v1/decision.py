"""Conditional height-component decision comparisons; no truth inputs.

The Bayesian comparator uses the Gaussian + uniform sensor of Vogiatzis and
Hernandez (2011), equations 1-2, with explicit bounded-development adaptations.
Neither its probabilities nor a finite photometric compatibility set certify
absolute current geometry. Unknown calibration contracts force strict abstention.
"""
from __future__ import annotations

import numpy as np

ACTIONS = ("IMAGE", "PRIOR", "FUSION", "ABSTAIN")
UNKNOWNS = [
    "camera_and_registration_absolute_error_not_calibrated",
    "current_occlusion_and_correspondence_not_certified",
    "finite_vertical_search_not_continuous_full_scene_bound",
    "point_support_does_not_certify_continuous_surface",
    "existing_mvs_and_development_views_share_image_lineage",
]
CERTIFICATION_CONTRACTS = (
    "absolute_camera_registration_bounds_calibrated",
    "current_visibility_and_correspondence_certified",
    "continuous_scene_search_inclusion_verified",
    "continuous_surface_support_certified",
    "shared_image_lineage_dependence_accounted",
)


def common_curve(rho, pair_ids, minimum_pairs=3, disjoint=False, limit=None):
    """Keep the same finite pairs at every height; never impute missing as zero."""
    rho = np.asarray(rho, dtype=float)
    pair_ids = np.asarray(pair_ids, dtype=np.int64)
    if rho.ndim != 2 or pair_ids.shape != (rho.shape[1], 2):
        raise ValueError("Expected rho[height,pair] and pair_ids[pair,2]")
    eligible = np.flatnonzero(np.isfinite(rho).all(axis=0))
    selected, used = [], set()
    for i in eligible:
        a, b = map(int, pair_ids[i])
        if disjoint and (a in used or b in used):
            continue
        selected.append(int(i))
        used.update((a, b))
        if limit is not None and len(selected) >= limit:
            break
    curve = (np.median(rho[:, selected], axis=1)
             if len(selected) >= minimum_pairs else np.full(rho.shape[0], np.nan))
    return curve, np.asarray(selected, dtype=np.int64)


def finite_range(heights, scores, threshold, tolerance, candidate_offset=0.0,
                 shared_shift_radius=0.0):
    heights, scores = np.asarray(heights, float), np.asarray(scores, float)
    if tolerance <= 0 or shared_shift_radius < 0:
        raise ValueError("positive tolerance and nonnegative shared shift required")
    result = {"state": "UNOBSERVED", "lower_m": None, "upper_m": None,
              "conditional_budget_m": None, "compatible_offsets_m": []}
    if not np.isfinite(scores).all():
        return result
    compatible = scores >= threshold
    if not compatible.any():
        result["state"] = "MODEL_MISMATCH"
        return result
    values = heights[compatible]
    distances = abs(values - candidate_offset)
    lower = max(0.0, float(distances.min()) - shared_shift_radius)
    upper = float(distances.max()) + shared_shift_radius
    result.update(lower_m=lower, upper_m=upper, compatible_offsets_m=values.tolist())
    if compatible[0] or compatible[-1]:
        result["state"] = "SEARCH_BOUNDARY_UNRESOLVED"
    elif upper <= tolerance:
        result.update(state="SUPPORTED_FINITE_HEIGHT_CONDITIONAL",
                      conditional_budget_m=max(0.0, tolerance - upper))
    elif lower > tolerance:
        result["state"] = "OPPOSED_FINITE_HEIGHT_CONDITIONAL"
    else:
        result["state"] = "AMBIGUOUS"
    return result


def gaussian_uniform_posterior(heights, pair_scores, sigma_m, pi_bins=101):
    """Full discrete h x inlier-rate posterior, Gaussian-uniform Eq.1-2.

    Per-pair global NCC maximum replaces the paper's stream of local maxima;
    disjoint camera pairs are selected by the caller. A uniform bounded prior
    and midpoint quadrature for pi avoid privileging endpoint probabilities.
    sigma_m is a conditional one-pixel triangulation+source-roughness model.
    """
    h = np.asarray(heights, float)
    scores = np.asarray(pair_scores, float)
    sigma = np.asarray(sigma_m, float)
    if h.ndim != 1 or len(h) < 3 or not np.all(np.diff(h) > 0):
        raise ValueError("heights must be a strictly ordered nontrivial grid")
    if scores.shape != (len(h), len(sigma)):
        raise ValueError("score and sigma shapes differ")
    valid = np.isfinite(scores).all(0) & np.isfinite(sigma) & (sigma > 0)
    scores, sigma = scores[:, valid], sigma[valid]
    if scores.shape[1] == 0:
        return None
    # Exactly flat or tied maxima contain no unique depth measurement.
    maximum = scores.max(axis=0)
    unique = ((scores == maximum[None, :]).sum(axis=0) == 1)
    scores, sigma = scores[:, unique], sigma[unique]
    if scores.shape[1] == 0:
        return None
    peaks = h[np.argmax(scores, axis=0)]
    pi = (np.arange(pi_bins) + 0.5) / pi_bins
    logp = np.zeros((len(h), pi_bins), dtype=float)
    width = float(h[-1] - h[0])
    for x, sd in zip(peaks, sigma):
        normal = np.exp(-0.5 * ((x - h) / sd) ** 2) / (np.sqrt(2 * np.pi) * sd)
        likelihood = normal[:, None] * pi + (1 - pi) / width
        logp += np.log(likelihood)
    joint = np.exp(logp - logp.max())
    joint /= joint.sum()
    mass = joint.sum(axis=1)
    mean = float(mass @ h)
    return {"height_mass": mass, "mean_offset_m": mean,
            "sd_offset_m": float(np.sqrt(mass @ (h - mean) ** 2)),
            "mean_inlier_probability": float(joint.sum(axis=0) @ pi),
            "measurement_count": len(peaks), "peaks_m": peaks.tolist(),
            "sigma_m": sigma.tolist(), "boundary_mass": float(mass[0] + mass[-1])}


def posterior_candidate(posterior, heights, offset, tolerance):
    if posterior is None:
        return {"probability_within_tolerance": None, "expected_abs_error_m": None,
                "state": "UNOBSERVED"}
    distance = abs(np.asarray(heights) - offset)
    mass = posterior["height_mass"]
    return {"probability_within_tolerance": float(mass[distance <= tolerance].sum()),
            "expected_abs_error_m": float(mass @ distance),
            "state": "CONDITIONAL_POSTERIOR",
            "mean_inlier_probability": posterior["mean_inlier_probability"],
            "sd_offset_m": posterior["sd_offset_m"],
            "boundary_mass": posterior["boundary_mass"],
            "measurement_count": posterior["measurement_count"]}


def choose_action(candidates, method, threshold=0.3, probability=0.9):
    """Select supported candidates; FUSION additionally requires both parents.

    Inputs contain only computed evidence. Fixed-source baselines intentionally
    skip eligibility and remain conditional reference-source comparisons.
    """
    if method in ("FIXED_IMAGE", "FIXED_PRIOR"):
        source = method.removeprefix("FIXED_")
        return source if source in candidates else "ABSTAIN"
    eligible, ranking = {}, {}
    for source, c in candidates.items():
        if method == "SCORE_GATE":
            score = c.get("score")
            eligible[source] = score is not None and score >= threshold
            ranking[source] = -(score if score is not None else -np.inf)
        elif method.startswith("BAYES_GAUSS_UNIFORM"):
            p = c["posterior"].get("probability_within_tolerance")
            eligible[source] = p is not None and p >= probability
            ranking[source] = c["posterior"].get("expected_abs_error_m")
        elif method.startswith("DISCRETE_RANGE"):
            eligible[source] = c["range"]["state"] == "SUPPORTED_FINITE_HEIGHT_CONDITIONAL"
            ranking[source] = c["range"]["upper_m"]
        else:
            raise ValueError(f"Unknown method {method}")
    if "FUSION" in eligible:
        eligible["FUSION"] &= eligible.get("IMAGE", False) and eligible.get("PRIOR", False)
        eligible["FUSION"] &= candidates["FUSION"].get("parent_geometry_compatible", False)
    options = [s for s in candidates if eligible.get(s, False)]
    return min(options, key=lambda s: (ranking[s], ACTIONS.index(s))) if options else "ABSTAIN"


def strict_action(conditional_action, verified_contracts=None):
    """A missing contract is unknown, never a default True."""
    if conditional_action not in ACTIONS:
        raise ValueError(f"Invalid action: {conditional_action}")
    contracts = verified_contracts or {}
    return conditional_action if all(contracts.get(k) is True for k in CERTIFICATION_CONTRACTS) else "ABSTAIN"


def acceptance_metrics(actions, usable_by_action, errors_by_action):
    """Reference-only consumer; unknown truth stays outside risk denominator.

    None denotes absent/ambiguous reference, unlike measured False. Multiple
    candidates may be usable. Zero acceptance risk is None, not zero.
    """
    n, accepted, evaluable, false, valid_abstain, valid_any, both_bad = 0, 0, 0, 0, 0, 0, 0
    errors, unknown_accepted = [], 0
    for a, usable, err in zip(actions, usable_by_action, errors_by_action):
        n += 1
        known = [v for v in usable.values() if v is not None]
        any_valid = any(v is True for v in known)
        valid_any += any_valid
        valid_abstain += a == "ABSTAIN" and any_valid
        both_bad += bool(known) and len(known) == len(usable) and not any_valid
        if a == "ABSTAIN":
            continue
        accepted += 1
        state = usable.get(a)
        if state is None:
            unknown_accepted += 1
            continue
        evaluable += 1
        false += state is False
        if err.get(a) is not None:
            errors.append(float(err[a]))
    return {"units": n, "accepted": accepted, "reference_evaluable_accepted": evaluable,
            "reference_unknown_accepted": unknown_accepted, "false_accepted": false,
            "false_acceptance_rate": false / evaluable if evaluable else None,
            "acceptance_coverage": accepted / n if n else None,
            "usable_candidate_units": valid_any, "usable_but_abstained": valid_abstain,
            "usable_abstention_rate": valid_abstain / valid_any if valid_any else None,
            "all_available_candidates_bad": both_bad,
            "accepted_mean_error_m": float(np.mean(errors)) if errors else None}
