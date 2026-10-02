"""PHD-MAIN-DESIGN-REALCHANGE-SURVEY-v1 step 5: one figure row per target.

Row = [current photo crop (most nadir view) | MVS - ALS 2022 height map |
       MVS - LoD2 height map | section: ALS 2022, LoD2, MVS 2024, ULS 2024].
'Current observation' in the maps = the MVS dense cloud of the 937 current images
(90th percentile per 0.5 m cell, 3x3 median).  The ULS is the reference and
appears only in the section (and in the row's numbers).  LoD2 map: outside LoD2
footprints LoD2 says 'no building', so MVS height above the ALS DTM is shown there.
Vegetation-like cells (ULS multi-return > 0.3) are greyed.  scientific_verdict: null.
"""
import csv
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np
from PIL import Image

for f in ('/fonts/NotoSansCJK-Regular.ttc', '/fonts/NotoSansCJK-Bold.ttc'):
    if Path(f).exists():
        font_manager.fontManager.addfont(f)
plt.rcParams['font.family'] = ['Noto Sans CJK JP', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

out = Path(sys.argv[1]); cfg = json.loads(Path(sys.argv[2]).read_text()); spec = json.loads(Path(sys.argv[3]).read_text())
rowdir = out / (sys.argv[4] if len(sys.argv) > 4 else 'rows'); rowdir.mkdir(exist_ok=True)
D = dict(np.load(out / 'derived.npz'))
g = cfg['grid']; res = g['res_m']
ny, nx = D['dtm'].shape
ec = g['e_min'] + (np.arange(nx) + 0.5) * res; nc = g['n_min'] + (np.arange(ny) + 0.5) * res
dtm = D['dtm'].astype(float)
veg = D['veg'] > 0.3
tv = {r['tid']: r for r in json.loads((out / 'targets_views.json').read_text())}
comps = {}
for r in csv.DictReader(open(out / 'change_components.csv')):
    pass
fid = D['fid']
mvs = D['mvs'].astype(float); als = D['als'].astype(float); lod = D['lod'].astype(float); uls = D['uls'].astype(float)
d_als = mvs - als
d_lod = np.where(np.isfinite(lod), mvs - lod, np.where(fid >= 0, np.nan, mvs - dtm))


def sample(layer, e, n):
    ix = np.clip(((e - g['e_min']) / res).astype(int), 0, nx - 1); iy = np.clip(((n - g['n_min']) / res).astype(int), 0, ny - 1)
    return layer[iy, ix]


def section_line(poly, mode='auto', ext=15.0):
    P = np.array(poly)
    c = P.mean(0)
    X = P - c
    w, V = np.linalg.eigh(np.cov(X.T) if len(P) > 2 else np.eye(2))
    major = V[:, np.argmax(w)]; minor = V[:, np.argmin(w)]
    proj_major = X @ major; proj_minor = X @ minor
    L1 = np.ptp(proj_major); L2 = np.ptp(proj_minor)
    if mode == 'across' or (mode == 'auto' and L1 > 2.5 * max(L2, 1e-6)):
        dvec, half = minor, L2 / 2
    else:
        dvec, half = major, L1 / 2
    half += ext
    return c - dvec * half, c + dvec * half


def draw_map(ax, data, bbox, title, poly, line, cmap='RdBu_r', vmax=6.0, poly2=None):
    x0, y0, x1, y1 = bbox
    ix0, ix1 = int((x0 - g['e_min']) / res), int((x1 - g['e_min']) / res)
    iy0, iy1 = int((y0 - g['n_min']) / res), int((y1 - g['n_min']) / res)
    ix0, iy0 = max(ix0, 0), max(iy0, 0); ix1, iy1 = min(ix1, nx), min(iy1, ny)
    sub = data[iy0:iy1, ix0:ix1]
    ext = [g['e_min'] + ix0 * res, g['e_min'] + ix1 * res, g['n_min'] + iy0 * res, g['n_min'] + iy1 * res]
    ax.set_facecolor('#d9d9d9')
    im = ax.imshow(sub, origin='lower', extent=ext, cmap=cmap, vmin=-vmax, vmax=vmax, interpolation='nearest')
    vs = np.where(veg[iy0:iy1, ix0:ix1], 1.0, np.nan)
    ax.imshow(vs, origin='lower', extent=ext, cmap='Greys', vmin=0, vmax=2.5, alpha=0.55, interpolation='nearest')
    fp = (fid[iy0:iy1, ix0:ix1] >= 0).astype(float)
    if fp.any() and not fp.all():
        ax.contour(np.linspace(ext[0], ext[1], fp.shape[1]), np.linspace(ext[2], ext[3], fp.shape[0]), fp, [0.5], colors='k', linewidths=0.6)
    P = np.array(list(poly) + [poly[0]])
    ax.plot(P[:, 0], P[:, 1], color='#d000d0', lw=1.4)
    for p2 in (poly2 or []):
        Q = np.array(list(p2) + [p2[0]])
        ax.plot(Q[:, 0], Q[:, 1], color='#111111', lw=1.2, ls='--')
    if line is not None:
        a, b = line
        ax.plot([a[0], b[0]], [a[1], b[1]], 'k-', lw=1.6)
        ax.text(a[0], a[1], 'A', fontsize=10, weight='bold', ha='center', va='center', bbox=dict(boxstyle='circle,pad=0.15', fc='w', ec='k', lw=0.6))
        ax.text(b[0], b[1], 'B', fontsize=10, weight='bold', ha='center', va='center', bbox=dict(boxstyle='circle,pad=0.15', fc='w', ec='k', lw=0.6))
    ax.set_xlim(x0, x1); ax.set_ylim(y0, y1); ax.set_aspect('equal')
    ax.set_xticks([]); ax.set_yticks([])
    sb = 10 if (x1 - x0) < 120 else 50
    ax.plot([x0 + 0.05 * (x1 - x0), x0 + 0.05 * (x1 - x0) + sb], [y0 + 0.05 * (y1 - y0)] * 2, 'k-', lw=3)
    ax.text(x0 + 0.05 * (x1 - x0) + sb / 2, y0 + 0.08 * (y1 - y0), '%d m' % sb, ha='center', fontsize=8)
    ax.set_title(title, fontsize=10)
    return im


def row(t):
    tid = t['tid']; poly = t['poly']
    P = np.array(poly)
    line = t.get('line') or section_line(poly, t.get('section', 'auto'))
    line = (np.array(line[0]), np.array(line[1]))
    pts = np.vstack([P, line[0], line[1]])
    cx, cy = pts.mean(0)
    half = max(np.ptp(pts[:, 0]), np.ptp(pts[:, 1])) / 2 + t.get('margin', 8.0)
    half = max(half, 20.0)
    bbox = (cx - half, cy - half, cx + half, cy + half)
    fig = plt.figure(figsize=(17, 3.9))
    gs = fig.add_gridspec(1, 6, width_ratios=[1.05, 1, 1, 0.05, 0.42, 1.6], wspace=0.06)
    ax0 = fig.add_subplot(gs[0]); ax1 = fig.add_subplot(gs[1]); ax2 = fig.add_subplot(gs[2]); cax = fig.add_subplot(gs[3]); ax3 = fig.add_subplot(gs[5])
    v = tv.get(t.get('view_tid', tid), {})
    crop = out / 'crops' / ('%s_%s.jpg' % (t.get('view_tid', tid), t.get('crop', 'nadir')))
    if crop.exists():
        ax0.imshow(Image.open(crop)); c = v.get('crop_' + t.get('crop', 'nadir'), {})
        ax0.set_title('현재 영상 %s (경사 %s°)' % (c.get('image', '')[-12:-4], c.get('tilt', '')), fontsize=10)
    else:
        ax0.text(0.5, 0.5, '덮는 영상 없음', ha='center'); ax0.set_title('현재 영상', fontsize=10)
    ax0.axis('off')
    im = draw_map(ax1, d_als, bbox, 'MVS(2024) − 항공 LiDAR(2022)', poly, line, poly2=t.get('poly2'))
    draw_map(ax2, d_lod, bbox, 'MVS(2024) − LoD2', poly, line, poly2=t.get('poly2'))
    cb = fig.colorbar(im, cax=cax); cb.set_label('높이 차이 (m)\n파랑 = 지금 낮음 · 빨강 = 지금 높음', fontsize=8); cb.ax.tick_params(labelsize=8)
    a, b = line
    L = np.linalg.norm(b - a); s = np.arange(0, L, 0.25)
    e = a[0] + (b[0] - a[0]) * s / L; n = a[1] + (b[1] - a[1]) * s / L
    base = float(np.nanmedian(sample(dtm, e, n)))
    ax3.fill_between(s, sample(dtm, e, n) - base, -50, color='#e6e6e6', label='지면(항공 LiDAR 2022)')
    ax3.plot(s, sample(als, e, n) - base, color='#1f5fbf', lw=1.6, label='항공 LiDAR 2022')
    ax3.plot(s, sample(lod, e, n) - base, color='#e07b00', lw=1.8, label='LoD2')
    ax3.plot(s, sample(mvs, e, n) - base, color='#2a9d3a', lw=1.2, label='MVS 2024 (현재 관측)')
    ax3.plot(s, sample(uls, e, n) - base, 'k.', ms=2.2, label='드론 LiDAR 2024 (참값)')
    vals = np.concatenate([sample(x, e, n) - base for x in (als, lod, mvs, uls)])
    vals = vals[np.isfinite(vals)]
    top = np.nanquantile(vals, 0.995) if len(vals) else 10
    ax3.set_ylim(min(-2, np.nanmin(vals) - 1 if len(vals) else -2), top + 3)
    ax3.set_xlim(0, L)
    ax3.set_xlabel('A → B 거리 (m)', fontsize=9); ax3.set_ylabel('지면 기준 높이 (m)', fontsize=9)
    ax3.tick_params(labelsize=8); ax3.grid(alpha=0.3)
    ax3.legend(fontsize=7, loc='upper right', ncol=2, framealpha=0.85)
    ax3.text(0, 1.02, 'A', transform=ax3.transAxes, fontsize=10, weight='bold'); ax3.text(1, 1.02, 'B', transform=ax3.transAxes, fontsize=10, weight='bold', ha='right')
    fig.suptitle(t.get('title', tid), fontsize=11, x=0.01, ha='left', y=1.07, weight='bold')
    if t.get('note'):
        fig.text(0.01, -0.04, t['note'], fontsize=9, ha='left')
    fig.savefig(rowdir / ('%s.png' % tid), dpi=110, bbox_inches='tight')
    plt.close(fig)
    return dict(tid=tid, line=[a.tolist(), b.tolist()], bbox=list(bbox))


done = []
for t in spec['targets']:
    if 'poly' not in t:
        src = tv.get(t.get('view_tid', t['tid']))
    done.append(row(t))
    print('row', t['tid'], flush=True)
(rowdir / 'rows_meta.json').write_text(json.dumps(done, indent=1))
