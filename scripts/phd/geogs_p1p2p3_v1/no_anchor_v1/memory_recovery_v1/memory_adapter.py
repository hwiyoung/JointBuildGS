"""CPU storage for depth caches and Adam moments; original CUDA arithmetic stays."""
import atexit
import hashlib
import json
from pathlib import Path
import sys

import torch


MOMENTS = ("exp_avg", "exp_avg_sq")
SCHEMA = "jointbuildgs.geogs.memory_recovery_lifecycle.v1"


def tensor_sha(tensor):
    return hashlib.sha256(tensor.detach().cpu().contiguous().numpy().tobytes()).hexdigest()


def write_new(path, payload):
    with path.open("x") as stream:
        json.dump(payload, stream, indent=2, allow_nan=False)
        stream.write("\n")


class MomentStorage:
    """No optimizer math. Resolve live parameters anew after every densification."""
    def __init__(self, require_cuda=True):
        self.require_cuda = require_cuda
        self.phase = "GPU_READY"
        self.iteration = 0
        self.records = None
        self.first_populated_cycle_checked = False

    def entries(self, optimizer):
        if not isinstance(optimizer, torch.optim.Adam):
            raise ValueError("Only the native torch.optim.Adam is supported")
        for group in optimizer.param_groups:
            if group.get("amsgrad") or group.get("differentiable") or group.get("capturable"):
                raise ValueError("Unexpected Adam mode")
            for parameter in group["params"]:
                if self.require_cuda and parameter.device.type != "cuda":
                    raise ValueError("Gaussian parameters must remain CUDA tensors")
                state = optimizer.state.get(parameter, {})
                if not state:
                    continue  # Fresh optimizer before its first native step.
                if set(state) != {"step", *MOMENTS}:
                    raise ValueError("Unexpected Adam state fields")
                for name in MOMENTS:
                    moment = state[name]
                    if moment.shape != parameter.shape or moment.dtype != parameter.dtype or moment.requires_grad:
                        raise ValueError("Adam moment shape/dtype/gradient flag differs")
                yield parameter, state

    def assert_device(self, optimizer, cpu=False):
        total = 0
        for parameter, state in self.entries(optimizer):
            expected = torch.device("cpu") if cpu else parameter.device
            for name in MOMENTS:
                value = state[name]
                if value.device != expected:
                    raise RuntimeError("Adam moment is on the wrong lifecycle device")
                total += value.numel() * value.element_size()
        return total

    def offload(self, optimizer, iteration):
        if self.phase != "GPU_READY" or self.records is not None:
            raise RuntimeError("Cannot start a new cycle before restoring the previous one")
        self.iteration = iteration
        self.phase = "OFFLOADING"
        total = self.assert_device(optimizer)
        # These temporary records are released before the optimizer step and any
        # parameter replacement. Never retain an old densification generation.
        records = []
        self.records = records
        check_roundtrip = total > 0 and not self.first_populated_cycle_checked
        with torch.no_grad():
            for parameter, state in self.entries(optimizer):
                step = state["step"]
                record = dict(parameter=parameter, state=state, pointer=parameter.data_ptr(), step=step,
                              step_copy=step.detach().clone() if torch.is_tensor(step) else step,
                              hashes={})
                for name in MOMENTS:
                    state[name] = state[name].to(device="cpu", non_blocking=False)
                    if check_roundtrip:
                        record["hashes"][name] = tensor_sha(state[name])
                records.append(record)
        self.phase = "CPU_OFFLOADED"
        self.assert_device(optimizer, cpu=True)
        return total

    def restore(self, optimizer, iteration):
        if self.phase != "CPU_OFFLOADED" or self.iteration != iteration:
            raise RuntimeError("Restore does not match an active memory cycle")
        self.phase = "RESTORING"
        live = list(self.entries(optimizer))
        if len(live) != len(self.records):
            raise RuntimeError("Optimizer state changed during forward/backward")
        checked = False
        with torch.no_grad():
            for (parameter, state), record in zip(live, self.records):
                if (parameter is not record["parameter"] or state is not record["state"]
                        or parameter.data_ptr() != record["pointer"] or state["step"] is not record["step"]):
                    raise RuntimeError("Parameter/state identity or step object changed before optimizer.step")
                step = state["step"]
                if torch.is_tensor(step):
                    if not torch.equal(step, record["step_copy"]):
                        raise RuntimeError("Adam step counter changed during storage transfer")
                elif step != record["step_copy"]:
                    raise RuntimeError("Adam step counter changed during storage transfer")
                for name in MOMENTS:
                    state[name] = state[name].to(device=parameter.device, non_blocking=False)
                    if record["hashes"]:
                        if tensor_sha(state[name]) != record["hashes"][name]:
                            raise RuntimeError("First populated Adam roundtrip changed tensor bytes")
                        checked = True
        self.records = None
        self.phase = "GPU_READY"
        if checked:
            self.first_populated_cycle_checked = True
        return self.assert_device(optimizer)


