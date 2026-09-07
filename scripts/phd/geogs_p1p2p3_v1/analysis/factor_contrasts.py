"""Additive, post-seal contrasts of existing metrics; no scoring or selection."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import sys

CONDITIONS = {
    'D005_Pnative': (.005, 'native'), 'D0005_Pnative': (.0005, 'native'),
    'D0_Pnative': (0., 'native'), 'D005_Prelease': (.005, 'released'),
    'D0005_Prelease': (.0005, 'released'), 'D0_Prelease': (0., 'released')}
GEOMETRY_METRICS = ('precision', 'recall', 'f1',
    'p2ref_mean_m', 'p2ref_median_m', 'p2ref_p95_m', 'p2ref_rmse_m',
    'ref2candidate_mean_m', 'ref2candidate_median_m', 'ref2candidate_p95_m', 'ref2candidate_rmse_m',
    'surface_area_m2', 'far_from_observed_reference_area_estimate_m2')
OPTICAL_METRICS = ('psnr_native_db', 'ssim_native', 'lpips_vgg_native_01', 'lpips_vgg_signed_11')
DOMAINS = ('full_frame', 'fixed_prism_projected_bbox')
CAMERA_FIELDS = ('name', 'evaluation_index', 'image_id', 'camera_id', 'photo_sha256',
                 'seed', 'roi_x0', 'roi_y0', 'roi_x1', 'roi_y1', 'pixel_count')
EXPLANATION = ('Descriptive difference of completed primary runs under the unchanged adaptive DA3 rule; '
    'realized DA3 weights may differ. Protection release jointly changes gradient attenuation and topology restrictions. '
    'Prior initialization and the common anchor remain. No ranking, confidence interval, repeat substitution or scientific verdict.')


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def dump(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False, ensure_ascii=False)


def file_record(root, path):
    path = Path(path)
    return dict(path=str(path.relative_to(root)), sha256=sha(path), bytes=path.stat().st_size)


def truth(value):
    if value in (True, 'True', 'true', '1', 1):
        return True
    if value in (False, 'False', 'false', '0', 0, '', None):
        return False
    raise ValueError('Invalid CSV boolean: '+str(value))


def mapping():
    rows = []
    for lower in ('D0005', 'D0'):
        for protection in ('Pnative', 'Prelease'):
            rows.append(dict(id=f'depth_D005_to_{lower}_{protection}', family='depth_at_fixed_protection',
                terms=[(lower+'_'+protection, 1), ('D005_'+protection, -1)],
                formula='lower_depth - depth_0.005'))
    for depth in ('D005', 'D0005', 'D0'):
        rows.append(dict(id=f'protection_{depth}_native_to_release', family='protection_at_fixed_depth',
            terms=[(depth+'_Prelease', 1), (depth+'_Pnative', -1)], formula='release - native'))
    for lower in ('D0005', 'D0'):
        rows.append(dict(id=f'interaction_D005_to_{lower}', family='difference_of_differences',
            terms=[(lower+'_Prelease', 1), ('D005_Prelease', -1),
                   (lower+'_Pnative', -1), ('D005_Pnative', 1)],
            formula='(lower_release - 0.005_release) - (lower_native - 0.005_native)'))
    return dict(schema='GEOGS_PRIMARY_FACTOR_CONTRAST_MAPPING_v1', scientific_verdict=None,
        conditions={key:dict(depth_weight=value[0], protection=value[1]) for key, value in CONDITIONS.items()},
        contrasts=rows, interpretation=EXPLANATION, regional_aggregation=False,
        positive_contrast='Increase in this metric; interaction is a change in the depth contrast, not a simple quality gain',
        render_aggregation='Equal-image mean only if every declared image contrast is finite and identity-matched; no finite-survivor mean')


def metric_direction(metric):
    if metric in ('precision', 'recall', 'f1', 'psnr_native_db', 'ssim_native'):
        return 'HIGHER'
    if metric == 'surface_area_m2':
        return 'NO_MONOTONIC_QUALITY_DIRECTION'
    if metric == 'far_from_observed_reference_area_estimate_m2':
        return 'LOWER_OBSERVED_REFERENCE_DISAGREEMENT_NOT_CONFIRMED_ERROR_AREA'
    return 'LOWER'


def number(value, missing='MISSING_METRIC'):
    result = dict(value=None, status=missing, positive_infinity=False, negative_infinity=False)
    if value is None or value == '':
        return result
    try:
        numeric = float(value)
    except (ValueError, TypeError):
        return dict(result, status='INVALID_NUMERIC')
    if math.isnan(numeric):
        return dict(result, status='INVALID_NAN')
    if math.isinf(numeric):
        return dict(result, status='POSITIVE_INFINITY' if numeric > 0 else 'NEGATIVE_INFINITY',
                    positive_infinity=numeric > 0, negative_infinity=numeric < 0)
    return dict(result, value=numeric, status='FINITE')


def metric_value(row, metric, optical=False):
    if row is None:
        return number(None, 'MISSING_ROW')
    status = row['status']
    if optical:
        if status != 'ASSESSED':
            return number(None, status)
        if metric == 'psnr_native_db' and truth(row.get('psnr_positive_infinity')):
            require(row.get(metric) in (None, ''), 'Infinite PSNR may not also contain a finite score')
            return number(float('inf'))
        return number(row.get(metric), row.get('lpips_status', 'MISSING_METRIC')
                      if metric.startswith('lpips') else 'MISSING_METRIC')
    if metric == 'surface_area_m2':
        # Surface size is defined independently of reference presence.
        return number(row.get(metric))
    if status == 'NOT_ASSESSED_REFERENCE_ABSENT':
        require(row.get(metric) in (None, ''), 'Reference-absent quality metric must be unavailable')
        return number(None, status)
    if status == 'RECONSTRUCTION_FAILURE':
        if metric.startswith('ref2candidate_'):
            # Existing evaluator stores an empty prediction as +infinity per reference point;
            # its strict-JSON distance statistics cannot retain this in the numeric CSV field.
            require(row.get(metric) in (None, '', 'inf') or row.get(metric) == float('inf'),
                    'Empty prediction cannot have a finite reference-to-surface distance')
            return dict(number(float('inf')), status='POSITIVE_INFINITY_EMPTY_PREDICTION')
        if metric.startswith('p2ref_'):
            require(row.get(metric) in (None, ''), 'Empty prediction has no forward distance samples')
            return number(None, 'UNDEFINED_EMPTY_PREDICTION')
        # Do not invent zeros: the upstream failure convention must already be present.
        if metric in ('precision', 'recall', 'f1', 'far_from_observed_reference_area_estimate_m2'):
            require(row.get(metric) not in (None, '') and float(row[metric]) == 0.,
                    'Existing reconstruction-failure zero is absent or inconsistent')
    elif status != 'ASSESSED_DEVELOPMENT_ONLY':
        return number(None, status)
    return number(row.get(metric))


def linear_contrast(terms):
    """Extended-real contrast; missing, invalid and infinity cancellation never become zero."""
    states = Counter(value['status'] for _, value in terms)
    unavailable = [value for _, value in terms if value['value'] is None
                   and not value['positive_infinity'] and not value['negative_infinity']]
    positive = negative = False
    for coefficient, value in terms:
        positive |= (coefficient > 0 and value['positive_infinity']) or (coefficient < 0 and value['negative_infinity'])
        negative |= (coefficient < 0 and value['positive_infinity']) or (coefficient > 0 and value['negative_infinity'])
    result = dict(contrast_value=None, contrast_status='FINITE', contrast_positive_infinity=False,
                  contrast_negative_infinity=False, operand_status_counts_json=json.dumps(states, sort_keys=True))
    if unavailable:
        return dict(result, contrast_status='UNAVAILABLE_OR_INVALID_OPERAND')
    if positive and negative:
        return dict(result, contrast_status='UNDEFINED_INFINITY_CANCELLATION')
    if positive or negative:
        return dict(result, contrast_status='POSITIVE_INFINITY' if positive else 'NEGATIVE_INFINITY',
                    contrast_positive_infinity=positive, contrast_negative_infinity=negative)
    try:
        value = math.fsum(coefficient * item['value'] for coefficient, item in terms)
    except OverflowError:
        return dict(result, contrast_status='INVALID_FINITE_ARITHMETIC_OVERFLOW')
    if not math.isfinite(value):
        return dict(result, contrast_status='INVALID_FINITE_ARITHMETIC_OVERFLOW')
    return dict(result, contrast_value=value)


def make_contrast(identity, contrast, by_condition, metric, optical=False):
    operands, values = [], []
    present = [by_condition.get(condition) for condition, _ in contrast['terms'] if by_condition.get(condition) is not None]
    mismatched = []
    if optical and present:
        mismatched = [field for field in CAMERA_FIELDS
                      if len({str(row.get(field, '')) for row in present}) > 1]
    for condition, coefficient in contrast['terms']:
        source = by_condition.get(condition)
        value = metric_value(source, metric, optical)
        values.append((coefficient, value))
        operands.append(dict(condition=condition, coefficient=coefficient,
            evaluation_status=source['status'] if source else 'MISSING_ROW',
            source_numeric_text=str(source.get(metric, '')) if source else None,
            far_area_estimate_status=source.get('far_area_estimate_status') if source else None,
            **value))
    result = dict(identity, contrast_id=contrast['id'], contrast_family=contrast['family'],
        formula=contrast['formula'], metric=metric, preferred_metric_direction=metric_direction(metric),
        **linear_contrast(values), operand_count=len(operands), operands_json=json.dumps(operands, allow_nan=False),
        identity_status='PAIR_IDENTITY_MISMATCH' if mismatched else ('MATCHED_PRESENT_ROWS' if present else 'NO_PRESENT_ROWS') if optical else 'FIXED_GEOMETRY_ESTIMATOR',
        mismatched_identity_fields_json=json.dumps(mismatched), supplemental_only=False)
    if mismatched:
        result.update(contrast_value=None, contrast_status='PAIR_IDENTITY_MISMATCH',
                      contrast_positive_infinity=False, contrast_negative_infinity=False)
    if optical:
        result['camera_identity_by_condition_json'] = json.dumps(
            {condition:{field:row.get(field) for field in CAMERA_FIELDS}
             for condition, _ in contrast['terms'] if (row := by_condition.get(condition)) is not None})
    return result


def sensitivities(cfg):
    ev = cfg['evaluation']
    values = [(ev['surface_sample_spacing_m'], ev['reference_voxel_m'])]
    values += [(item, ev['reference_voxel_m']) for item in ev['sample_sensitivity_m']]
    values += [(ev['surface_sample_spacing_m'], item) for item in ev['reference_voxel_sensitivity_m']]
    result = tuple(f'sample{a:g}_reference{b:g}' for a, b in values)
    require(len(set(result)) == len(result), 'Duplicate declared sampling sensitivity')
    return result


def geometry_contrasts(rows, cfg):
    expected = {(region, kind, sensitivity, float(threshold))
                for region in cfg['regions'] for kind in ('raw', 'post')
                for sensitivity in sensitivities(cfg) for threshold in cfg['evaluation']['thresholds_m']}
    lookup = defaultdict(dict)
    ignored = 0
    for row in rows:
        require(not truth(row.get('supplemental_only')), 'Supplemental row in primary table')
        if row['candidate'] in ('als_points', 'mvs_points', 'prior_mesh'):
            ignored += 1
            continue
        parts = row['candidate'].split('.')
        require(len(parts) == 3 and parts[0] in CONDITIONS and parts[1] == 'final' and parts[2] in ('raw', 'post'),
                'Unexpected primary1024 candidate')
        require(row['surface_kind'] == 'triangle_surface' and int(row['mesh_res']) == 1024
                and int(row['iteration']) == 30000, 'Primary surface estimator/resolution/iteration changed')
        key = row['region'], parts[2], row['sensitivity'], float(row['threshold_m'])
        require(key in expected, 'Unexpected regional geometry threshold or sensitivity')
        require(parts[0] not in lookup[key], 'Duplicate geometry metric identity')
        lookup[key][parts[0]] = row
    results = []
    for region, kind, sensitivity, threshold in sorted(expected):
        identity = dict(region=region, mesh_res=1024, stage='final', mesh_kind=kind,
                        sensitivity=sensitivity, surface_kind='triangle_surface', threshold_m=threshold)
        for contrast in mapping()['contrasts']:
            for metric in GEOMETRY_METRICS:
                results.append(make_contrast(identity, contrast, lookup[(region, kind, sensitivity, threshold)], metric))
    return results, dict(ignored_baseline_rows=ignored, expected_condition_rows=len(expected)*len(CONDITIONS),
                        present_condition_rows=sum(map(len, lookup.values())))


def optical_contrasts(rows, cfg):
    lookup = defaultdict(dict)
    names_seen = defaultdict(set)
    ignored = 0
    for row in rows:
        require(not truth(row.get('supplemental_only')), 'Supplemental row in primary table')
        require(row['condition'] in CONDITIONS, 'Unexpected optical primary condition')
        if row['stage'] in ('anchor', 'anchor_512') and row['condition'] == 'D005_Pnative':
            ignored += 1
            continue
        require(row['stage'] == 'final' and row['region'] in cfg['regions'] and row['domain'] in DOMAINS,
                'Unexpected optical stage, region or domain')
        index = int(row['evaluation_index'])
        require(0 <= index < cfg['regions'][row['region']]['expected_test'], 'Unexpected evaluation image index')
        key = row['region'], row['domain'], index
        require(row['condition'] not in lookup[key], 'Duplicate optical metric identity')
        name_key = row['region'], row['condition'], row['domain']
        require(row['name'] and row['name'] not in names_seen[name_key], 'Duplicate or empty optical image name')
        names_seen[name_key].add(row['name'])
        lookup[key][row['condition']] = row
    # Keep declared indices even if every condition lacks the image row.
    output = []
    for region in cfg['regions']:
        for domain in DOMAINS:
            for index in range(cfg['regions'][region]['expected_test']):
                present = lookup[(region, domain, index)]
                names = sorted({row['name'] for row in present.values()})
                identity = dict(region=region, stage='final', domain=domain, evaluation_index=index,
                    name=names[0] if len(names) == 1 else None, names_present_json=json.dumps(names))
                for contrast in mapping()['contrasts']:
                    for metric in OPTICAL_METRICS:
                        output.append(make_contrast(identity, contrast, present, metric, optical=True))
    return output, dict(ignored_anchor_rows=ignored,
        expected_condition_rows=sum(row['expected_test'] for row in cfg['regions'].values())*len(DOMAINS)*len(CONDITIONS),
        present_condition_rows=sum(map(len, lookup.values())))


def optical_means(rows, cfg):
    groups = defaultdict(list)
    fields = ('region', 'stage', 'domain', 'contrast_id', 'contrast_family', 'formula', 'metric', 'preferred_metric_direction')
    for row in rows:
        groups[tuple(row[field] for field in fields)].append(row)
    output = []
    for key, members in sorted(groups.items()):
        expected = cfg['regions'][key[0]]['expected_test']
        require(len(members) == expected and {row['evaluation_index'] for row in members} == set(range(expected)),
                'Incomplete or duplicate declared image contrast membership')
        statuses = Counter(row['contrast_status'] for row in members)
        complete = statuses['FINITE'] == expected
        value = math.fsum(row['contrast_value']/expected for row in members) if complete else None
        output.append(dict(zip(fields, key), expected_image_pairs=expected, finite_image_pairs=statuses['FINITE'],
            mean_contrast_value=value, mean_status='FINITE_ALL_DECLARED_IMAGES' if complete else 'UNAVAILABLE_NOT_ALL_DECLARED_IMAGES_FINITE',
            contrast_status_counts_json=json.dumps(statuses, sort_keys=True),
            aggregation='REGIONAL_EQUAL_IMAGE_PAIRED_MEAN_NO_FINITE_SURVIVOR_MEAN', supplemental_only=False))
    return output


def load_csv(path, required):
    with Path(path).open(newline='') as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames and set(required) <= set(reader.fieldnames), 'Missing CSV columns: '+str(path))
        require(len(reader.fieldnames) == len(set(reader.fieldnames)), 'Duplicate CSV columns')
        rows = list(reader)
        require(all(None not in row and all(value is not None for value in row.values()) for row in rows),
                'Malformed CSV row width')
        return rows


def csv_write(path, rows):
    require(bool(rows), 'Expected nonempty contrast output')
    with Path(path).open('x', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def validate_policy(cfg):
    require(cfg.get('scientific_verdict') is None and list(cfg['regions']) == ['P1', 'P2', 'P3'], 'Unexpected frozen regions/verdict')
    require(len(cfg['conditions']) == len(CONDITIONS)
            and {row['id']:(row['lambda_lod_anchor'], row['protection']) for row in cfg['conditions']} == CONDITIONS,
            'The exact six-condition factor mapping is required')


def input_gate(task, gate_factory=None):
    """Validate the explicitly scoped complete seal before opening any metric CSV.

    Only contract/seal/summary files are read here. Completed producer payloads are
    not rescored or rehashed; the existing strict sealer and summary are authority.
    """
    if gate_factory is None:
        from finalization_control import FinalizationGate
        gate_factory = FinalizationGate
    gate = gate_factory(task)
    seal, seal_sha = gate.candidate_seal()
    from resource_support import seal_status
    expected_status = seal_status(gate.resource) if hasattr(gate, 'resource') else 'ALL_REQUIRED_CANDIDATES_SEALED_OPTIONAL_ACCOUNTED'
    require(seal.get('schema') == 'JBGS_GEOGS_CANDIDATES_SEALED_v2'
            and seal.get('status') == expected_status
            and seal.get('scientific_verdict') is None and seal.get('reference_accessed') is False,
            'Actual complete resource-v3 seal required')
    summary_path = task/'evaluation/summary/receipt.json'
    receipt = gate.bound_receipt(summary_path, 'TABLES_AND_ACTUAL_VIEWER_DATA_READY', seal_sha,
        config_sha256=sha(task/'contracts/execution_v1.json'),
        analysis_config_sha256=sha(task/'contracts/evaluation_analysis_v1.json'))
    require(receipt.get('regions') == ['P1', 'P2', 'P3'] and receipt.get('primary_condition_count') == 6
            and receipt.get('supplemental_in_primary_tables_or_case_ranking') is False,
            'Summary region/primary/repeat membership differs')
    items = receipt['summary_files']
    require(len({item['path'] for item in items}) == len(items), 'Duplicate summary inventory paths')
    selected = {}
    for name in ('geometry_primary_1024.csv', 'render_all_images.csv'):
        relative = 'evaluation/summary/'+name
        matches = [item for item in items if item['path'] == relative]
        require(len(matches) == 1, 'Required summary CSV is not bound to successful receipt')
        path = task/relative
        item = matches[0]
        require(path.is_file() and path.stat().st_size == item['bytes'] and sha(path) == item['sha256'],
                'Summary CSV bytes changed: '+name)
        selected[name] = file_record(task, path)
    require(sha(task/'contracts/candidates_sealed_v1.json') == seal_sha, 'Candidate seal changed during access gate')
    completion_binding = {key:seal[key] for key in ('completion_contract_sha256', 'evaluation_scope') if key in seal}
    contract_names = ['execution_v1.json', 'evaluation_analysis_v1.json', 'runtime_layout_allocator_v2.json',
                      'supplemental_repeat_v1.json', 'extraction_resource_v3.json', 'candidates_sealed_v1.json']
    if seal.get('completion_contract_sha256'):
        contract_names.append('evaluation_completion_v2.json')
    return dict(candidate_seal_sha256=seal_sha, summary_receipt=file_record(task, summary_path),
                summary_csv_files=selected, config_sha256=seal['config_sha256'],
                contract_files=[file_record(task, task/'contracts'/name) for name in contract_names],
                runtime_layout_sha256=seal['runtime_layout_sha256'], repeat_contract_sha256=seal['repeat_contract_sha256'],
                resource_contract_sha256=seal['resource_contract_sha256'],
                **completion_binding,
                seal_validation='Exact declared complete candidate/inventory gate plus bound summary receipt; no arbitrary subset or producer payload rehash')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--task', type=Path, default=Path('/task'))
    parser.add_argument('--output', type=Path, default=Path('/out/results'))
    args = parser.parse_args()
    require(Path('/.dockerenv').exists(), 'Run this analysis in Docker')
    require(not Path('/reference').exists() and not Path('/artifacts/JointBuildGS').exists(), 'Raw reference mount forbidden')
    access = input_gate(args.task)
    cfg = read_json(args.task/'contracts/execution_v1.json')
    validate_policy(cfg)
    geometry = load_csv(args.task/'evaluation/summary/geometry_primary_1024.csv',
        ('region', 'candidate', 'surface_kind', 'sensitivity', 'threshold_m', 'status', 'mesh_res', 'iteration', *GEOMETRY_METRICS))
    optical = load_csv(args.task/'evaluation/summary/render_all_images.csv',
        ('region', 'condition', 'stage', 'domain', 'status', 'psnr_positive_infinity', 'lpips_status', *CAMERA_FIELDS, *OPTICAL_METRICS))
    for rows in (geometry, optical):
        for row in rows:
            for key in ('runtime_layout_sha256', 'repeat_contract_sha256'):
                require(row.get(key) == access[key], 'Metric row contract binding changed: '+key)
    contrasts_g, inventory_g = geometry_contrasts(geometry, cfg)
    contrasts_o, inventory_o = optical_contrasts(optical, cfg)
    means = optical_means(contrasts_o, cfg)
    # Verify exact input bytes remained fixed while deriving contrasts.
    for item in access['summary_csv_files'].values():
        require(file_record(args.task, args.task/item['path']) == item, 'Metric CSV changed during derivation')
    for item in access['contract_files']:
        require(file_record(args.task, args.task/item['path']) == item, 'Contract or seal changed during derivation')
    require(file_record(args.task, args.task/'evaluation/summary/receipt.json') == access['summary_receipt'], 'Summary receipt changed')
    args.output.mkdir(parents=True, exist_ok=False)
    outputs = {'geometry_factor_contrasts.csv':contrasts_g, 'render_per_image_factor_contrasts.csv':contrasts_o,
               'render_regional_paired_contrasts.csv':means}
    for name, rows in outputs.items():
        csv_write(args.output/name, rows)
    dump(args.output/'mapping.json', mapping())
    dump(args.output/'receipt.json', dict(schema='GEOGS_POST_SUMMARY_FACTOR_CONTRASTS_v1',
        status='DESCRIPTIVE_FACTOR_CONTRAST_TABLES_READY', scientific_verdict=None,
        created_at_utc=datetime.now(timezone.utc).isoformat(), **access,
        geometry_inventory=inventory_g, render_inventory=inventory_o,
        output_rows={name:len(rows) for name, rows in outputs.items()},
        contrast_status_counts={name:dict(Counter(row['contrast_status'] for row in rows))
                                for name, rows in outputs.items() if name != 'render_regional_paired_contrasts.csv'},
        files=[file_record(args.output, path) for path in sorted(args.output.iterdir())],
        sources=[file_record(Path(__file__).parent, path) for path in sorted(Path(__file__).parent.rglob('*')) if path.is_file()],
        command_argv=sys.argv, python_version=platform.python_version(),
        runtime_image_id=os.environ.get('EXECUTION_IMAGE_ID'), git_head=os.environ.get('EXECUTION_GIT_HEAD'),
        interpretation=EXPLANATION, reference_payload_read=False, metrics_recomputed=False,
        finite_survivor_aggregation=False, regional_ranking=False, confidence_interval=False,
        repeat_included=False, existing_summary_modified=False))
    print(json.dumps(dict(status='DESCRIPTIVE_FACTOR_CONTRAST_TABLES_READY', scientific_verdict=None,
                         output_rows={name:len(rows) for name, rows in outputs.items()})))


if __name__ == '__main__':
    main()
