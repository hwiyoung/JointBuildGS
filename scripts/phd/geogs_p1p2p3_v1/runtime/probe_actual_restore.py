"""Audit an actual anchor before and after exactly one native optimizer step.

The source files remain unchanged. This process temporarily wraps the restore
function to compare its returned environment, installed hooks and PLY rendering,
then permits exactly one native optimizer step and verifies its camera selection.
"""
import importlib.util
import json
import math
import os
from pathlib import Path
import random
import runpy
import sys

import torch

config_path = Path(os.environ.get("JBGS_PROBE_CONFIG", "/config/native_example_parity_v1.json"))
config = json.loads(config_path.read_text())
sys.path.insert(0, "/source")
import jbgs_state

spec = importlib.util.spec_from_file_location("jbgs_compare_states", "/audit/compare_states.py")
comparison = importlib.util.module_from_spec(spec)
spec.loader.exec_module(comparison)
production_restore = jbgs_state.restore_state
probe_context = {}


def probe_restore(path, env, functions):
    restored = production_restore(path, env, functions)
    current = dict(env, **restored)
    current["iteration"] = restored["first_iter"]
    actual = jbgs_state.capture_state(current)
    expected = torch.load(path, map_location="cpu")
    rows = []
    for key in ("model", "iteration", "frozen_mask", "completed_mask", "building_freeze_mask",
                "runtime", "rng", "train_order", "test_order", "viewpoint_stack", "optimization",
                "implementation_hashes", "input_manifest_sha256", "hook_state"):
        rows += comparison.compare(expected[key], actual[key], key)
    # The comparison above is before even a synthetic backward pass. Validate
    # that the restored hooks actually attenuate a known unit incoming gradient.
    gaussian = env["gaussians"]
    mask = gaussian.frozen_mask
    hook_rows = []
    for name, scale in (("_xyz", env["args"].lod2_building_xyz_lr_scale),
                        ("_rotation", env["args"].protect_bldg_lr_scale),
                        ("_scaling", env["args"].protect_bldg_lr_scale)):
        parameter = getattr(gaussian, name)
        parameter.grad = None
        parameter.sum().backward()
        target = torch.ones_like(parameter)
        target[mask] *= scale
        hook_rows.append({"parameter": name, "scale": scale,
                          "exact_expected_gradient": bool(torch.equal(parameter.grad, target)),
                          "registered_hooks": len(parameter._backward_hooks or {})})
        parameter.grad = None
    # PLY is a rendering/surface-export artifact, not a complete restart state.
    # Verify its render-relevant parameters and actual render against the same
    # checkpoint, without introducing an extra independent training trajectory.
    from scene.gaussian_model import GaussianModel
    ply_gaussian = GaussianModel(gaussian.max_sh_degree)
    ply_gaussian.load_ply(str(Path(path).with_name("point_cloud.ply")))
    ply_rows = []
    for name in ("active_sh_degree", "_xyz", "_features_dc", "_features_rest", "_opacity", "_scaling", "_rotation"):
        ply_rows += comparison.compare(getattr(gaussian, name), getattr(ply_gaussian, name), "ply/" + name)
    cameras = env["scene"].getTestCameras() or env["scene"].getTrainCameras()[:1]
    render_rows = []
    with torch.no_grad():
        for camera in cameras:
            full_render = functions["render"](camera, gaussian, env["pipe"], env["background"])
            ply_render = functions["render"](camera, ply_gaussian, env["pipe"], env["background"])
            for name in ("render", "surf_depth", "rend_alpha", "rend_normal"):
                render_rows += comparison.compare(full_render[name], ply_render[name], f"render/{camera.image_name}/{name}")
            del full_render, ply_render
    del ply_gaussian
    # The audit itself must not consume the global RNG before native continuation.
    current_rng = jbgs_state.capture_state(current)["rng"]
    rng_rows = comparison.compare(actual["rng"], current_rng, "probe_preserves_rng")
    equal = (all(row["equal"] for row in rows + ply_rows + render_rows + rng_rows)
             and all(row["exact_expected_gradient"] for row in hook_rows))
    receipt = {"status": "EXACT_PRESTEP_RESTORE_AND_HOOK_PARITY" if equal else "RESTORE_DIFFERENCES_REQUIRE_REVIEW",
               "task_id": config["task_id"], "scientific_verdict": None,
               "runtime_image_id": config["runtime_image_id"], "config_sha256": jbgs_state.digest(config_path),
               "probe_script_sha256": jbgs_state.digest(__file__),
               "checkpoint_sha256": jbgs_state.digest(path), "optimizer_steps_before_comparison": 0,
               "native_render_backwards": 0, "synthetic_unit_gradient_backwards": len(hook_rows),
               "protected_gaussians": int(mask.sum()), "total_gaussians": len(mask),
               "nonmatching_entries": sum(not row["equal"] for row in rows),
               "entries": rows, "hook_checks": hook_rows, "ply_parameter_checks": ply_rows,
               "same_checkpoint_render_checks": render_rows, "audit_preserves_rng_checks": rng_rows}
    with Path("/output/restore_probe.json").open("x") as stream:
        json.dump(receipt, stream, indent=2, allow_nan=False)
    print(json.dumps({key: receipt[key] for key in ("status", "optimizer_steps_before_comparison", "protected_gaussians", "nonmatching_entries")}))
    if not equal:
        raise SystemExit(2)
    isolated_rng = random.Random()
    isolated_rng.setstate(actual["rng"]["python"])
    stack = list(actual["viewpoint_stack"] or actual["train_order"])
    next_camera = stack.pop(isolated_rng.randint(0, len(stack) - 1))
    probe_context.update(expected_camera=next_camera, expected_stack=stack,
                         expected_python_rng=isolated_rng.getstate(), iteration=actual["iteration"] + 1,
                         gaussian_count=len(mask), protected_count=int(mask.sum()),
                         expected_optimizer_steps={str(key): float(value["step"]) + 1
                                                   for key, value in expected["model"][-2]["state"].items()})
    return restored


