"""Frozen technical admission policy for local, reversible Gaussian probes."""
import numpy as np
import warnings


def curve_summary(depths, costs):
    """Descriptive discrete intervals; not a calibrated confidence interval."""
    count = len(depths)
    result = {k: np.full(count, np.nan) for k in ('best', 'cost', 'width', 'spacing', 'modes', 'edge', 'boundary')}
    for i in range(count):
        c, z = costs[i], depths[i]
        if not np.isfinite(c).all():
            continue
        j = int(np.argmin(c)); near = c <= c[j]+.03
        result['best'][i], result['cost'][i] = z[j], c[j]
        result['width'][i] = np.ptp(z[near])
        result['spacing'][i] = np.max(np.diff(z[max(0,j-1):min(len(z),j+2)]))
        result['modes'][i] = int(near[0])+np.count_nonzero(near[1:] & ~near[:-1])
        result['edge'][i] = c[0]<=c[j]+1e-12 or c[-1]<=c[j]+1e-12
        result['boundary'][i] = near[0] or near[-1]
    return result


def assess(a, cfg):
    delta = np.asarray(a['point_delta'])
    finite = np.isfinite(delta)
    candidate = finite & (np.abs(delta) > cfg['candidate_threshold_m'])
    n = len(delta)
    pidx = a['profile_point_indices'].astype(int)
    # Profile measurements have a separate 48px support from 16px observation grid.
    profile_ok_by_neighbor = np.zeros(a['mvs_self_status'].shape, bool)
    raw = np.asarray(a['profile_per_neighbor_costs'])
    for ni in range(raw.shape[0]):
        profile_ok_by_neighbor[ni, pidx] = np.isfinite(raw[ni]).all((1, 2))
    costs = a['photo_costs_per_neighbor']
    margin = costs[..., 0] - costs[..., 1]
    admitted = ((a['prior_self_status'] == 3) & (a['mvs_self_status'] == 3)
                & np.isfinite(margin) & profile_ok_by_neighbor)
    if 'per_neighbor_parallax_deg' in a:
        admitted &= np.isfinite(a['per_neighbor_parallax_deg']) & (a['per_neighbor_parallax_deg'] >= cfg['minimum_patch_parallax_degrees'])
    joint = admitted & (margin > cfg['minimum_photo_margin'])
    opposite = admitted & (margin < -cfg['minimum_photo_margin'])
    selected_raw = np.where(admitted[:len(raw), pidx, None, None], raw, np.nan)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', RuntimeWarning)
        curves = np.min(np.nanmedian(selected_raw, axis=0), axis=1)
    curves[admitted[:,pidx].sum(0)<2] = np.nan
    stats = curve_summary(a['profile_depths'], curves)
    full = {k: np.full(n, np.nan) for k in stats}
    for key in full: full[key][pidx] = stats[key]
    best = np.full(n, np.nan)
    best[pidx] = stats['best']
    checks = {
        'candidate_discrepancy': candidate,
        'same_neighbor_support': joint.sum(0) >= cfg['minimum_joint_views'],
        'low_absolute_profile_cost': np.isfinite(full['cost']) & (full['cost'] <= cfg['profile_maximum_cost']),
        'localized_profile': np.isfinite(full['width']) & (full['width'] <= cfg['profile_maximum_width_m']),
        'resolved_depth_grid': np.isfinite(full['spacing']) & (full['spacing'] <= cfg['profile_maximum_spacing_m']),
        'single_interval': full['modes'] == 1,
        'search_interior': (full['edge'] == 0) & (full['boundary'] == 0),
        'mvs_matches_profile': np.isfinite(best) & (np.abs(best-a['point_mvs_depth']) <= cfg['profile_maximum_mvs_offset_m']),
        'parallax': np.isfinite(a['point_parallax_deg']) & (a['point_parallax_deg'] >= cfg['minimum_patch_parallax_degrees'])}
    accepted = np.logical_and.reduce(list(checks.values()))
    reasons = [[key for key, mask in checks.items() if not mask[i]] for i in range(n)]
    return dict(candidate=candidate, agree=finite & ~candidate, accepted=accepted,
                joint=joint, joint_count=joint.sum(0), admitted=admitted, opposite=opposite,
                checks=checks, reasons=reasons, curves=curves, profile_stats=full,
                profile_best=best, profile_neighbor_support=profile_ok_by_neighbor)
