"""Freeze candidate pixel support and diagnostic views before optimization."""
import argparse
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import numpy as np
import torch
from gsplat import rasterization_2dgs
from gs_engine import Scene, tensor, project
from input_audit import bind
from prepare_places import save


def representative_views(unit, cams):
    reps = json.loads(Path('/docs/representatives_v1.json').read_text())['rows']
    with np.load(Path('/out/places') / (unit + '.npz')) as z:
        d = {k: z[k] for k in ['point_id', 'centre', 'normal', 'tangent1', 'tangent2', 'mvs_p']}
    result = {}
    for rep in reps:
        if rep['unit'] != unit or rep['selection'] is None: continue
        ids = np.flatnonzero(np.isin(d['point_id'], rep['selection']['point_ids']))
        c, n, a, b, m = [d[k][ids] for k in ['centre', 'normal', 'tangent1', 'tangent2', 'mvs_p']]
        offsets = np.array([[-.25, -.25], [.25, -.25], [.25, .25], [-.25, .25]])
        corners = c[:, None] + a[:, None] * offsets[None, :, :1] + b[:, None] * offsets[None, :, 1:]
        points = np.concatenate([corners.reshape(-1, 3), (corners + n[:, None] * m[:, None, None]).reshape(-1, 3)])
        ranks = []
        for cam in cams:
            uv, depth = project(points, cam); uv -= .5
            direction = cam['position'] - c.mean(0); direction /= np.linalg.norm(direction)
            if np.dot(direction, n.mean(0)) <= 0 or not (depth > .01).all() or not np.isfinite(uv).all(): continue
            lo, hi = uv.min(0), uv.max(0)
            if (lo < 0).any() or hi[0] >= cam['width'] or hi[1] >= cam['height']: continue
            poly = uv[:len(corners) * 4].reshape(-1, 4, 2)
            area = .5 * np.abs((poly[:, :, 0] * np.roll(poly[:, :, 1], -1, axis=1) -
                              poly[:, :, 1] * np.roll(poly[:, :, 0], -1, axis=1)).sum(1)).sum()
            centre = (lo + hi) / 2; half = np.maximum((hi - lo) / 2 + 24, 64)
            crop = [max(0, int(centre[0] - half[0])), max(0, int(centre[1] - half[1])),
                    min(cam['width'], int(np.ceil(centre[0] + half[0]))),
                    min(cam['height'], int(np.ceil(centre[1] + half[1])))]
            ranks.append(dict(view=cam['name'], projected_area_px=float(area), crop=crop, direction=direction.tolist()))
        ranks.sort(key=lambda x: (-x['projected_area_px'], x['view']))
        chosen = []
        for row in ranks:
            if all(np.dot(row['direction'], old['direction']) < np.cos(np.deg2rad(10)) for old in chosen):
                chosen.append(row)
            if len(chosen) == 3: break
        for row in ranks:
            if len(chosen) == 3: break
            if row['view'] not in [x['view'] for x in chosen]: chosen.append(row)
        result[rep['id']] = dict(views=chosen, available=len(chosen),
            rule='Largest projected prior-cell area in training photos, all candidate corners inside image, outward facing; prefer 10 degree view separation; no results used.')
    return result


def run(unit):
    root = Path('/out/render_masks') / unit; root.mkdir(parents=True, exist_ok=False)
    scene = Scene(unit)
    masks, rows = [], []
    with torch.no_grad():
        for index, cam in enumerate(scene.cams):
            alpha = rasterization_2dgs(**scene.geometry,
                opacities=torch.ones(len(scene.opacity), device='cuda'),
                colors=torch.zeros((len(scene.opacity), 3), device='cuda'),
                viewmats=tensor(cam['E'])[None], Ks=tensor(cam['K'])[None],
                width=cam['width'], height=cam['height'], render_mode='RGB', packed=False,
                sh_degree=None, near_plane=.01, backgrounds=None)[1][0, ..., 0]
            mask = (alpha > 0).cpu().numpy()
            masks.append(np.packbits(mask.ravel()))
            rows.append(dict(name=cam['name'], width=cam['width'], height=cam['height'], pixels=int(mask.sum())))
            if index % 100 == 0: print(unit, 'fixed masks', index + 1, '/', len(scene.cams), flush=True)
    assert len({(x['width'], x['height']) for x in rows}) == 1
    np.savez_compressed(root / 'masks.npz', packed_masks=np.stack(masks))
    monitor = [r['name'] for r in sorted(rows, key=lambda x: (-x['pixels'], x['name']))[:5]]
    report = dict(task_id='PHD-MAIN-CANDPICK-v1', unit=unit,
        at=datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),
        mask_rule='Candidate-only gsplat alpha>0 with both candidate opacities exactly 1, fixed geometry and native pixel filter; frozen for all arms and iterations.',
        views=rows, mask_file=bind(root / 'masks.npz'),
        error_monitor_views=monitor, psnr_monitor_views=[c['name'] for c in scene.cams[:5]],
        representative_views=representative_views(unit, scene.cams), optimizer_steps=0, scientific_verdict=None)
    save(root / 'index.json', report)
    save(Path('/docs/render_masks') / (unit + '.json'), report)


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('units', nargs='+'); args = p.parse_args()
    for unit in args.units: run(unit)
