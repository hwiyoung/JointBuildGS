"""Camera geometry facts for the data section (read-only inputs):
 - 937-image COLMAP model (OPF poses, undistorted PINHOLE 1400x1013): tilt of the optical axis from the down direction
 - camera height above ground: camera centre (ellipsoidal-like frame z + 604) minus ALS class-2 ground (DHHN2016 + 45.7 m bridge),
   2 m cells (mean of class-2 z), holes filled from the nearest valid cell
 - GSD at ground for nadir images = H_agl / f; surface GSD per box = median camera-Z depth of the common-937 COLMAP geometric depth
   maps over pixels whose 3-D point lies inside the box polygon, divided by f (fronto-parallel pixel footprint)
 - nadir (tilt <= 20 deg) / oblique counts for the common base and each box split (fork_inputs split.json)
Usage: python3 -I gsd_views.py <colmap_dense> <ground_npz_glob_dir> <regions_used.json> <fork_inputs_s61> <xmp_all.json> <out.json>"""
import json, sys, struct, glob, time
from pathlib import Path
import numpy as np
from matplotlib.path import Path as MPath
from scipy import ndimage
t0 = time.time()
dense, gdir, reg_path, fi_dir, xmp_path, out = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], Path(sys.argv[4]), sys.argv[5], sys.argv[6]
SHIFT = np.array([690953.0, 5336071.0, 604.0]); ZB = 45.7
def read_cameras(p):
    with open(p, "rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]; cams = {}
        for _ in range(n):
            cid, model, w, h = struct.unpack("<iiQQ", f.read(24))
            npar = {0: 3, 1: 4, 2: 4, 3: 5, 4: 8, 5: 8, 6: 12}[model]
            cams[cid] = dict(model=model, w=w, h=h, p=struct.unpack("<" + "d" * npar, f.read(8 * npar)))
    return cams
def qR(q):
    w, x, y, z = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)], [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
                     [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)]])
