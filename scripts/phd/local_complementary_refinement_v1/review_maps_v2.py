"""Independently verify every displayed cell against immutable raw distances.

This QA uses original Anchor/G/LC point distances, not the producer's transition
aggregation helpers. It never fits parameters or modifies evaluation artifacts.
"""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import resource
import sys
import time

import numpy as np


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            h.update(block)
    return h.hexdigest()


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def read(path):
    return json.loads(path.read_text())


def arrays(path, keys):
    with np.load(path, allow_pickle=False) as source:
        return {key: source[key] for key in keys}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('evaluation', 'maps', 'parent', 'config', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--allow-partial', action='store_true')
    args = parser.parse_args()
    require(Path('/.dockerenv').exists(), 'Docker required')
    out = args.output / ('attempt_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ'))
    out.mkdir(parents=True, exist_ok=False)
    started = time.time()
    bound, checks = {}, []
    code_sha = sha(Path(__file__))

    def bind(path, expected=None):
        actual = sha(path)
        require(expected is None or actual == expected, 'Input digest differs: '+str(path))
        bound[str(path)] = dict(path=str(path), bytes=path.stat().st_size, sha256=actual)
        return path

    try:
        cfg = read(bind(args.config))
        er = read(bind(args.evaluation/'receipt.json'))
        mr = read(bind(args.maps/'receipt.json'))
        full = er['status'] == 'COMPLETE_DEVELOPMENT_EVALUATION'
        require(full or (args.allow_partial and er['status'] == 'PARTIAL_DEVELOPMENT_EVALUATION'),
                'Full evaluation required unless explicit --allow-partial')
        require(mr['status'] == 'PASS_STATIC_MAPS', 'Finalized successful maps required')
        require(cfg['scientific_verdict'] is er['scientific_verdict'] is mr['scientific_verdict'] is None,
                'Scientific verdict forbidden')
        require(er['reference_used_for_training_or_parameter_selection'] is False and
                mr['reference_for_training_or_parameter_selection'] is False, 'Reference use boundary differs')
        require(cfg['runtime']['image_id'] == os.environ['JBGS_RUNTIME_IMAGE_ID'], 'Pinned image differs')
        eo = {r['path']: r['sha256'] for r in er['outputs']}
        ei = {r['path']: r['sha256'] for r in er['inputs']}
        mi = {r['path']: r['sha256'] for r in mr['inputs']}
        require(mi.get(str(args.evaluation/'receipt.json')) == sha(args.evaluation/'receipt.json'), 'Map evaluation binding differs')
        require({r['sha256'] for r in er['inputs'] if r['path'].endswith('/experiment_v2.json')} == {sha(args.config)}, 'Config binding differs')
        require(read(bind(args.evaluation/'config_snapshot.json', eo['config_snapshot.json'])) == cfg, 'Config snapshot differs')
        expected = {(Path(k).parts[0], Path(k).parts[1]) for k in eo
                    if len(Path(k).parts) == 3 and k.endswith('/raw_metrics.json')}
        observed = {(r['region'], r['condition']) for r in mr['cases']}
        require(expected == observed and len(mr['cases']) == len(expected) == er['run_count'] == mr['case_count'], 'Map membership differs')
        configured = {(r, c['id']) for r in cfg['regions'] for c in cfg['conditions']}
        require(expected <= configured, 'Unexpected map condition')
        if full:
            require(expected == configured and len(expected) == 18, 'Full18 membership differs')
        threshold = cfg['evaluation']['paired_primary_threshold_m']
        size = cfg['evaluation']['xy_cell_m']
        require(threshold == mr['threshold_m'] == .5 and size == mr['xy_cell_m'] == .5, 'Frozen threshold/cell differs')
        for item in mr['outputs']:
            p = Path(item['path'])
            require(not p.is_absolute() and len(p.parts) == 1, 'Unsafe map output path')
            require(bind(args.maps/p, item['sha256']).stat().st_size == item['bytes'], 'Map output byte count differs')
        keys = ['reference_original_indices', 'reference_points', 'reference_to_triangle_distance']
        memberships = {}
        for case in mr['cases']:
            region, local = case['region'], case['condition']
            global_name = next(c['parent_condition'] for c in cfg['conditions'] if c['id'] == local)
            require(case['parent_condition'] == global_name, 'Matched G differs')
            prefix = region+'/'+local
            metric = read(bind(args.evaluation/prefix/'raw_metrics.json', eo[prefix+'/raw_metrics.json']))
            require(metric['region'] == region and metric['candidate'] == local and metric['mesh_kind'] == 'raw'
                    and metric['mesh_res'] == 512, 'Raw metric identity differs')
            data = {local: arrays(bind(args.evaluation/prefix/'raw_distances.npz', eo[prefix+'/raw_distances.npz']), keys)}
            for label, suffix in [('ANCHOR', 'D005_Pnative.anchor_512.raw'), (global_name, global_name+'.mesh_512.raw')]:
                path = args.parent/'evaluation/geometry'/region/suffix/'sample0.1_reference0.1.npz'
                data[label] = arrays(bind(path, ei[str(path)]), keys)
            path = args.parent/'evaluation/da3_refinement_spatial_v1'/(region+'.paired.npz')
            paired = arrays(bind(path, ei[str(path)]), ['reference_original_indices', 'reference_points',
                'xy_cell_index', 'xy_cell_centres', 'strict_target_world_z_error_median'])
            ids, points = data[local]['reference_original_indices'], data[local]['reference_points']
            require(ids.ndim == 1 and ids.dtype.kind in 'iu' and len(np.unique(ids)) == len(ids)
                    and np.all(ids >= 0), 'Original reference IDs invalid')
            require(points.shape == (len(ids),3) and np.isfinite(points).all(), 'Original reference XYZ invalid')
            for d in [data['ANCHOR'], data[global_name], paired]:
                for key in ('reference_original_indices', 'reference_points'):
                    require(d[key].dtype == data[local][key].dtype and np.array_equal(d[key], data[local][key]), 'Original ID/XYZ order or dtype differs')
            bounds = np.asarray(metric['bounds_half_open'])
            require(bounds.shape == (3,2) and np.isfinite(bounds).all() and np.all(bounds[:,1] > bounds[:,0]), 'ROI bounds invalid')
            require(np.all(points >= bounds[:,0]) and np.all(points < bounds[:,1]), 'Reference escaped half-open ROI')
            require(case['bounds_half_open'] == bounds.tolist() and case['crs'] == metric['crs'], 'Map ROI/CRS differs')
            identity = (hashlib.sha256(ids.tobytes()).hexdigest(), hashlib.sha256(points.tobytes()).hexdigest(), bounds.tolist())
            require(case['original_ids_sha256'] == identity[0] and case['reference_points_sha256'] == identity[1], 'Map reference digest differs')
            require(region not in memberships or memberships[region] == identity, 'Reference membership changed across conditions')
            memberships[region] = identity
            dims = np.ceil((bounds[:2,1]-bounds[:2,0])/size).astype(int)
            xy = np.floor((points[:,:2]-bounds[:2,0])/size).astype(int)
            cell = xy[:,1]*dims[0]+xy[:,0]
            nc = int(np.prod(dims))
            centers = np.c_[bounds[0,0]+(np.arange(nc)%dims[0]+.5)*size,
                            bounds[1,0]+(np.arange(nc)//dims[0]+.5)*size]
            require(np.array_equal(cell, paired['xy_cell_index']), 'Inherited cell membership differs')
            require(np.allclose(centers, paired['xy_cell_centres'], atol=1e-8, rtol=0), 'Inherited cell centers differ')
            count = np.bincount(cell, minlength=nc)
            strict = np.bincount(cell[np.isfinite(paired['strict_target_world_z_error_median'])], minlength=nc)
            require(case['grid_dims_xy'] == dims.tolist() and case['reference_count'] == len(ids)
                    and metric['reference_points_after_voxel'] == len(ids), 'Map/metric dimensions differ')
            require(case['reference_supported_cells'] == np.count_nonzero(count) and
                    case['cells_without_observed_reference'] == np.count_nonzero(count == 0), 'Map support differs')
            with (args.maps/(region+'_'+local+'_raw512.csv')).open(newline='') as stream:
                rows = list(csv.DictReader(stream))
            require(len(rows) == nc and {int(r['cell_id']) for r in rows} == set(range(nc)), 'Full-grid map membership differs')
            rows.sort(key=lambda r: int(r['cell_id']))
            for i,r in enumerate(rows):
                require((r['region'],r['condition'],r['parent_condition'],r['mesh_kind']) ==
                        (region,local,global_name,'raw'), 'Map row identity differs')
                require(float(r['threshold_m']) == threshold and float(r['xy_cell_m']) == size, 'Map row threshold differs')
                require(int(r['reference_count']) == count[i] and int(r['strict_reference_count']) == strict[i], 'Map row support differs')
                require(np.allclose([float(r['x_m']),float(r['y_m'])], centers[i], atol=1e-8, rtol=0), 'Map row center differs')
            panels = []
            for key,before,after in [('anchor_to_global','ANCHOR',global_name),
                                     ('anchor_to_local','ANCHOR',local), ('global_to_local',global_name,local)]:
                a,b = data[before]['reference_to_triangle_distance'], data[after]['reference_to_triangle_distance']
                require(a.shape == b.shape == ids.shape and not np.isnan(a).any() and not np.isnan(b).any()
                        and np.all(a >= 0) and np.all(b >= 0), 'Raw reference distances invalid')
                corr = np.bincount(cell[(a >= threshold)&(b < threshold)], minlength=nc)
                damage = np.bincount(cell[(a < threshold)&(b >= threshold)], minlength=nc)
                finite = np.bincount(cell[np.isfinite(a)&np.isfinite(b)], minlength=nc)
                states = np.where(count == 0, 'NO_REFERENCE', 'NO_THRESHOLD_CROSSING').astype(object)
                states[(corr > 0)&(damage == 0)] = 'CORRECTION_ONLY'
                states[(corr == 0)&(damage > 0)] = 'DAMAGE_ONLY'
                states[(corr > 0)&(damage > 0)] = 'BOTH_CORRECTION_AND_DAMAGE'
                for suffix, values in [('corrected_count',corr), ('damaged_count',damage), ('finite_pair_count',finite)]:
                    require(np.array_equal([int(r[key+'_'+suffix]) for r in rows], values), 'Map point-to-cell count differs: '+key+' '+suffix)
                require([r[key+'_state'] for r in rows] == states.tolist(), 'Map categorical state differs')
                counts = {label:int(np.count_nonzero(states == label)) for label in
                          ['NO_REFERENCE','NO_THRESHOLD_CROSSING','CORRECTION_ONLY','DAMAGE_ONLY','BOTH_CORRECTION_AND_DAMAGE']}
                declared = [p for p in case['panels'] if p['key'] == key]
                require(len(declared) == 1 and declared[0]['before'] == before and declared[0]['after'] == after, 'Map panel identity differs')
                require(declared[0]['cell_state_counts'] == counts and declared[0]['corrected_point_count'] == corr.sum()
                        and declared[0]['damaged_point_count'] == damage.sum(), 'Map receipt panel totals differ')
                panels.append(dict(panel=key, corrected_points=int(corr.sum()), damaged_points=int(damage.sum()), cell_states=counts))
            checks.append(dict(region=region, condition=local, reference_count=len(ids), full_grid_cells=nc,
                strict_reference_count=int(strict.sum()), original_ids_and_xyz_exact=True, all_displayed_cells_exact=True, panels=panels))
        require(sha(Path(__file__)) == code_sha, 'QA source changed during execution')
        (out/'review_maps_v2.py').write_bytes(Path(__file__).read_bytes())
        (out/'config_snapshot.json').write_bytes(args.config.read_bytes())
        result = dict(schema='jbgs.actual_map_distance_review.v2', status='PASS_EXACT_ORIGINAL_DISTANCES_AND_ALL_CELLS',
            matrix_status='FULL18' if full else 'PARTIAL', scientific_verdict=None, run_count=len(checks),
            checks=checks, inputs=list(bound.values()), source_sha256=code_sha, command=sys.argv,
            wall_seconds=time.time()-started, peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
            runtime=dict(image_id=os.environ['JBGS_RUNTIME_IMAGE_ID'], python=sys.version, numpy=np.__version__,
                cpu_max=Path('/sys/fs/cgroup/cpu.max').read_text().strip(), memory_max=Path('/sys/fs/cgroup/memory.max').read_text().strip()),
            independent_training_repeats=False, manual_visual_review='SEPARATE_REQUIRED',
            interpretation='Original reference proximity counts, not surface area, semantic truth, temporal correctness or independent trials')
        with (out/'receipt.json').open('x') as stream:
            json.dump(result, stream, indent=2, allow_nan=False); stream.write('\n')
        print(json.dumps(dict(status=result['status'], output=str(out), run_count=len(checks), scientific_verdict=None)), flush=True)
    except Exception as error:
        with (out/'failure.json').open('x') as stream:
            json.dump(dict(status='FAIL_MAP_DISTANCE_QA', scientific_verdict=None, error=str(error),
                exception_type=type(error).__name__, inputs=list(bound.values()), completed_checks=checks,
                source_sha256=code_sha), stream, indent=2, allow_nan=False)
        raise


if __name__ == '__main__':
    main()
