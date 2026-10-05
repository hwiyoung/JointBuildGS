"""PHD-STAGE2-R9-THREE-FIXES-v1 step 13d (conf-guided image, GPU; /source = r9 fork, /s2, /r8, /p9 mounted): the same added
views for r8 and r9 (fix 'da', qualitative panel and the mesh check).

  python views_r9.py [run]      # default M_N

r8's 16 virtual cameras are rebuilt from r8's aimed Gaussians (mesh_r8: the base helper reads only their centres). Both
final scenes (r8 and r9 of the run) are rendered from every camera; per camera the aimed Gaussians each run's own mesh
step chose (invisible prior Gaussians, opacity >= 0.5, outward faces of the target building) that the view sees (centre
within 0.5 m of the rendered expected depth, one-sided), in total and on the back roof 3393. The figure's camera = the
one with the most back-roof Gaussians seen by the weaker of the two runs; its depth, normal and opacity are saved.
Masking check on the camera of r8's figure: r9 rendered with groups of Gaussians left out (image origin; prior origin of
other buildings; protected; scale above 1 m) -- which group puts a layer in front of the aimed faces.
Writes /p9/mesh/<run>/views_shared.npz and views_shared.json."""
import json
import sys
from argparse import ArgumentParser
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import torch

sys.path.insert(0, "/source")
from arguments import ModelParams, PipelineParams  # noqa: E402
from gaussian_renderer import GaussianModel, render  # noqa: E402
from scene import Scene  # noqa: E402
from utils.render_utils import create_virtual_cameras_for_completion  # noqa: E402
import jbgs_judgment as J  # noqa: E402

run = sys.argv[1] if len(sys.argv) > 1 else "M_N"
P9 = Path("/p9"); R8 = Path("/r8")
OUT = P9 / "mesh" / run


def load(root, scene_dir):
    rec = json.loads((root / "runs" / run / "receipt.json").read_text())
    its = int(rec["iterations"])
    parser = ArgumentParser(); mp = ModelParams(parser); pp = PipelineParams(parser)
    args = parser.parse_args(["-s", scene_dir, "-m", str(root / "runs" / run / "model"), "--eval"])
    ds, pipe = mp.extract(args), pp.extract(args)
    g = GaussianModel(ds.sh_degree)
    sc = Scene(ds, g, load_iteration=its, shuffle=False)
    return g, sc, pipe, ds


cond = json.loads((P9 / "runs" / run / "receipt.json").read_text())["condition_json"]["condition"]
g9, sc9, pipe, ds = load(P9, f"/p9/scenes/{run.split('_')[0]}_{run.split('_')[1]}" if run.startswith("M") else f"/s2/runs/{cond}/scene")
g8, _, _, _ = load(R8, f"/s2/runs/{cond}/scene")
bg = torch.tensor([0, 0, 0], dtype=torch.float32, device="cuda")
train = sc9.getTrainCameras()
iv8 = np.load(R8 / "mesh" / run / "invisible.npz"); iv9 = np.load(P9 / "mesh" / run / "invisible.npz")
reg8 = torch.as_tensor(iv8["region"], device="cuda"); reg9 = torch.as_tensor(iv9["region"], device="cuda")
stub = SimpleNamespace(completed_mask=torch.ones(int(reg8.sum()), dtype=torch.bool, device="cuda"),
                       get_xyz=torch.as_tensor(iv8["xyz"][iv8["region"]], device="cuda").float())
with torch.no_grad():
    cams = create_virtual_cameras_for_completion(gaussians=stub, reference_cameras=train, n_virtual_cams=8, distance_scale=1.5)


def ext_rows(root):
    dz = np.load(root / "runs" / run / f"model/dump/iteration_3500/gaussians.npz")
    ids = dz["init_id"].astype(np.int64)
    return dz, torch.as_tensor(np.where(ids >= 0, dz["init_surface_ext"][np.maximum(ids, 0)], -1), device="cuda")


dz9, e9 = ext_rows(P9); dz8, e8 = ext_rows(R8)


