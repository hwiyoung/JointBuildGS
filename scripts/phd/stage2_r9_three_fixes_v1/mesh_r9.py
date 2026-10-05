"""PHD-STAGE2-R9-THREE-FIXES-v1 mesh step (conf-guided image, GPU; /source = r9 fork, /s2, /p9 and /r8 mounted).

  python mesh_r9.py <run>          # e.g. M_N; reads /p9/runs/<run>/model (iteration of the run's receipt)
  python mesh_r9.py <run> r8cams   # the same, with r8's 16 virtual cameras instead of the ones aimed at r9's Gaussians
                                   # (separates the camera placement from the fixes); writes /p9/mesh/<run>_r8cams/

r8's mesh step (mesh_r8.py) unchanged in its method -- invisible Gaussians (final render as the one-sided occluder),
the aimed region (invisible prior-origin Gaussians, opacity >= 0.5, on outward faces of the target building), the base
helper's virtual cameras (two rings of 8), TSDF of the training views and of the training + virtual views at 0.10 m in the
crop box, distances of Gaussian centres to the meshes -- with the r9 paths (the LoD2 runs load their r9 scene). Added for
the side-by-side figures: r8's virtual cameras are rebuilt from r8's aimed Gaussians (r8 mesh/<run>/invisible.npz, the
helper only reads their centres) and the r9 scene is rendered from the r8 virtual view that r8's figure used.
Writes /p9/mesh/<run>/{mesh_train.ply, mesh_train_virtual.ply, mesh.json, invisible.npz, virtual_view.npz,
virtual_view_r8cam.npz}."""
import json
import sys
import time
from argparse import ArgumentParser
from pathlib import Path

import numpy as np
import open3d as o3d
import torch

sys.path.insert(0, "/source")
from arguments import ModelParams, PipelineParams  # noqa: E402
from gaussian_renderer import GaussianModel, render  # noqa: E402
from scene import Scene  # noqa: E402
from utils.mesh_utils import GaussianExtractor  # noqa: E402
from utils.render_utils import create_virtual_cameras_for_completion  # noqa: E402
import jbgs_judgment as J  # noqa: E402

run = sys.argv[1]
VARIANT = sys.argv[2] if len(sys.argv) > 2 else ""
P8 = Path("/p9")          # the r9 payload (the name P8 is kept from mesh_r8.py)
R8 = Path("/r8")
CFG = json.loads(Path("/repo/configs/phd/stage2_r9_three_fixes_v1/r9.json").read_text())
MC = CFG["mesh"]
rec = json.loads((P8 / "runs" / run / "receipt.json").read_text())
cond = rec["condition_json"]["condition"]
its = int(rec["iterations"])
OUT = P8 / "mesh" / (run + ("_r8cams" if VARIANT == "r8cams" else "")); OUT.mkdir(parents=True, exist_ok=True)
t0 = time.time()

parser = ArgumentParser()
mp = ModelParams(parser); pp = PipelineParams(parser)
scene_dir = f"/p9/scenes/{rec['setting']}" if (rec["setting"].startswith("M") and rec.get("fork", "r9") == "r9") else f"/s2/runs/{cond}/scene"
args = parser.parse_args(["-s", scene_dir, "-m", f"/p9/runs/{run}/model", "--eval"])
dataset, pipe = mp.extract(args), pp.extract(args)
gaussians = GaussianModel(dataset.sh_degree)
scene = Scene(dataset, gaussians, load_iteration=its, shuffle=False)
bg = torch.tensor([1, 1, 1] if dataset.white_background else [0, 0, 0], dtype=torch.float32, device="cuda")
train = scene.getTrainCameras()
dump = np.load(P8 / "runs" / run / f"model/dump/iteration_{its}/gaussians.npz")
n = gaussians.get_xyz.shape[0]
assert dump["xyz"].shape[0] == n and np.allclose(dump["xyz"], gaussians.get_xyz.detach().cpu().numpy(), atol=1e-5), "dump rows != PLY rows"

