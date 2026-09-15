"""Manual input-surface annotations transferred by current MVS camera geometry.

Diagnostic draft only. No optimizer connection, calibrated confidence, GT labels,
depth filling, or prior-driven visibility. Integer native camera rays are retained.
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


def unproject(depth, K, R, t):
    yy, xx = np.indices(depth.shape, dtype=np.float64)
    rays = np.stack((xx, yy, np.ones_like(xx)), -1) @ np.linalg.inv(K).T
    valid = np.isfinite(depth) & (depth > 0)
    xyz = (rays * np.where(valid, depth, 0)[..., None] - np.asarray(t)) @ np.asarray(R)
    return np.where(valid[..., None], xyz, np.nan)


def project(xyz, K, R, t):
    camera = np.asarray(xyz) @ np.asarray(R).T + np.asarray(t)
    pixels = camera @ np.asarray(K).T
    good = np.isfinite(camera).all(-1) & (camera[..., 2] > 0)
    uv = np.full(camera.shape[:-1] + (2,), np.nan)
    np.divide(pixels[..., :2], pixels[..., 2:3], out=uv, where=good[..., None])
    return uv, camera[..., 2], good


def nearest_indices(uv, shape):
    finite = np.isfinite(uv).all(-1)
    clean = np.where(finite[..., None], uv, 0)
    idx = np.floor(clean + .5).astype(np.int64)
    x, y = idx[..., 0], idx[..., 1]
    inside = finite & (x >= 0) & (y >= 0) & (x < shape[1]) & (y < shape[0])
    return np.clip(y, 0, shape[0]-1), np.clip(x, 0, shape[1]-1), inside


def resample_nearest(values, source_K, target_K, width, height, outside=0):
    yy, xx = np.indices((height, width), dtype=np.float64)
    uvw = np.stack((xx, yy, np.ones_like(xx)), -1) @ (np.asarray(source_K) @ np.linalg.inv(target_K)).T
    iy, ix, good = nearest_indices(uvw[..., :2] / uvw[..., 2:3], values.shape)
    values = values[iy, ix]
    # An integer outside=0 must not promote a boolean mask to int64; ~mask
    # would then become negative integer indexing rather than logical negation.
    fill = np.asarray(outside, dtype=values.dtype)
    return np.where(good[..., None] if values.ndim == 3 else good, values, fill)


def polygon_mask(width, height, polygons, default=5):
    canvas = Image.new('L', (width, height), default)
    draw = ImageDraw.Draw(canvas)
    for item in polygons:
        points = item['xy']
        if len(points) < 3 or not all(0 <= x <= width and 0 <= y <= height for x, y in points):
            raise ValueError('Invalid full-RGB polygon')
        draw.polygon([tuple(p) for p in points], fill=int(item['region']))
    return np.asarray(canvas).copy()


def boundary_band(labels, radius):
    edge = np.zeros(labels.shape, dtype=bool)
    edge[:, 1:] |= labels[:, 1:] != labels[:, :-1]
    edge[:, :-1] |= labels[:, 1:] != labels[:, :-1]
    edge[1:, :] |= labels[1:, :] != labels[:-1, :]
    edge[:-1, :] |= labels[1:, :] != labels[:-1, :]
    if radius:
        edge = np.asarray(Image.fromarray(edge.astype('uint8') * 255).filter(ImageFilter.MaxFilter(2*radius+1))) > 0
    return edge


def depth_edges(depth, radius, threshold):
    valid = np.isfinite(depth) & (depth > 0)
    edge = boundary_band(valid, 0)
    d = np.where(valid, depth, 0)
    horizontal = valid[:, 1:] & valid[:, :-1] & (np.abs(d[:, 1:] - d[:, :-1]) > threshold)
    vertical = valid[1:] & valid[:-1] & (np.abs(d[1:] - d[:-1]) > threshold)
    edge[:, 1:] |= horizontal; edge[:, :-1] |= horizontal
    edge[1:] |= vertical; edge[:-1] |= vertical
    if radius:
        edge = np.asarray(Image.fromarray(edge.astype('uint8')*255).filter(ImageFilter.MaxFilter(2*radius+1))) > 0
    return edge


def correspondence(target_xyz, target_view, source, tolerance_m, roundtrip_px):
    """Reject depth disagreement/occlusion and excessive bidirectional reprojection.

    The tolerances are diagnostic parameters, not noise calibration.
    """
    sv = source['view']
    uv, z, in_front = project(target_xyz, sv['maps']['depth']['K'], sv['R'], sv['t'])
    sy, sx, inside = nearest_indices(uv, source['depth'].shape)
    sd = source['depth'][sy, sx]
    good = in_front & inside & np.isfinite(sd) & (sd > 0) & (np.abs(sd-z) <= tolerance_m)
    back_uv, _, front_back = project(source['xyz'][sy, sx], target_view['maps']['depth']['K'], target_view['R'], target_view['t'])
    yy, xx = np.indices(target_xyz.shape[:2])
    distance = np.hypot(back_uv[..., 0]-xx, back_uv[..., 1]-yy)
    good &= front_back & np.isfinite(distance) & (distance <= roundtrip_px)
    return sy, sx, good


def make_regions(depth, view, sources, cfg):
    xyz = unproject(depth, np.asarray(view['maps']['depth']['K']), view['R'], view['t'])
    valid = np.isfinite(depth) & (depth > 0)
    inside = valid.copy()
    for axis, key in enumerate(('x', 'y', 'z')):
        lo, hi = cfg['training_context'][key]
        inside &= (xyz[..., axis] >= lo) & (xyz[..., axis] <= hi)
    # Separate reasons even when their numerical multiplier is zero.
    labels = np.full(depth.shape, 5, dtype=np.uint8)
    building = np.zeros(depth.shape, np.uint8)
    ground = np.zeros(depth.shape, np.uint8)
    veto = np.zeros(depth.shape, bool)
    candidate = np.zeros(depth.shape, bool)
    local = None
    for source in sources:
        sy, sx, accepted = correspondence(xyz, view, source, cfg['depth_match_m'], cfg['roundtrip_native_px'])
        accepted &= inside
        sl = source['labels'][sy, sx]
        building += (accepted & (sl == 2)).astype(np.uint8)
        ground += (accepted & (sl == 3)).astype(np.uint8)
        veto |= accepted & (sl == 4)
        if source.get('candidate') is not None:
            candidate |= accepted & source['candidate'][sy, sx]
        if source['view']['name'] == view['name']:
            local = source
    conflict = (building > 0) & (ground > 0)
    labels[(building > 0) & (ground == 0) & ~veto] = 2
    labels[(ground > 0) & (building == 0) & ~veto] = 3
    if local is not None:
        # A manually inspected camera keeps its own labels; cross-view conflicts
        # remain recorded separately for review.
        labels[inside] = local['labels'][inside]
        if local.get('candidate') is not None:
            candidate[inside] = local['candidate'][inside]
    # P1 interventions concern current ground. Roof/facade experiments must
    # explicitly opt in to building surfaces; unknown/excluded never promote.
    base_regions = cfg.get('intervention_base_regions', [3])
    if not base_regions or not set(base_regions).issubset({2, 3}):
        raise ValueError('Intervention base regions must be building and/or ground')
    labels[np.isin(labels, base_regions) & candidate & inside] = 1
    boundaries = boundary_band(labels, cfg['target_boundary_native_px'])
    boundaries |= depth_edges(depth, cfg['depth_edge_native_px'], cfg['depth_edge_m'])
    labels[boundaries & inside & (labels != 4)] = 5
    labels[valid & ~inside] = 6
    labels[~valid] = 5
    weights = np.zeros(depth.shape, np.float32)
    weights[(labels == 2) | (labels == 3)] = 1
    weights[labels == 1] = cfg['display_alpha']
    weights[~valid] = 0
    return {'region_id': labels, 'valid': valid, 'inside_context': inside,
            'weight': weights, 'building_votes': building, 'ground_votes': ground,
            'cross_view_conflict': conflict & inside, 'exclusion_veto': veto & inside,
            'candidate_support': candidate & inside, 'boundary': boundaries & inside}