@torch.no_grad()
def seen(g, cam, mask):
    pkg = render(cam, g, pipe, bg)
    D = pkg["surf_depth"].squeeze(0); AL = pkg["rend_alpha"].squeeze(0)
    _, cnt, _ = J.compute_E_render(g.get_xyz[mask], [cam], {cam.image_name: torch.ones_like(D)}, {cam.image_name: D},
                                   {cam.image_name: AL}, 0.5, 0.05)
    return cnt > 0, pkg


rows = []
for k, cam in enumerate(cams):
    s8, _ = seen(g8, cam, reg8); s9, _ = seen(g9, cam, reg9)
    rows.append(dict(camera=k, centre=cam.camera_center.cpu().numpy().round(2).tolist(),
                     r8_aimed_seen=int(s8.sum()), r9_aimed_seen=int(s9.sum()),
                     r8_back_roof_seen=int((s8 & (e8[reg8] == 3393)).sum()), r9_back_roof_seen=int((s9 & (e9[reg9] == 3393)).sum()),
                     r8_3405_seen=int((s8 & (e8[reg8] == 3405)).sum()), r9_3405_seen=int((s9 & (e9[reg9] == 3405)).sum())))
    print(rows[-1], flush=True)
best = max(rows, key=lambda r: min(r["r8_back_roof_seen"], r["r9_back_roof_seen"]))
k = best["camera"]
out = {}
for tag, g in (("r8", g8), ("r9", g9)):
    _, pkg = seen(g, cams[k], reg8 if tag == "r8" else reg9)
    out[f"{tag}_depth"] = pkg["surf_depth"].squeeze(0).cpu().numpy().astype(np.float32)
    out[f"{tag}_normal"] = pkg["rend_normal"].cpu().numpy().astype(np.float16)
    out[f"{tag}_alpha"] = pkg["rend_alpha"].squeeze(0).cpu().numpy().astype(np.float16)
np.savez_compressed(OUT / "views_shared.npz", camera=k, **out)


# masking check on the camera of r8's figure
def subset(g, keep):
    h = GaussianModel(ds.sh_degree)
    h.active_sh_degree = g.active_sh_degree
    for name in ("_xyz", "_features_dc", "_features_rest", "_scaling", "_rotation", "_opacity"):
        setattr(h, name, torch.nn.Parameter(getattr(g, name).detach()[keep].clone(), requires_grad=False))
    return h


k8 = int(np.load(R8 / "mesh" / run / "virtual_view.npz")["index"])
cam = cams[k8]
lock9 = torch.as_tensor(dz9["locked"], device="cuda"); org9 = torch.as_tensor(dz9["origin"], device="cuda")
tab = {r["ext"]: r for r in json.loads((P9 / "stage1/products" / ("M_N" if run.startswith("M_N") else run) / "surfaces_poly.json").read_text())["surfaces"]} \
    if run.startswith("M") else {}
tgt_ext = torch.as_tensor(sorted(e for e, r in tab.items() if r.get("target")), device="cuda") if tab else torch.zeros(0, device="cuda")
other_prior = (org9 == 1) & ~torch.isin(e9, tgt_ext)
big = g9.get_scaling.detach().max(1).values > 1.0
masks = {"all": torch.ones_like(lock9), "without image origin": org9 == 1, "without prior of other buildings": ~other_prior,
         "without protected": ~lock9, "without scale > 1 m": ~big}
check = {}
for name, keep in masks.items():
    h = subset(g9, keep)
    regk = reg9[keep]
    s, pkg = seen(h, cam, regk)
    D = pkg["surf_depth"].squeeze(0)
    check[name] = dict(kept=int(keep.sum()), aimed_seen=int(s.sum()), back_roof_seen=int((s & (e9[keep][regk] == 3393)).sum()),
                       face_3405_seen=int((s & (e9[keep][regk] == 3405)).sum()), median_depth=float(D[D > 0].median()))
    print(name, check[name], flush=True)
s8, _ = seen(g8, cam, reg8)
res = dict(rule=__doc__.split("\n\n")[1], cameras=rows, figure_camera=k, figure_camera_rule="max over r8's 16 cameras of min(r8, r9) back-roof Gaussians seen",
           masking_check=dict(camera=k8, r8_aimed_seen=int(s8.sum()), r9=check))
(OUT / "views_shared.json").write_text(json.dumps(res, indent=1))
print("figure camera", k, best)