class Recovery:
    def __init__(self, env):
        args = env["args"]
        manifest = json.loads(Path(args.jbgs_sfm_initialization_manifest).read_text())
        if manifest.get("region") not in ("P1", "P2", "P3") or env["first_iter"] != 0 or args.jbgs_resume_full or args.start_checkpoint:
            raise ValueError("This amendment supports only a fresh P1/P2/P3 retry")
        self.root = Path(args.model_path) / "jbgs_memory_recovery"
        self.root.mkdir(exist_ok=False)
        self.storage = MomentStorage()
        self.last_completed = 0
        self.total_iterations = args.iterations
        self.closed = False
        self.optimizer = env["gaussians"].optimizer
        self.storage.assert_device(self.optimizer)
        cache = {}
        for role in ("lod_depth_maps", "da_depth_maps"):
            values = env[role]
            if any(t.device.type != "cpu" or t.dtype != torch.float32 or t.requires_grad for t in values.values()):
                raise ValueError("Depth cache must retain native float32 values on CPU")
            cache[role] = dict(count=len(values), bytes=sum(t.numel() * t.element_size() for t in values.values()))
        amendment = Path(__file__).with_name("jbgs_memory_recovery_receipt.json")
        self.amendment_sha256 = hashlib.sha256(amendment.read_bytes()).hexdigest()
        write_new(self.root / "initialization.json", dict(schema=SCHEMA,
            status="PASS_MEMORY_RECOVERY_INITIALIZED", scientific_verdict=None, region=manifest["region"],
            source_amendment_sha256=self.amendment_sha256, depth_caches=cache,
            moments="CPU only during forward/backward; original parameter device before native CUDA Adam",
            model_parameters_device="cuda", step_counters_and_math_unchanged=True,
            early_zero_grad_added=False, complete_resume_supported=False))
        atexit.register(self.finalize)

    def log(self, iteration, event, **details):
        if iteration in (1, 2, 22000, 30000) or iteration % 100 == 0:
            payload = dict(schema=SCHEMA, scientific_verdict=None, iteration=iteration, event=event,
                           phase=self.storage.phase, allocated_cuda_bytes=torch.cuda.memory_allocated(), **details)
            with (self.root / "trace.jsonl").open("a") as stream:
                stream.write(json.dumps(payload, allow_nan=False) + "\n")

    def before_forward(self, optimizer, iteration):
        amount = self.storage.offload(optimizer, iteration)
        self.log(iteration, "BEFORE_FORWARD_MOMENTS_CPU", moment_bytes=amount)

    def depths_to_device(self, lod, da, device, iteration):
        if self.storage.phase != "CPU_OFFLOADED" or device.type != "cuda":
            raise RuntimeError("Depth transfer must precede the CUDA refinement computation")
        result, checks = [], []
        for role, value in (("lod", lod), ("da", da)):
            if value is None:
                result.append(None)
                continue
            if value.device.type != "cpu" or value.dtype != torch.float32:
                raise ValueError("Unexpected depth cache placement or dtype")
            copied = value.to(device=device, non_blocking=False)
            if iteration == 1:
                expected = tensor_sha(value)
                if tensor_sha(copied) != expected:
                    raise RuntimeError("Selected depth CPU-to-CUDA transfer changed bytes")
                checks.append(dict(role=role, shape=list(value.shape), dtype=str(value.dtype), sha256=expected))
            result.append(copied)
        if iteration == 1:
            write_new(self.root / "first_depth_transfer.json", dict(schema=SCHEMA,
                status="PASS_SELECTED_DEPTH_TRANSFER", scientific_verdict=None, maps=checks))
        return tuple(result)

    def before_optimizer_step(self, optimizer, iteration):
        amount = self.storage.restore(optimizer, iteration)
        self.log(iteration, "BEFORE_NATIVE_CUDA_OPTIMIZER_STEP", moment_bytes=amount,
                 first_populated_moment_roundtrip_checked=self.storage.first_populated_cycle_checked)

    def after_step_boundary(self, optimizer, iteration):
        if self.storage.phase != "GPU_READY" or self.storage.records is not None:
            raise RuntimeError("Offloaded state cannot reach densification/capture boundary")
        amount = self.storage.assert_device(optimizer)
        self.last_completed = iteration
        self.log(iteration, "AFTER_DENSIFICATION_BEFORE_COMPLETE_CAPTURE", moment_bytes=amount,
                 first_populated_moment_roundtrip_checked=self.storage.first_populated_cycle_checked)

    def after_optimizer_step(self, optimizer, iteration):
        if self.storage.phase != "GPU_READY" or self.storage.records is not None:
            raise RuntimeError("Native Adam did not finish with restored moments")
        self.storage.assert_device(optimizer)

    def finalize(self):
        if self.closed:
            return
        self.closed = True
        passed = self.last_completed == self.total_iterations and self.storage.phase == "GPU_READY"
        payload = dict(schema=SCHEMA, status="PASS_MEMORY_LIFECYCLE_COMPLETED" if passed else "INCOMPLETE_MEMORY_LIFECYCLE",
                       scientific_verdict=None, last_completed_iteration=self.last_completed,
                       active_iteration=self.storage.iteration, phase=self.storage.phase,
                       moments_restored=self.storage.phase == "GPU_READY",
                       first_populated_moment_roundtrip_checked=self.storage.first_populated_cycle_checked,
                       source_amendment_sha256=self.amendment_sha256, complete_resume_supported=False)
        try:
            write_new(self.root / "receipt.json", payload)
        except Exception as error:
            print(f"[memory recovery] Could not persist lifecycle receipt: {error}", file=sys.stderr)


def initialize(env):
    return Recovery(env)
