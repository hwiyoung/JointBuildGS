#!/usr/bin/env python3
"""Bounded synthetic CPU proof tests; never train, render or load the large 8k state."""
import argparse
import copy
import json
from pathlib import Path
import resource
import subprocess
import tempfile
import time
import traceback

import common as c
import export as exporter
import validate as validator


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, allow_nan=True) + "\n")


def rejects(function, kind=ValueError, contains=None):
    try:
        function()
    except kind as error:
        if contains is not None:
            assert contains in str(error), (contains, str(error))
        return
    raise AssertionError("Invalid fixture unexpectedly accepted")


def producer(region, phase="train", iteration=None, status="PASS"):
    return dict(region=region, condition_id=c.CONDITION, phase=phase, iteration=iteration,
                scientific_verdict=None, status=status, started_unix=1., finished_unix=2.,
                native_exit_code=0 if status == "PASS" else 1,
                validated_exit_code=0 if status == "PASS" else 1, config_sha256="fixture-config")


def populate(parents, failed_train=None, failed_export=None):
    for region in c.SELECTED:
        put(parents / region / "receipt.json", producer(region, status="FAIL" if region == failed_train else "PASS"))
        for iteration in (22000, 30000):
            put(parents / region / "exports" / f"iteration_{iteration}" / "receipt.json",
                producer(region, "export", iteration, "FAIL" if (region, iteration) == failed_export else "PASS"))


def synthetic_state(torch, n=8):
    shapes = [(n, 3), (n, 1, 3), (n, 15, 3), (n, 2), (n, 4), (n, 1)]
    tensors = [torch.arange(torch.tensor(shape).prod().item(), dtype=torch.float32).reshape(shape) / 100 for shape in shapes]
    names = ["xyz", "f_dc", "f_rest", "scaling", "rotation", "opacity"]
    optimizer = {"state": {}, "param_groups": []}
    for index, (name, tensor) in enumerate(zip(names, tensors)):
        optimizer["param_groups"].append(dict(name=name, params=[index]))
        optimizer["state"][index] = dict(step=torch.tensor(8000.), exp_avg=torch.zeros_like(tensor), exp_avg_sq=torch.ones_like(tensor))
    model = (3, *tensors, torch.zeros(n), torch.zeros((n, 1)), torch.ones((n, 1)), optimizer, 3.0)
    args = dict(iterations=30000, stage_switch_iter=0, lambda_lod_anchor=.005, lambda_da_depth=.05,
                protect_bldg=True, freeze_onlybldg=True, dynamic_depth_weight=True, dynamic_stage_switch=False,
                enable_gaussian_completion=False, jbgs_release_protection=False, start_checkpoint=None,
                jbgs_resume_full=None, lod_init=False, jbgs_capture_iterations=[1, 8000, 15000, 22000, 30000])
    mapping = {"train.py": c.TRAIN_SHA, "jbgs_state.py": c.STATE_SHA, "render.py": c.RENDER_SHA}
    state = dict(schema="JBGS_GEOGS_COMPLETE_STATE_v1", iteration=8000, scientific_verdict=None,
                 source_sha256=c.TRAIN_SHA, implementation_hashes=mapping, input_manifest_sha256="fixture-sfm",
                 args=args, optimization=dict(iterations=30000, densify_until_iter=15000, position_lr_max_steps=30000),
                 model=model, frozen_mask=torch.arange(n) < 2, runtime=dict(freeze_done=False))
    expected = dict(source_map=mapping, parent=dict(sfm_manifest_sha256="fixture-sfm"))
    return state, expected


