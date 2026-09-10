"""Source-symmetric local plane diagnostic; no GT or supervision weights."""
import numpy as np


def crop(a, size):
    r = a.shape[0] // 2
    h = size // 2
    return a[r-h:r+h+1, r-h:r+h+1]


def rays(uv, K):
    return np.concatenate([uv, np.ones(uv.shape[:-1] + (1,))], -1) @ np.linalg.inv(K).T


def estimate_normal(uv, depth, mask, K, fit_size=9, min_fraction=.8):
    """TLS orientation only; the candidate center Z is never fitted or moved."""
    d, m, q = crop(depth, fit_size), crop(mask, fit_size), crop(uv, fit_size)
    m = m & np.isfinite(d) & (d > 0)
    r = fit_size // 2
    out = dict(status='UNAVAILABLE', normal_camera=None, fit_count=int(m.sum()),
               center_depth_m=float(d[r,r]) if m[r,r] else None,
               fit_rms_m=None, anchored_rms_m=None, planarity_ratio=None,
               fit_size=fit_size, independent_observation=False)
    if not m[r,r]:
        out['status'] = 'MISSING_CENTER_DEPTH'
        return out
    if m.sum() < max(3, int(np.ceil(fit_size**2 * min_fraction))):
        out['status'] = 'INSUFFICIENT_NORMAL_SUPPORT'
        return out
    X = rays(q, K) * d[...,None]
    points = X[m]
    mean = points.mean(0)
    _, s, vh = np.linalg.svd(points - mean, full_matrices=False)
    if len(s) < 3 or s[1] <= max(1e-12, s[0] * 1e-8):
        out['status'] = 'DEGENERATE_NORMAL_SUPPORT'
        return out
    n = vh[-1]
    if n @ X[r,r] < 0:
        n = -n
    out.update(status='AVAILABLE_DERIVED_FROM_SAME_DEPTH', normal_camera=n.tolist(),
               fit_rms_m=float(np.sqrt(np.mean(((points-mean)@n)**2))),
               anchored_rms_m=float(np.sqrt(np.mean(((points-X[r,r])@n)**2))),
               planarity_ratio=float(s[-1]/s[1]))
    return out


def plane_depth(uv, raw_depth, raw_mask, K, normal):
    out = np.full(raw_depth.shape, np.nan)
    mask = np.zeros(raw_mask.shape, bool)
    if normal['normal_camera'] is None:
        return out, mask
    ray = rays(uv, K)
    r = len(raw_depth)//2
    n = np.asarray(normal['normal_camera'])
    offset = float(n @ (ray[r,r]*raw_depth[r,r]))
    denom = ray @ n
    with np.errstate(divide='ignore', invalid='ignore'):
        d = offset/denom
    # A plane is never permission to interpolate an original missing target.
    mask = raw_mask & np.isfinite(d) & (d > 0) & (np.abs(denom) > 1e-8)
    out[mask] = d[mask]
    return out, mask


def eligibility(scores, count, size, fraction, texture_std):
    reasons = []
    if count < int(np.ceil(size*size*fraction)):
        reasons.append('LOW_COMMON_SUPPORT')
    if any(s['cost'] is None for s in scores):
        reasons.append('UNDEFINED_PHOTO_COST')
    if any(s['std_reference'] is None or s['std_warp'] is None or
           min(s['std_reference'],s['std_warp']) < texture_std for s in scores):
        reasons.append('LOW_TEXTURE')
    return dict(usable=not reasons, reasons=reasons)


def summarize(rows, mode, image_source, cfg):
    paired = [r for r in rows if all(r[mode][s]['cost'] is not None for s in ('prior',image_source))]
    eligible = [r for r in paired if r['eligibility']['usable']]
    out = dict(paired_views=len(paired), eligible_views=len(eligible), median_prior_cost=None,
               median_image_cost=None, median_delta_image_minus_prior=None,
               prior_lower_views=0, image_lower_views=0, reading='INSUFFICIENT_SUPPORT',
               absolute_fit='UNASSESSED', selected_neighbor_count=len(rows))
    if not eligible:
        return out
    p = np.array([r[mode]['prior']['cost'] for r in eligible])
    i = np.array([r[mode][image_source]['cost'] for r in eligible])
    delta = i-p
    margin = cfg['cost_margin']
    out.update(median_prior_cost=float(np.median(p)), median_image_cost=float(np.median(i)),
               median_delta_image_minus_prior=float(np.median(delta)),
               prior_lower_views=int((delta > margin).sum()), image_lower_views=int((delta < -margin).sum()),
               absolute_fit='RELATIVE_COST_ONLY_NO_ACCURACY_CLAIM')
    if len(eligible) >= cfg['minimum_views']:
        pshare, ishare = (delta > margin).mean(), (delta < -margin).mean()
        if pshare >= cfg['consistent_fraction']:
            out['reading'] = 'PHOTO_COST_PREFERS_PRIOR'
        elif ishare >= cfg['consistent_fraction']:
            out['reading'] = 'PHOTO_COST_PREFERS_IMAGE'
        elif np.all(np.abs(delta) <= margin):
            out['reading'] = 'PHOTO_COST_CLOSE'
        else:
            out['reading'] = 'VIEW_DEPENDENT_OR_CLOSE'
    return out
