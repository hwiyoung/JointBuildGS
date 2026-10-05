"""PHD-STAGE2-R10-TWO-FIXES-THREE-CHECKS-v1 mesh step (conf-guided image, GPU; /source = r10 fork, /s2, /p9, /p10, /r8, /repo).

  python mesh_r10.py <run>          # e.g. M_N; reads /p10/runs/<run>/model (iteration of the run's receipt)

Check 'da' (order 3-1): the mesh check of invisible faces in two layers, with r9's mesh method (mesh_r9.py) unchanged in
its parts -- invisible Gaussians (final render as the one-sided occluder), the aimed region (invisible prior-origin
Gaussians, opacity >= 0.5, on outward faces of the target building), the base helper's virtual cameras aimed at it (two
rings of 8), TSDF at 0.10 m (sdf_trunc 0.5 m) in the crop box:
  product layer   (r9) TSDF of the training views + the virtual views, whole scene   -> mesh_train_virtual.ply
                  (+ r9's training-view-only TSDF -> mesh_train.ply)
  mechanism layer TSDF of the virtual views only, rendered with only the aimed Gaussians   -> mesh_mechanism.ply
Both layers: distance of every aimed Gaussian centre to the mesh (dist_region_<layer>.npy).
Occluders (product layer), per virtual view: an aimed Gaussian is hidden when its centre lies more than 0.5 m behind the
rendered expected depth (accumulated opacity >= 0.05); an occluder of it is a Gaussian that is not aimed, has opacity >= 0.05,
lies more than 0.5 m in front of it and whose projected centre is within its own screen radius (the rasterizer's radii) of
the hidden Gaussian's pixel. Occluders counted by group (groups overlap): image origin, scale above 1 m, prior origin of
other buildings, protected, prior origin of the target building; per group the share of the hidden aimed Gaussians it hides.
Figure cameras: r8's virtual cameras 3 and 11 of the setting (rebuilt from r8's aimed Gaussians, as r9's views_r9.py);
both layers rendered there (depth, normal, opacity).
Writes /p10/mesh/<run>/{mesh_train.ply, mesh_train_virtual.ply, mesh_mechanism.ply, mesh.json, invisible.npz,
dist_region_*.npy, occluders.json, figure_views.npz}."""
import json
import sys
import time
from argparse import ArgumentParser
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import open3d as o3d
import torch
from scipy.spatial import cKDTree

sys.path.insert(0, "/source")
from arguments import ModelParams, PipelineParams  # noqa: E402
from gaussian_renderer import GaussianModel, render  # noqa: E402
from scene import Scene  # noqa: E402
from utils.mesh_utils import GaussianExtractor  # noqa: E402
from utils.render_utils import create_virtual_cameras_for_completion  # noqa: E402
import jbgs_judgment as J  # noqa: E402

run = sys.argv[1]
P10 = Path("/p10"); P9 = Path("/p9"); R8 = Path("/r8")
CFG = json.loads(Path("/repo/configs/phd/stage2_r10_two_fixes_three_checks_v1/r10.json").read_text())
MC = CFG["mesh"]
rec = json.loads((P10 / "runs" / run / "receipt.json").read_text())
cond = rec["condition_json"]["condition"]
its = int(rec["iterations"])
setting = rec["setting"]
OUT = P10 / "mesh" / run; OUT.mkdir(parents=True, exist_ok=True)
t0 = time.time()
times = {}

parser = ArgumentParser()
mp = ModelParams(parser); pp = PipelineParams(parser)
scene_dir = f"/p10/scenes/{setting}" if setting.startswith("M") else f"/s2/runs/{cond}/scene"
args = parser.parse_args(["-s", scene_dir, "-m", f"/p10/runs/{run}/model", "--eval"])
dataset, pipe = mp.extract(args), pp.extract(args)
gaussians = GaussianModel(dataset.sh_degree)
scene = Scene(dataset, gaussians, load_iteration=its, shuffle=False)
bg = torch.tensor([1, 1, 1] if dataset.white_background else [0, 0, 0], dtype=torch.float32, device="cuda")
train = scene.getTrainCameras()
dump = np.load(P10 / "runs" / run / f"model/dump/iteration_{its}/gaussians.npz")
n = gaussians.get_xyz.shape[0]
assert dump["xyz"].shape[0] == n and np.allclose(dump["xyz"], gaussians.get_xyz.detach().cpu().numpy(), atol=1e-5), "dump rows != PLY rows"