# 1. invisible Gaussians (final render as the occluder)
with torch.no_grad():
    D, AL, A = {}, {}, {}
    for cam in train:
        pkg = render(cam, gaussians, pipe, bg)
        D[cam.image_name] = pkg["surf_depth"].squeeze(0); AL[cam.image_name] = pkg["rend_alpha"].squeeze(0)
        A[cam.image_name] = torch.ones_like(D[cam.image_name])
    xyz = gaussians.get_xyz.detach()
    _, n_seeing, _ = J.compute_E_render(xyz, train, A, D, AL, 0.5, 0.05)
invisible = (n_seeing == 0).cpu().numpy()
prior = dump["origin"] == 1
opac = gaussians.get_opacity.squeeze(-1).detach().cpu().numpy()
cat = dump["init_category"] if "init_category" in dump.files else np.full(n, -1)
# the initial surface of every Gaussian (through its initial disk) and whether it is an outward face of the target building
setting = rec["setting"]
var = "poly" if setting.startswith("M") else "lod2"
table = {r["ext"]: r for r in json.loads((P8 / "stage1/products" / setting / f"surfaces_{var}.json").read_text())["surfaces"]}
ids = dump["init_id"].astype(np.int64)
ext_init = dump["init_surface_ext"]
ext_row = np.where(ids >= 0, ext_init[np.maximum(ids, 0)], -1)
ext_keys = np.array(sorted(table), np.int64)
is_target = np.zeros(n, bool); is_ground = np.zeros(n, bool)
for e, r_ in table.items():
    m_ = ext_row == e
    if not m_.any():
        continue
    is_target[m_] = bool(r_.get("target"))
    is_ground[m_] = r_.get("type") == "ground"
opaque = opac >= 0.5
region = invisible & prior & opaque & is_target & ~is_ground      # outward faces of the target building no training view sees
np.savez_compressed(OUT / "invisible.npz", invisible=invisible, region=region, n_seeing=n_seeing.cpu().numpy().astype(np.int16),
                    opacity=opac.astype(np.float32), xyz=xyz.cpu().numpy().astype(np.float32), origin=dump["origin"], category=cat)

# 2-3. meshes
ext = GaussianExtractor(gaussians, render, pipe, bg_color=[0, 0, 0])
ext.gaussians.active_sh_degree = 0


PJ = json.loads(Path("/artifacts/JointBuildGS/phase-payloads/phd/stage1_conf_tol_conflict_v1/PHD-STAGE1-CONF-TOL-CONFLICT-v1/inputs/lod2_polygons.json").read_text())
RECT = np.array(PJ["als_crop_local_xy"], float)
BOX = np.array([[RECT[0, 0] - MC["box_margin_m"], RECT[0, 1] - MC["box_margin_m"], MC["box_z_m"][0]],
                [RECT[1, 0] + MC["box_margin_m"], RECT[1, 1] + MC["box_margin_m"], MC["box_z_m"][1]]])


@torch.no_grad()
def box_mask(cam, depth):
    """1 where the rendered point lies inside the scene box (the crop rectangle of the stage-1 products + margin; z range),
    through the base implementation's background mask (gt_alpha_mask -> depth 0 in extract_mesh_bounded)."""
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


def tsdf(cams):
    ext.reconstruction(cams)
    kept = 0
    for i, cam in enumerate(ext.viewpoint_stack):
        m = box_mask(cam, ext.depthmaps[i])
        cam.gt_alpha_mask = m.cpu()
        kept += float(m.mean())
    print(f"box mask: mean share of pixels kept {kept / max(len(cams), 1):.3f}", flush=True)
    return ext.extract_mesh_bounded(voxel_size=MC["voxel_m"], sdf_trunc=MC["sdf_trunc_m"], depth_trunc=MC["depth_trunc_m"])


mesh_a = tsdf(list(train))
o3d.io.write_triangle_mesh(str(OUT / "mesh_train.ply"), mesh_a)
gaussians.completed_mask = torch.as_tensor(region, device="cuda")
with torch.no_grad():   # the base helper calls .numpy() on gaussians.get_xyz[mask]
    virtual = create_virtual_cameras_for_completion(gaussians=gaussians, reference_cameras=train, n_virtual_cams=8, distance_scale=1.5)
