"""PHD-MAIN-VISCMP-v3 the new distance metric's d_g for the figures (request 2.2), with the distance task's own code (dm_common,
d2_dist.oriented_sign): d_g = distance from a GT point to the nearest triangle of a mesh, + where the nearest mesh point lies outside the GT
surface (the GT normal turned toward the outward normal of the point's patch; points without a patch use the nearest patch, as d3_metrics).
  scene points ('전체'): SiteGT.Gb (the drone-LiDAR points of the building-surface cells) -> the lower-row colours
  region rows ('곳'): Unit.r_P (the thinned rows) -> the panel numbers (median |d_g|, the 7.1 table's quantity)
Stored results: the distance files (s_d, s_sign, s_sign_near; r_d, r_sign). New meshes (the image-depth mesh): computed here on the
crop's subset [이 발주에서 냄]. Also: the 'no surface nearby' test (rays along +-normal within 2 x the colour range) and the depth-map mesh.
scientific_verdict: null"""
import numpy as np
from scipy.spatial import cKDTree

import vc_common  # noqa: F401  (paths)
from vc_common import dist_file

from dm_common import WORK as DMWORK, SiteGT, Unit, closest, owner_of_scene_points  # noqa: E402
from d2_dist import oriented_sign  # noqa: E402
from src.phd.metrics_v3.surface import MeshScene  # noqa: E402


class Case:
    def __init__(self, site, prior):
        self.site, self.prior = site, prior
        self.gt = SiteGT(site)
        self.u = Unit(site, prior, self.gt)
        Z = np.load(DMWORK / f"normals_{site}.npz")
        self.Nfull = {}
        for s, X in self.gt.X.items():
            a = np.full((len(X), 3), np.nan, np.float32)
            a[Z[f"use_{s}"]] = Z[f"normal_{s}"]
            self.Nfull[s] = a
        self.n_scene = self.Nfull[0][self.gt.bs_idx]
        self.own = owner_of_scene_points(site, prior, self.gt)
        self.near = cKDTree(self.u.centre).query(self.gt.Gb, workers=-1)[1].astype(np.int64)
        u = self.u
        self.n_rows = np.full((len(u.r_P), 3), np.nan, np.float32)
        for s_ in np.unique(u.r_src):
            m = u.r_src == s_
            self.n_rows[m] = self.Nfull[int(s_)][u.r_pt[m]]

    # --- selections
    def scene_in_box(self, box, margin=0.0):
        G = self.gt.Gb
        return np.nonzero((G[:, 0] >= box[0] - margin) & (G[:, 0] <= box[2] + margin) & (G[:, 1] >= box[1] - margin) & (G[:, 1] <= box[3] + margin))[0]

    def rows_of(self, patches):
        return np.nonzero(np.isin(self.u.r_pa, np.asarray(patches, np.int64)))[0]

    # --- stored values
    def stored(self, res):
        f = dist_file(self.site, self.prior, res)
        if f is None:
            return None
        d = np.load(f)
        s = np.where(d["s_sign"] != 0, d["s_sign"], d["s_sign_near"]).astype(np.float64)
        rs = np.where(d["r_sign"] != 0, d["r_sign"], 1).astype(np.float64)
        return dict(file=str(f), scene=d["s_d"].astype(np.float64) * s, rows=d["r_d"].astype(np.float64) * rs, r_place=d["r_place"], r_patch=d["r_patch"],
                    s_patch=d["s_patch"], rows_sign_undefined=int((d["r_sign"] == 0).sum()))

    # --- new meshes
    def oriented_normals(self, idx):
        n = self.n_scene[idx].astype(np.float64)
        o = self.own[idx]
        npat = np.where((o >= 0)[:, None], self.u.n_p[np.maximum(o, 0)], self.u.n_p[self.near[idx]])
        flip = np.where((n * npat).sum(1) < 0, -1.0, 1.0)
        return n * flip[:, None]

    def dg_scene(self, V, F, idx):
        P = self.gt.Gb[idx]
        sc = MeshScene(V, F)
        d = sc.distance(P).astype(np.float64)
        q, _ = closest(sc, P)
        o = self.own[idx]
        n_pat = np.full((len(idx), 3), np.nan)
        n_pat[o >= 0] = self.u.n_p[o[o >= 0]]
        s = oriented_sign(P, q, d, self.n_scene[idx], n_pat)
        s_near = oriented_sign(P, q, d, self.n_scene[idx], self.u.n_p[self.near[idx]])
        return d * np.where(s != 0, s, s_near)

    def dg_rows(self, V, F, ridx):
        P = self.u.r_P[ridx]
        sc = MeshScene(V, F)
        d = sc.distance(P).astype(np.float64)
        q, _ = closest(sc, P)
        s = oriented_sign(P, q, d, self.n_rows[ridx], self.u.r_n[ridx])
        return d * np.where(s != 0, s, 1)


def no_surface(V, F, P, N, lim):
    """True where rays from P along +N and -N meet no triangle within lim (the 'no surface nearby' grey); points without a normal: the
    caller's |d_g| > lim test is used instead (returned as None in that slot)."""
    import open3d as o3d
    ok = np.isfinite(N).all(1)
    out = np.zeros(len(P), bool)
    if len(F) == 0:
        out[:] = True
        return out, ok
    sc = o3d.t.geometry.RaycastingScene()
    sc.add_triangles(o3d.core.Tensor(np.asarray(V, np.float32)), o3d.core.Tensor(np.asarray(F, np.uint32)))
    hit = np.zeros(len(P), bool)
    for sgn in (1.0, -1.0):
        rays = np.concatenate([P[ok], sgn * N[ok]], 1).astype(np.float32)
        t = sc.cast_rays(o3d.core.Tensor(rays))["t_hit"].numpy()
        hit[np.nonzero(ok)[0]] |= t <= lim
    out[ok] = ~hit[ok]
    return out, ok


def depth_mesh(view, depth, jump_rel=0.01, jump_min=0.3):
    """the 1024 x 741 depth map as a mesh on its pixel grid: two triangles per pixel square whose three corners have depth and differ by
    at most max(jump_min, jump_rel x depth) (no bridge over depth jumps). Returns V, F and the rule."""
    import pf_geo as G
    H, W = depth.shape
    ok = np.isfinite(depth) & (depth > 0)
    X, iy, ix = G.backproject(view, depth, ok)
    vid = np.full((H, W), -1, np.int64)
    vid[iy, ix] = np.arange(len(X))
    a, b, c_, d_ = vid[:-1, :-1], vid[:-1, 1:], vid[1:, :-1], vid[1:, 1:]
    za, zb, zc, zd = depth[:-1, :-1], depth[:-1, 1:], depth[1:, :-1], depth[1:, 1:]
    lim = np.maximum(jump_min, jump_rel * np.nan_to_num(za, nan=0.0))
    F = []
    for (p, q, r), (zp, zq, zr) in (((a, c_, b), (za, zc, zb)), ((b, c_, d_), (zb, zc, zd))):
        m = (p >= 0) & (q >= 0) & (r >= 0)
        zz = np.stack([zp, zq, zr], -1)
        m &= (np.nanmax(zz, -1) - np.nanmin(zz, -1)) <= lim
        F.append(np.stack([p[m], q[m], r[m]], 1))
    F = np.concatenate(F)
    return X, F, dict(rule=f"pixel-grid mesh, no triangle over a depth jump > max({jump_min} m, {jump_rel:.0%} of depth)", pixels_with_depth=int(ok.sum()),
                      pixels=int(H * W), masked_share=float(1 - ok.mean()), vertices=int(len(X)), triangles=int(len(F)))
