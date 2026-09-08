"""Finite-support multiview evidence on connected surface units.

Geometry and currentness are not inferred from a component label. Small patches
measure evidence; a surface is the decision context; accepted scope records only
sampled footprint tiles. References, semantic GT and resampled geometry are never
inputs. This is a development evaluator, not COLMAP PatchMatch.
"""
from __future__ import annotations

from copy import deepcopy
from itertools import combinations
from statistics import median

import numpy as np
from scipy.spatial import cKDTree

from src.phd.source_candidate_v1.decision import _profile_check
from src.phd.source_candidate_v1.photometry import (
    ScoringConfig, _cost, _disjoint_count, _inside, _intersect,
    _prepare_candidate, _sample_gray, _warp, project,
)


DEFAULT_CONFIG = {
    "max_anchor_centers": 36,
    "footprint_spacing_m": 0.5,
    "photometry": {
        "max_views": 16, "max_pairs": 24, "max_patch_centers": 36,
        "patch_width": 9, "minimum_patch_pixels": 16,
        "minimum_patch_fraction": 0.2, "minimum_patch_std": 2.,
        "support_tolerance_m": 0.6, "angle_min_deg": 2., "angle_max_deg": 45.,
        "preferred_angle_deg": 12., "resolution_ratio_max": 2.,
        "visibility_tolerance_m": 0.75,
        "profile_offsets_m": [-2., -1., -.5, 0., .5, 1., 2.],
        "profile_shift_axis": "normal", "pixel_center_offset": 0.,
    },
    "decision": {
        "min_common_pairs": 3, "min_distinct_views": 4, "min_disjoint_pairs": 2,
        "max_cost": .25, "min_pair_quality_fraction": .75,
        "margin": .05, "min_support_fraction": .75,
        "min_profile_separation": .03, "max_best_shift_m": .5,
        "profile_control_min_abs_shift_m": 1., "min_profile_coverage": .75,
        "reject_cost": .4, "min_spatial_consistency": .75,
        "min_scored_tiles": 3,
    },
}


def _settings(config):
    out = deepcopy(DEFAULT_CONFIG)
    for key, value in (config or {}).items():
        if key not in out:
            raise ValueError("Unknown surface-evidence setting: " + key)
        if isinstance(out[key], dict):
            unknown = set(value) - set(out[key])
            if unknown:
                raise ValueError("Unknown surface-evidence settings: " + str(sorted(unknown)))
            out[key].update(value)
        else:
            out[key] = value
    if int(out["max_anchor_centers"]) < 2 or out["footprint_spacing_m"] <= 0:
        raise ValueError("At least two anchor slots and positive footprint spacing required")
    return out


def _finite_median(values):
    finite = [float(v) for v in values if v is not None and np.isfinite(v)]
    return float(median(finite)) if finite else None


def _json_number(value):
    return float(value) if np.isfinite(value) else None


def _edges(rows):
    return [(str(row["reference_id"]), str(row["target_id"])) for row in rows]


def _counts(rows):
    edges = set(tuple(sorted(edge)) for edge in _edges(rows))
    return {"pair_count": len(edges), "distinct_view_count": len({v for e in edges for v in e}),
            "disjoint_pair_count": _disjoint_count(list(edges))}


def _enough(counts, cfg):
    return (counts["pair_count"] >= cfg["min_common_pairs"]
            and counts["distinct_view_count"] >= cfg["min_distinct_views"]
            and counts["disjoint_pair_count"] >= cfg["min_disjoint_pairs"])


def _farthest_indices(xy, count):
    """Deterministic spatial sample; labels and image costs never affect anchors."""
    if not len(xy):
        return []
    first = int(np.lexsort((xy[:, 1], xy[:, 0]))[0])
    selected = [first]
    distances = np.sum((xy - xy[first]) ** 2, axis=1)
    while len(selected) < min(count, len(xy)):
        distances[selected] = -1
        nxt = int(np.argmax(distances))
        selected.append(nxt)
        distances = np.minimum(distances, np.sum((xy - xy[nxt]) ** 2, axis=1))
    return selected