# 1. invisible Gaussians (final render as the occluder) and the aimed region (r9's rule)
with torch.no_grad():
    D, AL, A = {}, {}, {}
    for cam in train:
        pkg = render(cam, gaussians, pipe, bg)
        D[cam.image_name] = pkg["surf_depth"].squeeze(0); AL[cam.image_name] = pkg["rend_alpha"].squeeze(0)
        A[cam.image_name] = torch.ones_like(D[cam.image_name])
    xyz = gaussians.get_xyz.detach()
    _, n_seeing, _ = J.compute_E_render(xyz, train, A, D, AL, 0.5, 0.05)
    del D, AL, A
invisible = (n_seeing == 0).cpu().numpy()
prior = dump["origin"] == 1
opac = gaussians.get_opacity.squeeze(-1).detach().cpu().numpy()
cat = dump["init_category"] if "init_category" in dump.files else np.full(n, -1)
var = "poly" if setting.startswith("M") else "lod2"
root = P10 if setting.startswith("M") else P9
table = {r["ext"]: r for r in json.loads((root / "stage1/products" / setting / f"surfaces_{var}.json").read_text())["surfaces"]}
ids = dump["init_id"].astype(np.int64)
ext_row = np.where(ids >= 0, dump["init_surface_ext"][np.maximum(ids, 0)], -1)
is_target = np.zeros(n, bool); is_ground = np.zeros(n, bool)
for e, r_ in table.items():
    m_ = ext_row == e
    if m_.any():
        is_target[m_] = bool(r_.get("target")); is_ground[m_] = r_.get("type") == "ground"
opaque = opac >= 0.5
region = invisible & prior & opaque & is_target & ~is_ground
np.savez_compressed(OUT / "invisible.npz", invisible=invisible, region=region, n_seeing=n_seeing.cpu().numpy().astype(np.int16),
                    opacity=opac.astype(np.float32), xyz=xyz.cpu().numpy().astype(np.float32), origin=dump["origin"], category=cat)
times["invisible"] = round(time.time() - t0, 1)

PJ = json.loads(Path("/artifacts/JointBuildGS/phase-payloads/phd/stage1_conf_tol_conflict_v1/PHD-STAGE1-CONF-TOL-CONFLICT-v1/inputs/lod2_polygons.json").read_text())
RECT = np.array(PJ["als_crop_local_xy"], float)
BOX = np.array([[RECT[0, 0] - MC["box_margin_m"], RECT[0, 1] - MC["box_margin_m"], MC["box_z_m"][0]],
                [RECT[1, 0] + MC["box_margin_m"], RECT[1, 1] + MC["box_margin_m"], MC["box_z_m"][1]]])


@torch.no_grad()
def box_mask(cam, depth):   # mesh_r9.box_mask
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


def tsdf(ext, cams):
    ext.reconstruction(cams)
    kept = 0
    for i, cam in enumerate(ext.viewpoint_stack):
        m = box_mask(cam, ext.depthmaps[i])
        cam.gt_alpha_mask = m.cpu()
        kept += float(m.mean())
    print(f"box mask: mean share of pixels kept {kept / max(len(cams), 1):.3f}", flush=True)
    mesh = ext.extract_mesh_bounded(voxel_size=MC["voxel_m"], sdf_trunc=MC["sdf_trunc_m"], depth_trunc=MC["depth_trunc_m"])
    for cam in ext.viewpoint_stack:
        cam.gt_alpha_mask = None
    ext.clean()
    return mesh


