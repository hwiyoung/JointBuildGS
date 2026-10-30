"""Order-v2 eligibility and scoring, independent of source/renderer choices.

No optimization, GT loss, nearest-neighbor label substitution, or missing-value
imputation is performed here. The source adapter must prove point ownership.
"""
import numpy as np


def classify_places(mvs_p, gt_p, tau, judgment):
    """One result per photo-check point; outward normal is positive.

    Reasons are exclusive in this order, so excluded totals reconcile exactly.
    GT is already a point-level scalar when this function is called.
    """
    m, g = np.broadcast_arrays(np.asarray(mvs_p, float), np.asarray(gt_p, float))
    j = np.asarray(judgment)
    if j.shape != m.shape or not np.isin(j, [0, 1, 2, 3, 4]).all():
        raise ValueError('judgment must contain one defined photo label per point')
    if not np.isfinite(tau) or tau <= 0:
        raise ValueError('tau must be positive and finite')
    reason = np.full(m.shape, 'eligible', dtype='<U20')
    reason[~np.isfinite(m)] = 'missing_mvs'
    reason[(reason == 'eligible') & (np.abs(m) < 2 * tau)] = 'gap_below_2tau'
    reason[(reason == 'eligible') & ~np.isfinite(g)] = 'missing_gt'
    right_prior = np.isfinite(g) & (np.abs(g) <= tau)
    right_image = np.isfinite(m) & np.isfinite(g) & (np.abs(g - m) <= tau)
    reason[(reason == 'eligible') & right_prior & right_image] = 'both_right'
    reason[(reason == 'eligible') & ~right_prior & ~right_image] = 'both_wrong'
    eligible = reason == 'eligible'
    right = np.full(m.shape, '', dtype='<U5')
    right[eligible & right_prior] = 'prior'
    right[eligible & right_image] = 'image'
    front = (right_image & (m > 0)) | (right_prior & (m < 0))
    side = np.full(m.shape, '', dtype='<U5')
    side[eligible & front], side[eligible & ~front] = 'front', 'back'
    group = np.full(m.shape, '', dtype='<U1')
    group[eligible & (j >= 2)] = 'b'
    agrees = (right_prior & (j == 0)) | (right_image & (j == 1))
    group[eligible & (j < 2) & agrees] = 'a'
    group[eligible & (j < 2) & ~agrees] = 'c'
    return dict(eligible=eligible, reason=reason, right=right, side=side, group=group)


def outcomes(right_opacity, wrong_opacity):
    """Point opacities must be aggregated explicitly by the calling config.

    Invalid/missing measurements remain unavailable and never become zero.
    """
    a, b = np.broadcast_arrays(np.asarray(right_opacity, float), np.asarray(wrong_opacity, float))
    valid = np.isfinite(a) & np.isfinite(b) & (a >= 0) & (a <= 1) & (b >= 0) & (b <= 1)
    result = np.full(a.shape, 'unavailable', dtype='<U14')
    result[valid & (a >= .5) & (b < .5)] = 'right_only'
    result[valid & (a < .5) & (b >= .5)] = 'wrong_only'
    result[valid & (a >= .5) & (b >= .5)] = 'both'
    result[valid & (a < .5) & (b < .5)] = 'neither'
    return result


def in_candidate_column(xyz, centre, tangent1, tangent2, normal, mvs_p, tau):
    """Exact single 50cm cell-column membership, tested in its tangent frame.

    The scene builder unions these masks. GT is not an argument.
    """
    frame = np.stack([tangent1, tangent2, normal]).astype(float)
    if not np.isfinite(frame).all() or not np.allclose(frame @ frame.T, np.eye(3), atol=1e-6):
        raise ValueError('undefined/non-orthonormal point frame')
    if not np.isfinite(mvs_p) or not np.isfinite(tau) or tau <= 0:
        raise ValueError('column requires finite MVS and positive tau')
    delta = np.asarray(xyz, float) - np.asarray(centre, float)
    u, v, h = (delta @ frame.T).T
    return ((np.abs(u) <= .25) & (np.abs(v) <= .25) &
            (h >= min(0., mvs_p) - tau) & (h <= max(0., mvs_p) + 3.))