gaussians.completed_mask = None
if VARIANT == "r8cams":   # r8's cameras, rebuilt from r8's aimed Gaussians (the helper reads only their centres)
    from types import SimpleNamespace
    _iv8 = np.load(R8 / "mesh" / run / "invisible.npz")
    _reg8 = torch.as_tensor(_iv8["xyz"][_iv8["region"]], device="cuda").float()
    with torch.no_grad():
        virtual = create_virtual_cameras_for_completion(gaussians=SimpleNamespace(completed_mask=torch.ones(_reg8.shape[0], dtype=torch.bool, device="cuda"),
                                                                                  get_xyz=_reg8), reference_cameras=train, n_virtual_cams=8, distance_scale=1.5)
mesh_b = tsdf(list(train) + virtual)
o3d.io.write_triangle_mesh(str(OUT / "mesh_train_virtual.ply"), mesh_b)
reg_xyz = xyz.cpu().numpy()[region]
centre = reg_xyz.mean(0) if len(reg_xyz) else None
radius = float(np.linalg.norm(reg_xyz - centre, axis=1).max()) if len(reg_xyz) else None
# the virtual view that sees the most region Gaussians (for the figure): rendered depth, normal and opacity
best = None
with torch.no_grad():
    for vi, vc in enumerate(virtual):
        pkg = render(vc, gaussians, pipe, bg)
        Dv = pkg["surf_depth"].squeeze(0); ALv = pkg["rend_alpha"].squeeze(0)
        _, cnt_v, _ = J.compute_E_render(xyz[torch.as_tensor(region, device="cuda")], [vc], {vc.image_name: torch.ones_like(Dv)},
                                         {vc.image_name: Dv}, {vc.image_name: ALv}, 0.5, 0.05)
        k = int(cnt_v.sum())
        if best is None or k > best[0]:
            best = (k, vi, Dv.cpu().numpy().astype(np.float32), pkg["rend_normal"].cpu().numpy().astype(np.float16),
                    ALv.cpu().numpy().astype(np.float16), vc.world_view_transform.cpu().numpy(), vc.full_proj_transform.cpu().numpy(),
                    (vc.image_width, vc.image_height))
if best is not None:
    np.savez_compressed(OUT / "virtual_view.npz", n_region_seen=best[0], index=best[1], depth=best[2], normal=best[3], alpha=best[4],
                        world_view=best[5], full_proj=best[6], size=np.array(best[7]))
# r8's virtual cameras rebuilt from r8's aimed Gaussians; the r9 scene rendered from the view r8's figure used
r8cam = {}
if (R8 / "mesh" / run / "invisible.npz").exists():
    from types import SimpleNamespace
    iv8 = np.load(R8 / "mesh" / run / "invisible.npz")
    reg8 = torch.as_tensor(iv8["xyz"][iv8["region"]], device="cuda").float()
    stub = SimpleNamespace(completed_mask=torch.ones(reg8.shape[0], dtype=torch.bool, device="cuda"), get_xyz=reg8)
    with torch.no_grad():
        virtual8 = create_virtual_cameras_for_completion(gaussians=stub, reference_cameras=train, n_virtual_cams=8, distance_scale=1.5)
    m8j = json.loads((R8 / "mesh" / run / "mesh.json").read_text())
    c8 = np.array(m8j["virtual_camera_centres"]); c8r = np.array([v.camera_center.cpu().numpy() for v in virtual8])
    idx8 = int(np.load(R8 / "mesh" / run / "virtual_view.npz")["index"]) if (R8 / "mesh" / run / "virtual_view.npz").exists() else 0
    with torch.no_grad():
        vc = virtual8[idx8]
        pkg = render(vc, gaussians, pipe, bg)
        Dv = pkg["surf_depth"].squeeze(0); ALv = pkg["rend_alpha"].squeeze(0)
        _, cnt_v, _ = J.compute_E_render(xyz[torch.as_tensor(region, device="cuda")], [vc], {vc.image_name: torch.ones_like(Dv)},
                                         {vc.image_name: Dv}, {vc.image_name: ALv}, 0.5, 0.05)
    np.savez_compressed(OUT / "virtual_view_r8cam.npz", n_region_seen=int(cnt_v.sum()), index=idx8, depth=Dv.cpu().numpy().astype(np.float32),
                        normal=pkg["rend_normal"].cpu().numpy().astype(np.float16), alpha=ALv.cpu().numpy().astype(np.float16),
                        world_view=vc.world_view_transform.cpu().numpy(), full_proj=vc.full_proj_transform.cpu().numpy(),
                        size=np.array((vc.image_width, vc.image_height)))
    r8cam = dict(n_r8_virtual_cameras=len(virtual8), max_centre_difference_to_r8_m=float(np.abs(c8r - c8).max()) if c8.shape == c8r.shape else None,
                 r8_figure_view_index=idx8,
                 r9_cameras_vs_r8_max_centre_shift_m=float(np.abs(np.array([v.camera_center.cpu().numpy() for v in virtual]) - c8).max())
                 if len(virtual) == len(c8) else None)


