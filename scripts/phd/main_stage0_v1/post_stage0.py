"""PHD-MAIN-STAGE0-v1 5.4 post step of one stage-0 training (jointbuildgs:geogs-conf-guided-v1, GPU; /source = fork r12,
/p = this payload, /dr discard payload (ro), /repo (ro)).

  python post_stage0.py <run>        # e.g. b1_LoD2; reads /p/stage0/<run>/model at iteration 30,000

1. evaluation views (test split): RGB, expected depth (surf_depth), rendered normal (rend_normal, world), accumulated opacity
   -> /p/stage0/<run>/post/eval/<view>.npz (+ <view>_rgb.png)
2. TSDF of the training views (config stage0.post.tsdf): expected depth, Open3D ScalableTSDFVolume through the fork's
   GaussianExtractor.extract_mesh_bounded, voxel 0.05 m, sdf_trunc 0.25 m, depth_trunc 300 m; fusion limited to the box
   rectangle + 2 m and z in [5th percentile of the box GT z - 5 m, max GT z + 5 m] (pixels whose rendered point lies outside
   -> depth 0, the r10 box mask) -> /p/stage0/<run>/post/mesh_tsdf.ply
3. Gaussians at 30,000: counts by origin, opacity quantiles, protected -> post/post.json (with the seconds of each step)
scientific_verdict: null."""
import json
import sys
import time
from argparse import ArgumentParser
from pathlib import Path

import cv2
import numpy as np
import open3d as o3d
import torch

sys.path.insert(0, "/source")
from arguments import ModelParams, PipelineParams  # noqa: E402
from gaussian_renderer import GaussianModel, render  # noqa: E402
from scene import Scene  # noqa: E402
from utils.mesh_utils import GaussianExtractor  # noqa: E402

run = sys.argv[1]
SC = json.loads(Path("/repo/configs/phd/main_stage0_v1/stage0_v1.json").read_text())["stage0"]
P = Path("/p"); R = P / "stage0" / run
rec = json.loads((R / "receipt.json").read_text())
prior, site = rec["prior"], rec["site"]
its = int(SC["iterations"])
OUT = R / "post"; (OUT / "eval").mkdir(parents=True, exist_ok=True)
t0 = time.time(); times = {}
I = P / "fork_inputs/s61" / site
parser = ArgumentParser(); mp = ModelParams(parser); pp = PipelineParams(parser)
args = parser.parse_args(["-s", str(I / f"scene_{prior}"), "-m", str(R / "model"), "--eval", "-r", "1"])
dataset, pipe = mp.extract(args), pp.extract(args)
gaussians = GaussianModel(dataset.sh_degree)
scene = Scene(dataset, gaussians, load_iteration=its, shuffle=False)
bg = torch.tensor([0, 0, 0], dtype=torch.float32, device="cuda")
train, test = scene.getTrainCameras(), scene.getTestCameras()
times["load"] = round(time.time() - t0, 1)

