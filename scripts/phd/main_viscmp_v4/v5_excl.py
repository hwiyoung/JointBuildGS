"""PHD-MAIN-VISCMP-v4 V5 (request 6.3 V5): what the GT-excluded cells near the piece are — per class of the exclusion cells
(S1/v3/box_gt/<site>/exclusion_cells.npz: trees, transient, prior_side_trees; 'any' = the cells whose GT points gt_classes.npz marks
excl_gt_points) the cells in the V5 render box (the piece's plan box + 2 m), and the excluded GT points of the box drawn on the photo crop
(training image 0146) so the report can say what they look like.
  python v5_excl.py   -> /docs/tables/V5_excluded_cells.json, /vc/work/v5_excl_photo.png   scientific_verdict: null"""
import numpy as np
from PIL import Image, ImageDraw

import vc_common  # noqa: F401
import p0_places as P0
import vc_fig as VF
import vc_render as RD
from a3_split import excl_lookup
from vc_common import CFG, DOCS, S1, VC, jdump, jl, log, now

KO = {"trees": "나무", "transient": "일시 물체", "prior_side_trees": "사전 정보 쪽 나무(항공 LiDAR)", "any": "모두(참값에서 뺀 칸)"}


def main():
    P = jl(CFG.parent / "places_v4.json")["V5"]; site, prior = P["site"], P["prior"]
    U = P0.store(site, prior); place = np.asarray(P["place"], int)
    xy = U["loc_center"][place][:, :2]; m = float(P["camera"]["margin_m"])
    box = [float(xy[:, 0].min() - m), float(xy[:, 1].min() - m), float(xy[:, 0].max() + m), float(xy[:, 1].max() + m)]
    f, e = excl_lookup(site)
    gx = np.arange(box[0], box[2], 0.25) + 0.125; gy = np.arange(box[1], box[3], 0.25) + 0.125
    GX, GY = np.meshgrid(gx, gy); Q = np.column_stack([GX.ravel(), GY.ravel(), np.zeros(GX.size)])
    out = {}
    for k in ("trees", "transient", "prior_side_trees", "any"):
        hit = f(Q, key=k)
        ix = np.floor((Q[hit, 0] + 690953.0 - 690700.0) / 0.5).astype(int); iy = np.floor((Q[hit, 1] + 5336071.0 - 5335820.0) / 0.5).astype(int)
        n = len(set(zip(ix.tolist(), iy.tolist())))
        out[k] = dict(name=KO[k], cells=n, area_m2=0.25 * n)
    G = np.load(S1 / "defs" / site / "gt_classes.npz")
    X = G["xyz_gt_points"].astype(np.float64); ex = G["excl_gt_points"]
    inb = ex & (X[:, 0] >= box[0]) & (X[:, 0] <= box[2]) & (X[:, 1] >= box[1]) & (X[:, 1] <= box[3])
    Xe = X[inb]
    cls = {k: f(Xe, key=k) for k in ("trees", "transient", "prior_side_trees")}
    pv = P["photo"]; pc = RD.Pinhole(pv, (0, 0, 1400, 1013), 1)
    u, v, z = pc.project(Xe)
    ph = Image.fromarray(VF.photo(pv, [0, 0, 1400, 1013])).convert("RGB")
    dr = ImageDraw.Draw(ph)
    col = {"trees": (0, 200, 0), "transient": (255, 0, 255), "prior_side_trees": (0, 160, 255)}
    for k, msk in cls.items():
        for a, b in zip(u[msk], v[msk]):
            dr.point((float(a), float(b)), fill=col[k])
    qo = VF.outline(pc, VF.quads(U, place), close_px=4)
    yy, xx = np.nonzero(qo)
    x0, y0, x1, y1 = max(xx.min() - 120, 0), max(yy.min() - 90, 0), min(xx.max() + 120, 1400), min(yy.max() + 90, 1013)
    crop = ph.crop((int(x0), int(y0), int(x1), int(y1)))
    crop = crop.resize((crop.width * 4, crop.height * 4), Image.NEAREST)
    dc = ImageDraw.Draw(crop)
    for a, b in zip(xx[::7], yy[::7]):
        dc.point(((a - x0) * 4, (b - y0) * 4), fill=(255, 215, 0))
    crop.save(VC / "work" / "v5_excl_photo.png")
    pts = {k: int(v_.sum()) for k, v_ in cls.items()}
    rec = dict(task="PHD-MAIN-VISCMP-v4", work="일 가 V5", made=now(), box_xy=box, cells_in_box=out, excluded_gt_points_in_box=int(len(Xe)), points_by_class=pts,
               point_height_m=dict(min=float(Xe[:, 2].min()) if len(Xe) else None, median=float(np.median(Xe[:, 2])) if len(Xe) else None, max=float(Xe[:, 2].max()) if len(Xe) else None),
               place_height_m=float(np.median(U["loc_center"][place][:, 2])), photo=pv, photo_crop=[int(x0), int(y0), int(x1), int(y1)],
               rule="cells: exclusion_cells.npz on the 0.5 m survey grid; points: gt_classes.npz excl_gt_points in the box, projected into the photo (green trees, magenta transient, blue prior-side trees)",
               scientific_verdict=None)
    jdump(DOCS / "tables/V5_excluded_cells.json", rec)
    log(rec["cells_in_box"], pts, rec["point_height_m"], rec["place_height_m"])


if __name__ == "__main__":
    main()
