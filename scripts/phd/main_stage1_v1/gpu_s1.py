"""PHD-MAIN-STAGE1-v1 GPU steps after training (jointbuildgs:geogs-conf-guided-v1; /source = fork r12 (ro), /s0 stage-0 payload (ro),
/dr (ro), /out this payload, /repo (ro), /weights (ro)). No training: models are only read and rendered.

  python gpu_s1.py samepath <site> <prior>    the registered prior surface ray-cast at the site's training views and fused by the
                                              stage-0 TSDF path (0.05 m, sdf 0.25 m, the stage-0 box mask) -> /out/stage1/<site>/samepath_<prior>/mesh.ply
  python gpu_s1.py post <site> <result>       = scripts/phd/main_stage0_v1/post_stage0.py for one stage-1 training (evaluation renders,
                                              TSDF of the training views 0.05 m in the stage-0 box, Gaussians by origin) + image quality of
                                              the evaluation views (PSNR, SSIM, LPIPS-VGG) -> /out/stage1/<site>/<result>/post/
  python gpu_s1.py run <site> <result>        = the trial's run steps: (a) evaluation-view points, (b) floater pixels, (c) the virtual-view
                                              mesh of option 2 (the fix 4.7: the trial's 16 views aimed at the site's unseen wall patches,
                                              only the Gaussians inside the box, TSDF 0.10 m) where defs/<site>/unseen.npz exists
                                              -> /out/stage1/<site>/<result>/gpu/
Models: the stage-0 trainings of B173nb_b10 (prop_<prior>_s0 / s1 = b1 / b2) are read from /s0 (their post exists there); every other
model from /out/stage1/<site>/<result>/model. scientific_verdict: null."""
import json
import resource
import sys
import time
from argparse import ArgumentParser
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import open3d as o3d
import torch

sys.path.insert(0, "/source")
from arguments import ModelParams, PipelineParams  # noqa: E402
from gaussian_renderer import GaussianModel, render  # noqa: E402
from scene import Scene  # noqa: E402
from utils.mesh_utils import GaussianExtractor, to_cam_open3d  # noqa: E402
from utils.render_utils import create_virtual_cameras_for_completion  # noqa: E402

ITS = 30000
S0, OUT, DR = Path("/s0"), Path("/out"), Path("/dr")
PCFG = json.loads(Path("/repo/configs/phd/main_prep_measure_v1/prep_v5.json").read_text())
_a = np.deg2rad(PCFG["frame"]["u_axis_angle_degrees_ccw_from_easting"])
BASIS = np.array([[np.cos(_a), np.sin(_a)], [np.sin(_a), -np.cos(_a)]])
STAGE0 = {"prop_LoD2_s0": "b1_LoD2", "prop_LoD2_s1": "b2_LoD2", "prop_ALS_s0": "b1_ALS", "prop_ALS_s1": "b2_ALS"}
FLOAT = dict(opacity=0.5, above_m=3.0, pixel_depth_m=0.5)
B173NB = "B173nb_b10"


def box_of(site):
    """the stage-0 post box: box range rectangle + 2 m, z from the 5th percentile of the box GT - 5 m to its maximum + 5 m (s52 GT)."""
    rng = json.loads((DR / "s02_box" / site / "range.json").read_text())
    poly = np.asarray(rng["polygon_local"], np.float64)
    gz = np.load(DR / "s52/box_gt" / site / "gt_points.npz")["xyz"][:, 2].astype(np.float64)
    return np.array([[poly[:, 0].min() - 2.0, poly[:, 1].min() - 2.0, float(np.percentile(gz, 5)) - 5.0],
                     [poly[:, 0].max() + 2.0, poly[:, 1].max() + 2.0, float(gz.max()) + 5.0]])


def model_dir(site, res):
    if site == B173NB and res in STAGE0:
        return S0 / "stage0" / STAGE0[res] / "model"
    return OUT / "stage1" / site / res / "model"


