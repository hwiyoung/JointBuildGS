"""Standalone v3.8 algebra candidate; not a training or confidence estimator.

The external observation gate must certify whether the costs may be interpreted.
Unknown visibility/correspondence means gate=0. Setting gate=1 without that
validation is a hypothetical cost-only probe, not measured source confidence.
The fixed 0.10/0.30/0.50 cost knots are development candidates, not calibrated
accuracy thresholds. This module has no reference, photograph, or GS dependency.
"""

import numpy as np


def _as_real_array(value, name):
    if np.iscomplexobj(value):
        raise ValueError(f"{name} must be real")
    try:
        return np.asarray(value, dtype=np.float64)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a real numeric array") from exc


def evidence_from_costs(costs, observation_gate):
    """Return support, rejection, unknown arrays, broadcasting batch dimensions.

    ``costs`` has shape (..., 3), for three scales, and finite costs in [0, 1].
    NaN/Inf/None costs are permitted only for entries with gate=0, which return
    (0, 0, 1). The finite gate lies in [0, 1] and broadcasts with costs.shape[:-1].
    All three scales must support the same conclusion; a scale reversal remains
    unknown. Outputs are evidence amounts, not calibrated probabilities.
    """
    costs = _as_real_array(costs, "costs")
    gate = _as_real_array(observation_gate, "observation_gate")
    if costs.ndim < 1 or costs.shape[-1] != 3:
        raise ValueError("costs must have exactly three scales on the last axis")
    if np.any(~np.isfinite(gate) | (gate < 0) | (gate > 1)):
        raise ValueError("observation_gate must be finite and in [0, 1]")
    if np.any(np.isfinite(costs) & ((costs < 0) | (costs > 1))):
        raise ValueError("finite costs must be in [0, 1]")
    try:
        gate, _ = np.broadcast_arrays(gate, costs[..., 0])
        costs = np.broadcast_to(costs, gate.shape + (3,))
    except ValueError as exc:
        raise ValueError("gate and cost batch dimensions must broadcast") from exc
    if np.any((gate > 0) & ~np.all(np.isfinite(costs), axis=-1)):
        raise ValueError("positive observation_gate requires three finite costs")
    # Avoid evaluating missing costs even when the output is forced to unknown.
    usable_costs = np.where(gate[..., None] > 0, costs, 0.30)
    support = gate * np.min(np.clip((0.30 - usable_costs) / 0.20, 0, 1), axis=-1)
    rejection = gate * np.min(np.clip((usable_costs - 0.30) / 0.20, 0, 1), axis=-1)
    unknown = 1.0 - support - rejection
    return support, rejection, unknown


def weight_from_evidence(cP, cI, SP, RP, SI, RI):
    """Return prior/image effective coefficients using conservative budget transfer.

    All inputs broadcast. cP/cI are finite nonnegative *effective* coefficients
    including original valid-mask denominators; a missing or disabled source has
    coefficient zero. Evidence lies in [0, 1], with S+R <= 1 per source. Coefficient
    zero prevents transfer from reactivating that source. No output normalization
    is applied: unsubstantiated budget remains unused, and wP+wI <= cP+cI.

    Targets and maps must be detached if integrated into a differentiable loss.
    Returning zero depth weights does not disable other GS losses or updates.
    """
    names = ("cP", "cI", "SP", "RP", "SI", "RI")
    values = tuple(_as_real_array(v, n) for v, n in zip((cP, cI, SP, RP, SI, RI), names))
    try:
        cP, cI, SP, RP, SI, RI = np.broadcast_arrays(*values)
    except ValueError as exc:
        raise ValueError("coefficient and evidence dimensions must broadcast") from exc
    for value, name in zip((cP, cI, SP, RP, SI, RI), names):
        if np.any(~np.isfinite(value) | (value < 0)):
            raise ValueError(f"{name} must be finite and nonnegative")
    if np.any((SP > 1) | (RP > 1) | (SI > 1) | (RI > 1)):
        raise ValueError("support and rejection must be in [0, 1]")
    if np.any((SP + RP > 1) | (SI + RI > 1)):
        raise ValueError("support plus rejection must not exceed one")
    with np.errstate(over="ignore"):
        budget = cP + cI
    if np.any(~np.isfinite(budget)):
        raise ValueError("total coefficient budget must be finite")
    wP = np.where(cP > 0, cP * (1 - RP) + cI * SP * RI, 0.0)
    wI = np.where(cI > 0, SI * (cI + cP * RP), 0.0)
    return wP, wI