def read_images(p):
    ims = {}; n2d = 0
    with open(p, "rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        for _ in range(n):
            iid = struct.unpack("<i", f.read(4))[0]
            q = struct.unpack("<dddd", f.read(32)); t = np.array(struct.unpack("<ddd", f.read(24))); cid = struct.unpack("<i", f.read(4))[0]
            name = b""
            while True:
                c = f.read(1)
                if c == b"\x00":
                    break
                name += c
            k = struct.unpack("<Q", f.read(8))[0]; f.seek(24 * k, 1); n2d += k
            R = qR(q); ims[name.decode()] = dict(R=R, t=t, C=-R.T @ t, cam=cid)
    return ims, n2d
cams = read_cameras(dense / "sparse/cameras.bin")
ims, n2d = read_images(dense / "sparse/images.bin")
cam = cams[1]; fx, fy, cx, cy = cam["p"]
W0, H0 = cam["w"], cam["h"]; GW, GH = 1024, 741
fgx, fgy = fx * GW / W0, fy * GH / H0
F_ORIG = 3717.199209328326          # Pix4D calibrated focal length of the 5280 x 3956 originals (OPF calibrated_cameras.json)
names = sorted(ims)
tilt = {n: float(np.degrees(np.arccos(np.clip(-(ims[n]["R"].T @ np.array([0, 0, 1.0]))[2], -1, 1)))) for n in names}
# ground grid
gs = None
for f in sorted(gdir.glob("als_ground_*.npz")):
    d = np.load(f)
    if gs is None:
        gs, gc = d["gsum"].astype(np.float64), d["gcnt"].astype(np.int64)
    else:
        gs += d["gsum"]; gc += d["gcnt"]
G = np.where(gc > 0, gs / np.maximum(gc, 1), np.nan)
valid = gc > 0
idx = ndimage.distance_transform_edt(~valid, return_distances=False, return_indices=True)
Gf = G[idx[0], idx[1]]
def ground_at(E, N):
    i = int((E - 690000.0) / 2.0); j = int((N - 5335000.0) / 2.0)
    if 0 <= i < 1000 and 0 <= j < 1000:
        return float(Gf[j, i]), bool(valid[j, i])
    return None, None
xmp = json.load(open(xmp_path))["per_image"]
rows = {}
for n in names:
    C = ims[n]["C"] + SHIFT
    g, gv = ground_at(C[0], C[1])
    hagl = (C[2] - (g + ZB)) if g is not None else None
    ra = xmp.get(n, {}).get("RelativeAltitude")
    rows[n] = dict(tilt_deg=round(tilt[n], 2), E=round(C[0], 3), N=round(C[1], 3), h=round(C[2], 3), ground_dhhn=round(g, 3) if g is not None else None,
                   ground_cell_measured=gv, H_agl=round(hagl, 2) if hagl is not None else None, rel_alt_exif=float(ra) if ra else None)
T = np.array([tilt[n] for n in names])
H = np.array([rows[n]["H_agl"] for n in names], float)
nad = T <= 20.0
def stats(a):
    a = np.asarray(a, float); a = a[np.isfinite(a)]
    return dict(n=int(a.size), median=round(float(np.median(a)), 3), p10=round(float(np.percentile(a, 10)), 3), p90=round(float(np.percentile(a, 90)), 3),
                min=round(float(a.min()), 3), max=round(float(a.max()), 3)) if a.size else None
res = dict(camera=dict(model=cam["model"], width=W0, height=H0, fx=fx, fy=fy, cx=cx, cy=cy, grid=[GW, GH], fx_grid=fgx, fy_grid=fgy, f_original_px=F_ORIG,
                       undistorted_equivalent_original_width_px=W0 * F_ORIG / fx),
           n_images=len(names), n_2d_observations_in_images_bin=n2d,
           tilt_counts=dict(nadir_le20=int(nad.sum()), oblique_gt20=int((~nad).sum()), t20_45=int(((T > 20) & (T <= 45)).sum()), gt45=int((T > 45).sum()),
                            le5=int((T <= 5).sum()), le10=int((T <= 10).sum())),
           H_agl_nadir=stats(H[nad]), H_agl_oblique=stats(H[~nad]),
           gsd_ground_nadir_original_cm=stats(H[nad] / F_ORIG * 100), gsd_ground_nadir_train_grid_cm=stats(H[nad] / fgx * 100))
# nadir blocks at 75 m relative altitude
ra = np.array([rows[n]["rel_alt_exif"] if rows[n]["rel_alt_exif"] is not None else np.nan for n in names])
hi = ra > 70
res["H_agl_rel_alt_75m_images"] = stats(H[hi]); res["n_rel_alt_75m"] = int(hi.sum())
res["gsd_ground_rel75_original_cm"] = stats(H[hi] / F_ORIG * 100); res["gsd_ground_rel75_train_grid_cm"] = stats(H[hi] / fgx * 100)
res["tilt_rel75"] = stats(T[hi]); res["tilt_low_alt"] = stats(T[~hi])
res["H_agl_low_alt_images"] = stats(H[~hi])
# per box
REG = json.load(open(reg_path))
def read_depth(p):
    data = Path(p).read_bytes(); off = 0
    for _ in range(3):
        off = data.find(b"&", off, 100) + 1
    w, h, c = map(int, data[:off].decode("ascii").split("&")[:3])
    return np.frombuffer(data, dtype="<f4", offset=off, count=w * h).reshape((w, h), order="F").T
yy, xx = np.indices((GH, GW), dtype=np.float64)
rays = np.stack([(xx + 0.5 - cx * GW / W0) / fgx, (yy + 0.5 - cy * GH / H0) / fgy, np.ones_like(xx)], -1).reshape(-1, 3)
boxes = {}
for bid in ("B0_b10", "B173nb_b10", "B173_b0", "R1rep_b10"):
    sp0 = json.load(open(fi_dir / bid / "split.json"))
    stem2name = {n.rsplit(".", 1)[0]: n for n in names}
    sp = {k: [stem2name[x.rsplit(".", 1)[0] if x.lower().endswith(".jpg") else x] for x in v] for k, v in sp0.items()}
    poly = np.asarray(REG[f"box_{bid}"]["polygon"]) - SHIFT[:2]
    pth = MPath(poly)
    out_b = {}
    for part in ("train", "test"):
        L = sp[part]
        tt = np.array([tilt[n] for n in L])
        med_depth, med_depth_nadir, med_depth_obl = [], [], []
        for n in L:
            dp = dense / "stereo/depth_maps" / f"{n}.geometric.bin"
            if not dp.exists():
                continue
            d = read_depth(dp).ravel()
            ok = np.isfinite(d) & (d > 0)
            X = (rays[ok] * d[ok, None] - ims[n]["t"]) @ ims[n]["R"]
            ins = pth.contains_points(X[:, :2])
            if ins.sum() < 100:
                continue
            md = float(np.median(d[ok][ins]))
            med_depth.append(md); (med_depth_nadir if tilt[n] <= 20 else med_depth_obl).append(md)
        Hb = np.array([rows[n]["H_agl"] for n in L], float)
        out_b[part] = dict(n=len(L), nadir=int((tt <= 20).sum()), oblique=int((tt > 20).sum()), tilt=stats(tt),
                           H_agl_nadir=stats(Hb[tt <= 20]), gsd_ground_nadir_original_cm=stats(Hb[tt <= 20] / F_ORIG * 100),
                           gsd_ground_nadir_train_grid_cm=stats(Hb[tt <= 20] / fgx * 100),
                           surface_depth_m_all=stats(med_depth), surface_depth_m_nadir=stats(med_depth_nadir), surface_depth_m_oblique=stats(med_depth_obl),
                           surface_gsd_original_cm=stats(np.array(med_depth) / F_ORIG * 100), surface_gsd_train_grid_cm=stats(np.array(med_depth) / fgx * 100),
                           surface_gsd_train_grid_cm_nadir=stats(np.array(med_depth_nadir) / fgx * 100),
                           surface_gsd_train_grid_cm_oblique=stats(np.array(med_depth_obl) / fgx * 100),
                           n_views_with_depth_in_box=len(med_depth))
    boxes[bid] = out_b
    print(bid, json.dumps({p: (v["n"], v["nadir"], v["oblique"], v["surface_gsd_train_grid_cm"]) for p, v in out_b.items()}), flush=True)
res["boxes"] = boxes
res["seconds"] = round(time.time() - t0, 1)
json.dump(dict(summary=res, per_image=rows), open(out, "w"), indent=1)
print(json.dumps({k: v for k, v in res.items() if k != "boxes"}, indent=1))
