"""v4.0 allocation/budget candidate, separate from observation score estimation.

q is the requested final image allocation, NOT image reliability or the v3.8 SI.
For two active sources, maximize depth strength while respecting that allocation
and each original effective coefficient cap. No image, GT, or GS dependency.
"""

import numpy as np


def _real(value, name):
    if np.iscomplexobj(value):
        raise ValueError(f"{name} must be real")
    try:
        result = np.asarray(value, dtype=np.float64)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if np.any(~np.isfinite(result)):
        raise ValueError(f"{name} must be finite")
    return result


def weight_from_allocation(q, cP, cI, *, prior_status="active", image_status="active",
                           single_image_admission=None):
    """Return weights and explicit allocation/availability metadata as NumPy arrays.

    Numeric inputs and source status arrays broadcast. Status is one of active,
    missing, disabled. A source must also have a positive coefficient to be active.
    Missing and disabled retain separate metadata; both imply zero supervision.

    When both sources are active, 0<q<1 uses
      s = min(cP/(1-q), cI/q), wP=s*(1-q), wI=s*q.
    q=0 gives (cP,0); q=1 gives (0,cI). This is continuous on a fixed active set.
    It does not guarantee a minimum total strength or unchanged strength when
    the two targets coincide. Weights and targets need detaching in training.

    With prior inactive, q is not a justified single-image quality estimate:
    absent separate admission gives zero; provided admission in [0,1] gives
    wI=cI*admission. With image inactive and prior active, wP=cP. Other GS losses
    are outside this function. Admission is ignored when both sources are active.
    """
    q, cp, ci = (_real(value, name) for value, name in ((q, "q"), (cP, "cP"), (cI, "cI")))
    admission_supplied = single_image_admission is not None
    admission = _real(single_image_admission if admission_supplied else 0., "single_image_admission")
    ps, ins = np.asarray(prior_status, dtype=str), np.asarray(image_status, dtype=str)
    if np.any(~np.isin(ps, ["active", "missing", "disabled"])) or np.any(~np.isin(ins, ["active", "missing", "disabled"])):
        raise ValueError("source status must be active, missing, or disabled")
    try:
        q, cp, ci, admission, ps, ins = np.broadcast_arrays(q, cp, ci, admission, ps, ins)
    except ValueError as exc:
        raise ValueError("all inputs must broadcast") from exc
    if np.any((q < 0) | (q > 1)) or np.any((admission < 0) | (admission > 1)):
        raise ValueError("q and admission must lie in [0,1]")
    if np.any(cp < 0) or np.any(ci < 0):
        raise ValueError("coefficient caps must be nonnegative")
    with np.errstate(over="ignore"):
        original_budget = cp + ci
    if np.any(~np.isfinite(original_budget)):
        raise ValueError("original coefficient budget must be finite")
    pa, ia = (ps == "active") & (cp > 0), (ins == "active") & (ci > 0)
    both = pa & ia
    interior = both & (q > 0) & (q < 1)
    with np.errstate(divide="ignore", over="ignore", invalid="ignore"):
        p_limit = np.divide(cp, 1 - q, out=np.full_like(q, np.inf), where=interior)
        i_limit = np.divide(ci, q, out=np.full_like(q, np.inf), where=interior)
    strength = np.where(interior, np.minimum(p_limit, i_limit), 0.)
    strength = np.where(both & (q == 0), cp, strength)
    strength = np.where(both & (q == 1), ci, strength)
    wp, wi = strength * (1 - q), strength * q
    wp = np.where(pa & ~ia, cp, wp)
    wi = np.where(ia & ~pa, ci * admission, wi)
    strength = wp + wi
    defined = strength > 0
    actual_q = np.divide(wi, strength, out=np.zeros_like(q), where=defined)
    return {"wP": wp, "wI": wi, "strength": strength,
            "q_requested": q, "q_effective": actual_q, "q_defined": defined,
            "requested_q_applicable": both, "prior_status": ps, "image_status": ins,
            "prior_active": pa, "image_active": ia,
            "prior_coefficient_zero": cp == 0, "image_coefficient_zero": ci == 0,
            "single_image_admission_supplied": np.full(q.shape, admission_supplied),
            "single_image_admission_used": ia & ~pa & admission_supplied,
            "original_budget": original_budget,
            "active_source_budget": np.where(pa, cp, 0.) + np.where(ia, ci, 0.)}
