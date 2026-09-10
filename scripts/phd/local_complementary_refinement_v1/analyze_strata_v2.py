"""Audit sealed raw512/0.5m source-proxy transition aggregates, without raw GT.

Consumes only three producer CSVs, the frozen config snapshot and producer
receipt. No geometry, cameras, source targets, parameters or training are read.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import sys
import time


THRESHOLD = .5
SOURCE_QUADRANTS = tuple("PRIOR_PROXIMITY_" + prior + "_IMAGE_TARGET_Z_" + visual
                         for prior in ("NEAR", "FAR") for visual in ("NEAR", "FAR"))
PRIMARY_COHORTS = ("ALL_REFERENCE", "STRICT_SUPPORT", "NO_STRICT_SUPPORT") + SOURCE_QUADRANTS
FILES = ("paired_transitions.csv", "anchor_global_local_transitions.csv", "coverage.csv", "config_snapshot.json")
LIMITATIONS = [
    "Counts are transitions of fixed observed reference-point proximity, not building counts, area, same-shape preservation or temporal truth.",
    "Prior NEAR means nearest-prior proximity <0.5m; strict DA3 NEAR means absolute median target world-Z residual <=0.5m. These unequal geometric proxies are not source correctness labels.",
    "Finite strict target support is inherited diagnostic support, not complete visibility, photograph O/X or independent DA3-only causal identification.",
    "The four source quadrants partition STRICT_SUPPORT only. NO_STRICT_SUPPORT stays separate and is not silently labeled target-FAR.",
    "Coarse source/error/spread and Anchor-conditioned cohorts overlap. Only explicitly audited partitions may be summed.",
    "Rates retain distinct denominators: correction/G-far, damage/G-near, and net proximity change/all cohort reference points. Their numerical sizes are not directly interchangeable.",
    "This CSV-only audit checks producer hashes and aggregate arithmetic; it does not independently recompute raw geometry, original reference membership or source residuals.",
    "Only completed conditions present in the sealed evaluation are assessed. No threshold tuning, independent repeats, spatial-allocation isolation, controller replay or population generalization is performed.",
]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def dump(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def csv_rows(data):
    reader = csv.DictReader(io.StringIO(data.decode("utf-8")))
    if len(reader.fieldnames or []) != len(set(reader.fieldnames or [])):
        raise ValueError("Duplicate CSV column names")
    return list(reader)


def unique_index(rows, columns):
    result = {}
    for row in rows:
        key = tuple(float(row[c]) if c == "threshold_m" else row[c] for c in columns)
        if key in result:
            raise ValueError("Duplicate analytical grain: " + str(key))
        result[key] = row
    return result


def integer_counts(row):
    result = {}
    for key, value in row.items():
        if key.endswith("_count"):
            parsed = int(value)
            if parsed < 0:
                raise ValueError("Negative count: " + key)
            result[key] = parsed
    return result


def ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def check_ratio(value, expected, name):
    if expected is None:
        if value not in (None, ""):
            raise ValueError("Non-null ratio with zero denominator: " + name)
    elif value in (None, "") or not math.isclose(float(value), expected, rel_tol=1e-12, abs_tol=1e-12):
        raise ValueError("Ratio denominator or value differs: " + name)


def validate_paired(row):
    c = integer_counts(row)
    n = c["reference_count"]
    near, far = c["comparator_near_count"], c["comparator_far_count"]
    corrected, damaged = c["corrected_count"], c["damaged_count"]
    retained, remaining = c["retained_near_count"], c["remaining_far_count"]
    if near + far != n or damaged + retained != near or corrected + remaining != far:
        raise ValueError("Paired transition counts do not partition the reference cohort")
    if c["unchanged_proximity_class_count"] != retained + remaining:
        raise ValueError("Unchanged proximity count differs")
    if c["closer_finite_count"] + c["farther_finite_count"] + c["equal_finite_distance_count"] != c["finite_pair_count"]:
        raise ValueError("Finite distance sign counts disagree")
    if c["finite_pair_count"] + c["became_missing_count"] + c["recovered_from_missing_count"] > n:
        raise ValueError("Finite/missing states exceed cohort count")
    for field, expected in (("corrected_fraction_of_comparator_far", ratio(corrected, far)),
                            ("damaged_fraction_of_comparator_near", ratio(damaged, near)),
                            ("preservation_fraction_of_comparator_near", ratio(retained, near)),
                            ("comparator_reference_recall", ratio(near, n)),
                            ("candidate_reference_recall", ratio(retained + corrected, n))):
        check_ratio(row[field], expected, field)
    return c


def validate_threeway(paired, threeway, anchor_to_global):
    p, t, g = integer_counts(paired), integer_counts(threeway), integer_counts(anchor_to_global)
    states = [t[f"anchor_global_local_near_{i:03b}_count"] for i in range(8)]
    if sum(states) != p["reference_count"] or t["reference_count"] != p["reference_count"]:
        raise ValueError("Three-way state counts do not exhaust the same cohort")
    checks = {
        "global_corrected_count": states[2] + states[3],
        "global_correction_retained_by_local_count": states[3],
        "global_correction_lost_by_local_count": states[2],
        "additional_local_correction_count": states[1],
        "global_damaged_count": states[4] + states[5],
        "global_damage_recovered_by_local_count": states[5],
        "global_damage_remaining_in_local_count": states[4],
        "additional_local_damage_count": states[6],
        "anchor_valid_retained_by_both_count": states[7],
        "anchor_far_remaining_far_in_both_count": states[0],
    }
    if any(t[key] != value for key, value in checks.items()):
        raise ValueError("Three-way named decomposition differs from eight states")
    if (p["corrected_count"], p["damaged_count"], p["retained_near_count"], p["remaining_far_count"]) != (
            states[1] + states[5], states[2] + states[6], states[3] + states[7], states[0] + states[4]):
        raise ValueError("Three-way states and G-to-LC paired transitions disagree")
    if (g["corrected_count"], g["damaged_count"], g["reference_count"]) != (
            t["global_corrected_count"], t["global_damaged_count"], t["reference_count"]):
        raise ValueError("Three-way baseline success/damage disagrees with Anchor-to-G paired rows")
    return t


def validate_partition(rows, total, children, count_fields):
    for field in count_fields:
        if sum(int(rows[child][field]) for child in children) != int(rows[total][field]):
            raise ValueError(f"Cohort partition mismatch: {total}/{field}")


def save_csv(path, rows):
    fields = sorted(set().union(*(r.keys() for r in rows)))
    with Path(path).open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def completed_conditions(threeway, producer, config):
    """Discover condition/region pairs without pretending missing rows completed."""
    conditions = sorted({key[:3] for key in threeway if key[3] == "raw" and key[5] == THRESHOLD})
    declared = {condition["id"]: condition["parent_condition"] for condition in config["conditions"]}
    if not conditions or len(conditions) != producer["run_count"]:
        raise ValueError("Completed condition count differs from producer receipt")
    for region, candidate, parent in conditions:
        if region not in producer["selected_regions"] or region not in config["regions"] or declared.get(candidate) != parent:
            raise ValueError("Unexpected region or condition/parent mapping")
    expected = len(config["regions"]) * len(declared)
    if producer["expected_full_run_count"] != expected:
        raise ValueError("Expected matrix size differs from frozen config")
    return conditions, "COMPLETE_MATRIX" if len(conditions) == expected else "PARTIAL_MATRIX"


def analyze(source, output):
    source, output = Path(source), Path(output)
    receipt_bytes = (source / "receipt.json").read_bytes()
    producer = json.loads(receipt_bytes)
    if (producer.get("schema") != "jbgs.local_complementary_evaluation.v2" or
            producer.get("scientific_verdict") is not None or producer.get("reference_used_for_training_or_parameter_selection") is not False):
        raise ValueError("Unexpected producer evaluation contract")
    declared = {row["path"]: row for row in producer["outputs"]}
    if len(declared) != len(producer["outputs"]):
        raise ValueError("Duplicate producer output paths")
    verified, inputs = {}, [{"path": "receipt.json", "bytes": len(receipt_bytes), "sha256": sha(receipt_bytes),
                            "hash_scope": "producer receipt snapshotted here; not an independent signature"}]
    for name in FILES:
        data = (source / name).read_bytes()
        if len(data) != declared[name]["bytes"] or sha(data) != declared[name]["sha256"]:
            raise ValueError("Sealed producer output bytes changed: " + name)
        verified[name] = data
        inputs.append({"path": name, "bytes": len(data), "sha256": sha(data), "producer_output_hash_verified": True})
    config = json.loads(verified["config_snapshot.json"])
    evaluation = config["evaluation"]
    if (evaluation["mesh_resolutions"] != [512] or evaluation["paired_primary_threshold_m"] != THRESHOLD
            or evaluation["source_stratum_threshold_m"] != THRESHOLD):
        raise ValueError("This bounded diagnostic requires raw512 and frozen 0.5m output/source thresholds")
    paired = unique_index(csv_rows(verified["paired_transitions.csv"]),
                          ("region", "candidate", "comparator", "mesh_kind", "cohort", "threshold_m"))
    threeway = unique_index(csv_rows(verified["anchor_global_local_transitions.csv"]),
                            ("region", "candidate", "parent_condition", "mesh_kind", "cohort", "threshold_m"))
    coverage = unique_index(csv_rows(verified["coverage.csv"]), ("region", "candidate", "mesh_kind"))
    conditions, matrix_status = completed_conditions(threeway, producer, config)
    all_rows, regional_counts, partition_checks = [], {}, []
    for region, candidate, parent in conditions:
        cohort_counts = regional_counts.setdefault(region, {})
        selected = {key[4]: row for key, row in paired.items()
                    if key[:4] == (region, candidate, parent, "raw") and key[5] == THRESHOLD}
        if not set(PRIMARY_COHORTS).issubset(selected):
            raise ValueError("Expected complete supported/unsupported source-proxy cohorts")
        for cohort, row in selected.items():
            p = validate_paired(row)
            anchor = paired[(region, parent, "ANCHOR", "raw", cohort, THRESHOLD)]
            validate_paired(anchor)
            trow = threeway[(region, candidate, parent, "raw", cohort, THRESHOLD)]
            t = validate_threeway(row, trow, anchor)
            if cohort in cohort_counts and cohort_counts[cohort] != p["reference_count"]:
                raise ValueError("Source cohort denominator changes between completed conditions")
            cohort_counts[cohort] = p["reference_count"]
            result = dict(row)
            result.update(t)
            result.update(matrix_status=matrix_status, scientific_verdict="null",
                support_class="STRICT_UNSUPPORTED" if cohort == "NO_STRICT_SUPPORT" else
                    "STRICT_SUPPORTED_SOURCE_QUADRANT" if cohort in SOURCE_QUADRANTS else "AGGREGATE_OR_OVERLAPPING_DIAGNOSTIC",
                disjoint_full_reference_partition_member=cohort in SOURCE_QUADRANTS or cohort == "NO_STRICT_SUPPORT",
                net_near_count_change=p["corrected_count"] - p["damaged_count"],
                net_reference_recall_change=ratio(p["corrected_count"] - p["damaged_count"], p["reference_count"]),
                corrected_per_reference=ratio(p["corrected_count"], p["reference_count"]),
                damaged_per_reference=ratio(p["damaged_count"], p["reference_count"]),
                global_correction_retained_fraction=ratio(t["global_correction_retained_by_local_count"], t["global_corrected_count"]),
                global_damage_recovered_fraction=ratio(t["global_damage_recovered_by_local_count"], t["global_damaged_count"]))
            all_rows.append(result)
        paired_counts = list(integer_counts(selected["ALL_REFERENCE"]))
        validate_partition(selected, "ALL_REFERENCE", ("STRICT_SUPPORT", "NO_STRICT_SUPPORT"), paired_counts)
        validate_partition(selected, "STRICT_SUPPORT", SOURCE_QUADRANTS, paired_counts)
        validate_partition(selected, "STRICT_TARGET_WITHIN_0.5M", (SOURCE_QUADRANTS[0], SOURCE_QUADRANTS[2]), paired_counts)
        for cohort in selected:
            children = (cohort + "__ANCHOR_NEAR_0.5M", cohort + "__ANCHOR_FAR_0.5M")
            if all(child in selected for child in children):
                validate_partition(selected, cohort, children, paired_counts)
        three_selected = {key[4]: row for key, row in threeway.items()
                          if key[:4] == (region, candidate, parent, "raw") and key[5] == THRESHOLD}
        three_counts = list(integer_counts(three_selected["ALL_REFERENCE"]))
        validate_partition(three_selected, "ALL_REFERENCE", ("STRICT_SUPPORT", "NO_STRICT_SUPPORT"), three_counts)
        validate_partition(three_selected, "STRICT_SUPPORT", SOURCE_QUADRANTS, three_counts)
        partition_checks.append({"region": region, "candidate": candidate, "paired_cohort_count": len(selected),
                                 "paired_and_threeway_exact_integer_partitions": "PASS",
                                 "near_far_rate_denominators": "PASS", "anchor_global_local_eight_state_identity": "PASS"})
    raw_coverage = [row for key, row in coverage.items() if key[0] in regional_counts and key[2] == "raw"]
    for row in raw_coverage:
        cohort_counts = regional_counts[row["region"]]
        if (int(row["reference_scored_count"]), int(row["strict_target_supported_reference_count"]),
            int(row["strict_target_unsupported_reference_count"])) != (
                cohort_counts["ALL_REFERENCE"], cohort_counts["STRICT_SUPPORT"], cohort_counts["NO_STRICT_SUPPORT"]):
            raise ValueError("Coverage and strata reference support counts disagree")
    for region, candidate, parent in conditions:
        for condition in (candidate, parent, "ANCHOR"):
            if (region, condition, "raw") not in coverage:
                raise ValueError("Missing matched raw coverage row")
    sources = output / "source_snapshots"
    sources.mkdir()
    (sources / "receipt.json").write_bytes(receipt_bytes)
    for name, data in verified.items():
        (sources / name).write_bytes(data)
    primary = [row for row in all_rows if row["cohort"] in PRIMARY_COHORTS]
    save_csv(output / "primary_source_strata.csv", primary)
    save_csv(output / "all_cohorts.csv", all_rows)
    save_csv(output / "cohort_counts.csv", [dict(region=region, cohort=k, reference_count=v,
        fraction_of_all_reference=v / cohort_counts["ALL_REFERENCE"],
        is_disjoint_full_partition=k in SOURCE_QUADRANTS or k == "NO_STRICT_SUPPORT")
        for region, cohort_counts in regional_counts.items() for k, v in cohort_counts.items()])
    save_csv(output / "coverage_scope.csv", raw_coverage)
    return dict(schema="JBGS_SOURCE_STRATA_DIAGNOSTIC_v2", status="PASS", matrix_status=matrix_status,
        scientific_verdict=None, raw_reference_accessed=False, gt_used_for_training_or_tuning=False,
        scope="Completed matched LC/G conditions in sealed evaluation; raw512; output proximity <0.5m; source proxy thresholds fixed",
        completed_conditions=[dict(region=r, candidate=c, parent_condition=p) for r, c, p in conditions],
        cohort_definitions={"prior_near": "nearest-prior proximity <0.5m", "strict_DA3_near": "finite strict median target world-Z error, absolute value <=0.5m",
                            "strict_unsupported": "nonfinite strict target diagnostic; source truth and raw photo O/X remain unclassified"},
        checks=partition_checks, full_cohort_counts=regional_counts, primary_rows=len(primary), all_cohort_rows=len(all_rows),
        raw_coverage_rows=len(raw_coverage), input_files=inputs, producer_status=producer["status"],
        producer_completed_run_count=producer["run_count"], producer_expected_run_count=producer["expected_full_run_count"],
        producer_implementation_metadata=producer.get("implementation_snapshots"),
        limitations=LIMITATIONS)


def main():
    if not Path("/.dockerenv").exists():
        raise RuntimeError("Project analysis requires Docker")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.resolve().is_relative_to(args.source.resolve()):
        raise ValueError("Diagnostic output must be separate from sealed producer output")
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    started = time.time()
    try:
        result = analyze(args.source, args.output)
        code = 0
    except Exception as error:
        result = dict(status="FAIL", exception_type=type(error).__name__, exception=str(error), scientific_verdict=None)
        code = 1
    result.update(started_unix=started, finished_unix=time.time(), script_sha256=sha(Path(__file__).read_bytes()),
                  python_version=sys.version, command=sys.argv)
    result["runtime"] = dict(runtime_image_id=os.environ.get("JBGS_RUNTIME_IMAGE_ID"), cpu_only=True,
        cgroup_cpu_max=Path("/sys/fs/cgroup/cpu.max").read_text().strip(),
        cgroup_memory_max=Path("/sys/fs/cgroup/memory.max").read_text().strip(),
        network="none", raw_gt_or_model_mounts=False)
    result["outputs"] = [{"path": p.name, "bytes": p.stat().st_size, "sha256": sha(p.read_bytes())}
                         for p in sorted(args.output.glob("*.csv"))]
    dump(args.output / "receipt.json", result)
    print(json.dumps({k: result[k] for k in ("status", "scientific_verdict")}, allow_nan=False))
    if code:
        print(result["exception"], file=sys.stderr)
    raise SystemExit(code)


if __name__ == "__main__":
    main()
