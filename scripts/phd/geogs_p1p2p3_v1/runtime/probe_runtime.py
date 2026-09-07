"""Import-only native runtime probe; never loads a scene or starts training."""
import importlib
import importlib.metadata
import contextlib
import argparse
import json
import os
import platform
import subprocess
import sys

import torch

parser = argparse.ArgumentParser()
parser.add_argument("--source-root")
args = parser.parse_args()
if args.source_root:
    sys.path.insert(0, args.source_root)

modules = {}
module_names = ["diff_surfel_rasterization", "simple_knn._C", "open3d", "py4dgeo", "lpips"]
if args.source_root:
    module_names += ["gaussian_renderer", "utils.mesh_utils", "metrics"]
for module in module_names:
    with contextlib.redirect_stdout(sys.stderr):
        loaded = importlib.import_module(module)
    modules[module] = str(loaded.__file__)

plot_probe = None
if args.source_root:
    import numpy as np
    from utils.general_utils import colormap
    painted = colormap(np.zeros((32, 32), dtype=np.float32), cmap="turbo")
    assert painted.shape == (3, 32, 32) and torch.isfinite(painted).all()
    plot_probe = "PASS_NATIVE_COLORMAP"

print(json.dumps({
    "task_id": "PHD-GEOGS-P1P2P3-v1",
    "kind": "native_dependency_import_probe",
    "scientific_verdict": None,
    "scene_training_runs": 0,
    "python": platform.python_version(),
    "torch": torch.__version__,
    "torch_cuda": torch.version.cuda,
    "ld_library_path": os.environ.get("LD_LIBRARY_PATH"),
    "ld_preload": os.environ.get("LD_PRELOAD"),
    "plot_probe": plot_probe,
    "cuda_available": torch.cuda.is_available(),
    "device_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
    "modules": modules,
    "versions": {name: importlib.metadata.version(name) for name in (
        "torch", "torchvision", "numpy", "open3d", "py4dgeo", "lpips", "Pillow", "matplotlib")},
    "nvcc": subprocess.check_output(["nvcc", "--version"], text=True).strip(),
}, indent=2))
