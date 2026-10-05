"""Derive a zero-reference audit invocation from the actual baseline command."""
import hashlib
import json
import os
from pathlib import Path
import runpy

invocation_path = Path("/invocation.json")
invocation = json.loads(invocation_path.read_text())
assert invocation["phase"] == "train" and invocation["condition"] == "D005_Pnative"
assert invocation["runtime_image_id"] == os.environ["JBGS_RUNTIME_IMAGE_ID"]
manifest = Path("/input/input_manifest.json")
assert hashlib.sha256(manifest.read_bytes()).hexdigest() == invocation["input_manifest_sha256"]
command = invocation["command"].copy()
assert command[:2] == ["python", "train.py"]
assert command[command.index("-s") + 1] == "/input/scene"
assert command[command.index("-m") + 1] == "/output/model"
assert "--jbgs_resume_full" not in command and "--jbgs_release_protection" not in command
assert command[command.index("--iterations") + 1] == "30000"
config = {"task_id": invocation["task_id"], "region": invocation["region"], "scientific_verdict": None,
          "purpose": "Actual regional complete-anchor restore, hooks, same-anchor PLY/render and one-step audit",
          "runtime_image_id": invocation["runtime_image_id"],
          "baseline_invocation_sha256": hashlib.sha256(invocation_path.read_bytes()).hexdigest(),
          "baseline_config_sha256": invocation["config_sha256"],
          "input_manifest_sha256": invocation["input_manifest_sha256"],
          "base_command": command, "resumed_options": ["--jbgs_resume_full", "/anchor/checkpoint.pth"],
          "training_controls_changed": False, "reference_mount": False}
layout_path = Path('/runtime_layout.json')
if layout_path.exists():
    layout = json.loads(layout_path.read_text())
    assert layout['allocator'] == os.environ.get('PYTORCH_CUDA_ALLOC_CONF')
    assert layout['scientific_config_sha256'] == invocation['config_sha256']
    config['runtime_layout_sha256'] = hashlib.sha256(layout_path.read_bytes()).hexdigest()
    config['runtime_revision'] = layout['revision']
    config['allocator'] = layout['allocator']
    config['baseline_allocator'] = invocation['environment'].get('PYTORCH_CUDA_ALLOC_CONF')
config_path = Path("/output/probe_config.json")
with config_path.open("x") as stream:
    json.dump(config, stream, indent=2)
os.environ["JBGS_PROBE_CONFIG"] = str(config_path)
runpy.run_path("/audit/runtime/probe_actual_restore.py", run_name="__main__")
