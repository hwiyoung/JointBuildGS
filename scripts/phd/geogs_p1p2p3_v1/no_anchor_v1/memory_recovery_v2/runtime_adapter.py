"""v2 lifecycle wrapper: pinned cache storage, inherited v1 training boundaries."""
import sys

import jbgs_memory_recovery_v1_base as base
from jbgs_pinned_storage import make_storage_class

# Form the subclass before replacing the constructor used by v1 Recovery.
# Every original method continues using the same live optimizer/state objects.
base.MomentStorage = make_storage_class(base)


class Recovery(base.Recovery):
    def __init__(self, env):
        super().__init__(env)
        base.write_new(self.root / "pinned_cache_policy.json", dict(
            schema="jointbuildgs.geogs.pinned_cache_policy.v2", scientific_verdict=None,
            status="PASS_PINNED_CACHE_POLICY_INITIALIZED",
            source_amendment_sha256=self.amendment_sha256,
            storage="Twelve stable native-group/moment slots; flat power-of-two capacities and exact-shape views",
            transfers="Blocking D2H copy into reused pinned CPU buffers; original v1 blocking restore to each CUDA parameter device",
            retirement="No persistent Parameter/gradient/state-dict references; prune keeps high-water capacity; retired pinned blocks may remain in PyTorch host allocator cache",
            allocation_history_bound="Requested bytes per slot strictly below twice its largest capacity",
            host_guard="Before cache growth: cgroup.current + all new capacity + 3*parameter bytes snapshot reserve + 1 GiB <= min(existing finite cgroup.max,32 GiB)",
            host_limit_raised=False, science_config_unchanged=True, complete_resume_supported=False,
            source_math_and_stage_boundaries="Inherited frozen v1; no RNG, camera, optimizer math, gradient timing, snapshot or densification changes"))

    def log(self, iteration, event, **details):
        if iteration in (1, 2, 22000, 30000) or iteration % 100 == 0:
            super().log(iteration, event, pinned_cache=self.storage.cache_summary(), **details)

    def finalize(self):
        if self.closed:
            return
        self.closed = True
        passed = self.last_completed == self.total_iterations and self.storage.phase == "GPU_READY"
        payload = dict(schema=base.SCHEMA,
            status="PASS_MEMORY_LIFECYCLE_COMPLETED" if passed else "INCOMPLETE_MEMORY_LIFECYCLE",
            scientific_verdict=None, last_completed_iteration=self.last_completed,
            active_iteration=self.storage.iteration, phase=self.storage.phase,
            moments_restored=self.storage.phase == "GPU_READY",
            first_populated_moment_roundtrip_checked=self.storage.first_populated_cycle_checked,
            source_amendment_sha256=self.amendment_sha256, complete_resume_supported=False,
            storage_version=2, pinned_cache=self.storage.cache_summary())
        try:
            base.write_new(self.root / "receipt.json", payload)
        except Exception as error:
            print(f"[memory recovery v2] Could not persist lifecycle receipt: {error}", file=sys.stderr)


def initialize(env):
    return Recovery(env)
