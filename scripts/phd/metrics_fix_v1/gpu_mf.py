"""PHD-MAIN-METRICS-FIX-v1 4.7 GPU step (jointbuildgs:geogs-conf-guided-v1; /source = fork r12 (ro), /s0 the stage-0 payload (ro),
/mt the trial payload (ro), /dr (ro), /out this payload, /repo (ro)). No training: the stage-0 models are only read and rendered.

  python gpu_mf.py option1 <run>     10 views 25 m in front of the main unseen wall (config virtual_view_test.option1.cameras),
                                     all Gaussians
  python gpu_mf.py option2 <run>     the trial's 16 views (the fork's create_virtual_cameras_for_completion aimed at the unseen
                                     patch centres, rings of 8, distance_scale 1.5), every view rendered with only the Gaussians
                                     inside the stage-0 TSDF box

Both: TSDF of the rendered expected depth of the 203 training views + the virtual views, the stage-0 box mask, voxel 0.10 m
(sdf_trunc 0.5 m, depth_trunc 300 m) as the trial's virtual-view mesh -> /out/virtual/<option>/<run>/mesh_virtual.ply,
virtual.json (cameras, unseen patch centres seen per virtual view, seconds, peak host memory). scientific_verdict: null."""
import copy
import json
import resource
import sys
import time
from argparse import ArgumentParser
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import open3d as o3d
import torch

sys.path.insert(0, "/source")
from arguments import ModelParams, PipelineParams  # noqa: E402
from gaussian_renderer import GaussianModel, render  # noqa: E402
from scene import Scene  # noqa: E402
from utils.mesh_utils import GaussianExtractor  # noqa: E402
from utils.render_utils import create_virtual_cameras_for_completion  # noqa: E402

FC = json.loads(Path("/repo/configs/phd/metrics_fix_v1/metrics_fix_v1.json").read_text())
VT = FC["virtual_view_test"]
SITE = "B173nb_b10"
ITS = 30000
S0, MT, OUT = Path("/s0"), Path("/mt"), Path("/out")
BOX = np.array(json.loads((S0 / "stage0/b1_LoD2/post/post.json").read_text())["box"])


def load(run):
    prior = json.loads((S0 / "stage0" / run / "receipt.json").read_text())["prior"]
    parser = ArgumentParser()
    mp, pp = ModelParams(parser), PipelineParams(parser)
    args = parser.parse_args(["-s", str(S0 / "fork_inputs/s61" / SITE / f"scene_{prior}"), "-m", str(S0 / "stage0" / run / "model"), "--eval", "-r", "1"])
    dataset, pipe = mp.extract(args), pp.extract(args)
    g = GaussianModel(dataset.sh_degree)
    scene = Scene(dataset, g, load_iteration=ITS, shuffle=False)
    return dataset, pipe, g, scene


def cam_mats(cam):
    Hc, Wc = cam.image_height, cam.image_width
    ndc2pix = torch.tensor([[Wc / 2, 0, 0, (Wc - 1) / 2], [0, Hc / 2, 0, (Hc - 1) / 2], [0, 0, 0, 1]]).float().cuda().T
    intr = (cam.projection_matrix @ ndc2pix)[:3, :3].T
    c2w = torch.linalg.inv(cam.world_view_transform.T)
    return intr, c2w


@torch.no_grad()
def box_mask(cam, depth):   # the stage-0 post box mask
    intr, c2w = cam_mats(cam)
    Hc, Wc = depth.shape[-2:]
    v, u = torch.meshgrid(torch.arange(Hc, device="cuda").float(), torch.arange(Wc, device="cuda").float(), indexing="ij")
    x = (u - intr[0, 2]) / intr[0, 0]
    y = (v - intr[1, 2]) / intr[1, 1]
    d = depth.reshape(Hc, Wc).cuda().float()
    Pc = torch.stack([x * d, y * d, d, torch.ones_like(d)], -1).reshape(-1, 4)
    Pw = (Pc @ c2w.T)[:, :3].reshape(Hc, Wc, 3)
    lo = torch.as_tensor(BOX[0], device="cuda").float()
    hi = torch.as_tensor(BOX[1], device="cuda").float()
    return (((Pw >= lo) & (Pw <= hi)).all(-1) & (d > 0)).float()[None]


def look_cameras(ref, specs):
    """virtual cameras with the fork helper's construction (right = up x forward, columns right, up, forward) at given centres."""
    out = []
    for i, s in enumerate(specs):
        C = np.asarray(s["centre"], np.float64)
        look = np.asarray(s["look_at"], np.float64) - C
        look /= np.linalg.norm(look)
        up = np.array([0, 0, 1.0])
        if abs(np.dot(look, up)) > 0.99:
            up = np.array([0, 1.0, 0])
        right = np.cross(up, look)
        right /= np.linalg.norm(right)
        up = np.cross(look, right)
        up /= np.linalg.norm(up)
        c2w = np.eye(4)
        c2w[:3, 0], c2w[:3, 1], c2w[:3, 2], c2w[:3, 3] = right, up, look, C
        w2c = np.linalg.inv(c2w)
        cam = copy.deepcopy(ref)
        cam.world_view_transform = torch.from_numpy(w2c.T).float().cuda()
        cam.full_proj_transform = cam.world_view_transform.unsqueeze(0).bmm(cam.projection_matrix.unsqueeze(0)).squeeze(0)
        cam.camera_center = cam.world_view_transform.inverse()[3, :3]
        cam.image_name = f"option1_{i:03d}"
        out.append(cam)
    return out


