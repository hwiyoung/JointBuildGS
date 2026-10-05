"""CPU verification by default; --device cuda requires a free GPU.

No GeoGS training/render is launched. CUDA mode exercises only tiny Adam tensors.
"""
import argparse
import gc
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import weakref

import torch


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify(source=None, cuda=False):
    if not Path("/.dockerenv").is_file():
        raise RuntimeError("Docker is required")
    folder = Path(__file__).parent
    module = load("memory_adapter_test", folder / "memory_adapter.py")
    preparer = load("memory_preparer_test", folder / "prepare_runtime.py")
    device = torch.device("cuda:0" if cuda else "cpu")
    allocator_cap = 64 << 20 if cuda else None
    if cuda:
        total = torch.cuda.get_device_properties(device).total_memory
        torch.cuda.set_per_process_memory_fraction(allocator_cap / total, device=device)
    torch.manual_seed(17)
    checks = []
    prepared_train_sha256 = None
    if source:
        with tempfile.TemporaryDirectory(prefix="jbgs-memory-copy-") as temporary:
            destination = Path(temporary) / "source"
            receipt = preparer.prepare(source, destination)
            assert receipt["status"] == "PASS_MEMORY_RECOVERY_RUNTIME_PREPARED"
            assert receipt["modified_or_added_python"] == ["jbgs_memory_recovery.py", "train.py"]
            prepared_train_sha256 = preparer.sha(destination / "train.py")
            assert preparer.sha(destination / "jbgs_no_anchor_runtime_receipt.json") == preparer.PARENT_RECEIPT_SHA256
            text = (destination / "train.py").read_text()
            assert text.index("memory_recovery.before_forward") < text.index("render_pkg = render(viewpoint_cam")
            assert text.index("total_loss.backward()") < text.index("memory_recovery.before_optimizer_step") < text.index("gaussians.optimizer.step()")
            assert text.index("memory_recovery.after_optimizer_step") < text.index("scene.save(iteration)") < text.index("gaussians.densify_and_prune")
            assert text.index("gaussians.densify_and_prune") < text.index("memory_recovery.after_step_boundary") < text.index("if jbgs_state.after_step(locals())")
            assert text.count("gaussians.optimizer.zero_grad(set_to_none=True)") == 1
            try:
                preparer.prepare(source, destination)
            except ValueError:
                pass
            else:
                raise AssertionError("Destination overwrite accepted")
            try:
                preparer.patch_train(text)
            except ValueError:
                pass
            else:
                raise AssertionError("Double patch accepted")
        checks.append("hash_bound_copy_parent_receipt_preserved_exact_lifecycle_patch_positions")
    dimensions = (3, 3, 45, 1, 2, 4)
    first = [torch.nn.Parameter(torch.randn(8, width, device=device)) for width in dimensions]
    second = [torch.nn.Parameter(p.detach().clone()) for p in first]
    optimizers = [torch.optim.Adam([{"params": [p], "lr": .001} for p in parameters], eps=1e-15, foreach=True)
                  for parameters in (first, second)]
    storage = module.MomentStorage(require_cuda=cuda)
    parameters = [first, second]
    for iteration in range(1, 7):
        offloaded = storage.offload(optimizers[1], iteration)
        assert storage.phase == "CPU_OFFLOADED"
        assert offloaded == storage.assert_device(optimizers[1], cpu=True)
        if iteration == 1:
            assert offloaded == 0
        # The migration audit must not keep previous parameter gradients alive.
        previous_grad = weakref.ref(parameters[1][0].grad) if parameters[1][0].grad is not None else None
        inputs = [torch.randn_like(p) for p in parameters[0]]
        losses = [sum(((p * x).sin() + p.square()).sum() for p, x in zip(group, inputs)) for group in parameters]
        for optimizer, loss in zip(optimizers, losses):
            optimizer.zero_grad(set_to_none=True)
            if optimizer is optimizers[1] and previous_grad is not None:
                gc.collect()
                assert previous_grad() is None
            loss.backward()
        gradients_before_restore = [p.grad for p in parameters[1]]
        pointers = [p.data_ptr() for p in parameters[1]]
        restored = storage.restore(optimizers[1], iteration)
        assert restored == offloaded and storage.records is None and storage.phase == "GPU_READY"
        assert all(p.grad is old and p.data_ptr() == pointer for p, old, pointer in zip(parameters[1], gradients_before_restore, pointers))
        for optimizer in optimizers:
            optimizer.step()
        storage.assert_device(optimizers[1])
        for left, right in zip(*parameters):
            assert torch.equal(left, right)
            for key in ("step", "exp_avg", "exp_avg_sq"):
                assert torch.equal(optimizers[0].state[left][key], optimizers[1].state[right][key])
        del gradients_before_restore
        # Simulate native prune/append parameter replacement after a full step.
        if iteration == 3:
            for index, optimizer in enumerate(optimizers):
                replacement = []
                for group in optimizer.param_groups:
                    previous = group["params"][0]
                    state = optimizer.state.pop(previous)
                    next_parameter = torch.nn.Parameter(torch.cat((previous.detach()[1:], previous.detach()[:2]), dim=0))
                    for name in module.MOMENTS:
                        state[name] = torch.cat((state[name][1:], torch.zeros_like(state[name][:2])), dim=0)
                    group["params"] = [next_parameter]
                    optimizer.state[next_parameter] = state
                    replacement.append(next_parameter)
                parameters[index] = replacement
    assert storage.first_populated_cycle_checked
    checks += ["six_step_parameter_gradient_moment_counter_bitwise_equivalence_foreach",
               "empty_first_state_then_dynamic_parameter_replacement",
               "previous_gradients_not_retained_by_offload_records",
               "first_populated_moment_roundtrip_byte_hash_verified"]
    guard = module.MomentStorage(require_cuda=cuda)
    try:
        guard.restore(optimizers[1], 7)
    except RuntimeError:
        pass
    else:
        raise AssertionError("Unmatched restore accepted")
    guard.offload(optimizers[1], 7)
    state = optimizers[1].state[parameters[1][0]]
    state["step"].add_(1)
    try:
        guard.restore(optimizers[1], 7)
    except RuntimeError:
        assert guard.phase == "RESTORING"
    else:
        raise AssertionError("Changed step counter accepted")
    checks.append("invalid_cycle_and_changed_step_counter_rejected")
    depth = torch.tensor([[1., float("nan")], [-0., float("inf")]], dtype=torch.float32)
    transferred = depth.to(device=device, non_blocking=False)
    assert module.tensor_sha(depth) == module.tensor_sha(transferred)
    checks.append("depth_float32_nan_inf_signed_zero_bytes_preserved")
    return dict(status="PASS_CUDA_TOY_EQUIVALENCE" if cuda else "PASS_CPU_MEMORY_RECOVERY_VALIDATION",
                scientific_verdict=None, checks=checks, geogs_training_executed=False,
                gpu_used=cuda, cuda_equivalence="PASS_TINY_FIXTURE" if cuda else "POSTPONED_BUSY_GPUS",
                torch_version=torch.__version__, allocator_peak_bytes=torch.cuda.max_memory_allocated() if cuda else None,
                cuda_allocator_cap_bytes=allocator_cap, cap_excludes_cuda_driver_context=True,
                parent_runtime_receipt_sha256=preparer.PARENT_RECEIPT_SHA256,
                runtime_preparation_tested=bool(source), prepared_train_sha256=prepared_train_sha256,
                source_sha256={name: hashlib.sha256((folder / name).read_bytes()).hexdigest()
                               for name in ("prepare_runtime.py", "memory_adapter.py", "verify_memory_recovery.py")})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    result = verify(args.source, args.device == "cuda")
    if args.receipt:
        with args.receipt.open("x") as stream:
            json.dump(result, stream, indent=2)
            stream.write("\n")
    print(json.dumps(result, indent=2))
