"""Tiny synthetic forward/backward check of the unchanged native CUDA renderer.

No optimizer step, project scene, prior, or evaluation reference is used.
"""
import argparse
import contextlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import torch

parser = argparse.ArgumentParser()
parser.add_argument("--source-root", required=True, type=Path)
args = parser.parse_args()
sys.path.insert(0, str(args.source_root))
from gaussian_renderer import render
from scene.gaussian_model import GaussianModel
from scene.cameras import Camera
from utils.graphics_utils import BasicPointCloud

torch.manual_seed(0)
points = np.array([[-0.2, -0.2, 2.0], [0.2, -0.2, 2.1],
                   [-0.2, 0.2, 2.0], [0.2, 0.2, 2.1]], dtype=np.float32)
pcd = BasicPointCloud(points=points, colors=np.full_like(points, 0.5), normals=np.zeros_like(points))
gaussians = GaussianModel(3)
with contextlib.redirect_stdout(sys.stderr):
    gaussians.create_from_pcd(pcd, 1.0)
camera = Camera(colmap_id=0, R=np.eye(3), T=np.zeros(3), FoVx=1.0, FoVy=1.0,
                image=torch.zeros(3, 32, 32), gt_alpha_mask=None,
                image_name="synthetic_runtime_probe", uid=0)
pipe = SimpleNamespace(convert_SHs_python=False, compute_cov3D_python=False,
                       depth_ratio=0.0, debug=False)
torch.cuda.reset_peak_memory_stats()
result = render(camera, gaussians, pipe, torch.zeros(3, device="cuda"))
loss = result["render"].square().mean() + 0.001 * result["surf_depth"].square().mean()
loss.backward()
torch.cuda.synchronize()
gradients = {}
for name in ("_xyz", "_features_dc", "_opacity", "_scaling", "_rotation"):
    grad = getattr(gaussians, name).grad
    if grad is None or not torch.isfinite(grad).all():
        raise RuntimeError(f"Nonfinite or absent native gradient: {name}")
    gradients[name] = float(grad.norm().item())
if gradients["_xyz"] == 0 or gradients["_opacity"] == 0:
    raise RuntimeError("Degenerate native gradient probe")
print(json.dumps({"task_id": "PHD-GEOGS-P1P2P3-v1", "scientific_verdict": None,
                  "kind": "synthetic_native_forward_backward", "status": "PASS",
                  "optimizer_steps": 0, "project_scene_training_runs": 0,
                  "loss": float(loss.item()), "gradient_norms": gradients,
                  "visible_gaussians": int(result["visibility_filter"].sum().item()),
                  "peak_gpu_allocated_bytes": torch.cuda.max_memory_allocated()}, indent=2))
