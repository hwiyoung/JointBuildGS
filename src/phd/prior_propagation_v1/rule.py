"""Location states and the propagation rule (PHD-STAGE2-R7-PROPAGATION-v1). Pure numpy, no file access.

Terms (method document 4.x, as transcribed in the order):
  seeing view     : the location is inside the image and not hidden by another surface (here: at least one pixel of the
                    location in that view, the pixels coming from the render of the prior)
  supporting view : at least half of the location's pixels in that view have observation confidence A = 1
  support / missing / invisible location: supporting views >= half of the seeing views / fewer / no seeing view
  vote of a support location: majority of the supporting views' marks; a tie is agree. A view's mark is agree when its
                    agree pixels >= its conflict pixels (a choice of the implementation; the document fixes only the vote)
  Gaussian confidence E of a location: supporting views / seeing views (0 when no view sees it)
  propagated judgment of a missing location: collect the support locations of the same surface nearest first, stop at
                    the minimum, collect nothing beyond the maximum distance; conflict share >= majority -> conflict,
                    agree share >= majority -> agree, otherwise mixed; fewer than the minimum -> insufficient evidence."""
import numpy as np

ST_INVISIBLE, ST_SUPPORT, ST_MISSING = 0, 1, 2
V_NONE, V_AGREE, V_CONFLICT = -1, 0, 1
J_NONE, J_CONFLICT, J_AGREE, J_MIXED, J_INSUFF = -1, 0, 1, 2, 3
J_NAMES = {J_CONFLICT: "conflict", J_AGREE: "agree", J_MIXED: "mixed", J_INSUFF: "insufficient"}
ST_NAMES = {ST_INVISIBLE: "invisible", ST_SUPPORT: "support", ST_MISSING: "missing"}


def location_state(n_pix, n_a1, n_ag, n_cf):
    """per-view pixel counts [V, L] -> (state [L], vote [L], n_seeing [L], n_supporting [L], E [L])."""
    n_pix = np.asarray(n_pix); n_a1 = np.asarray(n_a1); n_ag = np.asarray(n_ag); n_cf = np.asarray(n_cf)
    seeing = n_pix > 0
    supporting = seeing & (2 * n_a1 >= n_pix)
    mark_agree = n_ag >= n_cf
    n_seeing = seeing.sum(0); n_supporting = supporting.sum(0)
    state = np.full(n_pix.shape[1], ST_INVISIBLE, np.int8)
    state[(n_seeing > 0) & (2 * n_supporting >= n_seeing)] = ST_SUPPORT
    state[(n_seeing > 0) & (2 * n_supporting < n_seeing)] = ST_MISSING
    agree_views = (supporting & mark_agree).sum(0); conflict_views = (supporting & ~mark_agree).sum(0)
    vote = np.where(conflict_views > agree_views, V_CONFLICT, V_AGREE).astype(np.int8)
    vote[state != ST_SUPPORT] = V_NONE
    E = np.where(n_seeing > 0, n_supporting / np.maximum(n_seeing, 1), 0.0)
    return state, vote, n_seeing.astype(np.int32), n_supporting.astype(np.int32), E


def judge(k_dist, k_vote, q, k, r):
    """k_dist / k_vote [N, KMAX]: support locations of the same surface sorted by in-surface distance (inf / -1 padded)."""
    k_dist = np.asarray(k_dist); k_vote = np.asarray(k_vote)
    within = k_dist[:, :k] <= r + 1e-9
    got = within.sum(1)
    conf = ((k_vote[:, :k] == V_CONFLICT) & within).sum(1)
    agr = got - conf
    j = np.full(len(k_dist), J_MIXED, np.int8)
    thr = q * k - 1e-9
    j[conf >= thr] = J_CONFLICT
    j[agr >= thr] = J_AGREE
    j[got < k] = J_INSUFF
    return j
