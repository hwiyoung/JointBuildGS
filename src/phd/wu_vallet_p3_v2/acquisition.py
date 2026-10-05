"""Recover acquisition coordinates from recorded pulse time and scan angle.

No spatial triangulation or sensor-position estimate occurs here. Exact equal
GPS time is grouped only within a strip. Returns remain separate original rows.
Scan boundaries require a recurrent angle reset; missing metadata fails closed.
"""
from __future__ import annotations

import numpy as np


def group_pulses(time, strip, return_number, number_of_returns, xyz):
    time = np.asarray(time, dtype=np.float64)
    strip = np.asarray(strip)
    rn, nr = np.asarray(return_number), np.asarray(number_of_returns)
    xyz = np.asarray(xyz, dtype=np.float64)
    n = len(time)
    if not n or any(len(a) != n for a in [strip, rn, nr, xyz]):
        raise ValueError("Nonempty equal-length fields required")
    if xyz.shape != (n, 3) or not np.isfinite(time).all() or not np.isfinite(xyz).all():
        raise ValueError("Finite GPS time and XYZ required")
    if (rn < 1).any() or (nr < rn).any():
        raise ValueError("Invalid return indices")
    order = np.lexsort((rn, time, strip))
    start_mask = np.r_[True, (strip[order[1:]] != strip[order[:-1]]) |
                       (time[order[1:]] != time[order[:-1]])]
    starts = np.flatnonzero(start_mask)
    stops = np.r_[starts[1:], n]
    counts = stops - starts
    first, last = order[starts], order[stops - 1]
    group_sorted = np.cumsum(start_mask) - 1
    ids = np.empty(n, dtype=np.int64)
    ids[order] = group_sorted
    duplicate = np.zeros(len(starts), dtype=bool)
    duplicate_group = group_sorted[1:][(~start_mask[1:]) & (rn[order[1:]] == rn[order[:-1]])]
    duplicate[duplicate_group] = True
    min_nr = np.minimum.reduceat(nr[order], starts)
    max_nr = np.maximum.reduceat(nr[order], starts)
    ambiguous = duplicate | (min_nr != max_nr)
    complete = (~ambiguous) & (rn[first] == 1) & (rn[last] == nr[first]) & (counts == nr[first])
    return dict(context_pulse_id=ids, pulse_gps_time=time[first], pulse_strip=strip[first],
                pulse_first_context_row=first, pulse_last_context_row=last,
                pulse_first_xyz=xyz[first], pulse_last_xyz=xyz[last], pulse_return_count=counts,
                pulse_first_return_number=rn[first], pulse_last_return_number=rn[last],
                pulse_number_of_returns=nr[first], pulse_complete=complete, pulse_ambiguous=ambiguous,
                pulse_observed_return_span_m=np.linalg.norm(xyz[last] - xyz[first], axis=1))


def recover_scan_coordinates(time, angle, reset_degrees=5.0, minimum_boundaries=4):
    """One strip, sorted unique pulses. Angle resets define observed scan lines.

    Positive or negative reset direction is inferred from the recurring large
    jumps. Both directions recurring is unsupported oscillatory acquisition.
    Continuous beam_coordinate preserves GPS gaps instead of joining across
    missing pulses. beam_order is merely recorded-pulse rank inside a scan.
    """
    t, a = np.asarray(time, dtype=np.float64), np.asarray(angle, dtype=np.float64)
    if len(t) < 3 or t.shape != a.shape or not np.isfinite(t).all() or not np.isfinite(a).all():
        raise ValueError("Finite equal-length pulse time and angle required")
    dt, da = np.diff(t), np.diff(a)
    if (dt <= 0).any() or reset_degrees <= 0:
        raise ValueError("Strict pulse order and positive reset threshold required")
    pos, neg = da >= reset_degrees, da <= -reset_degrees
    if min(pos.sum(), neg.sum()) > 0:
        raise ValueError("Mixed large-angle directions: unsupported or ambiguous acquisition")
    resets = pos if pos.sum() else neg
    boundary_rows = np.flatnonzero(resets) + 1
    if len(boundary_rows) < minimum_boundaries:
        raise ValueError("Too few recurrent angle resets for scan recovery")
    period = np.diff(t[boundary_rows])
    period_median = float(np.median(period))
    if np.quantile(abs(period / period_median - 1), .95) > .1:
        raise ValueError("Irregular scan boundary intervals")
    starts = np.r_[0, boundary_rows]
    scan = np.cumsum(np.r_[False, resets]).astype(np.int32)
    beam_order = np.arange(len(t), dtype=np.int64) - starts[scan]
    typical = dt[dt < np.quantile(dt, .5) * 1.5]
    pulse_interval = float(typical.mean())
    beam_coordinate = (t - t[starts[scan]]) / pulse_interval
    complete_scan = (scan > 0) & (scan < len(starts) - 1)
    # Quantized angles may remain constant; every non-reset step should follow
    # the opposite direction to the reset. Violations remain visible in audit.
    reset_sign = 1 if pos.sum() else -1
    violation = (~resets) & (da * reset_sign > 0)
    report = dict(reset_degrees=float(reset_degrees), reset_sign=reset_sign,
                  boundary_count=int(len(boundary_rows)), observed_scan_count=int(len(starts)),
                  complete_scan_count=int(max(0, len(starts) - 2)),
                  scan_period_seconds_quantiles=np.quantile(period, [0, .1, .5, .9, 1]).tolist(),
                  typical_pulse_interval_seconds=pulse_interval,
                  nonreset_angle_reversal_count=int(violation.sum()),
                  gps_gap_seconds_quantiles=np.quantile(dt, [0, .5, .9, .99, .999, 1]).tolist(),
                  missing_pulse_gap_count=int(((dt > 1.5 * pulse_interval) & ~resets).sum()),
                  inferred_missing_pulses_approximate=int(np.maximum(np.rint(dt[~resets] / pulse_interval) - 1, 0).sum()),
                  interpretation="Observed scan order from recorded angle resets; scan timing is not sensor origin or independently validated acquisition calibration")
    return dict(scan_id=scan, beam_order=beam_order, beam_coordinate=beam_coordinate,
                complete_scan=complete_scan, boundary_rows=boundary_rows,
                report=report)
