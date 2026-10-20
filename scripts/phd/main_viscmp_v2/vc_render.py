"""PHD-MAIN-VISCMP-v2 renderer (request 1.4, 1.5): one camera per figure, the TSDF meshes ray-cast on the CPU (Open3D RaycastingScene),
one grey with one light from the view (headlight: brightness = 0.12 + 0.78 |n . d|), misses = white; GT points = dark grey dots with a
z-buffer among themselves; outside the place = 30 % opacity over white (the same mask rule in every panel).
Cameras: Pinhole = a training camera (the 1400 x 1013 COLMAP model) with the focal length scaled by `scale` over a crop; Ortho = a parallel
view along -n over a plane rectangle. scientific_verdict: null"""
import numpy as np

import pf_geo as G

GREY_LO, GREY_HI = 0.12, 0.78
PT_GREY = 0.25


class Pinhole:
    def __init__(self, view, box_native, scale):
        V = G.views(); self.k = G.vkey(view); self.view = view
        self.fx, self.fy, self.cx, self.cy = (float(x) for x in V.K0)
        self.R = V.R(self.k); self.t = V.t(self.k); self.C = V.C(self.k)
        self.u0, self.v0, u1, v1 = box_native; self.s = scale
        self.W, self.H = int(round((u1 - self.u0) * scale)), int(round((v1 - self.v0) * scale))

    def rays(self):
        uu = self.u0 + (np.arange(self.W) + 0.5) / self.s; vv = self.v0 + (np.arange(self.H) + 0.5) / self.s
        dc = np.stack(np.broadcast_arrays((uu[None, :] - self.cx) / self.fx, (vv[:, None] - self.cy) / self.fy, np.ones((self.H, self.W))), -1)
        dc = dc / np.linalg.norm(dc, axis=-1, keepdims=True)
        d = dc @ self.R
        return np.broadcast_to(self.C, d.shape), d

    def project(self, X):
        Xc = np.asarray(X, np.float64) @ self.R.T + self.t
        z = Xc[:, 2]
        with np.errstate(divide="ignore", invalid="ignore"):
            u = (self.fx * Xc[:, 0] / z + self.cx - self.u0) * self.s; v = (self.fy * Xc[:, 1] / z + self.cy - self.v0) * self.s
        return u, v, z

    def record(self):
        return dict(kind="pinhole (training camera, COLMAP 1400 x 1013 model)", view=self.view, K_native=[self.fx, self.fy, self.cx, self.cy],
                    R=self.R.tolist(), t=self.t.tolist(), centre=self.C.tolist(), crop_native=[self.u0, self.v0, self.u0 + self.W / self.s, self.v0 + self.H / self.s],
                    scale=self.s, size=[self.W, self.H])


class Ortho:
    def __init__(self, centre, right, up, toward_viewer, s_range, h_range, pixel, distance=30.0):
        self.c = np.asarray(centre, np.float64); self.r = np.asarray(right, np.float64); self.u = np.asarray(up, np.float64)
        self.n = np.asarray(toward_viewer, np.float64); self.sr, self.hr, self.px, self.D = s_range, h_range, pixel, distance
        self.W = int(np.ceil((s_range[1] - s_range[0]) / pixel)); self.H = int(np.ceil((h_range[1] - h_range[0]) / pixel))

    def rays(self):
        ss = self.sr[0] + (np.arange(self.W) + 0.5) * self.px; hh = self.hr[1] - (np.arange(self.H) + 0.5) * self.px
        O = self.c + self.D * self.n + ss[None, :, None] * self.r + hh[:, None, None] * self.u
        return O, np.broadcast_to(-self.n, O.shape)

    def project(self, X):
        d = np.asarray(X, np.float64) - self.c
        return (d @ self.r - self.sr[0]) / self.px, (self.hr[1] - d @ self.u) / self.px, self.D - d @ self.n

    def record(self):
        return dict(kind="orthographic (parallel rays along -n)", centre=self.c.tolist(), right=self.r.tolist(), up=self.u.tolist(), toward_viewer=self.n.tolist(),
                    s_range=list(self.sr), h_range=list(self.hr), pixel_m=self.px, size=[self.W, self.H])


def load_mesh(path, xy_box, margin=2.0, keep=None):
    V, F, info = G.read_ply_mesh_box(path, xy_box, margin=margin)
    if keep is not None and len(F):
        kv = keep(V)
        F = F[kv[F].all(1)]
        info = dict(info, kept_faces_after_place_cut=int(len(F)))
    return V, F, info


def raycast(V, F, cam):
    import open3d as o3d
    O, D = cam.rays()
    H, W = D.shape[:2]
    if len(F) == 0:
        return np.full((H, W), np.inf), np.zeros((H, W, 3)), D
    sc = o3d.t.geometry.RaycastingScene()
    sc.add_triangles(o3d.core.Tensor(np.asarray(V, np.float32)), o3d.core.Tensor(np.asarray(F, np.uint32)))
    rays = np.concatenate([O, D], -1).reshape(-1, 6).astype(np.float32)
    out = sc.cast_rays(o3d.core.Tensor(rays))
    t = out["t_hit"].numpy().reshape(H, W).astype(np.float64)
    n = out["primitive_normals"].numpy().reshape(H, W, 3).astype(np.float64)
    return t, n, D


def shade(t, n, D):
    hit = np.isfinite(t)
    g = np.ones(t.shape)
    g[hit] = GREY_LO + GREY_HI * np.abs((n * D).sum(-1))[hit]
    return g, hit


def down(img, f):
    """block mean of an f x f supersampled image (anti-aliasing of the mesh speckle)."""
    if f == 1:
        return img
    H, W = (img.shape[0] // f) * f, (img.shape[1] // f) * f
    return img[:H, :W].reshape(H // f, f, W // f, f).mean((1, 3))


def hit_points(t, cam):
    O, D = cam.rays()
    tt = np.where(np.isfinite(t), t, 0.0)
    return O + tt[..., None] * D


def fade(g, hit, inside):
    """outside the place: 30 % opacity over white."""
    out = g.copy()
    m = hit & ~inside
    out[m] = 1.0 - 0.3 * (1.0 - g[m])
    return out


def splat(cam, X, radius=1):
    """GT points as dark grey dots: nearest point per pixel (z-buffer among the points), drawn with a (2r+1) square."""
    u, v, z = cam.project(X)
    ok = (z > 0) & (u >= 0) & (u < cam.W) & (v >= 0) & (v < cam.H)
    iu, iv, zz = np.floor(u[ok]).astype(int), np.floor(v[ok]).astype(int), z[ok]
    zb = np.full((cam.H, cam.W), np.inf)
    np.minimum.at(zb, (iv, iu), zz)
    keep = zz <= zb[iv, iu] + 0.25
    img = np.ones((cam.H, cam.W))
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            a, b = np.clip(iv[keep] + dy, 0, cam.H - 1), np.clip(iu[keep] + dx, 0, cam.W - 1)
            img[a, b] = PT_GREY
    return img, int(ok.sum())
