"""Record an allocator-only runtime candidate and audit an existing exact anchor.

The process environment must select the allocator before importing torch. This
probe verifies restoration and one native step; it cannot establish that the
later, larger model will avoid the observed out-of-memory failure.
"""
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import time

EXPECTED_ALLOCATOR = "backend:native,max_split_size_mb:128"
assert os.environ.get("PYTORCH_CUDA_ALLOC_CONF") == EXPECTED_ALLOCATOR

import torch

output = Path("/output")
started = time.time()
assert torch.__version__ == "2.1.2+cu121"
assert torch.cuda.memory.get_allocator_backend() == "native"
tiny = torch.empty(1, device="cuda")
torch.cuda.synchronize()
initial_stats = torch.cuda.memory_stats()
assert initial_stats["max_split_size"] == 128 * 1024 * 1024
del tiny
receipt = {
    "task_id": "PHD-GEOGS-P1P2P3-v1",
    "scientific_verdict": None,
    "scope": "Allocator-only existing P1 anchor restore and one-step probe",
    "runtime_image_id": os.environ["JBGS_RUNTIME_IMAGE_ID"],
    "allocator_environment": EXPECTED_ALLOCATOR,
    "allocator_backend": torch.cuda.memory.get_allocator_backend(),
    "torch_version": torch.__version__,
    "torch_cuda_version": torch.version.cuda,
    "device_name": torch.cuda.get_device_name(),
    "visible_device_driver": subprocess.check_output(
        ["nvidia-smi", "--query-gpu=uuid,driver_version", "--format=csv,noheader"], text=True
    ).strip(),
    "initial_allocator_stats": dict(initial_stats),
    "probe_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    "training_source_changed": False,
    "training_controls_changed": False,
    "references_mounted": False,
    "late_training_oom_recovery_proven": False,
}
with (output / "allocator_preflight.json").open("x") as stream:
    json.dump(receipt, stream, indent=2, allow_nan=False)
exit_code = 1
try:
    runpy.run_path("/audit/runtime/prepare_regional_probe.py", run_name="__main__")
    exit_code = 0
except SystemExit as exc:
    exit_code = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
    raise
finally:
    receipt.update(
        exit_code=exit_code,
        wall_seconds=time.time() - started,
        final_allocator_stats=dict(torch.cuda.memory_stats()),
        status="PASS_ANCHOR_AND_ONE_STEP_ONLY" if exit_code == 0 else "FAIL_PROBE",
    )
    config_path = output / "probe_config.json"
    if config_path.exists():
        receipt["probe_config_sha256"] = hashlib.sha256(config_path.read_bytes()).hexdigest()
    with (output / "allocator_probe_receipt.json").open("x") as stream:
        json.dump(receipt, stream, indent=2, allow_nan=False)