def scene_prior(site, res):
    if site == B173NB and res in STAGE0:
        return json.loads((S0 / "stage0" / STAGE0[res] / "receipt.json").read_text())["prior"]
    rec = OUT / "stage1" / site / res / "receipt.json"
    return json.loads(rec.read_text())["scene_prior"]


def load(site, prior, mdir, its=ITS):
    parser = ArgumentParser()
    mp, pp = ModelParams(parser), PipelineParams(parser)
    args = parser.parse_args(["-s", str(S0 / "fork_inputs/s61" / site / f"scene_{prior}"), "-m", str(mdir), "--eval", "-r", "1"])
    dataset, pipe = mp.extract(args), pp.extract(args)
    g = GaussianModel(dataset.sh_degree)
    scene = Scene(dataset, g, load_iteration=its, shuffle=False)
    return dataset, pipe, g, scene


def cam_mats(cam):
    Hc, Wc = cam.image_height, cam.image_width
    ndc2pix = torch.tensor([[Wc / 2, 0, 0, (Wc - 1) / 2], [0, Hc / 2, 0, (Hc - 1) / 2], [0, 0, 0, 1]]).float().cuda().T
    intr = (cam.projection_matrix @ ndc2pix)[:3, :3].T
    c2w = torch.linalg.inv(cam.world_view_transform.T)
    return intr, c2w


@torch.no_grad()
def unproject(cam, depth):
    intr, c2w = cam_mats(cam)
    Hc, Wc = depth.shape[-2:]
    v, u = torch.meshgrid(torch.arange(Hc, device="cuda").float(), torch.arange(Wc, device="cuda").float(), indexing="ij")
    x = (u - intr[0, 2]) / intr[0, 0]
    y = (v - intr[1, 2]) / intr[1, 1]
    d = depth.reshape(Hc, Wc).cuda().float()
    Pc = torch.stack([x * d, y * d, d, torch.ones_like(d)], -1).reshape(-1, 4)
    return (Pc @ c2w.T)[:, :3].reshape(Hc, Wc, 3)


@torch.no_grad()
def box_mask(cam, depth, BOX):
    Pw = unproject(cam, depth)
    d = depth.reshape(Pw.shape[:2]).cuda()
    lo = torch.as_tensor(BOX[0], device="cuda").float()
    hi = torch.as_tensor(BOX[1], device="cuda").float()
    return (((Pw >= lo) & (Pw <= hi)).all(-1) & (d > 0)).float()[None]


def subset(dataset, g, keep):
    h = GaussianModel(dataset.sh_degree)
    h.active_sh_degree = g.active_sh_degree
    for name in ("_xyz", "_features_dc", "_features_rest", "_scaling", "_rotation", "_opacity"):
        setattr(h, name, torch.nn.Parameter(getattr(g, name).detach()[keep].clone(), requires_grad=False))
    return h


def peak_gb():
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024 ** 2, 2)


def in_eval(site, xy, margin=0.0):
    tr = np.load(OUT / "defs" / site / "top_raster.npz")
    uv = np.asarray(xy, np.float64)[:, :2] @ BASIS.T
    eu, ev = tr["eval_u"], tr["eval_v"]
    return (uv[:, 0] >= eu[0] - margin) & (uv[:, 0] <= eu[1] + margin) & (uv[:, 1] >= ev[0] - margin) & (uv[:, 1] <= ev[1] + margin)


def top_of(site, xy):
    tr = np.load(OUT / "defs" / site / "top_raster.npz")
    q = np.floor((np.asarray(xy, np.float64)[:, :2] - tr["lo"]) / float(tr["cell"])).astype(np.int64)
    g = tr["grid"]
    ok = (q[:, 0] >= 0) & (q[:, 0] < g.shape[1]) & (q[:, 1] >= 0) & (q[:, 1] < g.shape[0])
    return np.where(ok, g[np.clip(q[:, 1], 0, g.shape[0] - 1), np.clip(q[:, 0], 0, g.shape[1] - 1)], np.nan)


