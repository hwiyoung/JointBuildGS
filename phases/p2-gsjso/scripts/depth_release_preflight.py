#!/usr/bin/env python3
"""P2 impl ② preflight — gate before the 2x95min runs. Condition A config.

Checks (assert + print; if any fails, DO NOT launch the main runs):
  ① seeds entered model.means      — # seeds in each textureless footprint > 0
  ② L_sem actually computes        — semantic mask loads, w_sem>0, print loss_sem
  ③ detach-release works           — L_sem-only 1 backward -> seed-row means.grad != 0 with
                                      sem_detach_geometry=False; == 0 with True (contrast)
  ⑤ ground position sane           — converted LiDAR ground_local in [-45,-41]±3 & below seed column
(④ seed survival to 500 steps is run separately via train.py max_iter=500.)

Runs in dev container (torch). Reads configs/tum_mob/depth_release_range.yaml.
"""
import sys, json, yaml
from pathlib import Path
import numpy as np, torch
from matplotlib.path import Path as MplPath
sys.path.insert(0, "/workspace/JointBuildGS")
from src.stage2.dataloader import ColmapDataset
from src.stage2.model import GaussianModel2D
from src.stage2.semantic_seed import build_semantic_seeds, cameras_from_frames, concat_seeds
from src.stage2.renderer import render_semantic
from src.stage2.loss import data_fitting as L

REPO = "/workspace/JointBuildGS"
NOSEED = ["42364609", "4907182", "4908050", "4908166", "4908176"]
ALLREC = NOSEED + ["42364659", "42364663", "4907510"]


def ring_local(geo, bid, shift):
    g = [f for f in geo if f["properties"]["building_id"] == bid][0]["geometry"]
    co = g["coordinates"][0] if g["type"] == "Polygon" else g["coordinates"][0][0]
    return np.asarray(co)[:, :2] - np.asarray(shift)[:2]


def main():
    cfg = yaml.safe_load(open(f"{REPO}/configs/tum_mob/depth_release_range.yaml"))
    dev = "cuda"
    sc = cfg["seed_cfg"]
    shift = sc["world_offset"]
    geo = json.load(open(sc["footprints"]))["features"]

    ds = ColmapDataset(root=cfg["data_root"], downscale=1.0,
                       load_depth=False, load_normal=False, load_semantic=True)
    bands = json.loads(Path(sc["bands_file"]).read_text())
    seeds = build_semantic_seeds(
        cameras=cameras_from_frames(ds.frames), semantic_dir=sc["semantic_dir"],
        footprints_path=sc["footprints"], buildings=sc["buildings"],
        scene_rgb=ds.points_rgb.mean(0), id_field="building_id", world_offset=shift,
        bands=bands, voxel=sc["voxel"], tau=sc["tau"], min_obs=sc["min_obs"], verbose=False)
    pxyz, prgb, psem = concat_seeds(ds.points_xyz, ds.points_rgb, seeds)
    model = GaussianModel2D(points_xyz=pxyz, points_rgb=prgb, sh_degree=3, device=dev, points_sem=psem).to(dev)
    seed_mask = torch.from_numpy(psem >= 0).to(dev)
    means_np = model.means.detach().cpu().numpy()

    print("\n===== PREFLIGHT (condition A) =====")
    # ① seeds in footprints (model.means within each textureless footprint)
    print("① seeds in model.means (textureless footprints):")
    ok1 = True
    for b in NOSEED:
        r = ring_local(geo, f"DEBY_LOD2_{b}", shift); fp = MplPath(r)
        n = int(fp.contains_points(means_np[:, :2]).sum())
        ok1 &= n > 0
        print(f"    {b}: {n} means in footprint")
    print(f"   -> {'PASS' if ok1 else 'FAIL'}  (total seeds added = {int(seed_mask.sum())})")

    # pick a frame that sees a seeded building (42364663 best frame) for ②③
    fr_names = [fr.name for fr in ds.frames]
    target = "DJI_20241217103039_0045_D.JPG"
    fi = fr_names.index(target) if target in fr_names else 0
    batch = ds[fi]
    w2c = batch["w2c"].to(dev); K = batch["K"].to(dev); H, W = batch["height"], batch["width"]
    sem_gt = batch["semantic"].to(dev)

    # ② L_sem computes
    sem_pred = render_semantic(model, w2c, K, W, H, sem_detach_geometry=False)
    loss_sem = L.l_sem(sem_pred, sem_gt, ignore_index=0)
    print(f"② L_sem computes: semantic in batch={'semantic' in batch}, loss_sem={loss_sem.item():.4f}  "
          f"-> {'PASS' if torch.isfinite(loss_sem) and loss_sem.item()>0 else 'FAIL'}")

    # ③ detach release: grad to seed-row means (False) vs 0 (True)
    def seed_grad(detach):
        if model.means.grad is not None:
            model.means.grad = None
        sp = render_semantic(model, w2c, K, W, H, sem_detach_geometry=detach)
        L.l_sem(sp, sem_gt, ignore_index=0).backward()
        g = model.means.grad
        if g is None:
            return 0.0
        return float(g[seed_mask].norm().item())
    g_false = seed_grad(False)
    g_true = seed_grad(True)
    ok3 = g_false > 0 and g_true == 0.0
    print(f"③ detach release: seed-row means.grad  False(②)={g_false:.3e}  True(current)={g_true:.3e}  "
          f"-> {'PASS' if ok3 else 'FAIL'}")

    # ⑤ ground sane: ground_local from meta vs [-45,-41]±3 & below seed column bottom
    meta = json.loads(Path(f"{REPO}/results/tum_transfer/mob_analysis/seed_bands_meta.json").read_text())
    grow = {row["bid"]: row for row in meta["rows"]}
    print("⑤ ground sane (ground_local in expected [-48,-38]; seed column rises above ground = building):")
    ok5 = True
    for b in ALLREC:
        bid = f"DEBY_LOD2_{b}"
        gl = grow[bid]["ground_local"]
        r = ring_local(geo, bid, shift); fp = MplPath(r)
        sm = fp.contains_points(means_np[:, :2]) & (psem >= 0)
        zmin = float(means_np[sm, 2].min()) if sm.any() else float("nan")
        zmax = float(means_np[sm, 2].max()) if sm.any() else float("nan")
        in_range = (-48 <= gl <= -38)               # converted LiDAR ground where expected (not ~48m off)
        rises = zmax > gl + 1.0                      # roof/wall seeds sit above ground (a real building)
        not_below = zmin >= gl - 1.5                 # carve doesn't seed below the band floor (ground-1)
        sane = in_range and rises and not_below
        ok5 &= sane
        print(f"    {b}: ground_local={gl:.1f}  seed_col=[{zmin:.1f},{zmax:.1f}]  "
              f"in_range={in_range} rises_above_ground={rises} not_below_floor={not_below}  {'ok' if sane else 'CHECK'}")
    print(f"   -> {'PASS' if ok5 else 'CHECK'}")

    allok = ok1 and torch.isfinite(loss_sem) and loss_sem.item() > 0 and ok3 and ok5
    print(f"\n===== PREFLIGHT ①②③⑤: {'ALL PASS' if allok else 'FAILURE — DO NOT LAUNCH'} =====")


if __name__ == "__main__":
    main()
