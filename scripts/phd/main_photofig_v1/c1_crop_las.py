"""PHD-MAIN-PHOTOFIG-v1: crop the drone LiDAR files to the three site boxes in one pass each (figure 6, table B, figure 1 sections).
(jointbuildgs:dev, CPU)

  python c1_crop_las.py <src> [...]     src = nadir (v1.1.0 = the study's file) | manual (v1.2.0, fetched by B0REF) | fill (v1.2.0 5 mm)
  -> /pf/crop/<site>/<src>.npz  xyz (local float64 = laz - world shift, no height alignment), return_number, number_of_returns,
     gps_time, red, green, blue (16 bit);  /pf/crop/<src>_inventory.json (points per site, GPS range per site)
Chunks of 4 M points, cut to the box (+ 0 m; the box is the evaluation range + 10 m) before anything is kept. scientific_verdict: null"""
import sys
import time

import numpy as np

from pf_common import LAS, PF, SHIFT, SITES, in_rect, jdump, log, now

KEEP = ("return_number", "number_of_returns", "gps_time", "red", "green", "blue")


def main(src):
    import laspy
    t0 = time.time()
    parts = {s: {k: [] for k in ("xyz",) + KEEP} for s in SITES}
    n = 0
    with laspy.open(str(LAS[src]), laz_backend=laspy.LazBackend.LazrsParallel) as f:
        for pts in f.chunk_iterator(4_000_000):
            x = np.asarray(pts.x) - SHIFT[0]; y = np.asarray(pts.y) - SHIFT[1]
            n += len(x)
            xy = np.column_stack([x, y])
            for s in SITES:
                m = in_rect(xy, s, "box")
                if m.any():
                    parts[s]["xyz"].append(np.column_stack([x[m], y[m], np.asarray(pts.z)[m] - SHIFT[2]]))
                    for k in KEEP:
                        parts[s][k].append(np.asarray(getattr(pts, k))[m])
            if n % 40_000_000 < 4_000_000:
                log(src, f"{n:,} read")
    inv = dict(src=src, path=str(LAS[src]), points_in_file=n, sites={}, made=now(), scientific_verdict=None)
    for s in SITES:
        if not parts[s]["xyz"]:
            inv["sites"][s] = dict(points=0)
            continue
        out = {k: np.concatenate(v) for k, v in parts[s].items()}
        (PF / "crop" / s).mkdir(parents=True, exist_ok=True)
        np.savez(PF / "crop" / s / f"{src}.npz", **out)
        g = out["gps_time"]
        inv["sites"][s] = dict(points=int(len(g)), gps_min=float(g.min()), gps_max=float(g.max()))
        del out
    inv["seconds"] = round(time.time() - t0, 1)
    jdump(PF / "crop" / f"{src}_inventory.json", inv)
    log(src, "done", inv["sites"], inv["seconds"])


if __name__ == "__main__":
    for s in sys.argv[1:]:
        main(s)
