"""PHD-MAIN-METRICS-TRIAL-v1 GPU steps (jointbuildgs:geogs-conf-guided-v1; /source = fork r12 (ro), /s0 = the stage-0 payload
(ro), /dr (ro), /out = this payload, /repo (ro)). No training: the stage-0 models are only read and rendered.

  python gpu_mt.py samepath <prior>            4.4 path 4 (config results.prior_same_path)
  python gpu_mt.py run <run> [--voxel 0.05]    per training: (a) evaluation-view points (4.4 path 2), (b) floater pixels
                                               (4.3.5), (c) the virtual-view mesh (4.5)

samepath  the registered prior surface (defs/prior_<prior>.npz) ray-cast at the 203 training views of the fork's scene with the
          fork's camera model (to_cam_open3d intrinsics and extrinsics, integer pixel coordinates: the rasterizer's), camera-Z
          depth of the first hit, the stage-0 box mask, and fused by the fork's GaussianExtractor.extract_mesh_bounded with the
          stage-0 TSDF values (0.05 m, 0.25 m, 300 m) -> /out/gpu/samepath_<prior>/mesh.ply
run (a)   the stage-0 evaluation renders (post/eval/<view>.npz: expected depth, accumulated opacity) back-projected with the
          render cameras (pixels with opacity >= 0.5 and depth > 0, inside the evaluation range + 2 m) -> eval_points.npz
    (b)   floater Gaussians (dump at 30,000: opacity >= 0.5, inside the evaluation range, > 3 m over defs/top_raster) removed;
          the 29 evaluation views rendered with all and without them; a pixel counts when opacity_all >= 0.5 and
          (opacity_without < 0.5 or depth_without - depth_all > 0.5 m) -> floaters.json
    (c)   r10's product layer: virtual cameras of the fork's create_virtual_cameras_for_completion aimed at the B173 unseen
          wall patch centres (defs/unseen.npz; two rings of 8, distance_scale 1.5), TSDF of the expected depth of the
          training + virtual views, whole scene, the stage-0 box mask, voxel 0.05 m (sdf_trunc 0.25 m; fallback 0.10 / 0.5 m)
          -> mesh_virtual.ply, virtual.json (cameras, seen unseen-patch centres per virtual view, seconds, peak host memory)
scientific_verdict: null."""
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
from utils.mesh_utils import GaussianExtractor, to_cam_open3d  # noqa: E402
from utils.render_utils import create_virtual_cameras_for_completion  # noqa: E402

MC = json.loads(Path("/repo/configs/phd/metrics_trial_v1/metrics_trial_v1.json").read_text())
PCFG = json.loads(Path("/repo/configs/phd/main_prep_measure_v1/prep_v5.json").read_text())
SITE = MC["site"]
ITS = 30000
S0 = Path("/s0")
OUT = Path("/out")
BOX = np.array(json.loads((S0 / "stage0/b1_LoD2/post/post.json").read_text())["box"])
TR = np.load(OUT / "defs/top_raster.npz")
_a = np.deg2rad(PCFG["frame"]["u_axis_angle_degrees_ccw_from_easting"])
BASIS = np.array([[np.cos(_a), np.sin(_a)], [np.sin(_a), -np.cos(_a)]])


def in_eval(xy, margin=0.0):
    uv = np.asarray(xy, np.float64)[:, :2] @ BASIS.T
    eu, ev = TR["eval_u"], TR["eval_v"]
    return (uv[:, 0] >= eu[0] - margin) & (uv[:, 0] <= eu[1] + margin) & (uv[:, 1] >= ev[0] - margin) & (uv[:, 1] <= ev[1] + margin)


def top_of(xy):
    q = np.floor((np.asarray(xy, np.float64)[:, :2] - TR["lo"]) / float(TR["cell"])).astype(np.int64)
    g = TR["grid"]
    ok = (q[:, 0] >= 0) & (q[:, 0] < g.shape[1]) & (q[:, 1] >= 0) & (q[:, 1] < g.shape[0])
    return np.where(ok, g[np.clip(q[:, 1], 0, g.shape[0] - 1), np.clip(q[:, 0], 0, g.shape[1] - 1)], np.nan)


def load(run):
    rec = json.loads((S0 / "stage0" / run / "receipt.json").read_text())
    prior = rec["prior"]
    parser = ArgumentParser()
    mp, pp = ModelParams(parser), PipelineParams(parser)
    args = parser.parse_args(["-s", str(S0 / "fork_inputs/s61" / SITE / f"scene_{prior}"), "-m", str(S0 / "stage0" / run / "model"), "--eval", "-r", "1"])
    dataset, pipe = mp.extract(args), pp.extract(args)
    g = GaussianModel(dataset.sh_degree)
    scene = Scene(dataset, g, load_iteration=ITS, shuffle=False)
    return prior, dataset, pipe, g, scene


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
def box_mask(cam, depth):   # the stage-0 post box mask (= r10 mesh_r10.box_mask)
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


