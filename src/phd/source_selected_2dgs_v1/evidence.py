"""Source-only geometry assembly with explicit, nonpropagating authority.

No evaluation reference, morphology, interpolation through holes, or outcome
selection participates in these functions. IDs identify original image samples.
"""
import numpy as np
from scipy.ndimage import distance_transform_edt


def world_points(camera, uv, depth):
    uv, depth = np.asarray(uv, float), np.asarray(depth, float)
    rays = np.concatenate((uv, np.ones(uv.shape[:-1]+(1,))), -1) @ np.linalg.inv(camera['K']).T
    return (rays*depth[..., None]-np.asarray(camera['t'])) @ np.asarray(camera['R'])


def project_points(camera, xyz):
    cam = np.asarray(xyz) @ np.asarray(camera['R']).T + np.asarray(camera['t'])
    homogeneous = cam @ np.asarray(camera['K']).T
    with np.errstate(divide='ignore', invalid='ignore'):
        uv = homogeneous[..., :2]/homogeneous[..., 2:3]
    return uv, cam[..., 2]


def inside_xy(xyz, domain):
    return (np.isfinite(xyz).all(-1) & (xyz[..., 0] >= domain['x'][0]) & (xyz[..., 0] < domain['x'][1])
            & (xyz[..., 1] >= domain['y'][0]) & (xyz[..., 1] < domain['y'][1]))


def stable_ids(region_index, image_id, width, uv, source_kind):
    """Exact int64 namespace, also within JavaScript's exact integer range."""
    uv = np.asarray(uv)
    flat = uv[..., 1].astype(np.int64)*int(width)+uv[..., 0].astype(np.int64)
    if not (1 <= region_index <= 9 and 0 <= image_id < 10000 and source_kind in (0, 1)):
        raise ValueError('Source ID component outside frozen namespace')
    if np.any((flat < 0) | (flat >= 10000000)): raise ValueError('Image pixel outside ID namespace')
    return np.int64(region_index)*10**12 + np.int64(source_kind)*10**11 + np.int64(image_id)*10**7 + flat


def patch_mask(shape, bbox):
    h, w = shape
    x0, y0, x1, y1 = map(int, bbox)
    result = np.zeros(shape, bool)
    if x1 > x0 and y1 > y0:
        result[max(0, y0):min(h, y1), max(0, x0):min(w, x1)] = True
    return result


def seed_pixel_mask(shape, stride, bboxes):
    """Same baseline/selected sample density, including every exact patch pixel."""
    if int(stride) != stride or stride < 1: raise ValueError('Positive integer stride required')
    mask = np.zeros(shape, bool)
    mask[::stride, ::stride] = True
    exact = np.zeros(shape, bool)
    for box in bboxes: exact |= patch_mask(shape, box)
    return mask | exact, exact


def normals_from_depth(camera, depth):
    """Central differences require five valid raw samples; no filled depth."""
    depth = np.asarray(depth, float); h, w = depth.shape
    normal = np.full((h, w, 3), np.nan, dtype=np.float32)
    valid = np.isfinite(depth) & (depth > 0)
    if h < 3 or w < 3: return normal, np.zeros_like(valid)
    yy, xx = np.mgrid[1:h-1, 1:w-1]
    uv = np.stack((xx, yy), -1).astype(float)
    dx = world_points(camera, uv+[1, 0], depth[1:-1, 2:])-world_points(camera, uv-[1, 0], depth[1:-1, :-2])
    dy = world_points(camera, uv+[0, 1], depth[2:, 1:-1])-world_points(camera, uv-[0, 1], depth[:-2, 1:-1])
    n = np.cross(dx, dy); length = np.linalg.norm(n, axis=-1)
    good = (valid[1:-1, 1:-1] & valid[1:-1, 2:] & valid[1:-1, :-2] & valid[2:, 1:-1]
            & valid[:-2, 1:-1] & np.isfinite(length) & (length > 1e-12))
    n /= np.maximum(length[..., None], 1e-12)
    center = -np.asarray(camera['R']).T @ np.asarray(camera['t'])
    xyz = world_points(camera, uv, depth[1:-1, 1:-1])
    n *= np.where(np.sum(n*(center-xyz), axis=-1) < 0, -1., 1.)[..., None]
    normal[1:-1, 1:-1] = np.where(good[..., None], n, np.nan).astype(np.float32)
    return normal, np.isfinite(normal).all(-1)


def prior_replacement_membership(xyz, camera, bbox, prior_depth, tolerance):
    """Exact original patch footprint plus Prior-depth agreement, no dilation."""
    uv, z = project_points(camera, xyz)
    x0, y0, x1, y1 = map(int, bbox); h, w = prior_depth.shape
    inside = (np.isfinite(uv).all(1) & (z > 0) & (uv[:, 0] >= x0-.5) & (uv[:, 0] < x1-.5)
              & (uv[:, 1] >= y0-.5) & (uv[:, 1] < y1-.5))
    rounded = np.floor(np.nan_to_num(uv, nan=-1e9, posinf=1e9, neginf=-1e9)+.5).astype(np.int64)
    in_frame = (rounded[:, 0] >= 0) & (rounded[:, 0] < w) & (rounded[:, 1] >= 0) & (rounded[:, 1] < h)
    ids = np.flatnonzero(inside & in_frame)
    result = np.zeros(len(xyz), bool)
    observed = prior_depth[rounded[ids, 1], rounded[ids, 0]]
    result[ids] = np.isfinite(observed) & (observed > 0) & (np.abs(z[ids]-observed) <= tolerance)
    return result


