"""Pilot-specific MVS seed initialization controls."""
from __future__ import annotations

import numpy as np


DEFAULT_INIT_OPACITY = 0.10


def apply_mvs_seed_init_opacity(
    n_points: int,
    mvs_seed_mask: np.ndarray | None,
    existing: np.ndarray | None,
    requested_opacity: float | None,
) -> np.ndarray | None:
    """Return an explicit opacity vector when the pilot requests one.

    Legacy runs remain byte-path compatible: ``requested_opacity=None``
    returns ``existing`` unchanged.  For photo-control and plane arms, MVS
    lineage rows are initialized at 0.25 while all non-MVS rows retain their
    existing value (or the historical 0.10 default).
    """

    if requested_opacity is None:
        return existing
    value = float(requested_opacity)
    if not 0.0 < value < 1.0:
        raise ValueError("mvs_seed_init_opacity must lie in (0,1)")
    if mvs_seed_mask is None:
        raise ValueError("mvs_seed_init_opacity requires an MVS init point cloud")
    mask = np.asarray(mvs_seed_mask)
    if mask.dtype != np.bool_ or mask.shape != (int(n_points),):
        raise ValueError("MVS seed mask must be bool and aligned with all init points")
    if not bool(mask.any()):
        raise ValueError("MVS seed mask is empty")
    if existing is None:
        output = np.full(int(n_points), DEFAULT_INIT_OPACITY, dtype=np.float32)
    else:
        current = np.asarray(existing)
        if current.shape != (int(n_points),) or not np.isfinite(current).all():
            raise ValueError("existing init opacity must be a finite N-vector")
        output = current.astype(np.float32, copy=True)
    output[mask] = np.float32(value)
    return output
