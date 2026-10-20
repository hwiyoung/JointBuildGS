"""PHD-MAIN-PHOTOFIG-v1 [사용자 요청, 그리는 법 견본] the view of the R1 wall-19 sample figure, chosen from geometry only (no result file is
opened): the training views that hold all missing patches of wall 19 (evaluation range, code 4 or 13) inside the image with >= 80 % of them
visible against the prior render depth (the figure-3 rule, p0_places.score_views), and among them the largest image footprint (hull of the
patch centres, px^2 on the 1024 x 741 grid). Figure 3 used the smallest view angle instead (view 0011, 636 px^2).
  python p4_proto.py -> /pf/prep/places_proto.json   scientific_verdict: null"""
import numpy as np

import p0_places as P0
from pf_common import PF, jdump, now

SITE, PRIOR, EXT = "R1rep_b10", "LoD2", 19


def main():
    R = P0.region(SITE, PRIOR); U = P0.store(SITE, PRIOR)
    se = R["surf_ext"].astype(int); ev = R["in_eval"].astype(bool); code = R["code_ext_v3"].astype(int)
    mp = np.nonzero(ev & (se == EXT) & np.isin(code, [4, 13]))[0]
    n, _ = P0.wall_normal(SITE, EXT)
    n, _ = P0.oriented_out(SITE, EXT, n, R["centre"][mp].astype(np.float64).mean(0))
    P = P0.patch_corners(U, mp)
    V = P0.views(); rows = []
    for v in P0.train_views(SITE):
        k = P0.vname(v)
        if k is None:
            continue
        best, _ = None, None
        u, w, z = V.project(k, P)
        inside = (z > 0) & (u >= 0) & (u < 1024) & (w >= 0) & (w < 741)
        if inside.mean() < 1.0:
            continue
        D = np.load(P0.S0 / "s61/export" / SITE / PRIOR / "prior" / f"{v}.npy")
        d = D[np.clip(np.floor(w).astype(int), 0, 740), np.clip(np.floor(u).astype(int), 0, 1023)]
        vis = float((np.isfinite(d) & (np.abs(z - d) <= 0.5)).mean())
        if vis < P0.VIS_MIN:
            continue
        from scipy.spatial import ConvexHull
        C = V.C(k); dirc = C - P.mean(0); dirc /= np.linalg.norm(dirc)
        rows.append(dict(view=v, visible=vis, hull_px2=float(ConvexHull(np.column_stack([u, w])).volume), tilt_deg=round(V.tilt(k), 2),
                         view_angle_deg=round(float(np.degrees(np.arccos(np.clip(dirc @ n, -1, 1)))), 2), distance_m=round(float(np.linalg.norm(C - P.mean(0))), 1)))
    rows.sort(key=lambda r: -r["hull_px2"])
    rec = dict(site=SITE, prior=PRIOR, ext=EXT, missing=int(len(mp)), outward_normal=n.tolist(), view=rows[0]["view"], candidates=rows,
               rule=__doc__.split("\n\n")[0], made=now(), scientific_verdict=None)
    jdump(PF / "prep/places_proto.json", rec)
    for r in rows[:6]:
        print(r)
    print("n", len(rows))


if __name__ == "__main__":
    main()
