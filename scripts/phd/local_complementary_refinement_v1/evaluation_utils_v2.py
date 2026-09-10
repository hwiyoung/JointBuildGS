"""Version 2: fixed-membership comparisons; references never choose training.

Proximity transitions use a strict distance < threshold convention. Source
target-Z strata retain the historical <= boundary and are explicitly proxies.
"""
import csv
import hashlib
import json
from pathlib import Path

import numpy as np


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def write_csv(path, rows):
    keys = list(dict.fromkeys(key for row in rows for key in row))
    with Path(path).open('x', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=keys or ['status'])
        writer.writeheader()
        writer.writerows(rows)


def safe_child(root, relative):
    root, relative = Path(root).resolve(), Path(relative)
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('Expected a relative path without traversal: '+str(relative))
    result = root/relative
    if not result.resolve().is_relative_to(root):
        raise ValueError('Path or symlink escapes its source root: '+str(result))
    return result


def finite_statistics(values):
    values = np.asarray(values, dtype=np.float64)
    finite = values[np.isfinite(values)]
    return dict(count=int(values.size), finite_count=int(finite.size),
                nonfinite_count=int(values.size-finite.size),
                mean_m=float(finite.mean()) if finite.size else None,
                median_m=float(np.median(finite)) if finite.size else None,
                p95_m=float(np.percentile(finite, 95)) if finite.size else None,
                rmse_m=float(np.sqrt(np.mean(finite**2))) if finite.size else None)


def validate_distances(values, count):
    values = np.asarray(values, dtype=np.float64)
    if values.shape != (count,) or np.isnan(values).any() or (values < 0).any():
        raise ValueError('Distances must match membership and be nonnegative; +inf means absent surface')
    return values


def require_membership(points, ids, expected_points, expected_ids):
    points, ids = np.asarray(points), np.asarray(ids)
    if (points.shape != (len(ids), 3) or ids.ndim != 1 or not np.issubdtype(ids.dtype, np.integer)
            or len(np.unique(ids)) != len(ids) or not np.isfinite(points).all()
            or not np.array_equal(ids, expected_ids) or not np.array_equal(points, expected_points)):
        raise ValueError('Reference original IDs, point coordinates, or ordering differ')


def paired_rows(region, candidate, comparator, kind, before, after, cohorts, thresholds,
                change_epsilon=1e-6):
    if not np.isfinite(change_epsilon) or change_epsilon < 0:
        raise ValueError('Finite nonnegative reporting epsilon required')
    before = validate_distances(before, len(before))
    after = validate_distances(after, len(before))
    result = []
    for cohort, mask in cohorts.items():
        mask = np.asarray(mask, dtype=bool)
        if mask.shape != before.shape:
            raise ValueError('Cohort membership differs from reference point count')
        old, new = before[mask], after[mask]
        finite = np.isfinite(old) & np.isfinite(new)
        delta = new[finite]-old[finite]
        base = dict(region=region, candidate=candidate, comparator=comparator, mesh_kind=kind,
                    cohort=cohort, reference_count=int(mask.sum()),
                    finite_pair_count=int(finite.sum()),
                    became_missing_count=int((np.isfinite(old) & ~np.isfinite(new)).sum()),
                    recovered_from_missing_count=int((~np.isfinite(old) & np.isfinite(new)).sum()),
                    paired_change_mean_m=float(delta.mean()) if len(delta) else None,
                    paired_change_median_m=float(np.median(delta)) if len(delta) else None,
                    paired_change_abs_p95_m=float(np.percentile(np.abs(delta),95)) if len(delta) else None,
                    farther_finite_count=int((delta>change_epsilon).sum()),
                    closer_finite_count=int((delta< -change_epsilon).sum()),
                    equal_finite_distance_count=int((np.abs(delta)<=change_epsilon).sum()),
                    distance_change_reporting_epsilon_m=float(change_epsilon),
                    numerical_equality_is_effect_or_significance_test=False,
                    comparator_mean_finite_m=float(old[np.isfinite(old)].mean()) if np.isfinite(old).any() else None,
                    candidate_mean_finite_m=float(new[np.isfinite(new)].mean()) if np.isfinite(new).any() else None,
                    interpretation='reference-point proximity transitions; not area preservation, shape identity, or temporal truth')
        for threshold in thresholds:
            if not np.isfinite(threshold) or threshold <= 0:
                raise ValueError('Positive finite distance threshold required')
            near0, near1 = old<threshold, new<threshold
            near_count, far_count = int(near0.sum()), int((~near0).sum())
            corrected, damaged = int((~near0 & near1).sum()), int((near0 & ~near1).sum())
            retained, remaining = int((near0 & near1).sum()), int((~near0 & ~near1).sum())
            result.append(dict(base, threshold_m=float(threshold),
                comparator_near_count=near_count, comparator_far_count=far_count,
                corrected_count=corrected, damaged_count=damaged,
                retained_near_count=retained, remaining_far_count=remaining,
                unchanged_proximity_class_count=retained+remaining,
                corrected_fraction_of_comparator_far=corrected/far_count if far_count else None,
                damaged_fraction_of_comparator_near=damaged/near_count if near_count else None,
                preservation_fraction_of_comparator_near=retained/near_count if near_count else None,
                comparator_reference_recall=float(near0.mean()) if len(old) else None,
                candidate_reference_recall=float(near1.mean()) if len(old) else None))
    return result


