"""PHD-MAIN-METRICS-TRIAL-v1 4.4 path 5 (jointbuildgs:dev, CPU): the MVS of the training images at the GT roof points.

  python mvs_path.py

COLMAP geometric depth (confidence 1 = a valid geometric depth, the r10 confidence mask) of the 203 box training views of
B173nb_b10 (/prep/mvs/box_B173nb_b10), back-projected with the stage-1 camera convention (stage-0 common.Views: the 937 posed
images, native 1024 x 741 grid, camera-Z depth); z_MVS at a GT point = median of the MVS points in its 0.1 m cell (>= 3).
Query points = GT roof points of the rows of both priors in the regions measured agreement (2), image wrong (3), prior wrong
(11) and both wrong (12): path 5 on the accuracy points, and (a record, purpose: checking the per-patch MVS proxy that splits
11 from 12) the MVS height at the GT points of the conflicts. Writes /out/paths/mvs_points.npz. scientific_verdict: null."""
import json

import numpy as np

from mt_common import MCFG, OUT, PREP, S0, SITE, Timer, Views, jdump, log, read_depth_bin
from src.phd.metrics_v1.cells import CellMedian


def main():
    T = Timer()
    (OUT / "paths").mkdir(parents=True, exist_ok=True)
    G = np.load(OUT / "defs/gt_classes.npz")
    X = G["xyz"].astype(np.float64)
    pts = []
    for prior in ("LoD2", "ALS"):
        r = np.load(OUT / "defs" / f"rows_{prior}.npz")
        m = (r["kind"] == 1) & np.isin(r["code"], (2, 3, 11, 12))
        pts.append(r["point"][m])
    q = np.unique(np.concatenate(pts))
    bp = MCFG["bias_paths"]
    cm = CellMedian(X[q, :2], bp["cell_m"])
    names = json.loads((S0 / "fork_inputs/s61" / SITE / "split.json").read_text())["train"]
    V = Views()
    mvs = PREP / "mvs" / f"box_{SITE.split('_')[0]}_{SITE.split('_')[1]}"
    used, kept = 0, 0
    for i, n in enumerate(names):
        n = n if n.endswith(".JPG") else n + ".JPG"          # split.json names carry no extension; COLMAP names do
        p = mvs / "stereo/depth_maps" / f"{n}.geometric.bin"
        if not p.exists():
            continue
        d = read_depth_bin(p)
        ok = np.isfinite(d) & (d > 0)
        P = V.C(n)[None, :] + d[ok][:, None].astype(np.float64) * V.rays(n, np.float64)[ok]
        kept += cm.add(P)
        used += 1
        if i % 40 == 0:
            log(i, n, "points kept", kept)
    z, cnt = cm.medians(bp["min_points"])
    np.savez_compressed(OUT / "paths/mvs_points.npz", point=q, z=z.astype(np.float32), n=cnt.astype(np.int32))
    jdump(OUT / "paths/mvs_points.json", dict(rule=bp["paths"]["5"], views=used, query_points=int(len(q)), with_value=int(np.isfinite(z).sum()),
                                              points_kept=int(kept), mvs=str(mvs), seconds=T.mark("all"), scientific_verdict=None))
    print("mvs path done", used, int(np.isfinite(z).sum()), "/", len(q), T.mark("all"))


if __name__ == "__main__":
    main()