def subset(g, keep):
    h = GaussianModel(dataset.sh_degree)
    h.active_sh_degree = g.active_sh_degree
    for name in ("_xyz", "_features_dc", "_features_rest", "_scaling", "_rotation", "_opacity"):
        setattr(h, name, torch.nn.Parameter(getattr(g, name).detach()[keep].clone(), requires_grad=False))
    return h


# 2. virtual cameras (r9's rule) and the meshes
gaussians.completed_mask = torch.as_tensor(region, device="cuda")
with torch.no_grad():
    virtual = create_virtual_cameras_for_completion(gaussians=gaussians, reference_cameras=train, n_virtual_cams=8, distance_scale=1.5)
gaussians.completed_mask = None
ext = GaussianExtractor(gaussians, render, pipe, bg_color=[0, 0, 0])
ext.gaussians.active_sh_degree = 0
mesh_a = tsdf(ext, list(train)); o3d.io.write_triangle_mesh(str(OUT / "mesh_train.ply"), mesh_a)
times["mesh_train"] = round(time.time() - t0, 1)
mesh_b = tsdf(ext, list(train) + virtual); o3d.io.write_triangle_mesh(str(OUT / "mesh_train_virtual.ply"), mesh_b)
times["mesh_product"] = round(time.time() - t0, 1)
reg_t = torch.as_tensor(region, device="cuda")
aimed = subset(gaussians, reg_t); aimed.active_sh_degree = 0
ext_m = GaussianExtractor(aimed, render, pipe, bg_color=[0, 0, 0])
mesh_c = tsdf(ext_m, list(virtual)); o3d.io.write_triangle_mesh(str(OUT / "mesh_mechanism.ply"), mesh_c)
times["mesh_mechanism"] = round(time.time() - t0, 1)


# 3. distances of Gaussians to the meshes
def dist_to(mesh, pts):
    if len(pts) == 0 or len(mesh.triangles) == 0:
        return np.full(len(pts), np.inf)
    sc = o3d.t.geometry.RaycastingScene()
    sc.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(mesh))
    return sc.compute_distance(o3d.core.Tensor(pts.astype(np.float32))).numpy()


MESHES = (("train", mesh_a), ("train_virtual", mesh_b), ("mechanism", mesh_c))
groups = {"target outward faces, invisible, opacity >= 0.5 (aimed at)": region,
          "other invisible prior, opacity >= 0.5": invisible & prior & opaque & ~is_target,
          "invisible prior (all)": invisible & prior,
          "seen prior, opacity >= 0.5": ~invisible & prior & opaque}
reg_xyz = xyz.cpu().numpy()[region]
res = dict(run=run, iteration=its, box=BOX.tolist(), n=int(n), n_invisible=int(invisible.sum()), n_invisible_prior=int((invisible & prior).sum()),
           n_region=int(region.sum()), region_centre=reg_xyz.mean(0).tolist() if len(reg_xyz) else None,
           n_virtual_cameras=len(virtual), virtual_camera_centres=[v.camera_center.cpu().numpy().tolist() for v in virtual],
           training_camera_centres=[c.camera_center.cpu().numpy().tolist() for c in train],
           voxel_m=MC["voxel_m"], sdf_trunc_m=MC["sdf_trunc_m"], depth_trunc_m=MC["depth_trunc_m"],
           meshes={k: dict(vertices=len(m.vertices), triangles=len(m.triangles)) for k, m in MESHES}, groups={})
for gname, gm in groups.items():
    pts = xyz.cpu().numpy()[gm]
    row = dict(n=int(gm.sum()))
    for mname, mesh in MESHES:
        if mname == "mechanism" and not gname.startswith("target outward"):
            continue
        d = dist_to(mesh, pts)
        row[mname] = dict(median_m=float(np.median(d)) if len(d) else None,
                          **{f"within_{t:g}m": float((d <= t).mean()) if len(d) else None for t in MC["in_mesh_distance_m"]})
        if gname.startswith("target outward"):
            np.save(OUT / f"dist_region_{mname}.npy", d.astype(np.float32))
    res["groups"][gname] = row
times["distances"] = round(time.time() - t0, 1)