def evaluation_cohorts(paired, anchor_distance, prior_distance=None, source_threshold=.5):
    if source_threshold != .5:
        raise ValueError('Historical source-stratum labels are fixed at 0.5m')
    error = paired['strict_target_world_z_error_median']
    strict = np.isfinite(error)
    anchor_distance = validate_distances(anchor_distance, len(error))
    base = {
        'ALL_REFERENCE': np.ones(len(error), bool),
        'STRICT_SUPPORT': strict,
        'NO_STRICT_SUPPORT': ~strict,
        'STRICT_TARGET_WITHIN_0.5M': strict & (np.abs(error)<=.5),
        'STRICT_TARGET_ABOVE_1M': strict & (error>1),
        'STRICT_TARGET_BELOW_MINUS1M': strict & (error< -1),
        'STRICT_MULTIVIEW_SPREAD_GT1': strict & (paired['strict_view_count']>=3) & (paired['strict_view_range']>1),
    }
    # All before/after methods use this same Anchor-conditioned partition.
    result = dict(base)
    for label, mask in base.items():
        result[label+'__ANCHOR_NEAR_0.5M'] = mask & (anchor_distance<.5)
        result[label+'__ANCHOR_FAR_0.5M'] = mask & (anchor_distance>=.5)
    if prior_distance is not None:
        prior_distance = validate_distances(prior_distance, len(error))
        for prior_near in (True, False):
            for target_near in (True, False):
                label = 'PRIOR_PROXIMITY_'+('NEAR' if prior_near else 'FAR')+'_IMAGE_TARGET_Z_'+('NEAR' if target_near else 'FAR')
                result[label] = strict & ((prior_distance<.5)==prior_near) & ((np.abs(error)<=.5)==target_near)
    return result


def spatial_rows(region, candidate, comparator, kind, paired, before, after, threshold=.5):
    before = validate_distances(before, len(before))
    after = validate_distances(after, len(before))
    ids, centres = paired['xy_cell_index'], paired['xy_cell_centres']
    if ids.shape != before.shape or np.any(ids<0) or np.any(ids>=len(centres)):
        raise ValueError('Spatial cell membership differs')
    finite = np.isfinite(before) & np.isfinite(after)
    delta = np.zeros(len(before)); delta[finite] = after[finite]-before[finite]
    count = np.bincount(ids, minlength=len(centres))
    finite_count = np.bincount(ids, weights=finite, minlength=len(centres))
    sums = np.bincount(ids, weights=delta, minlength=len(centres))
    near0, near1 = before<threshold, after<threshold
    gained = np.bincount(ids, weights=(~near0 & near1), minlength=len(centres))
    lost = np.bincount(ids, weights=(near0 & ~near1), minlength=len(centres))
    strict = np.bincount(ids, weights=np.isfinite(paired['strict_target_world_z_error_median']), minlength=len(centres))
    return [dict(region=region,candidate=candidate,comparator=comparator,mesh_kind=kind,
        cell_id=int(i),x_m=float(centres[i,0]),y_m=float(centres[i,1]),reference_count=int(count[i]),
        strict_reference_count=int(strict[i]),threshold_m=threshold,
        corrected_count=int(gained[i]),damaged_count=int(lost[i]),
        both_correction_and_damage=bool(gained[i]>0 and lost[i]>0),
        paired_change_mean_finite_m=float(sums[i]/finite_count[i]) if finite_count[i] else None,
        finite_pair_count=int(finite_count[i])) for i in np.flatnonzero(count)]


