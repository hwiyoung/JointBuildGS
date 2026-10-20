"""Discard-rule variants (prior_propagation_v5, PHD-MAIN-PREP-DISCARD-RULE-v1; configs discard_v1.json 'rules').

'Discard' = a support patch voted conflict or a missing patch whose propagated judgment is conflict (prior depth term off,
missing points not planted); 'keep' = agree, mixed, insufficient. The variants change only the threshold of the marks that
the votes / propagation read, or how the propagation counts conflict evidence; the states, the gathering of up to k support
patches within r on the same surface, the 2/3 majority and the loss band are unchanged.
  current                marks at tau, standard propagation (rule.judge)
  margin_all k           marks at k tau (tau < |r| <= k tau counts as agree) for the votes and the propagation
  margin_propagation k   votes at tau; a gathered support patch voted conflict is conflict evidence only when the pooled median
                         |r| of its confidence-1 pixels in its supporting views exceeds k tau, otherwise it counts in the
                         gathered number but as neither side
  asymmetric             votes at tau; only agree propagates: a missing patch judged conflict becomes mixed (inherits)
  tau_scale s            marks at s tau (judgments of tau_scale 2 = margin_all 2)
Inputs are the per-(unit, view) tallies of tallies.view_counts (unit_view_pairs: loc, npix, na1, le) and the gathering of
locations.k_nearest_support_ids. Pure numpy. scientific_verdict: null."""
import numpy as np

from . import rule
from .tallies import THRESHOLDS

RULES = {
    "current": dict(t=1.0, prop="standard"),
    "margin_all_1.5": dict(t=1.5, prop="standard"), "margin_all_2": dict(t=2.0, prop="standard"), "margin_all_3": dict(t=3.0, prop="standard"),
    "margin_prop_1.5": dict(t=1.0, prop="margin", k=1.5), "margin_prop_2": dict(t=1.0, prop="margin", k=2.0), "margin_prop_3": dict(t=1.0, prop="margin", k=3.0),
    "asymmetric": dict(t=1.0, prop="asymmetric"),
    "tau_0.5": dict(t=0.5, prop="standard"), "tau_2": dict(t=2.0, prop="standard"),
}


def _ti(t):
    return THRESHOLDS.index(float(t))


def votes_at(pairs, L, t):
    """(state, vote) of every unit with the marks at t tau. pairs: loc, npix, na1, le [n, len(THRESHOLDS)]."""
    loc = np.asarray(pairs["loc"], np.int64); npix = np.asarray(pairs["npix"]); na1 = np.asarray(pairs["na1"])
    le = np.asarray(pairs["le"])[:, _ti(t)]
    sup = 2 * na1 >= npix
    mark_ag = le >= (na1 - le)
    ns = np.bincount(loc, minlength=L); nsp = np.bincount(loc[sup], minlength=L)
    av = np.bincount(loc[sup & mark_ag], minlength=L); cv = np.bincount(loc[sup & ~mark_ag], minlength=L)
    state = np.full(L, rule.ST_INVISIBLE, np.int8)
    state[(ns > 0) & (2 * nsp >= ns)] = rule.ST_SUPPORT
    state[(ns > 0) & (2 * nsp < ns)] = rule.ST_MISSING
    vote = np.where(cv > av, rule.V_CONFLICT, rule.V_AGREE).astype(np.int8)
    vote[state != rule.ST_SUPPORT] = rule.V_NONE
    return state, vote


def big_residual(pairs, L, k):
    """True where the pooled median |r| of the unit's confidence-1 pixels in its supporting views exceeds k tau
    (more than half of those pixels have |r| > k tau)."""
    loc = np.asarray(pairs["loc"], np.int64); npix = np.asarray(pairs["npix"]); na1 = np.asarray(pairs["na1"])
    le = np.asarray(pairs["le"])[:, _ti(k)]
    sup = 2 * na1 >= npix
    n1 = np.bincount(loc[sup], weights=na1[sup], minlength=L); nle = np.bincount(loc[sup], weights=le[sup], minlength=L)
    return (n1 - nle) > 0.5 * n1


def judge_margin(k_dist, k_vote, k_big, q, k, r):
    within = np.asarray(k_dist)[:, :k] <= r + 1e-9
    got = within.sum(1)
    conf = ((np.asarray(k_vote)[:, :k] == rule.V_CONFLICT) & np.asarray(k_big)[:, :k] & within).sum(1)
    agr = ((np.asarray(k_vote)[:, :k] == rule.V_AGREE) & within).sum(1)
    j = np.full(len(within), rule.J_MIXED, np.int8)
    thr = q * k - 1e-9
    j[conf >= thr] = rule.J_CONFLICT
    j[agr >= thr] = rule.J_AGREE
    j[got < k] = rule.J_INSUFF
    return j


def judge(mis, k_dist, k_id, vote, L, spec, q, k, r, big=None):
    """propagated judgment [L] (J_NONE outside the missing units) of the variant spec (RULES value)."""
    J = np.full(L, rule.J_NONE, np.int8)
    if not len(mis):
        return J
    kid = np.asarray(k_id)
    kv = np.where(kid >= 0, np.asarray(vote)[np.maximum(kid, 0)], rule.V_NONE)
    if spec["prop"] == "standard":
        J[mis] = rule.judge(k_dist, kv, q, int(k), float(r))
    elif spec["prop"] == "margin":
        kb = np.where(kid >= 0, np.asarray(big)[np.maximum(kid, 0)], False)
        J[mis] = judge_margin(k_dist, kv, kb, q, int(k), float(r))
    elif spec["prop"] == "asymmetric":
        jj = rule.judge(k_dist, kv, q, int(k), float(r))
        jj[jj == rule.J_CONFLICT] = rule.J_MIXED
        J[mis] = jj
    else:
        raise ValueError(spec)
    return J


def discard(state, vote, J):
    return ((state == rule.ST_SUPPORT) & (vote == rule.V_CONFLICT)) | ((state == rule.ST_MISSING) & (J == rule.J_CONFLICT))


def apply(pairs, L, mis, k_dist, k_id, name, q, k, r):
    """(state, vote, J, discard) of the named variant."""
    spec = RULES[name]
    state, vote = votes_at(pairs, L, spec["t"])
    big = big_residual(pairs, L, spec["k"]) if spec["prop"] == "margin" else None
    J = judge(mis, k_dist, k_id, vote, L, spec, q, k, r, big)
    return state, vote, J, discard(state, vote, J)
