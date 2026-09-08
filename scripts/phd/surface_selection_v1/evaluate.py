"""Post-seal native-geometry discrepancy and matched-area selection evaluation.

This process cannot fit planes, change labels, select thresholds or run GS. The
reference adapter and immutable reference identities are the existing audited
source-candidate evaluator's exact exports. Currentness remains unassessed.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import time

import numpy as np

from scripts.phd.surface_selection_v1.common import verify_seal, sha, write, clean
from scripts.phd.source_candidate_v1.evaluate import (
    DEFAULT_THRESHOLDS, REFERENCE_SHAS, assess_selection, geometric_discrepancy,
    grouped_indices, load_reference_npz, points, verify_method_seal,
)
from src.phd.source_candidate_v1.geometry import cell_membership

SOURCES = ("mvs", "als")
ACTION_SOURCE = {"IMAGE": "mvs", "PRIOR": "als"}
EMPTY_IDS = np.empty(0, dtype=np.int64)
SELECTION_DEADBAND_M = .1


def verify_inputs_before_reference(run, baseline):
    """Every P1/P2/P3 method byte must verify before any reference file access."""
    config, seal, digest = verify_seal(run)
    if set(config["regions"]) != set(REFERENCE_SHAS) or seal.get("scientific_verdict") is not None:
        raise ValueError("All P1/P2/P3 reference-free methods must be frozen")
    old_config, _, old_digest = verify_method_seal(baseline)
    for region, spec in config["regions"].items():
        if spec["native_sha256"] != old_config["regions"][region]["native_sha256"]:
            raise ValueError("Legacy comparison native source bytes differ: " + region)
        if spec["domain"] != old_config["regions"][region]["domain"]:
            raise ValueError("Legacy comparison region domain differs: " + region)
    return config, digest, old_config, old_digest


def weighted_mean(rows, key):
    valid = [(float(row[key]), float(row["area_m2"])) for row in rows
             if row.get(key) is not None and np.isfinite(row[key])]
    area = sum(weight for _, weight in valid)
    return dict(mean=sum(value * weight for value, weight in valid) / area if area else None,
                assessed_area_m2=area, assessed_tiles=len(valid))


def summarize_tiles(rows):
    """Area weighting and all-domain denominators, never one vote per surface."""
    total = sum(row["area_m2"] for row in rows)
    paired = [r for r in rows if r["paired_eligible"] and r["mvs_error_m"] is not None
              and r["als_error_m"] is not None]
    accepted = [r for r in rows if r["action"] in ACTION_SOURCE]
    common = [r for r in paired if r["action"] in ACTION_SOURCE]
    clear = [r for r in common if r["selection_correct"] is not None]
    clear_area = sum(r["area_m2"] for r in clear)
    common_legacy = [r for r in rows if r.get("selected_error_m") is not None
                     and r.get("legacy_selected_error_m") is not None]
    conditional = [r for r in rows if r["conditional_action"] in ACTION_SOURCE]
    legacy = [r for r in rows if r["legacy_action"] in ACTION_SOURCE]
    def area(subset):
        return float(sum(r["area_m2"] for r in subset))
    def errors(subset, keys):
        return {key: weighted_mean(subset, key) for key in keys}
    return dict(total_tiles=len(rows), total_area_m2=total,
                reference_supported_area_m2=area([r for r in rows if r["reference_count"]]),
                directly_sampled_accepted_area_m2=area(accepted),
                directly_sampled_coverage=area(accepted) / total if total else None,
                conditional_whole_unit_area_m2=area(conditional),
                conditional_whole_unit_coverage=area(conditional) / total if total else None,
                legacy_accepted_area_m2=area(legacy), legacy_coverage=area(legacy) / total if total else None,
                abstain_or_unsampled_area_m2=total - area(accepted),
                paired_eligible_reference_area_m2=area(paired),
                accepted_paired_reference_area_m2=area(common),
                accepted_clear_gap_area_m2=clear_area,
                accepted_incorrect_clear_gap_area_m2=area([r for r in clear if not r["selection_correct"]]),
                accepted_accuracy_clear_gap_area_weighted=(
                    area([r for r in clear if r["selection_correct"]]) / clear_area if clear_area else None),
                accepted_singleton_area_m2=area([r for r in accepted if not r["paired_eligible"]]),
                action_area_m2={a: area([r for r in rows if r["action"] == a])
                                for a in ("IMAGE", "PRIOR", "ABSTAIN")},
                same_accepted_paired_tiles=errors(common, (
                    "mvs_error_m", "als_error_m", "selected_error_m", "oracle_error_m", "regret_m")),
                same_new_and_legacy_accepted_tiles=errors(common_legacy, (
                    "selected_error_m", "legacy_selected_error_m", "new_minus_legacy_error_m")),
                native_geometry_on_all_tiles=errors(rows, (
                    "mvs_raw_error_m", "als_raw_error_m", "mvs_error_m", "als_error_m")),
                weighting="Spatial tile area, including clipped boundary tiles; no equal-unit weighting",
                missing_denominator="All ROI tiles remain in coverage; absent reference is unassessed; no selected geometry is missing output",
                scientific_verdict=None)


def scope_tiles(unit, decision):
    action = decision["action"]
    if action not in (*ACTION_SOURCE, "ABSTAIN"):
        raise ValueError("Unknown frozen action")
    values = decision.get("accepted_scope", {}).get("tile_ids", [])
    ids = [int(value) for value in values]
    if len(ids) != len(set(ids)) or not set(ids) <= set(unit["tile_ids"]):
        raise ValueError("Accepted scope escapes or duplicates the frozen unit")
    if action == "ABSTAIN" and ids:
        raise ValueError("Abstention cannot contain accepted scope")
    if action in ACTION_SOURCE and not ids:
        raise ValueError("Selected unit requires explicit directly sampled scope")
    return set(ids)


def selection_record(mvs, als, action, paired, deadband=SELECTION_DEADBAND_M):
    record = assess_selection(mvs, als, action, deadband)
    if not paired:
        record.update(oracle_error_m=None, regret_m=None, source_gap_m=None,
                      selection_correct=None,
                      selection_evaluation_status=("SINGLE_SOURCE_NO_PAIRED_ORACLE"
                          if action in ACTION_SOURCE else "UNASSESSED_OR_ABSTAIN"))
    return record


def tile_layout(domain, spacing, shape):
    low = np.array([domain[k][0] for k in "xy"], dtype=float)
    high = np.array([domain[k][1] for k in "xy"], dtype=float)
    tids = np.arange(int(np.prod(shape)))
    ij = np.column_stack((tids % shape[0], tids // shape[0]))
    corner = low + ij * spacing
    opposite = np.minimum(corner + spacing, high)
    if np.any(opposite <= corner):
        raise ValueError("Tile grid escapes evaluation domain")
    return (corner + opposite) / 2, np.prod(opposite - corner, axis=1)


def _missing(metric, thresholds):
    values = metric.get("thresholds", [])
    return [r["reference_missing_count"] for r in values] if values else [0] * len(thresholds)


def evaluate_region(region, native, membership, components, units, decisions, reference, domain,
                    legacy_membership, legacy_decisions, legacy_cell_m=2., thresholds=DEFAULT_THRESHOLDS):
    """All array inputs are already verified by the caller; this is evaluation only."""
    reference = points(reference)
    spacing = float(membership["spacing"])
    if spacing <= 0 or abs(legacy_cell_m / spacing - round(legacy_cell_m / spacing)) > 1e-9:
        raise ValueError("Common tiles must exactly refine the legacy cell grid")
    shape = np.asarray(membership["shape"], dtype=int)
    tile_unit = np.asarray(membership["tile_unit"], dtype=int)
    expected_shape = np.ceil((np.array([domain[k][1] for k in "xy"])
                              - np.array([domain[k][0] for k in "xy"])) / spacing).astype(int)
    if not np.array_equal(shape, expected_shape) or len(tile_unit) != int(np.prod(shape)):
        raise ValueError("Frozen unit grid shape mismatch")
    if [u["id"] for u in units] != list(range(len(units))):
        raise ValueError("Unit identities must be contiguous and ordered")
    decision_map = {d["unit_id"]: d for d in decisions}
    if set(decision_map) != set(range(len(units))) or len(decision_map) != len(decisions):
        raise ValueError("Frozen unit decision identity mismatch")
    old_decision_map = {d["cell_id"]: d for d in legacy_decisions}
    scopes = {u["id"]: scope_tiles(u, decision_map[u["id"]]) for u in units}
    for unit in units:
        if not np.array_equal(np.flatnonzero(tile_unit == unit["id"]), np.asarray(sorted(unit["tile_ids"]))):
            raise ValueError("Frozen unit tile identity mismatch")
        source = ACTION_SOURCE.get(decision_map[unit["id"]]["action"])
        if source and len(unit[source + "_ids"]) != 1:
            raise ValueError("Frozen selection chose an ambiguous or absent source")
    centers, tile_areas = tile_layout(domain, spacing, shape)
    middle_z = sum(domain["z"]) / 2
    legacy_ids, _ = cell_membership(np.column_stack((centers, np.full(len(centers), middle_z))), domain, legacy_cell_m)
    if not set(legacy_ids) <= set(old_decision_map):
        raise ValueError("Legacy cell decisions do not cover the complete common domain")
    ref_tiles, _ = cell_membership(reference, domain, spacing)
    inside = ref_tiles >= 0
    outside_count = int((~inside).sum())
    reference, ref_tiles = reference[inside], ref_tiles[inside]
    ref_groups = grouped_indices(ref_tiles)
    native_xyz, native_tiles, native_groups, unit_groups = {}, {}, {}, {}
    selected_masks, conditional_masks, legacy_masks, segmented_unit_counts = {}, {}, {}, {}
    for source in SOURCES:
        xyz = native_xyz[source] = points(native[source + "_xyz"])
        ids, _ = cell_membership(xyz, domain, spacing)
        native_tiles[source] = ids
        if np.any(ids < 0):
            raise ValueError("Native source escaped exact evaluation prism")
        comp_ids = membership[source + "_component"]
        if comp_ids.shape != (len(xyz),) or membership[source + "_unit"].shape != (len(xyz),):
            raise ValueError("Native surface membership shape mismatch")
        if not np.array_equal(membership[source + "_unit"], tile_unit[ids]):
            raise ValueError("Native unit identity changed")
        if not set(np.unique(comp_ids)) <= {-1, *range(len(components[source]))}:
            raise ValueError("Native component identity changed")
        if len(legacy_membership[source + "_inlier"]) != len(xyz):
            raise ValueError("Legacy native membership count mismatch")
        if legacy_membership[source + "_inlier"].dtype != np.dtype(bool):
            raise ValueError("Legacy native inlier mask must retain boolean identity")
        old_ids, _ = cell_membership(xyz, domain, legacy_cell_m)
        if not np.array_equal(old_ids, legacy_membership[source + "_cell"]):
            raise ValueError("Legacy native point identity changed")
        native_groups[source] = grouped_indices(ids)
        unit_groups[source] = grouped_indices(tile_unit[ids])
        segmented_unit_counts[source] = np.bincount(tile_unit[ids[comp_ids >= 0]], minlength=len(units))
        selected_masks[source] = np.zeros(len(xyz), bool)
        conditional_masks[source] = np.zeros(len(xyz), bool)
        legacy_masks[source] = np.zeros(len(xyz), bool)
    rows = []
    completeness = {key: np.zeros(len(thresholds), dtype=np.int64)
                    for key in ("directly_sampled", "conditional_whole_unit", "legacy")}
    for tid, uid in enumerate(tile_unit):
        unit, decision = units[uid], decision_map[uid]
        actual_action = decision["action"] if tid in scopes[uid] else "ABSTAIN"
        conditional_action = decision["action"]
        old_action = old_decision_map[int(legacy_ids[tid])]["action"]
        if old_action not in (*ACTION_SOURCE, "ABSTAIN"):
            raise ValueError("Unknown legacy method action")
        ref = reference[ref_groups.get(tid, EMPTY_IDS)]
        eligible = {s: len(unit[s + "_ids"]) == 1 and components[s][unit[s + "_ids"][0]]["valid"]
                    and segmented_unit_counts[s][uid] >= 6
                    for s in SOURCES}
        row = dict(region=region, tile_id=tid, unit_id=int(uid), legacy_cell_id=int(legacy_ids[tid]),
                   x=float(centers[tid, 0]), y=float(centers[tid, 1]), area_m2=float(tile_areas[tid]),
                   unit_status=unit["status"], action=actual_action, conditional_action=conditional_action,
                   legacy_action=old_action, directly_sampled=tid in scopes[uid], reference_count=len(ref),
                   paired_eligible=bool(all(eligible.values())))
        metrics, old_metrics = {}, {}
        for source in SOURCES:
            ids = native_groups[source].get(tid, EMPTY_IDS)
            seg = ids[membership[source + "_component"][ids] >= 0]
            old = ids[legacy_membership[source + "_inlier"][ids]]
            raw_metric = geometric_discrepancy(native_xyz[source][ids], ref, thresholds)
            metric = metrics[source] = geometric_discrepancy(native_xyz[source][seg], ref, thresholds)
            old_metric = old_metrics[source] = geometric_discrepancy(native_xyz[source][old], ref, thresholds)
            row.update({source + "_native_count": len(ids), source + "_segmented_count": len(seg),
                        source + "_legacy_inlier_count": len(old), source + "_eligible": bool(eligible[source]),
                        source + "_raw_error_m": raw_metric["symmetric_mean_m"],
                        source + "_error_m": metric["symmetric_mean_m"],
                        source + "_legacy_error_m": old_metric["symmetric_mean_m"]})
            if ACTION_SOURCE.get(actual_action) == source:
                selected_masks[source][seg] = True
            if ACTION_SOURCE.get(conditional_action) == source:
                conditional_masks[source][seg] = True
            if ACTION_SOURCE.get(old_action) == source:
                legacy_masks[source][old] = True
        row.update(selection_record(row["mvs_error_m"], row["als_error_m"], actual_action, row["paired_eligible"]))
        old_source = ACTION_SOURCE.get(old_action)
        row["legacy_selected_error_m"] = row[old_source + "_legacy_error_m"] if old_source else None
        row["new_minus_legacy_error_m"] = (row["selected_error_m"] - row["legacy_selected_error_m"]
            if row["selected_error_m"] is not None and row["legacy_selected_error_m"] is not None else None)
        for name, action, source_metrics in (("directly_sampled", actual_action, metrics),
                ("conditional_whole_unit", conditional_action, metrics), ("legacy", old_action, old_metrics)):
            source = ACTION_SOURCE.get(action)
            completeness[name] += _missing(source_metrics[source], thresholds) if source else len(ref)
        rows.append(row)
    ref_unit_groups = grouped_indices(tile_unit[ref_tiles])
    unit_rows = []
    for unit in units:
        uid = unit["id"]
        local_rows = [rows[t] for t in unit["tile_ids"]]
        direct_rows = [r for r in local_rows if r["directly_sampled"]]
        decision = decision_map[uid]
        ref_ids = ref_unit_groups.get(uid, EMPTY_IDS)
        scopes_metrics = {}
        for scope_name, direct in (("directly_sampled_scope", True), ("conditional_unit_scope", False)):
            keep_ref = np.isin(ref_tiles[ref_ids], list(scopes[uid])) if direct else np.ones(len(ref_ids), bool)
            ref = reference[ref_ids[keep_ref]]
            scope_metric = dict(reference_count=len(ref), source_metrics={},
                area_m2=sum(r["area_m2"] for r in (direct_rows if direct else local_rows)),
                semantics=("DIRECTLY_SAMPLED_TILES_ONLY" if direct else "HYPOTHETICAL_WHOLE_UNIT_PROPAGATION_NOT_METHOD_OUTPUT"))
            for source in SOURCES:
                ids = unit_groups[source].get(uid, EMPTY_IDS)
                keep = membership[source + "_component"][ids] >= 0
                if direct:
                    keep &= np.isin(native_tiles[source][ids], list(scopes[uid]))
                metric = geometric_discrepancy(native_xyz[source][ids[keep]], ref, thresholds)
                scope_metric["source_metrics"][source] = metric
                scope_metric[source + "_error_m"] = metric["symmetric_mean_m"]
            scope_metric.update(selection_record(scope_metric["mvs_error_m"], scope_metric["als_error_m"],
                                                 decision["action"], local_rows[0]["paired_eligible"]))
            scopes_metrics[scope_name] = scope_metric
        direct = scopes_metrics["directly_sampled_scope"]
        unit_rows.append(dict(region=region, unit_id=uid, status=unit["status"], area_m2=unit["area_m2"],
            action=decision["action"], reason=decision["reason"], reference_count=sum(r["reference_count"] for r in local_rows),
            accepted_area_m2=sum(r["area_m2"] for r in direct_rows), accepted_tile_count=len(direct_rows),
            unsampled_or_abstain_area_m2=unit["area_m2"] - sum(r["area_m2"] for r in direct_rows),
            native_counts={s:sum(r[s + "_native_count"] for r in local_rows) for s in SOURCES},
            segmented_counts={s:sum(r[s + "_segmented_count"] for r in local_rows) for s in SOURCES},
            **{key:direct[key] for key in ("mvs_error_m", "als_error_m", "selected_error_m", "regret_m", "selection_correct")},
            **scopes_metrics))
    whole = {}
    for source in SOURCES:
        whole[source + "_whole_native"] = geometric_discrepancy(native_xyz[source], reference, thresholds)
        whole[source + "_segmented_native"] = geometric_discrepancy(
            native_xyz[source][membership[source + "_component"] >= 0], reference, thresholds)
    for name, masks in (("directly_sampled_selected_union", selected_masks),
                         ("conditional_whole_unit_selected_union", conditional_masks),
                         ("legacy_selected_union", legacy_masks)):
        xyz = np.concatenate([native_xyz[s][masks[s]] for s in SOURCES])
        whole[name] = geometric_discrepancy(xyz, reference, thresholds)
    summary = summarize_tiles(rows)
    summary.update(region=region, total_units=len(units),
        action_unit_counts=dict(Counter(d["action"] for d in decisions)),
        status_unit_counts=dict(Counter(u["status"] for u in units)),
        native_counts={s:len(native_xyz[s]) for s in SOURCES},
        segmented_native_counts={s:int((membership[s + "_component"] >= 0).sum()) for s in SOURCES},
        selected_native_counts={s:int(selected_masks[s].sum()) for s in SOURCES},
        reference_point_count=len(reference), reference_points_outside_fixed_prism=outside_count,
        whole_native_point_weighted_diagnostics=whole,
        tile_constrained_completeness={name:[dict(threshold_m=float(t), reference_count=len(reference),
            reference_missing_count=int(missing), recall=1 - int(missing) / len(reference) if len(reference) else None)
            for t, missing in zip(thresholds, values)] for name, values in completeness.items()})
    return unit_rows, rows, summary


def write_csv(path, rows):
    keys = list(dict.fromkeys(k for row in rows for k, value in row.items() if not isinstance(value, (dict, list))))
    with Path(path).open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=keys)
        writer.writeheader()
        writer.writerows({k:clean(row.get(k)) for k in keys} for row in rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True)
    parser.add_argument("--baseline", default="/baseline/run")
    args = parser.parse_args()
    if not Path("/.dockerenv").exists():
        raise RuntimeError("Evaluation requires Docker")
    started = time.monotonic()
    run, baseline = Path(args.run), Path(args.baseline)
    config, seal_sha, old_config, old_seal_sha = verify_inputs_before_reference(run, baseline)
    # No reference hash, stat, read or array access may precede the verified gates.
    output = run / "evaluation"
    output.mkdir(exist_ok=False)
    summaries, all_units, all_tiles, inputs = {}, [], [], {}
    for region, spec in config["regions"].items():
        native_path = Path("/inputs") / region / "native.npz"
        reference_path = Path("/reference") / region / "reference.npz"
        if sha(native_path) != spec["native_sha256"]:
            raise ValueError("Native bytes changed: " + region)
        if sha(reference_path) != REFERENCE_SHAS[region]:
            raise ValueError("Exact immutable UAS reference changed: " + region)
        with np.load(native_path, allow_pickle=False) as archive:
            native = {k:archive[k] for k in archive.files}
        reference = load_reference_npz(reference_path)
        with np.load(run / region / "membership.npz", allow_pickle=False) as archive:
            membership = {k:archive[k] for k in archive.files}
        with np.load(baseline / region / "membership.npz", allow_pickle=False) as archive:
            old_membership = {k:archive[k] for k in archive.files}
        read = lambda name: json.loads((run / region / name).read_text())
        old_decisions = json.loads((baseline / region / "decisions.json").read_text())
        unit_rows, tile_rows, summary = evaluate_region(region, native, membership, read("components.json"),
            read("units.json"), read("decisions.json"), reference, spec["domain"], old_membership,
            old_decisions, old_config["geometry"]["cell_m"])
        summaries[region] = summary
        all_units.extend(unit_rows)
        all_tiles.extend(tile_rows)
        inputs[region] = dict(native_sha256=spec["native_sha256"], reference_sha256=REFERENCE_SHAS[region],
            reference_path=str(reference_path), reference_array="uas_xyz", reference_membership_array="uas_raw_rows")
        print(json.dumps(dict(stage="surface_reference_evaluation", region=region,
            units=len(unit_rows), tiles=len(tile_rows), accepted_area_m2=summary["directly_sampled_accepted_area_m2"])), flush=True)
    _, after_sha, _, old_after_sha = verify_inputs_before_reference(run, baseline)
    if (after_sha, old_after_sha) != (seal_sha, old_seal_sha):
        raise ValueError("Method seal changed during evaluation")
    summary = dict(status="COMPLETED_NONCONFIRMATORY_SURFACE_REFERENCE_DISCREPANCY", scientific_verdict=None,
        method_seal_sha256=seal_sha, legacy_method_seal_sha256=old_seal_sha,
        evaluation_config=dict(selection_deadband_m=SELECTION_DEADBAND_M, completeness_thresholds_m=DEFAULT_THRESHOLDS,
            common_denominator="Frozen 0.5m XY tiles clipped to exact shared ROI; legacy2m actions projected spatially"),
        input_hashes=inputs, regions=summaries, pooled=summarize_tiles(all_tiles), wall_seconds=time.monotonic() - started,
        limitations=[
            "UAS datum/registration and temporal uncertainty remain: distances are numerical discrepancies, not calibrated geometry accuracy or currentness verdicts.",
            "Source normal/height segmentation is a geometric hypothesis; it does not establish roof semantics.",
            "Direct scope is the frozen set of sampled tiles; a supported patch does not prove every native point or every pixel in its tile.",
            "Whole-unit conditional metrics are hypothetical propagation diagnostics, not actual accepted geometry.",
            "Same-source candidate segmentation, observation rules and unit scale changed together; improvements cannot be attributed to unit size alone.",
            "Native density and holes affect NN errors. Missing predictions remain missing; absent reference is unassessed.",
            "Singleton units have no paired-source oracle. Ambiguous vertical overlap is retained explicitly, not silently resolved.",
            "No source labels, segmentation parameters, gravity, poses or GS were updated during evaluation.",
            "P1/P2/P3 are development cases, not an independent confirmatory population test."])
    write(output / "per_unit.json", all_units)
    write(output / "per_tile.json", all_tiles)
    write(output / "summary.json", summary)
    write_csv(output / "per_unit.csv", all_units)
    write_csv(output / "per_tile.csv", all_tiles)
    write(output / "evaluation_receipt.json", dict(scientific_verdict=None, method_seal_sha256=seal_sha,
        legacy_method_seal_sha256=old_seal_sha, reference_accessed_only_after_all_method_verification=True,
        method_and_legacy_files_reverified_after_evaluation=True,
        output_sha256={p.name:sha(p) for p in sorted(output.iterdir()) if p.is_file()}))


if __name__ == "__main__":
    main()
