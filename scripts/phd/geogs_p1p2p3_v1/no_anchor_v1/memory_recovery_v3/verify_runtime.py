#!/usr/bin/env python3
"""CPU fixtures by default; optional explicitly launched <=64MiB CUDA toy only."""
import argparse
import ast
import gc
import importlib.util
import json
import os
from pathlib import Path
import resource
import sys
import tempfile
import time
import traceback
from types import SimpleNamespace
import weakref

import numpy as np
from plyfile import PlyData, PlyElement
import torch
import prepare_runtime as preparer

ATTRS = {"xyz": ("_xyz", (3,)), "f_dc": ("_features_dc", (1, 3)),
         "f_rest": ("_features_rest", (15, 3)), "opacity": ("_opacity", (1,)),
         "scaling": ("_scaling", (2,)), "rotation": ("_rotation", (4,))}


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def native_class(source):
    path = source / "scene/gaussian_model.py"
    assert preparer.sha(path) == preparer.GAUSSIAN_SHA
    tree = ast.parse(path.read_text())
    native = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "GaussianModel")
    methods = [node for node in native.body if isinstance(node, ast.FunctionDef)
               and node.name in ("save_ply", "construct_list_of_attributes")]
    assert len(methods) == 2
    native.body = methods
    module = ast.Module(body=[native], type_ignores=[])
    space = dict(np=np, torch=torch, os=os, PlyData=PlyData, PlyElement=PlyElement,
                 mkdir_p=lambda path: Path(path).mkdir(parents=True, exist_ok=True))
    exec(compile(ast.fix_missing_locations(module), str(path), "exec"), space)
    return space["GaussianModel"]


def make_model(kind, n, device, optimizer=True):
    model, groups = kind(), []
    for index, (name, (attr, shape)) in enumerate(ATTRS.items()):
        size = n * int(np.prod(shape))
        value = torch.arange(size, dtype=torch.float32).reshape(n, *shape) / 1000 + index / 100
        parameter = torch.nn.Parameter(value.to(device))
        setattr(model, attr, parameter)
        if name in ("xyz", "scaling", "rotation"):
            parameter.register_hook(protected_hook)
        groups.append(dict(name=name, params=[parameter], lr=.001))
    if optimizer: model.optimizer = torch.optim.Adam(groups, eps=1e-15, foreach=True)
    return model


def protected_hook(gradient):
    result = gradient.clone()
    result[:2] *= .01
    return result


def compare_files(left, right, n):
    a, b = left.read_bytes(), right.read_bytes()
    assert a == b and preparer.sha(left) == preparer.sha(right)
    header, body = a.split(b"end_header\n", 1)
    assert header.count(b"property float ") == 61 and f"element vertex {n}\n".encode() in header
    assert len(body) == 61 * 4 * n
    return dict(rows=n, sha256=preparer.sha(left), bytes=len(a), field_count=61,
                header_equal=True, vertex_order_and_all_field_bytes_equal=True)


def replace_generation(model, grow):
    references = []
    for group in model.optimizer.param_groups:
        old = group["params"][0]
        references.append(weakref.ref(old))
        state = model.optimizer.state.pop(old)
        values = torch.cat((old.detach(), old.detach()[:3]), dim=0) if grow else old.detach()[:-2].clone()
        new = torch.nn.Parameter(values)
        for name in ("exp_avg", "exp_avg_sq"):
            state[name] = (torch.cat((state[name], torch.zeros_like(state[name][:3])), dim=0)
                           if grow else state[name][:-2].clone())
        group["params"] = [new]
        model.optimizer.state[new] = state
        setattr(model, ATTRS[group["name"]][0], new)
        if group["name"] in ("xyz", "scaling", "rotation"): new.register_hook(protected_hook)
    return references


