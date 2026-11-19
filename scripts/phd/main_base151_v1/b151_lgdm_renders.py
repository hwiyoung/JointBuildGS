"""PHD-MAIN-BASE151-v1: LGDM (BASELINES mvsfuse depth composite, user decision 2026-11-19) into the mesh rule of the other methods
(GTJUDGE environment, CPU; /gtjudge = OUT/gt, /b151 = OUT read-only).

  python b151_lgdm_renders.py unit <run> <unit>    # 4.2: /gtjudge/jobs/<unit>__<P>__<run>.json + /gtjudge/renders/<key>/
  python b151_lgdm_renders.py site <run> <site>    # 4.1: /gtjudge/jobs/<site>__<P>__<run>.json + /gtjudge/renders/<key>/
run = b151_LGDM_<ALS|LoD2>. The 'render' of a view is the composite depth of that view (/b151/lgdm/<P>/cell<k>/depth/<stem>.npy:
camera-z m, NaN = none -> 0) with RESCORE render_model's box mask (back-projected point inside the box and depth > 0), and the view's
image as rgb (colour of the TSDF only). The receipt has render_model's fields, so RESCORE mesh_pipeline.prepare reads it unchanged.
Unit views = cell k training views -> the composite of cell k. Site views (GTJUDGE views/<site>.json): a view with a composite in some cell
uses the cell whose expanded rectangle holds the most of the site box; a site view without any composite (not a campus training view, no
WIDEN0 MVS) gets an empty depth (it adds nothing to the TSDF) and is counted in the receipt. scientific_verdict: null
"""
import sys
import time

import cv2
import numpy as np

sys.path.insert(0, '/repo/scripts/phd/main_gtjudge_v1')
from inherited import O, cfg as gt_cfg, sha, dump, now  # noqa: E402
import json  # noqa: E402
from pathlib import Path  # noqa: E402

B = Path('/b151')
IMG = Path('/art/phase-payloads/phd/main_trainunit_v1/PHD-MAIN-TRAINUNIT-v1/scenes/campus/images')
CELLS = Path('/art/phase-payloads/phd/main_trainunit_v1/PHD-MAIN-TRAINUNIT-v1/cells/cells.json')


def masked(d, v, box):
    """render_model.py: xyz = ((x - cx) d / fx, (y - cy) d / fy, d) in camera frame -> world with W2C^-1; keep inside box and d > 0."""
    H, W = d.shape
    K = np.asarray(v['K'], float)
    yy, xx = np.meshgrid(np.arange(H), np.arange(W), indexing='ij')
    cam = np.stack([(xx - K[0, 2]) * d / K[0, 0], (yy - K[1, 2]) * d / K[1, 1], d, np.ones_like(d)], -1)
    M = np.asarray(v['W2C'], float)
    world = cam.reshape(-1, 4) @ np.linalg.inv(M).T
    b = np.asarray(box, float)
    ok = ((world[:, :3] >= b[0]) & (world[:, :3] <= b[1])).all(1).reshape(H, W) & (d > 0)
    out = d.astype(np.float32).copy()
    out[~ok] = 0
    return out


def write(run, site, prior, views, box, source_of, extra):
    t0 = time.monotonic()
    key = f'{site}__{prior}__{run}'
    root = O / 'renders' / key
    if (root / 'receipt.json').exists():
        return
    root.mkdir(parents=True, exist_ok=True)
    job = dict(site=site, prior=prior, family='LGDM', key=key, box=box, run=run, note='LGDM depth composite (BASELINES mvsfuse compose), no Gaussians', **extra,
               scientific_verdict=None)
    dump(O / 'jobs' / f'{key}.json', job)
    recs, empty, finite = [], 0, []
    for i, v in enumerate(views):
        src = source_of(v['name'])
        if src is None:
            d = np.zeros((v['height'], v['width']), np.float32)
            empty += 1
        else:
            d = np.load(src).astype(np.float32)
            d[~np.isfinite(d)] = 0
            d = masked(d, v, box)
        finite.append(float((d > 0).mean()))
        rgb = cv2.cvtColor(cv2.imread(str(IMG / f'{v["name"]}.jpg')), cv2.COLOR_BGR2RGB)
        assert rgb.shape[:2] == d.shape
        p = root / f'{i:04d}.npz'
        np.savez_compressed(p, depth=d, rgb=rgb.astype(np.uint8))
        recs.append(dict(v, file=p.name, sha256=sha(p), source=str(src) if src else None))
    dump(root / 'receipt.json', dict(status='PASS', views=recs, cached_views=0, box=box, model_sha256=None, job=job, views_without_composite=empty,
                                     mean_share_of_pixels_with_depth=float(np.mean(finite)), seconds=time.monotonic() - t0, optimization_steps=0,
                                     rule='LGDM composite depth with render_model box mask', scientific_verdict=None))
    print('LGDM_RENDERS', key, len(views), empty, flush=True)


def unit(run, uname):
    gt_cfg()
    prior = run.split('_')[2]
    u = {x['unit']: x for x in json.loads((O / 'units/layout.json').read_text())['units']}[uname]
    views = json.loads((O / 'views' / f'{uname}.json').read_text())['views']
    k = u['cell']
    src = lambda n: B / 'lgdm' / prior / f'cell{k}' / 'depth' / f'{n}.npy'
    for v in views:
        assert src(v['name']).exists(), v['name']
    write(run, uname, prior, views, u['box'], src, dict(cell=k))


def site(run, site_name):
    gt_cfg()
    prior = run.split('_')[2]
    vf = json.loads((O / 'views' / f'{site_name}.json').read_text())
    box = vf['box']
    cells = json.loads(CELLS.read_text())['cells']
    lo, hi = np.array(box[0][:2]), np.array(box[1][:2])

    def overlap(c):
        a, b = np.maximum(lo, c['expanded_min']), np.minimum(hi, c['expanded_max'])
        return float(np.prod(np.clip(b - a, 0, None)))
    order = sorted(cells, key=lambda c: -overlap(c))
    has = {c['id']: {p.stem for p in (B / 'lgdm' / prior / f'cell{c["id"]}' / 'depth').glob('*.npy')} for c in cells}
    used = {}

    def src(n):
        for c in order:
            if n in has[c['id']]:
                used[n] = c['id']
                return B / 'lgdm' / prior / f'cell{c["id"]}' / 'depth' / f'{n}.npy'
        return None
    write(run, site_name, prior, vf['views'], box, src, dict(cell_order=[c['id'] for c in order], cell_overlap_m2=[overlap(c) for c in order]))


if __name__ == '__main__':
    a = sys.argv[1:]
    dict(unit=unit, site=site)[a[0]](a[1], a[2])
