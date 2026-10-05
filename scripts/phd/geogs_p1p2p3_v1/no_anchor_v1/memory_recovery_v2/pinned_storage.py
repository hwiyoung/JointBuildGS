"""Prototype storage policy; no live-runtime integration or optimizer changes.

The six native group names own 12 power-of-two host buffers. Parameter objects,
gradients and obsolete state dictionaries are never cached. A prune reuses high
water capacity; growth doubles capacity. PyTorch may cache retired allocations:
their cumulative requested bytes per slot are strictly below twice that slot's
largest allocation. This bounds requested storage history, not process RSS or
CUDA pinned-allocator metadata. There is no claimed host-cache purge.
"""
import hashlib
import importlib.util
from pathlib import Path

import torch

V1_SHA256 = "de4ba2a8c6a50efd670b195479b07962052c9cec10efd35d594c3ba9dc69c114"
GROUP_WIDTHS = {"xyz": 3, "f_dc": 3, "f_rest": 45, "opacity": 1, "scaling": 2, "rotation": 4}
GIB = 1024 ** 3


def cgroup_budget():
    """Read this container's v2 RAM budget; never change a host/container limit."""
    root = Path("/sys/fs/cgroup")
    limit = (root / "memory.max").read_text().strip()
    if limit == "max":
        raise RuntimeError("Pinned CUDA prototype requires an explicit finite container RAM limit")
    return int((root / "memory.current").read_text()), min(int(limit), 32 * GIB)