# 1. evaluation views
with torch.no_grad():
    for cam in test:
        pkg = render(cam, gaussians, pipe, bg)
        rgb = (pkg["render"].clamp(0, 1).permute(1, 2, 0).cpu().numpy() * 255).astype(np.uint8)
        cv2.imwrite(str(OUT / "eval" / f"{cam.image_name}_rgb.png"), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
        np.savez_compressed(OUT / "eval" / f"{cam.image_name}.npz", depth=pkg["surf_depth"].squeeze(0).cpu().numpy().astype(np.float32),
                            normal=pkg["rend_normal"].permute(1, 2, 0).cpu().numpy().astype(np.float16),
                            alpha=pkg["rend_alpha"].squeeze(0).cpu().numpy().astype(np.float16))
times["eval_renders"] = round(time.time() - t0, 1)

# 2. TSDF of the training views in the box
rng = json.loads((Path("/dr/s02_box") / site / "range.json").read_text())
poly = np.asarray(rng["polygon_local"], np.float64)
gz = np.load(Path("/dr/s52/box_gt") / site / "gt_points.npz")["xyz"][:, 2].astype(np.float64)
m = SC["post"]
BOX = np.array([[poly[:, 0].min() - 2.0, poly[:, 1].min() - 2.0, float(np.percentile(gz, 5)) - 5.0],
                [poly[:, 0].max() + 2.0, poly[:, 1].max() + 2.0, float(gz.max()) + 5.0]])


@torch.no_grad()
def box_mask(cam, depth):   # the r10 mesh box mask (mesh_r10.box_mask)
    Hc, Wc = depth.shape[-2:]
    ndc2pix = torch.tensor([[Wc / 2, 0, 0, (Wc - 1) / 2], [0, Hc / 2, 0, (Hc - 1) / 2], [0, 0, 0, 1]]).float().cuda().T
    intr = (cam.projection_matrix @ ndc2pix)[:3, :3].T
    c2w = torch.linalg.inv(cam.world_view_transform.T)
    v, u = torch.meshgrid(torch.arange(Hc, device="cuda").float(), torch.arange(Wc, device="cuda").float(), indexing="ij")
    x = (u - intr[0, 2]) / intr[0, 0]; y = (v - intr[1, 2]) / intr[1, 1]
    d = depth.reshape(Hc, Wc).cuda()
    Pc = torch.stack([x * d, y * d, d, torch.ones_like(d)], -1).reshape(-1, 4)
    Pw = (Pc @ c2w.T)[:, :3].reshape(Hc, Wc, 3)
    lo = torch.as_tensor(BOX[0], device="cuda").float(); hi = torch.as_tensor(BOX[1], device="cuda").float()
    inside = ((Pw >= lo) & (Pw <= hi)).all(-1) & (d > 0)
    return inside.float()[None]


ext = GaussianExtractor(gaussians, render, pipe, bg_color=[0, 0, 0])
ext.gaussians.active_sh_degree = 0
ext.reconstruction(list(train))
kept = 0.0
for i, cam in enumerate(ext.viewpoint_stack):
    mk = box_mask(cam, ext.depthmaps[i]); cam.gt_alpha_mask = mk.cpu(); kept += float(mk.mean())
times["tsdf_renders"] = round(time.time() - t0, 1)
mesh = ext.extract_mesh_bounded(voxel_size=0.05, sdf_trunc=0.25, depth_trunc=300.0)
for cam in ext.viewpoint_stack:
    cam.gt_alpha_mask = None
o3d.io.write_triangle_mesh(str(OUT / "mesh_tsdf.ply"), mesh)
times["tsdf"] = round(time.time() - t0, 1)

# 3. Gaussians at the end
dump = np.load(R / "model/dump" / f"iteration_{its}" / "gaussians.npz")
op = dump["opacity"]; org = dump["origin"]; lock = dump["locked"]


def q(x):
    return [float(v) for v in np.quantile(x, [0.1, 0.5, 0.9])] if len(x) else None


res = dict(run=run, site=site, prior=prior, iteration=its, box=BOX.tolist(), tsdf=dict(voxel_m=0.05, sdf_trunc_m=0.25, depth_trunc_m=300.0,
           views=len(train), mean_share_of_pixels_in_box=kept / max(len(train), 1), vertices=len(mesh.vertices), triangles=len(mesh.triangles)),
           eval_views=[c.image_name for c in test],
           gaussians=dict(n=int(len(op)), prior=int((org == 1).sum()), image=int((org == 0).sum()), protected=int(lock.sum()),
                          opacity_q_prior=q(op[org == 1]), opacity_q_image=q(op[org == 0]),
                          share_prior_ge05=float((op[org == 1] >= 0.5).mean()) if (org == 1).any() else None),
           seconds=times, scientific_verdict=None)
(OUT / "post.json").write_text(json.dumps(res, indent=1))
print(json.dumps({k: res[k] for k in ("run", "tsdf", "gaussians", "seconds")}))
