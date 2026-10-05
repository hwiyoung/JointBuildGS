"""Symmetric, conditional source selection from matched multiview observations.

These fixed development gates are not calibrated probabilities of source accuracy
or currentness. No evaluation reference is an input. A missing/weak image source
never grants the prior authority, and no fused geometry is instantiated.
"""
from __future__ import annotations

import math
from statistics import median


DEFAULT_CONFIG = {
    "min_common_pairs": 3,
    "min_distinct_views": 4,
    "min_disjoint_pairs": 2,
    "max_cost": 0.25,
    "margin": 0.05,
    "min_support_fraction": 0.75,
    "min_profile_separation": 0.03,
    "max_best_shift_m": 0.5,
    "profile_control_min_abs_shift_m": 1.0,
    "min_profile_coverage": 0.75,
}


def _number(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _maximum_disjoint_pairs(pairs):
    """Exact maximum matching for the small bounded observation-pair graph."""
    edges = {tuple(sorted(pair)) for pair in pairs if len(pair) == 2 and pair[0] != pair[1]}
    memo = {}

    def solve(remaining):
        if not remaining:
            return 0
        if remaining in memo:
            return memo[remaining]
        a, _ = next(iter(remaining))
        without_a = frozenset(edge for edge in remaining if a not in edge)
        best = solve(without_a)
        for edge in remaining:
            if a in edge:
                other = edge[1] if edge[0] == a else edge[0]
                rest = frozenset(e for e in without_a if other not in e)
                best = max(best, 1 + solve(rest))
        memo[remaining] = best
        return best

    return solve(frozenset(edges))


def _profile_check(profile, cfg):
    """Require an observable basin near the unmodified native candidate plane."""
    result = {"status": "PROFILE_MISSING", "best_shift_m": None,
              "control_separation": None, "valid_offset_fraction": 0.0,
              "metric": "PAIRED_SHIFTED_MINUS_NOMINAL_COST_SAME_MASK"}
    if not isinstance(profile, list) or not profile:
        return result
    rows = []
    for row in profile:
        offset, cost, coverage = (_number(row.get(key)) for key in ("offset_m", "paired_delta_cost", "coverage_fraction"))
        if (offset is not None and cost is not None and -1 <= cost <= 1
                and coverage is not None and cfg["min_profile_coverage"] <= coverage <= 1):
            rows.append((offset, cost))
    result["valid_offset_fraction"] = len(rows) / len(profile)
    if (result["valid_offset_fraction"] < cfg["min_profile_coverage"]
            or not any(abs(offset) < 1e-8 for offset, _ in rows)):
        result["status"] = "PROFILE_INSUFFICIENT_COVERAGE"
        return result
    low = [cost for offset, cost in rows if offset <= -cfg["profile_control_min_abs_shift_m"]]
    high = [cost for offset, cost in rows if offset >= cfg["profile_control_min_abs_shift_m"]]
    if not low or not high:
        result["status"] = "PROFILE_CONTROLS_MISSING"
        return result
    best_cost = min(cost for _, cost in rows)
    # Ties choose the farthest equally good offset, so a flat remote mode cannot
    # acquire a spurious zero-displacement optimum from array ordering.
    best_shift = max((offset for offset, cost in rows if abs(cost-best_cost) < 1e-12), key=abs)
    separation = min(min(low), min(high)) - best_cost
    result.update(best_shift_m=best_shift, control_separation=separation)
    if max(cost for _, cost in rows) - best_cost <= 1e-12:
        result["status"] = "PROFILE_FLAT_OR_REMOTE_AMBIGUITY"
    elif abs(best_shift) > cfg["max_best_shift_m"] + 1e-12:
        result["status"] = "PROFILE_REQUIRES_GEOMETRY_CORRECTION"
    elif separation + 1e-12 < cfg["min_profile_separation"]:
        result["status"] = "PROFILE_FLAT_OR_REMOTE_AMBIGUITY"
    else:
        result["status"] = "PROFILE_SUPPORTED_CONDITIONAL"
    return result


def decide(observation, candidate_metadata, config=None):
    """Return IMAGE/PRIOR/ABSTAIN without reference-based tuning.

    Observation is the output of ``photometry.score_candidates``. Pair geometry
    is under ``shared.selected_pairs``; per-source ``pairs`` contain costs, and
    ``profile`` contains offset/cost/coverage rows. Costs are (1-ZNCC)/2.
    Native metadata supplies ``mvs`` and ``als`` dictionaries with ``valid``.
    Pair counts are reconstructed from finite common observations, so duplicated
    pairs and a shared central view cannot manufacture independent support.
    """
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    for key, value in cfg.items():
        if key not in DEFAULT_CONFIG or _number(value) is None or value < 0:
            raise ValueError("Invalid source-selection configuration: " + key)
    for key in ("max_cost", "min_support_fraction", "min_profile_coverage"):
        if cfg[key] > 1:
            raise ValueError(key + " must lie in [0,1]")
    output = {"action": "ABSTAIN", "reason": "CANDIDATE_MISSING_OR_INVALID",
              "provisional_best_source": None, "score_margin": None,
              "signed_mvs_advantage": None, "accepted": False,
              "temporal_status": "UNIDENTIFIABLE", "scientific_verdict": None,
              "costs": {"mvs": None, "als": None}, "support_fraction": None,
              "common_pairs": 0, "distinct_views": 0, "disjoint_pairs": 0,
              "winner_profile": None}
    if not all(candidate_metadata.get(s, {}).get("valid", False) for s in ("mvs", "als")):
        return output
    pairs = []
    seen = set()
    by_source = {s: {row["pair_id"]: row for row in observation.get("candidates", {}).get(s, {}).get("pairs", [])}
                 for s in ("mvs", "als")}
    for row in observation.get("shared", {}).get("selected_pairs", []):
        ids = [row.get("reference_id"), row.get("target_id")]
        if None in ids or ids[0] == ids[1]:
            continue
        edge = tuple(sorted(map(str, ids)))
        m, p = (_number(by_source[s].get(row["pair_id"], {}).get("cost")) for s in ("mvs", "als"))
        if edge in seen or m is None or p is None or not (0 <= m <= 1 and 0 <= p <= 1):
            continue
        seen.add(edge)
        pairs.append((edge, m, p))
    output["common_pairs"] = len(pairs)
    output["distinct_views"] = len({image for edge, _, _ in pairs for image in edge})
    output["disjoint_pairs"] = _maximum_disjoint_pairs([edge for edge, _, _ in pairs])
    if pairs:
        m, p = median([row[1] for row in pairs]), median([row[2] for row in pairs])
        output["costs"] = {"mvs": m, "als": p}
        advantage = median([row[2]-row[1] for row in pairs])
        output["score_margin"] = abs(advantage)
        output["signed_mvs_advantage"] = advantage
        output["provisional_best_source"] = "mvs" if advantage > 0 else "als" if advantage < 0 else None
    for metric, threshold, reason in (
            ("common_pairs", "min_common_pairs", "INSUFFICIENT_COMMON_PAIRS"),
            ("distinct_views", "min_distinct_views", "INSUFFICIENT_DISTINCT_VIEWS"),
            ("disjoint_pairs", "min_disjoint_pairs", "INSUFFICIENT_DISJOINT_PAIRS")):
        if output[metric] < cfg[threshold]:
            output["reason"] = reason
            return output
    winner = output["provisional_best_source"]
    if winner is None or output["score_margin"] + 1e-12 < cfg["margin"]:
        output["reason"] = "SOURCES_NOT_DISTINGUISHABLE"
        return output
    if output["costs"][winner] > cfg["max_cost"] + 1e-12:
        output["reason"] = ("BOTH_SOURCES_POOR_IMAGE_SUPPORT" if min(output["costs"].values()) > cfg["max_cost"]
                            else "PREFERRED_SOURCE_POOR_IMAGE_SUPPORT")
        return output
    sign = 1 if winner == "mvs" else -1
    output["support_fraction"] = sum(sign*(p-m) + 1e-12 >= cfg["margin"] for _, m, p in pairs) / len(pairs)
    if output["support_fraction"] + 1e-12 < cfg["min_support_fraction"]:
        output["reason"] = "INCONSISTENT_PAIRED_SOURCE_PREFERENCE"
        return output
    profile = observation.get("candidates", {}).get(winner, {}).get("profile", [])
    check = _profile_check(profile, cfg)
    output["winner_profile"] = check
    if check["status"] != "PROFILE_SUPPORTED_CONDITIONAL":
        output["reason"] = check["status"]
        return output
    output.update(action="IMAGE" if winner == "mvs" else "PRIOR", accepted=True,
                  reason="PAIRED_OBSERVATION_AND_PROFILE_SUPPORTED_CONDITIONAL",
                  temporal_status="OBSERVATION_SUPPORTED_CONDITIONAL")
    return output