# 4. occluders per virtual view (product layer)
lock = torch.as_tensor(dump["locked"], device="cuda")
org = torch.as_tensor(dump["origin"], device="cuda")
ext_t = torch.as_tensor(ext_row, device="cuda")
tgt_ext = torch.as_tensor(sorted(e for e, r in table.items() if r.get("target")), device="cuda")
on_target = torch.isin(ext_t, tgt_ext)
big = gaussians.get_scaling.detach().max(1).values > 1.0
op_t = gaussians.get_opacity.squeeze(-1).detach()
GROUPS = {"image origin": org == 0, "scale above 1 m": big, "prior of other buildings": (org == 1) & ~on_target,
          "protected": lock, "prior of the target building (not aimed)": (org == 1) & on_target & ~reg_t}
occ = dict(rule=MC["occluders"], per_view=[], totals={})
tot_hidden, tot_inside = 0, 0
tot_by = {k: 0 for k in GROUPS}; tot_occ_by = {k: 0 for k in GROUPS}
idx_reg = torch.nonzero(reg_t).squeeze(1)
for vi, vc in enumerate(virtual):
    with torch.no_grad():
        pkg = render(vc, gaussians, pipe, bg)
    Dv = pkg["surf_depth"].squeeze(0); ALv = pkg["rend_alpha"].squeeze(0); radii = pkg["radii"]
    Hh, Ww = Dv.shape
    u, v, z = J.project_points(xyz[idx_reg], vc)
    ui, vi_ = torch.round(u).long(), torch.round(v).long()
    inside = (z > 0.01) & (ui >= 0) & (ui < Ww) & (vi_ >= 0) & (vi_ < Hh)
    pix = vi_.clamp(0, Hh - 1) * Ww + ui.clamp(0, Ww - 1)
    Dp = Dv.reshape(-1)[pix]; ap = ALv.reshape(-1)[pix]
    hidden = inside & (ap >= 0.05) & (z > Dp + 0.5)
    row = dict(camera=vi, aimed_inside=int(inside.sum()), aimed_hidden=int(hidden.sum()), aimed_seen=int((inside & ~hidden).sum()))
    if bool(hidden.any()):
        hu = torch.stack([u[hidden], v[hidden]], 1).cpu().numpy(); hz = z[hidden].cpu().numpy()
        cand = (radii > 0) & ~reg_t & (op_t >= 0.05)
        ci = torch.nonzero(cand).squeeze(1)
        cu, cv, cz = J.project_points(xyz[ci], vc)
        lo = hu.min(0); hi = hu.max(0); rr = radii[ci].float()
        near = (cu + rr >= float(lo[0])) & (cu - rr <= float(hi[0])) & (cv + rr >= float(lo[1])) & (cv - rr <= float(hi[1])) & (cz < float(hz.max()) - 0.5) & (cz > 0.01)
        ci, cu, cv, cz, rr = ci[near], cu[near], cv[near], cz[near], rr[near]
        tree = cKDTree(hu)
        lists = tree.query_ball_point(np.stack([cu.cpu().numpy(), cv.cpu().numpy()], 1), r=rr.cpu().numpy(), workers=-1)
        czn = cz.cpu().numpy()
        occ_rows = np.zeros(len(ci), bool)
        hid_by = {k: np.zeros(len(hz), bool) for k in GROUPS}
        gmask = {k: m[ci].cpu().numpy() for k, m in GROUPS.items()}
        hid_any = np.zeros(len(hz), bool)
        for j, L in enumerate(lists):
            if not L:
                continue
            L = np.asarray(L)
            fr = L[hz[L] > czn[j] + 0.5]
            if len(fr):
                occ_rows[j] = True
                hid_any[fr] = True
                for k in GROUPS:
                    if gmask[k][j]:
                        hid_by[k][fr] = True
        row["occluders"] = int(occ_rows.sum())
        row["occluders_by_group"] = {k: int((occ_rows & gmask[k]).sum()) for k in GROUPS}
        row["hidden_with_an_occluder_found"] = int(hid_any.sum())
        row["hidden_hidden_by_group"] = {k: int(hid_by[k].sum()) for k in GROUPS}
        row["occluder_scale_m"] = dict(p50=float(np.median(gaussians.get_scaling.detach().max(1).values[ci[torch.as_tensor(occ_rows, device='cuda')]].cpu().numpy()))
                                       if occ_rows.any() else None)
        for k in GROUPS:
            tot_by[k] += row["hidden_hidden_by_group"][k]; tot_occ_by[k] += row["occluders_by_group"][k]
    tot_hidden += row["aimed_hidden"]; tot_inside += row["aimed_inside"]
    occ["per_view"].append(row)
    print("occluders", json.dumps(row)[:400], flush=True)
