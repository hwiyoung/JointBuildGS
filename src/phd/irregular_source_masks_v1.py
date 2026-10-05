"""Per-center source evidence; patch support never becomes a square edit label.

These deterministic development rules are not calibrated source probabilities or
temporal-change ground truth. Source depths and image coordinates retain the
sampling conventions of mvs_evidence_v1.
"""
from __future__ import annotations

import warnings
import numpy as np

from src.phd import mvs_evidence_v1 as geometry
from src.phd.mvs_surface_update_v1 import curve_summary
from scripts.phd.mvs_evidence_v1.build import normals, patch_uv


DECISIONS = {0: 'OUTSIDE_ROI', 1: 'MISSING_SOURCE', 2: 'AGREE_NO_SOURCE_WINNER',
             3: 'UNASSESSED', 4: 'ABSTAIN', 5: 'MVS_SUPPORTED', 6: 'PRIOR_SUPPORTED',
             7: 'NO_SOURCE_XY_ROI_UNKNOWN'}
COLORS = np.array([[37, 48, 65, 25], [120, 125, 137, 160], [49, 173, 125, 150],
                   [239, 218, 118, 160], [170, 113, 184, 180], [244, 145, 46, 210],
                   [58, 129, 234, 210], [108, 115, 124, 145]], dtype=np.uint8)


def inside_xy(world, domain):
    world = np.asarray(world)
    return (np.isfinite(world[..., :2]).all(-1)
            & (world[..., 0] >= domain['x'][0]) & (world[..., 0] < domain['x'][1])
            & (world[..., 1] >= domain['y'][0]) & (world[..., 1] < domain['y'][1]))


def initial_decisions(prior, mvs, roi, threshold):
    prior_valid = np.isfinite(prior) & (prior > 0)
    mvs_valid = np.isfinite(mvs) & (mvs > 0)
    both = prior_valid & mvs_valid
    candidate = both & (np.abs(prior-mvs) > threshold)
    decision = np.zeros(prior.shape, np.uint8)
    decision[roi & ~both] = 1
    decision[roi & both & ~candidate] = 2
    decision[roi & candidate] = 3
    decision[~prior_valid & ~mvs_valid] = 7
    return decision, candidate


def votes(margins, eligible, minimum_margin, minimum_views):
    """Use identical eligible neighbors for positive, negative, and neutral votes."""
    margins, eligible = np.asarray(margins), np.asarray(eligible, bool)
    eligible = eligible & np.isfinite(margins)
    mvs = (eligible & (margins > minimum_margin)).sum(0)
    prior = (eligible & (margins < -minimum_margin)).sum(0)
    return dict(mvs=mvs, prior=prior, admitted=eligible.sum(0),
                dissent=(mvs > 0) & (prior > 0),
                profile_candidate=(mvs >= minimum_views) | (prior >= minimum_views),
                mvs_winner=(mvs >= minimum_views) & (mvs > prior),
                prior_winner=(prior >= minimum_views) & (prior > mvs))


def paired_costs(centers, prior_depth, mvs_depth, patch_prior, patch_mvs, ref, nb, cfg):
    """Original common raw-depth patch comparison with grayscale checked on load.

Avoid rescanning the entire source RGB array for every small chunk. The returned
score still belongs only to each center pixel.
"""
    uv = patch_uv(centers, cfg['patch_radius'])
    reference, rvalid = geometry.bilinear(ref['gray'], uv)
    warped, masks = [], []
    for patch in (patch_prior, patch_mvs):
        target, z, _ = geometry.project(uv, patch, ref['view'], nb['view'])
        color, good = geometry.bilinear(nb['gray'], target)
        warped.append(color)
        masks.append(rvalid & good & np.isfinite(patch) & (patch > 0) & (z > 0))
    common = masks[0] & masks[1]
    pc, pa, pb = geometry._cost(reference, warped[0], common)
    mc, ma, mb = geometry._cost(reference, warped[1], common)
    costs = np.stack([pc, mc], -1)
    texture = np.minimum.reduce([pa, pb, ma, mb])
    eligible = (np.isfinite(costs).all(-1) & (texture >= cfg['texture_std'])
                & (common.mean(-1) >= cfg['minimum_patch_fraction'])
                & np.isfinite(prior_depth) & np.isfinite(mvs_depth))
    return dict(costs=np.where(eligible[:, None], costs, np.nan),
                texture=texture, common_count=common.sum(-1), eligible=eligible)


