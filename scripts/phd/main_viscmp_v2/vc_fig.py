"""PHD-MAIN-VISCMP-v2 shared pieces of the training-camera figures (V1, V4): the crop from the place's patch squares, the place outline,
one panel = one TSDF mesh ray-cast from the camera (2 x 2 supersampled), faded to 30 % outside the place (plan squares of the place
patches for a roof, the wall slab for a wall), the GT panel, the photo panel. scientific_verdict: null"""
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

import pf_geo as G
import vc_render as RD
from vc_common import DENSE_IMG

SS = 2


def quads(U, idx):
    h = 0.5 * float(U["sp"])
    c, t1, t2 = U["loc_center"][idx].astype(np.float64), U["loc_t1"][idx].astype(np.float64), U["loc_t2"][idx].astype(np.float64)
    return np.stack([c - h * t1 - h * t2, c + h * t1 - h * t2, c + h * t1 + h * t2, c - h * t1 + h * t2], 1)


def crop_box(view, Q, margin=0.15, margin_v=None):
    pc = RD.Pinhole(view, (0, 0, 1400, 1013), 1)
    u, v, _ = pc.project(Q.reshape(-1, 3))
    du, dv = u.max() - u.min(), v.max() - v.min()
    mv = margin if margin_v is None else margin_v
    return [int(max(np.floor(u.min() - margin * du), 0)), int(max(np.floor(v.min() - mv * dv), 0)),
            int(min(np.ceil(u.max() + margin * du), 1400)), int(min(np.ceil(v.max() + mv * dv), 1013))]


def outline(cam, Q, close_px=None):
    """the place's footprint in the image: the projected patch squares, closed and filled into one piece."""
    m = Image.new("L", (cam.W, cam.H), 0); dr = ImageDraw.Draw(m)
    for q in Q:
        u, v, _ = cam.project(q)
        dr.polygon(list(zip(u, v)), fill=1)
    m = np.asarray(m).astype(bool)
    qpx = float(np.sqrt(max(m.sum(), 1) / max(len(Q), 1)))
    rr = close_px if close_px is not None else max(int(round(1.5 * qpx)), 1)
    yy, xx = np.mgrid[-rr:rr + 1, -rr:rr + 1]
    return ndimage.binary_fill_holes(ndimage.binary_closing(m, structure=(xx ** 2 + yy ** 2) <= rr * rr))


def render(path, box_xy, cam_hi, inside_fn, margin=10.0):
    """one mesh panel: grey headlight shading, faded outside the place; returns the panel image (down-sampled) and a record."""
    V, F, info = RD.load_mesh(path, box_xy, margin=margin)
    t, n, D = RD.raycast(V, F, cam_hi)
    g, hit = RD.shade(t, n, D)
    X = RD.hit_points(t, cam_hi)
    inside = inside_fn(X.reshape(-1, 3)).reshape(hit.shape)
    g = RD.fade(g, hit, inside)
    return RD.down(g, SS), dict(mesh=str(path), mesh_info=info, hit_share=float(hit.mean()), hit_in_place=float((hit & inside).sum() / max(inside.sum(), 1)))


def render_gt(Xg, cam_hi, inside_fn, radius=1):
    img, n = RD.splat(cam_hi, Xg, radius=radius)
    u, v, z = cam_hi.project(Xg)
    ok = (z > 0) & (u >= 0) & (u < cam_hi.W) & (v >= 0) & (v < cam_hi.H)
    ins = inside_fn(Xg)
    # outside the place: the same 30 % opacity (redraw those dots lighter)
    lt = 1.0 - 0.3 * (1.0 - RD.PT_GREY)
    iu, iv = np.floor(u[ok & ~ins]).astype(int), np.floor(v[ok & ~ins]).astype(int)
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            a, b = np.clip(iv + dy, 0, cam_hi.H - 1), np.clip(iu + dx, 0, cam_hi.W - 1)
            img[a, b] = np.maximum(img[a, b], lt)
    return RD.down(img, SS), dict(points_in_view=int(ok.sum()), points_in_place=int((ok & ins).sum()))


def photo(view, box_native):
    pc = RD.Pinhole(view, (0, 0, 1400, 1013), 1)
    im = np.asarray(Image.open(DENSE_IMG / f"{pc.k if pc.k.endswith('.JPG') else pc.k + '.JPG'}").convert("RGB"))
    x0, y0, x1, y1 = box_native
    return im[y0:y1, x0:x1]


def gt(site, box_xy, margin=2.0):
    X, _, _ = G.gt_points(site, box_xy, margin=margin)
    return X


def plan_inside(Q, pad=0.25, res=0.05):
    """inside test in plan: the place's patch squares (each grown by pad) rasterised on a res grid; returns f(X [N, 3]) -> bool [N]."""
    xy = Q[..., :2].reshape(-1, 2)
    x0, y0 = xy.min(0) - pad - res; x1, y1 = xy.max(0) + pad + res
    W, H = int(np.ceil((x1 - x0) / res)), int(np.ceil((y1 - y0) / res))
    m = Image.new("L", (W, H), 0); dr = ImageDraw.Draw(m)
    for q in Q:
        c = q[:, :2].mean(0); qq = c + (q[:, :2] - c) * (1 + 2 * pad / max(np.linalg.norm(q[0, :2] - q[2, :2]) / np.sqrt(2), 1e-6))
        dr.polygon([((a - x0) / res, (b - y0) / res) for a, b in qq], fill=1)
    M = np.asarray(m).astype(bool)

    def f(X):
        i = np.floor((X[:, 0] - x0) / res).astype(int); j = np.floor((X[:, 1] - y0) / res).astype(int)
        ok = (i >= 0) & (i < W) & (j >= 0) & (j < H)
        out = np.zeros(len(X), bool)
        out[ok] = M[j[ok], i[ok]]
        return out
    return f
