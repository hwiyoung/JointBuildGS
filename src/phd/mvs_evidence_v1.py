"""CPU observation diagnostics; no source weights, GT, or training decisions.

Camera depths are camera Z, not Euclidean ray lengths. Poses are world-to-camera.
The visibility statuses describe compatibility with the named neighbor model;
neither model self-consistency nor cross-source compatibility proves visibility
of the actual scene. Photometric comparison does not use either visibility gate.
"""
from __future__ import annotations

import numpy as np


VISIBILITY_LABELS = {
    0: 'INVALID_REFERENCE', 1: 'OUT_OF_FRAME_OR_BEHIND_CAMERA',
    2: 'MISSING_NEIGHBOR_DEPTH', 3: 'DEPTH_COMPATIBLE',
    4: 'BEHIND_OBSERVED_MODEL', 5: 'IN_FRONT_OF_OBSERVED_MODEL',
}


def _camera(view):
    K, R, t = (np.asarray(view[k], dtype=np.float64) for k in ('K', 'R', 't'))
    if K.shape != (3, 3) or R.shape != (3, 3) or t.shape != (3,):
        raise ValueError('Expected 3x3 K/R and three-vector t')
    if not all(np.isfinite(x).all() for x in (K, R, t)):
        raise ValueError('Nonfinite camera')
    if not np.allclose(K[2], [0, 0, 1], atol=1e-12, rtol=0) or np.linalg.det(K) <= 0:
        raise ValueError('Expected pinhole intrinsics')
    if not np.allclose(R @ R.T, np.eye(3), atol=1e-6, rtol=0) or np.linalg.det(R) <= 0:
        raise ValueError('Expected proper orthonormal world-to-camera rotation')
    return K, R, t


def _rays(uv, K):
    return np.concatenate((uv, np.ones(uv.shape[:-1] + (1,))), axis=-1) @ np.linalg.inv(K).T


def project(uv, depth, ref, neighbor):
    """Project matching-shaped UV/camera-Z arrays, retaining NaNs as missing."""
    uv, depth = np.asarray(uv, float), np.asarray(depth, float)
    if uv.shape != depth.shape + (2,):
        raise ValueError('UV shape must equal depth shape plus two coordinates')
    K, R, t = _camera(ref)
    Kn, Rn, tn = _camera(neighbor)
    valid = np.isfinite(uv).all(-1) & np.isfinite(depth) & (depth > 0)
    safe_uv = np.where(valid[..., None], uv, 0.)
    camera = _rays(safe_uv, K) * np.where(valid, depth, 0.)[..., None]
    world = (camera - t) @ R
    other = world @ Rn.T + tn
    homogeneous = other @ Kn.T
    projected = np.full(uv.shape, np.nan)
    denominator_ok = valid & np.isfinite(other).all(-1) & (np.abs(other[..., 2]) > 1e-12)
    np.divide(homogeneous[..., :2], homogeneous[..., 2:3], out=projected,
              where=denominator_ok[..., None])
    return projected, np.where(valid, other[..., 2], np.nan), np.where(valid[..., None], world, np.nan)


def bilinear(array, uv, positive=False):
    """Sample a finite four-pixel stencil. Invalid support remains NaN/False.

    The conservative four-corner requirement also applies at integer locations;
    depth holes are never interpolated across, even with a zero corner weight.
    """
    array, uv = np.asarray(array, float), np.asarray(uv, float)
    if array.ndim not in (2, 3) or min(array.shape[:2]) < 1 or uv.shape[-1] != 2:
        raise ValueError('Expected HxW[/C] data and UV coordinates')
    h, w = array.shape[:2]
    finite = np.isfinite(uv).all(-1)
    safe = np.where(finite[..., None], uv, 0.)
    x, y = safe[..., 0], safe[..., 1]
    inside = finite & (x >= 0) & (x <= w-1) & (y >= 0) & (y <= h-1)
    # Clip before integer conversion so extreme out-of-frame values cannot overflow.
    cx, cy = np.clip(x, 0, w-1), np.clip(y, 0, h-1)
    x0, y0 = np.floor(cx).astype(np.int64), np.floor(cy).astype(np.int64)
    x1, y1 = np.minimum(x0+1, w-1), np.minimum(y0+1, h-1)
    a, b, c, d = array[y0, x0], array[y0, x1], array[y1, x0], array[y1, x1]
    good = np.isfinite(a) & np.isfinite(b) & np.isfinite(c) & np.isfinite(d)
    if positive:
        good &= (a > 0) & (b > 0) & (c > 0) & (d > 0)
    if array.ndim == 3:
        good = good.all(-1)
    mask = inside & good
    dx, dy = cx-x0, cy-y0
    if array.ndim == 3:
        dx, dy = dx[..., None], dy[..., None]
    # Invalid stencils are rejected below; avoid 0*inf warnings on those stencils.
    stencil = mask[..., None] if array.ndim == 3 else mask
    a, b, c, d = (np.where(stencil, corner, 0.) for corner in (a, b, c, d))
    result = (1-dx)*(1-dy)*a + dx*(1-dy)*b + (1-dx)*dy*c + dx*dy*d
    return np.where(mask[..., None] if array.ndim == 3 else mask, result, np.nan), mask


