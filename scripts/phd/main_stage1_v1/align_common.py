"""PHD-MAIN-STAGE1-v1 3.1: one common GT height shift of the four boxes (jointbuildgs:dev, CPU; definitions = configs
main_stage1_v1.json 'common_alignment').

  python align_common.py diffs <box> <pass> <shift_so_far>   per-box bare-ground differences of one pass -> /out/v3/align/<box>_pass<k>.npz
  python align_common.py pool <pass>                          pooled median of the four boxes' differences -> /out/v3/align/pass<k>.json
  python align_common.py summary                              C, per-box shifts, reproduction check -> /out/v3/align/common_shift.json

Per box the pixel selection is that of the per-box alignment (s04_gt_v6.align_px): up to 40 box training views evenly spaced
by name (box_views.json, with a geometric depth map), the GT z-buffer (9 x 9 leak filter 0.3 m) of the cleaned ULS GT with
the box shift taken back, the box MVS geometric depth on bare-ground pixels (s04 ground definition, inside the box range;
range + 20 m when fewer than 5,000 pixels). scientific_verdict: null."""
import json
import sys
from pathlib import Path

import numpy as np

from s1_common import CFG, DR, OUT, PREP, SITES, Timer, Views, box_shift, jdump, log
import s04_gt_v6 as s04
from common import inside_range, widen
from src.phd.metrics_v3 import align

A_DIR = OUT / "v3/align"


def ground_masks(box):
    """the s04 bare hard ground cells inside the box range and inside range + prior margin (copied from s04_gt_v6.main)."""
    G, A = s04.survey_grids()
    grid = s04.Grid(G["dtm"].shape)
    rng = json.loads((DR / "s02_box" / box / "range.json").read_text())
    wide = widen(rng, CFG["ranges"]["prior_margin_m"]) if rng["kind"] != "polygon" else rng
    dtm = G["dtm"].astype(float); uls = G["uls"].astype(float); mvs = G["mvs"].astype(float)
    rough = A["uls_zmax"] - A["uls_zmin"]
    umulti = np.where(A["uls_n"] > 0, A["uls_n_multi"] / np.maximum(A["uls_n"], 1), 1.0)
    ground = (A["als_n_c2"] >= 2) & (rough < 0.25) & (G["fid"] < 0) & (G["veg"] < 0.05) & np.isfinite(uls) & np.isfinite(mvs) & (np.abs(uls - dtm) < 1.0) & (umulti < 0.05)
    EE, NN = np.meshgrid(grid.e0 + (np.arange(grid.nx) + 0.5) * grid.res, grid.n0 + (np.arange(grid.ny) + 0.5) * grid.res)
    cxy = np.stack([EE.ravel() - 690953.0, NN.ravel() - 5336071.0], 1)
    inr_cells = inside_range(cxy, rng).reshape(EE.shape) if rng["kind"] != "polygon" else np.zeros(EE.shape, bool)
    wide_cells = inside_range(cxy, wide).reshape(EE.shape) if rng["kind"] != "polygon" else np.ones(EE.shape, bool)
    return grid, ground & inr_cells, ground & wide_cells


def views_of(box, mvs_dir, n=40):
    views = json.loads((PREP / "step06/box_views.json").read_text())["views"][box]["train"]
    views = views if isinstance(views, list) else views["train"]
    views = [v for v in views if (Path(mvs_dir) / "stereo/depth_maps" / f"{v}.geometric.bin").exists()]
    return [views[int(i)] for i in np.unique(np.linspace(0, len(views) - 1, min(n, len(views))).round().astype(int))]


def diffs(box, k, shift):
    T = Timer()
    A_DIR.mkdir(parents=True, exist_ok=True)
    X = np.load(DR / "s52/box_gt" / box / "gt_points.npz")["xyz"].astype(np.float64)
    X[:, 2] -= box_shift(box)                       # the cleaned ULS before any alignment
    mvs_dir = PREP / "mvs" / f"box_{box}"
    sel = views_of(box, mvs_dir)
    grid, g_range, g_wide = ground_masks(box)
    Vw = Views()
    dr, dw = [], []
    for nme in sel:
        gt, _ = s04.zbuf(Vw, nme, X, shift)
        dr.append(s04.ground_diffs(Vw, nme, gt, mvs_dir, grid, g_range))
        dw.append(s04.ground_diffs(Vw, nme, gt, mvs_dir, grid, g_wide))
    d, src = align.select_pixels(np.concatenate(dr), np.concatenate(dw), SCFG_MIN_PX)
    np.savez_compressed(A_DIR / f"{box}_pass{k}.npz", d=d.astype(np.float64), source=src, views=np.array(sel), shift_applied=shift)
    log(box, "pass", k, "pixels", d.size, src, "median", round(float(np.median(d)), 5), T.mark("all"))


SCFG_MIN_PX = 5000


def pool(k):
    ds = {b: np.load(A_DIR / f"{b}_pass{k}.npz") for b in SITES}
    med, n = align.pooled_median([ds[b]["d"] for b in SITES])
    per = {b: dict(pixels=int(ds[b]["d"].size), source=str(ds[b]["source"]), median_m=float(np.median(ds[b]["d"])), shift_applied=float(ds[b]["shift_applied"]))
           for b in SITES}
    jdump(A_DIR / f"pass{k}.json", dict(pass_=k, pooled_pixels=n, pooled_median_m=med, per_box=per, scientific_verdict=None))
    print(json.dumps(dict(pass_=k, pooled_median_m=med, pooled_pixels=n)))


def summary():
    p1 = json.loads((A_DIR / "pass1.json").read_text())
    p2 = json.loads((A_DIR / "pass2.json").read_text())
    C = p1["pooled_median_m"] + p2["pooled_median_m"]
    rows, ok = {}, True
    for b in SITES:
        rec = json.loads((DR / "s52/box_gt" / b / "gt_summary.json").read_text())["height_alignment"]
        rp1 = rec["passes"][0]["median_mvs_minus_gt_m"]
        mine = p1["per_box"][b]["median_m"]
        rep = abs(mine - rp1) <= 1e-4          # the config check (median within 1e-4 m); the pixel counts are reported next to it
        ok &= rep
        rows[b] = dict(shift_box_m=box_shift(b), common_minus_box_m=C - box_shift(b), pass1_own_median_m=mine, pass1_recorded_median_m=rp1,
                       pass1_own_pixels=p1["per_box"][b]["pixels"], pass1_recorded_pixels=rec["passes"][0]["pixels"], reproduced=bool(rep))
    stop = [b for b in SITES if abs(C - box_shift(b)) > 0.10]
    jdump(A_DIR / "common_shift.json", dict(common_shift_m=C, passes=[p1, p2], boxes=rows, reproduction_ok=bool(ok), stop_boxes_over_10cm=stop,
                                           rule=json.loads(Path("/repo/configs/phd/main_stage1_v1/main_stage1_v1.json").read_text())["common_alignment"],
                                           scientific_verdict=None))
    print(json.dumps(dict(C=C, reproduction_ok=bool(ok), stop=stop, boxes={b: round(r["common_minus_box_m"], 4) for b, r in rows.items()})))


if __name__ == "__main__":
    if sys.argv[1] == "diffs":
        diffs(sys.argv[2], int(sys.argv[3]), float(sys.argv[4]))
    elif sys.argv[1] == "pool":
        pool(int(sys.argv[2]))
    else:
        summary()
