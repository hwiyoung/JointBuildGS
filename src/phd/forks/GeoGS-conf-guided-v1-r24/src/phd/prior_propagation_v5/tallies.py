"""Pass-3 per-view counts of the judgment units (prior_propagation_v5, PHD-MAIN-PREP-DISCARD-RULE-v1).

Moved unchanged from the PHD-MAIN-PREP-MEASURE-v1 stage-1 script (sparse per-view unit counts and the unit states / votes),
plus one new output: per (unit, view) the confidence-1 pixels with |r| <= t tau for the rule thresholds t, so that the
discard-rule variants (rules.py) can be read offline without re-rendering. Terms as rule.py. scientific_verdict: null."""
import numpy as np

from . import rule

THRESHOLDS = (0.5, 1.0, 1.5, 2.0, 3.0)


def new_acc(L):
    return dict(n_seeing=np.zeros(L, np.int32), n_supporting=np.zeros(L, np.int32), agree_views=np.zeros(L, np.int32),
                conflict_views=np.zeros(L, np.int32), pix_sum=np.zeros(L, np.int64), a1_sum=np.zeros(L, np.int64),
                agree_sum=np.zeros(L, np.int64), conflict_sum=np.zeros(L, np.int64))


def view_counts(loc, okl, a1, ag, cf, ar, tau_px, thresholds=THRESHOLDS):
    """one view. loc [P] unit of each prior pixel (-1 none), okl = loc >= 0, a1 confidence-1, ag / cf the marks at tau,
    ar |r|, tau_px the pixel's tolerance. Returns None or (u, npx, na1, nag, ncf, le [len(u), len(thresholds)])."""
    lv = loc[okl]
    if not len(lv):
        return None
    u, inv = np.unique(lv, return_inverse=True)
    npx = np.bincount(inv); na1 = np.bincount(inv, weights=a1[okl]).astype(np.int64)
    nag = np.bincount(inv, weights=ag[okl]).astype(np.int64); ncf = np.bincount(inv, weights=cf[okl]).astype(np.int64)
    le = np.stack([np.bincount(inv, weights=(a1 & (ar <= t * tau_px))[okl], minlength=len(u)).astype(np.int64) for t in thresholds], 1)
    return u, npx, na1, nag, ncf, le


def accumulate(acc, u, npx, na1, nag, ncf):
    supporting = 2 * na1 >= npx; mark_ag = nag >= ncf
    acc["n_seeing"][u] += 1; acc["n_supporting"][u] += supporting
    acc["agree_views"][u] += supporting & mark_ag; acc["conflict_views"][u] += supporting & ~mark_ag
    acc["pix_sum"][u] += npx; acc["a1_sum"][u] += na1; acc["agree_sum"][u] += nag; acc["conflict_sum"][u] += ncf


def unit_states(acc):
    """(state, vote, E) from the accumulated counts (support: supporting views >= half of the seeing views; vote: majority of
    the supporting views' marks, a tie is agree)."""
    ns, nsp = acc["n_seeing"], acc["n_supporting"]
    L = len(ns)
    state = np.full(L, rule.ST_INVISIBLE, np.int8)
    state[(ns > 0) & (2 * nsp >= ns)] = rule.ST_SUPPORT
    state[(ns > 0) & (2 * nsp < ns)] = rule.ST_MISSING
    vote = np.where(acc["conflict_views"] > acc["agree_views"], rule.V_CONFLICT, rule.V_AGREE).astype(np.int8)
    vote[state != rule.ST_SUPPORT] = rule.V_NONE
    E = np.where(ns > 0, nsp / np.maximum(ns, 1), 0.0)
    return state, vote, E
