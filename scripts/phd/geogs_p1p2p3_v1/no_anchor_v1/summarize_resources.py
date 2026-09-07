"""Summarize closed SfM/no-anchor resource records without mixing cost scopes.

Reads small producer receipts and traces, never checkpoints or geometry payloads.
Outputs are additive and must not exist. Partial/failed training is availability
information only; a failed export after successful training retains its cost row.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import re
import sys


SCHEMA = "jointbuildgs.geogs.no_anchor_resources.v1"
BASELINE_CONDITIONS = ("D005_Pnative", "D0005_Pnative")
BASELINE_PHASES = ("shared_anchor_prefix", "anchor_source_failed_attempt", "train", "training_trace")


def host_memory_error_observed(log):
    """Match CPU exception classes/tokens without matching CUDA OutOfMemoryError."""
    exception = re.search(
        r"(?m)^[ \t]*(?:[A-Za-z_]\w*\.)*(?:MemoryError|_ArrayMemoryError)(?::|[ \t]*$)", log)
    token = re.search(
        r"(?<![A-Za-z0-9_])(?:PINNED_HOST_BUDGET_EXCEEDED|std::bad_alloc)(?![A-Za-z0-9_])"
        r"|DefaultCPUAllocator: can't allocate memory", log)
    return exception is not None or token is not None


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def number(value, name):
    if isinstance(value, bool):
        raise ValueError(f"Boolean is not a resource measurement: {name}")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"Invalid nonnegative resource measurement: {name}")
    return result


def integer(value, name):
    result = number(value, name)
    if result != int(result):
        raise ValueError(f"Expected integer count: {name}")
    return int(result)


class Evidence:
    def __init__(self):
        self.sources = {}

    def read(self, path, expected=None):
        path = Path(path)
        raw = path.read_bytes()
        digest = sha_bytes(raw)
        if expected is not None and digest != expected:
            raise ValueError(f"Producer evidence hash mismatch: {path}")
        key = str(path)
        if key in self.sources and self.sources[key]["sha256"] != digest:
            raise ValueError(f"Evidence changed while summarizing: {path}")
        self.sources[key] = {"path": key, "bytes": len(raw), "sha256": digest}
        return raw.decode("utf-8")

    def json(self, path, expected=None):
        return json.loads(self.read(path, expected))

    def csv(self, path):
        return list(csv.DictReader(io.StringIO(self.read(path))))

    def record(self, path):
        return self.sources[str(Path(path))]


def task_path(task, relative):
    rel = Path(relative)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError("Baseline source must be contained task-relative evidence")
    return task / rel


def read_trace(evidence, path, expected=None):
    rows = [json.loads(line) for line in evidence.read(path, expected).splitlines() if line.strip()]
    iterations = [integer(row["iteration"], "iteration") for row in rows]
    elapsed = [number(row["elapsed_seconds"], "elapsed_seconds") for row in rows]
    if not rows or iterations != sorted(set(iterations)) or elapsed != sorted(elapsed):
        raise ValueError(f"Trace must have increasing unique steps and monotonic time: {path}")
    return rows, {row["iteration"]: row for row in rows}


def phase_row(evidence, path, receipt, region, condition, phase, iteration):
    source = evidence.record(path)
    return dict(region=region, condition=condition, phase=phase, iteration=iteration,
                status=receipt["status"], native_exit_code=receipt.get("native_exit_code"),
                validated_exit_code=receipt.get("validated_exit_code"),
                training_start_iteration=0 if phase == "train" else None,
                nominal_optimizer_updates=30000 if phase == "train" and receipt["status"] == "PASS" else None,
                wall_seconds=number(receipt["wall_seconds"], "wall_seconds"),
                child_peak_rss_bytes=integer(receipt["child_peak_rss_bytes"], "child_peak_rss_bytes"),
                resource_measurement_scope="no_anchor_driver_phase_v1",
                source_path=source["path"], source_sha256=source["sha256"], source_bytes=source["bytes"],
                scientific_verdict=None)


def validate_attempt_config(evidence, folder, cfg, expected_sha):
    """Memory-only recovery keeps the science configuration byte-identical."""
    path = folder / "config.json"
    actual = evidence.json(path, expected_sha)
    if actual != cfg:
        raise ValueError("Regional attempt changed the science configuration")


def final_retry_binding(evidence, task, selected, region):
    path=selected/"amendment.json"
    amendment=evidence.json(path) if path.is_file() else {}
    if "final_resource_retry" not in amendment and not selected.name.startswith("no_anchor_sfm_gradient_memory_v3_"):
        return None
    import importlib.util
    spec=importlib.util.spec_from_file_location("geogs_resource_final_retry",Path(__file__).with_name("final_retry.py"))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    def bind(source):
        relative=source.relative_to(task)
        if source.resolve()!=task.resolve()/relative:raise ValueError("Final retry evidence must remain a direct task file")
        evidence.read(source)
        row=evidence.record(source)
        return dict(path=str(relative),bytes=row["bytes"],sha256=row["sha256"])
    return module.bind_retry(task,selected,region,amendment,bind)


def new_records(evidence, experiment, cfg, region_experiments):
    availability, training, phases = [], [], []
    condition = cfg["condition_id"]
    config_sha = evidence.record(experiment / "config.json")["sha256"]
    for region in cfg["regions"]:
        selected_experiment = region_experiments.get(region, experiment)
        retry=final_retry_binding(evidence,experiment.parent,selected_experiment,region)
        retry_fields={} if retry is None else dict(final_retry_policy_sha256=retry["policy"]["sha256"],
            final_retry_predecessor=retry["predecessor_attempt_id"],final_retry_attempt_index=1,
            resource_recovery_version=3,storage_version=2)
        run = selected_experiment / "runs" / region / condition
        receipt_path = run / "receipt.json"
        identity = dict(region=region, selected_experiment=str(selected_experiment),
                        original_experiment=str(experiment), region_override=selected_experiment != experiment,**retry_fields)
        if not receipt_path.is_file():
            availability.append(dict(**identity, training_status="NOT_CLOSED_OR_NOT_STARTED",
                                     included=False, reason="No closed training receipt"))
            continue
        validate_attempt_config(evidence, selected_experiment, cfg, config_sha)
        receipt = evidence.json(receipt_path)
        if receipt.get("status") != "PASS":
            availability.append(dict(**identity, training_status=receipt.get("status", "UNKNOWN"),
                                     included=False, reason="Training did not pass; no training/geometry claim",
                                     training_receipt_path=str(receipt_path)))
            continue
        if receipt["region"] != region or receipt["condition_id"] != condition or receipt["phase"] != "train":
            raise ValueError("Completed training receipt identity differs")
        if receipt["config_sha256"] != config_sha or receipt["runtime_image_id"] != cfg["runtime_image_id"]:
            raise ValueError("Completed training configuration/runtime identity differs")
        sfm_path = selected_experiment / "inputs" / region / "initialization_manifest.json"
        if not sfm_path.is_file():
            # A memory-only runtime attempt reuses the same immutable SfM input.
            sfm_path = experiment / "inputs" / region / "initialization_manifest.json"
        sfm = evidence.json(sfm_path, receipt["sfm_manifest_sha256"])
        if sfm["source_kind"] != "image_sfm" or sfm["contains_als_points"] is not False:
            raise ValueError("Unexpected SfM initialization provenance")
        initial_path = run / "model/jbgs_no_anchor/initialization.json"
        initial = evidence.json(initial_path)
        first = evidence.json(run / "model/jbgs_no_anchor/first_step.json")
        if initial["status"] != "PASS_PREOPTIMIZATION_PROTECTION" or first["status"] != "PASS_FIRST_STEP_DIRECT_REFINEMENT":
            raise ValueError("Initialization/first-step audit did not pass")
        count = integer(sfm["point_count"], "initial_sfm_count")
        if count <= 0 or initial["gaussian_count_after"] != count or initial["gaussian_count_before"] != count:
            raise ValueError("Initialization Gaussian count changed")
        if initial["als_gaussians_inserted"] != 0 or first["anchor_iterations_executed"] != 0:
            raise ValueError("Training differs from fresh-SfM/no-anchor contract")
        trace_path = run / "model/jbgs_trace.jsonl"
        rows, trace = read_trace(evidence, trace_path)
        if rows[0]["iteration"] != 1 or rows[-1]["iteration"] != 30000 or any(n not in trace for n in (100, 22000)):
            raise ValueError("Completed trace lacks required boundaries")
        if trace[1]["gaussians"] != count or trace[1]["protected"] != initial["protected_gaussians"]:
            raise ValueError("First trace differs from initialization counts")
        for row in rows:
            if row["lod_weight"] != cfg["training"]["lambda_lod_anchor"] or row["da_weight"] <= 0:
                raise ValueError("Trace is not direct refinement throughout")
        info = dict(region=region, condition=condition, selected_experiment=str(selected_experiment),
                    **retry_fields,
                    original_experiment=str(experiment), training_start_iteration=0,
                    initial_sfm_gaussians=count, initial_protected_gaussians=initial["protected_gaussians"],
                    initial_protected_fraction=initial["protected_gaussians"] / count,
                    initial_protection_status=initial["protection_status"],
                    actual_anchor_updates=0, actual_total_optimizer_updates=30000,
                    resource_measurement_scope="training_process_trace_v1",
                    trace_path=str(trace_path), trace_sha256=evidence.record(trace_path)["sha256"],
                    initialization_audit_path=str(initial_path),
                    initialization_audit_sha256=evidence.record(initial_path)["sha256"],
                    scientific_verdict=None)
        for n in (22000, 30000):
            prefix = [row for row in rows if row["iteration"] <= n]
            info.update({f"process_to_{n}_trace_seconds": trace[n]["elapsed_seconds"],
                         f"gaussians_{n}": integer(trace[n]["gaussians"], "gaussians"),
                         f"protected_gaussians_{n}": integer(trace[n]["protected"], "protected"),
                         f"peak_cuda_allocated_through_{n}_bytes": max(integer(row["peak_cuda_allocated_bytes"], "cuda_allocated") for row in prefix),
                         f"peak_cuda_reserved_through_{n}_bytes": max(integer(row["peak_cuda_reserved_bytes"], "cuda_reserved") for row in prefix),
                         f"peak_self_rss_through_{n}_bytes": max(integer(row["peak_rss_bytes"], "self_rss") for row in prefix),
                         f"trace_1_to_{n}_seconds": trace[n]["elapsed_seconds"] - trace[1]["elapsed_seconds"],
                         f"trace_1_to_{n}_update_difference": n - 1,
                         f"trace_100_to_{n}_seconds": trace[n]["elapsed_seconds"] - trace[100]["elapsed_seconds"],
                         f"trace_100_to_{n}_update_difference": n - 100})
        training.append(info)
        phases.append(dict(phase_row(evidence, receipt_path, receipt, region, condition, "train", None),
                           selected_experiment=str(selected_experiment),**retry_fields))
        state = dict(**identity, training_status="PASS", included=True, reason="Closed training receipt and complete trace verified")
        for n in cfg["training"]["export_iterations"]:
            path = run / "exports" / f"iteration_{n}" / "receipt.json"
            if not path.is_file():
                state[f"export_{n}_status"] = "NOT_CLOSED_OR_NOT_STARTED"
                continue
            export = evidence.json(path)
            if (export["region"], export["condition_id"], export["phase"], export["iteration"]) != (region, condition, "export", n):
                raise ValueError("Export receipt identity differs")
            if export["config_sha256"] != config_sha or export["runtime_image_id"] != cfg["runtime_image_id"]:
                raise ValueError("Export configuration/runtime identity differs")
            state[f"export_{n}_status"] = export["status"]
            phases.append(dict(phase_row(evidence, path, export, region, condition, "export", n),
                               selected_experiment=str(selected_experiment),**retry_fields))
        availability.append(state)
    return availability, training, phases


def attempt_history(evidence, task, selected, region, condition):
    """Resolve explicitly sealed prior-attempt links, never discover other runs."""
    path = selected / "amendment.json"
    if not path.is_file():
        return []
    amendment = evidence.json(path)
    links = amendment.get("prior_resource_attempts", [])
    initialization_failure = amendment.get("prior_initialization_failure")
    final_retry=final_retry_binding(evidence,task,selected,region)
    if not isinstance(links, list):
        raise ValueError("prior_resource_attempts must be a list")
    if initialization_failure is not None and not isinstance(initialization_failure, dict):
        raise ValueError("prior_initialization_failure must be an object")
    if (links or initialization_failure is not None) and (amendment.get("region") != region or
                  amendment.get("arithmetic_or_scientific_controls_changed") is not False or
                  amendment.get("scientific_verdict") is not None):
        raise ValueError("Prior-attempt amendment identity/science controls differ")
    result = []
    records = [(link, "RESOURCE_ATTEMPT") for link in links]
    if initialization_failure is not None:
        records.append((initialization_failure, "INITIALIZATION_FAILURE"))
    if final_retry is not None:
        records.append((dict(receipt=final_retry["predecessor_training_receipt"]),"FINAL_RETRY_PREDECESSOR"))
    for link, kind in records:
        reference = link["receipt"]
        receipt_path = task_path(task, reference["path"])
        # Exactly one regional training producer per referenced experiment.
        folder = receipt_path.parents[3]
        if receipt_path != folder / "runs" / region / condition / "receipt.json":
            raise ValueError("Prior attempt is not this region's training receipt")
        producer = evidence.json(receipt_path, reference["sha256"])
        stop_path, stop = None, None
        if link.get("stop_intent") is not None:
            ref = link["stop_intent"]
            stop_path = task_path(task, ref["path"])
            if not stop_path.resolve().is_relative_to(folder.resolve()):
                raise ValueError("Stop intent is not inside the referenced attempt")
            stop = evidence.json(stop_path, ref["sha256"])
            if stop.get("region") != region:
                raise ValueError("Stop intent region differs")
        initialization_log_path, initialization_log_sha = None, None
        if kind == "INITIALIZATION_FAILURE":
            ref = link["log"]
            initialization_log_path = task_path(task, ref["path"])
            if initialization_log_path != receipt_path.parent / "native.log":
                raise ValueError("Initialization failure log differs from its training producer")
            log = evidence.read(initialization_log_path, ref["sha256"])
            initialization_log_sha = ref["sha256"]
            first = receipt_path.parent / "model/jbgs_no_anchor/first_step.json"
            if (link.get("cause") != "RESOURCE_SCHEDULING_ERROR" or producer.get("status") != "FAIL"
                    or producer.get("native_exit_code") != 1 or producer.get("region") != region
                    or producer.get("phase") != "train" or producer.get("condition_id") != condition
                    or producer.get("scientific_verdict") is not None
                    or "CUDA error: out of memory" not in log or first.exists() or first.is_symlink()):
                raise ValueError("Prior initialization failure does not match the sealed scheduling incident")
        result.append(dict(folder=folder, receipt_path=receipt_path, stop_path=stop_path,
                           stop=stop, history_amendment_path=str(path),
                           history_kind=kind, initialization_log_path=initialization_log_path,
                           cgroup_oom_kill=(kind=="FINAL_RETRY_PREDECESSOR" and final_retry.get("predecessor_resource_failure_classification")=="CGROUP_OOM_KILL"),
                           initialization_log_sha256=initialization_log_sha,
                           history_amendment_sha256=evidence.record(path)["sha256"]))
    return result


def closed_training_attempt_records(evidence, task, experiment, cfg, region_experiments):
    """Account for all explicit closed attempts; success is not a quality claim."""
    records = []
    config_sha = evidence.record(experiment / "config.json")["sha256"]
    for region in cfg["regions"]:
        selected = region_experiments.get(region, experiment)
        candidates = {folder: dict(folder=folder, stop=None, stop_path=None,
                                  history_amendment_path=None, history_amendment_sha256=None,
                                  history_kind=None, initialization_log_path=None,
                                  initialization_log_sha256=None)
                      for folder in dict.fromkeys((experiment, selected))}
        for linked in attempt_history(evidence, task, selected, region, cfg["condition_id"]):
            folder = linked["folder"]
            prior = candidates.get(folder)
            if prior and prior.get("stop") is not None and prior["stop"] != linked["stop"]:
                raise ValueError("Duplicate prior attempt has conflicting stop intents")
            if prior and prior.get("history_kind") and prior["history_kind"] != linked["history_kind"]:
                raise ValueError("One prior attempt cannot have conflicting history classifications")
            candidates[folder] = linked
        for folder, linked in candidates.items():
            run = folder / "runs" / region / cfg["condition_id"]
            path = run / "receipt.json"
            if not path.is_file():
                continue
            receipt = evidence.json(path)
            validate_attempt_config(evidence, folder, cfg, config_sha)
            if (receipt["region"], receipt["condition_id"], receipt["phase"]) != (region, cfg["condition_id"], "train"):
                raise ValueError("Closed training receipt identity differs")
            if receipt["config_sha256"] != config_sha:
                raise ValueError("Closed attempt configuration differs from its frozen file")
            stop, stop_path = linked["stop"], linked["stop_path"]
            if stop is None and (run / "stop_intent.json").is_file():
                stop_path = run / "stop_intent.json"
                stop = evidence.json(stop_path)
                if stop.get("region") != region:
                    raise ValueError("Local stop intent region differs")
            intended_cause = stop.get("cause") if stop else None
            intentional = (intended_cause == "RESOURCE_TRANSFER_OPTIMIZATION" and
                           receipt.get("native_exit_code") == -15 and receipt.get("status") != "PASS")
            native_log = run / "native.log"
            log = evidence.read(native_log) if receipt.get("status") != "PASS" and native_log.is_file() else None
            oom = log is not None and any(token in log for token in (
                "torch.cuda.OutOfMemoryError:", "CUDA out of memory", "CUDA error: out of memory")) and not intentional
            host_memory_failure=log is not None and host_memory_error_observed(log) and not intentional
            scheduling_failure = linked["history_kind"] == "INITIALIZATION_FAILURE"
            cgroup_oom=linked.get("cgroup_oom_kill",False)
            reason = ("RESOURCE_SCHEDULING_ERROR" if scheduling_failure else
                      "INTENTIONAL_RESOURCE_TRANSFER_REPLACEMENT" if intentional else
                      "CGROUP_OOM_KILL" if cgroup_oom else
                      "CUDA_OUT_OF_MEMORY" if oom else "HOST_MEMORY_RESOURCE_FAILURE" if host_memory_failure else "COMPLETED" if receipt.get("status") == "PASS" else
                      "UNCLASSIFIED_NONPASS_TERMINATION")
            item = dict(phase_row(evidence, path, receipt, region, cfg["condition_id"], "train", None),
                        attempt_experiment=str(folder), selected_for_region=folder == selected,
                        category=("PRIOR_INITIALIZATION_FAILURE" if scheduling_failure else
                                  "FINAL_RETRY_PREDECESSOR_FAILED_TRAINING" if linked["history_kind"]=="FINAL_RETRY_PREDECESSOR" else
                                  "INTENTIONALLY_REPLACED_RESOURCE_ATTEMPT" if intentional else
                                  "CLOSED_PRIOR_RESOURCE_ATTEMPT" if linked["history_amendment_path"] else
                                  "FAILED_ORIGINAL_TRAINING" if folder == experiment and receipt.get("status") != "PASS" else
                                  "FAILED_REGION_OVERRIDE_TRAINING" if receipt.get("status") != "PASS" else
                                  "CLOSED_TRAINING_ATTEMPT"),
                        termination_reason=reason, intentional_resource_replacement=intentional,
                        resource_scheduling_initialization_failure=scheduling_failure,
                        history_kind=linked["history_kind"],
                        cuda_oom_observed_in_log=oom, stop_intent_cause=intended_cause,
                        host_memory_failure_observed_in_log=host_memory_failure,
                        cgroup_oom_kill_verified=cgroup_oom,
                        counted_as_training_cuda_oom=oom and not scheduling_failure,
                        stop_intent_path=str(stop_path) if stop_path else None,
                        stop_intent_sha256=evidence.record(stop_path)["sha256"] if stop_path else None,
                        history_amendment_path=linked["history_amendment_path"],
                        history_amendment_sha256=linked["history_amendment_sha256"],
                        actual_optimizer_updates=None, last_recorded_trace_iteration=None,
                        minimum_completed_optimizer_updates=None, last_trace_process_elapsed_seconds=None,
                        last_recorded_gaussians=None, last_recorded_protected_gaussians=None,
                        failure_iteration_exactly_measured=False,
                        additive_to_selected_phase_work_seconds=True, calendar_wall_time_additive=False,
                        memory_peaks_additive=False, quality_evidence=False,
                        native_log_path=str(native_log), native_log_read=log is not None,
                        native_log_sha256=evidence.record(native_log)["sha256"] if log is not None else None)
            trace_path = run / "model/jbgs_trace.jsonl"
            if trace_path.is_file() and trace_path.stat().st_size:
                rows, _ = read_trace(evidence, trace_path)
                item.update(last_recorded_trace_iteration=rows[-1]["iteration"],
                            minimum_completed_optimizer_updates=rows[-1]["iteration"],
                            last_trace_process_elapsed_seconds=rows[-1]["elapsed_seconds"],
                            last_recorded_gaussians=integer(rows[-1]["gaussians"], "last_gaussians"),
                            last_recorded_protected_gaussians=integer(rows[-1]["protected"], "last_protected_gaussians"),
                            trace_path=str(trace_path), trace_sha256=evidence.record(trace_path)["sha256"],
                            peak_cuda_allocated_through_last_trace_bytes=max(integer(r["peak_cuda_allocated_bytes"], "cuda_allocated") for r in rows),
                            peak_cuda_reserved_through_last_trace_bytes=max(integer(r["peak_cuda_reserved_bytes"], "cuda_reserved") for r in rows))
            records.append(item)
    return records


def failed_training_records(evidence, experiment, cfg, region_experiments, task=None):
    """Compatibility accessor: non-PASS includes explicitly intentional stops."""
    return [row for row in closed_training_attempt_records(
        evidence, task or experiment.parent, experiment, cfg, region_experiments)
            if row["status"] != "PASS"]


def baseline_records(evidence, task, regions):
    source_rows = evidence.csv(task / "evaluation/summary/resource_summary.csv")
    selected = [row for row in source_rows if row["region"] in regions and
                row["condition"] in BASELINE_CONDITIONS and row["phase"] in BASELINE_PHASES]
    for row in selected:
        evidence.read(task_path(task, row["source_path"]), row["source_sha256"])
    intervals, failures = [], []
    for region in regions:
        anchors = [row for row in selected if row["region"] == region and row["phase"] == "shared_anchor_prefix"]
        if len(anchors) != 1:
            raise ValueError("Baseline requires one unambiguous shared anchor prefix")
        anchor = anchors[0]
        _, anchor_trace = read_trace(evidence, task_path(task, anchor["source_path"]), anchor["source_sha256"])
        anchor_elapsed = anchor_trace[8000]["elapsed_seconds"]
        if anchor_elapsed != float(anchor["anchor_prefix_elapsed_seconds"]):
            raise ValueError("Baseline anchor CSV differs from raw trace")
        for condition in BASELINE_CONDITIONS:
            matches = [row for row in selected if row["region"] == region and row["condition"] == condition and row["phase"] == "training_trace"]
            if len(matches) != 1:
                raise ValueError("Baseline requires one completed training trace per condition")
            row = matches[0]
            rows, trace = read_trace(evidence, task_path(task, row["source_path"]), row["source_sha256"])
            if rows[-1]["iteration"] != 30000 or 8100 not in trace:
                raise ValueError("Incomplete baseline trace")
            start = integer(row["training_start_iteration"], "baseline_start_iteration")
            if start not in (0, 8000):
                raise ValueError("Unsupported baseline start iteration")
            elapsed = trace[30000]["elapsed_seconds"]
            refinement = elapsed if start == 8000 else elapsed - trace[8000]["elapsed_seconds"]
            if elapsed != float(row["instrumented_process_elapsed_seconds"]) or refinement != float(row["post_anchor_instrumented_interval_seconds"]):
                raise ValueError("Baseline CSV interval differs from raw trace")
            intervals.append(dict(region=region, condition=condition, training_start_iteration=start,
                anchor_prefix_elapsed_seconds=anchor_elapsed,
                post_anchor_measured_interval_seconds=refinement,
                post_anchor_interval_scope=("PROCESS_IMPORT_RESTORE_TO_30000_TRACE" if start == 8000 else "TRACE_8000_TO_30000_INCLUDING_ANCHOR_SAVE"),
                anchor_plus_post_anchor_component_sum_seconds=anchor_elapsed + refinement,
                component_sum_scope=("MIXED_PROCESS_COMPONENT_SUM_NOT_FULL_30K" if start == 8000 else "CONTINUOUS_PROCESS_IMPORT_TO_30000_TRACE"),
                add_component_sum_to_driver_totals=False,
                process_import_to_last_trace_seconds=elapsed,
                trace_8100_to_30000_seconds=elapsed - trace[8100]["elapsed_seconds"],
                trace_update_difference=21900, paired_new_interval="trace_100_to_22000_seconds",
                isolated_optimizer_time=False, final_gaussians=trace[30000]["gaussians"],
                final_protected_gaussians=trace[30000]["protected"],
                anchor_trace_path=anchor["source_path"], anchor_trace_sha256=anchor["source_sha256"],
                final_trace_path=row["source_path"], final_trace_sha256=row["source_sha256"], scientific_verdict=None))
        for row in selected:
            if row["region"] == region and row["phase"] == "anchor_source_failed_attempt":
                failures.append(dict(region=region, condition=row["condition"], category="ANCHOR_SOURCE_FAILED_ATTEMPT_WITH_REUSED_ANCHOR",
                    wall_seconds=number(row["wall_seconds"], "failed_wall_seconds"), status=row["status"],
                    scope=row["resource_measurement_scope"], source_path=row["source_path"], source_sha256=row["source_sha256"],
                    additive_with_anchor_prefix=False, entirely_wasted_compute=False, scientific_verdict=None))
    repeat_path = task / "evaluation/summary/supplemental_repeat/failed_attempt_resources.csv"
    if repeat_path.is_file():
        for row in evidence.csv(repeat_path):
            if row["region"] in regions:
                path = row["original_failed_receipt_path"]
                digest = row["original_failed_receipt_sha256"]
                evidence.read(task_path(task, path), digest)
                failures.append(dict(region=row["region"], condition=row["condition"], category="FAILED_SUPPLEMENTAL_REPEAT",
                    wall_seconds=number(row["wall_seconds"], "failed_wall_seconds"), status=row["status"],
                    scope=row["resource_measurement_scope"], source_path=path, source_sha256=digest,
                    additive_with_anchor_prefix=False, entirely_wasted_compute=None, scientific_verdict=None))
    return selected, intervals, failures


def scope_metadata():
    return {
        "time_unit": "seconds", "memory_unit": "bytes", "scientific_verdict": None,
        "completed_region_policy": "Training receipt PASS and trace through30000 required. Other regions are availability only. Closed export FAIL after valid training retains its phase cost.",
        "regional_attempt_selection": "An explicit region-experiment override selects only that region's recovery output; other regions keep the original experiment. Science config bytes must match. Missing override receipt means pending, never a recovery success. SfM input may be reused from the original experiment only after the producer-recorded manifest SHA matches.",
        "new_failed_training_attempts": "Original, selected recovery, and SHA-bound prior attempts linked by the selected amendment are retained separately, including when no selected attempt has completed. The historical filename includes non-PASS intentional stops: cause RESOURCE_TRANSFER_OPTIMIZATION plus native exit -15 is an intentional replacement, not an OOM or quality failure. CUDA/host memory failure requires an observed error in the hashed native log; other terminations remain unclassified. A last100-step trace is a lower bound on completed optimizer updates, not the exact termination iteration. Distinct driver work seconds may be added; concurrent calendar duration and memory maxima may not. Trace times are already inside driver phases.",
        "new_prior_resource_attempts": "All explicitly SHA-bound earlier closed attempts from the selected amendment are indexed here, including a prior PASS if present. This is a provenance view of the same attempt records, not extra cost: deduplicate by source_path and source_sha256 before adding it to failed/selected tables. No quality claim is inferred from prior receipt status.",
        "prior_initialization_failure": "An explicit selected-amendment receipt/log pair with cause RESOURCE_SCHEDULING_ERROR binds a prior FAIL/native1 training producer, matching generic CUDA out-of-memory log and absent first-step audit. Keep this pre-first-step scheduling failure separate from ordinary training OOM and intentional replacement. Its work remains a distinct prior attempt; zero training quality is never inferred. This metadata is not inferred from an arbitrary CUDA error alone.",
        "final_resource_retry": "The frozen policy permits one fixed fresh resource-only retry after the exact selected predecessor's closed native resource failure and successful first step. Its policy, predecessor receipt/log/amendment and full earlier history are SHA-bound. Predecessor cost is kept once by source identity; the history table is not an additional cost. Selection remains the final attempt even if it fails, and historical fixed8k predecessor selection is unchanged.",
        "training_process_trace_v1": "Monotonic elapsed from jbgs_state import through the logged step; initialization/restore and earlier reporting/saves included; final after-trace complete-state capture/save excluded.",
        "no_anchor_driver_phase_v1": "Driver clock before native launch/log opening through polling and output validation. Input/config/source validation and invocation preparation excluded. Includes nvidia-smi polling and up to one polling interval of completion detection.",
        "old_regional_driver_phase_v1": "Old driver begins before invocation preparation and includes native execution/polling/output verification. Same broad phase family, not exactly identical clock boundaries to the new driver.",
        "child_peak_rss_bytes": "New driver RUSAGE_CHILDREN maximum over reaped child processes, including nvidia-smi; not process-tree sum, not GPU memory, not parent postprocess RSS.",
        "trace_memory_peaks": "Max of observed per-process PyTorch allocated/reserved peak counters and RUSAGE_SELF RSS through that trace. Not whole-GPU used memory; no phase reset or after-final-trace peak is inferred. Peaks cannot be added.",
        "anchor_prefix": "Import to step8000 trace before anchor complete-state capture; NOT measured whole-anchor cost.",
        "refinement_scope_difference": "Start0 baseline uses t30000-t8000 including anchor serialization. Resume8000 baseline uses process import through30000 including initialization/restore. Do not treat as identical scopes.",
        "component_sums": "Only P2/P3 D005 are continuous0-to30000. Other anchor+resume component sums omit anchor capture and include restore overhead; not full uninterrupted30k cost, not additive to driver totals.",
        "paired_21900_update_diagnostic": "New t22000-t100 and baseline t30000-t8100 each span21900 updates. Both include intervening reports/saves; baseline8100 capture and new22000 reporting schedules differ. Not isolated optimizer benchmarking.",
        "first_step_subtraction": "New t22000-t1 spans21999 updates; t30000-t1 spans29999. Use raw process elapsed for import-through22k/30k cost and preserve the explicit delta labels.",
        "new_training_initial_audit": "SFM counts and pre-step0 protection membership come from the validated initialization sidecar; Gaussian counts are representation/resource statistics, not final geometric accuracy.",
        "source_read_bound": "Only producer receipts, configuration, traces, stop-intent/amendment records and closed non-PASS native logs are read. Large checkpoint/mesh payload integrity is inherited from the completed producer receipt, not revalidated here.",
        "failed_costs": "P1 original failed phase contains the reused anchor prefix; summing both double counts. Supplemental failed repeats are separate actual attempts and never improve completed-run quality evidence.",
        "forbidden_sums": ["trace elapsed plus driver wall", "anchor prefix plus its original full failed phase", "component sum plus driver wall", "memory peaks across phases or runs"],
        "speed_interpretation": "Condition costs jointly reflect SfM initialization, omitted anchor, changed Gaussian population/fresh densification schedule and reporting/capture schedule; cannot attribute speed solely to anchor omission. GPU concurrency/background load are not normalized.",
        "export_comparison": "New exports use512. Original required final export uses1024; do not report these as equal-resolution rendering/extraction speed comparisons.",
    }


def write_csv(path, rows):
    columns = list(dict.fromkeys(key for row in rows for key in row)) or ["status"]
    with path.open("x", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def summarize(task, experiment, out, region_experiments=None):
    if not Path("/.dockerenv").is_file():
        raise RuntimeError("Docker-only resource summarization")
    task, experiment, out = Path(task).resolve(), Path(experiment).resolve(), Path(out).absolute()
    if out.exists() or out.is_symlink():
        raise FileExistsError(out)
    evidence = Evidence()
    cfg = evidence.json(experiment / "config.json")
    region_experiments = {name: Path(path).resolve() for name, path in (region_experiments or {}).items()}
    if set(region_experiments) - set(cfg["regions"]):
        raise ValueError("Region override is not present in the experiment plan")
    availability, training, phases = new_records(evidence, experiment, cfg, region_experiments)
    attempt_records = closed_training_attempt_records(evidence, task, experiment, cfg, region_experiments)
    new_failures = [row for row in attempt_records if row["status"] != "PASS"]
    prior_attempts = [row for row in attempt_records if row["history_amendment_path"]]
    initialization_failures = [row for row in attempt_records if row["resource_scheduling_initialization_failure"]]
    regions = [row["region"] for row in training]
    baseline, intervals, failures = baseline_records(evidence, task, regions)
    tables = {"region_availability": availability, "new_training": training,
              "new_phase_resources": phases, "baseline_resources": baseline,
              "baseline_training_intervals": intervals, "baseline_failed_attempt_resources": failures,
              "new_failed_training_attempts": new_failures,
              "new_prior_resource_attempts": prior_attempts,
              "new_prior_initialization_failures": initialization_failures,
              "new_final_retry_predecessors": [row for row in attempt_records if row["history_kind"]=="FINAL_RETRY_PREDECESSOR"]}
    result = dict(schema=SCHEMA, task_id=cfg["task_id"], scientific_verdict=None,
                  status="COMPLETED_REGIONS_SUMMARIZED" if regions else "NO_COMPLETED_TRAINING_REGIONS",
                  included_regions=regions, scope_metadata=scope_metadata(), tables=tables,
                  region_experiments={name: str(path) for name, path in region_experiments.items()},
                  sources=list(evidence.sources.values()), command=sys.argv,
                  summarizer_sha256=sha_bytes(Path(__file__).read_bytes()), python_version=sys.version)
    # Create output only after all selected source identities and arithmetic pass.
    out.mkdir(parents=True, exist_ok=False)
    for name, rows in tables.items():
        write_csv(out / (name + ".csv"), rows)
    (out / "summarize_resources_snapshot.py").write_bytes(Path(__file__).read_bytes())
    helper=Path(__file__).with_name("final_retry.py")
    if helper.is_file():
        (out / "final_retry.py").write_bytes(helper.read_bytes())
        result["helper_source_sha256"]={"final_retry.py":sha_bytes(helper.read_bytes())}
    result["output_csv_files"] = [{"path": name + ".csv", "bytes": (out / (name + ".csv")).stat().st_size,
                                   "sha256": sha_bytes((out / (name + ".csv")).read_bytes())} for name in tables]
    with (out / "summary.json").open("x") as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", type=Path, required=True)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--region-experiment", action="append", default=[], metavar="REGION=PATH",
                        help="Explicit memory-only recovery root for one region; repeat for other regions")
    args = parser.parse_args()
    overrides = {}
    for value in args.region_experiment:
        region, separator, path = value.partition("=")
        if not separator or not region or not path or region in overrides:
            parser.error("Each region-experiment must be a unique REGION=PATH")
        overrides[region] = path
    result = summarize(args.task, args.experiment, args.out, overrides)
    print(json.dumps({key: result[key] for key in ("status", "included_regions", "scientific_verdict")}))


if __name__ == "__main__":
    main()