def samepath(prior):
    t0 = time.time()
    O = OUT / "gpu" / f"samepath_{prior}"
    O.mkdir(parents=True, exist_ok=True)
    _, dataset, pipe, g, scene = load(f"b1_{prior}")
    train = list(scene.getTrainCameras())
    P = np.load(OUT / "defs" / f"prior_{prior}.npz")
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
        dt = torch.from_numpy(depth)[None]
        ext.depthmaps.append(dt)
        ext.rgbmaps.append(torch.zeros(3, H, W))
    for i, cam in enumerate(ext.viewpoint_stack):
        mk = box_mask(cam, ext.depthmaps[i])
        cam.gt_alpha_mask = mk.cpu()
        kept += float(mk.mean())
    t1 = time.time()
    mesh = ext.extract_mesh_bounded(voxel_size=0.05, sdf_trunc=0.25, depth_trunc=300.0)
    for cam in ext.viewpoint_stack:
        cam.gt_alpha_mask = None
    o3d.io.write_triangle_mesh(str(O / "mesh.ply"), mesh)
    res = dict(prior=prior, views=len(train), mean_hit_share=float(np.mean(hit_share)), mean_share_in_box=kept / len(train),
               voxel_m=0.05, sdf_trunc_m=0.25, depth_trunc_m=300.0, vertices=len(mesh.vertices), triangles=len(mesh.triangles),
               seconds=dict(render=round(t1 - t0, 1), tsdf=round(time.time() - t1, 1), all=round(time.time() - t0, 1)),
               peak_host_gb=peak_gb(), scientific_verdict=None)
    (O / "samepath.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res))


def run_steps(run, voxel):
    t0 = time.time()
    times = {}
    O = OUT / "gpu" / run
    O.mkdir(parents=True, exist_ok=True)
    prior, dataset, pipe, g, scene = load(run)
    bg = torch.tensor([0, 0, 0], dtype=torch.float32, device="cuda")
    train, test = list(scene.getTrainCameras()), list(scene.getTestCameras())
    times["load"] = round(time.time() - t0, 1)
    # (a) evaluation-view points
    pts, vid = [], []
    for k, cam in enumerate(test):
        z = np.load(S0 / "stage0" / run / "post/eval" / f"{cam.image_name}.npz")
        d = torch.from_numpy(z["depth"].astype(np.float32))
        a = z["alpha"].astype(np.float32)
        Pw = unproject(cam, d).cpu().numpy().reshape(-1, 3)
        ok = (a.reshape(-1) >= 0.5) & (z["depth"].reshape(-1) > 0)
        ok[ok] &= in_eval(Pw[ok], 2.0)
        pts.append(Pw[ok].astype(np.float32))
        vid.append(np.full(int(ok.sum()), k, np.int16))
    np.savez_compressed(O / "eval_points.npz", xyz=np.concatenate(pts), view=np.concatenate(vid), views=np.array([c.image_name for c in test]))
    times["eval_points"] = round(time.time() - t0, 1)
    # (b) floater pixels
    dump = np.load(S0 / "stage0" / run / "model/dump" / f"iteration_{ITS}" / "gaussians.npz")
    xyz = g.get_xyz.detach().cpu().numpy()
    assert dump["xyz"].shape[0] == xyz.shape[0] and np.allclose(dump["xyz"], xyz, atol=1e-5), "dump rows != PLY rows"
    fl = MC["floaters"]
    top = top_of(xyz)
    flo = (dump["opacity"] >= fl["opacity"]) & in_eval(xyz) & np.isfinite(top) & (xyz[:, 2] > top + fl["above_m"])
    g_wo = subset(dataset, g, torch.as_tensor(~flo, device="cuda"))
    per_view, tot_px, tot_fl = [], 0, 0
    with torch.no_grad():
        for cam in test:
            pa = render(cam, g, pipe, bg)
            pw = render(cam, g_wo, pipe, bg)
            a1, d1 = pa["rend_alpha"].squeeze(0), pa["surf_depth"].squeeze(0)
            a0, d0 = pw["rend_alpha"].squeeze(0), pw["surf_depth"].squeeze(0)
            m = (a1 >= 0.5) & ((a0 < 0.5) | (d0 - d1 > fl["pixel_depth_m"]))
            n = int(m.sum())
            per_view.append(dict(view=cam.image_name, pixels=int(m.numel()), floater_pixels=n))
            tot_px += int(m.numel())
            tot_fl += n
    del g_wo
    torch.cuda.empty_cache()
    (O / "floaters.json").write_text(json.dumps(dict(rule=fl, floaters=int(flo.sum()), floaters_prior_origin=int((flo & (dump["origin"] == 1)).sum()),
                                                     pixel_share=tot_fl / max(tot_px, 1), pixels=tot_px, floater_pixels=tot_fl, per_view=per_view,
                                                     scientific_verdict=None), indent=1))
    np.save(O / "floater_mask.npy", flo)
    times["floaters"] = round(time.time() - t0, 1)
    # (c) virtual-view mesh (r10 product layer)
    un = np.load(OUT / "defs/unseen.npz")
    C = torch.as_tensor(un["centre"], device="cuda").float()
    fake = SimpleNamespace(completed_mask=torch.ones(C.shape[0], dtype=torch.bool, device="cuda"), get_xyz=C)
    with torch.no_grad():
        virtual = create_virtual_cameras_for_completion(gaussians=fake, reference_cameras=train, n_virtual_cams=8, distance_scale=1.5)
    vc = MC["virtual_view_mesh"]
    centre = un["centre"].mean(0)
    assert np.allclose(centre, vc["centre_local_m"], atol=0.01), (centre, vc["centre_local_m"])
    assert len(virtual) == vc["count"]
    ext = GaussianExtractor(g, render, pipe, bg_color=[0, 0, 0])
    ext.gaussians.active_sh_degree = 0
    ext.reconstruction(train + virtual)
    seen = []
    Cn = un["centre"]
    for i, cam in enumerate(ext.viewpoint_stack):
        mk = box_mask(cam, ext.depthmaps[i])
        cam.gt_alpha_mask = mk.cpu()
        if i >= len(train):
            intr, c2w = cam_mats(cam)
            w2c = torch.linalg.inv(c2w).cpu().numpy()
            K = intr.cpu().numpy()
            Pc = Cn @ w2c[:3, :3].T + w2c[:3, 3]
            zc = Pc[:, 2]
            with np.errstate(divide="ignore", invalid="ignore"):
                u = np.round(K[0, 0] * Pc[:, 0] / zc + K[0, 2]).astype(np.int64)
                v = np.round(K[1, 1] * Pc[:, 1] / zc + K[1, 2]).astype(np.int64)
            H, W = cam.image_height, cam.image_width
            ins = (zc > 0.1) & (u >= 0) & (u < W) & (v >= 0) & (v < H)
            D = ext.depthmaps[i].reshape(H, W).numpy()
            Dp = np.where(ins, D[np.clip(v, 0, H - 1), np.clip(u, 0, W - 1)], 0.0)
            s = ins & ((Dp <= 0) | (zc <= Dp + 0.5))
            lab = un["label_inferred"]
            seen.append(dict(view=i - len(train), centre=cam.camera_center.cpu().numpy().tolist(), inside=int(ins.sum()), seen=int(s.sum()),
                             seen_below_roof=int((s & (lab == 0)).sum()), seen_above_roof=int((s & (lab == 1)).sum()), box_share=float(mk.mean())))
    times["virtual_renders"] = round(time.time() - t0, 1)
    sdf = {0.05: 0.25, 0.10: 0.5}[round(voxel, 2)]
    mesh = ext.extract_mesh_bounded(voxel_size=voxel, sdf_trunc=sdf, depth_trunc=vc["depth_trunc_m"])
    for cam in ext.viewpoint_stack:
        cam.gt_alpha_mask = None
    o3d.io.write_triangle_mesh(str(O / "mesh_virtual.ply"), mesh)
    times["virtual_tsdf"] = round(time.time() - t0, 1)
    res = dict(run=run, prior=prior, voxel_m=voxel, sdf_trunc_m=sdf, depth_trunc_m=vc["depth_trunc_m"], views_train=len(train), views_virtual=len(virtual),
               virtual=seen, centre=centre.tolist(), vertices=len(mesh.vertices), triangles=len(mesh.triangles), seconds=times, peak_host_gb=peak_gb(),
               scientific_verdict=None)
    (O / "virtual.json").write_text(json.dumps(res, indent=1))
    print(json.dumps({k: v for k, v in res.items() if k != "virtual"}))


if __name__ == "__main__":
    mode, arg = sys.argv[1], sys.argv[2]
    vox = float(sys.argv[sys.argv.index("--voxel") + 1]) if "--voxel" in sys.argv else MC["virtual_view_mesh"]["voxel_m"]
    if mode == "samepath":
        samepath(arg)
    else:
        run_steps(arg, vox)