def sample_mvs(native, uv_rgb, view):
    """Nearest native COLMAP sample on the RGB ray, with unfilled holes."""
    native, uv = np.asarray(native), np.asarray(uv_rgb, float)
    if native.ndim != 2 or native.size == 0 or uv.shape[-1] != 2:
        raise ValueError('Expected native 2D depth and UV coordinates')
    K = np.asarray(view['K'], float)
    Kn = np.asarray(view['maps']['depth']['K'], float)
    finite = np.isfinite(uv).all(-1)
    safe = np.where(finite[..., None], uv, 0.)
    mapped = _rays(safe, K) @ Kn.T
    mapped = mapped[..., :2] / mapped[..., 2:3]
    h, w = native.shape
    ix = np.floor(np.clip(mapped[..., 0], -1., w) + .5).astype(np.int64)
    iy = np.floor(np.clip(mapped[..., 1], -1., h) + .5).astype(np.int64)
    inside = (finite & np.isfinite(mapped).all(-1) & (ix >= 0) & (ix < w) & (iy >= 0) & (iy < h)
              & (uv[..., 0] >= 0) & (uv[..., 0] <= view['width']-1)
              & (uv[..., 1] >= 0) & (uv[..., 1] <= view['height']-1))
    sampled = native[np.clip(iy, 0, h-1), np.clip(ix, 0, w-1)]
    valid = inside & np.isfinite(sampled) & (sampled > 0)
    return np.where(valid, sampled, np.nan), valid


def sample_prior(depth, uv):
    """Open3D prior samples occupy half-pixel rays; retain that convention."""
    return bilinear(depth, np.asarray(uv, float) - .5, positive=True)


def visibility(uv, depth, ref, nb, nb_mvs, tolerance_m, *, neighbor_kind='mvs'):
    """Model-conditioned depth ordering plus unthresholded roundtrip/parallax.

    Roundtrip reconstructs at the continuous projected RGB ray with the sampled
    depth. For nearest MVS this inherits a native-pixel sampling approximation.
    A small roundtrip error is not geometry validation at small/zero parallax.
    """
    if not np.isfinite(tolerance_m) or tolerance_m <= 0 or neighbor_kind not in ('mvs', 'prior'):
        raise ValueError('Positive metric tolerance and mvs/prior neighbor kind required')
    uv, depth = np.asarray(uv, float), np.asarray(depth, float)
    projected, z, world = project(uv, depth, ref, nb)
    valid = np.isfinite(depth) & (depth > 0) & np.isfinite(uv).all(-1)
    inside = (valid & np.isfinite(projected).all(-1) & (z > 0)
              & (projected[..., 0] >= 0) & (projected[..., 0] <= nb['width']-1)
              & (projected[..., 1] >= 0) & (projected[..., 1] <= nb['height']-1))
    sampled, neighbor_valid = (sample_mvs(nb_mvs, projected, nb) if neighbor_kind == 'mvs'
                               else sample_prior(nb_mvs, projected))
    known = inside & neighbor_valid
    residual = np.where(known, z-sampled, np.nan)
    status = np.zeros(depth.shape, dtype=np.uint8)
    status[valid & ~inside] = 1
    status[inside & ~neighbor_valid] = 2
    status[known] = 3
    status[known & (residual > tolerance_m)] = 4
    status[known & (residual < -tolerance_m)] = 5
    back, back_z, _ = project(projected, np.where(known, sampled, np.nan), nb, ref)
    roundtrip = np.where(known & (back_z > 0), np.linalg.norm(back-uv, axis=-1), np.nan)
    _, R, t = _camera(ref); _, Rn, tn = _camera(nb)
    ray1, ray2 = world - (-R.T @ t), world - (-Rn.T @ tn)
    norm = np.linalg.norm(ray1, axis=-1) * np.linalg.norm(ray2, axis=-1)
    cosine = np.full(depth.shape, np.nan)
    np.divide(np.sum(ray1*ray2, axis=-1), norm, out=cosine, where=valid & (norm > 1e-12))
    parallax = np.degrees(np.arccos(np.clip(cosine, -1, 1)))
    return dict(projected_uv=projected, predicted_neighbor_z=z, neighbor_depth=sampled,
                z_residual=residual, status=status, roundtrip_px=roundtrip, parallax_deg=parallax,
                conditioning='MVS_MODEL_CONDITIONED' if neighbor_kind == 'mvs' else 'PRIOR_MODEL_CONDITIONED',
                labels=VISIBILITY_LABELS.copy())


