"""Native point membership and bounded local plane hypotheses; no reference inputs."""
from __future__ import annotations

import cv2
import numpy as np


def cell_membership(xyz, domain, spacing):
    lo = np.array([domain[k][0] for k in 'xyz'])
    hi = np.array([domain[k][1] for k in 'xyz'])
    shape = np.ceil((hi[:2] - lo[:2]) / spacing).astype(int)
    inside = np.isfinite(xyz).all(1) & (xyz >= lo).all(1) & (xyz < hi).all(1)
    index = np.floor((xyz[:, :2] - lo[:2]) / spacing).astype(np.int64)
    ids = index[:, 1] * shape[0] + index[:, 0]
    return np.where(inside, ids, -1), shape


def _fit(points):
    center = np.mean(points, axis=0)
    _, values, vectors = np.linalg.svd(points - center, full_matrices=False)
    return center, vectors[-1], values


def fit_candidate(points, up, config):
    """Fit deterministic dominant local plane, retaining native inlier membership.

    Robust fitting is a representation adapter, NOT evidence of source currentness.
    Mixed/linear/sparse cells remain represented in the census but are inadmissible.
    """
    points = np.asarray(points, np.float64)
    count = len(points)
    result = dict(valid=False, reason='SPARSE', count=count, center=None, normal=None,
                  inlier_count=0, inlier_fraction=0.0, rms_m=None, p90_m=None,
                  extent_m=None, second_singular_value_m=None)
    mask = np.zeros(count, bool)
    if count < config['min_points']:
        return result, mask
    # Deterministic input ordering and subsampling; independent of images/UAS.
    order = np.lexsort((points[:, 2], points[:, 1], points[:, 0]))
    sampled = points[order[np.linspace(0, count-1, min(count, config['fit_cap']), dtype=int)]]
    center, normal, values = _fit(sampled)
    residual = np.abs((sampled-center) @ normal)
    best = residual <= config['inlier_distance_m']
    best_key = (int(best.sum()), -float(np.median(residual)))
    rng = np.random.default_rng(config['seed'])
    for _ in range(config['ransac_trials']):
        a, b, c = sampled[rng.choice(len(sampled), 3, replace=False)]
        n = np.cross(b-a, c-a)
        length = np.linalg.norm(n)
        if length < 1e-8:
            continue
        n /= length
        dist = np.abs((sampled-a) @ n)
        support = dist <= config['inlier_distance_m']
        key = (int(support.sum()), -float(np.median(dist)))
        if key > best_key:
            best, best_key = support, key
    if best.sum() < 3:
        return result, mask
    center, normal, values = _fit(sampled[best])
    for _ in range(3):
        mask = np.abs((points-center) @ normal) <= config['inlier_distance_m']
        if mask.sum() < 3:
            break
        center, normal, values = _fit(points[mask])
    if normal @ up < 0:
        normal = -normal
    residual = np.abs((points-center) @ normal)
    mask = residual <= config['inlier_distance_m']
    span = np.sqrt(np.maximum(values * values / max(mask.sum()-1, 1), 0))
    fraction = float(mask.mean())
    valid = bool(mask.sum() >= config['min_points'] and fraction >= config['minimum_inlier_fraction']
                 and span[1] >= config['minimum_second_spread_m'])
    reason = 'OK' if valid else ('MIXED_OR_NONPLANAR' if fraction < config['minimum_inlier_fraction'] else 'LINEAR_OR_SPARSE')
    result.update(valid=valid, reason=reason, center=center.tolist(), normal=normal.tolist(),
                  inlier_count=int(mask.sum()), inlier_fraction=fraction,
                  rms_m=float(np.sqrt(np.mean(residual[mask]**2))) if mask.any() else None,
                  p90_m=float(np.quantile(residual, .9)), extent_m=np.ptp(points, axis=0).tolist(),
                  second_singular_value_m=float(span[1]))
    return result, mask


def build_candidates(native, domain, up, config):
    spacing = config['cell_m']
    membership, shape = {}, None
    inliers = {}
    for source in ('mvs', 'als'):
        membership[source], shape = cell_membership(native[source + '_xyz'], domain, spacing)
        if (membership[source] < 0).any():
            raise ValueError('Native input escaped the frozen half-open region prism')
        inliers[source] = np.zeros(len(membership[source]), bool)
    rows = []
    for cell_id in range(int(np.prod(shape))):
        ix, iy = cell_id % int(shape[0]), cell_id // int(shape[0])
        xmin = domain['x'][0] + ix*spacing
        ymin = domain['y'][0] + iy*spacing
        xmax = min(domain['x'][1], xmin+spacing)
        ymax = min(domain['y'][1], ymin+spacing)
        row = dict(cell_id=cell_id, ix=ix, iy=iy, x=(xmin+xmax)/2, y=(ymin+ymax)/2,
                   bbox_xy=[xmin, ymin, xmax, ymax], area_m2=(xmax-xmin)*(ymax-ymin), candidates={})
        for source in ('mvs', 'als'):
            indices = np.flatnonzero(membership[source] == cell_id)
            candidate, keep = fit_candidate(native[source+'_xyz'][indices], up, config)
            candidate['native_row_count'] = len(indices)
            inliers[source][indices[keep]] = True
            row['candidates'][source] = candidate
        m, p = [row['candidates'][s] for s in ('mvs', 'als')]
        row['availability'] = ('BOTH' if m['count'] and p['count'] else
                               'MVS_ONLY' if m['count'] else 'ALS_ONLY' if p['count'] else 'NONE')
        row['both_valid'] = bool(m['valid'] and p['valid'])
        row['height_difference_m'] = float(np.asarray(m['center']) @ up - np.asarray(p['center']) @ up) if m['center'] and p['center'] else None
        row['normal_difference_deg'] = float(np.rad2deg(np.arccos(np.clip(abs(np.dot(m['normal'], p['normal'])), 0, 1)))) if m['normal'] and p['normal'] else None
        rows.append(row)
    return rows, dict(**{s+'_cell': membership[s] for s in membership},
                      **{s+'_inlier': inliers[s] for s in inliers})


def self_depth_buffer(points, view, downsample=4, splat_radius=1):
    """Own-source local visibility hypothesis; no measured free-space claim.

    No averaging, nearest-depth point splats, fixed radius; missing pixels stay NaN.
    This diagnostic raster is not the candidate geometry or evaluation surface.
    """
    h, w = (view['height']+downsample-1)//downsample, (view['width']+downsample-1)//downsample
    cam = points @ view['R'].T + view['t']
    visible = cam[:, 2] > 0
    cam = cam[visible]
    uvh = cam @ view['K'].T
    uv = np.floor((uvh[:, :2]/uvh[:, 2:] + .5)/downsample).astype(int)
    good = (uv[:, 0] >= 0) & (uv[:, 0] < w) & (uv[:, 1] >= 0) & (uv[:, 1] < h)
    depth = np.full(h*w, np.inf, np.float32)
    np.minimum.at(depth, uv[good, 1]*w+uv[good, 0], cam[good, 2].astype(np.float32))
    depth = depth.reshape(h, w)
    if splat_radius:
        kernel = np.ones((2*splat_radius+1, 2*splat_radius+1), np.uint8)
        depth = cv2.erode(depth, kernel)
    depth[~np.isfinite(depth)] = np.nan
    return dict(depth=depth, scale_x=1/downsample, scale_y=1/downsample)