def verify(args):
    if not Path("/.dockerenv").is_file(): raise RuntimeError("Docker required")
    cuda = args.device == "cuda"
    device = torch.device("cuda:0" if cuda else "cpu")
    if cuda:
        torch.cuda.set_device(device)
        torch.cuda.set_per_process_memory_fraction((64 << 20) / torch.cuda.get_device_properties(device).total_memory, device=device)
    checks, ply_checks = [], []
    with tempfile.TemporaryDirectory(prefix="jbgs-memory-v3-fixture-") as temporary:
        temporary = Path(temporary)
        if args.source:
            source = temporary / "source"
            receipt = preparer.prepare(args.source, source, args.v1_directory, args.v2_directory)
        else:
            source = args.prepared_source.resolve(strict=True)
            receipt = json.loads((source / "jbgs_memory_recovery_receipt.json").read_text())
        v2 = preparer.load_v2(args.v2_directory)
        v1 = v2.load_preparer(args.v1_directory)
        assert receipt["status"] == "PASS_MEMORY_RECOVERY_RUNTIME_PREPARED"
        assert receipt["storage_version"] == 2 and receipt["resource_recovery_version"] == 3
        assert receipt["science_config_unchanged"] and not receipt["checkpoint_resume_supported"]
        assert v1.hashes(source) == receipt["destination_python_sha256"]
        assert preparer.sha(source / "jbgs_memory_recovery_v2_receipt.json") == receipt["v2_runtime_receipt_sha256"]
        assert preparer.sha(source / "jbgs_no_anchor_runtime_receipt.json") == v1.PARENT_RECEIPT_SHA256
        assert preparer.sha(source / "train.py") == preparer.TRAIN_SHA
        assert preparer.sha(source / "jbgs_memory_recovery_v2_base.py") == preparer.V2_HASHES["runtime_adapter.py"]
        assert preparer.sha(source / "jbgs_memory_recovery_v1_base.py") == v2.V1_ADAPTER_SHA256
        text = (source / "train.py").read_text()
        assert text.index("memory_recovery.before_forward") < text.index("render_pkg = render(viewpoint_cam")
        assert text.count("gaussians.optimizer.zero_grad(set_to_none=True)") == 1
        assert text.index("gaussians.optimizer.zero_grad(set_to_none=True)") < text.index("total_loss.backward()")
        assert text.index("gaussians.densify_and_prune") < text.index("memory_recovery.after_step_boundary") < text.index("if jbgs_state.after_step(locals())")
        checks.extend(["frozen_v1_v2_and_noanchor_bytes_preserved", "v2_train_renderer_and_original_before_backward_clear_unchanged"])
        base = load("jbgs_memory_recovery_v1_base", source / "jbgs_memory_recovery_v1_base.py")
        load("jbgs_pinned_storage", source / "jbgs_pinned_storage.py")
        load("jbgs_memory_recovery_v2_base", source / "jbgs_memory_recovery_v2_base.py")
        writer = load("jbgs_stream_ply", source / "jbgs_stream_ply.py")
        runtime = load("jbgs_memory_recovery", source / "jbgs_memory_recovery.py")
        if not cuda:
            storage = base.MomentStorage
            class CpuFixtureStorage(storage):
                def __init__(self):
                    super().__init__(require_cuda=False, pin_memory=False, budget_reader=lambda: (1 << 20, 2 << 30))
            base.MomentStorage = CpuFixtureStorage
        Native = native_class(source)
        # Native AST serialization is tested directly, without importing CUDA
        # renderer/extensions. Stress unusual finite float32 bits and >1 chunk.
        for n, chunk in ((0, 7), (1, 1), (19, 1), (19, 7), (19, 65536), (65537, 65536)):
            model = make_model(Native, n, torch.device("cpu"), optimizer=False)
            special = np.array([0, 0x80000000, 1, 0x007fffff, 0x00800000, 0x7f7fffff, 0xff7fffff, 0x3f800001], dtype=np.uint32).view(np.float32)
            with torch.no_grad():
                for attr, _ in ATTRS.values():
                    value = getattr(model, attr).view(-1)
                    count = min(len(value), len(special))
                    value[:count] = torch.from_numpy(special[:count])
            native_path, stream_path = temporary / "native.ply", temporary / "stream.ply"
            model.save_ply(str(native_path))
            model._jbgs_stream_ply_chunk_rows = chunk
            writer.save_ply(model, stream_path)
            result = compare_files(native_path, stream_path, n)
            result["chunk_rows"] = chunk
            ply_checks.append(result)
            del model
        checks.append("native_PLY_header61_fields_vertex_order_signed_zero_subnormal_extrema_SH_order_and_multichunk_SHA_equal")
        models = [make_model(Native, 8, device), make_model(Native, 8, device)]
        manifest = temporary / "sfm.json"
        manifest.write_text(json.dumps(dict(region="P1", fixture_only=True)))
        model_path = temporary / "model"
        model_path.mkdir()
        env = dict(args=SimpleNamespace(jbgs_sfm_initialization_manifest=str(manifest), jbgs_resume_full=False,
            start_checkpoint=None, model_path=str(model_path), iterations=8), first_iter=0, gaussians=models[1],
            lod_depth_maps={"toy": torch.ones((2, 2))}, da_depth_maps={"toy": torch.ones((2, 2))})
        recovery = runtime.initialize(env)
        assert models[1].save_ply.__func__ is writer.save_ply
        initialized = json.loads((model_path / "jbgs_memory_recovery/initialization.json").read_text())
        assert initialized["early_zero_grad_added"] and initialized["resource_recovery_version"] == 3
        assert json.loads((model_path / "jbgs_memory_recovery/v2_initialization.json").read_text())["early_zero_grad_added"] is False
        torch.manual_seed(39)
        total_released, retained_baseline_checks = 0, 0
        started = time.monotonic()
        for iteration in range(1, 9):
            previous = [weakref.ref(group["params"][0].grad) for group in models[1].optimizer.param_groups
                        if group["params"][0].grad is not None]
            amount = sum(group["params"][0].grad.numel() * 4 for group in models[1].optimizer.param_groups
                         if group["params"][0].grad is not None)
            if previous:
                assert all(group["params"][0].grad is not None for group in models[0].optimizer.param_groups)
                retained_baseline_checks += 1
            recovery.before_forward(models[1].optimizer, iteration)
            gc.collect()
            assert all(reference() is None for reference in previous)
            assert recovery.last_gradient_bytes_released == amount
            assert all(group["params"][0].grad is None for group in models[1].optimizer.param_groups)
            total_released += amount
            inputs = [torch.randn(group["params"][0].shape).to(device) for group in models[0].optimizer.param_groups]
            for model in models:
                loss = sum(((group["params"][0] * values).sin() + group["params"][0].square()).sum()
                           for group, values in zip(model.optimizer.param_groups, inputs))
                model.optimizer.zero_grad(set_to_none=True)
                loss.backward()
            del loss
            recovery.before_optimizer_step(models[1].optimizer, iteration)
            for model in models: model.optimizer.step()
            recovery.after_optimizer_step(models[1].optimizer, iteration)
            for left_group, right_group in zip(models[0].optimizer.param_groups, models[1].optimizer.param_groups):
                left, right = left_group["params"][0], right_group["params"][0]
                assert torch.equal(left, right) and torch.equal(left.grad, right.grad)
                for name in ("step", "exp_avg", "exp_avg_sq"):
                    assert torch.equal(models[0].optimizer.state[left][name], models[1].optimizer.state[right][name])
            del left, right, left_group, right_group
            if iteration in (3, 6):
                references = []
                for model in models: references.extend(replace_generation(model, grow=iteration == 3))
                gc.collect()
                assert all(reference() is None for reference in references)
            recovery.after_step_boundary(models[1].optimizer, iteration)
            if iteration in (1, 3, 6, 8):
                models[0].save_ply(str(temporary / "native_step.ply"))
                models[1].save_ply(str(temporary / "stream_step.ply"))
                ply_checks.append(dict(compare_files(temporary / "native_step.ply", temporary / "stream_step.ply", len(models[0]._xyz)), iteration=iteration, device=str(device)))
        elapsed = time.monotonic() - started
        if cuda:
            torch.cuda.synchronize(device)
            assert elapsed < 10, "Synthetic optimizer fixture exceeded10 seconds"
        else:
            assert not torch.cuda.is_initialized()
        assert retained_baseline_checks >= 4 and total_released > 0
        recovery.finalize()
        lifecycle = json.loads((model_path / "jbgs_memory_recovery/receipt.json").read_text())
        assert lifecycle["status"] == "PASS_MEMORY_LIFECYCLE_COMPLETED" and lifecycle["resource_recovery_version"] == 3
        assert lifecycle["early_gradient_clear_calls"] == 8 and lifecycle["storage_version"] == 2
        if cuda: assert all(row["pinned"] for row in lifecycle["pinned_cache"]["slots"])
        ply_audit = [json.loads(line) for line in (model_path / "jbgs_memory_recovery/ply_saves.jsonl").read_text().splitlines()]
        assert len(ply_audit) == 4 and all(row["status"] == "PASS_STREAMED_PLY_WRITTEN" for row in ply_audit)
        checks.extend(["previous_live_gradients_collected_before_forward_and_baseline_retains_them",
            "eight_steps_params_gradients_moments_counters_bitwise_equal", "protected_gradient_hooks_retained",
            "native_style_grow_prune_latest_parameter_generation_and_old_parameter_GC",
            "moment_GPU_state_retained_at_densification_and_capture_boundaries",
            "PLY_instance_binding_and_save_audit_bytes_exact", "v3_metadata_explicit_and_v2_records_preserved"])
        return dict(schema="jointbuildgs.geogs.resource_runtime_validation.v3",
            status="PASS_CUDA_RUNTIME_FIXTURE" if cuda else "PASS_CPU_RUNTIME_FIXTURE", scientific_verdict=None,
            checks=checks, torch_version=torch.__version__, numpy_version=np.__version__, device=str(device),
            storage_version=2, resource_recovery_version=3, early_gradient_release_verified=True,
            ply_serialization_byte_equal=True, ply_equivalence=ply_checks, ply_audit=ply_audit,
            original_scene_training_launched=False, synthetic_optimizer_steps=8, fixture_window_seconds=elapsed,
            no_reference_or_scene_input_access=True, full_state_resume_supported=False,
            prepared_source_python_sha256=receipt["destination_python_sha256"],
            prepared_amendment_sha256=preparer.sha(source / "jbgs_memory_recovery_receipt.json"),
            maximum_cuda_allocated_bytes=torch.cuda.max_memory_allocated(device) if cuda else None,
            cuda_allocator_cap_bytes=64 << 20 if cuda else None,
            peak_host_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024, lifecycle=lifecycle)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--source", type=Path)
    source.add_argument("--prepared-source", type=Path)
    parser.add_argument("--v1-directory", type=Path, required=True)
    parser.add_argument("--v2-directory", type=Path, required=True)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    if args.receipt.exists(): raise FileExistsError(args.receipt)
    try:
        result = verify(args)
    except Exception:
        result = dict(schema="jointbuildgs.geogs.resource_runtime_validation.v3", status="FAIL_RUNTIME_FIXTURE",
                      scientific_verdict=None, error=traceback.format_exc())
    result["validation_sources_sha256"] = {path.name: preparer.sha(path) for path in Path(__file__).parent.glob("*.py")}
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    with args.receipt.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps(dict(status=result["status"], receipt=str(args.receipt), checks=len(result.get("checks", [])), error=result.get("error"))))
    raise SystemExit(0 if result["status"].startswith("PASS_") else 1)