def load_v1(path):
    path = Path(path)
    if hashlib.sha256(path.read_bytes()).hexdigest() != V1_SHA256:
        raise ValueError("Frozen v1 moment adapter hash differs")
    spec = importlib.util.spec_from_file_location("jbgs_frozen_moment_v1", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def capacity_for(numel):
    return 1 << (max(1, numel) - 1).bit_length()


def make_storage_class(base):
    class PinnedMomentStorage(base.MomentStorage):
        """Same v1 records/restore guards; only the CPU destination is reused."""
        def __init__(self, require_cuda=True, pin_memory=True, budget_reader=None):
            super().__init__(require_cuda=require_cuda)
            if require_cuda and not pin_memory:
                raise ValueError("CUDA prototype requires pinned host buffers")
            self.pin_memory = pin_memory  # False is a CPU-only lifecycle test.
            self.slots = {}
            self.allocation_bytes_ever_requested = {}
            self.budget_reader = budget_reader or (cgroup_budget if require_cuda else None)
            self.last_growth_budget_check = None

        def group_entries(self, optimizer):
            names = [group.get("name") for group in optimizer.param_groups]
            if len(names) != 6 or set(names) != set(GROUP_WIDTHS):
                raise ValueError("Require the exact six distinct native group names")
            for group in optimizer.param_groups:
                if len(group["params"]) != 1:
                    raise ValueError("Native group must have exactly one current parameter")
                parameter = group["params"][0]
                if parameter.dtype != torch.float32 or parameter.ndim < 2:
                    raise ValueError("Only native float32 Gaussian tensors are supported")
                if parameter.numel() != parameter.shape[0] * GROUP_WIDTHS[group["name"]]:
                    raise ValueError("Native group width differs")
                state = optimizer.state.get(parameter, {})
                if state:
                    yield group["name"], parameter, state

        def check_growth_budget(self, entries):
            allocation_bytes = 0
            snapshot_bytes = 0
            for group_name, parameter, state in entries:
                # Full parameter plus two Adam moment copies. Other serializer
                # and allocator overhead must fit the additional 1-GiB margin.
                snapshot_bytes += 3 * parameter.numel() * parameter.element_size()
                for name in base.MOMENTS:
                    slot = self.slots.get((group_name, name))
                    if slot is None or slot.numel() < state[name].numel():
                        allocation_bytes += capacity_for(state[name].numel()) * state[name].element_size()
            if allocation_bytes and self.budget_reader is not None:
                current, limit = self.budget_reader()
                projected = current + allocation_bytes + snapshot_bytes + GIB
                self.last_growth_budget_check = dict(current_cgroup_bytes=current, limit_bytes=limit,
                    requested_new_capacity_bytes=allocation_bytes, snapshot_reserve_bytes=snapshot_bytes,
                    extra_margin_bytes=GIB, projected_bytes=projected, passed=projected <= limit)
                if projected > limit:
                    raise RuntimeError("PINNED_HOST_BUDGET_EXCEEDED: cache growth plus complete-snapshot reserve exceeds the unchanged RAM budget")

        def host_view(self, group_name, moment_name, moment):
            key = (group_name, moment_name)
            requested = moment.numel()
            slot = self.slots.get(key)
            if slot is None or slot.numel() < requested:
                # No copy of retired host contents is needed: the CUDA moments
                # are authoritative at this boundary. Remove the old reference
                # before allocating the larger capacity.
                self.slots.pop(key, None)
                del slot
                capacity = capacity_for(requested)
                slot = torch.empty(capacity, dtype=moment.dtype, device="cpu", pin_memory=self.pin_memory)
                self.slots[key] = slot
                self.allocation_bytes_ever_requested[key] = self.allocation_bytes_ever_requested.get(key, 0) + slot.numel() * slot.element_size()
            if self.pin_memory and not slot.is_pinned():
                raise RuntimeError("Host destination is not pinned")
            return slot[:requested].view(moment.shape)

        def offload(self, optimizer, iteration):
            if self.phase != "GPU_READY" or self.records is not None:
                raise RuntimeError("Cannot start a new cycle before restoring the previous one")
            # Validate all group identities before mutating storage placement.
            entries = list(self.group_entries(optimizer))
            total = self.assert_device(optimizer)
            self.check_growth_budget(entries)
            self.iteration = iteration
            self.phase = "OFFLOADING"
            records = []
            self.records = records
            check_roundtrip = total > 0 and not self.first_populated_cycle_checked
            with torch.no_grad():
                for group_name, parameter, state in entries:
                    step = state["step"]
                    record = dict(parameter=parameter, state=state, pointer=parameter.data_ptr(), step=step,
                                  step_copy=step.detach().clone() if torch.is_tensor(step) else step, hashes={})
                    for name in base.MOMENTS:
                        destination = self.host_view(group_name, name, state[name])
                        destination.copy_(state[name], non_blocking=False)
                        state[name] = destination
                        if check_roundtrip:
                            record["hashes"][name] = base.tensor_sha(state[name])
                    records.append(record)
            self.phase = "CPU_OFFLOADED"
            self.assert_device(optimizer, cpu=True)
            return total

        # The v1 restore method moves each state tensor to parameter.device with
        # non_blocking=False, checks pointers/step counters, and drops records
        # before optimizer.step. In CUDA mode the sole cached CPU allocation is
        # retained for the next D2H copy; no extra pageable CPU tensor is stored.

        def cache_summary(self):
            rows = []
            for key, tensor in self.slots.items():
                capacity_bytes = tensor.numel() * tensor.element_size()
                history_bytes = self.allocation_bytes_ever_requested[key]
                if history_bytes >= 2 * capacity_bytes:
                    raise RuntimeError("Power-of-two allocation-history bound failed")
                rows.append(dict(group=key[0], moment=key[1], capacity_elements=tensor.numel(),
                                 capacity_bytes=capacity_bytes, requested_history_bytes=history_bytes,
                                 pinned=tensor.is_pinned()))
            return dict(slots=rows, slot_count=len(rows),
                        live_capacity_bytes=sum(row["capacity_bytes"] for row in rows),
                        requested_allocation_history_bytes=sum(row["requested_history_bytes"] for row in rows),
                        last_growth_budget_check=self.last_growth_budget_check,
                        host_budget_policy="At growth, current cgroup RAM plus all requested new capacity plus 3*parameter bytes snapshot reserve plus 1 GiB must fit min(container limit,32 GiB); failure changes no scientific parameter.",
                        retained_parameter_or_gradient_references=False,
                        physical_pinned_allocator_cache_bytes_measured=False)

    return PinnedMomentStorage