# 4. distances of Gaussians to the meshes
def dist_to(mesh, pts):
    if len(pts) == 0 or len(mesh.triangles) == 0:
        return np.full(len(pts), np.inf)
    sc = o3d.t.geometry.RaycastingScene()
    sc.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(mesh))
    return sc.compute_distance(o3d.core.Tensor(pts.astype(np.float32))).numpy()


groups = {"target outward faces, invisible, opacity >= 0.5 (aimed at)": region,
          "target bottom face (LoD2 GroundSurface), invisible, opacity >= 0.5": invisible & prior & opaque & is_target & is_ground,
          "other invisible prior, opacity >= 0.5": invisible & prior & opaque & ~is_target,
          "invisible prior (all)": invisible & prior,
          "seen prior, opacity >= 0.5": ~invisible & prior & opaque}
res = dict(run=run, iteration=its, box=BOX.tolist(), n=int(n), n_invisible=int(invisible.sum()), n_invisible_prior=int((invisible & prior).sum()),
           n_region=int(region.sum()), region_centre=None if centre is None else centre.tolist(), region_radius_m=radius,
           n_virtual_cameras=len(virtual), virtual_camera_centres=[v.camera_center.cpu().numpy().tolist() for v in virtual], r8_cameras=r8cam,
           training_camera_centres=[c.camera_center.cpu().numpy().tolist() for c in train],
           voxel_m=MC["voxel_m"], sdf_trunc_m=MC["sdf_trunc_m"], depth_trunc_m=MC["depth_trunc_m"],
           mesh_train=dict(vertices=len(mesh_a.vertices), triangles=len(mesh_a.triangles)),
           mesh_train_virtual=dict(vertices=len(mesh_b.vertices), triangles=len(mesh_b.triangles)), groups={})
for gname, gm in groups.items():
    pts = xyz.cpu().numpy()[gm]
    row = dict(n=int(gm.sum()))
    for mname, mesh in (("train", mesh_a), ("train_virtual", mesh_b)):
        d = dist_to(mesh, pts)
        row[mname] = dict(median_m=float(np.median(d)) if len(d) else None,
                          **{f"within_{t:g}m": float((d <= t).mean()) if len(d) else None for t in MC["in_mesh_distance_m"]})
        if gname.startswith("target outward"):
            np.save(OUT / f"dist_region_{mname}.npy", d.astype(np.float32))
    if len(cat) == n:
        row["by_initial_category"] = {str(c): int((gm & (cat == c)).sum()) for c in np.unique(cat[gm])} if gm.any() else {}
    res["groups"][gname] = row
res["seconds"] = round(time.time() - t0, 1)
(OUT / "mesh.json").write_text(json.dumps(res, indent=1))
print(json.dumps({k: v for k, v in res.items() if k not in ("virtual_camera_centres", "training_camera_centres")}, indent=1))