def _patch_geometry(centers, center_depth, ref, radius, normal=None, patch_depth=None):
    centers, center_depth = np.asarray(centers, float), np.asarray(center_depth, float)
    if centers.ndim != 2 or centers.shape[1] != 2 or center_depth.shape != (len(centers),):
        raise ValueError('Expected Nx2 centers and N center depths')
    if not isinstance(radius, (int, np.integer)) or radius < 1:
        raise ValueError('Positive integer patch radius required')
    axis = np.arange(-radius, radius+1, dtype=float)
    yy, xx = np.meshgrid(axis, axis, indexing='ij')
    offsets = np.stack((xx, yy), -1).reshape(-1, 2)
    uv = centers[:, None, :] + offsets
    if patch_depth is not None:
        depth = np.asarray(patch_depth, float)
        if depth.shape == (len(centers), 2*radius+1, 2*radius+1):
            depth = depth.reshape(len(centers), -1)
        if depth.shape != uv.shape[:-1]:
            raise ValueError('Raw patch depths must be NxP or NxHxW')
        if normal is not None:
            raise ValueError('Choose raw patch depth or plane normal, not both')
        # An available neighboring patch cannot fill its missing candidate center.
        middle = depth[:, len(offsets)//2]
        center_valid = np.isfinite(center_depth) & (center_depth > 0)
        if np.any(center_valid & (~np.isfinite(middle) | ~np.isclose(middle, center_depth, rtol=1e-7, atol=1e-7))):
            raise ValueError('Raw patch must retain its candidate center depth')
    elif normal is None:
        depth = np.broadcast_to(center_depth[:, None], uv.shape[:-1]).copy()
    else:
        normal = np.asarray(normal, float)
        if normal.shape != (len(centers), 3):
            raise ValueError('Expected Nx3 camera-frame normals')
        K, _, _ = _camera(ref)
        rays, central_ray = _rays(uv, K), _rays(centers, K)
        denom = np.sum(rays * normal[:, None], axis=-1)
        offset = center_depth * np.sum(central_ray*normal, axis=-1)
        depth = np.full(uv.shape[:-1], np.nan)
        np.divide(offset[:, None], denom, out=depth,
                  where=np.isfinite(denom) & (np.abs(denom) > 1e-10))
    center_ok = np.isfinite(center_depth) & (center_depth > 0) & np.isfinite(centers).all(-1)
    return uv, np.where(center_ok[:, None] & np.isfinite(depth) & (depth > 0), depth, np.nan)


def _gray(rgb):
    rgb = np.asarray(rgb, float)
    if rgb.ndim not in (2, 3) or (rgb.ndim == 3 and rgb.shape[-1] != 3):
        raise ValueError('Expected HxWx3 RGB or precomputed HxW grayscale in [0,1]')
    if np.any(np.isfinite(rgb) & ((rgb < 0) | (rgb > 1))):
        raise ValueError('RGB must use [0,1] for meaningful texture thresholds')
    return rgb if rgb.ndim == 2 else rgb @ np.array([.299, .587, .114])


def _warped(centers, depth, ref, nb, ref_rgb, nb_rgb, radius, normal=None, patch_depth=None):
    uv, depths = _patch_geometry(centers, depth, ref, radius, normal, patch_depth)
    target, z, _ = project(uv, depths, ref, nb)
    reference, ref_valid = bilinear(_gray(ref_rgb), uv)
    warped, target_valid = bilinear(_gray(nb_rgb), target)
    valid = ref_valid & target_valid & np.isfinite(depths) & (z > 0)
    return reference, warped, valid


def _cost(reference, warped, mask):
    n = mask.sum(-1)
    denominator = np.maximum(n, 1)
    ref_mean = np.where(mask, reference, 0).sum(-1) / denominator
    warped_mean = np.where(mask, warped, 0).sum(-1) / denominator
    a = np.where(mask, reference-ref_mean[:, None], 0)
    b = np.where(mask, warped-warped_mean[:, None], 0)
    va, vb = np.sum(a*a, axis=-1)/denominator, np.sum(b*b, axis=-1)/denominator
    sa, sb = np.sqrt(va), np.sqrt(vb)
    defined = (n >= 2) & (sa > 1e-12) & (sb > 1e-12)
    corr = np.full(len(n), np.nan)
    np.divide(np.sum(a*b, axis=-1)/denominator, sa*sb, out=corr, where=defined)
    costs = (1-np.clip(corr, -1, 1))/2
    return costs, np.where(n > 0, sa, np.nan), np.where(n > 0, sb, np.nan)


def batched_patch_cost(centers, center_depth, ref, nb, ref_rgb, nb_rgb, radius, normal=None,
                       *, patch_depth=None):
    """Return cost, minimum reference/warp texture std, projectable fraction.

    Without raw depths or a normal this is a constant-camera-Z plane diagnostic.
    No cost threshold or neighbor-model visibility is applied.
    """
    reference, warped, valid = _warped(centers, center_depth, ref, nb, ref_rgb, nb_rgb, radius, normal, patch_depth)
    cost, a, b = _cost(reference, warped, valid)
    return cost, np.minimum(a, b), valid.mean(-1)


def pair_patch_cost(centers, prior_depth, mvs_depth, ref, nb, ref_rgb, nb_rgb, radius,
                    *, prior_patch_depth=None, mvs_patch_depth=None,
                    prior_normal=None, mvs_normal=None, minimum_fraction=.8, texture_std=.02):
    """Compare source hypotheses on identical per-pixel and texture support.

    Ordering is [prior, mvs], but swapping all source inputs swaps only columns.
    Failed texture/support admission removes BOTH comparison costs. Raw costs and
    exact common counts remain available; missing/flat is NaN, never zero cost.
    Cross-source visibility is deliberately absent from the comparison mask.
    """
    if not 0 <= minimum_fraction <= 1 or not np.isfinite(texture_std) or texture_std < 0:
        raise ValueError('Invalid diagnostic support/texture thresholds')
    p = _warped(centers, prior_depth, ref, nb, ref_rgb, nb_rgb, radius, prior_normal, prior_patch_depth)
    m = _warped(centers, mvs_depth, ref, nb, ref_rgb, nb_rgb, radius, mvs_normal, mvs_patch_depth)
    common = p[2] & m[2]
    pc, pra, pwa = _cost(p[0], p[1], common)
    mc, mra, mwa = _cost(m[0], m[1], common)
    raw = np.stack((pc, mc), -1)
    texture = np.stack((np.stack((pra, pwa), -1), np.stack((mra, mwa), -1)), axis=1)
    count = common.sum(-1)
    fraction = common.mean(-1)
    eligible = (np.isfinite(raw).all(-1) & (fraction >= minimum_fraction)
                & (texture >= texture_std).all(axis=(1, 2)))
    return dict(costs=np.where(eligible[:, None], raw, np.nan), raw_costs=raw,
                common_count=count, common_fraction=fraction, texture_std=texture,
                eligible=eligible, common_mask=common,
                geometry_model=('RAW_SOURCE_DEPTH' if prior_patch_depth is not None else
                                'CENTER_ANCHORED_PLANE' if prior_normal is not None else 'CONSTANT_CAMERA_Z',
                                'RAW_SOURCE_DEPTH' if mvs_patch_depth is not None else
                                'CENTER_ANCHORED_PLANE' if mvs_normal is not None else 'CONSTANT_CAMERA_Z'))