def save_ply(state, path):
    import numpy as np
    from plyfile import PlyData, PlyElement
    model = state["model"]
    n = len(model[1])
    names = ["x", "y", "z", "nx", "ny", "nz"] + [f"f_dc_{i}" for i in range(3)]
    names += [f"f_rest_{i}" for i in range(45)] + ["opacity", "scale_0", "scale_1"] + [f"rot_{i}" for i in range(4)]
    data = np.zeros(n, dtype=[(name, "f4") for name in names])
    for values, fields in ((model[1], ["x", "y", "z"]), (model[2], [f"f_dc_{i}" for i in range(3)]),
                           (model[4], ["scale_0", "scale_1"]), (model[5], [f"rot_{i}" for i in range(4)]),
                           (model[6], ["opacity"])):
        values = values.numpy().reshape(n, -1)
        for index, name in enumerate(fields): data[name] = values[:, index]
    for channel in range(3):
        for coeff in range(15): data[f"f_rest_{channel * 15 + coeff}"] = model[3][:, coeff, channel].numpy()
    PlyData([PlyElement.describe(data, "vertex")], text=False).write(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--parser", type=Path, required=True)
    parser.add_argument("--first-checkpoint", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    c.scope()
    import numpy as np
    import torch
    from PIL import Image
    started = time.time()
    checks = []
    def test(name, function):
        try:
            function()
            checks.append(dict(name=name, status="PASS"))
        except Exception:
            checks.append(dict(name=name, status="FAIL", error=traceback.format_exc()))
    with tempfile.TemporaryDirectory(prefix="prefix8000-cpu-") as temporary:
        root = Path(temporary)
        parents = root / "parents"
        test("frozen_source_save_after_optimizer_and_densification", lambda: c.assert_save_order(args.source))
        test("wrapper_shell_syntax", lambda: subprocess.run(["bash", "-n", str(Path(__file__).with_name("run.sh"))], check=True))
        def activation_train_failure():
            populate(parents, failed_train="P1")
            value = c.activation_evidence(parents, args.policy)
            assert len(value["failure_evidence"]) == 1 and value["regions"][0]["parent_training_status"] == "FAIL"
            put(root / "activation.json", value)
            c.verify_activation(root / "activation.json", parents, args.policy)
        test("actual_closed_train_failure_activates_and_remains_FAIL", activation_train_failure)
        def activation_export_failure():
            populate(parents, failed_export=("P2", 30000))
            value = c.activation_evidence(parents, args.policy)
            assert value["failure_evidence"][0]["phase"] == "export"
        test("actual_closed_export_failure_activates", activation_export_failure)
        def no_failure():
            populate(parents)
            rejects(lambda: c.activation_evidence(parents, args.policy))
        test("all_complete_does_not_trigger", no_failure)
        def missing_train():
            populate(parents, failed_train="P1")
            (parents / "P3/receipt.json").unlink()
            rejects(lambda: c.activation_evidence(parents, args.policy), c.NotReady)
        test("missing_selected_train_receipt_cannot_be_called_failure", missing_train)
        def missing_export():
            populate(parents, failed_train="P1")
            (parents / "P2/exports/iteration_22000/receipt.json").unlink()
            rejects(lambda: c.activation_evidence(parents, args.policy), c.NotReady)
        test("PASS_train_with_unfinished_export_must_wait", missing_export)
        def controller_failure():
            populate(parents, failed_train="P1")
            path = parents / "P1/receipt.json"
            value = c.read(path)
            value["native_exit_code"] = None
            put(path, value)
            rejects(lambda: c.activation_evidence(parents, args.policy))
        test("controller_or_prelaunch_failure_is_not_closed_native_failure", controller_failure)
        def changed_seal():
            populate(parents, failed_train="P1")
            put(root / "activation.json", c.activation_evidence(parents, args.policy))
            value = c.read(parents / "P1/receipt.json")
            value["finished_unix"] = 3.
            put(parents / "P1/receipt.json", value)
            rejects(lambda: c.verify_activation(root / "activation.json", parents, args.policy))
        test("activation_hash_membership_changes_rejected", changed_seal)
        trace_rows = [dict(iteration=i, lod_weight=.005, da_weight=.05, protected=2, gaussians=8, total_loss=1.)
                      for i in [1, *range(100, 8101, 100)]]
        trace_path = root / "trace.jsonl"
        def trace_write(rows): trace_path.write_text("".join(json.dumps(row) + "\n" for row in rows))
        def trace_valid():
            trace_write(trace_rows)
            raw, rows = validator.trace_prefix(trace_path, 8, 2)
            assert len(rows) == 81 and rows[-1]["iteration"] == 8000 and b'8100' not in raw
        test("exact81_trace_prefix_rows_and_no_later_rows", trace_valid)
        def later_failure_is_separate():
            trace_write(trace_rows[:-1])
            with trace_path.open("ab") as stream: stream.write(b'{"iteration": 8100, "total_loss":')
            _, rows = validator.trace_prefix(trace_path, 8, 2)
            assert len(rows) == 81 and rows[-1]["iteration"] == 8000
        test("later_incomplete_failed_step_does_not_invalidate_complete8k_prefix", later_failure_is_separate)
        def trace_missing():
            trace_write(trace_rows[:3] + trace_rows[4:])
            rejects(lambda: validator.trace_prefix(trace_path, 8, 2))
        test("missing_scheduled_prefix_trace_rejected", trace_missing)
        def trace_nan():
            rows = copy.deepcopy(trace_rows)
            rows[3]["total_loss"] = float("nan")
            trace_write(rows)
            rejects(lambda: validator.trace_prefix(trace_path, 8, 2))
        test("nonfinite_prefix_loss_rejected", trace_nan)
        state, expected = synthetic_state(torch)
        checkpoint, ply = root / "checkpoint.pth", root / "point_cloud.ply"
        capture, trace_row = dict(gaussians=8), dict(protected=2)
        def valid_checkpoint():
            torch.save(state, checkpoint)
            save_ply(state, ply)
            result = validator.validate_checkpoint(checkpoint, ply, capture, expected, trace_row)
            assert result["ply_model_parameter_values_equal"] and result["six_adam_step_counters"] == 8000
        test("complete_CPU_mmap_checkpoint_and_all58_PLY_parameter_values_equal", valid_checkpoint)
        def bad_counter():
            changed = copy.deepcopy(state)
            changed["model"][10]["state"][2]["step"] = torch.tensor(7999.)
            torch.save(changed, checkpoint)
            rejects(lambda: validator.validate_checkpoint(checkpoint, ply, capture, expected, trace_row), contains="8000 native optimizer steps")
        test("incorrect_Adam_update_counter_rejected", bad_counter)
        def nonfinite_moment():
            changed = copy.deepcopy(state)
            changed["model"][10]["state"][2]["exp_avg"][0, 1, 2] = float("nan")
            torch.save(changed, checkpoint)
            rejects(lambda: validator.validate_checkpoint(checkpoint, ply, capture, expected, trace_row), contains="Nonfinite checkpoint tensor")
        test("nonfinite_Adam_moment_rejected", nonfinite_moment)
        def changed_ply():
            torch.save(state, checkpoint)
            changed = copy.deepcopy(state)
            changed["model"][3][0, 4, 2] += 1
            save_ply(changed, ply)
            rejects(lambda: validator.validate_checkpoint(checkpoint, ply, capture, expected, trace_row), contains="PLY SH-rest differs")
        test("single_SH_rest_PLY_value_mismatch_rejected", changed_ply)
        if args.first_checkpoint:
            def actual_small_checkpoint():
                actual = torch.load(str(args.first_checkpoint), map_location="cpu", mmap=True)
                assert actual["schema"] == state["schema"] and actual["iteration"] == 1
                assert actual["source_sha256"] == c.TRAIN_SHA and actual["scientific_verdict"] is None
                for key, value in state["args"].items():
                    assert actual["args"].get(key) == value, (key, actual["args"].get(key), value)
                for key, value in state["optimization"].items(): assert actual["optimization"][key] == value
                assert len(actual["model"]) == 12 and all(s["step"].item() == 1 for s in actual["model"][10]["state"].values())
            test("actual_small_iteration1_schema_and_scientific_defaults_match", actual_small_checkpoint)
        export_root = root / "export"
        export_root.mkdir()
        mesh_dir = export_root / "model/train/ours_8000"
        mesh_dir.mkdir(parents=True)
        mesh = "ply\nformat ascii 1.0\nelement vertex 3\nproperty float x\nproperty float y\nproperty float z\nelement face 1\nproperty list uchar int vertex_indices\nend_header\n0 0 0\n1 0 0\n0 1 0\n3 0 1 2\n"
        for name in ("fuse.ply", "fuse_post.ply"): (mesh_dir / name).write_text(mesh)
        log = "The estimated bounding radius is 25.60\nRunning tsdf volume integration ...\nvoxel_size: 0.1\nsdf_trunc: 0.5\ndepth_truc: 51.2\npost processing the mesh to have 50 clusterscluster_to_kep\n"
        (export_root / "native.log").write_text(log)
        split_path = root / "split.json"
        put(split_path, {key: [dict(width=4, height=3) for _ in range(2)] for key in ("train", "evaluation")})
        base = dict(regions=dict(P1=dict(expected_train=2, expected_test=2)))
        for role in ("train", "test"):
            for category in ("renders", "gt"):
                directory = export_root / "model" / role / "ours_8000" / category
                directory.mkdir(parents=True)
                for index in range(2): Image.fromarray(np.zeros((3, 4, 3), np.uint8)).save(directory / f"{index:05d}.png")
        def outputs_check(): return exporter.check_outputs(export_root, 8000, base, "P1", split_path=split_path, parser_path=args.parser)
        def actual_output_files():
            found, outputs = outputs_check()
            assert len(outputs) == 10 and found[0]["realized_extraction"]["mesh_res"] == 512
        test("actual_mesh_triangle_and_PNG_decode_and_official_TSDF_log", actual_output_files)
        def extraction_changed():
            (export_root / "native.log").write_text(log.replace("voxel_size: 0.1", "voxel_size: 0.2"))
            rejects(outputs_check)
            (export_root / "native.log").write_text(log)
        test("wrong_realized_voxel_size_rejected", extraction_changed)
        def missing_image():
            (export_root / "model/test/ours_8000/renders/00001.png").unlink()
            rejects(outputs_check)
        test("missing_actual_render_rejected", missing_image)
        test("CUDA_never_initialized", lambda: c.require(not torch.cuda.is_initialized(), "Unexpected CUDA initialization"))
    args.out.mkdir(parents=True, exist_ok=True)
    result = dict(schema="GEOGS_SFM_PREFIX_CPU_IMPLEMENTATION_VALIDATION_v1",
                  status="PASS" if all(row["status"] == "PASS" for row in checks) else "FAIL",
                  scientific_verdict=None, validation_scope="SYNTHETIC_CPU_FIXTURES_PLUS_FROZEN_SOURCE_AND_SMALL_ITERATION1_SCHEMA_ONLY",
                  actual_prefix8000_checkpoint_validated=False, actual_render_or_mesh_executed=False,
                  reference_accessed=False, gpu_accessed=False, runtime_image_id=c.IMAGE,
                  versions=dict(torch=torch.__version__, numpy=np.__version__), checks=checks,
                  producer_code_sha256=c.driver_hashes(), verify_cpu_sha256=c.sha(__file__), parser_sha256=c.sha(args.parser),
                  policy_sha256=c.sha(args.policy), frozen_source_save_proof=c.assert_save_order(args.source),
                  small_checkpoint_sha256=c.sha(args.first_checkpoint) if args.first_checkpoint else None,
                  started_unix=started, finished_unix=time.time(), peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)
    c.write(args.out / "receipt.json", result)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
