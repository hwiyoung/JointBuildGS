"""Render the evaluation depth maps of one trained model with the calibrated stage-2 cameras (run in
jointbuildgs:geogs-conf-guided-v1 with the fork at /source).

  python render_depths.py --model_dir /s2/runs/<COND>/model --iteration 30000 --out /s2/eval/<COND>/render_30000
                          [--camera_scene /s2/runs/P_M_N/scene]

Every condition, including the official GeoGS ones (O), is rendered through the same calibrated cameras (PINHOLE K of
the stage-1 maps, principal point restored by jbgs_camera_adapter) so that D is comparable with the P/M/G maps.
O was trained with GeoGS's centred principal point; its renders here show its 3D geometry through the true cameras.
Outputs per view: <view>_depth.npy (surf_depth, float32 camera-Z metres, 0 = empty), <view>_alpha.npy (float16),
<view>_rgb.png; receipt.json (PLY sha256, gaussians, cameras)."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, "/source")
import cv2  # noqa: E402
import numpy as np  # noqa: E402
import torch  # noqa: E402
from arguments import ModelParams, PipelineParams  # noqa: E402
from gaussian_renderer import render  # noqa: E402
from scene import Scene  # noqa: E402
from scene.gaussian_model import GaussianModel  # noqa: E402

ap = argparse.ArgumentParser()
mp = ModelParams(ap)
pp = PipelineParams(ap)
ap.add_argument("--model_dir", required=True)
ap.add_argument("--iteration", type=int, required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--camera_scene", default="/s2/runs/P_M_N/scene")
a = ap.parse_args()
a.source_path, a.model_path, a.eval = a.camera_scene, a.model_dir, True   # cameras from the calibrated scene, PLY from the model
dataset, pipe = mp.extract(a), pp.extract(a)
ply = Path(a.model_dir) / "point_cloud" / f"iteration_{a.iteration}" / "point_cloud.ply"
if not ply.exists():
    raise SystemExit(f"missing {ply}")
if not (Path(a.camera_scene) / "jbgs_calibration.json").exists():
    raise SystemExit("camera scene has no jbgs_calibration.json (calibrated cameras required)")

gaussians = GaussianModel(dataset.sh_degree)
with torch.no_grad():
    scene = Scene(dataset, gaussians, load_iteration=a.iteration, shuffle=False)
    bg = torch.tensor([1, 1, 1] if dataset.white_background else [0, 0, 0], dtype=torch.float32, device="cuda")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    cams = scene.getTrainCameras() + scene.getTestCameras()
    views = {}
    for cam in cams:
        if getattr(cam, "jbgs_source_intrinsics", None) is None:
            raise SystemExit(f"camera {cam.image_name} is not calibrated")
        pkg = render(cam, gaussians, pipe, bg)
        D = pkg["surf_depth"].squeeze(0).float().cpu().numpy()
        alpha = pkg["rend_alpha"].squeeze(0).cpu().numpy().astype(np.float16)
        np.save(out / f"{cam.image_name}_depth.npy", D.astype(np.float32))
        np.save(out / f"{cam.image_name}_alpha.npy", alpha)
        rgb = (pkg["render"].clamp(0, 1).permute(1, 2, 0).cpu().numpy() * 255).astype(np.uint8)
        cv2.imwrite(str(out / f"{cam.image_name}_rgb.png"), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
        views[cam.image_name] = dict(split="test" if cam in scene.getTestCameras() else "train",
                                     size=[int(D.shape[1]), int(D.shape[0])], rendered_px=int((D > 0).sum()))
receipt = dict(model=a.model_dir, iteration=a.iteration, ply=str(ply), ply_sha256=hashlib.sha256(ply.read_bytes()).hexdigest(),
               gaussians=int(gaussians.get_xyz.shape[0]), camera_scene=a.camera_scene, calibrated=True,
               depth="surf_depth float32 camera-Z metres (0 = empty)", views=views, scientific_verdict=None)
(out / "receipt.json").write_text(json.dumps(receipt, indent=1))
print(json.dumps({k: receipt[k] for k in ("model", "iteration", "gaussians")}), len(views), "views")
