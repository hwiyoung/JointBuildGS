"""Static maps of fixed-reference proximity changes in shared 0.5m XY cells.

Chart contract: three categorical matrix panels, Anchor->G, Anchor->LC, G->LC;
the same original reference IDs, ROI, axes and cells are used in every panel.
Correction and damage coexistence is a separate category, never netted away.
Blue plus / orange cross / gold diamond / neutral fills provide explicit color
and shape encoding. Outputs are standalone PNG/CSV with immutable provenance.
"""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import time

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, BoundaryNorm
from matplotlib.lines import Line2D
import numpy as np

STATES = ('NO_REFERENCE', 'NO_THRESHOLD_CROSSING', 'CORRECTION_ONLY', 'DAMAGE_ONLY', 'BOTH_CORRECTION_AND_DAMAGE')
COLORS = ('#F5F4F0', '#C9CDD2', '#2E6FBB', '#DF8F35', '#E5BD44')
LABELS = ('No observed reference', 'No threshold crossing', 'Correction only (+)', 'Damage only (x)', 'Correction AND damage (diamond)')
MARKERS = {2: '+', 3: 'x', 4: 'D'}


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            h.update(block)
    return h.hexdigest()


def record(path):
    path = Path(path)
    return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': sha(path)}


def read(path):
    return json.loads(Path(path).read_text())


