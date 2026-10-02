"""PHD-MAIN-PREP-MEASURE-v1 step 06a (jointbuildgs:dev, CPU): case boxes and their candidate views.

  python step06a_box_views.py <boxes_json_relative_to_/out>

boxes json: {"boxes": {"<id>": {"eval_u": [u0, u1], "eval_v": [v0, v1], "bands": [10, 20, 40], "label": ...}}}
For every box and band b: range = evaluation range widened by b (uv box); candidate views by the 9-15 audit rule
(step 01 implementation), 1 in 8 for evaluation. Writes /out/step06/box_ranges.json and box_views.json
(range id '<box>_b<band>'). scientific_verdict: null."""
import json
import sys

import numpy as np

from common import CFG, DENSE, OUT, SHIFT, GRID_H, GRID_W, Views, inside_range, jdump, log, range_polygon, read_depth_bin, read_fused_rows

spec = json.loads((OUT / sys.argv[1]).read_text())
D = OUT / "step06"; D.mkdir(parents=True, exist_ok=True)
ranges = {}
for bid, b in spec["boxes"].items():
    for band in b["bands"]:
        rid = f"{bid}_b{int(band)}"
        r = dict(id=rid, box=bid, band_m=band, kind="uv_box", u_m=[b["eval_u"][0] - band, b["eval_u"][1] + band],
                 v_m=[b["eval_v"][0] - band, b["eval_v"][1] + band], eval_u=b["eval_u"], eval_v=b["eval_v"], label=b.get("label", ""))
        P = range_polygon(r); r["polygon_local"] = P.tolist(); r["polygon_epsg25832"] = (P + SHIFT[:2]).tolist()
        r["area_m2"] = float((r["u_m"][1] - r["u_m"][0]) * (r["v_m"][1] - r["v_m"][0]))
        r["eval_area_m2"] = float((b["eval_u"][1] - b["eval_u"][0]) * (b["eval_v"][1] - b["eval_v"][0]))
        ranges[rid] = r
jdump(D / "box_ranges.json", ranges)
xyz, rows = read_fused_rows(16)
zb = CFG["ranges"]["z_m"]
ok = np.isfinite(xyz).all(1) & (xyz[:, 2] >= zb[0]) & (xyz[:, 2] < zb[1])
xyz = xyz[ok]
_, first = np.unique(np.floor(xyz / 1.0).astype(np.int32), axis=0, return_index=True)
ref = xyz[np.sort(first)].astype(np.float64)
refs = {rid: ref[inside_range(ref[:, :2], r)] for rid, r in ranges.items()}
V = Views()
fx, fy, cx, cy = V.K
yy, xx = np.indices((GRID_H, GRID_W), dtype=np.float64)
nrays = np.stack([(xx - cx) / fx, (yy - cy) / fy, np.ones_like(xx)], -1).reshape(-1, 3)
proj = {rid: np.zeros(len(V.names), np.int64) for rid in ranges}
native = {rid: np.zeros(len(V.names), np.int64) for rid in ranges}
for i, n in enumerate(V.names):
    R, t = V.R(n), V.t(n)
    for rid, P in refs.items():
        Xc = P @ R.T + t; z = Xc[:, 2]; pos = z > 1e-6
        u = np.floor(fx * Xc[:, 0] / np.where(pos, z, 1) + cx + 0.5); v = np.floor(fy * Xc[:, 1] / np.where(pos, z, 1) + cy + 0.5)
        proj[rid][i] = int((pos & (u >= 0) & (u < GRID_W) & (v >= 0) & (v < GRID_H)).sum())
    d = read_depth_bin(DENSE / "stereo/depth_maps" / f"{n}.geometric.bin").ravel()
    nv = np.isfinite(d) & (d > 0)
    X = ((nrays[nv] * d[nv, None]) - t) @ R
    zok = (X[:, 2] >= zb[0]) & (X[:, 2] < zb[1])
    for rid, r in ranges.items():
        native[rid][i] = int((zok & inside_range(X[:, :2], r)).sum())
    if i % 200 == 0:
        log("views", i)
tilts = {n: V.tilt(n) for n in V.names}
views = {}
for rid in ranges:
    nref = len(refs[rid]); minimum = max(10, int(np.ceil(0.01 * nref)))
    cand = [n for i, n in enumerate(V.names) if proj[rid][i] >= minimum or native[rid][i] >= 100]
    ev = [n for k, n in enumerate(cand) if k % 8 == 0]; tr = [n for k, n in enumerate(cand) if k % 8 != 0]
    cnt = lambda L: dict(total=len(L), nadir=int(sum(tilts[x] <= 20 for x in L)), oblique=int(sum(tilts[x] > 20 for x in L)))
    views[rid] = dict(candidates=cand, train=tr, evaluation=ev, reference_points=nref, counts=dict(train=cnt(tr), evaluation=cnt(ev)))
jdump(D / "box_views.json", dict(views=views))
log("box views", {k: (v["counts"]["train"]["total"], v["counts"]["evaluation"]["total"]) for k, v in views.items()})
