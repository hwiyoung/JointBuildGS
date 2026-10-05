"""Prepare an isolated, hash-bound GeoGS MVS/PGSR diagnostic source tree.

The original input manifest and legacy depth-path arguments remain the exact
Anchor8k scene identity. Supplemental MVS bytes are independently bound by the
integration helper; the legacy ``da`` names are compatibility identifiers only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil


SCHEMA = "JBGS_GEOGS_MVS_PGSR_SOURCE_v1"
PROVENANCE_NAME = "mvs_pgsr_source_provenance.json"
EXPECTED_PARENT = {
    "train.py": "08cfab996b144488b1a583bf722b991c627d90136a9031f85f7d33b1cae0c44b",
    "jbgs_state.py": "7114f78e6f429c9186ce44e81a0c40d18e5087994f99a52d81eeee18ab7fa570",
    "gaussian_renderer/__init__.py": "6a7710f9a52aaf419705fbb983d6cdaeb8c6986e33a07446267ce2d407448492",
}
RESTORE_BLOCK = """    if state['source_sha256'] != digest(Path(__file__).with_name('train.py')):
        raise ValueError('Instrumented training source changed')
    if state['implementation_hashes'] != implementation_hashes():
        raise ValueError('An instrumented implementation file changed')"""
RESTORE_REPLACEMENT = """    from jbgs_mvs_pgsr_source import verify_resume_source
    verify_resume_source(state, Path(__file__).parent, implementation_hashes())"""
STAGE2_BLOCK = """            total_loss = rgb_loss + dist_loss + normal_loss
            if lod_depth is not None:"""
STAGE2_REPLACEMENT = """            normal_loss = mvs_pgsr_control.geometry_loss(
                viewpoint_cam, render_pkg, gaussians, pipe, background, iteration,
                native_normal_loss=normal_loss)
            total_loss = rgb_loss + dist_loss + normal_loss
            if lod_depth is not None:"""
TRACE_BLOCK = """        gaussians.optimizer.zero_grad(set_to_none=True)
        total_loss.backward()"""
TRACE_REPLACEMENT = """        mvs_pgsr_control.training_trace(
            iteration=iteration, camera=cam_name, prior_loss=lod_depth_loss,
            visual_loss=da_depth_loss, prior_weight=current_lod_weight,
            visual_weight=current_da_weight, geometry_loss=normal_loss,
            rgb_loss=rgb_loss)
        gaussians.optimizer.zero_grad(set_to_none=True)
        total_loss.backward()
        mvs_pgsr_control.after_backward(iteration, gaussians)"""

# Kept inside this preparer so the new diagnostic does not import mutable code
# from another experiment. This module is itself part of prepared source hashes.
SOURCE_ADAPTER = '''"""Exact source lineage and complete Anchor8k restore validation."""
import hashlib
import json
from pathlib import Path
import random

import numpy as np
import torch


def verify_resume_source(state, source_root, current_hashes):
    receipt = json.loads((Path(source_root) / "mvs_pgsr_source_provenance.json").read_text())
    if receipt.get("schema") != "JBGS_GEOGS_MVS_PGSR_SOURCE_v1":
        raise ValueError("Unrecognized MVS/PGSR source provenance")
    if receipt.get("scientific_verdict") is not None:
        raise ValueError("Source provenance must retain a null scientific verdict")
    if current_hashes != receipt["prepared_implementation_hashes"]:
        raise ValueError("Prepared MVS/PGSR implementation changed")
    allowed = (receipt["parent_implementation_hashes"], receipt["prepared_implementation_hashes"])
    if not any(state["implementation_hashes"] == expected for expected in allowed):
        raise ValueError("Checkpoint implementation differs from both exact recorded source lineages")
    if state["source_sha256"] != state["implementation_hashes"]["train.py"]:
        raise ValueError("Checkpoint train hash differs from its implementation hashes")
    for name, expected in receipt["helper_sha256"].items():
        if hashlib.sha256((Path(source_root) / name).read_bytes()).hexdigest() != expected:
            raise ValueError("Prepared helper changed: " + name)


def _assert_equal(expected, actual, path):
    """Check exact values without random draws or floating-point tolerances."""
    if expected is None:
        if actual is not None:
            raise ValueError("Restored optional value differs: " + path)
    elif isinstance(expected, torch.Tensor):
        if not isinstance(actual, torch.Tensor) or expected.dtype != actual.dtype or expected.shape != actual.shape:
            raise ValueError("Restored tensor metadata differs: " + path)
        if not torch.equal(expected.to(actual.device), actual):
            raise ValueError("Restored tensor differs: " + path)
    elif isinstance(expected, np.ndarray):
        if not isinstance(actual, np.ndarray) or expected.dtype != actual.dtype or not np.array_equal(expected, actual):
            raise ValueError("Restored array differs: " + path)
    elif isinstance(expected, dict):
        if not isinstance(actual, dict) or expected.keys() != actual.keys():
            raise ValueError("Restored mapping keys differ: " + path)
        for key, value in expected.items():
            _assert_equal(value, actual[key], path + "." + str(key))
    elif isinstance(expected, (list, tuple)):
        if type(expected) is not type(actual) or len(expected) != len(actual):
            raise ValueError("Restored sequence differs: " + path)
        for index, value in enumerate(expected):
            _assert_equal(value, actual[index], path + "." + str(index))
    elif expected != actual:
        raise ValueError("Restored scalar differs: " + path)


def verify_restored_anchor(state, env, restored):
    """Verify restoration before the first resumed native camera draw.

    Future CUDA trajectories are not asserted to be bitwise identical. New
    geometry sampling must use an independent RNG or iteration-derived seeds.
    """
    g, scene, args = env["gaussians"], env["scene"], env["args"]
    _assert_equal(state["model"], g.capture(), "model_and_optimizer")
    _assert_equal(state["completed_mask"], g.completed_mask, "completed_mask")
    for key, value in state["runtime"].items():
        expected = False if args.jbgs_release_protection and key == "freeze_done" else value
        _assert_equal(expected, restored[key], "runtime." + key)
    if args.jbgs_release_protection:
        _assert_equal(None, g.frozen_mask, "released_frozen_mask")
        _assert_equal(None, restored["building_freeze_mask"], "released_building_mask")
    else:
        _assert_equal(state["frozen_mask"], g.frozen_mask, "frozen_mask")
        _assert_equal(state["building_freeze_mask"], restored["building_freeze_mask"], "building_mask")
    for role, cameras in (("train", scene.getTrainCameras()), ("test", scene.getTestCameras())):
        _assert_equal(state[role + "_order"], [c.image_name for c in cameras], role + "_order")
    stack = restored["viewpoint_stack"]
    _assert_equal(state["viewpoint_stack"], None if stack is None else [c.image_name for c in stack], "viewpoint_stack")
    _assert_equal(state["rng"]["python"], random.getstate(), "rng.python")
    _assert_equal(state["rng"]["numpy"], np.random.get_state(), "rng.numpy")
    _assert_equal(state["rng"]["torch_cpu"].cpu(), torch.get_rng_state(), "rng.torch_cpu")
    _assert_equal([x.cpu() for x in state["rng"]["torch_cuda"]], torch.cuda.get_rng_state_all(), "rng.torch_cuda")
    return {"status": "PASS", "scope": "immediate_complete_anchor_restore",
            "model_optimizer_exact": True, "controller_exact": True,
            "camera_order_and_stack_exact": True, "rng_exact": True,
            "protection": "declared_release" if args.jbgs_release_protection else "native_exact",
            "scientific_verdict": None}
'''


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            value.update(block)
    return value.hexdigest()


def implementation_hashes(root):
    root = Path(root)
    return {str(path.relative_to(root)): digest(path) for path in sorted(root.rglob("*.py"))
            if "submodules" not in path.parts and "__pycache__" not in path.parts}


def payload_hashes(root):
    root = Path(root)
    return {str(path.relative_to(root)): digest(path) for path in sorted(root.rglob("*"))
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
            and path.name != PROVENANCE_NAME}


def replace_once(text, old, new, label):
    if text.count(old) != 1:
        raise ValueError(f"Expected one {label} block, found {text.count(old)}")
    return text.replace(old, new, 1)


def prepare_source(parent, destination, helper, geometry_helper, depth_helper):
    parent = Path(parent).resolve(strict=True)
    destination = Path(destination).absolute()
    if destination.exists():
        raise FileExistsError(destination)
    if destination.resolve().is_relative_to(parent):
        raise ValueError("Prepared destination must be outside the immutable parent")
    if any(path.is_symlink() for path in parent.rglob("*")):
        raise ValueError("Parent source must be self-contained without symlinks")
    parent_implementation = implementation_hashes(parent)
    for name, expected in EXPECTED_PARENT.items():
        if parent_implementation.get(name) != expected:
            raise ValueError("Pinned GeoGS parent differs: " + name)
    if any((parent / name).exists() for name in (PROVENANCE_NAME, "local_source_provenance.json", "jbgs_mvs_pgsr.py")):
        raise ValueError("Parent must be the original GeoGS state/camera snapshot")
    parent_payload = payload_hashes(parent)
    helper_inputs = {
        "jbgs_mvs_pgsr.py": Path(helper).resolve(strict=True),
        "jbgs_mvs_pgsr_geometry.py": Path(geometry_helper).resolve(strict=True),
        "jbgs_mvs_pgsr_depth.py": Path(depth_helper).resolve(strict=True),
    }
    helper_bytes = {name: path.read_bytes() for name, path in helper_inputs.items()}
    for name, contents in helper_bytes.items():
        if name in parent_payload:
            raise ValueError("Helper would overwrite a parent file: " + name)
        compile(contents, str(destination / name), "exec")
    train = (parent / "train.py").read_text()
    train = replace_once(train, "import jbgs_state\n", "import jbgs_state\nimport jbgs_mvs_pgsr\n", "integration import")
    train = replace_once(train, "    tb_writer = prepare_output_and_logger(dataset)\n",
                         "    tb_writer = prepare_output_and_logger(dataset)\n"
                         "    mvs_pgsr_control = jbgs_mvs_pgsr.from_environment(dataset, opt, pipe, args)\n",
                         "integration initialization before complete restore")
    train = replace_once(train,
                         "    da_depth_maps = load_depth_set(args.da_depth_path, all_cameras, target_size)\n",
                         "    # Legacy da variables now contain explicitly bound MVS supervision.\n"
                         "    da_depth_maps = mvs_pgsr_control.load_mvs_depth_set(\n"
                         "        all_cameras, target_size,\n"
                         "        train_camera_names=[camera.image_name for camera in scene.getTrainCameras()])\n",
                         "MVS depth source")
    train = replace_once(train, STAGE2_BLOCK, STAGE2_REPLACEMENT, "stage2 geometry objective")
    train = replace_once(train, TRACE_BLOCK, TRACE_REPLACEMENT, "realized supervision trace")
    state = (parent / "jbgs_state.py").read_text()
    state = replace_once(state, RESTORE_BLOCK, RESTORE_REPLACEMENT, "exact source lineage validation")
    rng_line = "    torch.cuda.set_rng_state_all([x.cpu() for x in state['rng']['torch_cuda']])\n"
    state = replace_once(state, rng_line, rng_line +
                         "    from jbgs_mvs_pgsr_source import verify_restored_anchor\n"
                         "    restore_equivalence = verify_restored_anchor(state, env, out)\n",
                         "complete restored state validation")
    receipt_line = "    with (Path(args.model_path) / 'jbgs_restore.json').open('x') as f:\n"
    state = replace_once(state, receipt_line,
                         "    receipt['restore_equivalence'] = restore_equivalence\n" + receipt_line,
                         "complete restore receipt")
    prepared_text = {"train.py": train, "jbgs_state.py": state,
                     "jbgs_mvs_pgsr_source.py": SOURCE_ADAPTER}
    for name, contents in prepared_text.items():
        compile(contents, str(destination / name), "exec")
    # Fail all pattern and syntax checks before creating the new source tree.
    shutil.copytree(parent, destination, symlinks=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for name, contents in prepared_text.items():
        (destination / name).write_text(contents)
    for name, contents in helper_bytes.items():
        (destination / name).write_bytes(contents)
    if payload_hashes(parent) != parent_payload:
        raise RuntimeError("Immutable parent source changed during preparation")
    prepared_payload = payload_hashes(destination)
    changed = sorted(name for name in parent_payload if prepared_payload.get(name) != parent_payload[name])
    added = sorted(set(prepared_payload) - set(parent_payload))
    expected_added = sorted([*helper_inputs, "jbgs_mvs_pgsr_source.py"])
    if changed != ["jbgs_state.py", "train.py"] or added != expected_added:
        raise RuntimeError("Prepared source changes exceeded the declared scope")
    receipt = {
        "schema": SCHEMA, "scientific_verdict": None,
        "parent_path": str(parent), "prepared_path": str(destination),
        "parent_implementation_hashes": parent_implementation,
        "prepared_implementation_hashes": implementation_hashes(destination),
        "parent_payload_hashes": parent_payload, "prepared_payload_hashes": prepared_payload,
        "changed_parent_files": changed, "added_files": added,
        "helper_inputs": {name: {"path": str(path), "sha256": digest(destination / name)}
                          for name, path in helper_inputs.items()},
        "helper_sha256": {name: digest(destination / name) for name in expected_added},
        "preparer_sha256": digest(__file__),
        "patch_scope": ["integration initialization", "supplemental MVS depth targets",
                        "stage2 geometry objective only", "realized supervision trace",
                        "total gradient diagnostics before optimizer step",
                        "exact parent or prepared checkpoint source verification",
                        "immediate complete anchor restoration verification"],
        "preserved_controls": ["original input manifest identity", "native optimizer settings",
                               "native camera sampling", "native adaptive visual-depth controller",
                               "prior depth and protection", "densification and renderer"],
        "new_sampling_contract": "Private or iteration-derived RNG; never native global RNG draws",
        "legacy_da_identifiers": "Compatibility aliases for MVS; actual source recorded by helper trace",
    }
    with (destination / PROVENANCE_NAME).open("x") as stream:
        json.dump(receipt, stream, indent=2, allow_nan=False)
        stream.write("\n")
    return receipt


def main():
    if not Path("/.dockerenv").is_file():
        raise RuntimeError("Source preparation requires Docker")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--helper", required=True, type=Path)
    parser.add_argument("--geometry-helper", required=True, type=Path)
    parser.add_argument("--depth-helper", required=True, type=Path)
    args = parser.parse_args()
    receipt = prepare_source(args.parent, args.destination, args.helper, args.geometry_helper, args.depth_helper)
    print(json.dumps({"prepared_path": receipt["prepared_path"],
                      "train_sha256": receipt["prepared_implementation_hashes"]["train.py"],
                      "scientific_verdict": None}))


if __name__ == "__main__":
    main()
