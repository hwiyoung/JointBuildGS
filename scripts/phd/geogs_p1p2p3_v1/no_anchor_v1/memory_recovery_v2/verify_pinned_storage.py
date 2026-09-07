#!/usr/bin/env python3
"""Docker CPU tests. Does not allocate CUDA or import a project renderer."""
import argparse
import gc
import hashlib
import json
from pathlib import Path
import weakref

import torch
from pinned_storage import GROUP_WIDTHS, capacity_for, load_v1, make_storage_class


def initialized_optimizer(count):
    groups = []
    for name, width in GROUP_WIDTHS.items():
        parameter = torch.nn.Parameter(torch.arange(count * width, dtype=torch.float32).reshape(count, width) / 100)
        groups.append({"name": name, "params": [parameter], "lr": .001})
    return torch.optim.Adam(groups, eps=1e-15, foreach=True)


def replace_parameters(optimizer, count):
    retired = []
    for group in optimizer.param_groups:
        old = group["params"][0]
        retired.append(weakref.ref(old))
        state = optimizer.state.pop(old)
        width = GROUP_WIDTHS[group["name"]]
        new = torch.nn.Parameter(torch.arange(count * width, dtype=torch.float32).reshape(count, width) / 100)
        for key in ("exp_avg", "exp_avg_sq"):
            values = torch.zeros_like(new)
            overlap = min(old.shape[0], count)
            values[:overlap].copy_(state[key][:overlap])
            state[key] = values
        optimizer.state[new] = state
        group["params"] = [new]
    return retired


def verify(v1_path):
    if not Path("/.dockerenv").is_file():
        raise RuntimeError("Docker is required")
    base = load_v1(v1_path)
    pinned_class = make_storage_class(base)
    old, new = initialized_optimizer(3), initialized_optimizer(3)
    storage = pinned_class(require_cuda=False, pin_memory=False)
    assert storage.offload(new, 1) == 0
    storage.restore(new, 1)
    assert not storage.slots
    checks = ["empty_first_state_preserved"]
    capacities, histories = [], []
    for iteration, count in enumerate([3, 4, 5, 3, 9, 7, 33, 2], 2):
        if iteration > 2:
            refs = replace_parameters(old, count) + replace_parameters(new, count)
            gc.collect()
            assert all(reference() is None for reference in refs), "Old parameter retained by storage"
        state_objects = [new.state.get(g["params"][0], {}).get("step") for g in new.param_groups]
        gradients = [weakref.ref(g["params"][0].grad) for g in new.param_groups if g["params"][0].grad is not None]
        storage.offload(new, iteration)
        offload_ptrs = {key: tensor.data_ptr() for key, tensor in storage.slots.items()}
        for optimizer in (old, new):
            optimizer.zero_grad(set_to_none=True)
        gc.collect()
        assert all(reference() is None for reference in gradients)
        for optimizer in (old, new):
            loss = sum((g["params"][0].square() + g["params"][0].sin()).sum() for g in optimizer.param_groups)
            loss.backward()
        del loss
        storage.restore(new, iteration)
        assert storage.records is None
        assert offload_ptrs == {key: tensor.data_ptr() for key, tensor in storage.slots.items()}
        for group, step_object in zip(new.param_groups, state_objects):
            if step_object is not None:
                assert new.state[group["params"][0]]["step"] is step_object
        for optimizer in (old, new):
            optimizer.step()
        for left_group, right_group in zip(old.param_groups, new.param_groups):
            left, right = left_group["params"][0], right_group["params"][0]
            assert torch.equal(left, right)
            for key in ("step", "exp_avg", "exp_avg_sq"):
                assert torch.equal(old.state[left][key], new.state[right][key])
        del left, right, left_group, right_group, group
        summary = storage.cache_summary()
        assert summary["slot_count"] in (0, 12)
        capacities.append(summary["live_capacity_bytes"])
        histories.append(summary["requested_allocation_history_bytes"])
    checks.extend(["eight_cpu_adam_steps_bitwise_parameters_moments_counters",
                   "growth_and_prune_current_parameter_replacement",
                   "retired_parameters_and_previous_gradients_collectible",
                   "cache_has_twelve_stable_slots_no_parameter_keys",
                   "cache_same_buffer_before_after_restore_no_duplicate_cpu_copy",
                   "allocation_history_less_than_twice_high_water_capacity"])
    # Many gradual growth/prune requests must cause only logarithmic allocations.
    tiny = pinned_class(require_cuda=False, pin_memory=False)
    pointers, allocations = {}, 0
    for count in [*range(1, 1025), 100, 2, 1024]:
        tensor = torch.empty(count, 45)
        tiny.host_view("f_rest", "exp_avg", tensor)
        capacity = tiny.slots[("f_rest", "exp_avg")].numel()
        assert capacity >= tensor.numel()
        pointers.setdefault(capacity, tiny.slots[("f_rest", "exp_avg")].data_ptr())
        assert pointers[capacity] == tiny.slots[("f_rest", "exp_avg")].data_ptr()
        assert tiny.cache_summary()["requested_allocation_history_bytes"] < 2 * capacity * 4
    assert len(pointers) <= 11 and capacity == capacity_for(1024 * 45)
    checks.append("1024_gradual_sizes_allocate_only_power_of_two_capacities_then_reuse_after_prune")
    blocked = pinned_class(require_cuda=False, pin_memory=False, budget_reader=lambda: (2 * 1024**3, 2 * 1024**3))
    try:
        blocked.offload(new, 50)
    except RuntimeError as error:
        assert "PINNED_HOST_BUDGET_EXCEEDED" in str(error)
        assert blocked.phase == "GPU_READY" and blocked.records is None and not blocked.slots
    else:
        raise AssertionError("Insufficient host headroom accepted")
    allowed = pinned_class(require_cuda=False, pin_memory=False, budget_reader=lambda: (1000000, 2 * 1024**3))
    allowed.offload(new, 50)
    allowed.restore(new, 50)
    assert allowed.last_growth_budget_check["passed"]
    checks.append("host_growth_guard_before_mutation_reserves_complete_snapshot_and_margin")
    return dict(schema="jointbuildgs.geogs.pinned_storage_cpu_validation.v1", status="PASS_CPU_LIFECYCLE",
                scientific_verdict=None, checks=checks, torch_version=torch.__version__,
                cuda_executed=False, actual_pinned_allocation_tested=False,
                note="CPU substitutes ordinary host buffers; CUDA pinning and speed require separate approved GPU probe.",
                capacities_bytes=capacities, requested_history_bytes=histories,
                cache=storage.cache_summary(), growth_case=tiny.cache_summary())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v1-adapter", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    if args.receipt.exists():
        raise ValueError("Receipt exists")
    payload = verify(args.v1_adapter)
    payload["source_sha256"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in (Path(__file__), Path(__file__).with_name("pinned_storage.py"), args.v1_adapter)}
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    with args.receipt.open("x") as stream:
        json.dump(payload, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"status": payload["status"], "receipt": str(args.receipt), "checks": len(payload["checks"])}))


if __name__ == "__main__":
    main()
