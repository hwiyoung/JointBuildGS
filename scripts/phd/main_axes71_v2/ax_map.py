"""PHD-MAIN-AXES71-v2 map drawing shared by 일 6 (영역 지도) and 일 7 (결측 지도): the prior patches as filled squares, seen from above
(orthographic, north up) and in two oblique perspective views (45 deg from vertical, azimuths 225 and 45 deg, looking at the centre of the
range: scripts/phd/main_viscmp_v4/d4_diag.camera). A patch is drawn by 5 x 5 points on its square (centre +- 0.125 m along the two tangent
vectors of the patch store, S0/s61/box/<site>/<prior>/units.npz loc_t1, loc_t2); the nearest point per pixel wins (z-buffer).
Hatching (config cells.hatch) is drawn in image space. scientific_verdict: null."""
import sys

import numpy as np
from matplotlib import colors as mcolors

sys.path.insert(0, "/repo/scripts/phd/main_viscmp_v4")
sys.path.insert(0, "/repo/scripts/phd/main_photofig_v1")
sys.path.insert(0, "/repo/scripts/phd/main_stage0_v1")
import vc_render as RD  # noqa: E402

S0U = "/s0/s61/box/{site}/{prior}/units.npz"


def setup_plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    for f in ("/fonts/NotoSansCJK-Regular.ttc", "/fonts/NotoSansCJK-Bold.ttc"):
        try:
            font_manager.fontManager.addfont(f)
        except Exception:
            pass
    plt.rcParams["font.family"] = ["Noto Sans CJK JP", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["pdf.fonttype"] = 42
    return plt


def rgb(h):
    return np.array(mcolors.to_rgb(h))


def patch_points(site, prior, idx, k=5):
    """points on the squares of the patches idx: (points [N*k*k, 3], patch index of each point)."""
    U = np.load(S0U.format(site=site, prior=prior))
    c, t1, t2 = U["loc_center"][idx], U["loc_t1"][idx], U["loc_t2"][idx]
    g = (np.arange(k) + 0.5) / k - 0.5
    a, b = np.meshgrid(g, g)
    a, b = a.ravel() * 0.25, b.ravel() * 0.25
    P = c[:, None, :] + a[None, :, None] * t1[:, None, :] + b[None, :, None] * t2[:, None, :]
    return P.reshape(-1, 3), np.repeat(idx, k * k)


def hatch_mask(H, W, period=6, width=2, angle=45):
    yy, xx = np.mgrid[0:H, 0:W]
    s = (xx + yy) if angle == 45 else (xx - yy)
    return (s % period) < width


def paint(lab_img, palette, hatch=None, light=None):
    """lab_img [H, W] integer labels (-1 = background); palette: label -> rgb; hatch: label -> (bg rgb, line rgb); light [H, W] bool = lighten."""
    H, W = lab_img.shape
    img = np.ones((H, W, 3))
    hm = hatch_mask(H, W)
    for l, c in palette.items():
        m = lab_img == l
        if not m.any():
            continue
        if hatch and l in hatch:
            bg, ln = hatch[l]
            img[m] = bg
            img[m & hm] = ln
        else:
            img[m] = c
    if light is not None:
        img[light] = 0.35 * img[light] + 0.65
    return img


def top_labels(P, lab, lo, hi, px, extra=None):
    """orthographic top view: per pixel the label of the highest point (and of `extra` arrays the same pick)."""
    W = int(np.ceil((hi[0] - lo[0]) / px)); H = int(np.ceil((hi[1] - lo[1]) / px))
    iu = np.clip(((P[:, 0] - lo[0]) / px).astype(int), 0, W - 1)
    iv = np.clip(((hi[1] - P[:, 1]) / px).astype(int), 0, H - 1)
    order = np.argsort(P[:, 2])                      # low first, high last (high overwrites)
    img = np.full((H, W), -1, np.int64)
    img[iv[order], iu[order]] = lab[order]
    ex = None
    if extra is not None:
        ex = np.zeros((H, W), bool)
        ex[iv[order], iu[order]] = extra[order]
    return img, ex


def camera(lo, hi, az_deg, tilt_deg=45.0, pw=900):
    c = 0.5 * (lo + hi); ext = float(np.linalg.norm((hi - lo)[:2]))
    a, t = np.radians(az_deg), np.radians(tilt_deg)
    d = np.array([np.sin(a) * np.sin(t), np.cos(a) * np.sin(t), np.cos(t)])
    eye = c + 2.5 * ext * d
    fit = np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])
    pr = RD.LookAt(eye, c, [0, 0, 1], fit, [pw, pw], margin=0.04)
    u, v, _ = pr.project(fit)
    size = [pw, int(round(pw * np.clip((v.max() - v.min()) / (u.max() - u.min()), 0.35, 1.2)))]
    return RD.LookAt(eye, c, [0, 0, 1], fit, size, margin=0.04)


def oblique_labels(cam, P, lab, extra=None, ss=2):
    """perspective view: per pixel the label of the nearest point (z-buffer), drawn on a ss-times finer grid then down-picked."""
    big = RD.LookAt.__new__(RD.LookAt)
    big.__dict__.update(cam.__dict__)
    big.W, big.H = cam.W * ss, cam.H * ss
    big.fx, big.fy, big.cx, big.cy = cam.fx * ss, cam.fy * ss, cam.cx * ss, cam.cy * ss
    u, v, z = big.project(P)
    ok = (z > 0) & (u >= 0) & (u < big.W) & (v >= 0) & (v < big.H)
    iu, iv, zz, ll = np.floor(u[ok]).astype(int), np.floor(v[ok]).astype(int), z[ok], lab[ok]
    order = np.argsort(-zz)
    img = np.full((big.H, big.W), -1, np.int64)
    img[iv[order], iu[order]] = ll[order]
    ex = None
    if extra is not None:
        ex = np.zeros((big.H, big.W), bool)
        ex[iv[order], iu[order]] = extra[ok][order]
    # fill one-pixel holes by the 3 x 3 mode is not done; down-pick the top-left sample of each ss block
    img = img[::ss, ::ss]
    ex = ex[::ss, ::ss] if ex is not None else None
    return img, ex


def scalebar(ax, px, W, H, length_m=10.0):
    L = length_m / px
    x0, y0 = W * 0.04, H * 0.96
    ax.plot([x0, x0 + L], [y0, y0], color="k", lw=2.0, solid_capstyle="butt")
    ax.text(x0 + L / 2, y0 - H * 0.015, f"{length_m:g} m", ha="center", va="bottom", fontsize=6)


def north(ax, W, H):
    x, y = W * 0.96, H * 0.97
    ax.annotate("", xy=(x, y - H * 0.07), xytext=(x, y), arrowprops=dict(arrowstyle="-|>", color="k", lw=1.0))
    ax.text(x, y - H * 0.08, "북", ha="center", va="bottom", fontsize=6)
