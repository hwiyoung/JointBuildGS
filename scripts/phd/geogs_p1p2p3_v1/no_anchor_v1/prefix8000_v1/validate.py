#!/usr/bin/env python3
"""Validate a closed selected 8k prefix, without executing or resuming training."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
import traceback

import common as c


def identity(region):
    source, trained, sfm_input, original_input = map(Path, ("/source", "/trained", "/sfm_input", "/input"))
    cfg, base = c.read("/config.json"), c.read("/base_config.json")
    c.require(c.sha("/base_config.json") == cfg["base_config_sha256"], "Base config changed")
    c.require(cfg["condition_id"] == c.CONDITION and cfg["seed"] == 0 and cfg["runtime_image_id"] == c.IMAGE,
              "Experiment identity differs")
    c.require(c.sha(trained / "config_snapshot.json") == c.sha("/config.json"), "Saved training config changed")
    parent = c.closed_receipt(trained / "receipt.json", region, "train")
    invocation = c.read(trained / "invocation.json")
    c.require(all(parent.get(k) == v for k, v in invocation.items()), "Closed receipt changed its original invocation")
    c.require(parent["config_sha256"] == c.sha("/config.json") and parent["runtime_image_id"] == c.IMAGE
              and parent.get("reference_accessed") is False, "Parent execution identity differs")
    sfm, sealed = c.read(sfm_input / "initialization_manifest.json"), c.read(original_input / "input_manifest.json")
    c.require(sfm["region"] == region and sfm["source_kind"] == "image_sfm" and sfm["contains_als_points"] is False,
              "Fresh SfM input identity differs")
    c.require(sfm["source_points3D_sha256"] == cfg["initialization"]["points3D_sha256"], "SfM source changed")
    c.require(parent["sfm_manifest_sha256"] == c.sha(sfm_input / "initialization_manifest.json")
              and parent["original_input_manifest_sha256"] == c.sha(original_input / "input_manifest.json"),
              "Parent input seals changed")
    c.require(sealed["region"] == region and sealed["config_sha256"] == cfg["base_config_sha256"], "Original input identity differs")
    for item in sealed["files"]:
        c.require(c.sha(original_input / c.relative(item["path"])) == item["sha256"], "Original input file changed: " + item["path"])
    c.require(c.sha(sfm_input / c.relative(sfm["points_ply_path"])) == sfm["points_ply_sha256"], "SfM PLY changed")
    for name in ("cameras.bin", "images.bin"):
        c.require(c.sha(sfm_input / "scene/sparse/0" / name) == c.sha(original_input / "scene/sparse/0" / name), "Camera bytes differ")
    for name in ("jbgs_calibration.json", "scene_reference_frame.json"):
        c.require(c.sha(sfm_input / "scene" / name) == c.sha(original_input / "scene" / name), "Calibration changed")
    runtime = c.read(source / "jbgs_no_anchor_runtime_receipt.json")
    amendment = c.read("/amendment.json")
    memory = c.read(source / "jbgs_memory_recovery_receipt.json")
    c.require(runtime["status"] == "PASS_RUNTIME_PREPARED_NO_TRAINING"
              and memory["status"] == "PASS_MEMORY_RECOVERY_RUNTIME_PREPARED"
              and memory["science_config_unchanged"] is True and memory["scientific_verdict"] is None,
              "Prepared runtime has not passed")
    c.require(memory["parent_runtime_receipt_sha256"] == c.sha(source / "jbgs_no_anchor_runtime_receipt.json")
              and memory["original_source_python_sha256"] == runtime["destination_python_sha256"], "Runtime lineage changed")
    c.require(amendment["attempt_id"] == c.SELECTED[region] and amendment["scientific_verdict"] is None
              and amendment["arithmetic_or_scientific_controls_changed"] is False
              and amendment["original_config_sha256"] == c.sha("/config.json")
              and amendment["runtime_receipt_sha256"] == c.sha(source / "jbgs_memory_recovery_receipt.json"), "Recovery amendment differs")
    c.require(parent["memory_recovery_amendment_sha256"] == c.sha("/amendment.json")
              and c.sha(trained / "memory_recovery_amendment_snapshot.json") == c.sha("/amendment.json"), "Parent amendment binding changed")
    mapping = c.source_maps(source)
    c.require(mapping == memory["destination_python_sha256"] == amendment["prepared_source_python_sha256"], "Runtime source membership/hash changed")
    c.require(c.method_source_map(mapping) == invocation["source_sha256"], "Invocation source differs")
    order = c.assert_save_order(source)
    initial = c.read(trained / "model/jbgs_no_anchor/initialization.json")
    first = c.read(trained / "model/jbgs_no_anchor/first_step.json")
    c.require(initial["status"] == "PASS_PREOPTIMIZATION_PROTECTION" and initial["scientific_verdict"] is None
              and initial["iteration"] == 0 and initial["optimizer_steps"] == 0
              and initial["pretrained_model_or_optimizer_loaded"] is False and initial["als_gaussians_inserted"] == 0
              and initial["gaussian_count_before"] == initial["gaussian_count_after"] == sfm["point_count"]
              and initial["points_ply_sha256"] == sfm["points_ply_sha256"]
              and initial["protection_applied_before_first_step"] is True, "Initial controls did not pass")
    c.require(first["status"] == "PASS_FIRST_STEP_DIRECT_REFINEMENT" and first["scientific_verdict"] is None
              and first["iteration"] == 1 and first["stage2_active"] is True
              and first["anchor_iterations_executed"] == 0 and first["pretrained_optimizer_loaded"] is False
              and first["als_gaussians_inserted"] == 0 and first["optimizer_state_entries"] == 6
              and first["lod_weight"] == .005 and first["da_weight"] == .05
              and first["protected_gaussians"] == initial["protected_gaussians"], "First-step controls did not pass")
    return dict(cfg=cfg, base=base, parent=parent, invocation=invocation, source_map=mapping,
                sfm=sfm, initial=initial, first=first, save_order=order)


def trace_prefix(path, expected_n, protected):
    rows, prefix = [], []
    previous = 0
    with path.open("rb") as stream:
        for line in stream:
            c.require(line.endswith(b"\n"), "Prefix contains an incomplete trace line")
            row = json.loads(line)
            c.require(type(row["iteration"]) is int and row["iteration"] > previous, "Non-monotonic/duplicate trace iteration")
            previous = row["iteration"]
            if row["iteration"] > c.PREFIX:
                break
            c.check_finite_numbers(row)
            c.require(row["lod_weight"] == .005 and row["da_weight"] > 0 and row["protected"] == protected,
                      "Prefix refinement/protection changed")
            rows.append(row)
            prefix.append(line)
            if row["iteration"] == c.PREFIX:
                # A later failed step or incomplete last trace write does not
                # invalidate this already complete, fixed prefix. The full
                # closed trace remains hash-bound as original evidence.
                break
    c.require([row["iteration"] for row in rows] == [1, *range(100, 8001, 100)], "Incomplete frozen 8k trace membership")
    c.require(rows[-1]["gaussians"] == expected_n, "8k trace count differs from checkpoint")
    return b"".join(prefix), rows


def validate_checkpoint(checkpoint, ply_path, capture, expected, trace_row):
    import numpy as np
    import torch
    from plyfile import PlyData
    # mmap prevents eagerly duplicating multi-GB checkpoint storages. All
    # floating values are checked in bounded chunks; no GPU is requested.
    state = torch.load(str(checkpoint), map_location="cpu", mmap=True)
    c.require(isinstance(state, dict) and state.get("schema") == "JBGS_GEOGS_COMPLETE_STATE_v1"
              and state.get("iteration") == 8000 and state.get("scientific_verdict") is None,
              "Complete checkpoint schema/iteration/verdict differs")
    c.require(state["source_sha256"] == c.TRAIN_SHA
              and state["implementation_hashes"] == c.method_source_map(expected["source_map"])
              and state["input_manifest_sha256"] == expected["parent"]["sfm_manifest_sha256"], "Checkpoint lineage differs")
    args, opt = state["args"], state["optimization"]
    for field, value in dict(iterations=30000, stage_switch_iter=0, lambda_lod_anchor=.005,
                             lambda_da_depth=.05, protect_bldg=True, freeze_onlybldg=True,
                             dynamic_depth_weight=True, dynamic_stage_switch=False,
                             enable_gaussian_completion=False, jbgs_release_protection=False).items():
        c.require(args.get(field) == value, "Checkpoint scientific control differs: " + field)
    c.require(not args.get("start_checkpoint") and not args.get("jbgs_resume_full") and not args.get("lod_init"),
              "Checkpoint is not a fresh no-anchor trajectory")
    c.require(opt["iterations"] == 30000 and opt["densify_until_iter"] == 15000
              and opt["position_lr_max_steps"] == 30000 and 8000 in args["jbgs_capture_iterations"], "Checkpoint schedule differs")
    model = state["model"]
    c.require(isinstance(model, (tuple, list)) and len(model) == 12, "Native capture tuple differs")
    n = capture["gaussians"]
    shapes = ((n, 3), (n, 1, 3), (n, 15, 3), (n, 2), (n, 4), (n, 1))
    for tensor, shape in zip(model[1:7], shapes):
        c.require(tuple(tensor.shape) == shape and tensor.dtype == torch.float32, "Gaussian parameter shape/dtype differs")
    for tensor, shape in zip(model[7:10], ((n,), (n, 1), (n, 1))):
        c.require(tuple(tensor.shape) == shape, "Native densification statistic shape differs")
    optimizer = model[10]
    c.require(len(optimizer["param_groups"]) == len(optimizer["state"]) == 6, "Native optimizer membership differs")
    widths = {"xyz": shapes[0], "f_dc": shapes[1], "f_rest": shapes[2], "scaling": shapes[3], "rotation": shapes[4], "opacity": shapes[5]}
    c.require({g["name"] for g in optimizer["param_groups"]} == set(widths), "Native optimizer group names differ")
    for group in optimizer["param_groups"]:
        c.require(len(group["params"]) == 1, "Native optimizer group size differs")
        stored = optimizer["state"][group["params"][0]]
        c.require(set(stored) == {"step", "exp_avg", "exp_avg_sq"} and stored["step"].item() == 8000,
                  "Checkpoint does not contain 8000 native optimizer steps")
        for name in ("exp_avg", "exp_avg_sq"):
            c.require(tuple(stored[name].shape) == widths[group["name"]] and stored[name].dtype == torch.float32,
                      "Optimizer moment shape/dtype differs")
    tensor_count, scalar_count = 0, 0
    def finite(value):
        nonlocal tensor_count, scalar_count
        if torch.is_tensor(value):
            tensor_count += 1
            c.require(value.device.type == "cpu", "CPU validation unexpectedly obtained a GPU tensor")
            if value.is_floating_point() or value.is_complex():
                flat = value.reshape(-1)
                for start in range(0, flat.numel(), 1 << 20):
                    c.require(bool(torch.isfinite(flat[start:start+(1 << 20)]).all()), "Nonfinite checkpoint tensor")
        elif isinstance(value, dict):
            for child in value.values(): finite(child)
        elif isinstance(value, (list, tuple)):
            for child in value: finite(child)
        elif isinstance(value, np.ndarray):
            if np.issubdtype(value.dtype, np.number): c.require(np.isfinite(value).all(), "Nonfinite numpy state")
        else:
            c.check_finite_numbers(value)
            scalar_count += 1
    finite(state)
    mask = state["frozen_mask"]
    c.require(mask is not None and tuple(mask.shape) == (n,) and mask.dtype == torch.bool
              and mask.sum().item() == trace_row["protected"], "Checkpoint protection count differs")
    c.require(state["runtime"]["freeze_done"] is False, "Checkpoint disabled further native densification")
    data = PlyData.read(ply_path, mmap="r")["vertex"].data
    c.require(len(data) == n and n > 0, "Gaussian PLY count differs")
    for name in data.dtype.names:
        if data.dtype[name].kind == "f":
            for start in range(0, n, 1 << 18):
                c.require(np.isfinite(data[name][start:start+(1 << 18)]).all(), "Nonfinite Gaussian PLY field")
    fields = [(model[1], ["x", "y", "z"]), (model[2], [f"f_dc_{i}" for i in range(3)]),
              (model[4], ["scale_0", "scale_1"]), (model[5], [f"rot_{i}" for i in range(4)]),
              (model[6], ["opacity"])]
    for tensor, names in fields:
        values = tensor.detach().reshape(n, -1).numpy()
        for index, name in enumerate(names):
            c.require(name in data.dtype.names and np.array_equal(values[:, index], data[name]), "PLY/checkpoint field differs: " + name)
    # PLY SH-rest order is (color,coefficient), while native parameter is (coefficient,color).
    for channel in range(3):
        for coefficient in range(15):
            name = f"f_rest_{channel * 15 + coefficient}"
            c.require(np.array_equal(model[3][:, coefficient, channel].detach().numpy(), data[name]), "PLY SH-rest differs")
    return dict(gaussians=n, all_checkpoint_tensors_finite=True, tensor_count=tensor_count,
                all_ply_float_fields_finite=True, ply_model_parameter_values_equal=True,
                six_adam_step_counters=8000, checkpoint_loaded_with_cpu_mmap=True,
                protected=int(mask.sum()), scientific_verdict=None)


def validate(region, output):
    c.policy("/policy.json")
    c.verify_activation(Path("/activation/receipt.json"), Path("/parents"), Path("/policy.json"))
    expected = identity(region)
    trained = Path("/trained")
    snapshot = trained / "model/jbgs_complete/iteration_8000"
    capture = c.read(snapshot / "receipt.json")
    c.require(capture["schema"] == "JBGS_GEOGS_COMPLETE_STATE_v1" and capture["iteration"] == 8000
              and capture["scientific_verdict"] is None and capture["after_protection_registration"] is True
              and type(capture["gaussians"]) is int and capture["gaussians"] > 0, "Invalid complete-prefix receipt")
    for filename, key in (("point_cloud.ply", "ply_sha256"), ("checkpoint.pth", "checkpoint_sha256")):
        c.require(c.sha(snapshot / filename) == capture[key], "Complete prefix payload changed: " + filename)
    raw, rows = trace_prefix(trained / "model/jbgs_trace.jsonl", capture["gaussians"], expected["initial"]["protected_gaussians"])
    check = validate_checkpoint(snapshot / "checkpoint.pth", snapshot / "point_cloud.ply", capture, expected, rows[-1])
    prefix_path = output / "trace_through_8000.jsonl"
    with prefix_path.open("xb") as stream: stream.write(raw)
    rel = c.run_relative(region)
    records = {"parent_training_receipt": c.record(trained / "receipt.json", rel + "/receipt.json"),
        "parent_invocation": c.record(trained / "invocation.json", rel + "/invocation.json"),
        "config": c.record(Path("/config.json"), c.SELECTED[region] + "/config.json"),
        "model_cfg_args": c.record(trained / "model/cfg_args", rel + "/model/cfg_args"),
        "sfm_manifest": c.record(Path("/sfm_input/initialization_manifest.json"), c.SELECTED[region] + f"/inputs/{region}/initialization_manifest.json"),
        "original_input_manifest": c.record(Path("/input/input_manifest.json"), f"inputs/{region}/input_manifest.json"),
        "amendment": c.record(Path("/amendment.json"), c.SELECTED[region] + "/amendment.json"),
        "source_runtime_receipt": c.record(Path("/source/jbgs_memory_recovery_receipt.json"), c.SELECTED[region] + "/source/jbgs_memory_recovery_receipt.json"),
        "snapshot_capture_receipt": c.record(snapshot / "receipt.json", rel + "/model/jbgs_complete/iteration_8000/receipt.json"),
        "snapshot_checkpoint": c.record(snapshot / "checkpoint.pth", rel + "/model/jbgs_complete/iteration_8000/checkpoint.pth"),
        "snapshot_ply": c.record(snapshot / "point_cloud.ply", rel + "/model/jbgs_complete/iteration_8000/point_cloud.ply"),
        "original_trace": c.record(trained / "model/jbgs_trace.jsonl", rel + "/model/jbgs_trace.jsonl"),
        "initialization": c.record(trained / "model/jbgs_no_anchor/initialization.json", rel + "/model/jbgs_no_anchor/initialization.json"),
        "first_step": c.record(trained / "model/jbgs_no_anchor/first_step.json", rel + "/model/jbgs_no_anchor/first_step.json"),
        "activation_receipt": c.record(Path("/activation/receipt.json"), "completed_prefix8000_v1/activation/receipt.json"),
        "prefix_trace": c.record(prefix_path, f"completed_prefix8000_v1/{region}/validation/trace_through_8000.jsonl")}
    for name, file in (("parent_training_receipt.json", trained / "receipt.json"), ("parent_invocation.json", trained / "invocation.json"),
        ("config_snapshot.json", Path("/config.json")), ("amendment_snapshot.json", Path("/amendment.json")),
        ("first_step_snapshot.json", trained / "model/jbgs_no_anchor/first_step.json"),
        ("initialization_snapshot.json", trained / "model/jbgs_no_anchor/initialization.json")):
        shutil.copyfile(file, output / name)
    return dict(schema="GEOGS_SFM_PREFIX_VALIDATION_v1", status="PREFIX_8000_VALIDATED", validation_pass=True,
        scientific_verdict=None, analysis_role=c.ROLE, region=region, condition_id=c.CONDITION,
        selected_experiment=c.SELECTED[region], selected_run=rel, iteration=8000, actual_optimizer_updates=8000,
        planned_total_updates=30000, parent_training_status=expected["parent"]["status"],
        parent_failure_status_preserved=True, establishes_22000_or_30000_completion=False,
        reference_accessed=False, source_sha256=c.method_source_map(expected["source_map"]),
        full_source_python_sha256=expected["source_map"], config_sha256=c.sha("/config.json"),
        runtime_image_id=c.IMAGE, policy_sha256=c.POLICY_SHA, files=list(records.values()), **records,
        producer_code_sha256=c.driver_hashes(),
        trace_record_count=len(rows), trace_iterations=[row["iteration"] for row in rows],
        trace_validation_scope="Scheduled trace membership through8000 only; complete parent trace separately hash-bound",
        save_provenance=expected["save_order"], checkpoint_validation=check,
        limitations=["Supplementary fixed8000 diagnostic only", "No final convergence or22k/30k completion claim", "Not an anchor-only causal ablation"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--activate", action="store_true")
    parser.add_argument("--region", choices=tuple(c.SELECTED))
    args = parser.parse_args()
    c.scope()
    output = Path("/output")
    c.require(output.is_dir(), "Mount an existing output directory")
    c.require(not (output / "receipt.json").exists(), "Immutable receipt already exists")
    started = time.time()
    try:
        if args.activate:
            payload = c.activation_evidence(Path("/parents"), Path("/policy.json"))
        else:
            c.require(args.region in c.SELECTED, "Region required")
            payload = validate(args.region, output)
    except Exception as error:
        payload = dict(schema="GEOGS_SFM_PREFIX_ACTIVATION_v1" if args.activate else "GEOGS_SFM_PREFIX_VALIDATION_v1",
            status="NOT_READY" if isinstance(error, c.NotReady) else "FAIL_PREFIX_VALIDATION",
            scientific_verdict=None, analysis_role=c.ROLE, region=args.region, error=traceback.format_exc(),
            reference_accessed=False, started_unix=started, finished_unix=time.time())
        name = f"attempt_{time.time_ns()}.json" if args.activate else "receipt.json"
        c.write(output / name, payload)
        print(json.dumps({"status": payload["status"], "error": str(error)}))
        return 3 if isinstance(error, c.NotReady) else 1
    c.write(output / "receipt.json", payload)
    print(json.dumps({"status": payload["status"], "region": args.region}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
