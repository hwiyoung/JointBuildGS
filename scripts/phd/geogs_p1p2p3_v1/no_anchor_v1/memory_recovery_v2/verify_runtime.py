#!/usr/bin/env python3
"""CPU by default. Optional approved CUDA test: eight tiny synthetic Adam steps.

No scene, renderer, training dataset, or actual GeoGS training is loaded.
"""
import argparse
import gc
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import time
import traceback
from types import SimpleNamespace
import weakref

import torch
import prepare_runtime as preparer
from pinned_storage import GROUP_WIDTHS


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def verify(args):
    if not Path("/.dockerenv").is_file():
        raise RuntimeError("Docker is required")
    cuda = args.device == "cuda"
    device = torch.device("cuda:0" if cuda else "cpu")
    if cuda:
        torch.cuda.set_device(device)
        total = torch.cuda.get_device_properties(device).total_memory
        torch.cuda.set_per_process_memory_fraction((64 << 20) / total, device=device)
    checks = []
    with tempfile.TemporaryDirectory(prefix="jbgs-pinned-runtime-") as temporary:
        temporary = Path(temporary)
        if args.source:
            source = temporary / "prepared_source"
            amendment = preparer.prepare(args.source, source, args.v1_directory)
            checks.append("prepared_from_exact_original_source_hashes_preserved")
        else:
            source = args.prepared_source.resolve(strict=True)
            amendment = json.loads((source / "jbgs_memory_recovery_receipt.json").read_text())
        v1 = preparer.load_preparer(args.v1_directory)
        assert amendment["status"] == "PASS_MEMORY_RECOVERY_RUNTIME_PREPARED"
        assert amendment["storage_version"] == 2 and amendment["science_config_unchanged"]
        assert v1.hashes(source) == amendment["destination_python_sha256"]
        assert preparer.sha(source / "train.py") == preparer.EXPECTED_PATCHED_TRAIN_SHA256
        assert preparer.sha(source / "jbgs_memory_recovery_v1_base.py") == preparer.V1_ADAPTER_SHA256
        assert preparer.sha(source / "jbgs_no_anchor_runtime_receipt.json") == v1.PARENT_RECEIPT_SHA256
        text = (source / "train.py").read_text()
        assert text.index("memory_recovery.before_forward") < text.index("render_pkg = render(viewpoint_cam")
        assert text.index("total_loss.backward()") < text.index("memory_recovery.before_optimizer_step") < text.index("gaussians.optimizer.step()")
        assert text.index("memory_recovery.after_optimizer_step") < text.index("scene.save(iteration)") < text.index("gaussians.densify_and_prune")
        assert text.index("gaussians.densify_and_prune") < text.index("memory_recovery.after_step_boundary") < text.index("if jbgs_state.after_step(locals())")
        assert text.count("gaussians.optimizer.zero_grad(set_to_none=True)") == 1
        checks.append("train_bytes_identical_v1_boundaries_parent_receipt_preserved")
        base = load("jbgs_memory_recovery_v1_base", source / "jbgs_memory_recovery_v1_base.py")
        load("jbgs_pinned_storage", source / "jbgs_pinned_storage.py")
        runtime = load("jbgs_memory_recovery", source / "jbgs_memory_recovery.py")
        if not cuda:
            gpu_storage_class = base.MomentStorage

            class CpuFixtureStorage(gpu_storage_class):
                def __init__(self):
                    super().__init__(require_cuda=False, pin_memory=False,
                                     budget_reader=lambda: (1 << 20, 2 << 30))

            base.MomentStorage = CpuFixtureStorage
        optimizers = []
        for _ in range(2):
            groups = []
            for name, width in GROUP_WIDTHS.items():
                values = torch.arange(8 * width, dtype=torch.float32).reshape(8, width) / 100
                groups.append(dict(name=name, params=[torch.nn.Parameter(values.to(device))], lr=.001))
            optimizers.append(torch.optim.Adam(groups, eps=1e-15, foreach=True))
        model = temporary / "model"
        model.mkdir()
        manifest = temporary / "synthetic_manifest.json"
        manifest.write_text(json.dumps({"region": "P1", "fixture_only": True}))
        environment = dict(args=SimpleNamespace(jbgs_sfm_initialization_manifest=str(manifest),
            jbgs_resume_full=False, start_checkpoint=None, model_path=str(model), iterations=8),
            first_iter=0, gaussians=SimpleNamespace(optimizer=optimizers[1]),
            lod_depth_maps={"fixture": torch.tensor([[1., -0.], [float("nan"), 2.]])},
            da_depth_maps={"fixture": torch.tensor([[1., 2.], [3., 4.]])})
        recovery = runtime.initialize(environment)
        fixture_started = time.monotonic()
        torch.manual_seed(23)
        for iteration in range(1, 9):
            recovery.before_forward(optimizers[1], iteration)
            previous_gradients = [weakref.ref(g["params"][0].grad) for g in optimizers[1].param_groups
                                  if g["params"][0].grad is not None]
            if cuda and iteration == 1:
                recovery.depths_to_device(environment["lod_depth_maps"]["fixture"],
                    environment["da_depth_maps"]["fixture"], device, iteration)
            inputs = [torch.randn(g["params"][0].shape).to(device) for g in optimizers[0].param_groups]
            for optimizer in optimizers:
                loss = sum(((g["params"][0] * x).sin() + g["params"][0].square()).sum()
                           for g, x in zip(optimizer.param_groups, inputs))
                optimizer.zero_grad(set_to_none=True)
                loss.backward()
            del loss
            gc.collect()
            assert all(reference() is None for reference in previous_gradients)
            recovery.before_optimizer_step(optimizers[1], iteration)
            for optimizer in optimizers:
                optimizer.step()
            recovery.after_optimizer_step(optimizers[1], iteration)
            for first, second in zip(optimizers[0].param_groups, optimizers[1].param_groups):
                left, right = first["params"][0], second["params"][0]
                assert torch.equal(left, right)
                for key in ("step", "exp_avg", "exp_avg_sq"):
                    assert torch.equal(optimizers[0].state[left][key], optimizers[1].state[right][key])
            del left, right, first, second
            if iteration in (3, 6):
                references = []
                for optimizer in optimizers:
                    for group in optimizer.param_groups:
                        old = group["params"][0]
                        references.append(weakref.ref(old))
                        state = optimizer.state.pop(old)
                        values = torch.cat((old.detach()[1:], old.detach()[:3]), dim=0) if iteration == 3 else old.detach()[1:].clone()
                        new = torch.nn.Parameter(values)
                        for name in base.MOMENTS:
                            state[name] = (torch.cat((state[name][1:], torch.zeros_like(state[name][:3])), dim=0)
                                           if iteration == 3 else state[name][1:].clone())
                        group["params"] = [new]
                        optimizer.state[new] = state
                del old, new, state, values, group
                gc.collect()
                assert all(reference() is None for reference in references)
            recovery.after_step_boundary(optimizers[1], iteration)
        fixture_seconds = time.monotonic() - fixture_started
        if cuda and fixture_seconds > 10:
            raise RuntimeError("Synthetic CUDA fixture exceeded its observed 10-second window")
        recovery.finalize()
        lifecycle = json.loads((model / "jbgs_memory_recovery/receipt.json").read_text())
        assert lifecycle["status"] == "PASS_MEMORY_LIFECYCLE_COMPLETED"
        assert lifecycle["storage_version"] == 2 and lifecycle["pinned_cache"]["slot_count"] == 12
        assert lifecycle["first_populated_moment_roundtrip_checked"]
        if cuda:
            assert all(row["pinned"] for row in lifecycle["pinned_cache"]["slots"])
        policy = json.loads((model / "jbgs_memory_recovery/pinned_cache_policy.json").read_text())
        assert policy["science_config_unchanged"] and not policy["complete_resume_supported"]
        checks.extend(["eight_synthetic_steps_parameters_moments_counters_bitwise_equal",
            "native_style_growth_prune_gpu_state_at_boundaries", "old_parameters_gradients_collectible",
            "first_roundtrip_byte_check", "wrapper_cache_policy_trace_and_final_receipt",
            "actual_cuda_pinned_allocations" if cuda else "cpu_lifecycle_substitution_no_cuda"])
        return dict(schema="jointbuildgs.geogs.pinned_runtime_validation.v2",
            status="PASS_CUDA_RUNTIME_FIXTURE" if cuda else "PASS_CPU_RUNTIME_FIXTURE",
            scientific_verdict=None, checks=checks, torch_version=torch.__version__, device=str(device),
            original_scene_training_launched=False, synthetic_optimizer_steps=8,
            fixture_window_seconds=fixture_seconds,
            prepared_source=str(args.prepared_source or "temporary original-source copy"),
            prepared_source_python_sha256=amendment["destination_python_sha256"],
            prepared_amendment_sha256=preparer.sha(source / "jbgs_memory_recovery_receipt.json"),
            maximum_cuda_allocated_bytes=torch.cuda.max_memory_allocated(device) if cuda else None,
            cuda_allocator_cap_bytes=64 << 20 if cuda else None,
            lifecycle=lifecycle)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--source", type=Path)
    selection.add_argument("--prepared-source", type=Path)
    parser.add_argument("--v1-directory", type=Path, required=True)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    if args.receipt.exists():
        raise ValueError("Receipt exists")
    try:
        payload = verify(args)
    except Exception:
        payload = dict(schema="jointbuildgs.geogs.pinned_runtime_validation.v2",
                       status="FAIL_RUNTIME_FIXTURE", scientific_verdict=None, error=traceback.format_exc())
    payload["validation_sources_sha256"] = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in Path(__file__).parent.glob("*.py")}
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    with args.receipt.open("x") as stream:
        json.dump(payload, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"status": payload["status"], "receipt": str(args.receipt), "checks": len(payload.get("checks", []))}))
    return 0 if payload["status"].startswith("PASS_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
