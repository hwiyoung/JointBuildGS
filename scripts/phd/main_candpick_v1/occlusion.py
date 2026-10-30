"""Background transmittance before each candidate plane in all train images.

Uses the frozen gsplat projection/tile lists and exactly its alpha kernel. The
additional depth cut is a diagnostic query, never a rendering/training change.
"""
import json
import sys
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import cv2
import numpy as np
import torch
from torch.utils.cpp_extension import load_inline
from gs_engine import Scene, tensor, project
from input_audit import sha
from prepare_places import save


def extension():
    code = Path(__file__).with_suffix('.cu')
    declaration = 'torch::Tensor cand_transmittance(torch::Tensor, torch::Tensor, torch::Tensor, torch::Tensor, torch::Tensor, torch::Tensor, int64_t, int64_t);'
    return load_inline(name='candpick_occlusion_' + sha(code)[:12], cpp_sources=declaration,
                       cuda_sources=code.read_text(), functions=['cand_transmittance'],
                       extra_cuda_cflags=['--use_fast_math'], verbose=False)


def queries(d, cam):
    p = len(d['centre']); corners = np.array([[-.25, -.25], [.25, -.25], [.25, .25], [-.25, .25]])
    shifts = d['tangent1'][:, None] * corners[None, :, :1] + d['tangent2'][:, None] * corners[None, :, 1:]
    groups, values = [], []
    facing = np.sum((cam['position'] - d['centre']) * d['normal'], 1) > 0
    invK = np.linalg.inv(cam['K'])
    for candidate in range(2):
        c = d['centre'] + d['normal'] * (d['mvs_p'][:, None] if candidate else 0)
        uv, depth = project((c[:, None] + shifts).reshape(-1, 3), cam)
        uv = uv.reshape(p, 4, 2) - .5; depth = depth.reshape(p, 4)
        for i in np.flatnonzero(facing & (depth > .01).all(1) & np.isfinite(uv).all((1, 2))):
            lo = np.maximum(np.floor(uv[i].min(0)).astype(int), 0)
            hi = np.minimum(np.ceil(uv[i].max(0)).astype(int), [cam['width'] - 1, cam['height'] - 1])
            if (hi < lo).any(): continue
            mask = np.zeros((hi[1] - lo[1] + 1, hi[0] - lo[0] + 1), np.uint8)
            cv2.fillConvexPoly(mask, np.rint((uv[i] - lo) * 256).astype(np.int32), 1, shift=8)
            y, x = np.nonzero(mask); pixels = np.column_stack([x + lo[0] + .5, y + lo[1] + .5])
            ray = np.column_stack([pixels, np.ones(len(x))]) @ invK.T @ cam['E'][:3, :3]
            denominator = ray @ d['normal'][i]
            with np.errstate(divide='ignore', invalid='ignore'):
                z = np.dot(c[i] - cam['position'], d['normal'][i]) / denominator
            valid = np.isfinite(z) & (z > .01)
            values.append(np.column_stack([pixels[valid], z[valid]]).astype(np.float32))
            groups.append(np.full(int(valid.sum()), i * 2 + candidate, np.int32))
    if not values: return np.empty((0, 3), np.float32), np.empty(0, np.int32)
    return np.concatenate(values), np.concatenate(groups)


def run(unit, ext):
    folder = Path('/out/occlusion') / unit; folder.mkdir(parents=True, exist_ok=False)
    with np.load(Path('/out/places') / (unit + '.npz')) as z:
        d = {k: z[k] for k in ['point_id', 'centre', 'normal', 'tangent1', 'tangent2', 'mvs_p']}
    scene = Scene(unit); total = np.zeros(len(d['centre']) * 2, np.int64); blocked = total.copy()
    view_count = total.copy(); checks = []; views = []
    for index, cam in enumerate(scene.cams):
        with torch.no_grad():
            result = scene.render(cam, background_only=True)
            meta = result[-1]
            args = [meta[k].contiguous() for k in ['means2d', 'ray_transforms', 'opacities', 'isect_offsets', 'flatten_ids']]
            q, owner = queries(d, cam)
            if index < 5:
                # Validate the complete alpha compositing against the native
                # renderer before applying a finite candidate-depth cutoff.
                rng = np.random.default_rng(index)
                ids = rng.choice(cam['width'] * cam['height'], 2048, replace=False)
                samples = np.column_stack([ids % cam['width'] + .5, ids // cam['width'] + .5, np.full(len(ids), np.inf)])
                t = ext.cand_transmittance(*args, tensor(samples), meta['tile_width'], meta['tile_height']).cpu().numpy()
                reference = 1 - result[1][0, ..., 0].flatten()[torch.as_tensor(ids, device='cuda')].cpu().numpy()
                error = float(np.max(np.abs(t - reference)))
                checks.append(dict(view=cam['name'], pixels=len(ids), maximum_alpha_difference=error))
                assert error <= 2e-5, f'alpha reference mismatch {error}'
            t = ext.cand_transmittance(*args, tensor(q), meta['tile_width'], meta['tile_height']).cpu().numpy()
            assert np.isfinite(t).all()
            total += np.bincount(owner, minlength=len(total))
            blocked += np.bincount(owner[t < .5], minlength=len(total))
            view_count[np.unique(owner)] += 1
        views.append(dict(name=cam['name'], candidate_pixels=len(q), occluded_pixels=int((t < .5).sum())))
        if index % 20 == 0: print(unit, 'occlusion', index + 1, '/', len(scene.cams), flush=True)
        del result, meta, args
    total = total.reshape(-1, 2); blocked = blocked.reshape(-1, 2)
    ratio = np.divide(blocked.sum(1), total.sum(1), out=np.full(len(total), np.nan), where=total.sum(1) > 0)
    np.savez_compressed(folder / 'points.npz', point_id=d['point_id'], observed_pixels=total,
        occluded_pixels=blocked, train_views=view_count.reshape(-1, 2), occluded_fraction=ratio,
        over_30pct=np.isfinite(ratio) & (ratio > .3))
    report = dict(unit=unit, at=datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),
        status='PASS', train_views=len(scene.cams), points=len(total), unavailable_points=int(np.isnan(ratio).sum()),
        points_over_30pct=int((ratio > .3).sum()),
        rule='Pool pixel observations across all train views and both 50cm candidate sheets; count native background alpha product before ray-plane candidate depth <0.5. Per-candidate counts retained.',
        visibility='on-image, positive depth, outward normal facing camera; background occlusion is measured rather than filtered',
        alpha_reference_checks=checks, views=views, payload_sha256=sha(folder / 'points.npz'),
        code_sha256={name: sha(Path(__file__).with_name(name)) for name in ['occlusion.py', 'occlusion.cu']},
        GT_used=False, optimizer_steps=0, scientific_verdict=None)
    save(folder / 'receipt.json', report); save(Path('/docs/occlusion') / (unit + '.json'), report)


if __name__ == '__main__':
    ext = extension()
    for unit in sys.argv[1:]: run(unit, ext)
