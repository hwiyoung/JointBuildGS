"""Compare saved reference-to-triangle proximity states; never compute surfaces.

Docker example: python compare_reference_support.py --task /task --out /out
  --output-relative support_transitions_v1

All reference coordinates and original indices remain in their saved order.
These are evaluation-only proximity transitions, not temporal-validity labels.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import platform
import sys
import time

import numpy as np


THRESHOLDS = (0.1, 0.2, 0.25, 0.5, 1.0, 2.0)
REGIONS = ("P1", "P2", "P3")
BASELINES = ("D005_Pnative", "D0005_Pnative")
ITERATIONS = (22000, 30000)
KINDS = ("raw", "post")
STATES = ("retained_hit", "new_hit", "lost_hit", "still_missed")
PRIMARY = "sample0.1_reference0.1"
SCHEMA = "jointbuildgs.geogs.reference_support_transitions.v1"
INTERPRETATION = (
    "A hit means saved reference-to-triangle distance is strictly below the frozen threshold. "
    "Transitions concern proximity at the same observed reference points; they do not identify "
    "temporally valid assets, obsolete structures, or causes. Reference gaps remain unobserved. "
    "Evaluation only: never use these arrays to select training settings or update geometry."
)


def sha(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            value.update(block)
    return value.hexdigest()


def write_json(path, value):
    with Path(path).open("x") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def exact_array_equal(left, right):
    return (left.shape == right.shape and left.dtype.str == right.dtype.str
            and left.tobytes(order="C") == right.tobytes(order="C"))


def load_arrays(path):
    keys = ("reference_original_indices", "reference_points", "reference_to_triangle_distance")
    with np.load(path, allow_pickle=False) as archive:
        values = {key: archive[key] for key in keys}
    ids, xyz, distance = (values[key] for key in keys)
    if ids.ndim != 1 or ids.dtype.kind not in "iu" or (ids < 0).any() or len(np.unique(ids)) != len(ids):
        raise ValueError(f"Invalid or duplicate original reference indices: {path}")
    if xyz.shape != (len(ids), 3) or xyz.dtype.kind != "f" or not np.isfinite(xyz).all():
        raise ValueError(f"Invalid saved reference coordinates: {path}")
    if (distance.shape != (len(ids),) or distance.dtype.kind != "f"
            or np.isnan(distance).any() or (distance < 0).any()):
        raise ValueError(f"Invalid reference-to-triangle distances: {path}")
    # Positive infinity is the frozen reconstruction-failure convention.
    return values


def compare_arrays(baseline, candidate):
    for key in ("reference_original_indices", "reference_points"):
        if not exact_array_equal(baseline[key], candidate[key]):
            raise ValueError(f"Reference membership/order/dtype/bytes differ: {key}")
    old = baseline["reference_to_triangle_distance"]
    new = candidate["reference_to_triangle_distance"]
    count = len(old)
    codes = np.empty((len(THRESHOLDS), count), dtype=np.uint8)
    rows = []
    for index, threshold in enumerate(THRESHOLDS):
        old_hit, new_hit = old < threshold, new < threshold
        code = np.full(count, 3, dtype=np.uint8)
        code[old_hit & new_hit] = 0
        code[~old_hit & new_hit] = 1
        code[old_hit & ~new_hit] = 2
        codes[index] = code
        counts = np.bincount(code, minlength=4)
        if int(counts.sum()) != count:
            raise RuntimeError("Transition states do not partition the saved reference")
        row = dict(threshold_m=threshold, reference_point_count=count,
                   status="ASSESSED_REFERENCE_PROXIMITY" if count else "NOT_ASSESSED_REFERENCE_ABSENT")
        for state, number in zip(STATES, counts):
            row[state + "_count"] = int(number)
            row[state + "_fraction"] = int(number) / count if count else None
        row.update(baseline_recall=float(old_hit.mean()) if count else None,
                   new_recall=float(new_hit.mean()) if count else None,
                   net_hit_change_count=int(counts[1]) - int(counts[2]),
                   recall_delta=(int(counts[1]) - int(counts[2])) / count if count else None)
        rows.append(row)
    return codes, rows


def inspect_metrics(path, region, candidate, config):
    metrics = json.loads(path.read_text())
    if (metrics.get("scientific_verdict") is not None or metrics.get("region") != region
            or metrics.get("candidate") != candidate or metrics.get("mesh_res") != 512
            or metrics.get("crs") != config["crs"]):
        raise ValueError(f"Candidate identity/CRS/verdict metadata differ: {path}")
    if (tuple(row["threshold_m"] for row in metrics["thresholds"]) != THRESHOLDS
            or metrics["surface_sample_spacing_m"] != 0.1
            or metrics["reference_voxel_size_m"] != 0.1):
        raise ValueError(f"Frozen threshold or primary sampling metadata differ: {path}")
    return metrics


def check_recall(rows, metrics, field):
    for row, saved in zip(rows, metrics["thresholds"]):
        actual, expected = row[field], saved["recall"]
        if ((actual is None) != (expected is None)
                or actual is not None and not np.isclose(actual, expected, rtol=0, atol=1e-12)):
            raise ValueError("Saved distance arrays disagree with the adjacent recall metric")


def run(task, out, output_relative, availability_path=None, allow_partial=False):
    if not Path("/.dockerenv").is_file():
        raise RuntimeError("Docker is required")
    task, out = task.resolve(strict=True), out.resolve(strict=True)
    relative = Path(output_relative)
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise ValueError("Output must be a fresh relative descendant of --out")
    destination = (out / relative).resolve()
    if out not in destination.parents:
        raise ValueError("Output must remain inside --out")
    if destination.exists():
        raise FileExistsError(destination)
    destination.mkdir(parents=True, exist_ok=False)
    receipt = dict(schema=SCHEMA, status="RUNNING", scientific_verdict=None,
                   started_unix=time.time(), task=str(task), out=str(out), output=str(destination),
                   script_sha256=sha(__file__), python_version=platform.python_version(),
                   numpy_version=np.__version__, command=sys.argv,
                   thresholds_m=THRESHOLDS, threshold_operator="strictly_less_than",
                   status_codes=dict(enumerate(STATES)), fraction_denominator="all saved observed reference points",
                   distance_direction="observed reference point to candidate triangle surface",
                   evaluation_only=True, training_or_parameter_selection_allowed=False,
                   surfaces_computed=0, alignment_or_resampling_performed=False,
                   interpretation=INTERPRETATION, inputs=[], comparisons=[], outputs=[])
    try:
        availability = {}
        unavailable = {}
        receipt["unavailable_comparisons"] = []
        if allow_partial:
            if availability_path is None:
                raise ValueError("Partial comparisons require the explicit viewer availability manifest")
            availability_path = Path(availability_path).resolve(strict=True)
            if out not in availability_path.parents:
                raise ValueError("Availability must be a saved profile inside --out")
            value = json.loads(availability_path.read_text())
            if value.get("schema") != "GEOGS_NO_ANCHOR_AVAILABILITY_v1" or value.get("scientific_verdict") is not None:
                raise ValueError("Unexpected availability contract")
            availability = {(row["region"], row["candidate"]): row for row in value["entries"]}
            expected = {(region, f"SFM_noanchor_D005_Pnative_R{iteration}.mesh_512.{kind}")
                        for region in REGIONS for iteration in ITERATIONS for kind in KINDS}
            if set(availability) != expected or len(value["entries"]) != len(expected):
                raise ValueError("Availability must account for every region, budget and raw/post candidate")
            receipt["availability_manifest"] = dict(path=str(availability_path), sha256=sha(availability_path))
        elif availability_path is not None:
            raise ValueError("Use --allow-partial explicitly with an availability manifest")
        contract_path = task / "contracts/execution_v1.json"
        config = json.loads(contract_path.read_text())
        if (tuple(config["evaluation"]["thresholds_m"]) != THRESHOLDS
                or config["evaluation"]["surface_sample_spacing_m"] != 0.1
                or config["evaluation"]["reference_voxel_m"] != 0.1):
            raise ValueError("Execution contract no longer uses the frozen thresholds/sampling")
        receipt.update(execution_contract_sha256=sha(contract_path), crs=config["crs"],
                       reference_coordinates="unchanged saved scene-local metric XYZ; world_shift recorded in CRS; no transform applied")
        sources = {}
        for region in REGIONS:
            candidates = [(cid, task / "evaluation/geometry") for cid in BASELINES]
            candidates += [(f"SFM_noanchor_D005_Pnative_R{iteration}", out / "geometry") for iteration in ITERATIONS]
            for condition, source_root in candidates:
                for kind in KINDS:
                    cid = f"{condition}.mesh_512.{kind}"
                    array_path = source_root / region / cid / (PRIMARY + ".npz")
                    metric_path = array_path.with_suffix(".json")
                    declared = availability.get((region, cid))
                    if declared and declared.get("optimizer_updates") is None:
                        if array_path.exists() or metric_path.exists():
                            raise ValueError("Availability is stale or conflicts with partial metric files: " + cid)
                        if declared["status"] not in ("pending", "failed"):
                            raise ValueError("Missing output is neither explicit pending nor execution failure")
                        attempt = declared["execution_attempt"]
                        if declared["status"] == "failed":
                            failure = attempt["failure_receipt"]
                            path = task / failure["path"]
                            if (not path.resolve().is_relative_to(task) or sha(path) != failure["sha256"]
                                    or json.loads(path.read_text()).get("status") != "FAIL"):
                                raise ValueError("Declared producer failure evidence changed")
                        unavailable[region, cid] = declared
                        continue
                    metrics = inspect_metrics(metric_path, region, cid, config)
                    if declared and metrics.get("experiment_source_relative", "no_anchor_sfm_v1") != declared["execution_attempt"].get("experiment_source_relative", "no_anchor_sfm_v1"):
                        raise ValueError("Availability selects a different attempt than the metrics")
                    item = dict(region=region, candidate=cid, array_path=str(array_path),
                                array_sha256=sha(array_path), array_bytes=array_path.stat().st_size,
                                metrics_path=str(metric_path), metrics_sha256=sha(metric_path),
                                original_reference_sha256=metrics["reference_sha256"],
                                original_surface_sha256=metrics["source_sha256"])
                    sources[region, cid] = (item, metrics)
                    receipt["inputs"].append(item)
        all_rows = []
        for region in REGIONS:
            for baseline_id in BASELINES:
                for iteration in ITERATIONS:
                    new_id = f"SFM_noanchor_D005_Pnative_R{iteration}"
                    for kind in KINDS:
                        old_cid, new_cid = f"{baseline_id}.mesh_512.{kind}", f"{new_id}.mesh_512.{kind}"
                        old_source, old_metrics = sources[region, old_cid]
                        if (region, new_cid) in unavailable:
                            missing = unavailable[region, new_cid]
                            failure = missing["execution_attempt"].get("failure_receipt", {})
                            identity = dict(region=region, baseline_candidate=old_cid, new_candidate=new_cid,
                                new_iteration=iteration, surface_kind=kind, transition_array=None,
                                status=missing["quality_status"], failure_phase=missing.get("failure_phase"),
                                failure_kind=missing.get("failure_kind"), failure_receipt_sha256=failure.get("sha256"),
                                execution_attempt_id=missing["execution_attempt"]["execution_attempt_id"],
                                reference_point_count=None, baseline_recall=None, new_recall=None,
                                net_hit_change_count=None, recall_delta=None)
                            for threshold in THRESHOLDS:
                                row = dict(identity, threshold_m=threshold)
                                for state in STATES:
                                    row[state + "_count"] = None
                                    row[state + "_fraction"] = None
                                all_rows.append(row)
                            receipt["unavailable_comparisons"].append(dict(identity,
                                reason=missing["execution_attempt"].get("reason"),
                                execution_attempt=missing["execution_attempt"]))
                            continue
                        new_source, new_metrics = sources[region, new_cid]
                        for key in ("reference_sha256", "bounds_half_open", "reference_voxel_origin", "crs"):
                            if old_metrics[key] != new_metrics[key]:
                                raise ValueError(f"Original reference or evaluation domain differs: {key}")
                        old = load_arrays(old_source["array_path"])
                        new = load_arrays(new_source["array_path"])
                        codes, rows = compare_arrays(old, new)
                        check_recall(rows, old_metrics, "baseline_recall")
                        check_recall(rows, new_metrics, "new_recall")
                        comparison_id = f"{region}.{baseline_id}__to__{new_id}.{kind}"
                        filename = comparison_id + ".npz"
                        with (destination / filename).open("xb") as stream:
                            np.savez_compressed(stream,
                                reference_original_indices=old["reference_original_indices"],
                                reference_points=old["reference_points"],
                                baseline_reference_to_triangle_distance=old["reference_to_triangle_distance"],
                                new_reference_to_triangle_distance=new["reference_to_triangle_distance"],
                                thresholds_m=np.asarray(THRESHOLDS, dtype=np.float64), status_codes=codes,
                                status_code_names=np.asarray(STATES), region=np.asarray(region),
                                baseline_candidate_id=np.asarray(old_cid), new_candidate_id=np.asarray(new_cid),
                                schema=np.asarray(SCHEMA), evaluation_only=np.asarray(True))
                        for row in rows:
                            all_rows.append(dict(region=region, baseline_candidate=old_cid, new_candidate=new_cid,
                                                 new_iteration=iteration, surface_kind=kind,
                                                 execution_attempt_id=new_metrics.get("execution_attempt_id", "no_anchor_sfm_v1"),
                                                 transition_array=filename, **row))
                        descriptor = dict(comparison_id=comparison_id, region=region, baseline_candidate=old_cid,
                            new_candidate=new_cid, surface_kind=kind, reference_point_count=len(old["reference_points"]),
                            execution_attempt={key: new_metrics[key] for key in (
                                "experiment_source_relative", "execution_attempt_id", "resource_recovery_applied",
                                "memory_recovery_amendment_path", "memory_recovery_amendment_sha256") if key in new_metrics},
                            original_indices_and_reference_xyz_byte_equal=True,
                            reference_array_dtypes={key: old[key].dtype.str for key in ("reference_original_indices", "reference_points")},
                            reference_array_sha256={key: hashlib.sha256(old[key].tobytes(order="C")).hexdigest()
                                                    for key in ("reference_original_indices", "reference_points")},
                            baseline_array_sha256=old_source["array_sha256"], new_array_sha256=new_source["array_sha256"],
                            positive_infinite_distance_counts=dict(baseline=int(np.isposinf(old["reference_to_triangle_distance"]).sum()),
                                                                  new=int(np.isposinf(new["reference_to_triangle_distance"]).sum())))
                        receipt["comparisons"].append(descriptor)
                        receipt["outputs"].append(dict(path=filename, sha256=sha(destination / filename)))
                        del old, new, codes
        actual_count = len(receipt["comparisons"])
        missing_count = len(receipt["unavailable_comparisons"])
        if actual_count + missing_count != 24 or len(all_rows) != 144:
            raise RuntimeError("The required 24-comparison / six-threshold availability matrix is incomplete")
        csv_path = destination / "support_transitions.csv"
        with csv_path.open("x", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(dict.fromkeys(key for row in all_rows for key in row)))
            writer.writeheader()
            writer.writerows(all_rows)
        receipt["outputs"].append(dict(path=csv_path.name, sha256=sha(csv_path), rows=len(all_rows)))
        for item in receipt["inputs"]:
            if sha(item["array_path"]) != item["array_sha256"] or sha(item["metrics_path"]) != item["metrics_sha256"]:
                raise RuntimeError("An evaluation source changed during comparison")
        if sha(contract_path) != receipt["execution_contract_sha256"]:
            raise RuntimeError("Execution contract changed during comparison")
        if allow_partial and sha(availability_path) != receipt["availability_manifest"]["sha256"]:
            raise RuntimeError("Availability changed during comparison")
        receipt.update(status="PARTIAL_REFERENCE_PROXIMITY_TRANSITIONS" if missing_count else "PASS_REFERENCE_PROXIMITY_TRANSITIONS",
                       comparison_count=actual_count, unavailable_comparison_count=missing_count,
                       threshold_rows=144, assessed_threshold_rows=actual_count * len(THRESHOLDS),
                       unavailable_threshold_rows=missing_count * len(THRESHOLDS), source_files_unchanged=True)
    except Exception as error:
        receipt.update(status="FAIL_REFERENCE_PROXIMITY_TRANSITIONS", error_type=type(error).__name__, error=str(error))
        raise
    finally:
        receipt["completed_unix"] = time.time()
        write_json(destination / "receipt.json", receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--output-relative", default="support_transitions_v1")
    parser.add_argument("--allow-partial", action="store_true",
                        help="Account for documented unavailable outputs with null metrics; requires availability manifest")
    parser.add_argument("--availability-manifest", type=Path)
    args = parser.parse_args()
    result = run(args.task, args.out, args.output_relative, args.availability_manifest, args.allow_partial)
    print(json.dumps({key: result[key] for key in ("status", "comparison_count", "threshold_rows", "output", "scientific_verdict")}, indent=2))


if __name__ == "__main__":
    main()