def point_projection_support(camera, xyz, observed_depth=None, tolerance=.5):
    """One projected native pixel per observed 3D point, with explicit links.

    This is a diagnostic projection of an existing source sample. It does not
    become independent authority in the receiving view.
    """
    h, w = int(camera['height']), int(camera['width'])
    uv, z = project_points(camera, xyz)
    valid = np.isfinite(uv).all(1) & (z > 0) & (uv[:, 0] >= -.5) & (uv[:, 0] < w-.5) & (uv[:, 1] >= -.5) & (uv[:, 1] < h-.5)
    ids = np.flatnonzero(valid); ij = np.floor(uv[ids]+.5).astype(np.int64)
    residual = np.full(len(ids), np.nan)
    compatible = np.zeros(len(ids), bool)
    if observed_depth is not None:
        observed = observed_depth[ij[:, 1], ij[:, 0]]
        residual = z[ids]-observed
        compatible = np.isfinite(observed) & (observed > 0) & (np.abs(residual) <= tolerance)
    mask = np.zeros((h, w), bool)
    mask[ij[:, 1], ij[:, 0]] = True
    visible = np.zeros_like(mask); visible[ij[compatible, 1], ij[compatible, 0]] = True
    return dict(mask=mask, compatible_mask=visible, point_indices=ids, pixel_xy=ij,
                depth=z[ids], observed_residual=residual, compatible=compatible)


def assemble_source_arms(prior, replacement_mask, mvs):
    """Return paired seeds; unsupported Prior rows remain exact and ordered."""
    replacement_mask = np.asarray(replacement_mask, bool)
    if len(replacement_mask) != len(prior['xyz']): raise ValueError('Replacement membership length differs')
    keys = ('xyz', 'rgb', 'normal', 'scale', 'source_kind', 'stable_source_id')
    if any(len(prior[k]) != len(replacement_mask) for k in keys): raise ValueError('Prior arrays differ in length')
    if any(len(mvs[k]) != len(mvs['xyz']) for k in keys): raise ValueError('MVS arrays differ in length')
    baseline = {k: np.array(prior[k], copy=True) for k in keys}
    baseline['trainable_geometry'] = replacement_mask.copy()
    selected = {k: np.concatenate((prior[k][~replacement_mask], mvs[k]), axis=0) for k in keys}
    selected['trainable_geometry'] = np.r_[np.zeros(int((~replacement_mask).sum()), bool), np.ones(len(mvs['xyz']), bool)]
    ids = np.r_[prior['stable_source_id'], mvs['stable_source_id']]
    if len(np.unique(ids)) != len(ids): raise ValueError('Duplicate stable source sample ID')
    for key in keys:
        if not np.array_equal(baseline[key][~replacement_mask], selected[key][:int((~replacement_mask).sum())], equal_nan=True):
            raise ValueError('Fallback source rows changed')
    return baseline, selected


def view_targets(prior_depth, mvs_depth, prior_normal, mvs_normal, domain_mask,
                 authority_mask, projection_mask, agreement_mask, abstain_mask, ring_radius=31,
                 prior_domain_mask=None, mvs_domain_mask=None):
    """Authority stays on independently admitted pixels, separate from support."""
    pd, md = np.asarray(prior_depth), np.asarray(mvs_depth)
    pvalid = np.isfinite(pd) & (pd > 0) & (domain_mask if prior_domain_mask is None else prior_domain_mask)
    mvalid = np.isfinite(md) & (md > 0) & (domain_mask if mvs_domain_mask is None else mvs_domain_mask)
    authority = np.asarray(authority_mask, bool) & domain_mask
    paired_authority = authority & pvalid & mvalid
    projection_abstain = np.asarray(projection_mask, bool) & ~authority
    fallback = pvalid & ~authority & ~projection_abstain
    selected = np.where(paired_authority, md, np.where(fallback, pd, np.nan)).astype(np.float32)
    depth_valid = np.isfinite(selected) & (selected > 0)
    normal = np.where(authority[..., None], mvs_normal, prior_normal).astype(np.float32)
    pnvalid = np.isfinite(prior_normal).all(-1) & (np.linalg.norm(np.nan_to_num(prior_normal), axis=-1) > .5)
    mnvalid = np.isfinite(mvs_normal).all(-1) & (np.linalg.norm(np.nan_to_num(mvs_normal), axis=-1) > .5)
    normal_valid = depth_valid & pnvalid & (~authority | mnvalid)
    normal[~normal_valid] = np.nan
    target = (authority | projection_mask) & domain_mask
    surrounding = (distance_transform_edt(~target) <= ring_radius) & ~target & domain_mask if target.any() else np.zeros_like(target)
    choice = np.where(pvalid, 1, 0).astype(np.uint8)
    choice[np.asarray(agreement_mask, bool) & pvalid] = 3
    choice[np.asarray(abstain_mask, bool) & pvalid] = 4
    choice[projection_abstain & domain_mask] = 5
    choice[authority] = 2
    return dict(prior_depth=pd.astype(np.float32), mvs_depth=md.astype(np.float32), selected_depth=selected,
                prior_depth_valid=depth_valid.copy(), mvs_depth_valid=mvalid, depth_valid=depth_valid,
                prior_input_valid=pvalid, mvs_input_valid=mvalid,
                authority_mask=authority, photo_mask=domain_mask,
                target_mask=target, surrounding_mask=surrounding, outside_mask=domain_mask & ~(target | surrounding),
                source_normal=normal, selected_normal=normal, prior_normal=np.asarray(prior_normal, np.float32),
                mvs_normal=np.asarray(mvs_normal, np.float32), normal_valid=normal_valid,
                prior_normal_valid=normal_valid.copy(),
                projection_abstain_mask=projection_abstain & domain_mask,
                projected_support_mask=np.asarray(projection_mask, bool), decision_mask=choice,
                agreement_mask=np.asarray(agreement_mask, bool), abstain_mask=np.asarray(abstain_mask, bool))
