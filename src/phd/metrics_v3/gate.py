"""Gate of stage 1 (PHD-MAIN-STAGE1-v1 2.2): repeatability s_r pooled over cells, r = 2.8 s_r, the three-way decision, the pass rule."""
import numpy as np

MET, NOT_MET, UNDECIDABLE = "met", "not met", "undecidable"          # the three ways (undecidable: the difference within r)
FEW_SAMPLES, NO_VALUE = "undecidable (samples < 10,000)", "no value"     # units that cannot be judged


def pooled_sr(pairs):
    """pairs: list of (x1, x2) of the proposed method per cell (two seeds). s_r^2 = mean over cells of (x1 - x2)^2 / 2 (ISO 5725-2,
    n = 2 per cell); degrees of freedom = number of cells. Cells with a missing value are left out. Returns (s_r, dof)."""
    d = [(float(a) - float(b)) ** 2 / 2.0 for a, b in pairs if a is not None and b is not None and np.isfinite(a) and np.isfinite(b)]
    if not d:
        return float("nan"), 0
    return float(np.sqrt(np.mean(d))), len(d)


def limit(s_r):
    return 2.8 * s_r


def decide(proposed, comparator, r, kind="lower", samples=None, min_samples=10000):
    """kind 'lower' (conditions 1-3: the proposed value should be lower / smaller): comparator - proposed > r -> met,
    proposed - comparator > r -> not met, else undecidable. kind 'not_lower' (condition 4: completeness should not be lower):
    comparator - proposed > r -> not met, else met. Fewer samples than min_samples -> FEW_SAMPLES; a missing value -> NO_VALUE."""
    if samples is not None and samples < min_samples:
        return FEW_SAMPLES
    if proposed is None or comparator is None or not np.isfinite(proposed) or not np.isfinite(comparator) or not np.isfinite(r):
        return NO_VALUE
    diff = comparator - proposed
    if kind == "lower":
        if diff > r:
            return MET
        if -diff > r:
            return NOT_MET
        return UNDECIDABLE
    if kind == "not_lower":
        return NOT_MET if diff > r else MET
    raise ValueError(kind)


def passes(table):
    """table: {condition: {unit: decision}}. A condition without a judgeable unit (all FEW_SAMPLES / NO_VALUE) cannot be decided and
    is left out; pass = no 'not met' anywhere and at least one 'met' in every other condition. Returns (passed, per-condition summary)."""
    summ, ok = {}, True
    for cond, units in table.items():
        vals = list(units.values())
        judgeable = [v for v in vals if v in (MET, NOT_MET, UNDECIDABLE)]
        nm = sum(v == NOT_MET for v in judgeable)
        mt = sum(v == MET for v in judgeable)
        summ[cond] = dict(met=mt, not_met=nm, undecidable=len(judgeable) - mt - nm, not_judgeable=len(vals) - len(judgeable),
                          cannot_be_decided=len(judgeable) == 0)
        if not judgeable:
            continue
        if nm or not mt:
            ok = False
    return ok, summ
