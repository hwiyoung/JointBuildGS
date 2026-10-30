"""No optimizer: real-scene exterior identity and gradient-isolation checks.

The geometric 50cm cell mask and actual splat support are measured separately.
An actual support mask must never silently replace the user's place boundary.
"""
import argparse
import json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import cv2
import numpy as np
import torch
from PIL import Image
from gs_engine import Scene, photo, project
from input_audit import sha
from prepare_places import save


def cell_mask(unit, cam):
    with np.load(Path('/out/places') / (unit + '.npz')) as z:
        c, a, b, n, m = [z[k] for k in ['centre', 'tangent1', 'tangent2', 'normal', 'mvs_p']]
    offsets = np.array([[-.25, -.25], [.25, -.25], [.25, .25], [-.25, .25]])
    corners = c[:, None] + a[:, None] * offsets[None, :, :1] + b[:, None] * offsets[None, :, 1:]
    mask = np.zeros((cam['height'], cam['width']), np.uint8)
    for heights in [np.zeros_like(m), m]:
        uv, depth = project((corners + n[:, None] * heights[:, None, None]).reshape(-1, 3), cam)
        uv = uv.reshape(-1, 4, 2) - .5; depth = depth.reshape(-1, 4)
        valid = np.isfinite(uv).all((1, 2)) & (depth > .01).all(1)
        for polygon in uv[valid]:
            if polygon[:, 0].max() < 0 or polygon[:, 1].max() < 0 or polygon[:, 0].min() >= cam['width'] or polygon[:, 1].min() >= cam['height']:
                continue
            # Fixed-point rasterization; mask includes boundary-touched pixels.
            cv2.fillConvexPoly(mask, np.rint(polygon * 256).astype(np.int32), 1, shift=8)
    return mask.astype(bool)


def psnr(a, b, mask):
    if not mask.any(): return None
    mse = float(np.mean((a[mask].astype(float) - b[mask])**2))
    return None if mse == 0 else float(-10 * np.log10(mse))


def png(path, image):
    Image.fromarray(np.rint(np.clip(image, 0, 1) * 255).astype(np.uint8)).save(path)


def run(unit, full_views=False):
    suffix = '_all_views' if full_views else ''
    dest = Path('/out/preflight') / (unit + suffix); dest.mkdir(parents=True, exist_ok=False)
    scene = Scene(unit, start='wrong', sh_degree=3)
    rows = []
    gradient_camera = None
    for index, cam in enumerate(scene.cams if full_views else scene.cams[:5]):
        with torch.no_grad():
            base = scene.render(cam, background_only=True)[0][0].cpu().numpy()
            full = scene.render(cam)[0][0].cpu().numpy()
            candidate = scene.render(cam, candidates_only=True)[1][0, ..., 0].cpu().numpy()
        mask = cell_mask(unit, cam)
        delta = np.max(np.abs(full - base), axis=2)
        outside = ~mask; beyond_splat = candidate == 0
        target = photo(cam).astype(float) / 255.
        pbase, pfull = psnr(base, target, outside), psnr(full, target, outside)
        row = dict(view=cam['name'], outside_pixels=int(outside.sum()),
            changed_outside_pixels=int((outside & (delta != 0)).sum()),
            max_abs_outside_rgb=float(delta[outside].max()) if outside.any() else None,
            outside_identity_psnr_db=psnr(full, base, outside),
            outside_photo_psnr_before_db=pbase, outside_photo_psnr_after_db=pfull,
            outside_photo_psnr_delta_db=pfull - pbase if pfull is not None and pbase is not None else None,
            changed_beyond_actual_splat_support=int((beyond_splat & (delta != 0)).sum()),
            splat_support_outside_cell_pixels=int((outside & (candidate > 0)).sum()),
            status='PASS' if not (outside & (delta != 0)).any() else 'FAIL_OUTSIDE_CELL_CHANGED')
        rows.append(row)
        if gradient_camera is None and (candidate > 0).any(): gradient_camera = cam
        if index < 5:
            png(dest / (cam['name'] + '_photo.png'), target)
            png(dest / (cam['name'] + '_background.png'), base)
            png(dest / (cam['name'] + '_candidates.png'), full)
            heat = np.zeros_like(full); heat[outside & (delta > 0)] = [1, 0, 0]; heat[mask] = [.2, .2, .2]
            png(dest / (cam['name'] + '_outside_changes.png'), heat)
        if index < 5 or index % 20 == 0: print(unit, index + 1, row, flush=True)
    assert gradient_camera is not None, 'No candidate-visible training view in inspected set'
    cam = gradient_camera
    image = scene.render(cam)[0][0]
    loss = scene.loss(image, cam); loss.backward()
    frozen = {**{'base.' + k: v for k, v in scene.base.items()},
              **{'candidate.' + k: v for k, v in scene.geometry.items()}}
    fixed_checks = {k: dict(requires_grad=v.requires_grad, grad_is_none=v.grad is None,
        gradient_max_abs=0. if v.grad is None else float(v.grad.abs().max())) for k, v in frozen.items()}
    trainable_checks = {k: dict(grad_exists=v.grad is not None,
        grad_finite=bool(torch.isfinite(v.grad).all()) if v.grad is not None else False,
        nonzero=int(torch.count_nonzero(v.grad)) if v.grad is not None else 0)
        for k, v in [('opacity', scene.opacity), ('color_dc', scene.dc), ('color_sh', scene.rest)]}
    gradients = (all(not x['requires_grad'] and x['gradient_max_abs'] == 0 for x in fixed_checks.values()) and
                 all(x['grad_exists'] and x['grad_finite'] and x['nonzero'] > 0 for x in trainable_checks.values()))
    report = dict(task_id='PHD-MAIN-CANDPICK-v1', unit=unit,
        at=datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),
        renderer='gsplat 1.4.0 rasterization_2dgs; unchanged background SH3 in both candidate color arms',
        status='PASS' if gradients and all(r['status'] == 'PASS' for r in rows) else 'STOP_PREFLIGHT',
        outside_scope='union of projected prior and MVS 50cm cells, boundary-touched pixels included; actual Gaussian support reported separately',
        tested_views=len(rows), total_train_views=len(scene.cams), outside=rows,
        strict_cell_status='PASS' if all(r['status'] == 'PASS' for r in rows) else 'FAIL',
        actual_support_status='PASS' if all(r['changed_beyond_actual_splat_support'] == 0 for r in rows) else 'FAIL',
        gradient_view=cam['name'],
        gradients=dict(status='PASS' if gradients else 'FAIL', frozen=fixed_checks, trainable=trainable_checks),
        optimizer_steps=0, scientific_verdict=None,
        source_sha256={p.name: sha(p) for p in Path(__file__).parent.glob('*.py')})
    save(dest / 'preflight.json', report)
    save(Path('/docs/preflight') / (unit + suffix + '.json'), report)
    print(unit, report['status'], 'gradient', gradients, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('units', nargs='+')
    parser.add_argument('--full-views', action='store_true'); args = parser.parse_args()
    for unit in args.units: run(unit, args.full_views)
