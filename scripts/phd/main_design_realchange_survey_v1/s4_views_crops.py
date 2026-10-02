"""PHD-MAIN-DESIGN-REALCHANGE-SURVEY-v1 step 4: views and photo crops.

For every target (region, R1 Z08, and each ULS-based change component of
s3 with |d| > 2.5 m and >= 25 m2), using the frozen COLMAP model of the 937
current images (local frame = EPSG:25832 - [690953, 5336071, 604]):
  * tilt of each image = angle between optical axis and nadir;
    nadir (연직) <= 20 deg, oblique (경사) > 20 deg  (flight_meta_summary.md rule)
  * covering views = target sample points project inside the frame in front of
    the camera (>= 50 % of the samples); pose projection, not visibility
  * depth-consistent views = additionally the COLMAP geometric depth at the
    projected pixel is within 1 m of the camera-Z of the current ULS surface
    point for >= 30 % of the samples (MVS actually measured that surface)
  * crop = most nadir covering view whose projected target box lies fully in
    frame; undistorted 1400 x 1013 PINHOLE image of the COLMAP workspace.
Read-only on inputs.  scientific_verdict: null.
"""
import csv
import json
import struct
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

out = Path(sys.argv[1]); cfg = json.loads(Path(sys.argv[2]).read_text())
art = Path(cfg['artifact_root_container'])
sh = np.array(cfg['world_shift_xyz_m'])
D = dict(np.load(out / 'derived.npz'))
g = cfg['grid']; res = g['res_m']
ny, nx = D['dtm'].shape
ec = g['e_min'] + (np.arange(nx) + 0.5) * res; nc = g['n_min'] + (np.arange(ny) + 0.5) * res


def read_cameras(p):
    cams = {}
    with open(p, 'rb') as f:
        n = struct.unpack('<Q', f.read(8))[0]
        for _ in range(n):
            cid, model, w, h = struct.unpack('<iiQQ', f.read(24))
            npar = {0: 3, 1: 4, 2: 4, 3: 5, 4: 8, 5: 8, 6: 12}[model]
            cams[cid] = dict(model=model, w=w, h=h, p=struct.unpack('<' + 'd' * npar, f.read(8 * npar)))
    return cams


def qR(q):
    w, x, y, z = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
                     [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
                     [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)]])


def read_images(p):
    ims = []
    with open(p, 'rb') as f:
        n = struct.unpack('<Q', f.read(8))[0]
        for _ in range(n):
            iid = struct.unpack('<i', f.read(4))[0]
            q = struct.unpack('<dddd', f.read(32)); t = struct.unpack('<ddd', f.read(24)); cid = struct.unpack('<i', f.read(4))[0]
            name = b''
            while True:
                c = f.read(1)
                if c == b'\x00':
                    break
                name += c
            n2 = struct.unpack('<Q', f.read(8))[0]; f.seek(24 * n2, 1)
            R = qR(q); tt = np.array(t)
            axis = R.T @ np.array([0, 0, 1.0])
            tilt = float(np.degrees(np.arccos(np.clip(-axis[2], -1, 1))))
            ims.append(dict(id=iid, name=name.decode(), R=R, t=tt, cam=cid, C=-R.T @ tt, tilt=tilt))
    return ims


def read_depth(p):
    data = Path(p).read_bytes(); off = 0
    for _ in range(3):
        off = data.find(b'&', off, 100) + 1
    w, h, c = map(int, data[:off].decode('ascii').split('&')[:3])
    return np.frombuffer(data, dtype='<f4', offset=off).reshape((w, h), order='F').T


colmap = art / cfg['inputs']['colmap_sparse']
cams = read_cameras(colmap / 'cameras.bin'); ims = read_images(colmap / 'images.bin')
cam = cams[ims[0]['cam']]
fx, fy, cx, cy = cam['p']; W, H = cam['w'], cam['h']
print('images', len(ims), 'camera', cam['model'], W, H, flush=True)


def sample_dsm(e, n, layer='uls'):
    ix = np.clip(((np.asarray(e) - g['e_min']) / res).astype(int), 0, nx - 1)
    iy = np.clip(((np.asarray(n) - g['n_min']) / res).astype(int), 0, ny - 1)
    return D[layer][iy, ix].astype(float)


# ---- targets ---------------------------------------------------------------------
regs = json.loads((out / 'regions.json').read_text())
targets = []
z08 = np.array([[690916.7665713681, 5336041.620778608], [690932.4994979611, 5336084.846639165], [690977.6047437588, 5336068.429672285], [690961.8718171659, 5336025.203811728]])
targets.append(dict(tid='R1_Z08', kind='zone', poly=z08.tolist()))
for rid in ('R1', 'R2', 'R3', 'R4', 'R5'):
    targets.append(dict(tid=rid + '_region', kind='region', poly=regs[rid]['corners_epsg25832']))
