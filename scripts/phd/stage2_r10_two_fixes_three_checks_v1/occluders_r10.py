"""PHD-STAGE2-R10-TWO-FIXES-THREE-CHECKS-v1 (conf-guided image, GPU; /source = r10 fork, /s2, /p9, /p10, /repo): what hides
the aimed Gaussians in the product layer (check 'da', order 3-1 'gaim'), per added view.

  python occluders_r10.py <run> [...]

The added views are rebuilt with the mesh step's rule from the run's aimed region (mesh/<run>/invisible.npz; the camera
centres must equal mesh.json's). Per view:
  hidden      an aimed Gaussian inside the image whose centre lies more than 0.5 m behind the rendered expected depth of the
              whole scene (accumulated opacity >= 0.05) -- r9's seeing test, one-sided
  removal     per group G: the scene rendered without G; the hidden aimed Gaussians that become seen = the ones G hides
              (a Gaussian hidden by two groups becomes seen only when both are gone, so the shares need not add up)
  occluders   Gaussians of G with opacity >= 0.5 that lie more than 0.5 m in front of a hidden aimed Gaussian and whose
              projected centre is within one standard deviation (the rasterizer's 3-sigma screen radius / 3) of its pixel
Groups (they overlap): image origin; scale above 1 m (largest axis); prior origin of other buildings; protected at the end;
prior origin of the target building that is not aimed; and everything that is not aimed (what stays hidden then is hidden
by other aimed Gaussians: the far side of the building seen from that view).
The mesh step's first count (3-sigma screen radius, opacity >= 0.05; mesh/<run>/occluders.json) found an image-origin
occluder for 99.98 % of the hidden ones and is kept only as a record.
Writes /p10/mesh/<run>/occluders_v2.json."""
import json
import sys
from argparse import ArgumentParser
from pathlib import Path

import numpy as np
import torch
from scipy.spatial import cKDTree

sys.path.insert(0, "/source")
from arguments import ModelParams, PipelineParams  # noqa: E402
from gaussian_renderer import GaussianModel, render  # noqa: E402
from scene import Scene  # noqa: E402
from utils.render_utils import create_virtual_cameras_for_completion  # noqa: E402
import jbgs_judgment as J  # noqa: E402

