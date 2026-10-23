"""PHD-MAIN-UNCERT-v1 일 1: the original ALS points (order 1.2-7) and the GT points (1.5) of one site, inside the experiment region widened
by 3 m (jointbuildgs:dev).

  python u1_other_points.py <site> [...] -> /out/points/<site>/als_{xyz,cls,multi}.npy, als.json; gt_{xyz,src}.npy, gt.json

ALS = the four P0 raw LAZ tiles read as scripts/phd/main_prep_discard_rule_v1/common.read_als (points inside each tile's nominal 1 km,
local XY = (E, N) - world shift, z = H + 45.7 - world shift z), classes 2 and 6 only (the classes of the prior TIN, s02_meshes.als_mesh),
plus the site's ALS registration shift (S0/s61/box/<site>/ALS/summary.json registration.shift_applied, = the region file frame_shift),
NOT de-duplicated (the TIN dropped XY duplicates at 1 mm; the original points are used here). GT = gt_classes.npz xyz_gt_points without
excl_gt_points (trees, temporary objects), for B0 also xyz_gt_primary without excl_gt_primary (src 1). scientific_verdict: null."""
import json
import sys

import numpy as np

sys.path.insert(0, "/repo/scripts/phd/main_uncert_v1")
import uc_common as U  # noqa: E402

TILES = ("690_5335", "690_5336", "691_5335", "691_5336")


def als_all(sites):
    """read each tile once and crop it for every site."""
    import laspy
    acc = {}
    for site in sites:
        sh = np.asarray(json.loads((U.S0 / "s61/box" / site / "ALS/summary.json").read_text())["registration"]["shift_applied"], np.float64)
        fs = np.load(U.S1 / "regions_v3" / f"regions_ext_v3_{site}_ALS.npz")["frame_shift"]
        acc[site] = dict(sh=sh, fs=fs, rect=U.crop_rect(site), xs=[], cs=[], ms=[], rec=[])
    for t in TILES:
        p = U.ART / "phase-payloads/p0-audit/data/raw/als" / f"{t}.laz"
        las = laspy.read(str(p))
        E, N, Z = np.asarray(las.x), np.asarray(las.y), np.asarray(las.z)
        cls = np.asarray(las.classification)
        nr = np.asarray(las.number_of_returns)
        del las
        te0, tn0 = float(t.split("_")[0]) * 1000, float(t.split("_")[1]) * 1000
        nominal = (E >= te0) & (E < te0 + 1000) & (N >= tn0) & (N < tn0 + 1000)
        P0 = np.stack([E - U.SHIFT[0], N - U.SHIFT[1], Z + U.ZB - U.SHIFT[2]], 1)
        for site, a in acc.items():
            P = P0 + a["sh"]
            m = nominal & U.in_rect_uv(P, a["rect"])
            a["rec"].append(dict(tile=t, points=int(len(E)), in_crop_all_classes=int(m.sum()),
                                 in_crop_by_class={int(k): int(v) for k, v in zip(*np.unique(cls[m], return_counts=True))}))
            m &= np.isin(cls, (2, 6))
            a["xs"].append(P[m]); a["cs"].append(cls[m].astype(np.uint8)); a["ms"].append(nr[m] > 1)
        U.log("tile", t, len(E))
    out = {}
    for site, a in acc.items():
        out[site] = (np.concatenate(a["xs"]), np.concatenate(a["cs"]), np.concatenate(a["ms"]),
                     dict(shift_applied=a["sh"], region_frame_shift=a["fs"], shift_equal=bool(np.allclose(a["sh"], a["fs"])), tiles=a["rec"]))
    return out


def main(site, A):
    T = U.Timer()
    rect = U.crop_rect(site)
    O = U.PTS / site
    O.mkdir(parents=True, exist_ok=True)
    X, cls, multi, info = A[site]
    np.save(O / "als_xyz.npy", X.astype(np.float64))
    np.save(O / "als_cls.npy", cls)
    np.save(O / "als_multi.npy", multi)
    U.jdump(O / "als.json", dict(site=site, rule=__doc__, made=U.now(), env=U.env(), n_points=int(len(X)),
                                 by_class={int(k): int(v) for k, v in zip(*np.unique(cls, return_counts=True))}, multi_return=int(multi.sum()),
                                 crop_rect_uv=rect, **info, seconds=T.mark("als"), scientific_verdict=None))
    U.log(site, "ALS", len(X))
    G = np.load(U.S1 / "defs" / site / "gt_classes.npz")
    parts, src, rec = [], [], {}
    for s, (kx, ke) in enumerate((("xyz_gt_points", "excl_gt_points"), ("xyz_gt_primary", "excl_gt_primary"))):
        if kx not in G.files:
            continue
        P = G[kx].astype(np.float64)
        ex = G[ke].astype(bool)
        m = ~ex & U.in_rect_uv(P, rect)
        rec[kx] = dict(points=int(len(P)), excluded=int(ex.sum()), kept_in_crop=int(m.sum()))
        parts.append(P[m]); src.append(np.full(int(m.sum()), s, np.int8))
    GX = np.concatenate(parts)
    np.save(O / "gt_xyz.npy", GX)
    np.save(O / "gt_src.npy", np.concatenate(src))
    U.jdump(O / "gt.json", dict(site=site, rule=__doc__, made=U.now(), n_points=int(len(GX)), sources=rec, crop_rect_uv=rect,
                                seconds=T.mark("gt"), scientific_verdict=None))
    U.log(site, "GT", len(GX), T.marks)


if __name__ == "__main__":
    A = als_all(sys.argv[1:])
    for s in sys.argv[1:]:
        main(s, A)