blds_all = json.loads((out / 's1' / 'lod2_buildings.json').read_text())
for b in blds_all:
    if b['id'] == 'DEBY_LOD2_4959323':
        ring = max(b['surfaces']['ground'], key=lambda p: len(p['ext']))['ext']
        targets.append(dict(tid='B0_building', kind='building', poly=[[q[0], q[1]] for q in ring[:-1]]))
comps = list(csv.DictReader(open(out / 'change_components.csv')))
seen = []
for r in comps:
    if r['cur'] != 'uls' or r['thr'] != '2.5':
        continue
    e, n = float(r['e']), float(r['n'])
    key = None
    for s in seen:
        if abs(s[0] - e) < 6 and abs(s[1] - n) < 6:
            key = s
    if key:
        continue
    seen.append((e, n))
    bb = json.loads(r['bbox'])
    targets.append(dict(tid='C%02d' % (len(seen)), kind='component', prior=r['prior'], change=r['kind'], area=float(r['area_m2']),
                        d_med=float(r['d_med']), e=e, n=n, buildings=r['buildings'], regions=r['regions'],
                        poly=[[bb[0] - 1, bb[1] - 1], [bb[2] + 1, bb[1] - 1], [bb[2] + 1, bb[3] + 1], [bb[0] - 1, bb[3] + 1]]))
extra = json.loads(Path(sys.argv[3]).read_text()) if len(sys.argv) > 3 else {}
if extra.get('buildings'):
    from shapely.geometry import Polygon as SPoly
    from shapely.ops import unary_union as SUnion
    byid = {b['id']: b for b in blds_all}
    for tid, idl in extra['buildings'].items():
        ps = []
        for bid in idl:
            for p in byid[bid]['surfaces']['ground']:
                ps.append(SPoly(np.asarray(p['ext'])[:, :2]).buffer(0))
        rect = SUnion(ps).minimum_rotated_rectangle
        targets.append(dict(tid=tid, kind='building', poly=[list(c) for c in list(rect.exterior.coords)[:4]]))

# samples per target: grid points inside polygon at the current ULS height (MVS where ULS missing)
from matplotlib.path import Path as MPath
for t in targets:
    poly = np.array(t['poly'])
    x0, y0 = poly.min(0); x1, y1 = poly.max(0)
    step = max(0.5, np.sqrt((x1 - x0) * (y1 - y0) / 400.0))
    xx, yy = np.meshgrid(np.arange(x0, x1, step), np.arange(y0, y1, step))
    pts = np.column_stack([xx.ravel(), yy.ravel()])
    pts = pts[MPath(poly).contains_points(pts)] if len(pts) else pts
    z = sample_dsm(pts[:, 0], pts[:, 1], 'uls')
    zm = sample_dsm(pts[:, 0], pts[:, 1], 'mvs')
    z = np.where(np.isfinite(z), z, zm)
    ok = np.isfinite(z)
    t['samples'] = np.column_stack([pts[ok], z[ok]])
    t['ztop'] = float(np.nanmax(z)) if ok.any() else 0.0
    t['zbot'] = float(np.nanmin(sample_dsm(pts[:, 0], pts[:, 1], 'dtm'))) if len(pts) else 0.0

# ---- one pass over the images ------------------------------------------------------
t0 = time.time()
dm = art / cfg['inputs']['colmap_depth_maps']
for t in targets:
    t['cover'] = []; t['consistent'] = []
for k, im in enumerate(ims):
    depth = None
    for t in targets:
        S = t['samples']
        if len(S) == 0:
            continue
        X = S - sh
        Xc = X @ im['R'].T + im['t']
        z = Xc[:, 2]
        front = z > 1.0
        u = fx * Xc[:, 0] / np.where(front, z, 1) + cx; v = fy * Xc[:, 1] / np.where(front, z, 1) + cy
        inside = front & (u >= 0) & (u < W) & (v >= 0) & (v < H)
        if inside.mean() < 0.5:
            continue
        t['cover'].append(k)
        if depth is None:
            depth = read_depth(dm / (im['name'] + '.geometric.bin'))
            dh, dw = depth.shape
        ud = np.clip((u * dw / W).astype(int), 0, dw - 1); vd = np.clip((v * dh / H).astype(int), 0, dh - 1)
        dv = depth[vd, ud]
        cons = inside & (dv > 0) & (np.abs(dv - z) < 1.0)
        if cons.sum() >= 0.3 * len(S):
            t['consistent'].append(k)
    if k % 200 == 0:
        print('img', k, round(time.time() - t0, 1), flush=True)
print('views pass', round(time.time() - t0, 1), 's', flush=True)

# ---- crops -----------------------------------------------------------------------------
# Two crops per target: the most nadir covering view (tilt <= 20 deg preferred, then the
# largest share of the projected target box inside the frame), and the most oblique-informative
# view (tilt > 20 deg with the largest box share).  The crop is the in-frame part of the box.
cropdir = out / 'crops'; cropdir.mkdir(exist_ok=True)
imgdir = art / cfg['inputs']['colmap_images']
summary = []


