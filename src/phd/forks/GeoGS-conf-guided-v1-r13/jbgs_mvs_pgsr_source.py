"""Exact source lineage and complete Anchor8k restore validation."""
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