# ------------------------------------------------------------------------------------------------ same-path prior mesh
def samepath(site, prior):
    t0 = time.time()
    O = OUT / "stage1" / site / f"samepath_{prior}"
    O.mkdir(parents=True, exist_ok=True)
    (O / "scene_tmp").mkdir(exist_ok=True)
    dataset, pipe, g, scene = load(site, prior, O / "scene_tmp", its=None)
    train = list(scene.getTrainCameras())
    BOX = box_of(site)
    P = np.load(OUT / "defs" / site / f"prior_{prior}.npz")
    sc = o3d.t.geometry.RaycastingScene()
    sc.add_triangles(o3d.core.Tensor(P["V"].astype(np.float32)), o3d.core.Tensor(P["F"].astype(np.uint32)))
    ext = GaussianExtractor(g, render, pipe, bg_color=[0, 0, 0])
    ext.clean()
    ext.viewpoint_stack = train
    hit_share, kept = [], 0.0
    for cam, co in zip(train, to_cam_open3d(train)):
        K = co.intrinsic.intrinsic_matrix
        E = np.asarray(co.extrinsic)
        c2w = np.linalg.inv(E)
        H, W = cam.image_height, cam.image_width
        u, v = np.meshgrid(np.arange(W, dtype=np.float64), np.arange(H, dtype=np.float64))
        dc = np.stack([(u - K[0, 2]) / K[0, 0], (v - K[1, 2]) / K[1, 1], np.ones_like(u)], -1).reshape(-1, 3)
        dw = dc @ c2w[:3, :3].T
        rays = np.concatenate([np.broadcast_to(c2w[:3, 3], dw.shape), dw], 1).astype(np.float32)
        t = sc.cast_rays(o3d.core.Tensor(rays))["t_hit"].numpy().reshape(H, W)
        depth = np.where(np.isfinite(t), t, 0.0).astype(np.float32)
        hit_share.append(float(np.isfinite(t).mean()))
        ext.depthmaps.append(torch.from_numpy(depth)[None])
        ext.rgbmaps.append(torch.zeros(3, H, W))
    for i, cam in enumerate(ext.viewpoint_stack):
        mk = box_mask(cam, ext.depthmaps[i], BOX)
        cam.gt_alpha_mask = mk.cpu()
        kept += float(mk.mean())
    t1 = time.time()
    mesh = ext.extract_mesh_bounded(voxel_size=0.05, sdf_trunc=0.25, depth_trunc=300.0)
    for cam in ext.viewpoint_stack:
        cam.gt_alpha_mask = None
    o3d.io.write_triangle_mesh(str(O / "mesh.ply"), mesh)
    res = dict(site=site, prior=prior, views=len(train), mean_hit_share=float(np.mean(hit_share)), mean_share_in_box=kept / len(train), box=BOX.tolist(),
               voxel_m=0.05, sdf_trunc_m=0.25, depth_trunc_m=300.0, vertices=len(mesh.vertices), triangles=len(mesh.triangles),
               seconds=dict(render=round(t1 - t0, 1), tsdf=round(time.time() - t1, 1), all=round(time.time() - t0, 1)), peak_host_gb=peak_gb(),
               scientific_verdict=None)
    (O / "samepath.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res))


# ------------------------------------------------------------------------------------------------ post of one training
def post(site, res):
    from utils.image_utils import psnr
    from utils.loss_utils import ssim
    from lpipsPyTorch import lpips
    t0 = time.time()
    times = {}
    R = OUT / "stage1" / site / res
    O = R / "post"
    (O / "eval").mkdir(parents=True, exist_ok=True)
    prior = scene_prior(site, res)
    dataset, pipe, g, scene = load(site, prior, model_dir(site, res))
    bg = torch.tensor([0, 0, 0], dtype=torch.float32, device="cuda")
    train, test = scene.getTrainCameras(), scene.getTestCameras()
    times["load"] = round(time.time() - t0, 1)
    q = []
    write = not (site == B173NB and res in STAGE0)          # the stage-0 renders and mesh exist; only the image quality is added
    with torch.no_grad():
        for cam in test:
            pkg = render(cam, g, pipe, bg)
            img = pkg["render"].clamp(0, 1)
            gt = cam.original_image[0:3].cuda()
            q.append(dict(view=cam.image_name, psnr=float(psnr(img[None], gt[None]).mean()), ssim=float(ssim(img[None], gt[None])),
                          lpips_vgg=float(lpips(img[None], gt[None], net_type="vgg"))))
            if write:
                rgb = (img.permute(1, 2, 0).cpu().numpy() * 255).astype(np.uint8)
                cv2.imwrite(str(O / "eval" / f"{cam.image_name}_rgb.png"), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
                np.savez_compressed(O / "eval" / f"{cam.image_name}.npz", depth=pkg["surf_depth"].squeeze(0).cpu().numpy().astype(np.float32),
                                    normal=pkg["rend_normal"].permute(1, 2, 0).cpu().numpy().astype(np.float16),
                                    alpha=pkg["rend_alpha"].squeeze(0).cpu().numpy().astype(np.float16))
    mean = {k: round(float(np.mean([x[k] for x in q])), 4) for k in ("psnr", "ssim", "lpips_vgg")}
    (O / "quality.json").write_text(json.dumps(dict(site=site, result=res, views=len(q), mean=mean, per_view=q, lpips_net="vgg", scientific_verdict=None), indent=1))
    times["eval_renders"] = round(time.time() - t0, 1)
    if not write:
        print(json.dumps(dict(result=res, quality=mean)))
        return
    BOX = box_of(site)
    ext = GaussianExtractor(g, render, pipe, bg_color=[0, 0, 0])
    ext.gaussians.active_sh_degree = 0
    ext.reconstruction(list(train))
    kept = 0.0
    for i, cam in enumerate(ext.viewpoint_stack):
        mk = box_mask(cam, ext.depthmaps[i], BOX)
        cam.gt_alpha_mask = mk.cpu()
        kept += float(mk.mean())
    times["tsdf_renders"] = round(time.time() - t0, 1)
    mesh = ext.extract_mesh_bounded(voxel_size=0.05, sdf_trunc=0.25, depth_trunc=300.0)
    for cam in ext.viewpoint_stack:
        cam.gt_alpha_mask = None
    o3d.io.write_triangle_mesh(str(O / "mesh_tsdf.ply"), mesh)
    times["tsdf"] = round(time.time() - t0, 1)
    gd = {}
    dp = model_dir(site, res) / "dump" / f"iteration_{ITS}" / "gaussians.npz"
    if dp.exists():
        dump = np.load(dp)
        op, org = dump["opacity"], dump["origin"]
        lock = dump["locked"] if "locked" in dump.files else np.zeros(len(op), bool)

        def qq(x):
            return [float(v) for v in np.quantile(x, [0.1, 0.5, 0.9])] if len(x) else None
        gd = dict(n=int(len(op)), prior=int((org == 1).sum()), image=int((org == 0).sum()), protected=int(lock.sum()), opacity_q_prior=qq(op[org == 1]),
                  opacity_q_image=qq(op[org == 0]), share_prior_ge05=float((op[org == 1] >= 0.5).mean()) if (org == 1).any() else None)
    out = dict(site=site, result=res, prior_scene=prior, iteration=ITS, box=BOX.tolist(),
               tsdf=dict(voxel_m=0.05, sdf_trunc_m=0.25, depth_trunc_m=300.0, views=len(train), mean_share_of_pixels_in_box=kept / max(len(train), 1),
                         vertices=len(mesh.vertices), triangles=len(mesh.triangles)),
               eval_views=[c.image_name for c in test], quality=mean, gaussians=gd, seconds=times, peak_host_gb=peak_gb(), scientific_verdict=None)
    (O / "post.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: out[k] for k in ("result", "tsdf", "quality", "seconds")}))


# ------------------------------------------------------------------------------------------------ run steps of one training
def run_steps(site, res):
    t0 = time.time()
    times = {}
    R = OUT / "stage1" / site / res
    O = R / "gpu"
    O.mkdir(parents=True, exist_ok=True)
    prior = scene_prior(site, res)
    mdir = model_dir(site, res)
    dataset, pipe, g, scene = load(site, prior, mdir)
    bg = torch.tensor([0, 0, 0], dtype=torch.float32, device="cuda")
    train, test = list(scene.getTrainCameras()), list(scene.getTestCameras())
    BOX = box_of(site)
    evdir = (S0 / "stage0" / STAGE0[res] / "post/eval") if (site == B173NB and res in STAGE0) else (R / "post/eval")
    times["load"] = round(time.time() - t0, 1)
    pts, vid = [], []
    for k, cam in enumerate(test):
        z = np.load(evdir / f"{cam.image_name}.npz")
        d = torch.from_numpy(z["depth"].astype(np.float32))
        a = z["alpha"].astype(np.float32)
        Pw = unproject(cam, d).cpu().numpy().reshape(-1, 3)
        ok = (a.reshape(-1) >= 0.5) & (z["depth"].reshape(-1) > 0)
        ok[ok] &= in_eval(site, Pw[ok], 2.0)
        pts.append(Pw[ok].astype(np.float32))
        vid.append(np.full(int(ok.sum()), k, np.int16))
    np.savez_compressed(O / "eval_points.npz", xyz=np.concatenate(pts), view=np.concatenate(vid), views=np.array([c.image_name for c in test]))
    times["eval_points"] = round(time.time() - t0, 1)
    dp = mdir / "dump" / f"iteration_{ITS}" / "gaussians.npz"
    xyz = g.get_xyz.detach().cpu().numpy()
    if dp.exists():
        dump = np.load(dp)
        assert dump["xyz"].shape[0] == xyz.shape[0] and np.allclose(dump["xyz"], xyz, atol=1e-5), "dump rows != PLY rows"
        op_all, org_all = dump["opacity"], dump["origin"]
    else:
        op_all, org_all = g.get_opacity.detach().cpu().numpy().ravel(), np.zeros(len(xyz), np.int8)
    top = top_of(site, xyz)
    flo = (op_all >= FLOAT["opacity"]) & in_eval(site, xyz) & np.isfinite(top) & (xyz[:, 2] > top + FLOAT["above_m"])
    g_wo = subset(dataset, g, torch.as_tensor(~flo, device="cuda"))
    per_view, tot_px, tot_fl = [], 0, 0
    with torch.no_grad():
        for cam in test:
            pa = render(cam, g, pipe, bg)
            pw = render(cam, g_wo, pipe, bg)
            a1, d1 = pa["rend_alpha"].squeeze(0), pa["surf_depth"].squeeze(0)
            a0, d0 = pw["rend_alpha"].squeeze(0), pw["surf_depth"].squeeze(0)
            m = (a1 >= 0.5) & ((a0 < 0.5) | (d0 - d1 > FLOAT["pixel_depth_m"]))
            n = int(m.sum())
            per_view.append(dict(view=cam.image_name, pixels=int(m.numel()), floater_pixels=n))
            tot_px += int(m.numel())
            tot_fl += n
    del g_wo
    torch.cuda.empty_cache()
    (O / "floaters.json").write_text(json.dumps(dict(rule=FLOAT, floaters=int(flo.sum()), floaters_prior_origin=int((flo & (org_all == 1)).sum()),
                                                     pixel_share=tot_fl / max(tot_px, 1), pixels=tot_px, floater_pixels=tot_fl, per_view=per_view,
                                                     scientific_verdict=None), indent=1))
    np.save(O / "floater_mask.npy", flo)
    times["floaters"] = round(time.time() - t0, 1)
    uf = OUT / "defs" / site / "unseen.npz"
    if uf.exists():
        un = np.load(uf)
        C = torch.as_tensor(un["centre"], device="cuda").float()
        fake = SimpleNamespace(completed_mask=torch.ones(C.shape[0], dtype=torch.bool, device="cuda"), get_xyz=C)
        with torch.no_grad():
            virtual = create_virtual_cameras_for_completion(gaussians=fake, reference_cameras=train, n_virtual_cams=8, distance_scale=1.5)
        xg = g.get_xyz.detach()
        inside = ((xg >= torch.as_tensor(BOX[0], device="cuda").float()) & (xg <= torch.as_tensor(BOX[1], device="cuda").float())).all(1)
        model = subset(dataset, g, inside)
        ext = GaussianExtractor(model, render, pipe, bg_color=[0, 0, 0])
        ext.gaussians.active_sh_degree = 0
        ext.reconstruction(train + virtual)
        seen = []
        lab = un["label_inferred"]
        for i, cam in enumerate(ext.viewpoint_stack):
            mk = box_mask(cam, ext.depthmaps[i], BOX)
            cam.gt_alpha_mask = mk.cpu()
            if i >= len(train):
                intr, c2w = cam_mats(cam)
                w2c = torch.linalg.inv(c2w).cpu().numpy()
                K = intr.cpu().numpy()
                Pc = un["centre"] @ w2c[:3, :3].T + w2c[:3, 3]
                zc = Pc[:, 2]
                with np.errstate(divide="ignore", invalid="ignore"):
                    u = np.round(K[0, 0] * Pc[:, 0] / zc + K[0, 2]).astype(np.int64)
                    v = np.round(K[1, 1] * Pc[:, 1] / zc + K[1, 2]).astype(np.int64)
                H, W = cam.image_height, cam.image_width
                ins = (zc > 0.1) & (u >= 0) & (u < W) & (v >= 0) & (v < H)
                Dm = ext.depthmaps[i].reshape(H, W).numpy()
                Dp = np.where(ins, Dm[np.clip(v, 0, H - 1), np.clip(u, 0, W - 1)], 0.0)
                s = ins & ((Dp <= 0) | (zc <= Dp + 0.5))
                seen.append(dict(view=i - len(train), centre=cam.camera_center.cpu().numpy().tolist(), inside=int(ins.sum()), seen=int(s.sum()),
                                 seen_below_roof=int((s & (lab == 0)).sum()), seen_above_roof=int((s & (lab == 1)).sum()), box_share=float(mk.mean())))
        times["virtual_renders"] = round(time.time() - t0, 1)
        mesh = ext.extract_mesh_bounded(voxel_size=0.10, sdf_trunc=0.5, depth_trunc=300.0)
        for cam in ext.viewpoint_stack:
            cam.gt_alpha_mask = None
        (O / "virtual").mkdir(exist_ok=True)
        o3d.io.write_triangle_mesh(str(O / "virtual/mesh_virtual.ply"), mesh)
        times["virtual_tsdf"] = round(time.time() - t0, 1)
        (O / "virtual/virtual.json").write_text(json.dumps(dict(option="option2", voxel_m=0.10, views_train=len(train), views_virtual=len(virtual), gaussians_rendered=int(inside.sum()),
                                                                virtual=seen, vertices=len(mesh.vertices), triangles=len(mesh.triangles), seconds=times,
                                                                peak_host_gb=peak_gb(), scientific_verdict=None), indent=1))
    (O / "run.json").write_text(json.dumps(dict(site=site, result=res, seconds=times, peak_host_gb=peak_gb(), scientific_verdict=None), indent=1))
    print(json.dumps(dict(result=res, seconds=times)))


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "samepath":
        samepath(sys.argv[2], sys.argv[3])
    elif mode == "post":
        post(sys.argv[2], sys.argv[3])
    else:
        run_steps(sys.argv[2], sys.argv[3])
