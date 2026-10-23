"""PHD-MAIN-UNCERT-v1 일 1: the MVS points of one site and one version (order 1.2-6), not fused: every valid pixel of every training view's
MVS depth map becomes one 3-D point; the view of each point is kept. Run in jointbuildgs:geogs-conf-guided-v1 (IMG=...; the fork's
colmap_loader through the AXES71 module).

  python u1_mvs_points.py <site> <a|b>   -> /out/points/<site>/mvs_<a|b>_{xyz,view,key}.npy (sorted by key), mvs_<a|b>.json

Cameras and depth = scripts/phd/main_axes71_v2/mvs_surface.py cameras(site) and depth_source(site, a|b) called as they are (the same
functions that built the AXES71 MVS surfaces; their CPU TSDF matched the GPU-run fusion). Unprojection = mvs_surface.box_mask's formula
in float64: camera point ((u - cx) / fx * d, (v - cy) / fy * d, d) (d = depth along the optical axis), world = inv(W2C) * camera point.
Kept: inside the experiment region widened by 3 m (uc_common.crop_rect). Keys: default_rng([seed, site id, version id]).random(N) in the
order (view, row, column); the arrays are stored sorted by key so that 'key < p' is a prefix (the exact thinning of order 1.2-4).
scientific_verdict: null."""
import sys

import numpy as np

sys.path.insert(0, "/repo/scripts/phd/main_uncert_v1")
sys.path.insert(0, "/repo/scripts/phd/main_axes71_v2")
import uc_common as U  # noqa: E402
import mvs_surface as MS  # noqa: E402


def main(site, var):
    T = U.Timer()
    cams, camrec = MS.cameras(site)
    depth_of, st, mdir, cdir = MS.depth_source(site, var)
    rect = U.crop_rect(site)
    xs, vs = [], []
    per_view = []
    for i, c in enumerate(cams):
        d = depth_of(c)
        if d is None:
            per_view.append(dict(view=c["name"], depth=False))
            continue
        vv, uu = np.nonzero(d > 0)
        dd = d[vv, uu].astype(np.float64)
        x = (uu - np.float64(c["cx"])) / np.float64(c["fx"]) * dd
        y = (vv - np.float64(c["cy"])) / np.float64(c["fy"]) * dd
        C2W = np.linalg.inv(np.asarray(c["W2C"], np.float64))
        P = np.stack([x, y, dd], 1) @ C2W[:3, :3].T + C2W[:3, 3]
        keep = U.in_rect_uv(P, rect)
        xs.append(P[keep].astype(np.float32))
        vs.append(np.full(int(keep.sum()), i, np.int16))
        per_view.append(dict(view=c["name"], depth=True, px_valid=int(len(dd)), kept=int(keep.sum())))
        if (i + 1) % 50 == 0:
            U.log(site, var, i + 1, "/", len(cams), "points", sum(len(a) for a in xs), "peak", U.peak_gb())
    X = np.concatenate(xs)
    V = np.concatenate(vs)
    del xs, vs
    key = np.random.default_rng([U.CFG["seed"], U.SITE_ID[site], {"a": 0, "b": 1}[var]]).random(len(X))
    o = np.argsort(key, kind="stable")
    X, V, key = X[o], V[o], key[o].astype(np.float64)
    O = U.PTS / site
    O.mkdir(parents=True, exist_ok=True)
    np.save(O / f"mvs_{var}_xyz.npy", X)
    np.save(O / f"mvs_{var}_view.npy", V)
    np.save(O / f"mvs_{var}_key.npy", key)
    levels = {k: int(np.searchsorted(key, 4.0 ** -k)) for k in range(7)}
    U.jdump(O / f"mvs_{var}.json", dict(
        site=site, version=var, rule=__doc__, made=U.now(), env=U.env(), n_points=int(len(X)), views=len(cams),
        views_with_depth=int(sum(p["depth"] for p in per_view)), depth_dir=str(mdir), conf_dir=str(cdir), depth_checks=st,
        cameras=camrec, crop_rect_uv=rect, z_range=[float(X[:, 2].min()), float(X[:, 2].max())],
        level_prefix_counts={str(k): v for k, v in levels.items()}, per_view=per_view, seconds=T.mark("all"), peak_gb=U.peak_gb(),
        camera_names=[c["name"] for c in cams], scientific_verdict=None))
    U.log(site, var, "done", len(X), "points", T.mark("all"), "s, peak", U.peak_gb())


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