def after_one_native_step(env):
    gaussian = env["gaussians"]
    actual_steps = {str(key): float(value["step"]) for key, value in gaussian.optimizer.state_dict()["state"].items()}
    report = {"task_id": config["task_id"], "scientific_verdict": None, "optimizer_steps": 1,
              "iteration": env["iteration"], "expected_iteration": probe_context["iteration"],
              "camera": env["cam_name"], "expected_camera": probe_context["expected_camera"],
              "next_camera_and_stack_equal": env["cam_name"] == probe_context["expected_camera"]
                  and jbgs_state.camera_names(env["viewpoint_stack"]) == probe_context["expected_stack"],
              "python_rng_equal_after_draw": random.getstate() == probe_context["expected_python_rng"],
              "optimizer_steps_increment_exactly_one": actual_steps == probe_context["expected_optimizer_steps"],
              "finite_model_parameters": all(bool(torch.isfinite(getattr(gaussian, name)).all())
                  for name in ("_xyz", "_features_dc", "_features_rest", "_opacity", "_scaling", "_rotation")),
              "loss": float(env["total_loss"].item()), "gaussians": len(gaussian.get_xyz),
              "protected": int(gaussian.frozen_mask.sum()), "source_modified": False}
    okay = (report["iteration"] == report["expected_iteration"]
            and all(report[key] for key in ("next_camera_and_stack_equal", "python_rng_equal_after_draw",
                                           "optimizer_steps_increment_exactly_one", "finite_model_parameters"))
            and math.isfinite(report["loss"]) and report["gaussians"] == probe_context["gaussian_count"]
            and report["protected"] == probe_context["protected_count"])
    report["status"] = "PASS_ONE_NATIVE_STEP" if okay else "FAIL_ONE_NATIVE_STEP"
    with Path("/output/one_step_probe.json").open("x") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
    print(json.dumps(report))
    raise SystemExit(0 if okay else 3)


jbgs_state.restore_state = probe_restore
jbgs_state.after_step = after_one_native_step
sys.argv = config["base_command"][1:] + config["resumed_options"]
runpy.run_path("/source/train.py", run_name="__main__")
