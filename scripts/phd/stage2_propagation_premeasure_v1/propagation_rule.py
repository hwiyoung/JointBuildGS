"""Pre-measurement v1 rule functions (PHD-STAGE2-PROPAGATION-PREMEASURE-v1) -- now a thin shim over the shared module
src/phd/prior_propagation_v1 (PHD-STAGE2-R7-PROPAGATION-v1: the rule lives in one place, used by the training fork too).

judge, grid_edges and csr are the shared functions (identical code to the v1 copies they replace). location_state keeps
the v1 tie rule of the archived v1 results (a tied vote of the measuring views is broken by the pooled pixel counts, then
agree); the method document's rule (a tie is agree) is src/phd/prior_propagation_v1/rule.location_state. v1 is superseded
by scripts/phd/stage2_r7_propagation_v1/premeasure_v2.py; the v1 original of this file is kept in the r7 payload
(provenance/superseded/premeasure_v1_propagation_rule.py)."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from src.phd.prior_propagation_v1.locations import csr, grid_edges  # noqa: E402,F401
from src.phd.prior_propagation_v1.rule import (J_AGREE, J_CONFLICT, J_INSUFF, J_MIXED, ST_INVISIBLE, ST_MISSING,  # noqa: E402,F401
                                               ST_SUPPORT, V_AGREE, V_CONFLICT, judge)

J_NAMES = ["conflict", "agree", "mixed", "insufficient"]     # v1 list form (index = judgment code)


def location_state(n_pix, n_a1, n_ag, n_cf):
    """v1 rule (archived results): support / missing / invisible as the shared rule; vote = majority of the measuring
    views' marks, a tie broken by the pooled pixel counts of those views, an exact tie agree. Returns (state, vote,
    n_obs, n_meas) like v1."""
    obs = n_pix > 0
    meas = obs & (2 * n_a1 >= n_pix)
    vagree = n_ag >= n_cf
    n_obs = obs.sum(0); n_meas = meas.sum(0)
    state = np.full(n_pix.shape[1], ST_INVISIBLE, np.int8)
    state[(n_obs > 0) & (2 * n_meas >= n_obs)] = ST_SUPPORT
    state[(n_obs > 0) & (2 * n_meas < n_obs)] = ST_MISSING
    av = (meas & vagree).sum(0); cv = (meas & ~vagree).sum(0)
    pool_ag = (n_ag * meas).sum(0); pool_cf = (n_cf * meas).sum(0)
    vote = np.where(cv > av, V_CONFLICT, np.where(av > cv, V_AGREE, np.where(pool_cf > pool_ag, V_CONFLICT, V_AGREE))).astype(np.int8)
    vote[state != ST_SUPPORT] = -1
    return state, vote, n_obs, n_meas
