"""Audit one frozen input-region mask without consulting evaluation geometry."""
import numpy as np


def bounds_mask(xyz, bounds):
    inside = np.isfinite(xyz).all(axis=-1)
    for axis, key in enumerate(('x', 'y', 'z')):
        inside &= (xyz[..., axis] >= bounds[key][0]) & (xyz[..., axis] < bounds[key][1])
    return inside


def array_stats(array):
    values = np.asarray(array)
    values = values[np.isfinite(values)]
    if not values.size:
        return {'count': 0}
    return {'count': int(values.size), 'min': float(values.min()),
            'q01': float(np.quantile(values, .01)), 'median': float(np.median(values)),
            'q99': float(np.quantile(values, .99)), 'max': float(values.max())}


def audit_mask(native, rgb_depth, view, native_masks, rgb_masks, manual_labels_native,
               extra_exclusions_native, cfg, unproject, resample_nearest):
    """Preserve frozen R1; only explicit inspection exclusions can remove pixels."""
    if native.shape != (741, 1024) or rgb_depth.shape != (1013, 1400):
        raise ValueError('Unexpected frozen P1 raster dimensions')
    valid_native = np.isfinite(native) & (native > 0)
    valid_rgb = np.isfinite(rgb_depth) & (rgb_depth > 0)
    if native_masks['valid'].dtype != np.bool_ or rgb_masks['valid'].dtype != np.bool_:
        raise ValueError('Use the corrected boolean-mask lineage')
    if not np.array_equal(valid_native, native_masks['valid']) or not np.array_equal(valid_rgb, rgb_masks['valid']):
        raise ValueError('Frozen masks and current depth validity differ')
    original_native = native_masks['region_id'] == 1
    original_rgb = rgb_masks['region_id'] == 1
    Kn = view['maps']['depth']['K']
    remapped = resample_nearest(original_native, Kn, view['K'], 1400, 1013, False)
    if remapped.dtype != np.bool_ or not np.array_equal(remapped, original_rgb):
        raise ValueError('Frozen native/RGB R1 does not match the exact native nearest sampler')
    xyz = unproject(native, np.asarray(Kn), view['R'], view['t'])
    context = bounds_mask(xyz, cfg['training_context'])
    evaluation = bounds_mask(xyz, cfg['evaluation_roi'])
    r1_native = original_native & ~extra_exclusions_native
    if not r1_native.any() or np.any(r1_native & ~valid_native) or np.any(r1_native & ~context):
        raise ValueError('R1 must be nonempty and inside valid current-MVS context')
    if np.any(r1_native & (manual_labels_native != 3)):
        raise ValueError('R1 overlaps a manually excluded, building or unknown source label')
    r1_mask = resample_nearest(r1_native, Kn, view['K'], 1400, 1013, False)
    if r1_mask.dtype != np.bool_ or np.any(r1_mask & ~valid_rgb):
        raise ValueError('Training R1 must be boolean and depth-valid')
    evaluation_rgb = resample_nearest(evaluation, Kn, view['K'], 1400, 1013, False)
    context_rgb = resample_nearest(context, Kn, view['K'], 1400, 1013, False)
    xyz_rgb = resample_nearest(xyz, Kn, view['K'], 1400, 1013, np.nan)
    if cfg['support_policy'] != 'manual_regions_1_2_3_only':
        raise ValueError('This revision requires the user-approved manual-region support policy')
    use_native = np.isin(native_masks['region_id'], [1, 2, 3]) & valid_native
    use_mask = np.isin(rgb_masks['region_id'], [1, 2, 3]) & valid_rgb
    mapped_use = resample_nearest(use_native, Kn, view['K'], 1400, 1013, False)
    if not np.array_equal(mapped_use, use_mask) or np.any(r1_mask & ~use_mask):
        raise ValueError('Manual support must match native nearest sampling and include R1')
    weight_checks = []
    for alpha in cfg['alpha_values']:
        weight = use_mask.astype(np.float32)
        weight[r1_mask] = alpha
        if np.any(weight[use_mask & ~r1_mask] != 1) or np.any(weight[~use_mask] != 0):
            raise ValueError('R2/R3 must stay one and R4/R5/R6/invalid must stay zero')
        weight_checks.append({'alpha': alpha, 'r1_pixels': int(r1_mask.sum()),
                             'r2_r3_weight_one': True, 'excluded_unknown_outside_invalid_weight_zero': True,
                             'weight_zero_pixels': int((weight == 0).sum()),
                             'weight_one_pixels': int((weight == 1).sum()),
                             'weight_four_pixels': int((weight == 4).sum())})
    counts = {'original_native_r1': int(original_native.sum()), 'original_rgb_r1': int(original_rgb.sum()),
              'final_native_r1': int(r1_native.sum()), 'final_rgb_r1': int(r1_mask.sum()),
              'removed_native_r1': int((original_native & ~r1_native).sum()),
              'removed_rgb_r1': int((original_rgb & ~r1_mask).sum()),
              'native_r1_inside_30m_prism': int((r1_native & evaluation).sum()),
              'native_r1_outside_30m_prism_inside_80m_context': int((r1_native & ~evaluation).sum()),
              'rgb_r1_inside_30m_prism': int((r1_mask & evaluation_rgb).sum()),
              'rgb_r1_outside_30m_prism_inside_80m_context': int((r1_mask & ~evaluation_rgb).sum()),
              'valid_native': int(valid_native.sum()), 'valid_rgb': int(valid_rgb.sum()),
              'use_native': int(use_native.sum()), 'use_rgb': int(use_mask.sum()),
              'valid_but_not_used_native': int((valid_native & ~use_native).sum()),
              'valid_but_not_used_rgb': int((valid_rgb & ~use_mask).sum()),
              'r1_invalid_pixels': 0, 'r1_outside_context_pixels': 0,
              'r1_manual_exclusion_building_unknown_overlap': 0}
    mask_arrays = {'r1_mask': r1_mask, 'use_mask': use_mask, 'r1_native': r1_native,
                   'use_native': use_native, 'valid_rgb': valid_rgb, 'valid_native': valid_native,
                   'region_id': rgb_masks['region_id'].copy(),
                   'region_id_native': native_masks['region_id'].copy()}
    diagnostic = {'evaluation_rgb': evaluation_rgb, 'context_rgb': context_rgb,
                  'xyz_rgb': xyz_rgb, 'original_r1_rgb': original_rgb}
    stats = {'counts': counts, 'r1_native_camera_z_m': array_stats(native[r1_native]),
             'r1_native_local_xyz_m': {key: array_stats(xyz[..., axis][r1_native])
                                       for axis, key in enumerate(('x', 'y', 'z'))},
             'r1_rgb_bbox_xyxy': [int(np.where(r1_mask)[1].min()), int(np.where(r1_mask)[0].min()),
                                  int(np.where(r1_mask)[1].max()+1), int(np.where(r1_mask)[0].max()+1)],
             'weight_contract_checks': weight_checks,
             'region_counts': {grid: {str(r): {'all': int((labels == r).sum()),
                                                'valid': int(((labels == r) & valid).sum())}
                                        for r in range(1, 7)}
                              for grid, labels, valid in [('rgb', rgb_masks['region_id'], valid_rgb),
                                                          ('native', native_masks['region_id'], valid_native)]}}
    return mask_arrays, diagnostic, stats