def source_profiles(centers, dp, dm, patch_prior, patch_mvs, ref, neighbors, admission, cfg):
    """Two source-normal branches at all 33 depths for every admitted neighbor.

    A neighbor is retained only with complete common support over every depth and
    both branches. Opposing and neutral image preferences are retained. Missing
    source patches remain missing; no interpolation of unmeasured centers occurs.
    """
    n = len(centers); samples = cfg['profile_samples']
    uv = patch_uv(centers, cfg['patch_radius'])
    pnormal = normals(uv, patch_prior, np.asarray(ref['view']['K']))
    mnormal = normals(uv, patch_mvs, np.asarray(ref['view']['K']))
    padding = np.maximum(cfg['profile_padding_m'], .5*np.abs(dp-dm))
    lo, hi = np.maximum(.1, np.minimum(dp, dm)-padding), np.maximum(dp, dm)+padding
    tt = np.linspace(0, 1, samples)
    depths = 1/((1/lo[:, None])*(1-tt)+(1/hi[:, None])*tt)
    raw = np.full((len(neighbors), n, 2, samples), np.nan, dtype=np.float64)
    complete = ((np.isfinite(patch_prior) & (patch_prior > 0)).all(1)
                & (np.isfinite(patch_mvs) & (patch_mvs > 0)).all(1)
                & np.isfinite(pnormal).all(1) & np.isfinite(mnormal).all(1))
    for ni, nb in enumerate(neighbors):
        idx = np.flatnonzero(complete & admission[ni])
        if not len(idx):
            continue
        # The scalar-hypothesis loop bounds temporary memory independently of the
        # search length; no whole-frame Nx49x33 array is ever materialized.
        u = uv[idx]
        reference, valid_ref = geometry.bilinear(ref['gray'], u)
        good = np.ones(len(idx), bool)
        branch_costs = np.empty((len(idx), 2, samples), np.float64)
        for bi, normal in enumerate((pnormal[idx], mnormal[idx])):
            for j in range(samples):
                patch_uvs, patch_z = geometry._patch_geometry(centers[idx], depths[idx, j],
                                                             ref['view'], cfg['patch_radius'], normal=normal)
                target, z, _ = geometry.project(patch_uvs, patch_z, ref['view'], nb['view'])
                warped, valid_nb = geometry.bilinear(nb['gray'], target)
                valid = valid_ref & valid_nb & np.isfinite(patch_z) & (patch_z > 0) & (z > 0)
                cost, rt, wt = geometry._cost(reference, warped, valid)
                good &= (valid.all(1) & np.isfinite(cost)
                         & (np.minimum(rt, wt) >= cfg['texture_std']))
                branch_costs[:, bi, j] = cost
        branch_costs[~good] = np.nan
        raw[ni, idx] = branch_costs
    return depths, raw


def decide_profiles(prior_depth, mvs_depth, margins, eligible, depths, raw, cfg):
    """Symmetric source choice after shared evidence and ambiguity checks."""
    complete = np.isfinite(raw).all((2, 3))
    admitted = np.asarray(eligible, bool) & complete
    v = votes(margins, admitted, cfg['minimum_photo_margin'], cfg['minimum_joint_views'])
    kept = np.where(admitted[..., None, None], raw, np.nan)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', RuntimeWarning)
        curves = np.min(np.nanmedian(kept, axis=0), axis=1)
    curves[v['admitted'] < cfg['minimum_joint_views']] = np.nan
    stats = curve_summary(depths, curves)
    common = (np.isfinite(stats['cost']) & (stats['cost'] <= cfg['profile_maximum_cost'])
              & (stats['width'] <= cfg['profile_maximum_width_m'])
              & (stats['spacing'] <= cfg['profile_maximum_spacing_m'])
              & (stats['modes'] == 1) & (stats['edge'] == 0) & (stats['boundary'] == 0))
    mvs_close = np.abs(stats['best']-mvs_depth) <= cfg['profile_maximum_source_offset_m']
    prior_close = np.abs(stats['best']-prior_depth) <= cfg['profile_maximum_source_offset_m']
    result = np.full(len(prior_depth), 4, np.uint8)
    result[common & mvs_close & v['mvs_winner']] = 5
    result[common & prior_close & v['prior_winner']] = 6
    return dict(decision=result, stats=stats, votes=v, curves=curves,
                admitted=admitted, common_profile_pass=common)
