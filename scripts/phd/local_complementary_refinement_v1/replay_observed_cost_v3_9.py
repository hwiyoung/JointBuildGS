#!/usr/bin/env python3
"""Replay saved photo costs on shared cameras; never read reference geometry.

This aggregates immutable v3.7 costs. It does not recompute images, certify
visibility, estimate depth accuracy, construct dense weight maps, or train GS.
"""

import argparse
import csv
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import platform
import statistics
import sys
from datetime import datetime, timezone

import numpy as np


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def finite(value):
    return isinstance(value, (int, float)) and math.isfinite(value)


def evidence(costs, knots, gate):
    if gate == 0:
        return {"S": 0.0, "R": 0.0, "U": 1.0}
    low, center, high = knots
    plus = [min(1.0, max(0.0, (center - e) / (center - low))) for e in costs]
    minus = [min(1.0, max(0.0, (e - center) / (high - center))) for e in costs]
    support, rejection = min(plus), min(minus)
    assert -1e-12 <= support + rejection <= 1.0 + 1e-12
    return {"S": support, "R": rejection, "U": max(0.0, 1.0 - support - rejection)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args()
    cfg = json.loads(args.config.read_text())
    root, out = Path(cfg["source_root_container"]), Path(cfg["output_container"])
    assert not cfg["reference_read_allowed"]
    for name in ("result.json", "sensitivity.csv", "units.csv", "receipt.json", "failure.json"):
        if (out / name).exists():
            raise FileExistsError(out / name)
    started = datetime.now(timezone.utc).isoformat()
    module_path = Path("/repo/src/phd/local_source_weight_v3_8.py")
    module_spec = importlib.util.spec_from_file_location("frozen_weight", module_path)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    provenance_paths = [args.config, Path(__file__), module_path,
                        Path("/repo/docs/experiments/phd/local_complementary_refinement_v1/COST_WEIGHT_CANDIDATE_v3_8.json"),
                        Path("/repo/docs/experiments/phd/local_complementary_refinement_v1/COST_WEIGHT_CANDIDATE_ko_v3_8.md")]
    frozen_provenance = {str(path): sha(path) for path in provenance_paths}
    input_hashes = {}
    data = {}
    for relative, expected in cfg["input_sha256"].items():
        path = root / relative
        if relative != "scores.json" and not (relative.startswith("cases/") and relative.endswith("/case.json")):
            raise ValueError("Unexpected input file: " + relative)
        actual = sha(path)
        assert actual == expected, (relative, actual, expected)
        input_hashes[relative] = actual
        data[relative] = json.loads(path.read_text())
    scores = data.pop("scores.json")
    cases = {case["case_id"]: case for case in data.values()}
    assert len(scores) == cfg["expected_input_rows"]
    assert len(cases) == cfg["expected_cases"]
    indexed = {}
    for row in scores:
        key = (row["case_id"], row["pair"], row["patch_size"], row["neighbor"])
        assert key not in indexed, key
        indexed[key] = row
    units, sensitivity = [], []
    checks = {"input_hashes": len(input_hashes), "score_case_metadata_matches": 0,
              "median_independent_checks": 0, "central_evidence_parity": 0,
              "weight_budget_checks": 0, "unknown_gate_fallback_checks": 0}

    def costs_on(case_id, pair, branch, members):
        if len(members) < cfg["minimum_views"]:
            return None
        result = {}
        for source in cfg["pairs"][pair]:
            values = []
            for size in cfg["patch_sizes"]:
                samples = [indexed[(case_id, pair, size, i)][branch][source]["cost"] for i in members]
                median = float(statistics.median(samples))
                assert math.isclose(median, float(np.median(samples)), abs_tol=1e-15)
                checks["median_independent_checks"] += 1
                values.append(median)
            result[source] = values
        return result

    for case_id, case in sorted(cases.items()):
        neighbor_by_index = {x["index"]: x for x in case["neighbors"]}
        assert len(neighbor_by_index) == len(case["neighbors"])
        for pair, sources in cfg["pairs"].items():
            source_valid = {s: finite(case["depths"].get(s)) and case["depths"][s] > 0 for s in sources}
            branch_units = {}
            for branch in cfg["branches"]:
                eligibility = []
                common_views = []
                for index, neighbor in sorted(neighbor_by_index.items()):
                    all_eligible = True
                    scale_details = []
                    for size in cfg["patch_sizes"]:
                        row = indexed[(case_id, pair, size, index)]
                        embedded = neighbor["patches"][str(size)]["comparisons"][pair]
                        assert row[branch] == embedded[branch]
                        assert row["common_count"] == embedded["common_count"]
                        checks["score_case_metadata_matches"] += 1
                        reasons = []
                        fraction = row["common_count"] / (size * size)
                        if fraction < cfg["minimum_common_fraction"]:
                            reasons.append("LOW_INHERITED_FOURWAY_COMMON_SUPPORT")
                        for source in sources:
                            score = row[branch][source]
                            if not source_valid[source]:
                                reasons.append(source + ":MISSING_CENTER_TARGET")
                            cost = score.get("cost")
                            if not finite(cost) or not 0 <= cost <= 1:
                                reasons.append(source + ":UNDEFINED_OR_INVALID_COST")
                            for stat in ("std_reference", "std_warp"):
                                if not finite(score.get(stat)) or score[stat] < cfg["minimum_grayscale_std"]:
                                    reasons.append(source + ":LOW_OR_UNDEFINED_" + stat.upper())
                        usable = not reasons
                        all_eligible = all_eligible and usable
                        scale_details.append({"patch_size": size, "eligible": usable, "reasons": reasons,
                                              "common_count": row["common_count"], "common_fraction": fraction,
                                              "source_scores": {s: row[branch][s] for s in sources},
                                              "parent_fourway_eligibility": row["eligibility"]})
                    if all_eligible:
                        common_views.append(index)
                    eligibility.append({"index": index, "camera_id": neighbor["camera_id"],
                                        "eligible_all_scales": all_eligible, "scales": scale_details})
                medians = costs_on(case_id, pair, branch, common_views)
                available = medians is not None
                unit = {
                    "unit_id": f"{case_id}/{pair}/{branch}", "case_id": case_id,
                    "region": case["region"], "pair": pair, "branch": branch,
                    "reference_camera": case["ref_camera"], "center_uv": case["center_uv"],
                    "source_center_depths": {s: case["depths"].get(s) if finite(case["depths"].get(s)) else None for s in sources},
                    "source_target_valid": source_valid,
                    "status": "COMPARABLE_SAVED_COSTS_VISIBILITY_UNKNOWN" if available else "UNAVAILABLE_PAIRED_COST",
                    "camera_count": len(common_views), "camera_indices": common_views,
                    "camera_ids": [neighbor_by_index[i]["camera_id"] for i in common_views],
                    "medians_by_source_in_scale_order": medians,
                    "mean_cost_by_source": {s: statistics.mean(medians[s]) for s in sources} if available else None,
                    "eligibility_by_camera": eligibility,
                    "visibility_certified": False,
                    "actual_weight_map_computed": False,
                    "own_support_cost_used_for_pair": False,
                    "threshold_and_ratio_sensitivity": []
                }
                branch_units[branch] = unit
                for knots in cfg["threshold_triplets"]:
                    for ratio in cfg["coefficient_ratios_cI_over_cP"]:
                        for gate, gate_name in ((0, cfg["evidence_statuses"][0]), (1, cfg["evidence_statuses"][1])):
                            entries = None
                            weights = None
                            cP = 1.0 if source_valid[sources[0]] else 0.0
                            cI = float(ratio) if source_valid[sources[1]] else 0.0
                            if gate == 0 or available:
                                internal = {s: evidence(medians[s] if available else None, knots, gate) for s in sources}
                                entries = {s: internal[s] if source_valid[s] else None for s in sources}
                                if knots == [0.10, 0.30, 0.50]:
                                    for source in sources:
                                        observed = medians[source] if available else [None, None, None]
                                        actual = module.evidence_from_costs(observed, gate)
                                        expected = internal[source]
                                        assert np.allclose([float(x) for x in actual], [expected[k] for k in ("S", "R", "U")], rtol=0, atol=1e-12)
                                        checks["central_evidence_parity"] += 1
                                p, i = internal[sources[0]], internal[sources[1]]
                                wp, wi = module.weight_from_evidence(cP, cI, p["S"], p["R"], i["S"], i["R"])
                                wp, wi = float(wp), float(wi)
                                budget, strength = cP + cI, wp + wi
                                assert wp >= 0 and wi >= 0 and strength <= budget + 1e-10
                                checks["weight_budget_checks"] += 1
                                if gate == 0:
                                    assert math.isclose(wp, cP, abs_tol=1e-12) and wi == 0
                                    checks["unknown_gate_fallback_checks"] += 1
                                weights = {"cP": cP, "cI": cI, "B": budget, "wP": wp, "wI": wi,
                                           "q_image": wi / strength if strength > 0 else None,
                                           "s": strength, "s_over_B": strength / budget if budget > 0 else None,
                                           "prior_multiplier": wp / cP if cP > 0 else None,
                                           "image_multiplier": wi / cI if cI > 0 else None}
                            item = {"knots": knots, "nominal_cI_over_cP": ratio,
                                    "ratio_is_actual_run_ratio": False,
                                    "ratio_defined_for_this_target_pair": all(source_valid.values()),
                                    "status": gate_name if (gate == 0 or available) else "UNAVAILABLE_PAIRED_COST_NOT_ASSUMED_G1",
                                    "observation_gate": gate if (gate == 0 or available) else None,
                                    "evidence": entries, "dimensionless_coefficient_algebra": weights}
                            unit["threshold_and_ratio_sensitivity"].append(item)
                            flat = {"unit_id": unit["unit_id"], "case_id": case_id, "pair": pair, "branch": branch,
                                    "comparable": available, "camera_count": len(common_views),
                                    "camera_ids": "|".join(unit["camera_ids"]),
                                    "knots": "/".join(str(k) for k in knots), "nominal_cI_over_cP": ratio,
                                    "status": item["status"], "prior_target_valid": source_valid[sources[0]],
                                    "image_target_valid": source_valid[sources[1]],
                                    "g": item["observation_gate"]}
                            for source, prefix in zip(sources, ("P", "I")):
                                for idx, size in enumerate(cfg["patch_sizes"]):
                                    flat[f"E_{prefix}_{size}"] = medians[source][idx] if available else None
                                for key in ("S", "R", "U"):
                                    flat[f"{key}_{prefix}"] = entries[source][key] if entries and entries[source] else None
                            for key in ("cP", "cI", "B", "wP", "wI", "q_image", "s", "s_over_B", "prior_multiplier", "image_multiplier"):
                                flat[key] = weights[key] if weights else None
                            sensitivity.append(flat)
                units.append(unit)
            direct_members = sorted(set(branch_units["raw"]["camera_indices"]) & set(branch_units["plane"]["camera_indices"]))
            for branch in cfg["branches"]:
                branch_units[branch]["raw_plane_direct_comparison"] = {
                    "camera_ids": [neighbor_by_index[i]["camera_id"] for i in direct_members],
                    "camera_count": len(direct_members),
                    "lost_cameras_from_branch": len(branch_units[branch]["camera_indices"]) - len(direct_members),
                    "medians_by_source_in_scale_order": costs_on(case_id, pair, branch, direct_members)
                }
    assert len(units) == cfg["expected_comparison_units"]
    assert len(sensitivity) == len(units) * len(cfg["threshold_triplets"]) * len(cfg["coefficient_ratios_cI_over_cP"]) * 2
    for relative, expected in input_hashes.items():
        assert sha(root / relative) == expected
    for path, expected in frozen_provenance.items():
        assert sha(Path(path)) == expected
    available_units = sum(unit["medians_by_source_in_scale_order"] is not None for unit in units)
    result = {
        "task_id": cfg["task_id"], "scientific_verdict": None,
        "status": "PASS_SAVED_COST_REAGGREGATION_AND_ALGEBRA_ONLY",
        "scope": {
            "comparison_units": len(units), "comparable_units": available_units,
            "noncomparable_units": len(units) - available_units,
            "sensitivity_rows": len(sensitivity),
            "costs_recomputed_from_images": False, "reference_geometry_read": False,
            "new_visibility_evidence": False, "dense_weight_map": False,
            "actual_GS_loss_coefficients": False, "GS_update": False,
            "all_unknown_visibility_actual_g": 0,
            "coefficient_ratio_assumption": cfg["coefficient_interpretation"],
            "inherited_mask_limitation": cfg["inherited_mask_limitation"],
            "null_semantics": "undefined paired costs and hypothetical weights remain null; missing source is not a negative vote; CSV null serialized as literal null",
            "no_threshold_selection": True, "same_inspected_development_cases": True,
            "actual_g0_weights": "dimensionless algebra for unknown evidence; not a measured or executed weight map"
        },
        "units": units
    }
    write_json(out / "result.json", result)
    with (out / "sensitivity.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(sensitivity[0]))
        writer.writeheader()
        writer.writerows({k: "null" if v is None else v for k, v in row.items()} for row in sensitivity)
    unit_rows = []
    for unit in units:
        row = {key: unit[key] for key in ("unit_id", "case_id", "pair", "branch", "status", "camera_count")}
        row["camera_ids"] = "|".join(unit["camera_ids"])
        medians = unit["medians_by_source_in_scale_order"]
        for source, prefix in zip(cfg["pairs"][unit["pair"]], ("P", "I")):
            for idx, size in enumerate(cfg["patch_sizes"]):
                row[f"E_{prefix}_{size}"] = medians[source][idx] if medians else None
        unit_rows.append(row)
    with (out / "units.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(unit_rows[0]))
        writer.writeheader()
        writer.writerows({k: "null" if v is None else v for k, v in row.items()} for row in unit_rows)
    receipt = {
        "task_id": cfg["task_id"], "scientific_verdict": None,
        "status": result["status"], "started_utc": started,
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "config_frozen_before_replay": True,
        "commit": cfg["commit"], "container_image": cfg["image"], "resources": cfg["resources"],
        "python_version": sys.version, "numpy_version": np.__version__, "platform": platform.platform(),
        "input_sha256_verified_before_and_after": input_hashes,
        "code_and_config_sha256_verified_before_and_after": frozen_provenance,
        "outputs_sha256": {name: sha(out / name) for name in ("result.json", "sensitivity.csv", "units.csv")},
        "read_scope": "only frozen scores.json and eight cases/*/case.json plus code/config; no GT file read",
        "checks": checks, "scope": result["scope"]
    }
    write_json(out / "receipt.json", receipt)
    print(json.dumps({"status": receipt["status"], "output": str(out), "scope": result["scope"], "checks": checks}, ensure_ascii=False))


if __name__ == "__main__":
    main()