def validate_evaluation_spec(spec):
    """Require explicit evaluation numbers before any actual reference access."""
    fixed = {
        'thresholds_m': [.1, .2, .25, .5, 1., 2.],
        'surface_sample_spacing_m': .1, 'reference_voxel_m': .1,
        'seed': 0, 'reference_voxel_origin': [0., 0., 0.], 'xy_cell_m': .5,
        'paired_primary_threshold_m': .5, 'source_stratum_threshold_m': .5,
        'distance_change_reporting_epsilon_m': 1e-6,
    }
    for key, value in fixed.items():
        if key not in spec or spec[key] != value:
            raise ValueError('Explicit frozen evaluation setting differs: '+key)
    if spec.get('reference_for_training_or_parameter_selection') is not False:
        raise ValueError('Reference must be evaluation-only')
    if spec.get('mesh_resolutions') != [512] or spec.get('scientific_verdict', 'absent') is not None:
        raise ValueError('TSDF512 and explicit null scientific verdict required')
    return fixed


def verify_metric_cache(metrics, arrays, spec, expected_points, expected_ids):
    """Check every cached metric from its distance arrays, including failure cases."""
    require_membership(arrays['reference_points'], arrays['reference_original_indices'],
                       expected_points, expected_ids)
    d = validate_distances(arrays['reference_to_triangle_distance'], len(expected_ids))
    p = np.asarray(arrays['prediction_to_reference_distance'], dtype=float)
    if p.ndim != 1 or np.any(p < 0) or (len(d) and not np.isfinite(p).all()):
        raise ValueError('Invalid prediction distance cache')
    expected = {
        'seed': spec['seed'], 'surface_sample_spacing_m': spec['surface_sample_spacing_m'],
        'reference_voxel_size_m': spec['reference_voxel_m'],
        'reference_voxel_origin': spec['reference_voxel_origin'], 'mesh_res': 512,
        'reference_points_after_voxel': len(d), 'surface_samples': len(p),
    }
    for key, value in expected.items():
        if metrics.get(key) != value:
            raise ValueError('Cached evaluation setting/count differs: '+key)
    if metrics['xy_support']['cell_size_m'] != spec['xy_cell_m']:
        raise ValueError('Cached XY support grid differs')
    if [r['threshold_m'] for r in metrics['thresholds']] != spec['thresholds_m']:
        raise ValueError('Cached metric threshold membership differs')
    wanted_status = ('NOT_ASSESSED_REFERENCE_ABSENT' if not len(d) else
                     'RECONSTRUCTION_FAILURE' if not len(p) else 'ASSESSED_DEVELOPMENT_ONLY')
    if metrics['status'] != wanted_status:
        raise ValueError('Cached status disagrees with reference/prediction membership')
    for row in metrics['thresholds']:
        threshold = row['threshold_m']
        precision = (float(np.mean(p < threshold)) if len(p) else 0.) if len(d) else None
        recall = float(np.mean(d < threshold)) if len(d) else None
        f1 = (2*precision*recall/(precision+recall) if precision+recall else 0.) if len(d) else None
        for key, value in [('precision', precision), ('recall', recall), ('f1', f1)]:
            actual = row[key]
            if ((value is None) != (actual is None) or value is not None and
                    not np.isclose(value, actual, rtol=0, atol=1e-12)):
                raise ValueError('Cached '+key+' differs from exact distance arrays')
    return d


def three_way_rows(region, candidate, baseline, kind, anchor, global_result,
                   local_result, cohorts, thresholds):
    """Eight exhaustive Anchor/G/LC states on the exact same observed points.

    Names describe threshold proximity only: neither truth labels nor semantic
    correction. Missing surfaces are far and remain separately counted.
    """
    anchor = validate_distances(anchor, len(anchor))
    global_result = validate_distances(global_result, len(anchor))
    local_result = validate_distances(local_result, len(anchor))
    rows = []
    for cohort, mask in cohorts.items():
        mask = np.asarray(mask, dtype=bool)
        if mask.shape != anchor.shape:
            raise ValueError('Three-way cohort membership differs')
        a, g, local = anchor[mask], global_result[mask], local_result[mask]
        for threshold in thresholds:
            if not np.isfinite(threshold) or threshold <= 0:
                raise ValueError('Positive finite proximity threshold required')
            states = ((a < threshold).astype(np.uint8)*4 +
                      (g < threshold).astype(np.uint8)*2 + (local < threshold).astype(np.uint8))
            counts = np.bincount(states, minlength=8)
            row = dict(region=region, candidate=candidate, parent_condition=baseline,
                mesh_kind=kind, cohort=cohort, threshold_m=float(threshold), reference_count=len(a),
                global_corrected_count=int(counts[2]+counts[3]),
                global_correction_retained_by_local_count=int(counts[3]),
                global_correction_lost_by_local_count=int(counts[2]),
                additional_local_correction_count=int(counts[1]),
                global_damaged_count=int(counts[4]+counts[5]),
                global_damage_recovered_by_local_count=int(counts[5]),
                global_damage_remaining_in_local_count=int(counts[4]),
                additional_local_damage_count=int(counts[6]),
                anchor_valid_retained_by_both_count=int(counts[7]),
                anchor_far_remaining_far_in_both_count=int(counts[0]),
                anchor_surface_missing_count=int((~np.isfinite(a)).sum()),
                global_surface_missing_count=int((~np.isfinite(g)).sum()),
                local_surface_missing_count=int((~np.isfinite(local)).sum()),
                interpretation='same original reference-point proximity; not source truth, area, temporal truth or significance')
            for state in range(8):
                row[f'anchor_global_local_near_{state:03b}_count'] = int(counts[state])
            rows.append(row)
    return rows


