"""v3 resource lifecycle: inherit v2 storage; clear prior gradients before forward."""
import json
import sys

import jbgs_memory_recovery_v2_base as v2
from jbgs_stream_ply import bind

base = v2.base


def supersede(path, preserved_name, **changes):
    """Preserve inherited evidence bytes and write explicit v3 canonical metadata."""
    inherited = json.loads(path.read_text())
    preserved = path.with_name(preserved_name)
    if preserved.exists():
        raise FileExistsError(preserved)
    path.rename(preserved)
    base.write_new(path, dict(inherited, **changes))


class Recovery(v2.Recovery):
    def __init__(self, env):
        self.gradient_clear_calls = 0
        self.last_gradient_bytes_released = 0
        super().__init__(env)
        bind(env["gaussians"], self.root / "ply_saves.jsonl")
        supersede(self.root / "initialization.json", "v2_initialization.json",
            resource_recovery_version=3, early_zero_grad_added=True,
            early_zero_grad_scope="Previous step parameter gradients only, after its native densification and before next forward",
            original_before_backward_zero_grad_retained=True, stream_ply_instance_binding=True,
            initial_step0_save_remains_native=True)
        supersede(self.root / "pinned_cache_policy.json", "v2_pinned_cache_policy.json",
            resource_recovery_version=3,
            source_math_and_stage_boundaries="Inherited frozen v2 optimizer/loss/densification/capture boundaries; previous parameter gradients additionally released before forward",
            ply_serialization="Same native61-field float32 binary PLY bytes, bounded65536-row CPU staging")

    def before_forward(self, optimizer, iteration):
        if optimizer is not self.optimizer or self.storage.phase != "GPU_READY" or iteration != self.last_completed + 1:
            raise RuntimeError("Early gradient release requires the completed prior native boundary")
        released = sum(parameter.grad.numel() * parameter.grad.element_size()
                       for group in optimizer.param_groups for parameter in group["params"]
                       if parameter.grad is not None)
        optimizer.zero_grad(set_to_none=True)
        if any(parameter.grad is not None for group in optimizer.param_groups for parameter in group["params"]):
            raise RuntimeError("Previous parameter gradients were not released")
        self.gradient_clear_calls += 1
        self.last_gradient_bytes_released = released
        self.log(iteration, "BEFORE_FORWARD_PREVIOUS_PARAMETER_GRADIENTS_RELEASED",
                 previous_gradient_tensor_bytes_released=released,
                 original_before_backward_zero_grad_retained=True, resource_recovery_version=3)
        super().before_forward(optimizer, iteration)

    def finalize(self):
        if self.closed:
            return
        super().finalize()
        try:
            supersede(self.root / "receipt.json", "v2_lifecycle_receipt.json",
                resource_recovery_version=3, early_gradient_clear_calls=self.gradient_clear_calls,
                last_previous_gradient_tensor_bytes_released=self.last_gradient_bytes_released,
                original_before_backward_zero_grad_retained=True, stream_ply_audit="ply_saves.jsonl")
        except Exception as error:
            print(f"[memory recovery v3] Could not persist v3 lifecycle amendment: {error}", file=sys.stderr)


def initialize(env):
    return Recovery(env)
