"""Reference-only multi-scale height-detail diagnostics on a fixed XY domain.

These are 2.5D cell-median finite differences, not certified surfaces or semantic
roof-detail scores. Reference data must never be imported by the B optimizer.
"""
from __future__ import annotations
import numpy as np


def rasterize_median(xyz, bounds, spacing):
    xyz = np.asarray(xyz, dtype=float)
    bounds = np.asarray(bounds, dtype=float)
    if xyz.ndim != 2 or xyz.shape[1] != 3 or not np.isfinite(xyz).all():
        raise ValueError('finite XYZ [N,3] required')
    if bounds.shape != (2, 2) or np.any(bounds[1] <= bounds[0]) or spacing <= 0:
        raise ValueError('positive XY bounds and spacing required')
    dims = np.ceil((bounds[1]-bounds[0])/spacing).astype(int)
    ix = np.floor((xyz[:, :2]-bounds[0])/spacing).astype(int)
    valid = ((xyz[:, :2] >= bounds[0]) & (xyz[:, :2] < bounds[1])).all(1)
    cells = ix[valid, 1]*dims[0]+ix[valid, 0]
    z = xyz[valid, 2]
    order = np.argsort(cells, kind='stable')
    cells, z = cells[order], z[order]
    start = np.r_[0, np.flatnonzero(np.diff(cells))+1]
    end = np.r_[start[1:], len(cells)]
    height = np.full(dims.prod(), np.nan)
    counts = np.zeros(dims.prod(), dtype=np.int64)
    if len(cells):
        for a, b in zip(start, end):
            height[cells[a]] = np.median(z[a:b])
            counts[cells[a]] = b-a
    return height.reshape(dims[1], dims[0]), counts.reshape(dims[1], dims[0])


def detail_residual(height):
    """Centre minus neighbour mean; affine values on a regular grid vanish.

    Irregular within-cell median samples of an affine plane need not vanish.
    """
    height = np.asarray(height, dtype=float)
    if min(height.shape) < 3:
        raise ValueError('at least 3x3 raster required')
    c = height[1:-1, 1:-1]
    neighbours = np.stack([height[:-2, 1:-1], height[2:, 1:-1],
                           height[1:-1, :-2], height[1:-1, 2:]])
    valid = np.isfinite(c) & np.isfinite(neighbours).all(0)
    residual = np.full_like(c, np.nan)
    residual[valid] = c[valid] - neighbours[:, valid].mean(0)
    return residual, valid


def residual_stats(values):
    values = np.asarray(values)
    values = values[np.isfinite(values)]
    if not len(values):
        return dict(count=0, rmse_m=None, mae_m=None, p90_abs_m=None)
    return dict(count=int(len(values)), rmse_m=float(np.sqrt(np.mean(values**2))),
                mae_m=float(np.abs(values).mean()), p90_abs_m=float(np.quantile(np.abs(values), .9)))


def paired_detail_metrics(initial, final, reference, bounds, spacings=(.25, .5, 1.)):
    results = []
    for spacing in spacings:
        grids = [rasterize_median(p, bounds, spacing)[0] for p in [initial, final, reference]]
        details = [detail_residual(h) for h in grids]
        before, after, truth = [d[0] for d in details]
        bi, fi, ri = [d[1] for d in details]
        common = bi & fi & ri
        fixed_ref_count = int(ri.sum())
        results.append(dict(
            spacing_m=float(spacing), grid_shape=list(grids[0].shape),
            reference_eligible_stencils=fixed_ref_count,
            initial_supported_reference_stencils=int((bi & ri).sum()),
            final_supported_reference_stencils=int((fi & ri).sum()),
            initial_missing_reference_stencils=int((~bi & ri).sum()),
            final_missing_reference_stencils=int((~fi & ri).sum()),
            common_initial_final_reference_stencils=int(common.sum()),
            initial_error_common=residual_stats((before-truth)[common]),
            final_error_common=residual_stats((after-truth)[common]),
            initial_detail_amplitude_common=residual_stats(before[common]),
            final_detail_amplitude_common=residual_stats(after[common]),
            reference_detail_amplitude_common=residual_stats(truth[common]),
            reference_cells=int(np.isfinite(grids[2]).sum()),
            initial_present_reference_cells=int((np.isfinite(grids[0]) & np.isfinite(grids[2])).sum()),
            final_present_reference_cells=int((np.isfinite(grids[1]) & np.isfinite(grids[2])).sum()),
        ))
    return {'definition': 'cell median Z minus four-neighbour mean; metric residual, not derivative divided by spacing squared',
            'scope': '2.5D XY grid diagnostic; mixed layers, sampling and reference noise can affect scores; not a claim of restored semantic detail',
            'bounds_xy': np.asarray(bounds).tolist(), 'scientific_verdict': None, 'scales': results}


def common_detail_fields(arms, reference):
    """Compare precomputed residual fields on one all-arm paired support mask."""
    truth, ref_valid = reference
    common = ref_valid.copy()
    for stages in arms.values():
        for values, valid in stages.values():
            if values.shape != truth.shape or valid.shape != truth.shape:
                raise ValueError('All detail fields must share the same fixed grid')
            common &= valid
    rows = {}
    for name, stages in arms.items():
        rows[name] = {phase: dict(
            error_common=residual_stats((values-truth)[common]),
            supported_reference_stencils=int((valid & ref_valid).sum()),
            missing_reference_stencils=int((~valid & ref_valid).sum()))
            for phase, (values, valid) in stages.items()}
    return dict(common_stencils=int(common.sum()), reference_stencils=int(ref_valid.sum()),
                excluded_reference_stencils=int((ref_valid & ~common).sum()), arms=rows)