def coverage_row(region, candidate, kind, metrics, strict_count):
    bounds = np.asarray(metrics['bounds_half_open'], dtype=float)
    size = metrics['xy_support']['cell_size_m']
    origin = np.asarray(metrics['xy_support']['origin'])
    low = np.floor((bounds[:2, 0]-origin)/size).astype(np.int64)
    high = np.ceil((bounds[:2, 1]-origin)/size).astype(np.int64)
    total_cells = int(np.prod(high-low))
    support = metrics['xy_support']
    return dict(region=region, candidate=candidate, mesh_kind=kind, status=metrics['status'],
        reference_original_roi_count=metrics['reference_points_in_roi'],
        reference_scored_count=metrics['reference_points_after_voxel'],
        strict_target_supported_reference_count=int(strict_count),
        strict_target_unsupported_reference_count=metrics['reference_points_after_voxel']-int(strict_count),
        roi_intersecting_xy_cell_count=total_cells,
        xy_cells_without_observed_reference=total_cells-support['reference_supported_cells'],
        **{'xy_'+key: value for key, value in support.items() if key not in ('origin', 'status')},
        coverage_certified=False, reference_absence_is_prediction_failure=False,
        support_interpretation='XY observed sample support; does not certify roof/wall visibility or full surface coverage')


def postprocess_row(region, candidate, raw, post):
    area = raw['surface_area_m2']
    difference = area-post['surface_area_m2']
    return dict(region=region, candidate=candidate,
        raw_surface_area_m2=area, post_surface_area_m2=post['surface_area_m2'],
        raw_minus_post_surface_area_m2=difference,
        raw_removed_area_fraction=difference/area if area else None,
        raw_status=raw['status'], post_status=post['status'],
        interpretation='same TSDF512 extraction, postprocessing effect kept separate from raw primary')


def psnr_uint8(reference, prediction):
    if (reference.dtype != np.uint8 or prediction.dtype != np.uint8
            or reference.shape != prediction.shape or reference.ndim != 3 or reference.shape[2] != 3):
        raise ValueError('Equal-size uint8 RGB arrays required')
    mse = float(np.mean((reference.astype(np.float64)-prediction.astype(np.float64))**2)/255.**2)
    return (None, True) if mse == 0 else (float(-10*np.log10(mse)), False)


def self_test():
    """Small meaningful checks without scene payloads, model imports, or GPU."""
    old=np.array([.1,1.,.1,1.,np.inf]); new=np.array([1.,.1,.1,1.,.1])
    rows=paired_rows('P1','new','old','raw',old,new,{'all':np.ones(5,bool)},[.5])
    row=rows[0]
    assert (row['corrected_count'],row['damaged_count'],row['retained_near_count'],row['remaining_far_count'])==(2,1,1,1)
    assert row['finite_pair_count']==4 and row['recovered_from_missing_count']==1
    assert row['corrected_fraction_of_comparator_far']==2/3
    assert row['preservation_fraction_of_comparator_near']==.5
    points=np.array([[0.,0.,0.],[1.,0.,0.]])
    require_membership(points,np.array([4,9]),points,np.array([4,9]))
    for bad in (np.array([9,4]),np.array([4,4])):
        try: require_membership(points,bad,points,np.array([4,9]))
        except ValueError: pass
        else: raise AssertionError('Mismatched membership accepted')
    try: validate_distances(np.array([np.nan]),1)
    except ValueError: pass
    else: raise AssertionError('NaN distance accepted')
    assert psnr_uint8(np.zeros((2,2,3),np.uint8),np.zeros((2,2,3),np.uint8))==(None,True)
    assert psnr_uint8(np.zeros((2,2,3),np.uint8),np.full((2,2,3),255,np.uint8))==(0.,False)
    assert paired_rows('P1','n','a','raw',np.array([]),np.array([]),{'none':np.array([],bool)},[.5])[0]['candidate_reference_recall'] is None
    return {'status':'PASS_CPU_MEMBERSHIP_TRANSITIONS_PSNR_SMOKE','scientific_verdict':None}