def subset(dataset, g, keep):
    h = GaussianModel(dataset.sh_degree)
    h.active_sh_degree = g.active_sh_degree
    for name in ("_xyz", "_features_dc", "_features_rest", "_scaling", "_rotation", "_opacity"):
        setattr(h, name, torch.nn.Parameter(getattr(g, name).detach()[keep].clone(), requires_grad=False))
    return h


def main(option, run):
    t0 = time.time()
    times = {}
    O = OUT / "virtual" / option / run
    O.mkdir(parents=True, exist_ok=True)
    dataset, pipe, g, scene = load(run)
    train = list(scene.getTrainCameras())
    times["load"] = round(time.time() - t0, 1)
    un = np.load(MT / "defs/unseen.npz")
    if option == "option1":
        virtual = look_cameras(train[0], VT["option1"]["cameras"])
        model = g
        kept = int(g.get_xyz.shape[0])
    else:
        C = torch.as_tensor(un["centre"], device="cuda").float()
        fake = SimpleNamespace(completed_mask=torch.ones(C.shape[0], dtype=torch.bool, device="cuda"), get_xyz=C)
        with torch.no_grad():
            virtual = create_virtual_cameras_for_completion(gaussians=fake, reference_cameras=train, n_virtual_cams=8, distance_scale=1.5)
        xyz = g.get_xyz.detach()
        lo = torch.as_tensor(BOX[0], device="cuda").float()
        hi = torch.as_tensor(BOX[1], device="cuda").float()
        inside = ((xyz >= lo) & (xyz <= hi)).all(1)
        model = subset(dataset, g, inside)
        kept = int(inside.sum())
    ext = GaussianExtractor(model, render, pipe, bg_color=[0, 0, 0])
    ext.gaussians.active_sh_degree = 0
    ext.reconstruction(train + virtual)
    seen = []
    cen = un["centre"]
    lab = un["label_inferred"]
    for i, cam in enumerate(ext.viewpoint_stack):
        mk = box_mask(cam, ext.depthmaps[i])
        cam.gt_alpha_mask = mk.cpu()
        if i >= len(train):
            intr, c2w = cam_mats(cam)
            w2c = torch.linalg.inv(c2w).cpu().numpy()
            K = intr.cpu().numpy()
            Pc = cen @ w2c[:3, :3].T + w2c[:3, 3]
            zc = Pc[:, 2]
            with np.errstate(divide="ignore", invalid="ignore"):
                u = np.round(K[0, 0] * Pc[:, 0] / zc + K[0, 2]).astype(np.int64)
                v = np.round(K[1, 1] * Pc[:, 1] / zc + K[1, 2]).astype(np.int64)
            H, W = cam.image_height, cam.image_width
            ins = (zc > 0.1) & (u >= 0) & (u < W) & (v >= 0) & (v < H)
            D = ext.depthmaps[i].reshape(H, W).numpy()
            Dp = np.where(ins, D[np.clip(v, 0, H - 1), np.clip(u, 0, W - 1)], 0.0)
            s = ins & ((Dp <= 0) | (zc <= Dp + 0.5))
            seen.append(dict(view=i - len(train), centre=cam.camera_center.cpu().numpy().tolist(), inside=int(ins.sum()), seen=int(s.sum()),
                             seen_below_roof=int((s & (lab == 0)).sum()), seen_above_roof=int((s & (lab == 1)).sum()), box_share=float(mk.mean())))
    times["renders"] = round(time.time() - t0, 1)
    mesh = ext.extract_mesh_bounded(voxel_size=VT["voxel_m"], sdf_trunc=VT["sdf_trunc_m"], depth_trunc=300.0)
    for cam in ext.viewpoint_stack:
        cam.gt_alpha_mask = None
    o3d.io.write_triangle_mesh(str(O / "mesh_virtual.ply"), mesh)
    times["tsdf"] = round(time.time() - t0, 1)
    res = dict(option=option, run=run, voxel_m=VT["voxel_m"], views_train=len(train), views_virtual=len(virtual), gaussians_rendered=kept,
               virtual=seen, vertices=len(mesh.vertices), triangles=len(mesh.triangles), seconds=times,
               peak_host_gb=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024 ** 2, 2), scientific_verdict=None)
    (O / "virtual.json").write_text(json.dumps(res, indent=1))
    print(json.dumps({k: v for k, v in res.items() if k != "virtual"}))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
