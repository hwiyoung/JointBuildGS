"""Aggregate frozen diagnostics and build the actual comparison viewer manifest."""
import argparse
from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
from runtime_layout import RuntimeLayout
from supplemental_repeat import SupplementalRepeat
import resource_support as resource_policy
from display_export import manifest_mesh_links,display_candidate_state

PRIMARY = 'sample0.1_reference0.1'


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def file_record(task, path):
    path = Path(path)
    return dict(path=str(path.relative_to(task)), sha256=sha(path), bytes=path.stat().st_size)


def dump(path, value):
    with Path(path).open('x') as f:
        json.dump(value, f, indent=2, allow_nan=False)


def csv_write(path, rows):
    keys = list(dict.fromkeys(key for row in rows for key in row))
    with Path(path).open('x', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def finite_mean(values):
    """Compatibility name: never silently drop infinity from an aggregate."""
    return numeric_summary(values)['mean']


def numeric_summary(values, weights=None):
    """Strict-JSON mean with explicit missing/invalid/infinite denominators.

    Positive infinity remains positive infinity via a flag and null numeric mean.
    In particular, reconstruction failure is never converted to a finite-only
    favorable mean. Missing observations are excluded only with visible counts.
    """
    values = list(values)
    weights = np.ones(len(values)) if weights is None else np.asarray(weights, dtype=float)
    if len(weights) != len(values) or not np.isfinite(weights).all() or np.any(weights < 0):
        raise ValueError('Finite nonnegative aggregate weights required')
    parsed = [None if value is None or value == '' else float(value) for value in values]
    finite = [i for i, value in enumerate(parsed) if value is not None and np.isfinite(value) and weights[i] > 0]
    missing = sum(value is None for value in parsed)
    positive = sum(value is not None and np.isposinf(value) and weights[i] > 0 for i, value in enumerate(parsed))
    negative = sum(value is not None and np.isneginf(value) and weights[i] > 0 for i, value in enumerate(parsed))
    invalid = sum(value is not None and np.isnan(value) and weights[i] > 0 for i, value in enumerate(parsed))
    mean, status = None, 'UNAVAILABLE'
    if invalid or negative:
        status = 'INVALID_NUMERIC_VALUES'
    elif positive:
        status = 'POSITIVE_INFINITY'
    elif finite:
        mean = float(np.average([parsed[i] for i in finite], weights=weights[finite]))
        status = 'PARTIAL_MISSING_VALUES' if missing else 'FINITE'
    return dict(mean=mean, status=status, total_count=len(parsed), finite_count=len(finite),
                missing_count=missing, positive_infinity_count=int(positive),
                negative_infinity_count=int(negative), invalid_count=int(invalid),
                positive_infinity=status == 'POSITIVE_INFINITY')


def summary_value(summary):
    if summary['positive_infinity']:
        return float('inf')
    if summary['status'] == 'INVALID_NUMERIC_VALUES':
        return float('nan')
    return summary['mean']


def by_cell(points, cell_size=.5, origin=(0., 0.)):
    cells = np.floor((points[:, :2]-np.asarray(origin))/cell_size).astype(np.int64)
    result = {}
    for index, cell in enumerate(cells):
        result.setdefault(tuple(cell), []).append(index)
    return result


def fixed_cells(bounds, cell_size=.5, origin=(0., 0.)):
    if not np.isfinite(cell_size) or cell_size <= 0:
        raise ValueError('Positive fixed cell size required')
    minimum = np.floor((np.array([bounds[a][0] for a in 'xy'])-origin)/cell_size).astype(int)
    maximum = np.ceil((np.array([bounds[a][1] for a in 'xy'])-origin)/cell_size).astype(int)
    return [(x, y) for x in range(minimum[0], maximum[0]) for y in range(minimum[1], maximum[1])]


def difference_state(before, after):
    if before['status'] == 'INVALID_NUMERIC_VALUES' or after['status'] == 'INVALID_NUMERIC_VALUES':
        return None, 'INVALID_DISTANCE_VALUES'
    if before['positive_infinity'] and after['positive_infinity']:
        return None, 'PERSISTENT_RECONSTRUCTION_FAILURE'
    if before['positive_infinity'] and after['mean'] is not None:
        return None, 'RECOVERED_FROM_RECONSTRUCTION_FAILURE'
    if after['positive_infinity'] and before['mean'] is not None:
        return None, 'DEGRADED_TO_RECONSTRUCTION_FAILURE'
    if before['mean'] is None or after['mean'] is None:
        return None, 'NOT_ASSESSED_REFERENCE_ABSENT'
    return before['mean']-after['mean'], 'FINITE_DISTANCE_DIFFERENCE'


def reverse_distances(arrays):
    key = 'reference_to_candidate_distance' if 'reference_to_candidate_distance' in arrays else 'reference_to_triangle_distance'
    return arrays[key]


def relation_rows(task, region, cfg, analysis_cfg=None):
    analysis_cfg = analysis_cfg or {}
    cell_size = analysis_cfg.get('cell_size_m', .5)
    origin = np.asarray(analysis_cfg.get('cell_origin_xy', [0., 0.]))
    root = task/'evaluation/geometry'/region
    native = np.load(root/'D005_Pnative.final.raw'/(PRIMARY+'.npz'), allow_pickle=False)
    prior = np.load(root/'prior_mesh'/(PRIMARY+'.npz'), allow_pickle=False)
    als = np.load(root/'als_points'/(PRIMARY+'.npz'), allow_pickle=False)
    mvs = np.load(root/'mvs_points'/(PRIMARY+'.npz'), allow_pickle=False)
    members = native['reference_original_indices']
    for other in (prior, als, mvs):
        if (not np.array_equal(members, other['reference_original_indices']) or
                not np.array_equal(native['reference_points'], other['reference_points'])):
            raise ValueError('Reference identity differs between baseline and candidate evaluation')
    cells = by_cell(native['reference_points'], cell_size, origin)
    grid = fixed_cells(cfg['regions'][region]['domain'], cell_size, origin)
    source_cells = {'als': by_cell(als['prediction_surface_samples'], cell_size, origin),
                    'mvs': by_cell(mvs['prediction_surface_samples'], cell_size, origin)}
    rows, cases = [], []
    for condition in cfg['conditions']:
        candidate = np.load(root/(condition['id']+'.final.raw')/(PRIMARY+'.npz'), allow_pickle=False)
        if (not np.array_equal(members, candidate['reference_original_indices']) or
                not np.array_equal(native['reference_points'], candidate['reference_points'])):
            raise ValueError('Changed/native reference memberships differ')
        condition_rows = []
        native_reverse, candidate_reverse, prior_reverse = reverse_distances(native), reverse_distances(candidate), reverse_distances(prior)
        for cell in grid:
            indices = np.asarray(cells.get(cell, []), dtype=np.int64)
            before = numeric_summary(native_reverse[indices])
            after = numeric_summary(candidate_reverse[indices])
            prior_distance = numeric_summary(prior_reverse[indices])
            relation = ('reference_absent' if not len(indices) else
                        'prior_reconstruction_failure' if prior_distance['positive_infinity'] else
                        'prior_unavailable' if prior_distance['mean'] is None else
                        'reference_consistent_prior' if prior_distance['mean'] < .25 else
                        'reference_disagreeing_prior' if prior_distance['mean'] >= .5 else 'intermediate_prior_relation')
            difference, transition = difference_state(before, after)
            row = dict(region=region, condition=condition['id'], cell_x=int(cell[0]), cell_y=int(cell[1]),
                       center_x_m=float(origin[0]+(cell[0]+.5)*cell_size), center_y_m=float(origin[1]+(cell[1]+.5)*cell_size),
                       reference_points=len(indices), reference_to_prior_relation=relation,
                       prior_reference_mean_m=prior_distance['mean'], native_reference_mean_m=before['mean'],
                       changed_reference_mean_m=after['mean'],
                       prior_distance_status=prior_distance['status'], native_distance_status=before['status'],
                       changed_distance_status=after['status'],
                       prior_positive_infinity_points=prior_distance['positive_infinity_count'],
                       native_positive_infinity_points=before['positive_infinity_count'],
                       changed_positive_infinity_points=after['positive_infinity_count'],
                       native_invalid_points=before['invalid_count']+before['negative_infinity_count'],
                       changed_invalid_points=after['invalid_count']+after['negative_infinity_count'],
                       native_minus_changed_m=difference, distance_transition=transition,
                       als_cell_points=len(source_cells['als'].get(cell, [])),
                       mvs_cell_points=len(source_cells['mvs'].get(cell, [])),
                       temporal_status='NOT_AUTOMATICALLY_INFERRED',
                       image_observation_quality='REQUIRES_ACTUAL_IMAGE_VISIBILITY_TEXTURE_REVIEW')
            rows.append(row)
            condition_rows.append(row)
        eligible = [row for row in condition_rows if row['reference_points'] >= 3 and row['native_minus_changed_m'] is not None]
        if condition['id'] != 'D005_Pnative':
            positives = [row for row in eligible if row['native_minus_changed_m'] > 0]
            negatives = [row for row in eligible if row['native_minus_changed_m'] < 0]
            selected = []
            if positives:
                selected.append(('largest_reference_distance_reduction', max(positives, key=lambda r:r['native_minus_changed_m'])))
            if negatives:
                selected.append(('largest_reference_distance_increase', min(negatives, key=lambda r:r['native_minus_changed_m'])))
            if eligible:
                selected.append(('smallest_absolute_reference_distance_difference', min(eligible, key=lambda r:abs(r['native_minus_changed_m']))))
            for transition in ('DEGRADED_TO_RECONSTRUCTION_FAILURE', 'RECOVERED_FROM_RECONSTRUCTION_FAILURE',
                               'PERSISTENT_RECONSTRUCTION_FAILURE', 'INVALID_DISTANCE_VALUES'):
                failed = [row for row in condition_rows if row['reference_points'] >= 3 and row['distance_transition'] == transition]
                if failed:
                    selected.append((transition.lower()+'_first_fixed_cell', failed[0]))
            absent = [row for row in condition_rows if row['reference_points'] == 0]
            if absent:
                selected.append(('reference_absent_first_fixed_cell', absent[0]))
            for reason, row in selected:
                cases.append(dict(row, selection_reason=reason,
                    interpretation='diagnostic ranked case; geometric distance alone does not prove currentness or total quality'))
    strata = []
    for condition in cfg['conditions']:
        selected = [row for row in rows if row['condition'] == condition['id']]
        labels = sorted(set(row['reference_to_prior_relation'] for row in selected))
        for label in labels:
            subset = [row for row in selected if row['reference_to_prior_relation'] == label]
            weights = np.array([row['reference_points'] for row in subset])
            def distance_values(prefix):
                return [float('inf') if row[prefix+'_positive_infinity_points'] else
                        float('nan') if row[prefix+'_invalid_points'] else row[prefix+'_reference_mean_m'] for row in subset]
            native_stats = numeric_summary(distance_values('native'))
            changed_stats = numeric_summary(distance_values('changed'))
            weighted_stats = numeric_summary(distance_values('changed'), weights)
            strata.append(dict(region=region, condition=condition['id'], diagnostic_relation=label,
                cells=len(subset), reference_points=int(weights.sum()),
                equal_cell_native_mean_m=native_stats['mean'], equal_cell_native_status=native_stats['status'],
                equal_cell_changed_mean_m=changed_stats['mean'], equal_cell_changed_status=changed_stats['status'],
                reference_weighted_changed_mean_m=weighted_stats['mean'], reference_weighted_changed_status=weighted_stats['status'],
                native_infinite_distance_cells=native_stats['positive_infinity_count'],
                changed_infinite_distance_cells=changed_stats['positive_infinity_count'],
                changed_invalid_distance_cells=changed_stats['invalid_count'],
                reference_absent_cells=sum(row['reference_points']==0 for row in subset),
                image_geometry_absent_cells=sum(row['mvs_cell_points']==0 for row in subset),
                scientific_interpretation='evaluation-only prior/reference relation; not temporal labels'))
    return rows, cases, strata


GEOMETRY_METRICS = ('precision', 'recall', 'f1', 'p2ref_mean_m', 'p2ref_median_m', 'p2ref_p95_m', 'p2ref_rmse_m',
                    'ref2candidate_mean_m', 'ref2candidate_median_m', 'ref2candidate_p95_m', 'ref2candidate_rmse_m',
                    'surface_area_m2', 'far_from_observed_reference_area_estimate_m2')
OPTICAL_METRICS = ('psnr_native_db', 'ssim_native', 'lpips_vgg_native_01', 'lpips_vgg_signed_11')


def partition_geometry(rows, repeat):
    """Keep the declared repetition out of every primary table and macro."""
    primary, supplemental = [], []
    for row in rows:
        declared = bool(repeat.identifier and row['candidate'].split('.')[0] == repeat.identifier)
        marked = row.get('supplemental_only') in (True, 'True', 'true')
        if marked and not declared:
            raise ValueError('Undeclared supplemental geometry cannot enter the primary comparison')
        (supplemental if declared else primary).append(row)
    return primary, supplemental


def single_metric(value):
    stats = numeric_summary([value])
    return dict(value=stats['mean'], status=stats['status'], positive_infinity=stats['positive_infinity'],
                negative_infinity=stats['negative_infinity_count'] > 0)


def geometry_metric(row, metric):
    if row['status'] == 'RECONSTRUCTION_FAILURE':
        if metric.startswith('ref2candidate_'):
            return single_metric(float('inf'))
        if metric.startswith('p2ref_'):
            return dict(value=None, status='UNDEFINED_EMPTY_PREDICTION', positive_infinity=False, negative_infinity=False)
        if metric in ('precision', 'recall', 'f1'):
            return single_metric(0.)
    return single_metric(row.get(metric))


def paired_difference(primary, repeated):
    """Descriptive primary-minus-repeat; undefined/infinite pairs stay explicit."""
    if primary['value'] is not None and repeated['value'] is not None:
        return dict(primary_minus_repeat=primary['value']-repeated['value'], difference_status='FINITE',
                    difference_positive_infinity=False, difference_negative_infinity=False)
    if primary['positive_infinity'] and repeated['positive_infinity']:
        status, positive, negative = 'UNDEFINED_INFINITY_MINUS_INFINITY', False, False
    elif primary['positive_infinity'] and repeated['value'] is not None:
        status, positive, negative = 'POSITIVE_INFINITY', True, False
    elif repeated['positive_infinity'] and primary['value'] is not None:
        status, positive, negative = 'NEGATIVE_INFINITY', False, True
    else:
        status, positive, negative = 'UNAVAILABLE_OR_INVALID_PAIR', False, False
    return dict(primary_minus_repeat=None, difference_status=status,
                difference_positive_infinity=positive, difference_negative_infinity=negative)


def geometry_repeat_differences(primary_rows, repeat_rows, identifier):
    def key(row):
        return (row['region'], row['candidate'].split('.', 1)[1], row['sensitivity'],
                row['surface_kind'], float(row['threshold_m']))
    primary_rows = [row for row in primary_rows if row['candidate'].startswith('D005_Pnative.')]
    primary = {key(row):row for row in primary_rows}
    repeated = {key(row):row for row in repeat_rows}
    if len(primary) != len(primary_rows) or len(repeated) != len(repeat_rows) or set(primary) != set(repeated):
        raise ValueError('Native/repeat geometry must match exactly by region, variant, estimator, sensitivity and threshold')
    output = []
    for identity in sorted(primary):
        before, after = primary[identity], repeated[identity]
        for metric in GEOMETRY_METRICS:
            a, b = geometry_metric(before, metric), geometry_metric(after, metric)
            output.append(dict(region=identity[0], variant=identity[1], sensitivity=identity[2],
                surface_kind=identity[3], threshold_m=identity[4], metric=metric,
                primary_candidate=before['candidate'], repeat_candidate=after['candidate'],
                primary_evaluation_status=before['status'], repeat_evaluation_status=after['status'],
                primary_value=a['value'], repeat_value=b['value'], primary_metric_status=a['status'], repeat_metric_status=b['status'],
                primary_positive_infinity=a['positive_infinity'], repeat_positive_infinity=b['positive_infinity'],
                **paired_difference(a, b), supplemental_only=True, supplemental_repeat_id=identifier,
                interpretation='DESCRIPTIVE_PRIMARY_NATIVE_MINUS_SINGLE_REPEAT; no quality noise bound, confidence interval or primary ranking'))
    return output


def optical_repeat_differences(primary_rows, repeat_rows, identifier):
    def key(row):
        return row['region'], row['stage'], row['domain'], row['name']
    primary_rows = [row for row in primary_rows if row['condition']=='D005_Pnative']
    primary = {key(row):row for row in primary_rows}
    repeated = {key(row):row for row in repeat_rows}
    if len(primary) != len(primary_rows) or len(repeated) != len(repeat_rows) or set(primary) != set(repeated):
        raise ValueError('Native/repeat optical observations must match exactly by region, stage, domain and image')
    output = []
    camera_fields = ('evaluation_index', 'image_id', 'camera_id', 'photo_sha256', 'seed',
                     'roi_x0', 'roi_y0', 'roi_x1', 'roi_y1', 'pixel_count')
    for identity in sorted(primary):
        before, after = primary[identity], repeated[identity]
        if any(before.get(field) != after.get(field) for field in camera_fields):
            raise ValueError('Native/repeat image identity or fixed scoring domain differs')
        for metric in OPTICAL_METRICS:
            a, b = single_metric(optical_value(before, metric)), single_metric(optical_value(after, metric))
            output.append(dict(region=identity[0], stage=identity[1], domain=identity[2], name=identity[3], metric=metric,
                primary_condition='D005_Pnative', repeat_condition=identifier,
                primary_evaluation_status=before['status'], repeat_evaluation_status=after['status'],
                primary_value=a['value'], repeat_value=b['value'], primary_metric_status=a['status'], repeat_metric_status=b['status'],
                primary_positive_infinity=a['positive_infinity'], repeat_positive_infinity=b['positive_infinity'],
                **{field:before.get(field) for field in camera_fields}, **paired_difference(a, b), supplemental_only=True,
                interpretation='DESCRIPTIVE_MATCHED_IMAGE_PRIMARY_NATIVE_MINUS_SINGLE_REPEAT; no quality noise bound or confidence interval'))
    return output


def optical_difference_summary(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[(row['region'], row['stage'], row['domain'], row['metric'])].append(row)
    output = []
    for identity, members in sorted(groups.items()):
        finite = [row for row in members if row['difference_status']=='FINITE']
        states = {state:sum(row['difference_status']==state for row in members) for state in
                  ('POSITIVE_INFINITY', 'NEGATIVE_INFINITY', 'UNDEFINED_INFINITY_MINUS_INFINITY', 'UNAVAILABLE_OR_INVALID_PAIR')}
        all_finite = len(finite) == len(members)
        output.append(dict(region=identity[0], stage=identity[1], domain=identity[2], metric=identity[3],
            expected_pairs=len(members), finite_pairs=len(finite),
            mean_primary_minus_repeat=float(np.mean([row['primary_minus_repeat'] for row in finite])) if all_finite else None,
            finite_pair_mean_primary_minus_repeat=float(np.mean([row['primary_minus_repeat'] for row in finite])) if finite else None,
            difference_status='FINITE_ALL_MATCHED_PAIRS' if all_finite else 'PARTIAL_OR_UNDEFINED_MATCHED_PAIRS',
            **{state.lower()+'_pairs':count for state, count in states.items()}, supplemental_only=True,
            aggregation='REGIONAL_EQUAL_IMAGE_PAIRED_DESCRIPTIVE_DIFFERENCE',
            interpretation='Finite-pair mean is explicitly conditional on counted finite pairs; no confidence interval or quality noise bound'))
    return output


def geometry_region_macro(rows, expected_regions):
    """Average regional statistics, keeping estimator/density/threshold separate."""
    groups = defaultdict(list)
    for row in rows:
        groups[(row['candidate'], row['sensitivity'], row['surface_kind'], float(row['threshold_m']))].append(row)
    output = []
    for (candidate, sensitivity, kind, threshold), members in sorted(groups.items()):
        by_region = {row['region']: row for row in members}
        if len(by_region) != len(members) or set(by_region)-set(expected_regions):
            raise ValueError('Duplicate or unknown region in geometry macro group')
        summary = dict(candidate=candidate, sensitivity=sensitivity, surface_kind=kind, threshold_m=threshold,
                       aggregation='EQUAL_REGION_DESCRIPTIVE_MACRO', independent_inference=False,
                       expected_regions=len(expected_regions), present_regions=len(by_region),
                       assessed_regions=sum(row['status']=='ASSESSED_DEVELOPMENT_ONLY' for row in members),
                       reconstruction_failure_regions=sum(row['status']=='RECONSTRUCTION_FAILURE' for row in members),
                       reference_absent_regions=sum(row['status']=='NOT_ASSESSED_REFERENCE_ABSENT' for row in members),
                       missing_regions=len(expected_regions)-len(by_region),
                       statistic_note='mean of regional statistics; mean regional F1 is not F1 of macro precision/recall; mean regional median/p95/RMSE is not a pooled median/p95/RMSE; far-reference area is an area-sampling estimate, not confirmed wrong residual structure area')
        for metric in GEOMETRY_METRICS:
            values = []
            for region in expected_regions:
                row = by_region.get(region)
                value = row.get(metric) if row else None
                if row and row['status']=='RECONSTRUCTION_FAILURE' and metric.startswith('ref2candidate_'):
                    value = float('inf')
                if row and row['status']=='RECONSTRUCTION_FAILURE' and metric in ('precision', 'recall', 'f1'):
                    value = 0.
                values.append(value)
            statistics = numeric_summary(values)
            if metric.startswith('p2ref_') and summary['reconstruction_failure_regions']:
                # No prediction samples means this direction is undefined, not
                # a measured infinite distance. Do not average only surviving
                # regions and thereby hide the failed region.
                statistics.update(mean=None, status='UNDEFINED_WITH_RECONSTRUCTION_FAILURE')
            summary[metric+'_equal_region_mean'] = statistics['mean']
            for key in ('status', 'finite_count', 'missing_count', 'positive_infinity_count', 'invalid_count'):
                summary[metric+'_'+key] = statistics[key]
        output.append(summary)
    return output


def optical_value(row, metric):
    if row['status'] != 'ASSESSED':
        return None
    if metric == 'psnr_native_db' and row.get('psnr_positive_infinity', False):
        return float('inf')
    return row.get(metric)


def optical_summary(rows, **identity):
    """Unweighted per-image metric means, with metric-specific eligibility."""
    assessed = [row for row in rows if row['status']=='ASSESSED']
    unavailable = sum(row['status']=='PRISM_NOT_IN_CAMERA_DOMAIN' for row in rows)
    summary = dict(identity, expected_images=len(rows), assessed_images=len(assessed),
                   unavailable_camera_domain_images=unavailable,
                   failed_images=len(rows)-len(assessed)-unavailable,
                   assessed_pixels=sum(row['pixel_count'] for row in assessed))
    for metric in OPTICAL_METRICS:
        stats = numeric_summary([optical_value(row, metric) for row in rows])
        summary[metric] = stats['mean']
        for key in ('status', 'finite_count', 'missing_count', 'positive_infinity_count', 'invalid_count'):
            summary[metric+'_'+key] = stats[key]
    return summary


def optical_pooled(rows, expected_regions):
    """Distinct image-weighted and equal-region descriptive optical averages."""
    groups = defaultdict(list)
    for row in rows:
        groups[(row['condition'], row['stage'], row['domain'])].append(row)
    image_weighted, region_macro = [], []
    for (condition, stage, domain), members in sorted(groups.items()):
        identities = [(row['region'], row['name']) for row in members]
        if len(set(identities)) != len(identities):
            raise ValueError('Duplicate optical image in one condition/stage/domain')
        by_region = {region: [row for row in members if row['region']==region] for region in expected_regions}
        if set(row['region'] for row in members)-set(expected_regions):
            raise ValueError('Unknown optical region')
        base = dict(condition=condition, stage=stage, domain=domain, independent_inference=False,
                    expected_regions=len(expected_regions), present_regions=sum(bool(value) for value in by_region.values()))
        image_weighted.append(optical_summary(members, **base,
                              aggregation='POOLED_IMAGE_WEIGHTED_DESCRIPTIVE',
                              statistic_note='each assessed image has equal weight; no pixel weighting; view/region overlap prevents independent inference'))
        local = {region: optical_summary(value) for region, value in by_region.items()}
        macro = dict(base, aggregation='EQUAL_REGION_DESCRIPTIVE_MACRO',
                     expected_images=len(members), assessed_images=sum(row['assessed_images'] for row in local.values()),
                     failed_images=sum(row['failed_images'] for row in local.values()),
                     unavailable_camera_domain_images=sum(row['unavailable_camera_domain_images'] for row in local.values()),
                     assessed_pixels=sum(row['assessed_pixels'] for row in local.values()),
                     statistic_note='equal weight per available regional per-image mean; missing/invalid/infinite regions are explicit; no independent inference')
        for metric in OPTICAL_METRICS:
            values = [float('inf') if row[metric+'_positive_infinity_count'] else
                      float('nan') if row[metric+'_invalid_count'] else row[metric] for row in local.values()]
            stats = numeric_summary(values)
            macro[metric] = stats['mean']
            for key in ('status', 'finite_count', 'missing_count', 'positive_infinity_count', 'invalid_count'):
                macro[metric+'_'+key+'_regions'] = stats[key]
            macro[metric+'_finite_images'] = sum(row[metric+'_finite_count'] for row in local.values())
            macro[metric+'_positive_infinity_images'] = sum(row[metric+'_positive_infinity_count'] for row in local.values())
        region_macro.append(macro)
    return image_weighted, region_macro


def viewer_cases(cases, bounds):
    """Case navigation uses fixed prism mid-height, never a fitted output pose."""
    z = float(np.mean(bounds['z']))
    return [dict(id=f"{row['condition']}.{row['cell_x']}.{row['cell_y']}.{row['selection_reason']}",
                 label=row['condition']+' — '+row['selection_reason'].replace('_', ' '),
                 center=[row['center_x_m'], row['center_y_m'], z], extent_m=5,
                 description=(f"{row['reference_points']} observed reference points; "
                              f"{row['distance_transition']}; {row['reference_to_prior_relation']}. "
                              "Selection is descriptive. Currentness, image observation quality and total quality require manual review. "
                              "Camera center Z is the fixed regional prism midpoint."),
                 condition_id=row['condition']) for row in cases]


def resource_measurement_definitions():
    """Reporting metadata only; never read device logs or re-estimate a cost."""
    return dict(schema='GEOGS_RESOURCE_MEASUREMENT_DEFINITIONS_v1', scientific_verdict=None,
        scope_column='resource_measurement_scope', existing_numeric_fields_preserved=True,
        cross_scope_time_sum_is_full_pipeline=False, memory_peaks_are_additive=False,
        phase_and_variant_times_are_additive=False,
        raw_device_gpu_evidence=dict(read_by_this_summary=False,
            source='run_regional_phase.py:179-182; run_auxiliary_resource_v3.py:103-106',
            files='Native phase *_gpu.csv and resource_v3 auxiliary/<variant>/gpu.csv',
            measurement='nvidia-smi --query-gpu timestamp,uuid,memory.used,utilization.gpu',
            scope='Whole visible GPU device by UUID, including other device users; not native PID or container usage',
            memory_unit='MiB', utilization_unit='percent',
            ordinary_phase_sleep_seconds=5, resource_variant_sleep_seconds=2,
            sample_interval='Sleep plus query/loop duration; periodic observations, not a continuous maximum',
            is_pytorch_allocator_peak=False, final_regional_csv_device_peak_exported=False),
        scopes={
            'regional_driver_phase_v1': dict(
                rows='train/render/metrics; legacy auxiliary when no resource_v3 contract is supplied',
                source='run_regional_phase.py:47-48,61-63,142-150,174-249',
                wall_seconds=dict(clock='Driver time.time start through receipt construction',
                    includes=['invocation metadata and input-manifest SHA', 'native launch and process execution',
                              'nvidia-smi polling and 5-second sleep/termination detection', 'post-run validation and required-output SHA'],
                    excludes=['Docker start', 'preclock allocator audit', 'full frozen-input and source-file SHA checks',
                              'preclock snapshot/anchor checks', 'extraction-lock wait', 'receipt serialization after clock read']),
                raw_phase_wall_seconds='Alias of the same wall_seconds, not an additional duration',
                scheduling_wait_seconds='Separate extraction-lock wait before phase clock; not all queue/setup time',
                child_peak_rss_bytes=dict(api='getrusage(RUSAGE_CHILDREN).ru_maxrss * 1024',
                    scope='Largest RSS among terminated, waited-for children of this driver; includes preclock allocator audit and nvidia-smi children when present',
                    is_native_pid_only=False, is_simultaneous_process_tree_sum=False,
                    parent_driver_validation_rss_included=False, unit='bytes'),
                cuda_peak_fields='Not exported on this phase row; raw device GPU CSV is not read'),
            'resource_v3_auxiliary_phase_v1': dict(
                rows='Whole resource_v3 auxiliary phase, with all registered variants',
                source='run_auxiliary_resource_v3.py:195-224,228-251',
                wall_seconds=dict(clock='Driver monotonic start after extraction lock through aggregate receipt construction',
                    includes=['variant source/copy SHA and preparation', 'per-variant host headroom waits',
                              'native renderer and polling', 'post-run surface validation/output SHA', 'producer-file inventory hashing'],
                    excludes=['Docker start', 'preclock full input/source SHA and allocator audit',
                              'preclock snapshots', 'extraction-lock wait', 'aggregate receipt serialization']),
                raw_phase_wall_seconds='Alias of the same wall_seconds, not an additional duration',
                scheduling_wait_seconds='Extraction-lock wait before this clock; per-variant host headroom waits are inside it',
                child_peak_rss_bytes=dict(api='max(variant receipt child_peak_rss_bytes)',
                    scope='Maximum of the renderer-PID wait4 RSS values, including attempted optional variants',
                    is_simultaneous_process_tree_sum=False, parent_driver_validation_rss_included=False, unit='bytes'),
                variant_costs_included=True, additive_with_variant_rows=False,
                cuda_peak_fields='Not exported; raw per-variant device GPU CSV is not read'),
            'training_process_trace_v1': dict(
                rows='training_trace, primary and separately marked native repeat',
                source='jbgs_state.py:17,168-187; summarize.py:resource_records',
                wall_seconds='Last logged monotonic elapsed since instrumentation-module import; same value as instrumented_process_elapsed_seconds',
                includes=['process initialization/restore', 'earlier reports/captures/saves and waiting'],
                ends_before='The last logged step complete-state capture/save; final post-trace work may be excluded',
                post_anchor_instrumented_interval_seconds='Start0: last trace minus step8000 trace; includes anchor capture. Resume8000: last process elapsed includes initialization/restore',
                child_peak_rss_bytes=dict(api='max(logged getrusage(RUSAGE_SELF).ru_maxrss * 1024)',
                    scope='Training process itself, all its threads, through logged observations; old column name retained',
                    is_driver_children_measurement=False, final_after_trace_peak_guaranteed=False, unit='bytes'),
                peak_cuda_allocated_bytes='Maximum logged torch.cuda.max_memory_allocated(): training-process PyTorch allocator peak counter, not whole-device used memory',
                peak_cuda_reserved_bytes='Maximum logged torch.cuda.max_memory_reserved(): training-process PyTorch reserved-memory peak counter, not whole-device used memory',
                cuda_peak_scope='Counters as observed in the trace; no separate anchor/refinement reset or post-final-trace measurement is fabricated',
                additive_with_phase_wall_seconds=False, isolated_optimizer_time=False),
            'shared_anchor_trace_prefix_v1': dict(
                rows='shared_anchor_prefix; no whole-anchor wall_seconds is fabricated',
                source='jbgs_state.py:17,168-187; summarize.py:anchor_resource_records',
                anchor_prefix_elapsed_seconds='Instrumentation import through step8000 trace, before that complete-state capture/save',
                wall_seconds='Unmeasured whole-anchor duration: null', additive_to_final_phase_totals=False),
            'failed_anchor_source_phase_v1': dict(
                rows='anchor_source_failed_attempt, retained separately',
                source='Original failed train receipt; run_regional_phase.py driver clock',
                wall_seconds='Entire recorded failed driver phase, including attempted refinement after8000; never an anchor-only cost',
                raw_phase_wall_seconds='Alias of the same wall_seconds', additive_to_final_phase_totals=False),
            'resource_v3_auxiliary_variant_v1': dict(
                rows='extraction_attempt_resources.csv: each required/optional primary/repeat variant',
                source='run_auxiliary_resource_v3.py:47-156; memory():33-39',
                wall_seconds=dict(clock='monotonic before log opening/native launch through wait4 completion detection',
                    includes=['native renderer execution', 'memory/GPU sampling and 2-second sleep/termination detection'],
                    excludes=['source/copy SHA and preparation', 'host-headroom wait', 'invocation writing',
                              'after-exit memory sample', 'post-run surface validation and output SHA']),
                timestamp_warning='Invocation started_unix and receipt finished_unix have wider boundaries; their subtraction is not this wall_seconds',
                child_peak_rss_bytes=dict(api='os.wait4(native_renderer_pid, ...).rusage.ru_maxrss * 1024',
                    scope='Wait4 usage for the specified renderer child, not all sibling children of the driver',
                    is_simultaneous_process_tree_sum=False, parent_driver_validation_rss_included=False, unit='bytes'),
                sampled_peak_memory_current_bytes=dict(api='max(before, periodic and after memory.current samples)',
                    scope='Whole auxiliary-container cgroup accounting at these observations; includes driver/other processes and charged memory',
                    after_sample_precedes='Current variant post-run surface validation/output SHA',
                    is_continuous_peak=False, is_native_pid_rss=False, is_gpu_memory=False, unit='bytes'),
                cgroup_memory_limit_bytes='Host-memory cgroup memory.max cap; not a CUDA/VRAM cap',
                cgroup_oom_kill_delta='memory.events oom_kill after minus before this variant interval',
                host_headroom_wait_seconds='Recorded pre-variant wait; excluded from variant wall and included in whole auxiliary phase wall',
                raw_cgroup_lifetime_peak=dict(exported_as_variant_csv_number=False,
                    source='receipt memory_before/memory_after.memory_peak_bytes; raw memory.jsonl',
                    scope='Same auxiliary container lifetime through each observation, including earlier variants/preparation/validation',
                    current_variant_post_validation_included=False, before_after_difference_is_variant_peak=False),
                raw_host_available_minimum='Periodic /proc/meminfo MemAvailable minimum in producer receipt/trace; not exported here or a continuous minimum',
                included_within_auxiliary_phase_cost=True, additive_to_phase_totals=False)})


def resource_records(task, region, condition, layout, sealed_files, repeat=None, resource=None):
    """Measured process costs; no fabricated full-pipeline/comparable total."""
    supplemental = repeat is not None and condition == repeat.identifier
    run = repeat.run(region) if supplemental else layout.run(region, condition)
    binding = dict(layout.binding(), **(repeat.binding() if repeat is not None else {}),
                   **resource_policy.binding(resource))
    def read(path):
        relative = str(path.relative_to(task))
        if relative not in sealed_files or sha(path) != sealed_files[relative]['sha256']:
            raise ValueError('Resource input differs from candidate seal: '+relative)
        return path.read_text()
    rows = []
    start_iteration = 8000 if supplemental or layout.starts_from_anchor(region, condition) else 0
    for phase in ('train', 'render', 'metrics', 'auxiliary'):
        phase_run = resource.aux_run(region, 'D005_Pnative' if supplemental else condition,
                                    repeat.identifier if supplemental else None) if resource and phase == 'auxiliary' else run
        path = phase_run/(phase+'_receipt.json')
        receipt = json.loads(read(path))
        layout.require_receipt(receipt)
        if phase == 'auxiliary' and resource:
            resource.validate_receipt(receipt, region, 'D005_Pnative' if supplemental else condition,
                                      repeat.identifier if supplemental else None)
        if supplemental:
            repeat.require_run_receipt(receipt, region)
        if phase == 'train' and receipt.get('training_start_iteration', start_iteration) != start_iteration:
            raise ValueError('Resource training start differs from runtime layout')
        rows.append(dict(region=region, condition=condition, phase=phase,
            cost_category='SUPPLEMENTAL_REPEAT_RUN_PHASE' if supplemental else 'FINAL_RUN_PHASE', supplemental_only=supplemental,
            wall_seconds=receipt['wall_seconds'], raw_phase_wall_seconds=receipt['wall_seconds'],
            scheduling_wait_seconds=receipt.get('resource_scheduling', {}).get('wait_seconds'),
            serialized_extraction=receipt.get('resource_scheduling', {}).get('serialized_extraction'),
            child_peak_rss_bytes=receipt['child_peak_rss_bytes'], status=receipt['status'],
            shared_anchor=phase=='train' and start_iteration==8000,
            training_start_iteration=start_iteration if phase=='train' else None,
            full_pipeline_wall_seconds=None, comparable_refinement_compute_seconds=None,
            source_path=str(path.relative_to(task)), source_sha256=sha(path),
            cost_interpretation='recorded driver phase interval; see resource_measurement_scope; shared preprocessing, anchor reuse and failed attempts are separate',
            resource_measurement_scope='resource_v3_auxiliary_phase_v1' if resource and phase=='auxiliary' else 'regional_driver_phase_v1',
            anchor_checkpoint_directory=str(layout.anchor_checkpoint(region).relative_to(task)), **binding))
    trace_path = run/'model/jbgs_trace.jsonl'
    trace = [json.loads(line) for line in read(trace_path).splitlines()]
    if not trace or trace[-1]['iteration'] != 30000:
        raise ValueError('Completed final training trace required for resource summary')
    anchors = [row for row in trace if row['iteration']==8000]
    prefix = anchors[0]['elapsed_seconds'] if len(anchors)==1 else None
    rows.append(dict(region=region, condition=condition, phase='training_trace',
        cost_category='SUPPLEMENTAL_REPEAT_INSTRUMENTATION_INTERVAL' if supplemental else 'INSTRUMENTATION_INTERVAL', supplemental_only=supplemental,
        wall_seconds=trace[-1]['elapsed_seconds'], instrumented_process_elapsed_seconds=trace[-1]['elapsed_seconds'],
        training_start_iteration=start_iteration,
        post_anchor_instrumented_interval_seconds=(trace[-1]['elapsed_seconds']-prefix if prefix is not None else
                                                   trace[-1]['elapsed_seconds'] if start_iteration==8000 else None),
        interval_interpretation=('resumed process interval includes initialization/restore' if start_iteration==8000 else
                                 'step8000-to-step30000 trace interval includes anchor serialization; not isolated optimizer time'),
        peak_cuda_allocated_bytes=max(row['peak_cuda_allocated_bytes'] for row in trace),
        peak_cuda_reserved_bytes=max(row['peak_cuda_reserved_bytes'] for row in trace),
        child_peak_rss_bytes=max(row['peak_rss_bytes'] for row in trace), final_gaussians=trace[-1]['gaussians'],
        protected_final=trace[-1]['protected'], anchor_prefix_elapsed_seconds=prefix,
        full_pipeline_wall_seconds=None, comparable_refinement_compute_seconds=None,
        source_path=str(trace_path.relative_to(task)), source_sha256=sha(trace_path), status='MEASURED',
        resource_measurement_scope='training_process_trace_v1', **binding))
    return rows


def anchor_resource_records(task, region, anchor, layout):
    def read(record):
        path = task/record['path']
        if sha(path) != record['sha256']:
            raise ValueError('Anchor resource identity changed')
        return path.read_text()
    trace = [json.loads(line) for line in read(anchor['source_trace']).splitlines()]
    rows8000 = [row for row in trace if row['iteration']==8000]
    elapsed = rows8000[0]['elapsed_seconds'] if len(rows8000)==1 else None
    rows = [dict(region=region, condition='D005_Pnative', phase='shared_anchor_prefix',
        cost_category='SHARED_ANCHOR_PREFIX_COMPONENT', anchor_prefix_elapsed_seconds=elapsed,
        wall_seconds=None, full_pipeline_wall_seconds=None, comparable_refinement_compute_seconds=None,
        cost_interpretation='process import through completed step8000 trace; excludes checkpoint/PLY serialization; not full anchor-capture cost',
        status='MEASURED_PREFIX_ONLY' if elapsed is not None else 'UNAVAILABLE_UNAMBIGUOUS_PREFIX',
        source_path=anchor['source_trace']['path'], source_sha256=anchor['source_trace']['sha256'],
        anchor_checkpoint_directory=anchor['checkpoint_directory'], anchor_checkpoint_sha256=anchor['checkpoint']['sha256'],
        native_final_starts_from_anchor=anchor['native_final_starts_from_anchor'],
        additive_to_final_phase_totals=False, resource_measurement_scope='shared_anchor_trace_prefix_v1', **layout.binding())]
    original = json.loads(read(anchor['source_train_receipt']))
    if original['status'] != 'PASS':
        rows.append(dict(region=region, condition='D005_Pnative', phase='anchor_source_failed_attempt',
            cost_category='FAILED_ATTEMPT_NOT_ANCHOR_COST', status=original['status'],
            wall_seconds=original['wall_seconds'], raw_phase_wall_seconds=original['wall_seconds'],
            full_pipeline_wall_seconds=None, cost_interpretation='entire failed source attempt, including refinement after8000; never used as anchor duration',
            source_path=anchor['source_train_receipt']['path'], source_sha256=anchor['source_train_receipt']['sha256'],
            additive_to_final_phase_totals=False, resource_measurement_scope='failed_anchor_source_phase_v1', **layout.binding()))
    return rows


def anchor_refinement_pairs(primary_rows, final_rows):
    """Same-region, same-resolution 512 comparisons to the one shared anchor."""
    def key(row):
        return row['region'], row['candidate'].rsplit('.', 1)[1], row['sensitivity'], row['surface_kind'], float(row['threshold_m'])
    anchors = [row for row in primary_rows if row['candidate'].startswith('D005_Pnative.anchor_512.')]
    lookup = {key(row): row for row in anchors}
    if len(lookup) != len(anchors):
        raise ValueError('Duplicate shared 512 anchor metric identity')
    result = []
    for after in final_rows:
        if '.mesh_512.' not in after['candidate']:
            continue
        if key(after) not in lookup:
            raise ValueError('Final512 lacks its exactly matched regional anchor512 estimator')
        before = lookup[key(after)]
        for metric in GEOMETRY_METRICS:
            a, b = geometry_metric(before, metric), geometry_metric(after, metric)
            difference = paired_difference(a, b)
            result.append(dict(region=after['region'], condition=after['candidate'].split('.')[0],
                anchor_candidate=before['candidate'], final_candidate=after['candidate'], mesh_res=512,
                mesh_kind=key(after)[1], sensitivity=after['sensitivity'], surface_kind=after['surface_kind'],
                threshold_m=float(after['threshold_m']), metric=metric, anchor_value=a['value'], final_value=b['value'],
                anchor_status=before['status'], final_status=after['status'],
                anchor_minus_final=difference['primary_minus_repeat'], difference_status=difference['difference_status'],
                difference_positive_infinity=difference['difference_positive_infinity'],
                difference_negative_infinity=difference['difference_negative_infinity'],
                supplemental_only=after.get('supplemental_only', False),
                shared_anchor=True, comparison_family='anchor_refinement_512',
                interpretation='Same 512 extraction resolution and estimator; signed anchor-minus-final is not a uniform improvement score'))
    return result


def supplemental_completion_rows(repeat):
    """Frozen operational metadata only; never open failed-run logs or quality."""
    if repeat.completion is None:
        return [], []
    completion = repeat.completion
    source = str(completion.path.relative_to(repeat.task))
    evidence = {row['path']:row for row in completion.data['failure_evidence']}
    availability, costs = [], []
    for row in repeat.supplemental_availability:
        availability.append(dict(row, supplemental_only=True, included_in_primary_comparison=False,
            is_reference_absence=False, is_reconstruction_failure=False,
            source_completion_contract=source, **repeat.binding()))
        if row['attempted']:
            receipt_path = row['run_directory']+'/train_receipt.json'
            costs.append(dict(region=row['region'], condition=row['repeat_id'], scientific_condition=row['condition'],
                phase='train', cost_category='FAILED_SUPPLEMENTAL_ATTEMPT', status=row['status'],
                supplemental_only=True, wall_seconds=row['train_wall_seconds'], raw_phase_wall_seconds=row['train_wall_seconds'],
                native_exit_code=row['native_exit_code'], validated_exit_code=row['validated_exit_code'],
                last_completed_trace_iteration=row['last_completed_trace_iteration'],
                child_peak_rss_bytes=None, memory_cost_status='NOT_EXPORTED_BY_COMPLETION_CONTRACT',
                full_pipeline_wall_seconds=None, comparable_refinement_compute_seconds=None,
                additive_to_completed_run_phase_times=False, include_separately_in_total_resource_reporting=True,
                resource_measurement_scope='regional_driver_phase_v1',
                source_completion_contract=source, source_field='supplemental_availability.train_wall_seconds',
                original_failed_receipt_path=receipt_path, original_failed_receipt_sha256=evidence[receipt_path]['sha256'],
                metric_status=row['metric_status'], quality_metrics=None, scientific_verdict=None, **repeat.binding()))
    return availability, costs


def add_unavailable_repeat_view(view, row):
    """Visible operational state; unavailable repeats are not surface candidates."""
    view.setdefault('supplemental_availability', []).append(dict(row))
    view['notes'].append('Supplemental '+row['repeat_id']+': '+row['status']+'; '+row['metric_status']+
        '. Quality not assessed; no completed repeat surface/render. Neither reference absence nor reconstruction failure.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--task', type=Path, required=True)
    parser.add_argument('--analysis-config', type=Path, required=True)
    parser.add_argument('--runtime-layout', type=Path)
    parser.add_argument('--repeat-contract', type=Path)
    parser.add_argument('--resource-contract', type=Path)
    args = parser.parse_args()
    if not Path('/.dockerenv').exists():
        raise RuntimeError('Use Docker for report aggregation')
    task = args.task
    cfg = json.loads((task/'contracts/execution_v1.json').read_text())
    layout = RuntimeLayout(task, args.runtime_layout, cfg['regions'])
    layout.require_scientific_config(task/'contracts/execution_v1.json')
    repeat = SupplementalRepeat(task, args.repeat_contract, layout)
    resource = resource_policy.make_resource(task, args.resource_contract, layout, repeat)
    supplemental_availability, failed_supplemental_costs = supplemental_completion_rows(repeat)
    analysis_cfg = json.loads(args.analysis_config.read_text())
    if analysis_cfg['scientific_verdict'] is not None:
        raise ValueError('Technical summary cannot contain a scientific verdict')
    if sha(args.analysis_config) != sha(task/'contracts/evaluation_analysis_v1.json'):
        raise ValueError('Analysis policy differs from the pre-training frozen contract')
    candidate_seal_path = task/'contracts/candidates_sealed_v1.json'
    candidate_seal = json.loads(candidate_seal_path.read_text())
    candidate_seal_sha = sha(candidate_seal_path)
    layout.require_receipt(candidate_seal)
    repeat.require_candidates(candidate_seal)
    resource_policy.require(resource, candidate_seal)
    sealed_files = {row['path']:row for row in candidate_seal['files']}
    if candidate_seal['status'] != resource_policy.seal_status(resource) or candidate_seal['config_sha256'] != sha(task/'contracts/execution_v1.json'):
        raise ValueError('Summary requires the complete frozen candidate matrix')
    output = task/'evaluation/summary'
    output.mkdir(parents=True, exist_ok=False)
    all_geometry, all_optical, all_optical_images, resources, relation, cases, strata = [], [], [], [], [], [], []
    repeat_geometry, repeat_optical, repeat_optical_images, repeat_resources = [], [], [], []
    case_figure_inputs, display_files = {}, {}
    manifest = {'schema': 'geogs_p1p2p3_viewer_v1', 'scientific_verdict': None,
                **layout.binding(),
                **repeat.binding(),
                **resource_policy.binding(resource),
                'title': 'Official GeoGS — P1/P2/P3 fixed-control development diagnostic',
                'notes': ['ALS surface adaptation; prior initialization and anchor retained in every condition',
                          'Unsigned proximity to observed UAS; reference absence is not proof of reconstruction error',
                          'Source/display samples are not Gaussian centers or quantitative scoring proxies'], 'regions': [],
                'downloads': [{'label':'All geometry CSV', 'url':'../summary/geometry_all.csv'},
                              {'label':'Geometry region-macro CSV', 'url':'../summary/geometry_region_macro.csv'},
                              {'label':'Heldout render CSV', 'url':'../summary/render_summary.csv'},
                              {'label':'Render pooled image means CSV', 'url':'../summary/render_pooled_image_weighted.csv'},
                              {'label':'Render equal-region means CSV', 'url':'../summary/render_region_macro.csv'},
                              {'label':'All cell diagnostics', 'url':'../summary/cell_relations.csv'}]}
    if resource:
        manifest.update(default_resolution='1024', resolution_modes=[
            dict(id='1024', label='Main final comparison 1024', mesh_res=1024, anchor_variant='anchor', final_variant='final'),
            dict(id='512', label='Matched anchor/refinement 512', mesh_res=512, anchor_variant='anchor_512', final_variant='mesh_512')])
        manifest['notes'].append('Main comparisons remain final1024. Anchor/refinement comparisons use common512. Optional MEMCG OOM is technical unavailability, not reference absence or reconstruction failure.')
    for region, spec in cfg['regions'].items():
        geometry_root = task/'evaluation/geometry'/region
        receipt = json.loads((geometry_root/'receipt.json').read_text())
        if receipt['status'] != 'PASS_GEOMETRY_EVALUATION':
            raise ValueError('Geometry evaluation is incomplete')
        if receipt['candidate_seal_sha256'] != candidate_seal_sha:
            raise ValueError('Geometry evaluation uses a different candidate seal')
        layout.require_receipt(receipt)
        repeat.require_receipt(receipt)
        resource_policy.require(resource, receipt)
        with (geometry_root/'geometry_metrics.csv').open() as f:
            primary_rows, supplemental_rows = partition_geometry(list(csv.DictReader(f)), repeat)
            all_geometry += primary_rows
            repeat_geometry += supplemental_rows
        local_rows, local_cases, local_strata = relation_rows(task, region, cfg, analysis_cfg)
        for row in local_rows+local_cases+local_strata:
            row.update(layout.binding())
            row.update(repeat.binding())
            row.update(resource_policy.binding(resource))
        relation += local_rows
        cases += local_cases
        strata += local_strata
        index = json.loads((geometry_root/'viewer_index.json').read_text())
        view = {'id': region, 'label': region, 'bounds': {'min':[spec['domain'][a][0] for a in 'xyz'],
                 'max':[spec['domain'][a][1] for a in 'xyz']},
                'frame':'EPSG:25832 local meters; world shift [690953,5336071,604]; fixed existing ALS bridge',
                'notes':['UAS header EPSG:32632; no reference-based alignment; absolute datum/epoch unresolved',
                         'Agreement/disagreement strata are evaluation-only geometry relations, not temporal truth'],
                'candidates':[], 'conditions':[], 'sections':[], 'renders':[],
                'panel_candidates':{'prior':'prior_mesh','mvs':'mvs_points','anchor':'D005_Pnative.anchor.raw',
                                    'vanilla':'D005_Pnative.final.raw','reference':'reference'}}
        for row in index['candidates']:
            candidate_metrics = json.loads((task/row['metrics_relative']).read_text())
            layout.require_receipt(candidate_metrics)
            repeat.require_receipt(candidate_metrics)
            resource_policy.require(resource, candidate_metrics)
            for path in (task/row['metrics_relative'], (task/row['metrics_relative']).with_suffix('.npz')):
                record = file_record(task, path)
                case_figure_inputs[record['path']] = record
            display_metadata = row.get('display_metadata', {})
            candidate_status, display_reason = display_candidate_state(candidate_metrics,display_metadata)
            supplemental = row['id'].split('.')[0] == repeat.identifier
            label = 'Supplemental native repetition — '+row['id'] if supplemental else row['id']
            mesh_data, original_mesh = row.get('mesh_data'),row.get('original_mesh')
            display_downloads = [{'label':'Full metric JSON','url':'../../'+row['metrics_relative']},
                                 {'label':'Display samples (not scoring input)','url':region+'/'+row['data_url']}]
            mesh_downloads,mesh_files=manifest_mesh_links(task,mesh_data,original_mesh,sealed_files)
            display_downloads.extend(mesh_downloads)
            display_files.update({record['path']:record for record in mesh_files})
            view['candidates'].append({'id':row['id'], 'label':label, 'status':candidate_status, 'reason':display_reason, 'role':row['role'],
                'supplemental_only':supplemental,
                'evaluation_status':candidate_metrics['status'],
                'data':{'url':region+'/'+row['data_url'],'format':'json'}, 'surface_kind':row['surface_kind'],
                'provenance':{'source_path':row['source_path'],'full_evaluation':row['metrics_relative'],
                              'display':display_metadata,'original_mesh':original_mesh},
                'mesh_data':mesh_data,'display_metadata':display_metadata,
                'distance_definition':'unsigned proximity to observed UAS points; unsupported samples remain ambiguous',
                'downloads':display_downloads})
            condition_id = row['id'].split('.')[0] if row['role'] in ('changed','vanilla','native_repetition') else None
            for suffix, label in [('section_url','Fixed sections'), ('distance_url','Reference distance map')]:
                view['sections'].append({'id':row['id']+'.'+suffix,'label':row['id']+' — '+label,
                    'url':region+'/'+row[suffix],'caption':'Evaluated surface/original-point samples; same fixed bounds, width0.5m and distance0..2m scale. Sections are sample bands, not mesh-plane intersection lines.',
                    'selection_reason':'all candidates at preregistered region midpoints / whole ROI',
                    'condition_id':condition_id})
        if resource:
            for unavailable in candidate_seal['extraction_inventory']:
                if unavailable['region'] != region or unavailable['status'] != resource_policy.UNAVAILABLE:
                    continue
                for mesh_kind in ('raw', 'post'):
                    view['candidates'].append(dict(id=unavailable['condition']+'.'+unavailable['variant']+'.'+mesh_kind,
                        label='Technical resource unavailable — '+unavailable['variant'],
                        status='failed', reason='TECHNICAL_RESOURCE_UNAVAILABLE: native SIGKILL with confirmed matching MEMCG OOM; no geometry score was assigned.',
                        surface_kind='official_bounded_TSDF_triangle_mesh',
                        role='anchor' if unavailable['iteration']==8000 else 'changed',
                        provenance=unavailable, supplemental_only=unavailable['supplemental_only'],
                        downloads=[dict(label='Confirmed resource failure receipt', url='../../'+unavailable['receipt']['path'])]))
        view['candidates'].append({'id':'reference','label':'Observed current UAS','role':'reference',
            'status':'available' if index['reference_points'] else 'reference_unavailable',
            'data':{'url':region+'/reference.json','format':'json'}, 'surface_kind':'original_observed_reference_points',
            'provenance':{'evaluation_only':True,'reference_points':index['reference_points'],
                          'display':index.get('reference_display_metadata',{})},
            'display_metadata':index.get('reference_display_metadata',{})})
        native_candidate = next(row for row in candidate_seal['candidates'] if row['region']==region and
                                row['condition']=='D005_Pnative' and row['variant']==('anchor_512' if resource else 'anchor') and row['mesh_kind']=='raw')
        resources.extend(anchor_resource_records(task, region, native_candidate['anchor_provenance'], layout))
        conditions = cfg['conditions'] + ([{'id':repeat.identifier}] if repeat.evaluation_enabled(region) else [])
        for condition in conditions:
            condition_id = condition['id']
            supplemental = condition_id == repeat.identifier
            label = 'Supplemental native repetition (same anchor) — '+condition_id if supplemental else condition_id
            view['conditions'].append({'id':condition_id,'label':label,'candidate_id':condition_id+'.final.raw',
                                       'supplemental_only':supplemental,'included_in_primary_comparison':not supplemental})
            (repeat_resources if supplemental else resources).extend(resource_records(task, region, condition_id, layout, sealed_files, repeat, resource))
            stages = (list(dict.fromkeys(row['variant'] for row in candidate_seal['candidates'] if row['region']==region and row['condition']==condition_id and row['render_records']))
                      if resource else ['final'] + (['anchor'] if condition_id=='D005_Pnative' or supplemental else []))
            for stage in stages:
                root = task/'evaluation/renders'/region/condition_id/stage
                quality = json.loads((root/'receipt.json').read_text())
                if quality['status'] != 'PASS_RENDER_QUALITY_EVALUATION':
                    raise ValueError('Render quality has recorded failures requiring review')
                if quality['sealed_render_manifest_sha256'] != candidate_seal_sha:
                    raise ValueError('Render evaluation uses a different candidate seal')
                layout.require_receipt(quality)
                repeat.require_receipt(quality)
                resource_policy.require(resource, quality)
                for domain in ('full_frame','fixed_prism_projected_bbox'):
                    rows = [row for row in quality['rows'] if row['domain']==domain]
                    assessed = [row for row in rows if row['status']=='ASSESSED']
                    summary = optical_summary(rows, region=region, condition=condition_id, stage=stage, domain=domain,
                                              aggregation='REGIONAL_UNWEIGHTED_PER_IMAGE_MEAN', supplemental_only=supplemental,
                                              **layout.binding(), **repeat.binding())
                    (repeat_optical if supplemental else all_optical).append(summary)
                    (repeat_optical_images if supplemental else all_optical_images).extend(
                        dict(row, region=region, condition=condition_id, stage=stage, domain=domain,
                             supplemental_only=supplemental, **layout.binding(), **repeat.binding()) for row in rows)
                    for row in assessed:
                        view['renders'].append({'id':condition_id+'.'+stage+'.'+str(row['evaluation_index'])+'.'+domain,
                            'label':label+' '+stage+' '+row['name']+' '+domain,
                            'url':str((root/row['montage']).relative_to(task/'evaluation')).replace('renders/','../renders/',1),
                            'caption':'Actual heldout photo / saved native render / fixed 0..255 RGB error',
                            'selection_reason':'all heldout views; no favorable view filtering',
                            'condition_id':condition_id,'image_name':row['name'],'domain':domain,'stage':stage,'split':'evaluation',
                            'supplemental_only':supplemental})
        for unavailable in supplemental_availability:
            if unavailable['region'] == region:
                add_unavailable_repeat_view(view, unavailable)
        view['cases'] = viewer_cases(local_cases, spec['domain'])
        manifest['regions'].append(view)
    csv_write(output/'geometry_all.csv', all_geometry)
    primary_geometry = all_geometry
    optional_complete = None
    if resource:
        primary_geometry = [row for row in all_geometry if resource_policy.comparison_family(row['candidate']) in ('input_baseline', 'primary_1024')]
        matched512 = [row for row in all_geometry if resource_policy.comparison_family(row['candidate']) == 'anchor_refinement_512']
        availability = resource_policy.inventory_availability(candidate_seal)
        expected_conditions = [row['id'] for row in cfg['conditions']] + ([repeat.identifier] if repeat.evaluable_regions else [])
        optional_complete = resource_policy.optional_final_inventory_complete(candidate_seal, cfg['regions'], expected_conditions)
        csv_write(output/'geometry_primary_1024.csv', primary_geometry)
        csv_write(output/'geometry_anchor_refinement_512.csv', matched512)
        csv_write(output/'geometry_anchor_refinement_512_region_macro.csv', geometry_region_macro(matched512, list(cfg['regions'])))
        csv_write(output/'anchor_to_refinement_512_pairs.csv', anchor_refinement_pairs(all_geometry, all_geometry+repeat_geometry))
        csv_write(output/'extraction_availability.csv', availability)
        extraction_costs = [dict(region=row['region'], condition=row['condition'], variant=row['variant'],
            mesh_res=row['mesh_res'], status=row['status'], required=row['required'],
            supplemental_only=row['supplemental_only'], wall_seconds=row.get('wall_seconds'),
            child_peak_rss_bytes=row.get('child_peak_rss_bytes'),
            sampled_peak_memory_current_bytes=row.get('sampled_peak_memory_current_bytes'),
            cgroup_memory_limit_bytes=row.get('cgroup_memory_limit_bytes'),
            cgroup_oom_kill_delta=row.get('cgroup_oom_kill_delta'),
            host_headroom_wait_seconds=row.get('host_headroom_wait_seconds'),
            producer_receipt_path=row['receipt']['path'], producer_receipt_sha256=row['receipt']['sha256'],
            included_within_auxiliary_phase_cost=True, additive_to_phase_totals=False,
            shared_anchor=row['iteration']==8000, resource_measurement_scope='resource_v3_auxiliary_variant_v1',
            **resource_policy.binding(resource))
            for row in candidate_seal['extraction_inventory']]
        csv_write(output/'extraction_attempt_resources.csv', extraction_costs)
        optional_geometry = [row for row in all_geometry if resource_policy.comparison_family(row['candidate']) == 'optional_extraction_diagnostic']
        csv_write(output/'geometry_optional_available_individual.csv', optional_geometry)
        optional_final = [row for row in optional_geometry if '.mesh_2048.' in row['candidate']]
        if optional_complete:
            csv_write(output/'geometry_optional_2048_region_macro.csv', geometry_region_macro(optional_final, list(cfg['regions'])))
        dump(output/'optional_extraction_interpretation.json', dict(scientific_verdict=None,
            **resource_policy.binding(resource), optional_final_complete_matched_inventory=optional_complete,
            aggregate_status='COMPLETE_MATCHED_INVENTORY' if optional_complete else 'NOT_AGGREGATED_INCOMPLETE_RESOURCE_INVENTORY',
            available_individual_rows=len(optional_geometry),
            technical_unavailable_variants=sum(row['status']==resource_policy.UNAVAILABLE for row in availability),
            quality_metrics_for_technical_unavailability=None, missing_optional_rows_not_silently_dropped=True,
            anchor1024='Available individual diagnostic only; matched anchor-to-final claims use common512',
            optional2048='No across-condition aggregate or native/repeat difference unless every declared regional condition and repetition has a completed surface'))
        manifest['downloads'].extend([
            dict(label='Primary final1024 geometry', url='../summary/geometry_primary_1024.csv'),
            dict(label='Matched anchor/refinement512 metrics', url='../summary/geometry_anchor_refinement_512.csv'),
            dict(label='Shared anchor512 minus final512', url='../summary/anchor_to_refinement_512_pairs.csv'),
            dict(label='All planned extraction availability', url='../summary/extraction_availability.csv')])
    geometry_macro = geometry_region_macro(primary_geometry, list(cfg['regions']))
    image_pooled, optical_macro = optical_pooled(all_optical_images, list(cfg['regions']))
    for row in geometry_macro+image_pooled+optical_macro:
        row.update(layout.binding())
        row.update(repeat.binding())
        row.update(resource_policy.binding(resource))
    csv_write(output/'geometry_region_macro.csv', geometry_macro)
    csv_write(output/'render_summary.csv', all_optical)
    csv_write(output/'render_all_images.csv', all_optical_images)
    csv_write(output/'render_pooled_image_weighted.csv', image_pooled)
    csv_write(output/'render_region_macro.csv', optical_macro)
    csv_write(output/'resource_summary.csv', resources)
    csv_write(output/'cell_relations.csv', relation)
    csv_write(output/'relation_strata.csv', strata)
    supplemental_counts = None
    if repeat.evaluable_regions:
        supplemental_output = output/'supplemental_repeat'
        supplemental_output.mkdir()
        compared_primary, compared_repeat = all_geometry, repeat_geometry
        compared_optical = all_optical_images
        if resource:
            variants = ('final', 'mesh_512', 'mesh_2048') if optional_complete else ('final', 'mesh_512')
            compared_primary = [row for row in all_geometry if '.' in row['candidate'] and row['candidate'].split('.')[1] in variants]
            compared_repeat = [row for row in repeat_geometry if row['candidate'].split('.')[1] in variants]
            compared_optical = [row for row in all_optical_images if row['stage']=='final']
        geometry_difference = geometry_repeat_differences(compared_primary, compared_repeat, repeat.identifier)
        optical_difference = optical_repeat_differences(compared_optical, repeat_optical_images, repeat.identifier)
        paired_optical_summary = optical_difference_summary(optical_difference)
        repeat_geometry_macro = geometry_region_macro([row for row in repeat_geometry if not resource or '.final.' in row['candidate']], list(cfg['regions']))
        repeat_image_pooled, repeat_optical_macro = optical_pooled(repeat_optical_images, list(cfg['regions']))
        tables = {'geometry_all.csv':repeat_geometry, 'geometry_region_macro.csv':repeat_geometry_macro,
                  'geometry_primary_minus_repeat.csv':geometry_difference,
                  'render_summary.csv':repeat_optical, 'render_all_images.csv':repeat_optical_images,
                  'render_pooled_image_weighted.csv':repeat_image_pooled, 'render_region_macro.csv':repeat_optical_macro,
                  'render_primary_minus_repeat_images.csv':optical_difference,
                  'render_primary_minus_repeat_summary.csv':paired_optical_summary, 'resource_summary.csv':repeat_resources}
        for name, rows in tables.items():
            for row in rows:
                row.update(layout.binding())
                row.update(repeat.binding())
                row.update(resource_policy.binding(resource))
                row['supplemental_only'] = True
            csv_write(supplemental_output/name, rows)
        supplemental_counts = {name:len(rows) for name, rows in tables.items()}
        dump(supplemental_output/'interpretation.json', dict(scientific_verdict=None, **layout.binding(), **repeat.binding(), **resource_policy.binding(resource),
            supplemental_only=True, included_in_primary_comparison=False, primary_condition_count=len(cfg['conditions']),
            comparison='descriptive primary native minus one same-allocator same-anchor native repetition per region',
            anchor_interpretation=('One primary regional anchor surface/render is shared; it is not an independent repetition and no repeated-anchor difference is reported' if resource else 'anchor differences measure extraction/render repetition from the identical regional iteration8000 checkpoint'),
            optional2048_difference_status=('COMPLETE_MATCHED_INVENTORY' if optional_complete else 'NOT_COMPARED_RESOURCE_INVENTORY_INCOMPLETE') if resource else None,
            final_interpretation='final differences combine subsequent execution and extraction variation; not an isolated optimizer variance estimate',
            quality_noise_bound=False, confidence_interval=False, independent_inference=False,
            scientific_settings_changed=False, row_counts=supplemental_counts,
            metric_direction='signed primary-minus-repeat, not a uniform improvement score; smaller distance/LPIPS and larger PSNR/SSIM/F1 have different directions'))
        manifest['notes'].append('One supplemental native repetition per region is separate from six primary conditions; differences are descriptive, not a quality noise bound or confidence interval.')
        manifest['downloads'].extend([
            {'label':'Supplemental repetition geometry', 'url':'../summary/supplemental_repeat/geometry_all.csv'},
            {'label':'Native minus repetition geometry', 'url':'../summary/supplemental_repeat/geometry_primary_minus_repeat.csv'},
            {'label':'Native minus repetition heldout renders', 'url':'../summary/supplemental_repeat/render_primary_minus_repeat_summary.csv'},
            {'label':'Supplemental repetition resource cost', 'url':'../summary/supplemental_repeat/resource_summary.csv'}])
    if repeat.completion is not None:
        supplemental_output = output/'supplemental_repeat'
        supplemental_output.mkdir()
        csv_write(supplemental_output/'availability.csv', supplemental_availability)
        csv_write(supplemental_output/'failed_attempt_resources.csv', failed_supplemental_costs)
        dump(supplemental_output/'interpretation.json', dict(scientific_verdict=None, **repeat.binding(),
            **repeat.completion.data['supplemental_policy'],
            status='SUPPLEMENTAL_INCOMPLETE_NO_PAIRED_QUALITY_ASSESSMENT',
            supplemental_availability=supplemental_availability,
            availability_rows=len(supplemental_availability), failed_attempt_cost_rows=len(failed_supplemental_costs),
            failed_run_payloads_read_by_summary=False, primary_rows_selected_from_successful_repeats=False,
            failure_evidence=repeat.completion.data['failure_evidence']))
        supplemental_counts = dict(availability_rows=len(supplemental_availability),
                                  failed_attempt_cost_rows=len(failed_supplemental_costs), paired_metric_rows=0)
        manifest['notes'].append(repeat.completion.data['supplemental_policy']['interpretation'])
        manifest['downloads'].extend([
            dict(label='Supplemental execution availability: failed / not attempted', url='../summary/supplemental_repeat/availability.csv'),
            dict(label='Original failed supplemental driver costs', url='../summary/supplemental_repeat/failed_attempt_resources.csv'),
            dict(label='Supplemental incomplete interpretation', url='../summary/supplemental_repeat/interpretation.json')])
    dump(output/'selected_cases.json', {'scientific_verdict':None,'analysis_config_sha256':sha(args.analysis_config),
                                      **layout.binding(),
                                      **repeat.binding(),
                                      **resource_policy.binding(resource),
                                      'cases':cases,'selection_is_parameter_tuning':False})
    dump(output/'resource_measurement_definitions.json', resource_measurement_definitions())
    dump(task/'evaluation/viewer/manifest.json', manifest)
    summary_files = [file_record(task, path) for path in sorted(output.rglob('*')) if path.is_file()]
    summary_files.append(file_record(task, task/'evaluation/viewer/manifest.json'))
    summary_files.extend(display_files.values())
    dump(output/'receipt.json', {'scientific_verdict':None,'status':'TABLES_AND_ACTUAL_VIEWER_DATA_READY',
        **layout.binding(),
        **repeat.binding(),
        **resource_policy.binding(resource),
        'analysis_config_sha256':sha(args.analysis_config),'regions':list(cfg['regions']),
        'candidate_seal_sha256':candidate_seal_sha, 'config_sha256':sha(task/'contracts/execution_v1.json'),
        'summary_files':summary_files, 'case_figure_input_files':list(case_figure_inputs.values()),
        'resource_measurement_definitions_path':'evaluation/summary/resource_measurement_definitions.json',
        'geometry_rows':len(all_geometry),'render_rows':len(all_optical),'cases':len(cases),
        'geometry_macro_rows':len(geometry_macro), 'render_pooled_rows':len(image_pooled),
        'render_macro_rows':len(optical_macro), 'pooled_independent_inference':False,
        'primary_condition_count':len(cfg['conditions']), 'supplemental_tables':supplemental_counts,
        'supplemental_in_primary_tables_or_case_ranking':False,
        'geometry_failure_rows':sum(row['status']=='RECONSTRUCTION_FAILURE' for row in all_geometry),
        'geometry_reference_absent_rows':sum(row['status']=='NOT_ASSESSED_REFERENCE_ABSENT' for row in all_geometry),
        'case_failure_transitions':sum('RECONSTRUCTION_FAILURE' in row['distance_transition'] for row in cases),
        'scientific_conclusions_automatically_generated':False,'browser_qa_required':True})
    print(json.dumps({'status':'TABLES_AND_ACTUAL_VIEWER_DATA_READY','scientific_verdict':None}))


if __name__ == '__main__':
    main()