P10 = Path("/p10"); P9 = Path("/p9")
for run in sys.argv[1:]:
    rec = json.loads((P10 / "runs" / run / "receipt.json").read_text())
    setting, its, cond = rec["setting"], int(rec["iterations"]), rec["condition_json"]["condition"]
    parser = ArgumentParser(); mp = ModelParams(parser); pp = PipelineParams(parser)
    scene_dir = f"/p10/scenes/{setting}" if setting.startswith("M") else f"/s2/runs/{cond}/scene"
    args = parser.parse_args(["-s", scene_dir, "-m", f"/p10/runs/{run}/model", "--eval"])
    ds, pipe = mp.extract(args), pp.extract(args)
    g = GaussianModel(ds.sh_degree); sc = Scene(ds, g, load_iteration=its, shuffle=False)
    bg = torch.tensor([0, 0, 0], dtype=torch.float32, device="cuda")
    train = sc.getTrainCameras()
    iv = np.load(P10 / "mesh" / run / "invisible.npz"); mj = json.loads((P10 / "mesh" / run / "mesh.json").read_text())
    reg = torch.as_tensor(iv["region"], device="cuda")
    g.completed_mask = reg
    with torch.no_grad():
        virtual = create_virtual_cameras_for_completion(gaussians=g, reference_cameras=train, n_virtual_cams=8, distance_scale=1.5)
    g.completed_mask = None
    cc = np.array([v.camera_center.cpu().numpy() for v in virtual])
    same_cams = bool(np.allclose(cc, np.array(mj["virtual_camera_centres"]), atol=1e-4))
    dump = np.load(P10 / "runs" / run / f"model/dump/iteration_{its}/gaussians.npz")
    var = "poly" if setting.startswith("M") else "lod2"
    root = P10 if setting.startswith("M") else P9
    table = {r["ext"]: r for r in json.loads((root / "stage1/products" / setting / f"surfaces_{var}.json").read_text())["surfaces"]}
    ids = dump["init_id"].astype(np.int64)
    ext = torch.as_tensor(np.where(ids >= 0, dump["init_surface_ext"][np.maximum(ids, 0)], -1), device="cuda")
    tgt = torch.as_tensor(sorted(e for e, r in table.items() if r.get("target")), device="cuda")
    org = torch.as_tensor(dump["origin"], device="cuda"); lock = torch.as_tensor(dump["locked"], device="cuda")
    on_t = torch.isin(ext, tgt)
    big = g.get_scaling.detach().max(1).values > 1.0
    op = g.get_opacity.squeeze(-1).detach()
    xyz = g.get_xyz.detach()
    G = {"image origin": org == 0, "scale above 1 m": big, "prior of other buildings": (org == 1) & ~on_t, "protected": lock,
         "prior of the target building (not aimed)": (org == 1) & on_t & ~reg, "everything not aimed": ~reg}
    for k in G:
        G[k] = G[k] & ~reg

    def subset(keep):
        h = GaussianModel(ds.sh_degree); h.active_sh_degree = g.active_sh_degree
        for nm in ("_xyz", "_features_dc", "_features_rest", "_scaling", "_rotation", "_opacity"):
            setattr(h, nm, torch.nn.Parameter(getattr(g, nm).detach()[keep].clone(), requires_grad=False))
        return h
    subs = {k: subset(~m) for k, m in G.items()}
    idx = torch.nonzero(reg).squeeze(1)

    @torch.no_grad()
    def seen_of(model, cam, pts):
        pkg = render(cam, model, pipe, bg)
        D = pkg["surf_depth"].squeeze(0); AL = pkg["rend_alpha"].squeeze(0)
        Hh, Ww = D.shape
        u, v, z = J.project_points(pts, cam)
        ui, vi = torch.round(u).long(), torch.round(v).long()
        inside = (z > 0.01) & (ui >= 0) & (ui < Ww) & (vi >= 0) & (vi < Hh)
        pix = vi.clamp(0, Hh - 1) * Ww + ui.clamp(0, Ww - 1)
        hid = inside & (AL.reshape(-1)[pix] >= 0.05) & (z > D.reshape(-1)[pix] + 0.5)
        return inside, hid, (u, v, z), pkg["radii"]
    rows, tot = [], dict(inside=0, hidden=0, **{f"freed_{k}": 0 for k in G}, **{f"occ_{k}": 0 for k in G})
    for vi_, cam in enumerate(virtual):
        inside, hid, (u, v, z), radii = seen_of(g, cam, xyz[idx])
        row = dict(camera=vi_, inside=int(inside.sum()), hidden=int(hid.sum()))
        for k, h in subs.items():
            _, hid_k, _, _ = seen_of(h, cam, xyz[idx])
            row[f"freed_{k}"] = int((hid & ~hid_k).sum())
        if bool(hid.any()):
            hu = torch.stack([u[hid], v[hid]], 1).cpu().numpy(); hz = z[hid].cpu().numpy()
            tree = cKDTree(hu)
            for k, m in G.items():
                ci = torch.nonzero(m & (radii > 0) & (op >= 0.5)).squeeze(1)
                if ci.numel() == 0:
                    row[f"occ_{k}"] = 0; continue
                cu, cv, cz = J.project_points(xyz[ci], cam)
                r1 = (radii[ci].float() / 3.0).cpu().numpy()
                L = tree.query_ball_point(np.stack([cu.cpu().numpy(), cv.cpu().numpy()], 1), r=np.maximum(r1, 0.5), workers=-1)
                czn = cz.cpu().numpy()
                row[f"occ_{k}"] = int(sum(1 for j, l in enumerate(L) if l and (hz[np.asarray(l)] > czn[j] + 0.5).any()))
        for k_ in tot:
            tot[k_] += row.get(k_, 0)
        rows.append(row)
        print(run, json.dumps(row)[:300], flush=True)
    res = dict(run=run, rule=__doc__.split("\n\n")[1], cameras_equal_mesh_step=same_cams, n_aimed=int(reg.sum()), totals=tot,
               hidden_share=tot["hidden"] / max(tot["inside"], 1),
               freed_share_of_hidden={k: tot[f"freed_{k}"] / max(tot["hidden"], 1) for k in G},
               occluders={k: tot[f"occ_{k}"] for k in G}, per_view=rows,
               group_sizes={k: int(m.sum()) for k, m in G.items()})
    (P10 / "mesh" / run / "occluders_v2.json").write_text(json.dumps(res, indent=1))
    print(run, json.dumps({k: res[k] for k in ("cameras_equal_mesh_step", "hidden_share", "freed_share_of_hidden", "occluders")}), flush=True)
    del g, sc, subs
    torch.cuda.empty_cache()