def _anchors(footprint, prepared, config):
    # Each source gets the same tile locations and same budget. At a selected
    # tile we project actual native points, not an interpolated midpoint surface.
    budget = max(1, int(config["max_anchor_centers"]) // max(len(prepared), 1))
    selected = _farthest_indices(footprint, budget)
    records = {}
    for name, candidate in prepared.items():
        points = candidate["support_points"]
        tree = cKDTree(points[:, :2])
        if not selected:
            continue
        distances, indices = tree.query(footprint[selected])
        for tile, distance, point_index in zip(selected, distances, indices, strict=True):
            if distance > config["footprint_spacing_m"] * np.sqrt(2):
                continue
            xyz = points[point_index]
            key = tuple(float(x) for x in xyz)
            row = records.setdefault(key, {"xyz": xyz.tolist(), "origin_tile_id": int(tile),
                                           "origin_sources": []})
            row["origin_sources"].append(name)
    return [dict(anchor_id=i, **records[key]) for i, key in enumerate(sorted(records))]


def _spatial_pairs(views, anchors, cfg):
    if not anchors:
        return []
    points = np.array([a["xyz"] for a in anchors])
    center = points.mean(axis=0)
    eligible = []
    for view in views:
        uv, z = project(points, view)
        visible = (z > 0) & _inside(uv, view, cfg)
        if not visible.any():
            continue
        depth = float(np.median(z[visible]))
        scale = float(np.sqrt(view["K"][0, 0] * view["K"][1, 1]) / depth)
        eligible.append((-int(visible.sum()), str(view["id"]), scale, view))
    eligible.sort(key=lambda row: (row[0], row[1]))
    possible = []
    for first, second in combinations(eligible[:cfg.max_views], 2):
        a, b = first[3], second[3]
        da, db = np.asarray(a["center"]) - center, np.asarray(b["center"]) - center
        divisor = np.linalg.norm(da) * np.linalg.norm(db)
        if divisor <= 0:
            continue
        angle = float(np.degrees(np.arccos(np.clip(da @ db / divisor, -1, 1))))
        ratio = max(first[2], second[2]) / min(first[2], second[2])
        if not cfg.angle_min_deg <= angle <= cfg.angle_max_deg or ratio > cfg.resolution_ratio_max:
            continue
        if str(a["id"]) > str(b["id"]):
            a, b = b, a
        possible.append({"reference": a, "target": b, "pair_id": f"{a['id']}->{b['id']}",
                         "angle_deg": angle,
                         "rank": abs(angle-cfg.preferred_angle_deg) + 2*abs(np.log(ratio))})
    possible.sort(key=lambda pair: (pair["rank"], pair["pair_id"]))
    selected, used = [], set()
    for pair in possible:
        ids = {str(pair["reference"]["id"]), str(pair["target"]["id"])}
        if not ids & used and len(selected) < cfg.max_pairs:
            selected.append(pair)
            used |= ids
    selected_ids = {p["pair_id"] for p in selected}
    selected.extend(p for p in possible if p["pair_id"] not in selected_ids)
    return selected[:cfg.max_pairs]


def _pixels(anchors, reference, cfg):
    xyz = np.array([a["xyz"] for a in anchors])
    uv, z = project(xyz, reference)
    good = (z > 0) & _inside(uv, reference, cfg)
    indices = np.flatnonzero(good)
    uv = np.round(uv[good] - cfg.pixel_center_offset) + cfg.pixel_center_offset
    uv, unique = np.unique(uv, axis=0, return_index=True)
    indices = indices[unique]
    radius = cfg.patch_width // 2
    dx, dy = np.meshgrid(np.arange(-radius, radius+1), np.arange(-radius, radius+1))
    return uv[:, None] + np.column_stack((dx.ravel(), dy.ravel()))[None], indices


def _profile_rows(storage):
    return [{"offset_m": float(offset), "cost": _finite_median(row["costs"]),
             "paired_nominal_cost": _finite_median(row["nominal"]),
             "paired_delta_cost": _finite_median(row["delta"]),
             "common_patch_count": row["count"],
             "coverage_fraction": row["count"] / max(row["nominal_count"], 1)}
            for offset, row in storage.items()]


def _profile_storage(cfg):
    return {float(offset): {"costs": [], "nominal": [], "delta": [], "count": 0,
                            "nominal_count": 0} for offset in cfg.profile_offsets_m}


def _add_profiles(storage, nominal_costs, nominal_values, mask, pixels, reference,
                  target, candidate, reference_values, cfg):
    for offset, row in storage.items():
        if offset == 0:
            shifted_costs = baseline = nominal_costs
        else:
            shifted = _warp(pixels, reference, target, candidate, cfg, offset, use_context=False)
            shared = mask & shifted["valid"]
            shifted_costs = _cost(reference_values, shifted["values"], shared, cfg)[0]
            baseline = _cost(reference_values, nominal_values, shared, cfg)[0]
            shifted_costs[~np.isfinite(nominal_costs)] = np.nan
            baseline[~np.isfinite(nominal_costs)] = np.nan
        good = np.isfinite(shifted_costs) & np.isfinite(baseline)
        if good.any():
            row["costs"].append(float(np.median(shifted_costs[good])))
            row["nominal"].append(float(np.median(baseline[good])))
            row["delta"].append(float(np.median(shifted_costs[good] - baseline[good])))
        row["count"] += int(good.sum())
        row["nominal_count"] += int(np.isfinite(nominal_costs).sum())


def _assess(pair_rows, profile, cfg, available):
    scored = [row for row in pair_rows if row["cost"] is not None]
    counts = _counts(scored)
    cost = _finite_median([r["cost"] for r in scored])
    check = _profile_check(profile, cfg)
    good_fraction = sum(r["cost"] <= cfg["max_cost"] for r in scored) / max(len(scored), 1)
    bad_fraction = sum(r["cost"] >= cfg["reject_cost"] for r in scored) / max(len(scored), 1)
    out = {"status": "UNDETERMINED", "reason": "CANDIDATE_MISSING_OR_INVALID",
           "cost": cost, "counts": counts, "quality_pair_fraction": good_fraction,
           "poor_pair_fraction": bad_fraction, "profile_check": check,
           "profile": profile, "semantics": "CURRENT_IMAGE_COMPATIBILITY_CONDITIONAL"}
    if not available:
        return out
    if not _enough(counts, cfg):
        out["reason"] = "INSUFFICIENT_SOURCE_OBSERVATIONS"
    elif bad_fraction >= cfg["min_pair_quality_fraction"]:
        out.update(status="REJECT", reason="POOR_CURRENT_IMAGE_COMPATIBILITY")
    elif check["status"] == "PROFILE_REQUIRES_GEOMETRY_CORRECTION":
        out.update(status="REJECT", reason="NATIVE_GEOMETRY_REQUIRES_CORRECTION")
    elif (cost is not None and cost <= cfg["max_cost"]
          and good_fraction >= cfg["min_pair_quality_fraction"]
          and check["status"] == "PROFILE_SUPPORTED_CONDITIONAL"):
        out.update(status="SUPPORT", reason="SOURCE_OBSERVATION_AND_PROFILE_SUPPORTED")
    elif check["status"] != "PROFILE_SUPPORTED_CONDITIONAL":
        out["reason"] = check["status"]
    else:
        out["reason"] = "INCONSISTENT_SOURCE_OBSERVATIONS"
    return out


def _scope_tiles(tile_evidence, cfg):
    accepted = []
    for tile, rows in tile_evidence.items():
        # Aggregate multiple anchors within a camera pair before counting views.
        by_pair = {}
        for row in rows:
            by_pair.setdefault(row["pair_id"], []).append(row)
        pairs = [dict(values[0], cost=_finite_median([v["cost"] for v in values]))
                 for values in by_pair.values()]
        if not _enough(_counts(pairs), cfg):
            continue
        fraction = sum(r["cost"] <= cfg["max_cost"] for r in pairs) / len(pairs)
        if fraction >= cfg["min_pair_quality_fraction"]:
            accepted.append(int(tile))
    return sorted(accepted)


def _spatial_preferences(votes, cfg):
    """Persistent tile preferences, with camera diversity and one vote per pair."""
    tiles = {}
    for vote in votes:
        tiles.setdefault(vote["tile_id"], {}).setdefault(vote["pair_id"], []).append(vote)
    output = {"mvs": [], "als": [], "inconsistent": []}
    diagnostics = []
    for tile, grouped in sorted(tiles.items()):
        pairs = [dict(values[0], advantage=_finite_median([v["advantage"] for v in values]))
                 for values in grouped.values()]
        counts = _counts(pairs)
        preference = _finite_median([row["advantage"] for row in pairs])
        if not _enough(counts, cfg) or preference is None or abs(preference) < cfg["margin"]:
            continue
        sign = 1 if preference > 0 else -1
        agreement = sum(sign*p["advantage"] >= cfg["margin"] for p in pairs) / len(pairs)
        label = ("mvs" if preference > 0 else "als") if agreement >= cfg["min_support_fraction"] else "inconsistent"
        output[label].append(int(tile))
        diagnostics.append({"local_tile_id": int(tile), "preference": label,
                            "view_counts": counts, "agreement_fraction": agreement})
    return output, diagnostics


def evaluate_unit(unit, candidates, views, config=None):
    """Return observation and IMAGE/PRIOR/ABSTAIN on directly sampled scope.

    ``footprint_xy`` must be occupied tile centers. Geometry inputs remain exact
    source native points. Multiple candidate IDs for a source are kept ambiguous.
    A singleton is tested independently; absence of a competitor is not support.
    """
    settings = _settings(config)
    cfg, gate = ScoringConfig(**settings["photometry"]), settings["decision"]
    footprint = np.asarray(unit["footprint_xy"], dtype=float).reshape(-1, 2)
    if not np.isfinite(footprint).all() or not len(footprint):
        raise ValueError("Unit requires finite occupied footprint tile centers")
    valid = {s: c for s, c in candidates.items() if s in ("mvs", "als") and c
             and c.get("valid", True) and len(c.get("support_points", [])) >= 3}
    prepared = {s: _prepare_candidate(c, cfg) for s, c in valid.items()}
    anchors = _anchors(footprint, prepared, settings)
    pairs = _spatial_pairs(views, anchors, cfg)
    profiles = {s: _profile_storage(cfg) for s in prepared}
    paired_profiles = {s: _profile_storage(cfg) for s in prepared}
    source_pairs = {s: [] for s in ("mvs", "als")}
    paired_rows = {s: [] for s in ("mvs", "als")}
    tile_evidence = {s: {} for s in ("mvs", "als")}
    pair_records, patch_records, paired_preferences = [], [], []
    tile_tree = cKDTree(footprint)
    for pair in pairs:
        reference, target = pair["reference"], pair["target"]
        pixels, anchor_ids = _pixels(anchors, reference, cfg)
        if not len(pixels):
            continue
        reference_values = _sample_gray(pixels, reference, cfg)
        warps = {s: _warp(pixels, reference, target, c, cfg) for s, c in prepared.items()}
        common = (np.logical_and.reduce([w["valid"] for w in warps.values()])
                  if len(prepared) == 2 else np.zeros(pixels.shape[:2], bool))
        basic = {"pair_id": pair["pair_id"], "reference_id": reference["id"],
                 "target_id": target["id"], "angle_deg": pair["angle_deg"]}
        pair_records.append({**basic, "reference_pixel_centers": pixels[:, cfg.patch_width**2//2].tolist(),
                             "anchor_ids": anchor_ids.tolist()})
        own_costs, shared_costs, tiles = {}, {}, {}
        for source, candidate in prepared.items():
            warp = warps[source]
            own_costs[source] = _cost(reference_values, warp["values"], warp["valid"], cfg)[0]
            shared_costs[source] = _cost(reference_values, warp["values"], common, cfg)[0]
            center_index = cfg.patch_width**2//2
            xyz, supported = _intersect(pixels[:, center_index:center_index+1], reference, candidate, 0, cfg)
            finite = np.isfinite(xyz[:, 0, :2]).all(axis=1)
            _, tile_indices = tile_tree.query(np.where(finite[:, None], xyz[:, 0, :2], 1e30))
            in_tile = (np.abs(xyz[:, 0, :2] - footprint[tile_indices]).max(axis=1)
                       <= settings["footprint_spacing_m"] / 2 + 1e-6)
            tiles[source] = np.where(supported[:, 0] & warp["valid"][:, center_index]
                & finite & in_tile, tile_indices, -1)
            row = {**basic, "cost": _finite_median(own_costs[source]),
                   "scored_patch_count": int(np.isfinite(own_costs[source]).sum())}
            source_pairs[source].append(row)
            paired_rows[source].append({**basic, "cost": _finite_median(shared_costs[source]),
                "common_patch_count": int(np.isfinite(shared_costs[source]).sum()),
                "reference_pixel_centers": pixels[:, center_index].tolist()})
            _add_profiles(profiles[source], own_costs[source], warp["values"], warp["valid"],
                          pixels, reference, target, candidate, reference_values, cfg)
            if len(prepared) == 2:
                _add_profiles(paired_profiles[source], shared_costs[source], warp["values"], common,
                              pixels, reference, target, candidate, reference_values, cfg)
            for index, cost in enumerate(own_costs[source]):
                tile = int(tiles[source][index])
                if np.isfinite(cost) and tile >= 0:
                    tile_evidence[source].setdefault(tile, []).append({**basic, "cost": float(cost)})
        for index, anchor_id in enumerate(anchor_ids):
            costs = {s: _json_number(shared_costs[s][index]) if s in prepared else None for s in source_pairs}
            patch_records.append({"pair_id": pair["pair_id"], "patch_index": index,
                "anchor_id": int(anchor_id), "common_pixels": int(common[index].sum()),
                "own_costs": {s: _json_number(own_costs[s][index]) if s in prepared else None for s in source_pairs},
                "paired_costs": costs,
                "tile_ids": {s: int(tiles[s][index]) if s in prepared and tiles[s][index] >= 0 else None for s in source_pairs}})
            if all(costs[s] is not None for s in source_pairs):
                advantage = costs["als"] - costs["mvs"]
                if abs(advantage) >= gate["margin"]:
                    winner = "mvs" if advantage > 0 else "als"
                    tile = int(tiles[winner][index])
                    if tile >= 0:
                        paired_preferences.append({**basic, "source": winner, "tile_id": tile,
                                                   "advantage": float(advantage)})
    assessments = {s: _assess(source_pairs[s], _profile_rows(profiles[s]) if s in prepared else [],
                             gate, s in prepared) for s in source_pairs}
    scopes = {s: _scope_tiles(tile_evidence[s], gate) for s in source_pairs}
    for s in assessments:
        assessments[s]["scored_tile_count"] = len(tile_evidence[s])
        assessments[s]["supported_tile_ids"] = scopes[s]
        assessments[s]["supported_tile_fraction"] = len(scopes[s]) / len(footprint)
    scored_common = [r for r in pair_records if all(next((p["cost"] for p in paired_rows[s]
                           if p["pair_id"] == r["pair_id"]), None) is not None for s in source_pairs)]
    counts = _counts(scored_common)
    differences = [{"pair_id": m["pair_id"], "mvs_advantage": a["cost"]-m["cost"]}
                   for m, a in zip(paired_rows["mvs"], paired_rows["als"])
                   if m["cost"] is not None and a["cost"] is not None]
    advantage = _finite_median([r["mvs_advantage"] for r in differences])
    spacing = settings["footprint_spacing_m"]
    origin = footprint.min(axis=0)
    keys = {tuple(np.round((xy-origin) / spacing).astype(int)) for xy in footprint}
    boundary = [i for i, xy in enumerate(footprint)
                if any((tuple(np.round((xy-origin) / spacing).astype(int) + d) not in keys)
                       for d in ((-1, 0), (1, 0), (0, -1), (0, 1)))]
    preferences, spatial_diagnostics = _spatial_preferences(paired_preferences, gate)
    for s in assessments:
        assessments[s]["supported_boundary_tile_count"] = len(set(scopes[s]) & set(boundary))
        assessments[s]["boundary_tile_fraction"] = len(set(scopes[s]) & set(boundary)) / max(len(boundary), 1)
    observation = {"schema": "jointbuildgs.surface_selection.evidence.v1", "unit_id": unit["id"],
        "status": "SCORED" if any(a["cost"] is not None for a in assessments.values()) else "UNOBSERVED",
        "config": settings, "anchors": anchors, "source_assessments": assessments,
        "source_pairs": source_pairs, "patches": patch_records,
        "shared": {"selected_pairs": pair_records, "pair_count": len(pair_records),
                   "common_scored_pair_count": counts["pair_count"],
                   "distinct_view_count": counts["distinct_view_count"],
                   "disjoint_pair_count": counts["disjoint_pair_count"],
                   "visibility_semantics": "MODEL_SELF_VISIBILITY"},
        "candidates": {s: {"cost": _finite_median([r["cost"] for r in paired_rows[s]]),
                            "pairs": paired_rows[s],
                            "profile": _profile_rows(paired_profiles[s]) if s in prepared else []}
                       for s in source_pairs},
        "contrast": {"signed_mvs_advantage": advantage, "paired_differences": differences},
        "spatial": {"footprint_xy": footprint.tolist(), "boundary_tile_ids": boundary,
                    "tile_id_semantics": "LOCAL_ORDINAL_IN_FOOTPRINT_XY",
                    "footprint_tile_ids": unit.get("tile_ids", list(range(len(footprint)))),
                    "footprint_tile_count": len(footprint), "paired_preferences": paired_preferences,
                    "source_preference_tiles": preferences, "preference_diagnostics": spatial_diagnostics,
                    "directly_supported_tile_ids": scopes},
        "limitations": ["Source SUPPORT is conditional image compatibility, not currentness or correctness probability.",
            "REJECT never authorizes deletion or claims observed free space.",
            "Footprint tiles report sampled scope; unobserved parts never inherit the surface label.",
            "Current-image MVS and scoring views share developmental lineage."],
        "scientific_verdict": None}
    decision = _decide(unit, observation, gate, footprint, spacing)
    return observation, decision


def _decide(unit, observation, cfg, footprint, spacing):
    assessments = observation["source_assessments"]
    out = {"action": "ABSTAIN", "accepted": False, "reason": "INSUFFICIENT_OBSERVATION_EVIDENCE",
           "accepted_scope": {"tile_ids": [], "local_tile_indices": [], "footprint_xy": [], "sampled_area_m2": 0.,
                              "semantics": "DIRECTLY_SAMPLED_TILES_NOT_WHOLE_UNIT_PROPAGATION"},
           "unknown_tile_count": len(footprint), "scientific_verdict": None,
           "temporal_status": "UNIDENTIFIABLE", "source_assessments": {s: a["status"] for s, a in assessments.items()},
           "signed_mvs_advantage": observation["contrast"]["signed_mvs_advantage"],
           "spatial_preference_consistency": None}
    if any(len(unit.get(s+"_ids", [])) > 1 for s in assessments):
        out["reason"] = "AMBIGUOUS_MULTIPLE_SURFACE_COMPONENTS"
        return out
    supported = [s for s, a in assessments.items() if a["status"] == "SUPPORT"]
    source_present = [s for s, a in assessments.items() if a["reason"] != "CANDIDATE_MISSING_OR_INVALID"]
    selected, reason = None, None
    if len(source_present) == 1 and supported == source_present:
        selected, reason = supported[0], "SINGLE_SOURCE_INDEPENDENTLY_OBSERVATION_SUPPORTED"
    elif len(supported) == 1 and any(a["status"] == "REJECT" for a in assessments.values()):
        selected, reason = supported[0], "ONE_SUPPORTED_OTHER_OBSERVATION_INCOMPATIBLE"
    else:
        counts = {"pair_count": observation["shared"]["common_scored_pair_count"],
                  "distinct_view_count": observation["shared"]["distinct_view_count"],
                  "disjoint_pair_count": observation["shared"]["disjoint_pair_count"]}
        advantage = observation["contrast"]["signed_mvs_advantage"]
        if _enough(counts, cfg) and advantage is not None and abs(advantage) >= cfg["margin"]:
            winner = "mvs" if advantage > 0 else "als"
            sign = 1 if winner == "mvs" else -1
            differences = observation["contrast"]["paired_differences"]
            consistency = sum(sign*r["mvs_advantage"] >= cfg["margin"] for r in differences) / len(differences)
            common_cost = observation["candidates"][winner]["cost"]
            common_profile = _profile_check(observation["candidates"][winner]["profile"], cfg)
            if (winner in supported and consistency >= cfg["min_support_fraction"]
                    and common_cost is not None and common_cost <= cfg["max_cost"]
                    and common_profile["status"] == "PROFILE_SUPPORTED_CONDITIONAL"):
                selected, reason = winner, "MATCHED_PATCH_PREFERENCE_AND_SOURCE_SUPPORT"
            else:
                out["reason"] = "PAIRED_PREFERENCE_NOT_SUFFICIENTLY_SUPPORTED"
        elif supported:
            out["reason"] = "SUPPORTED_CANDIDATES_NOT_COMPARABLY_DISTINGUISHED"
    if selected is None:
        return out
    preferences = observation["spatial"]["source_preference_tiles"]
    total_preferences = len(preferences["mvs"]) + len(preferences["als"])
    consistency = len(preferences[selected]) / total_preferences if total_preferences else None
    out["spatial_preference_consistency"] = consistency
    if consistency is not None and consistency < cfg["min_spatial_consistency"]:
        out["reason"] = "SPATIAL_SOURCE_CONFLICT_REQUIRES_SUBDIVISION"
        return out
    other = "als" if selected == "mvs" else "mvs"
    excluded = set(preferences[other]) | set(preferences["inconsistent"])
    scope = sorted(set(assessments[selected]["supported_tile_ids"]) - excluded)
    out["excluded_conflicting_local_tile_indices"] = sorted(excluded)
    if len(scope) < cfg["min_scored_tiles"]:
        out["reason"] = "INSUFFICIENT_SPATIALLY_DISTRIBUTED_DIRECT_SUPPORT"
        return out
    out.update(action="IMAGE" if selected == "mvs" else "PRIOR", accepted=True, reason=reason,
        temporal_status="OBSERVATION_SUPPORTED_CONDITIONAL", unknown_tile_count=len(footprint)-len(scope),
        accepted_scope={"tile_ids": [int(unit.get("tile_ids", list(range(len(footprint))))[i]) for i in scope],
                        "local_tile_indices": scope, "footprint_xy": footprint[scope].tolist(),
                        "sampled_area_m2": min(len(scope)*spacing**2, float(unit.get("area_m2", len(footprint)*spacing**2))),
                        "semantics": "DIRECTLY_SAMPLED_TILES_NOT_WHOLE_UNIT_PROPAGATION"})
    return out


def replay_evidence(observation, candidates, views, pair_id=None, anchor_index=None):
    """Replay a saved pair/patch using exact RGB and native support, without scoring decisions."""
    settings = observation["config"]
    cfg = ScoringConfig(**settings["photometry"])
    saved = observation["shared"]["selected_pairs"]
    if not saved:
        return {"available": False, "reason": "NO_SAVED_CAMERA_PAIR", "scientific_verdict": None}
    pair = next((p for p in saved if p["pair_id"] == pair_id), None) if pair_id is not None else saved[0]
    if pair is None:
        raise ValueError("Unknown saved camera pair")
    by_id = {str(v["id"]): v for v in views}
    reference, target = [by_id[str(pair[k])] for k in ("reference_id", "target_id")]
    radius = cfg.patch_width // 2
    dx, dy = np.meshgrid(np.arange(-radius, radius+1), np.arange(-radius, radius+1))
    centers = np.asarray(pair["reference_pixel_centers"], dtype=float)
    pixels = centers[:, None] + np.column_stack((dx.ravel(), dy.ravel()))[None]
    prepared = {s: _prepare_candidate(c, cfg) for s, c in candidates.items() if s in ("mvs", "als")
                and c and c.get("valid", True) and len(c.get("support_points", [])) >= 3}
    warps = {s: _warp(pixels, reference, target, c, cfg) for s, c in prepared.items()}
    common = (np.logical_and.reduce([w["valid"] for w in warps.values()])
              if len(warps) == 2 else np.zeros(pixels.shape[:2], bool))
    ref_values = _sample_gray(pixels, reference, cfg)
    costs = {s: _cost(ref_values, w["values"], common, cfg)[0] for s, w in warps.items()}
    own_costs = {s: _cost(ref_values, w["values"], w["valid"], cfg)[0] for s, w in warps.items()}
    if anchor_index is None:
        counts = common.sum(1) if common.any() else np.logical_or.reduce([w["valid"] for w in warps.values()]).sum(1)
        anchor_index = int(np.argmax(counts))
    if not 0 <= int(anchor_index) < len(pixels):
        raise ValueError("Unknown saved patch index")
    index = int(anchor_index)
    target_pixels = {}
    for source, candidate in prepared.items():
        xyz, _ = _intersect(pixels[index:index+1], reference, candidate, 0, cfg)
        target_pixels[source] = project(xyz, target)[0][0].tolist()
    def describe(view):
        return {"id": view["id"], "name": view.get("name", str(view["id"])),
                "width": view["width"], "height": view["height"],
                "image_url": view.get("image_url"), "path": view.get("path")}
    return {"available": True, "unit_id": observation["unit_id"], "pair_id": pair["pair_id"],
        "anchor_index": index, "anchor_id": pair["anchor_ids"][index], "patch_width": cfg.patch_width,
        "reference": {**describe(reference), "pixels": pixels[index].tolist()},
        "target": {**describe(target), "pixels": target_pixels},
        "patches": {"reference": ref_values[index].tolist(),
                    **{s: w["values"][index].tolist() for s, w in warps.items()}},
        "common_mask": common[index].tolist(), "common_pixels": int(common[index].sum()),
        "own_masks": {s: w["valid"][index].tolist() for s, w in warps.items()},
        "costs": {s: _json_number(c[index]) for s, c in costs.items()},
        "own_costs": {s: _json_number(c[index]) for s, c in own_costs.items()},
        "reproduced_pair_costs": {s: _finite_median(c) for s, c in costs.items()},
        "scientific_verdict": None}