def write_new(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def safe_child(root, relative):
    root, relative = Path(root), Path(relative)
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('Expected a safe relative producer output')
    result = root/relative
    if not result.resolve().is_relative_to(root.resolve()):
        raise ValueError('Producer output escaped evaluation attempt')
    return result


def verify_output(evaluation, receipt, relative):
    matches = [r for r in receipt['outputs'] if r['path'] == relative]
    if len(matches) != 1:
        raise ValueError('Expected one producer digest for '+relative)
    path = safe_child(evaluation, relative)
    if path.stat().st_size != matches[0]['bytes'] or sha(path) != matches[0]['sha256']:
        raise ValueError('Finalized evaluation output changed: '+relative)
    return path


def grid_membership(points, bounds, cell_size):
    points, bounds = np.asarray(points), np.asarray(bounds, dtype=float)
    if points.ndim != 2 or points.shape[1] != 3 or not np.isfinite(points).all():
        raise ValueError('Finite original reference XYZ required')
    if bounds.shape != (3, 2) or not np.isfinite(bounds).all() or not np.all(bounds[:, 1] > bounds[:, 0]):
        raise ValueError('Finite increasing fixed XYZ bounds required')
    if not np.isfinite(cell_size) or cell_size <= 0:
        raise ValueError('Positive cell size required')
    if np.any(points < bounds[:, 0]) or np.any(points >= bounds[:, 1]):
        raise ValueError('Original reference points escape half-open fixed ROI')
    dims = np.ceil((bounds[:2, 1]-bounds[:2, 0])/cell_size).astype(np.int64)
    if int(np.prod(dims)) > 10_000_000:
        raise ValueError('Unexpected map grid exceeds bounded 10 million cells')
    xy = np.floor((points[:, :2]-bounds[:2, 0])/cell_size).astype(np.int64)
    ids = xy[:, 1]*dims[0]+xy[:, 0]
    n = int(np.prod(dims))
    centers = np.column_stack([bounds[0, 0]+(np.arange(n) % dims[0]+.5)*cell_size,
                               bounds[1, 0]+(np.arange(n) // dims[0]+.5)*cell_size])
    return ids, centers, (int(dims[0]), int(dims[1]))


def category(reference_count, corrected, damaged):
    n, c, d = map(np.asarray, (reference_count, corrected, damaged))
    if not (n.shape == c.shape == d.shape) or np.any(n < 0) or np.any(c < 0) or np.any(d < 0) or np.any(c+d > n):
        raise ValueError('Correction and damage must be disjoint subsets of fixed reference points')
    result = np.where(n > 0, 1, 0).astype(np.uint8)
    result[(c > 0) & (d == 0)] = 2
    result[(d > 0) & (c == 0)] = 3
    result[(c > 0) & (d > 0)] = 4
    return result


def parse_bool(value):
    if value in (True, 'True', 'true', '1', 1): return True
    if value in (False, 'False', 'false', '0', 0): return False
    raise ValueError('Invalid boolean cell flag')


def validate_panel(rows, counts, centers, threshold):
    ncell = len(counts)
    corrected, damaged, strict, finite = [np.zeros(ncell, dtype=np.int64) for _ in range(4)]
    seen = set()
    for row in rows:
        i = int(row['cell_id'])
        if i in seen or not 0 <= i < ncell:
            raise ValueError('Duplicate or out-of-range immutable cell ID')
        seen.add(i)
        if not np.allclose([float(row['x_m']), float(row['y_m'])], centers[i], rtol=0, atol=1e-8):
            raise ValueError('CSV cell center differs from original reference grid')
        if int(row['reference_count']) != counts[i] or float(row['threshold_m']) != threshold:
            raise ValueError('CSV reference membership or threshold differs')
        corrected[i], damaged[i] = int(row['corrected_count']), int(row['damaged_count'])
        strict[i], finite[i] = int(row['strict_reference_count']), int(row['finite_pair_count'])
        if parse_bool(row['both_correction_and_damage']) != (corrected[i] > 0 and damaged[i] > 0):
            raise ValueError('CSV opposing changes must remain explicitly marked')
        if not (0 <= strict[i] <= counts[i] and 0 <= finite[i] <= counts[i]):
            raise ValueError('CSV support count exceeds original reference membership')
    if seen != set(np.flatnonzero(counts)):
        raise ValueError('CSV omits or invents occupied reference cells')
    return {'corrected': corrected, 'damaged': damaged, 'strict': strict, 'finite_pairs': finite,
            'category': category(counts, corrected, damaged)}


def build_case(rows, region, condition, metrics, points, original_ids, distances, cell_size, threshold):
    ids = np.asarray(original_ids)
    if ids.ndim != 1 or ids.dtype.kind not in 'iu' or len(ids) != len(points) or np.any(ids < 0) or len(np.unique(ids)) != len(ids):
        raise ValueError('Unique original reference IDs required without remapping')
    distances = np.asarray(distances)
    if distances.shape != ids.shape or np.any(np.isnan(distances)) or np.any(distances < 0):
        raise ValueError('Finite nonnegative or positive-infinite reference distances required')
    if metrics.get('scientific_verdict') is not None or metrics.get('mesh_kind') != 'raw' or metrics.get('mesh_res') != 512:
        raise ValueError('Expected evaluation-only raw TSDF512 metrics')
    if metrics.get('region') != region or metrics.get('candidate') != condition['id']:
        raise ValueError('Raw evaluation case identity differs')
    if metrics['reference_points_after_voxel'] != len(ids):
        raise ValueError('Raw metric reference count differs from original IDs')
    bounds = np.asarray(metrics['bounds_half_open'], dtype=float)
    cell_ids, centers, dims = grid_membership(points, bounds, cell_size)
    counts = np.bincount(cell_ids, minlength=len(centers)).astype(np.int64)
    pairs = [('anchor_to_global', 'ANCHOR', condition['parent_condition']),
             ('anchor_to_local', 'ANCHOR', condition['id']),
             ('global_to_local', condition['parent_condition'], condition['id'])]
    panels = []
    for key, before, after in pairs:
        selected = [r for r in rows if r['region'] == region and r['mesh_kind'] == 'raw'
                    and r['comparator'] == before and r['candidate'] == after]
        panel = validate_panel(selected, counts, centers, threshold)
        panel.update(key=key, before=before, after=after)
        panels.append(panel)
    if any(not np.array_equal(p['strict'], panels[0]['strict']) for p in panels):
        raise ValueError('Strict reference support changed between mapped comparisons')
    return dict(region=region, condition=condition['id'], parent_condition=condition['parent_condition'],
                panels=panels, counts=counts, centers=centers, dims=dims, bounds=bounds,
                cell_size=cell_size, threshold=threshold, crs=metrics['crs'], reference_count=len(ids),
                original_ids_sha256=hashlib.sha256(ids.tobytes()).hexdigest(),
                original_ids_dtype=str(ids.dtype),
                reference_points_sha256=hashlib.sha256(np.asarray(points).tobytes()).hexdigest())


def draw_map(path, case):
    path = Path(path)
    if path.exists(): raise FileExistsError(path)
    nx, ny = case['dims']; bounds = case['bounds']; size = case['cell_size']
    extent = [bounds[0, 0], bounds[0, 0]+nx*size, bounds[1, 0], bounds[1, 0]+ny*size]
    fig, axes = plt.subplots(1, 3, figsize=(16, 7), sharex=True, sharey=True)
    cmap = ListedColormap(COLORS); norm = BoundaryNorm(np.arange(-.5, 5, 1), cmap.N)
    try:
        for ax, panel, label in zip(axes, case['panels'], ('Anchor8k -> G', 'Anchor8k -> LC', 'G -> LC')):
            ax.imshow(panel['category'].reshape(ny, nx), origin='lower', extent=extent,
                      cmap=cmap, norm=norm, interpolation='nearest', aspect='equal', rasterized=True)
            for state, marker in MARKERS.items():
                subset = case['centers'][panel['category'] == state]
                if len(subset):
                    ax.scatter(subset[:, 0], subset[:, 1], marker=marker,
                               s=max(.7, min(18., 16000/max(nx, ny)**2)),
                               c='#26303A' if state != 4 else 'none',
                               edgecolors='#26303A' if state == 4 else None,
                               linewidths=.35, rasterized=True)
            corrected, damaged = int(panel['corrected'].sum()), int(panel['damaged'].sum())
            both = int(np.count_nonzero(panel['category'] == 4))
            ax.set_title(f'{label}\nCorrected points {corrected:,} | damaged points {damaged:,}\nCells with BOTH {both:,}', fontsize=10, pad=9)
            ax.set_xlim(bounds[0]); ax.set_ylim(bounds[1]); ax.set_xlabel('Scene X (m)', fontsize=10)
            ax.ticklabel_format(style='plain', useOffset=False)
            ax.tick_params(labelsize=8)
            ax.set_facecolor(COLORS[0])
            for spine in ax.spines.values(): spine.set_color('#69737D'); spine.set_linewidth(.6)
        axes[0].set_ylabel('Scene Y (m)', fontsize=10)
        occupied = int(np.count_nonzero(case['counts']))
        fig.suptitle(f"{case['region']} | fixed-cell correction and damage\nG: {case['parent_condition']}    LC: {case['condition']}",
                     fontsize=13, y=.97, color='#1E2933')
        fig.text(.5, .895, f"Raw TSDF512 | distance < {case['threshold']:g} m | cells {size:g} x {size:g} m | "
                 f"original reference points {case['reference_count']:,} | supported cells {occupied:,}/{len(case['counts']):,}",
                 ha='center', fontsize=10, color='#43505C')
        # Filled legend squares retain the categorical fill colors even for
        # unfilled +/x map markers; labels explicitly name those marker shapes.
        handles = [Line2D([], [], marker='D' if i == 4 else 's', linestyle='none', color='#26303A',
                          markerfacecolor=COLORS[i], markeredgewidth=.7, markersize=8, label=LABELS[i])
                   for i in range(5)]
        fig.legend(handles=handles, loc='lower center', bbox_to_anchor=(.5, .073), ncol=3,
                   frameon=False, fontsize=9, columnspacing=1.8)
        fig.text(.5, .03, 'Same axes, ROI and original reference IDs in all panels. Counts are points/cells, not surface area.\n'
                 'No threshold crossing does not mean identical geometry. Reference gaps remain unassessed; opposing changes are never netted.',
                 ha='center', fontsize=9, color='#43505C')
        fig.subplots_adjust(left=.07, right=.985, top=.805, bottom=.22, wspace=.12)
        fig.savefig(path, dpi=170, facecolor='white')
    finally:
        plt.close(fig)


def export_case(output, case):
    stem = case['region']+'_'+case['condition']+'_raw512'
    path = output/(stem+'.csv')
    fields = ['region', 'condition', 'parent_condition', 'mesh_kind', 'threshold_m', 'xy_cell_m',
              'cell_id', 'x_m', 'y_m', 'reference_count', 'strict_reference_count']
    for p in case['panels']:
        fields.extend(p['key']+'_'+suffix for suffix in ('state', 'corrected_count', 'damaged_count', 'finite_pair_count'))
    with path.open('x', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader()
        for i, (x, y) in enumerate(case['centers']):
            row = dict(region=case['region'], condition=case['condition'], parent_condition=case['parent_condition'],
                       mesh_kind='raw', threshold_m=case['threshold'], xy_cell_m=case['cell_size'],
                       cell_id=i, x_m=float(x), y_m=float(y), reference_count=int(case['counts'][i]),
                       strict_reference_count=int(case['panels'][0]['strict'][i]))
            for p in case['panels']:
                row.update({p['key']+'_state': STATES[p['category'][i]],
                            p['key']+'_corrected_count': int(p['corrected'][i]),
                            p['key']+'_damaged_count': int(p['damaged'][i]),
                            p['key']+'_finite_pair_count': int(p['finite_pairs'][i])})
            writer.writerow(row)
    draw_map(output/(stem+'.png'), case)
    return {'region': case['region'], 'condition': case['condition'], 'parent_condition': case['parent_condition'],
            'bounds_half_open': case['bounds'].tolist(), 'crs': case['crs'], 'grid_dims_xy': list(case['dims']),
            'reference_count': case['reference_count'], 'reference_supported_cells': int(np.count_nonzero(case['counts'])),
            'cells_without_observed_reference': int(np.count_nonzero(case['counts'] == 0)),
            'original_ids_sha256': case['original_ids_sha256'], 'original_ids_dtype': case['original_ids_dtype'],
            'reference_points_sha256': case['reference_points_sha256'],
            'panels': [{'key': p['key'], 'before': p['before'], 'after': p['after'],
                        'corrected_point_count': int(p['corrected'].sum()), 'damaged_point_count': int(p['damaged'].sum()),
                        'cell_state_counts': {state: int(np.count_nonzero(p['category'] == i)) for i, state in enumerate(STATES)}}
                       for p in case['panels']]}


def main():
    if not Path('/.dockerenv').is_file(): raise RuntimeError('Project tools require Docker')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evaluation', type=Path, required=True)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); started = time.time()
    evaluation = args.evaluation.resolve(); cfg = read(args.config); receipt = read(evaluation/'receipt.json')
    if (receipt.get('schema') != 'jbgs.local_complementary_evaluation.v2'
        or receipt.get('status') not in ('COMPLETE_DEVELOPMENT_EVALUATION', 'PARTIAL_DEVELOPMENT_EVALUATION')
        or receipt.get('scientific_verdict') is not None
        or receipt.get('reference_used_for_training_or_parameter_selection') is not False
        or (evaluation/'failure.json').exists()):
        raise ValueError('A finalized successful development evaluation is required')
    if cfg.get('schema') != 'jbgs.local_complementary_refinement.v2' or cfg.get('scientific_verdict') is not None or receipt['task_id'] != cfg['task_id']:
        raise ValueError('Frozen technical configuration identity differs')
    config_record = record(args.config)
    if not any(item['sha256'] == config_record['sha256'] and Path(item['path']).name == args.config.name for item in receipt['inputs']):
        raise ValueError('Evaluation was not bound to this exact configuration')
    snapshot = verify_output(evaluation, receipt, 'config_snapshot.json')
    if read(snapshot) != cfg: raise ValueError('Evaluation configuration snapshot differs')
    size, threshold = cfg['evaluation']['xy_cell_m'], cfg['evaluation']['paired_primary_threshold_m']
    if size != .5 or threshold != .5 or cfg['evaluation']['mesh_resolutions'] != [512]:
        raise ValueError('This map contract requires frozen 0.5m cells/threshold and raw512')
    csv_path = verify_output(evaluation, receipt, 'same_cell_changes.csv')
    with csv_path.open(newline='') as stream: rows = list(csv.DictReader(stream))
    sources = [record(evaluation/'receipt.json'), config_record, record(snapshot), record(csv_path), record(__file__)]
    output_root = args.output.resolve()
    if output_root == evaluation or output_root.is_relative_to(evaluation) or evaluation.is_relative_to(output_root):
        raise ValueError('Map output must be separate from immutable evaluation attempt')
    output_root.mkdir(parents=True, exist_ok=True)
    output = output_root/evaluation.name
    output.mkdir(exist_ok=False)
    cases = []; memberships = {}
    try:
        for region in cfg['regions']:
            for condition in cfg['conditions']:
                prefix = region+'/'+condition['id']
                if not any(r['path'] == prefix+'/raw_metrics.json' for r in receipt['outputs']): continue
                metrics_path = verify_output(evaluation, receipt, prefix+'/raw_metrics.json')
                array_path = verify_output(evaluation, receipt, prefix+'/raw_distances.npz')
                sources.extend((record(metrics_path), record(array_path)))
                with np.load(array_path, allow_pickle=False) as arrays:
                    points, ids = arrays['reference_points'], arrays['reference_original_indices']
                    distances = arrays['reference_to_triangle_distance']
                case = build_case(rows, region, condition, read(metrics_path), points, ids, distances, size, threshold)
                membership = (case['original_ids_sha256'], case['reference_points_sha256'], case['bounds'].tolist(), case['crs'])
                if region in memberships and memberships[region] != membership:
                    raise ValueError('Reference IDs/points/ROI/CRS differ across same-region maps')
                memberships[region] = membership
                cases.append(export_case(output, case))
        if len(cases) != receipt['run_count'] or not cases:
            raise ValueError('Map case count differs from completed evaluation run count')
        result = {'schema': 'jbgs.local_complementary_evaluation_maps.v2', 'status': 'PASS_STATIC_MAPS',
                  'task_id': cfg['task_id'], 'scientific_verdict': None, 'render_revision': 'v2.2_header_spacing',
                  'created_utc': datetime.now(timezone.utc).isoformat(),
                  'evaluation_status': receipt['status'], 'case_count': len(cases),
                  'threshold_m': threshold, 'xy_cell_m': size, 'reference_for_training_or_parameter_selection': False,
                  'inputs': sources, 'cases': cases, 'palette': dict(zip(STATES, COLORS)),
                  'classification': 'strict distance<threshold proximity transitions; BOTH retains opposing changes within each fixed cell',
                  'limitations': ['Counts are original reference point/cell counts, not surface area or independent repeats.',
                                  'No threshold crossing does not imply identical geometry.',
                                  'No-reference cells are unassessed; no spatial interpolation or target/parameter fitting.',
                                  'Transitions reuse the finalized evaluator CSV; original IDs/points independently check cell support.'],
                  'versions': {'python': platform.python_version(), 'numpy': np.__version__, 'matplotlib': matplotlib.__version__},
                  'wall_seconds': time.time()-started,
                  'outputs': [dict(record(p), path=p.name) for p in sorted(output.iterdir()) if p.is_file()]}
        write_new(output/'receipt.json', result)
        print(json.dumps({'status': result['status'], 'case_count': len(cases), 'output': str(output), 'scientific_verdict': None}))
    except Exception as error:
        write_new(output/'failure.json', {'status': 'FAIL_STATIC_MAPS', 'scientific_verdict': None,
                                        'exception_type': type(error).__name__, 'exception': str(error), 'inputs': sources})
        raise


if __name__ == '__main__': main()