def box_share(u, v):
    uc = np.clip(u, 0, W); vc = np.clip(v, 0, H)
    a = (u.max() - u.min()) * (v.max() - v.min())
    ai = max(0.0, uc.max() - uc.min()) * max(0.0, vc.max() - vc.min())
    return ai / a if a > 0 else 0.0


def make_crop(t, k, tag):
    im = ims[k]
    poly = np.array(t['poly'])
    box3 = np.array([[p[0], p[1], zz] for p in poly for zz in (t['zbot'], t['ztop'])])
    Xc = (box3 - sh) @ im['R'].T + im['t']
    u = fx * Xc[:, 0] / Xc[:, 2] + cx; v = fy * Xc[:, 1] / Xc[:, 2] + cy
    img = Image.open(imgdir / im['name']).convert('RGB')
    pad = max(40, 0.35 * max(min(u.max(), W) - max(u.min(), 0), min(v.max(), H) - max(v.min(), 0)))
    x0, y0 = max(0, int(u.min() - pad)), max(0, int(v.min() - pad)); x1, y1 = min(W, int(u.max() + pad)), min(H, int(v.max() + pad))
    crop = img.crop((x0, y0, x1, y1))
    zc = float(np.nanmedian(t['samples'][:, 2])) if len(t['samples']) else t['ztop']
    Pc = np.array([[p[0], p[1], zc] for p in poly] + [[poly[0][0], poly[0][1], zc]])
    Xc = (Pc - sh) @ im['R'].T + im['t']
    uu = fx * Xc[:, 0] / Xc[:, 2] + cx - x0; vv = fy * Xc[:, 1] / Xc[:, 2] + cy - y0
    ImageDraw.Draw(crop).line(list(zip(uu.tolist(), vv.tolist())), fill=(255, 0, 255), width=2)
    crop.save(cropdir / ('%s_%s.jpg' % (t['tid'], tag)), quality=92)
    return dict(image=im['name'], tilt=round(im['tilt'], 1), box=[x0, y0, x1, y1], share=round(box_share(u, v), 3))


for t in targets:
    poly = np.array(t['poly'])
    box3 = np.array([[p[0], p[1], zz] for p in poly for zz in (t['zbot'], t['ztop'])])
    cand = []
    for k in t['cover']:
        im = ims[k]
        Xc = (box3 - sh) @ im['R'].T + im['t']
        if (Xc[:, 2] <= 1).any():
            continue
        u = fx * Xc[:, 0] / Xc[:, 2] + cx; v = fy * Xc[:, 1] / Xc[:, 2] + cy
        cand.append((k, box_share(u, v), im['tilt']))
    rec = dict(tid=t['tid'], kind=t['kind'], n_cover=len(t['cover']), n_cover_nadir=sum(ims[k]['tilt'] <= 20 for k in t['cover']),
               n_consistent=len(t['consistent']), n_consistent_nadir=sum(ims[k]['tilt'] <= 20 for k in t['consistent']),
               samples=int(len(t['samples'])))
    for key in ('prior', 'change', 'area', 'd_med', 'e', 'n', 'buildings', 'regions'):
        if key in t:
            rec[key] = t[key]
    rec['n_cover_oblique'] = rec['n_cover'] - rec['n_cover_nadir']
    rec['poly'] = [[round(float(a), 2), round(float(b), 2)] for a, b in np.array(t['poly'])]
    rec['n_consistent_oblique'] = rec['n_consistent'] - rec['n_consistent_nadir']
    nad = [c for c in cand if c[2] <= 20]
    obl = [c for c in cand if c[2] > 20]
    if nad:
        k = sorted(nad, key=lambda c: (-round(c[1], 2), c[2]))[0][0]
        rec['crop_nadir'] = make_crop(t, k, 'nadir')
    if obl:
        k = sorted(obl, key=lambda c: (-round(c[1], 2), abs(c[2] - 45)))[0][0]
        rec['crop_oblique'] = make_crop(t, k, 'oblique')
    summary.append(rec)
(out / 'targets_views.json').write_text(json.dumps(summary, indent=1, ensure_ascii=False))
tilts = np.array([im['tilt'] for im in ims])
(out / 'image_tilts.json').write_text(json.dumps({im['name']: round(im['tilt'], 2) for im in ims}, indent=0))
print('tilt <=20:', int((tilts <= 20).sum()), '20-45:', int(((tilts > 20) & (tilts <= 45)).sum()), '>45:', int((tilts > 45).sum()))
for r in summary:
    print(r['tid'], r.get('change'), r.get('area'), r.get('d_med'), 'cover', r['n_cover'], '(n', r['n_cover_nadir'], 'o', r['n_cover_oblique'], ') consistent', r['n_consistent'],
          '(n', r['n_consistent_nadir'], 'o', r['n_consistent_oblique'], ')', (r.get('crop_nadir') or {}).get('share'), r.get('buildings'), r.get('regions'))
