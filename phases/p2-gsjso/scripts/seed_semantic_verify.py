#!/usr/bin/env python3
"""P2 ① acceptance check: do semantic seeds appear inside textureless footprints?

Builds the carve seeds, constructs the REAL ``GaussianModel2D`` with the seeds
concatenated onto the SfM init cloud (exercising the new ``points_sem`` path), and
counts ``model.means`` falling inside each target footprint (xy, point-in-polygon):

    seeding OFF (vanilla)  = SfM-only rows of model.means  -> expect ~0
    seeding ON             = all rows (SfM + seeds)         -> expect >0

Counting is done in UTM (means + world_offset) against the footprint polygon, matching
``tum_mob_seeding_diag.py``. Writes a JSON summary + a top-view figure. dev container.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.path import Path as MplPath  # noqa: E402

from src.stage2.dataloader import ColmapDataset
from src.stage2.model import GaussianModel2D
from src.stage2.semantic_seed import (
    build_semantic_seeds, cameras_from_frames, concat_seeds, ROOF_CODE_DEFAULT,
)

REPO = "/workspace/JointBuildGS"
DATA_ROOT = f"{REPO}/results/tum_transfer/data"
SEMANTIC_DIR = f"{REPO}/results/tum_transfer/clean_labels_geoidfix/semantic"
FOOTPRINTS = f"{REPO}/results/tum_transfer/analysis/footprints_aoi.geojson"
OUT_DIR = Path(f"{REPO}/results/tum_transfer/mob_analysis")
WORLD_OFFSET = np.array([690953.0, 5336071.0, 604.0])

# the 5 textureless "make-or-break" buildings the task requires (subset of the 8)
TEXTURELESS_5 = {"42364609", "4907182", "4908050", "4908166", "4908176"}
TARGETS = ["42364609", "42364659", "42364663", "4907182", "4907510",
           "4908050", "4908166", "4908176"]
BUILDINGS = [f"DEBY_LOD2_{t}" for t in TARGETS]


def footprint_ring(geo, bid):
    g = [f for f in geo if f["properties"]["building_id"] == bid][0]["geometry"]
    co = g["coordinates"][0] if g["type"] == "Polygon" else g["coordinates"][0][0]
    return np.asarray(co)[:, :2]


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    geo = json.load(open(FOOTPRINTS))["features"]

    print("[load] ColmapDataset ...")
    ds = ColmapDataset(root=DATA_ROOT, downscale=1.0, load_depth=False, load_normal=False)
    print(f"[load] frames={len(ds)} SfM_pts={ds.points_xyz.shape[0]}")

    print("[carve] building semantic seeds ...")
    seeds = build_semantic_seeds(
        cameras=cameras_from_frames(ds.frames),
        semantic_dir=SEMANTIC_DIR, footprints_path=FOOTPRINTS, buildings=BUILDINGS,
        scene_rgb=ds.points_rgb.mean(axis=0), id_field="building_id",
        world_offset=WORLD_OFFSET, z_min=-55.0, z_max=5.0, voxel=1.0, tau=0.6,
        min_obs=5, roof_code=1, wall_code=2, max_seeds_per_building=0, verbose=True)

    n_sfm = ds.points_xyz.shape[0]
    pts_xyz, pts_rgb, pts_sem = concat_seeds(ds.points_xyz, ds.points_rgb, seeds)

    # construct the real model (CPU; validates the points_sem init path)
    print("[model] constructing GaussianModel2D with seeds (device=cpu) ...")
    model = GaussianModel2D(points_xyz=pts_xyz, points_rgb=pts_rgb, points_sem=pts_sem,
                            sh_degree=3, device="cpu")
    means = model.means.detach().cpu().numpy()
    means_utm = means + WORLD_OFFSET
    is_seed = pts_sem >= 0
    # sanity: model init matches our expectations
    assert means.shape[0] == n_sfm + len(seeds.xyz)
    opa = model.opacities.detach().cpu().numpy()
    sem_argmax = model.sem_logits.detach().cpu().numpy().argmax(axis=1)
    print(f"[model] N={means.shape[0]} (SfM={n_sfm} + seeds={len(seeds.xyz)})  "
          f"seed opacity={opa[is_seed].mean():.3f} (expect 0.25), "
          f"SfM opacity={opa[~is_seed].mean():.3f} (expect 0.10)")
    if is_seed.any():
        agree = float((sem_argmax[is_seed] == pts_sem[is_seed]).mean())
        print(f"[model] seed sem_logits argmax == carved class: {agree*100:.1f}% (expect 100%)")

    rows = []
    print("\n%-20s %-4s %8s %8s %8s %8s" %
          ("building", "tex5", "SfM(OFF)", "ON_tot", "seeds", "roof/wall"))
    for t in TARGETS:
        bid = f"DEBY_LOD2_{t}"
        fp = MplPath(footprint_ring(geo, bid))
        inb = fp.contains_points(means_utm[:, :2])
        off = int((inb & ~is_seed).sum())
        on = int(inb.sum())
        seed_in = int((inb & is_seed).sum())
        seed_cls = sem_argmax[inb & is_seed]
        n_roof = int((seed_cls == ROOF_CODE_DEFAULT).sum())
        n_wall = int((seed_cls == 2).sum())
        rows.append(dict(building=bid, textureless5=(t in TEXTURELESS_5),
                         sfm_in_fp_OFF=off, model_means_in_fp_ON=on,
                         seeds_in_fp=seed_in, seed_roof=n_roof, seed_wall=n_wall,
                         carve=seeds.per_building.get(bid, {})))
        print("%-20s %-4s %8d %8d %8d   %d/%d" %
              (bid, "YES" if t in TEXTURELESS_5 else "-", off, on, seed_in, n_roof, n_wall))

    summary = dict(
        n_sfm=n_sfm, n_seeds_total=int(len(seeds.xyz)),
        z_band=[-55.0, 5.0], voxel=1.0, tau=0.6, min_obs=5,
        semantic_dir=SEMANTIC_DIR, world_offset=WORLD_OFFSET.tolist(),
        seed_init_opacity=float(opa[is_seed].mean()) if is_seed.any() else None,
        rows=rows)
    (OUT_DIR / "seed_semantic_verify.json").write_text(json.dumps(summary, indent=2))
    print(f"\n[done] -> {OUT_DIR/'seed_semantic_verify.json'}")

    # ---- top-view figure: footprint + seeds (roof red / wall green) + SfM (grey) ----
    seed_xyz_utm = seeds.xyz + WORLD_OFFSET
    fig, axes = plt.subplots(2, 4, figsize=(20, 10))
    for ax, t in zip(axes.ravel(), TARGETS):
        bid = f"DEBY_LOD2_{t}"
        ring = footprint_ring(geo, bid)
        ax.plot(np.r_[ring[:, 0], ring[0, 0]], np.r_[ring[:, 1], ring[0, 1]], "k-", lw=1.5)
        fp = MplPath(ring)
        # SfM points in/near fp
        sfm_utm = ds.points_xyz + WORLD_OFFSET
        m_sfm = fp.contains_points(sfm_utm[:, :2])
        if m_sfm.any():
            ax.scatter(sfm_utm[m_sfm, 0], sfm_utm[m_sfm, 1], s=2, c="0.6", label="SfM")
        m_seed = fp.contains_points(seed_xyz_utm[:, :2])
        sc = seeds.sem[m_seed]
        for cls, col, lab in [(1, "#dc2828", "roof"), (2, "#28c83c", "wall")]:
            mm = m_seed.copy(); mm[m_seed] = (sc == cls)
            if mm.any():
                ax.scatter(seed_xyz_utm[mm, 0], seed_xyz_utm[mm, 1], s=3, c=col, label=lab)
        tag = "  [make-or-break]" if t in TEXTURELESS_5 else ""
        ax.set_title(f"{bid}{tag}\nSfM={int(m_sfm.sum())}  seeds={int(m_seed.sum())}", fontsize=9)
        ax.set_aspect("equal"); ax.legend(fontsize=7, loc="upper right")
    fig.suptitle("P2 ① semantic seeds (top view, UTM) — vanilla SfM gives ~0 in textureless footprints",
                 fontsize=13)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "seed_semantic_topview.png", dpi=110)
    print(f"[done] -> {OUT_DIR/'seed_semantic_topview.png'}")


if __name__ == "__main__":
    main()
