"""Ablation switches of the method (prior_propagation_v5, PHD-MAIN-PREP-DISCARD-RULE-v1; configs discard_v1.json 'switches').

Names and defaults shared by the measurement and the training fork; default all on = the method as it is. Judgment-level
switches are applied here (numpy); the training-time switches (prior band, protection, prior, the MVS term weight) are applied
by the fork with these names.
  confidence_mask   off: COLMAP photometric depth (before the geometric filter) is the MVS depth and every pixel with a depth
                    has confidence 1 (the states then come from a pass 3 with that confidence)
  judgment          off: every patch judgment = agree; pixels without a patch also g_p = 1 (nothing discarded anywhere)
  propagation       off: missing patches all 'insufficient' (inherit); support votes unchanged
  prior_band        off: rho(r) = |r| (no tolerance band, no truncation)
  protection        off: no protection mask (no lr scaling, no densify / prune exclusion, no reset exemption, no floor)
  init_exclusion    off: points of missing patches judged conflict are planted too; judgments unchanged
  prior             off: no prior-origin Gaussians, no prior depth term
scientific_verdict: null."""
import numpy as np

from . import locations
from . import rule

NAMES = ("confidence_mask", "judgment", "propagation", "prior_band", "protection", "init_exclusion", "prior")
DEFAULT = {n: True for n in NAMES}


def judgment_level(state, vote, J, sw):
    """(vote, J, J_loc) after the judgment-level switches (judgment, propagation); unchanged when both are on."""
    state = np.asarray(state); vote = np.asarray(vote).copy(); J = np.asarray(J).copy()
    if not sw.get("propagation", True):
        J = np.where(state == rule.ST_MISSING, rule.J_INSUFF, rule.J_NONE).astype(np.int8)
    if not sw.get("judgment", True):
        vote = np.where(state == rule.ST_SUPPORT, rule.V_AGREE, rule.V_NONE).astype(np.int8)
        J = np.where(state == rule.ST_MISSING, rule.J_AGREE, rule.J_NONE).astype(np.int8)
    return vote, J, locations.location_judgment(state, vote, J)


def planted(state, J_loc, sw):
    """False for the prior points that initialisation does not plant (missing patch judged conflict), per patch."""
    drop = (np.asarray(state) == rule.ST_MISSING) & (np.asarray(J_loc) == rule.J_CONFLICT)
    if not sw.get("init_exclusion", True):
        drop = np.zeros_like(drop)
    return ~drop
