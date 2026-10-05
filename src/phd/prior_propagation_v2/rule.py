"""Judgment-unit states, the propagation rule and the pixel weight g_p (prior_propagation_v2, PHD-STAGE2-R8-FOUR-CASES-v1).
Pure numpy (prior_term_off also takes torch tensors), no file access. Code names: 'location' = judgment unit (판정 단위).

Terms (method document 2026-10-01, 4.2):
  seeing view     : the unit is inside the image and not hidden by another surface (here: at least one pixel of the unit in
                    that view, the pixels coming from the render of the prior)
  supporting view : at least half of the unit's pixels in that view have observation confidence c = 1
  support / missing / invisible unit: supporting views >= half of the seeing views / fewer / no seeing view
  vote of a support unit: majority of the supporting views' marks; a tie is agree. A view's mark is agree when its agree
                    pixels >= its conflict pixels (a choice of the implementation; the document fixes only the vote)
  Gaussian confidence of a unit (eq. 1): supporting views / seeing views (0 when no view sees it)
  propagated judgment of a missing unit: collect the support units of the same surface nearest first, stop at the
                    minimum, collect nothing beyond the maximum distance; conflict share >= majority -> conflict,
                    agree share >= majority -> agree, otherwise mixed; fewer than the minimum -> insufficient evidence
  g_p (eq. 4, decision 1 and 3): 0 where the pixel's unit is judged conflict (a support unit's vote or a missing unit's
                    propagated judgment, read alike), 1 where agree or undetermined; for a pixel without a unit: 1 where
                    c = 0, its own mark where c = 1 (agree 1, conflict 0). Decided once at initialisation."""
import numpy as np

ST_INVISIBLE, ST_SUPPORT, ST_MISSING = 0, 1, 2
V_NONE, V_AGREE, V_CONFLICT = -1, 0, 1
MARK_NONE, MARK_AGREE, MARK_CONFLICT = -1, 0, 1          # per-pixel agree/conflict marks (stage-1 product)
J_NONE, J_CONFLICT, J_AGREE, J_MIXED, J_INSUFF = -1, 0, 1, 2, 3
J_NAMES = {J_CONFLICT: "conflict", J_AGREE: "agree", J_MIXED: "mixed", J_INSUFF: "insufficient"}
ST_NAMES = {ST_INVISIBLE: "invisible", ST_SUPPORT: "support", ST_MISSING: "missing"}
# why a unit is undetermined (평가가 읽는 출력, decision 6)
WHY_DETERMINED, WHY_INVISIBLE, WHY_MIXED, WHY_NO_SUPPORT_ON_SURFACE, WHY_TOO_FEW_WITHIN_DISTANCE = 0, 1, 2, 3, 4
WHY_NAMES = {WHY_DETERMINED: "determined", WHY_INVISIBLE: "invisible (no seeing view)", WHY_MIXED: "mixed votes",
             WHY_NO_SUPPORT_ON_SURFACE: "insufficient: no support unit on the same surface",
             WHY_TOO_FEW_WITHIN_DISTANCE: "insufficient: fewer than the minimum within the maximum distance"}


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


def undetermined_why(state, J, k_dist, missing_ids, k, r):
    """why [L] (WHY_*): invisible units; missing units judged mixed; missing units with insufficient evidence split into
    'no support unit on the same surface' (no finite distance at all) and 'fewer than the minimum within the maximum
    distance'. k_dist rows follow missing_ids (locations.propagate)."""
    why = np.full(len(state), WHY_DETERMINED, np.int8)
    why[np.asarray(state) == ST_INVISIBLE] = WHY_INVISIBLE
    mis = np.asarray(missing_ids, np.int64)
    if len(mis):
        Jm = np.asarray(J)[mis]
        any_support = np.isfinite(np.asarray(k_dist)[:, 0])
        why[mis[Jm == J_MIXED]] = WHY_MIXED
        why[mis[(Jm == J_INSUFF) & ~any_support]] = WHY_NO_SUPPORT_ON_SURFACE
        why[mis[(Jm == J_INSUFF) & any_support]] = WHY_TOO_FEW_WITHIN_DISTANCE
    return why


def prior_term_off(located, judgment_of_unit, A, mark):
    """True where g_p = 0 (decision 1 / 3). located [..] bool (the pixel sees a judgment unit); judgment_of_unit [..] the
    judgment that unit carries (locations.location_judgment: J_AGREE / J_CONFLICT for a support unit's vote, the
    propagated J_* for a missing one; read alike); A [..] observation confidence (0/1); mark [..] MARK_* of the pixel.
    numpy arrays or torch tensors; g_p = 1 - prior_term_off(...)."""
    unit_conflict = located & (judgment_of_unit == J_CONFLICT)
    pixel_conflict = ~located & (A > 0.5) & (mark == MARK_CONFLICT)
    return unit_conflict | pixel_conflict
