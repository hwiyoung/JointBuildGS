"""Reference-only evaluation of the complete, sealed regional candidate matrix."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import time

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import open3d as o3d
from scipy.spatial import cKDTree

from geometry import (evaluate_geometry, inside_half_open, voxel_reference,
                      distance_statistics, xy_support_diagnostic, save_distance_arrays)
from render_quality import NativeMetrics, evaluate_render_set
from runtime_layout import RuntimeLayout, relative_path
from supplemental_repeat import SupplementalRepeat
import resource_support as resources
from display_export import export_clipped_mesh, original_mesh_provenance

REFERENCE_SHAS = {
    'P1': '3d111cf0cd8ab39fccb85ce0075486ec40f4f60584b5c68b2ab122918b321543',
    'P2': '9dc75111e8a5e83808d566c0b6621092423898a1f6badb9438f1a0d75e16e7ba',
    'P3': 'a72041a28c8242d3901f5696d88e607473814299baab43103fda89fc179b1f81'}
SECTIONS = {'P1': [-8., -6.], 'P2': [134., 109.], 'P3': [-40., -15.]}


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(8 << 20), b''):
            h.update(block)
    return h.hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as f:
        json.dump(value, f, indent=2, allow_nan=False)


def write_csv(path, rows):
    keys = list(dict.fromkeys(key for row in rows for key in row))
    with Path(path).open('x', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def distance_table_fields(metrics):
    """Export every already-computed directional statistic without re-estimation."""
    reverse = metrics.get('reference_to_prediction_triangle') or metrics['reference_to_prediction_point']
    return {prefix+'_'+statistic+'_m': values[statistic]
            for prefix, values in [('p2ref', metrics['prediction_to_reference_point']), ('ref2candidate', reverse)]
            for statistic in ('mean', 'median', 'p95', 'rmse')}


def far_surface_area_fields(metrics, threshold):
    """Report an area-sampling estimate from the existing strict-threshold precision."""
    area, precision = metrics['surface_area_m2'], threshold['precision']
    estimate = None
    if area is None:
        status = 'NOT_APPLICABLE_POINTSET'
    elif metrics['status'] == 'NOT_ASSESSED_REFERENCE_ABSENT':
        status = 'NOT_ASSESSED_REFERENCE_ABSENT'
    elif precision is None:
        status = 'UNAVAILABLE_PRECISION'
    else:
        if not np.isfinite(area) or area < 0 or not np.isfinite(precision) or not 0 <= precision <= 1:
            raise ValueError('Far-surface area reporting requires finite nonnegative area and precision in [0,1]')
        estimate = float(area * (1. - precision))
        status = 'EMPTY_SURFACE_ZERO_AREA' if area == 0 else 'AREA_SAMPLING_ESTIMATE'
    return dict(far_from_observed_reference_area_estimate_m2=estimate,
                far_area_estimate_status=status,
                far_area_estimate_interpretation='A*(1-precision): area-sampling estimate for sample-to-observed-UAS distance >= threshold_m; reference coverage is uncertified; not confirmed wrong residual structure area')


def verify_stage_inputs(task, cfg, seal, seal_sha, region, stage):
    """Verify every regional scoring input against the original full seal.

    This changes only verification I/O. All candidates remain in the seal;
    original reference/baseline verification and scoring functions are retained.
    """
    if region not in cfg['regions'] or stage not in ('geometry', 'renders'):
        raise ValueError('Unknown regional verification scope')
    task = Path(task)
    catalogue = {row['path']: row for row in seal['files']}
    if len(catalogue) != len(seal['files']):
        raise ValueError('Duplicate sealed input path')
    verified = {}

    def check(relative, expected_sha=None, expected_bytes=None):
        relative = str(relative_path(relative))
        if relative not in catalogue:
            raise ValueError('Consumed input is absent from the full seal: ' + relative)
        record = catalogue[relative]
        if ((expected_sha is not None and record['sha256'] != expected_sha) or
                (expected_bytes is not None and record['bytes'] != expected_bytes)):
            raise ValueError('Consumed input identity differs from the sealed catalogue: ' + relative)
        if relative not in verified:
            path = task/relative
            if (path.resolve() != task.resolve()/relative or not path.is_file() or
                    path.stat().st_size != record['bytes'] or sha(path) != record['sha256']):
                raise ValueError('Consumed input bytes differ from the full seal: ' + relative)
            verified[relative] = dict(path=relative, bytes=record['bytes'], sha256=record['sha256'])
        return task/relative

    candidates = [row for row in seal['candidates'] if row['region'] == region]
    if not candidates:
        raise ValueError('Regional candidate inventory is empty')
    if stage == 'geometry':
        check(f'inputs/{region}/surface/als_surface.ply')
        for candidate in candidates:
            surface = candidate['surface']
            check(surface['path'], surface['sha256'], surface['bytes'])
    else:
        split_path = check(f'inputs/{region}/scene/split_manifest_da3_v2.json')
        split = json.loads(split_path.read_text())
        expected = sorted(split['evaluation'], key=lambda row: row['name'])
        names = {row['name'] for row in expected}
        if (len(expected) != cfg['regions'][region]['expected_test'] or len(names) != len(expected) or
                names & {row['name'] for row in split['train']} or split.get('region', region) != region):
            raise ValueError('Frozen regional evaluation image membership differs')
        for view in expected:
            check(f'inputs/{region}/scene/images/'+view['name'], view['sha256'])
        render_candidates = [row for row in candidates if row['render_records']]
        if not render_candidates:
            raise ValueError('Regional render inventory is empty')
        for candidate in render_candidates:
            records = candidate['render_records']
            mapping = {row['name']: row for row in records}
            if len(records) != len(expected) or len(mapping) != len(records) or set(mapping) != names:
                raise ValueError('Sealed regional render membership differs from exact evaluation images')
            for index, view in enumerate(expected):
                record = mapping[view['name']]
                if any(record.get(key) != value for key, value in
                       dict(evaluation_index=index, image_id=view['image_id'], camera_id=view['camera_id']).items()):
                    raise ValueError('Sealed regional render camera identity differs')
                check(record['render_path'], record['render_sha256'])
    records = [verified[key] for key in sorted(verified)]
    manifest = json.dumps(records, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
    return dict(policy='REGIONAL_CONSUMED_INPUTS_v1', stage=stage, region=region,
                candidate_seal_sha256=seal_sha, files_count=len(records),
                verified_bytes=sum(row['bytes'] for row in records), files=records,
                manifest_sha256=hashlib.sha256(manifest).hexdigest(), scientific_verdict=None)


def load_seal(task, runtime_layout=None, repeat_contract=None, resource_contract=None, stage_inputs=None):
    """Default returns the original triple after full verification.

    Explicit amended stage verification returns that triple plus its input proof.
    """
    config = task / 'contracts/execution_v1.json'
    seal_path = task / 'contracts/candidates_sealed_v1.json'
    seal = json.loads(seal_path.read_text())
    cfg = json.loads(config.read_text())
    layout = runtime_layout if isinstance(runtime_layout, RuntimeLayout) else RuntimeLayout(task, runtime_layout, cfg['regions'])
    layout.require_scientific_config(config)
    layout.require_receipt(seal)
    repeat = repeat_contract if isinstance(repeat_contract, SupplementalRepeat) else SupplementalRepeat(task, repeat_contract, layout)
    repeat.require_candidates(seal)
    resource = resource_contract if hasattr(resource_contract, 'variant_inventory') else resources.make_resource(task, resource_contract, layout, repeat)
    resources.require(resource, seal)
    if seal['status'] != resources.seal_status(resource) or seal['config_sha256'] != sha(config):
        raise ValueError('All fixed candidate outputs must be sealed before evaluation')
    if stage_inputs is not None:
        if not repeat.completion or repeat.completion.data['evaluation_scope'] != 'PRIMARY18_SUPPLEMENTAL_INCOMPLETE':
            raise ValueError('Regional verification requires the exact prospective completion amendment')
        seal_sha = sha(seal_path)
        proof = verify_stage_inputs(task, cfg, seal, seal_sha, *stage_inputs)
        if sha(seal_path) != seal_sha:
            raise ValueError('Candidate seal changed during regional input verification')
        return cfg, seal, seal_sha, proof
    for row in seal['files']:
        if sha(task / row['path']) != row['sha256']:
            raise ValueError(f'Sealed candidate bytes changed: {row["path"]}')
    return cfg, seal, sha(seal_path)


def point_metrics(points, reference, bounds, cfg):
    points = np.asarray(points)
    original_indices = np.flatnonzero(inside_half_open(points, bounds))
    prediction, selection = voxel_reference(points[original_indices], cfg['reference_voxel_m'])
    members = np.flatnonzero(inside_half_open(reference, bounds))
    ref, selected = voxel_reference(reference[members], cfg['reference_voxel_m'])
    if len(ref) == 0:
        status, p2r, r2p = 'NOT_ASSESSED_REFERENCE_ABSENT', np.full(len(prediction), np.nan), np.empty(0)
    elif len(prediction) == 0:
        status, p2r, r2p = 'RECONSTRUCTION_FAILURE', np.empty(0), np.full(len(ref), np.inf)
    else:
        status = 'ASSESSED_DEVELOPMENT_ONLY'
        p2r = cKDTree(ref).query(prediction, workers=1)[0]
        r2p = cKDTree(prediction).query(ref, workers=1)[0]
    rows = []
    for threshold in cfg['thresholds_m']:
        if not np.isfinite(threshold) or threshold <= 0:
            raise ValueError('Distance threshold must be positive')
        p = float(np.mean(p2r < threshold)) if len(prediction) and len(ref) else (0. if len(ref) else None)
        r = float(np.mean(r2p < threshold)) if len(ref) else None
        f1 = 2*p*r/(p+r) if p is not None and p+r > 0 else (0. if p is not None else None)
        rows.append(dict(threshold_m=threshold, precision=p, recall=r, f1=f1))
    metrics = {'scientific_verdict': None, 'status': status, 'surface_kind': 'ORIGINAL_POINTSET_NN_BASELINE',
               'reference_to_prediction_triangle': None, 'prediction_to_reference_point': distance_statistics(p2r),
               'reference_to_prediction_point': distance_statistics(r2p), 'thresholds': rows,
               'prediction_points': len(prediction), 'reference_points_after_voxel': len(ref),
               'prediction_original_points': len(original_indices), 'surface_area_m2': None,
               'point_voxel_m': cfg['reference_voxel_m'],
               'bounds_half_open': [[float(x) for x in bounds[axis]] for axis in 'xyz'] if isinstance(bounds, dict) else np.asarray(bounds).tolist(),
               'prediction_distance_interpretation': 'proximity between observed pointsets after equal fixed-origin voxel sampling; not triangle-surface distance',
               'xy_support': xy_support_diagnostic(prediction, ref, cfg['xy_cell_m']),
               'reference_coverage_verified_by_this_function': False}
    arrays = {'prediction_surface_samples': prediction, 'reference_points': ref,
              'prediction_original_indices': original_indices[selection],
              'reference_original_indices': members[selected],
              'prediction_to_reference_distance': p2r, 'reference_to_prediction_point_distance': r2p,
              'reference_to_candidate_distance': r2p}
    return metrics, arrays


def column_diagnostics(points, cell=.5, layer_gap=.5):
    """Potential stacked observations; roofs/walls can also form multiple layers."""
    points = np.asarray(points)
    cells = np.floor(points[:, :2]/cell).astype(np.int64)
    if not len(points):
        return []
    order = np.lexsort((points[:, 2], cells[:, 1], cells[:, 0]))
    starts = np.r_[0, np.flatnonzero(np.any(np.diff(cells[order], axis=0), axis=1))+1]
    ends = np.r_[starts[1:], len(order)]
    rows = []
    for start, end in zip(starts, ends):
        ids = order[start:end]
        z = points[ids, 2]
        rows.append({'cell_x': int(cells[ids[0], 0]), 'cell_y': int(cells[ids[0], 1]),
                     'points': len(ids), 'z_min': float(z.min()), 'z_max': float(z.max()),
                     'separated_height_groups': 1 + int(np.sum(np.diff(z) > layer_gap))})
    return rows


def export_display(path, arrays, color, kind, source_path, mesh=None, evaluation_metadata=None):
    points = arrays['prediction_surface_samples']
    _, picked = voxel_reference(points, .1)
    voxel_selected_count = len(picked)
    if len(picked) > 200000:
        picked = picked[np.linspace(0, len(picked)-1, 200000, dtype=np.int64)]
    selected = points[picked]
    colors = np.tile(np.asarray(color, dtype=np.uint8), (len(selected), 1))
    if mesh is not None and mesh.has_vertex_colors() and len(selected):
        nearest = cKDTree(np.asarray(mesh.vertices)).query(selected, workers=1)[1]
        colors = np.clip(np.asarray(mesh.vertex_colors)[nearest]*255, 0, 255).astype(np.uint8)
    distance = arrays['prediction_to_reference_distance'][picked]
    evaluation_metadata = evaluation_metadata or {}
    color_kind = 'NEAREST_ORIGINAL_MESH_VERTEX_COLOR' if mesh is not None and mesh.has_vertex_colors() else 'FIXED_SOURCE_COLOR'
    metadata = {'xyz': selected.astype(np.float32).reshape(-1).tolist(),
                      'rgb': colors.reshape(-1).tolist(),
                      'distance_m': [float(x) if np.isfinite(x) else None for x in distance],
                      'display_only': True, 'surface_kind': kind, 'source_path': source_path,
                      'sampling': 'Existing evaluated point/surface samples selected per fixed .1m voxel then deterministic ordered cap200000; never used in scoring',
                      'display_sample_count': len(selected),
                      'full_evaluation_sample_count': len(points),
                      'original_points_in_roi': evaluation_metadata.get('prediction_original_points',evaluation_metadata.get('original_points_in_roi')),
                      'sampling_metadata': dict(evaluation_kind='AREA_UNIFORM_TRIANGLE_SURFACE_SAMPLES' if mesh is not None else 'FIXED_VOXEL_SELECTED_ORIGINAL_SOURCE_POINTS',
                          evaluation_surface_sample_spacing_m=evaluation_metadata.get('surface_sample_spacing_m'),
                          evaluation_point_voxel_m=None if mesh is not None else evaluation_metadata.get('point_voxel_m',evaluation_metadata.get('reference_voxel_size_m')),
                          reference_voxel_m=evaluation_metadata.get('reference_voxel_size_m',evaluation_metadata.get('point_voxel_m')),
                          evaluation_bvh_coordinate_dtype=evaluation_metadata.get('bvh_coordinate_dtype'),
                          display_voxel_m=.1,display_voxel_selected_count=voxel_selected_count,
                          display_cap=200000,display_cap_applied=voxel_selected_count>200000,
                          never_used_in_scoring=True),
                      'color_provenance': dict(kind=color_kind,description='Nearest original mesh vertex RGB transferred to surface samples for display; not interpolated texture or saved official RGB render.'
                          if color_kind=='NEAREST_ORIGINAL_MESH_VERTEX_COLOR' else 'Fixed source display color; no measured point RGB supplied.'),
                      'color': 'nearest original mesh vertex color for display only' if color_kind=='NEAREST_ORIGINAL_MESH_VERTEX_COLOR' else 'fixed source color'}
    write_json(path,metadata)
    return {key:value for key,value in metadata.items() if key not in ('xyz','rgb','distance_m')}


def section_figure(path, arrays, reference, bounds, region, label):
    figure, axes = plt.subplots(1, 2, figsize=(13, 4.5), constrained_layout=True)
    pred = arrays['prediction_surface_samples']
    distances = arrays['prediction_to_reference_distance']
    for axis, constant in enumerate(SECTIONS[region]):
        across = 1-axis
        selected = np.abs(pred[:, axis]-constant) < .25
        ref_selected = np.abs(reference[:, axis]-constant) < .25
        axes[axis].scatter(reference[ref_selected, across], reference[ref_selected, 2], s=1, c='#282828', label='Observed UAS')
        dots = axes[axis].scatter(pred[selected, across], pred[selected, 2], s=2, c=distances[selected],
                                  cmap='turbo', vmin=0, vmax=2, label='Prediction surface/source samples')
        axes[axis].set(xlim=bounds['xy'[across]], ylim=bounds['z'], xlabel='XY'[across]+' (m)', ylabel='Z (m)',
                       title=f'{region} {"XY"[axis]}={constant:g}m; width0.5m')
        axes[axis].set_aspect('equal', adjustable='box')
        axes[axis].grid(alpha=.2)
    axes[0].legend(markerscale=3, fontsize=7)
    figure.colorbar(dots, ax=axes, label='Distance to observed UAS points (m), clipped at2m', shrink=.8)
    figure.suptitle(label+' — fixed frame; reference gaps are not error truth', fontsize=10)
    figure.savefig(path, dpi=160)
    plt.close(figure)


def distance_figure(path, arrays, bounds, label):
    figure, axes = plt.subplots(1, 2, figsize=(11, 5), constrained_layout=True)
    reverse = arrays['reference_to_candidate_distance'] if 'reference_to_candidate_distance' in arrays else arrays['reference_to_triangle_distance']
    pairs = [(arrays['prediction_surface_samples'], arrays['prediction_to_reference_distance'], 'Prediction to observed UAS'),
             (arrays['reference_points'], reverse, 'UAS to candidate geometry')]
    for axis, (points, distance, title) in zip(axes, pairs):
        picked = np.arange(len(points))
        if len(picked) > 250000:
            picked = picked[np.linspace(0, len(picked)-1, 250000, dtype=np.int64)]
        dots = axis.scatter(points[picked, 0], points[picked, 1], c=distance[picked], s=.4, vmin=0, vmax=2, cmap='turbo')
        axis.set(xlim=bounds['x'], ylim=bounds['y'], xlabel='X (m)', ylabel='Y (m)', title=title)
        axis.set_aspect('equal')
    figure.colorbar(dots, ax=axes, label='Unsigned distance (m), clipped at2m', shrink=.8)
    figure.suptitle(label, fontsize=10)
    figure.savefig(path, dpi=160)
    plt.close(figure)


def geometry_stage(args, cfg, seal, seal_sha):
    region = args.region
    output = args.task / 'evaluation/geometry' / region
    output.mkdir(parents=True, exist_ok=False)
    reference_path = Path('/reference') / region / 'reference.npz'
    if sha(reference_path) != REFERENCE_SHAS[region]:
        raise ValueError('Frozen UAS reference identity differs')
    reference = np.load(reference_path, allow_pickle=False)['uas_xyz']
    spec, ev = cfg['regions'][region], cfg['evaluation']
    bounds = spec['domain']
    sources = json.loads((args.task/'contracts/evaluation_sources_v1.json').read_text())
    baseline_identity = next(row for row in sources['baselines'] if row['region'] == region)
    baseline_path = args.task / baseline_identity['path']
    if sha(baseline_path) != baseline_identity['sha256']:
        raise ValueError('Frozen original ALS/MVS baseline bytes differ')
    baseline = np.load(baseline_path, allow_pickle=False)
    viewer_root = args.task / 'evaluation/viewer' / region
    viewer_root.mkdir(parents=True, exist_ok=False)
    jobs = [{'id': 'als_points', 'points': baseline['als_xyz'], 'role': 'source_prior', 'color': [214, 171, 97]},
            {'id': 'mvs_points', 'points': baseline['mvs_xyz'], 'role': 'mvs', 'color': [75, 181, 212]},
            {'id': 'prior_mesh', 'path': args.task / 'inputs' / region / 'surface/als_surface.ply',
             'role': 'prior', 'color': [214, 171, 97]}]
    for candidate in seal['candidates']:
        if candidate['region'] != region:
            continue
        name = f'{candidate["condition"]}.{candidate["variant"]}.{candidate["mesh_kind"]}'
        role = 'anchor' if candidate['iteration'] == 8000 else ('native_repetition' if candidate.get('supplemental_only') else ('vanilla' if candidate['condition'] == 'D005_Pnative' else 'changed'))
        jobs.append({'id': name, 'path': args.task / candidate['surface']['path'], 'candidate': candidate,
                     'role': role, 'color': [167, 130, 236]})
    tables, viewer = [], []
    for job in jobs:
        start = time.time()
        directory = output / job['id']
        directory.mkdir()
        source_sha256 = sha(job['path']) if 'path' in job else sha(baseline_path)
        mesh = o3d.io.read_triangle_mesh(str(job['path'])) if 'path' in job else None
        primary = True
        if 'candidate' in job:
            row = job['candidate']
            primary = row['mesh_res'] in (512, 1024) if getattr(args, 'resource', None) else row['mesh_res'] == cfg['extraction']['mesh_res']
        settings = [(ev['surface_sample_spacing_m'], ev['reference_voxel_m'])]
        if mesh is not None:
            settings += [(spacing, ev['reference_voxel_m']) for spacing in ev['sample_sensitivity_m']]
            settings += [(ev['surface_sample_spacing_m'], voxel) for voxel in ev['reference_voxel_sensitivity_m']]
        for index, (spacing, voxel) in enumerate(settings):
            variant = f'sample{spacing:g}_reference{voxel:g}'
            if mesh is None:
                metrics, arrays = point_metrics(job['points'], reference, bounds, ev)
            else:
                metrics, arrays = evaluate_geometry(np.asarray(mesh.vertices), np.asarray(mesh.triangles), reference,
                    bounds, spacing, voxel, cfg['seed'], ev['thresholds_m'], xy_cell_size=ev['xy_cell_m'])
                metrics['surface_kind'] = 'triangle_surface'
            metrics.update(region=region, candidate=job['id'], candidate_seal_sha256=seal_sha,
                           **args.layout.binding(),
                           **args.repeat.binding(), supplemental_only=job.get('candidate', {}).get('supplemental_only', False),
                           **resources.binding(getattr(args, 'resource', None)),
                           mesh_res=job.get('candidate', {}).get('mesh_res'),
                           iteration=job.get('candidate', {}).get('iteration'),
                           comparison_family=resources.comparison_family(job['id']) if getattr(args, 'resource', None) else None,
                           reference_sha256=REFERENCE_SHAS[region], crs=cfg['crs'],
                           source_sha256=source_sha256,
                           source_array_key=None if mesh is not None else ('als_xyz' if job['id']=='als_points' else 'mvs_xyz'))
            for threshold in metrics['thresholds']:
                threshold.update(far_surface_area_fields(metrics, threshold))
            save_distance_arrays(directory / (variant+'.npz'), arrays)
            write_json(directory / (variant+'.json'), metrics)
            for threshold in metrics['thresholds']:
                tables.append(dict(region=region, candidate=job['id'], role=job['role'], surface_kind=metrics['surface_kind'],
                    **args.layout.binding(),
                    **args.repeat.binding(), supplemental_only=metrics['supplemental_only'],
                    **resources.binding(getattr(args, 'resource', None)),
                    mesh_res=metrics['mesh_res'], iteration=metrics['iteration'], comparison_family=metrics['comparison_family'],
                    sensitivity=variant, status=metrics['status'], **threshold,
                    **distance_table_fields(metrics),
                    surface_area_m2=metrics['surface_area_m2']))
            if index == 0:
                write_csv(directory / 'height_columns.csv', column_diagnostics(arrays['prediction_surface_samples']))
                write_json(directory / 'diagnostic_notes.json', {
                    'height_groups': '0.5m XY columns; sorted consecutive z gaps above0.5m; possible multilayer evidence, also roofs/walls/holes; not automatic double-surface truth',
                    'coverage': metrics['xy_support'], 'scientific_verdict': None})
                if primary:
                    display = viewer_root / (job['id']+'.json')
                    display_metadata = export_display(display, arrays, job['color'], metrics['surface_kind'],
                                   str(job.get('path', baseline_path)), mesh,metrics)
                    mesh_data, original_mesh = None,None
                    if mesh is not None:
                        original_mesh = original_mesh_provenance(args.task,job['path'],seal['files'],job['role'])
                        mesh_data = export_clipped_mesh(viewer_root/(job['id']+'.mesh.json'),arrays,
                            metrics['bounds_half_open'],original_mesh,job['color'],args.task/'evaluation/viewer',metrics)
                    sections = viewer_root / (job['id']+'.sections.png')
                    section_figure(sections, arrays, arrays['reference_points'], bounds, region, job['id'])
                    distances = viewer_root / (job['id']+'.distance.png')
                    distance_figure(distances, arrays, bounds, job['id'])
                    viewer.append({'id': job['id'], 'role': job['role'], 'data_url': display.name,
                                   'section_url': sections.name, 'distance_url': distances.name,
                                   'metrics_relative': str((directory/(variant+'.json')).relative_to(args.task)),
                                   'source_path': str(job.get('path', baseline_path)), 'surface_kind': metrics['surface_kind'],
                                   'display_metadata':display_metadata,'mesh_data':mesh_data,'original_mesh':original_mesh})
        write_json(directory / 'run_receipt.json', {'wall_seconds': time.time()-start, 'scientific_verdict': None,
                                                   'candidate': job['id'], 'status': 'EVALUATED'})
        print(json.dumps({'region': region, 'candidate': job['id'], 'wall_seconds': time.time()-start}), flush=True)
    ref, _ = voxel_reference(reference[inside_half_open(reference, bounds)], ev['reference_voxel_m'])
    reference_display_metadata = export_display(viewer_root/'reference.json', {'prediction_surface_samples': ref,
                    'prediction_to_reference_distance': np.full(len(ref), np.nan)}, [232, 235, 239],
                   'observed_UAS_reference_points', str(reference_path),evaluation_metadata=dict(
                       original_points_in_roi=int(inside_half_open(reference,bounds).sum()),reference_voxel_size_m=ev['reference_voxel_m']))
    write_csv(output/'geometry_metrics.csv', tables)
    if getattr(args, 'resource', None):
        write_csv(output/'extraction_availability.csv', [row for row in resources.inventory_availability(seal) if row['region'] == region])
    write_json(output/'viewer_index.json', {'region': region, 'candidates': viewer, 'reference_url': 'reference.json',
               'scientific_verdict': None, 'reference_points': len(ref), 'reference_display_metadata':reference_display_metadata,
               'candidate_seal_sha256': seal_sha,
               **args.layout.binding(), **args.repeat.binding(), **resources.binding(getattr(args, 'resource', None))})
    write_json(output/'receipt.json', {'status': 'PASS_GEOMETRY_EVALUATION', 'scientific_verdict': None,
               'region': region, 'rows': len(tables), 'candidate_seal_sha256': seal_sha,
               **args.layout.binding(),
               **args.repeat.binding(),
               **resources.binding(getattr(args, 'resource', None)),
               **({'input_verification': args.input_verification} if getattr(args, 'input_verification', None) else {}),
               'reference_sha256': REFERENCE_SHAS[region], 'baseline_sha256': sha(baseline_path),
               'limitations': ['fixed existing frame; absolute datum not recalibrated',
                   'mesh-to-reference uses observed point proximity; sparse/missing UAS support can cause large distances',
                   'pointset NN baselines and triangle distances are distinct estimands',
                   'all-view historical MVS and cameras; not independent acquisition testing'],
               'script_sha256': sha(__file__)})


def renders_stage(args, cfg, seal, seal_sha):
    region = args.region
    split = json.loads((args.task/'inputs'/region/'scene/split_manifest_da3_v2.json').read_text())
    scorer = NativeMetrics('/source', '/weights', device='cuda', signed_lpips=True)
    for candidate in seal['candidates']:
        if candidate['region'] != region or not candidate['render_records']:
            continue
        records = [dict(row, render_path=str(args.task/row['render_path'])) for row in candidate['render_records']]
        output = args.task/'evaluation/renders'/region/candidate['condition']/candidate['variant']
        result = evaluate_render_set(split, records, cfg['regions'][region]['domain'],
            args.task/'inputs'/region/'scene/images', scorer, output, region, candidate['condition'],
            candidate['variant'], cfg['seed'], seal_sha, runtime_metadata=dict(args.layout.binding(), **args.repeat.binding(),
                **resources.binding(getattr(args, 'resource', None)),
                **({'input_verification': args.input_verification} if getattr(args, 'input_verification', None) else {}),
                supplemental_only=candidate.get('supplemental_only', False)))
        print(json.dumps({'region': region, 'condition': candidate['condition'], 'stage': candidate['variant'],
                          'status': result['status']}), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--task', type=Path, required=True)
    parser.add_argument('--region', choices=('P1', 'P2', 'P3'), required=True)
    parser.add_argument('--stage', choices=('geometry', 'renders'), required=True)
    parser.add_argument('--runtime-layout', type=Path)
    parser.add_argument('--repeat-contract', type=Path)
    parser.add_argument('--resource-contract', type=Path)
    parser.add_argument('--verify-stage-inputs', action='store_true',
                        help='Exact completion amendment only: verify all consumed regional inputs; retain the full original candidate seal')
    args = parser.parse_args()
    if not Path('/.dockerenv').exists():
        raise RuntimeError('Project evaluation must run in Docker')
    args.layout = RuntimeLayout(args.task, args.runtime_layout,
                               json.loads((args.task/'contracts/execution_v1.json').read_text())['regions'])
    args.repeat = SupplementalRepeat(args.task, args.repeat_contract, args.layout)
    args.resource = resources.make_resource(args.task, args.resource_contract, args.layout, args.repeat)
    loaded = load_seal(args.task, args.layout, args.repeat, args.resource,
                       stage_inputs=(args.region, args.stage) if args.verify_stage_inputs else None)
    cfg, seal, seal_sha = loaded[:3]
    args.input_verification = loaded[3] if args.verify_stage_inputs else None
    if args.layout.path and args.stage == 'renders':
        # NativeMetrics constructs its first torch CUDA objects only afterwards.
        allocator = args.layout.data['allocator']
        if os.environ.get('PYTORCH_CUDA_ALLOC_CONF') not in (None, allocator):
            raise ValueError('Evaluation allocator differs from the explicit runtime layout')
        os.environ['PYTORCH_CUDA_ALLOC_CONF'] = allocator
    if args.stage == 'geometry':
        geometry_stage(args, cfg, seal, seal_sha)
    else:
        renders_stage(args, cfg, seal, seal_sha)


if __name__ == '__main__':
    main()
