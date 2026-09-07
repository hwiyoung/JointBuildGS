"""Read-only comparison of original/recovery initialization and saved trace prefixes.

Run in Docker with both experiment roots read-only and a fresh audit output mount.
No checkpoint tensor is loaded; only small JSON, trace bytes, and initial PLY hashes.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import time


CONDITION = "SFM_noanchor_D005_Pnative"
INITIAL_FIELDS = (
    "source_kind", "contains_als_points", "point_count", "points_ply_sha256",
    "source_points3D_sha256", "region", "gaussian_xyz_matches_sfm_float32_order",
    "fresh_optimizer_state_entries", "iteration", "optimizer_steps",
    "pretrained_model_or_optimizer_loaded", "als_gaussians_inserted",
    "gaussian_count_before", "gaussian_count_after", "protection_applied_before_first_step",
    "protected_gaussians", "protected_fraction", "matching_only_prior_sha256",
    "matching_distance_m", "native_xyz_gradient_scale", "native_rotation_scale_gradient_scale",
    "lambda_lod_anchor", "training_entry_stage", "normal_activates_after_iteration",
    "densify_until_iteration_exclusive", "continued_resume_supported",
)
FIRST_FIELDS = ("iteration", "stage2_active", "anchor_iterations_executed", "pretrained_optimizer_loaded",
                "als_gaussians_inserted", "protected_gaussians", "optimizer_state_entries",
                "lod_weight", "da_weight", "normal_weight", "camera")
TRACE_EXACT_FIELDS = ("camera", "lod_weight", "da_weight", "gaussians", "protected")
LOSS_FIELDS = ("rgb_loss", "lod_loss", "da_loss")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def small_file(path, maximum=16 << 20):
    size = path.stat().st_size
    if size > maximum:
        raise ValueError(f"Read-only audit refuses unexpectedly large file: {path} ({size})")
    value = path.read_bytes()
    return value, dict(path=str(path), bytes=len(value), sha256=digest(value))


def read_json(path):
    data, source = small_file(path)
    return json.loads(data), source


def snapshot_trace(path):
    with path.open("rb") as stream:
        before = os.fstat(stream.fileno())
        if before.st_size > 16 << 20:
            raise ValueError("Trace exceeds this bounded audit's 16 MiB input cap")
        data = stream.read(before.st_size)
        after = os.fstat(stream.fileno())
    boundary = data.rfind(b"\n") + 1
    complete = data[:boundary]
    rows, raw = {}, {}
    previous = 0
    for line in complete.splitlines(keepends=True):
        row = json.loads(line)
        iteration = row["iteration"]
        if not isinstance(iteration, int) or iteration <= previous:
            raise ValueError("Trace has duplicate or non-increasing iteration membership")
        previous = iteration
        rows[iteration], raw[iteration] = row, line
    if not rows:
        raise ValueError("No complete trace rows were available at snapshot time")
    metadata = dict(path=str(path), inode=before.st_ino, size_at_open=before.st_size,
                    captured_bytes=len(data), captured_bytes_sha256=digest(data),
                    complete_bytes=boundary, ignored_incomplete_tail_bytes=len(data) - boundary,
                    observed_size_after_read=after.st_size, maximum_complete_iteration=max(rows),
                    scope="Fixed byte length at open; only newline-complete JSON rows; concurrent append allowed")
    return rows, raw, metadata


def field_comparison(left, right, fields):
    records = {key: dict(original=left[key], recovery=right[key], exact=left[key] == right[key]) for key in fields}
    return dict(all_exact=all(item["exact"] for item in records.values()), fields=records)


def numeric_difference(old, new):
    if not math.isfinite(old) or not math.isfinite(new):
        raise ValueError("Nonfinite numeric observation in trace audit")
    return dict(original=old, recovery=new, exact=old == new,
                signed_delta=new - old, absolute_delta=abs(new - old),
                symmetric_relative_delta=abs(new - old) / max(abs(old), abs(new), 1e-12))


def audit(original, recovery, out, regions, region_recovery=None):
    if not Path("/.dockerenv").is_file():
        raise RuntimeError("Docker is required")
    original, recovery = original.resolve(strict=True), recovery.resolve(strict=True)
    out.mkdir(parents=True, exist_ok=True)
    if (out / "receipt.json").exists():
        raise FileExistsError(out / "receipt.json")
    result = dict(schema="jointbuildgs.geogs.memory_recovery_prefix_audit.v1", status="RUNNING",
                  scientific_verdict=None, started_unix=time.time(), regions=[],
                  script_sha256=digest(Path(__file__).read_bytes()), training_executed=False,
                  gpu_accessed=False, checkpoint_tensors_loaded=False,
                  interpretation="Initialization and control audit of an observed prefix. Floating losses and Gaussian-count drift are recorded; no whole-trajectory bitwise or scientific-equivalence claim.",
                  numeric_relative_delta_denominator="max(abs(original), abs(recovery), 1e-12)")
    try:
        _, old_config = small_file(original / "config.json")
        _, new_config = small_file(recovery / "config.json")
        result["science_config"] = dict(original=old_config, recovery=new_config,
                                         bytes_equal=old_config["sha256"] == new_config["sha256"])
        for region in regions:
            if region not in ("P1", "P2", "P3"):
                raise ValueError("Unknown requested region")
            regional_recovery = (region_recovery or {}).get(region, recovery).resolve(strict=True)
            _, region_config = small_file(regional_recovery / "config.json")
            models = [root / "runs" / region / CONDITION / "model" for root in (original, regional_recovery)]
            initials, firsts, sources, ply, camera_files, traces = [], [], [], [], [], []
            for model in models:
                initial, initial_source = read_json(model / "jbgs_no_anchor/initialization.json")
                first, first_source = read_json(model / "jbgs_no_anchor/first_step.json")
                if initial["status"] != "PASS_PREOPTIMIZATION_PROTECTION" or first["status"] != "PASS_FIRST_STEP_DIRECT_REFINEMENT":
                    raise ValueError("Initial native protection or first refinement step has not passed")
                initials.append(initial)
                firsts.append(first)
                sources.append(dict(initialization=initial_source, first_step=first_source))
                initial_ply = model / "jbgs_no_anchor/iteration_0/point_cloud.ply"
                _, ply_metadata = small_file(initial_ply)
                ply.append(ply_metadata)
                _, camera_metadata = small_file(model / "cameras.json")
                camera_files.append(camera_metadata)
                traces.append(snapshot_trace(model / "jbgs_trace.jsonl"))
            end = min(max(traces[0][0]), max(traces[1][0])) // 100 * 100
            membership = [1] + list(range(100, end + 1, 100))
            for rows, _, _ in traces:
                if any(iteration not in rows for iteration in membership):
                    raise ValueError("A required row is missing inside the common 100-step trace prefix")
            prefix_sources = []
            for name, (_, raw, metadata) in zip(("original", "recovery"), traces):
                data = b"".join(raw[iteration] for iteration in membership)
                filename = f"{region}.{name}.trace_prefix.jsonl"
                with (out / filename).open("xb") as stream:
                    stream.write(data)
                prefix_sources.append(dict(**metadata, selected_prefix=filename,
                                           selected_prefix_sha256=digest(data), selected_prefix_bytes=len(data)))
            exact = {}
            for field in TRACE_EXACT_FIELDS:
                differences = [dict(iteration=i, original=traces[0][0][i][field], recovery=traces[1][0][i][field])
                               for i in membership if traces[0][0][i][field] != traces[1][0][i][field]]
                exact[field] = dict(matched_rows=len(membership) - len(differences), total_rows=len(membership),
                                    all_exact=not differences, differences=differences)
            losses = {}
            for field in LOSS_FIELDS:
                differences = [dict(iteration=i, **numeric_difference(traces[0][0][i][field], traces[1][0][i][field])) for i in membership]
                differing = [item for item in differences if not item["exact"]]
                losses[field] = dict(exact_rows=len(membership) - len(differing), total_rows=len(membership),
                    first_differing_iteration=differing[0]["iteration"] if differing else None,
                    max_absolute_delta=max(item["absolute_delta"] for item in differences),
                    mean_absolute_delta=sum(item["absolute_delta"] for item in differences) / len(differences),
                    max_symmetric_relative_delta=max(item["symmetric_relative_delta"] for item in differences),
                    observations=differences)
            item = dict(region=region, recovery_root=str(regional_recovery),
                        science_config=dict(original=old_config, recovery=region_config,
                                            bytes_equal=old_config["sha256"] == region_config["sha256"]),
                        initialization=field_comparison(*initials, INITIAL_FIELDS),
                        first_step_controls=field_comparison(*firsts, FIRST_FIELDS),
                        first_step_total_loss=numeric_difference(firsts[0]["total_loss"], firsts[1]["total_loss"]),
                        initialization_sources=sources, initial_step0_ply=dict(original=ply[0], recovery=ply[1],
                                                                             bytes_equal=ply[0]["sha256"] == ply[1]["sha256"]),
                        camera_definitions=dict(original=camera_files[0], recovery=camera_files[1],
                                                bytes_equal=camera_files[0]["sha256"] == camera_files[1]["sha256"]),
                        selected_iterations=membership, common_periodic_end=end, trace_sources=prefix_sources,
                        exact_trace_fields=exact, floating_loss_differences=losses)
            item["initialization_and_first_controls_exact"] = all((item["initialization"]["all_exact"],
                item["first_step_controls"]["all_exact"], item["initial_step0_ply"]["bytes_equal"],
                item["camera_definitions"]["bytes_equal"], item["science_config"]["bytes_equal"]))
            item["entire_observed_trace_numerically_equal"] = all(value["all_exact"] for value in exact.values()) and all(value["exact_rows"] == len(membership) for value in losses.values())
            result["regions"].append(item)
        controls_match = result["science_config"]["bytes_equal"] and all(item["initialization_and_first_controls_exact"] for item in result["regions"])
        prefix_equal = all(item["entire_observed_trace_numerically_equal"] for item in result["regions"])
        result.update(status=("PASS_INITIAL_CONTROL_AUDIT_PREFIX_EQUAL" if prefix_equal else "PASS_INITIAL_CONTROL_AUDIT_WITH_RECORDED_TRACE_DIFFERENCES") if controls_match else "INITIAL_CONTROL_MISMATCH_REQUIRES_REVIEW",
                      initialization_and_first_controls_exact=controls_match,
                      entire_observed_prefix_numerically_equal=prefix_equal,
                      original_and_recovery_inputs_modified=False)
    except Exception as error:
        result.update(status="FAIL_PREFIX_AUDIT", error_type=type(error).__name__, error=str(error))
        raise
    finally:
        result["completed_unix"] = time.time()
        with (out / "receipt.json").open("x") as stream:
            json.dump(result, stream, indent=2, allow_nan=False)
            stream.write("\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", type=Path, required=True)
    parser.add_argument("--recovery", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--regions", nargs="+", default=["P1", "P2"])
    parser.add_argument("--region-recovery", action="append", default=[], metavar="REGION=PATH")
    args = parser.parse_args()
    overrides = {}
    for specification in args.region_recovery:
        region, separator, path = specification.partition("=")
        if not separator or region not in ("P1", "P2", "P3") or not path or region in overrides:
            parser.error("Each region recovery override must be unique REGION=PATH")
        overrides[region] = Path(path)
    result = audit(args.original, args.recovery, args.out, args.regions, overrides)
    print(json.dumps(dict(status=result["status"], scientific_verdict=None,
        regions=[dict(region=row["region"], common_periodic_end=row["common_periodic_end"],
                      initial_controls_equal=row["initialization_and_first_controls_exact"],
                      prefix_equal=row["entire_observed_trace_numerically_equal"],
                      exact_trace_fields={k: {x: v[x] for x in ("matched_rows", "total_rows")} for k, v in row["exact_trace_fields"].items()},
                      loss_max_abs_delta={k: v["max_absolute_delta"] for k, v in row["floating_loss_differences"].items()}) for row in result["regions"]]), indent=2))