occ["totals"] = dict(aimed_inside=tot_inside, aimed_hidden=tot_hidden, hidden_share=tot_hidden / max(tot_inside, 1),
                     hidden_hidden_by_group=tot_by, occluders_by_group=tot_occ_by,
                     hidden_share_by_group={k: tot_by[k] / max(tot_hidden, 1) for k in GROUPS})
(OUT / "occluders.json").write_text(json.dumps(occ, indent=1))
times["occluders"] = round(time.time() - t0, 1)

# 5. figure cameras: r8's virtual cameras 3 and 11 of the setting (rebuilt from r8's aimed Gaussians)
r8run = {"M_N": "M_N", "M_B": "M_B", "L_N": "L_N", "L_B": "L_B"}[setting]
fig = {}
if (R8 / "mesh" / r8run / "invisible.npz").exists():
    iv8 = np.load(R8 / "mesh" / r8run / "invisible.npz")
    reg8 = torch.as_tensor(iv8["xyz"][iv8["region"]], device="cuda").float()
    with torch.no_grad():
        virtual8 = create_virtual_cameras_for_completion(gaussians=SimpleNamespace(completed_mask=torch.ones(reg8.shape[0], dtype=torch.bool, device="cuda"),
                                                                                   get_xyz=reg8), reference_cameras=train, n_virtual_cams=8, distance_scale=1.5)
    for k in (3, 11):
        vc = virtual8[k]
        with torch.no_grad():
            for tag, g in (("product", gaussians), ("mechanism", aimed)):
                pkg = render(vc, g, pipe, bg)
                fig[f"cam{k}_{tag}_depth"] = pkg["surf_depth"].squeeze(0).cpu().numpy().astype(np.float32)
                fig[f"cam{k}_{tag}_normal"] = pkg["rend_normal"].cpu().numpy().astype(np.float16)
                fig[f"cam{k}_{tag}_alpha"] = pkg["rend_alpha"].squeeze(0).cpu().numpy().astype(np.float16)
            fig[f"cam{k}_world_view"] = vc.world_view_transform.cpu().numpy(); fig[f"cam{k}_full_proj"] = vc.full_proj_transform.cpu().numpy()
            fig[f"cam{k}_centre"] = vc.camera_center.cpu().numpy(); fig[f"cam{k}_size"] = np.array((vc.image_width, vc.image_height))
            _, cnt_v, _ = J.compute_E_render(xyz[reg_t], [vc], {vc.image_name: torch.ones_like(torch.as_tensor(fig[f"cam{k}_product_depth"], device="cuda"))},
                                             {vc.image_name: torch.as_tensor(fig[f"cam{k}_product_depth"], device="cuda")},
                                             {vc.image_name: torch.as_tensor(fig[f"cam{k}_product_alpha"], device="cuda").float()}, 0.5, 0.05)
            fig[f"cam{k}_aimed_seen_product"] = int(cnt_v.sum())
    np.savez_compressed(OUT / "figure_views.npz", **fig)
res["figure_cameras"] = {k: int(v) for k, v in fig.items() if k.endswith("aimed_seen_product")}
times["figure_views"] = round(time.time() - t0, 1)
res["seconds"] = round(time.time() - t0, 1); res["times"] = times
(OUT / "mesh.json").write_text(json.dumps(res, indent=1))
print(json.dumps({k: v for k, v in res.items() if k not in ("virtual_camera_centres", "training_camera_centres")}, indent=1)[:3000])
