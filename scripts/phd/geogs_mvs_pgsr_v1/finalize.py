"""Frozen-output GeoGS MVS/PGSR extraction and reference-only evaluation.

Invoked in separate Docker stages by finalize.sh. A reference-free plan binds
all twelve completed continuations before any reference is mounted. Native GPU
rendering sees only one staged model, its original scene, and frozen source.
CPU scoring reuses the earlier exact surface/photograph evaluation functions.
Nothing writes back into training outputs or historical controls.
"""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import time


REFERENCE_SHAS = {
    'P1': '3d111cf0cd8ab39fccb85ce0075486ec40f4f60584b5c68b2ab122918b321543',
    'P2': '9dc75111e8a5e83808d566c0b6621092423898a1f6badb9438f1a0d75e16e7ba',
    'P3': 'a72041a28c8242d3901f5696d88e607473814299baab43103fda89fc179b1f81'}
CONDITIONS = {.005: 'D005_Pnative', .0005: 'D0005_Pnative'}
IMAGE_ID = 'sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e'


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def csv_write(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    keys = list(dict.fromkeys(key for row in rows for key in row))
    with path.open('x', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def path_below(root, relative):
    path = (Path(root) / relative).resolve(strict=True)
    path.relative_to(Path(root).resolve())
    return path


def identity(path, relative=None):
    path = Path(path)
    return {'path': str(relative if relative is not None else path),
            'bytes': path.stat().st_size, 'sha256': sha(path)}


def verify(root, record):
    path = path_below(root, record['path'])
    if path.stat().st_size != record['bytes'] or sha(path) != record['sha256']:
        raise ValueError('Frozen payload changed: ' + str(path))
    return path


def candidate_id(region, mode, prior):
    return f'{region}.{mode}.{CONDITIONS[float(prior)]}'


def static_preflight(args):
    """Freeze dependencies now, before the overnight training queue is launched."""
    cfg = read('/experiment.json')
    base = Path('/base')
    seal = read(base / 'contracts/candidates_sealed_v1.json')
    selected = [row for row in seal['candidates'] if row['region'] in cfg['regions']
                and row['condition'] in CONDITIONS.values() and row['iteration'] == 30000
                and row['mesh_res'] == 512 and not row.get('supplemental_only')]
    if len(selected) != 12:
        raise ValueError('Exactly twelve historical raw/post surfaces must exist')
    for row in selected:
        verify(base, row['surface'])
    for region, expected in REFERENCE_SHAS.items():
        if sha(Path('/reference') / region / 'reference.npz') != expected:
            raise ValueError('Frozen reference identity mismatch: ' + region)
    self_test(args)
    _, _, rq = load_legacy()
    scorer = rq.NativeMetrics('/source', '/weights', device='cpu')
    del scorer
    write('/frozen/static.json', {'status': 'PASS', 'scientific_verdict': None,
          'config_sha256': sha('/experiment.json'),
          'legacy_seal_sha256': sha(base / 'contracts/candidates_sealed_v1.json'),
          'legacy_config_sha256': sha(base / 'contracts/execution_v1.json'),
          'source_provenance_sha256': sha('/source/mvs_pgsr_source_provenance.json'),
          'reference_sha256': REFERENCE_SHAS,
          'weight_manifest_sha256': sha('/weights/manifest.json'),
          'legacy_code_sha256': {str(p.relative_to('/legacy')): sha(p) for p in sorted(Path('/legacy').rglob('*.py'))},
          'finalizer_sha256': sha(__file__), 'created_unix': time.time(),
          'scope': 'CPU-only dependency and exact input audit; no new training, rendering, source decisions, or scientific scoring'})
    print('PASS static finalization preflight', flush=True)


def plan(args):
    """Bind all finals, all historical controls, and code before UAS access."""
    if Path('/reference').exists():
        raise RuntimeError('The plan stage must not see evaluation references')
    output, base, task = Path('/evaluation'), Path('/base'), Path('/task')
    cfg = read('/experiment.json')
    config_sha = sha('/experiment.json')
    if cfg['scientific_verdict'] is not None or cfg['runtime_image_id'] != IMAGE_ID:
        raise ValueError('Unexpected scientific or runtime contract')
    static = read('/frozen/static.json')
    for key, path in {'config_sha256': '/experiment.json',
                      'legacy_seal_sha256': '/base/contracts/candidates_sealed_v1.json',
                      'legacy_config_sha256': '/base/contracts/execution_v1.json',
                      'source_provenance_sha256': '/source/mvs_pgsr_source_provenance.json',
                      'finalizer_sha256': __file__}.items():
        if sha(path) != static[key]:
            raise ValueError('Overnight frozen finalization dependency changed: ' + key)
    for relative, expected_sha in static['legacy_code_sha256'].items():
        if sha(Path('/legacy') / relative) != expected_sha:
            raise ValueError('Frozen helper changed: ' + relative)
    index = read(args.run_index)
    entries = index['runs'] if isinstance(index, dict) else index
    expected = {(r, m, float(p)) for r in cfg['regions'] for m in cfg['modes'] for p in cfg['prior_weights']}
    keys = [(row['region'], row['mode'], float(row['prior'])) for row in entries]
    if len(keys) != 12 or len(set(keys)) != 12 or set(keys) != expected:
        raise ValueError('Exactly twelve unique authorized final runs are required')
    source_receipt = read('/source/mvs_pgsr_source_provenance.json')
    for relative, expected_sha in source_receipt['prepared_implementation_hashes'].items():
        if sha(Path('/source') / relative) != expected_sha:
            raise ValueError('Prepared source changed: ' + relative)
    source_sha = sha('/source/mvs_pgsr_source_provenance.json')
    old_cfg = read(base / 'contracts/execution_v1.json')
    seal = read(base / 'contracts/candidates_sealed_v1.json')
    if seal['scientific_verdict'] is not None or seal['config_sha256'] != sha(base / 'contracts/execution_v1.json'):
        raise ValueError('Historical seal/config binding mismatch')
    originals = []
    seen_directories = set()
    for row in sorted(entries, key=lambda row: (row['region'], row['mode'], float(row['prior']))):
        host_path = PurePosixPath(os.path.normpath(row['output_directory']))
        relative = str(host_path.relative_to(PurePosixPath(args.host_task)))
        run = path_below(task, relative)
        if run in seen_directories:
            raise ValueError('A training directory cannot stand for multiple conditions')
        seen_directories.add(run)
        receipt = read(run / 'receipt.json')
        if any(receipt.get(key) != value for key, value in {
                'status': 'PASS', 'completed': True, 'phase': 'train', 'final_iteration': 30000,
                'region': row['region'], 'mode': row['mode'], 'prior': float(row['prior']),
                'config_sha256': config_sha, 'source_provenance_sha256': source_sha,
                'runtime_image_id': IMAGE_ID, 'scientific_verdict': None}.items()):
            raise ValueError('Training receipt does not bind a completed declared run: ' + relative)
        complete = run / 'model/jbgs_complete/iteration_30000'
        complete_receipt = read(complete / 'receipt.json')
        if complete_receipt['iteration'] != 30000 or complete_receipt['scientific_verdict'] is not None:
            raise ValueError('Final complete-state receipt mismatch')
        final_ply = run / 'model/point_cloud/iteration_30000/point_cloud.ply'
        ply_record = identity(final_ply, str(final_ply.relative_to(task)))
        if ply_record['sha256'] != complete_receipt['ply_sha256']:
            raise ValueError('Native final PLY differs from complete final-state PLY')
        checkpoint = identity(complete / 'checkpoint.pth', str((complete / 'checkpoint.pth').relative_to(task)))
        if checkpoint['sha256'] != complete_receipt['checkpoint_sha256']:
            raise ValueError('Final checkpoint bytes changed')
        identifier = candidate_id(row['region'], row['mode'], row['prior'])
        destination = output / 'extractions' / identifier
        (destination / 'model/point_cloud/iteration_30000').mkdir(parents=True, exist_ok=False)
        shutil.copyfile(final_ply, destination / 'model/point_cloud/iteration_30000/point_cloud.ply')
        shutil.copyfile(run / 'model/cfg_args', destination / 'model/cfg_args')
        files = [ply_record, checkpoint,
                 identity(run / 'receipt.json', str((run / 'receipt.json').relative_to(task))),
                 identity(run / 'model/cfg_args', str((run / 'model/cfg_args').relative_to(task))),
                 identity(run / 'model/mvs_pgsr_trace.jsonl', str((run / 'model/mvs_pgsr_trace.jsonl').relative_to(task)))]
        trace_snapshot = output / 'training' / identifier
        trace_snapshot.mkdir(parents=True, exist_ok=False)
        for name in ('receipt.json', 'gpu.csv'):
            shutil.copyfile(run / name, trace_snapshot / name)
        shutil.copyfile(run / 'model/mvs_pgsr_trace.jsonl', trace_snapshot / 'trace.jsonl')
        descriptor = {'id': identifier, 'region': row['region'], 'mode': row['mode'],
                      'prior': float(row['prior']), 'training_relative': relative,
                      'host_output_directory': str(host_path), 'files': files,
                      'input_manifest_sha256': sha(base / 'inputs' / row['region'] / 'input_manifest.json'),
                      'source_provenance_sha256': source_sha, 'config_sha256': config_sha,
                      'scientific_verdict': None}
        write(destination / 'job.json', descriptor)
        originals.append(descriptor)
    controls = []
    for region in cfg['regions']:
        for prior in cfg['prior_weights']:
            condition = CONDITIONS[float(prior)]
            rows = [row for row in seal['candidates'] if row['region'] == region
                    and row['condition'] == condition and row['iteration'] == 30000
                    and row['mesh_res'] == 512 and not row.get('supplemental_only')]
            if len(rows) != 2 or {row['mesh_kind'] for row in rows} != {'raw', 'post'}:
                raise ValueError('Missing exact historical final512 raw/post pair')
            for row in rows:
                verify(base, row['surface'])
            rgb = [row for row in seal['candidates'] if row['region'] == region
                   and row['condition'] == condition and row['iteration'] == 30000
                   and row['mesh_kind'] == 'raw' and row.get('render_records')
                   and not row.get('supplemental_only')]
            if len(rgb) != 1:
                raise ValueError('Historical native image render lineage is ambiguous')
            for record in rgb[0]['render_records']:
                path = path_below(base, record['render_path'])
                if sha(path) != record['render_sha256']:
                    raise ValueError('Historical RGB render changed')
            controls.append({'id': candidate_id(region, 'da3', prior), 'region': region,
                             'mode': 'da3', 'prior': float(prior), 'surfaces': rows,
                             'render_records': rgb[0]['render_records'],
                             'scientific_verdict': None})
    document = {'schema': 'JBGS_MVS_PGSR_FINALIZATION_v1', 'task_id': cfg['task_id'],
                'status': 'ALL12_FINALS_BOUND_BEFORE_REFERENCE_ACCESS', 'scientific_verdict': None,
                'config_sha256': config_sha, 'run_index_sha256': sha(args.run_index),
                'source_provenance_sha256': source_sha,
                'legacy_seal_sha256': sha(base / 'contracts/candidates_sealed_v1.json'),
                'legacy_config_sha256': sha(base / 'contracts/execution_v1.json'),
                'reference_sha256': REFERENCE_SHAS, 'crs': old_cfg['crs'],
                'evaluation': old_cfg['evaluation'], 'regions': old_cfg['regions'],
                'runs': originals, 'controls': controls,
                'extraction': {'mesh_res': 512, 'num_cluster': 50, 'raw_primary': True,
                               'post_secondary': True, 'native_renderer_unchanged': True},
                'created_unix': time.time(), 'runtime_image_id': IMAGE_ID,
                'driver_sha256': sha(__file__),
                'legacy_code_sha256': {str(p.relative_to('/legacy')): sha(p) for p in sorted(Path('/legacy').rglob('*.py'))}}
    write(output / 'plan.json', document)
    shutil.copyfile('/frozen/static.json', output / 'static_preflight_snapshot.json')
    shutil.copyfile('/experiment.json', output / 'experiment_snapshot.json')
    shutil.copyfile(args.run_index, output / 'run_index_snapshot.json')
    shutil.copyfile(base / 'contracts/execution_v1.json', output / 'legacy_config_snapshot.json')
    with (output / 'extractions.tsv').open('x') as stream:
        for row in originals:
            stream.write(row['region'] + '\t' + row['id'] + '\n')
    print('All 12 trained finals and 6 historical controls bound; references not mounted.', flush=True)


def extract(args):
    if any(Path(path).exists() for path in ('/reference', '/base', '/task', '/artifacts/JointBuildGS')):
        raise RuntimeError('Extraction container exposes broad or reference-bearing mounts')
    sys.path.insert(0, '/legacy')
    from parse_extraction import parse_extraction_log
    import numpy as np
    import open3d as o3d
    from PIL import Image
    output = Path('/output')
    job = read(output / 'job.json')
    if sha('/source/mvs_pgsr_source_provenance.json') != job['source_provenance_sha256']:
        raise ValueError('Extraction source provenance changed')
    for relative, expected in read('/source/mvs_pgsr_source_provenance.json')['prepared_implementation_hashes'].items():
        if sha(Path('/source') / relative) != expected:
            raise ValueError('Extraction source changed: ' + relative)
    if sha('/input/input_manifest.json') != job['input_manifest_sha256']:
        raise ValueError('Extraction input manifest changed')
    for record in read('/input/input_manifest.json')['files']:
        verify('/input', record)
    model_ply = output / 'model/point_cloud/iteration_30000/point_cloud.ply'
    if sha(model_ply) != job['files'][0]['sha256']:
        raise ValueError('Staged final PLY changed')
    for name in ('train', 'test'):
        if (output / 'model' / name).exists():
            raise FileExistsError('Extraction must use a fresh staged model')
    command = ['python', 'render.py', '-s', '/input/scene', '-m', '/output/model',
               '--iteration', '30000', '--mesh_res', '512', '--num_cluster', '50']
    started = time.time()
    invocation = {'job': job, 'command': command, 'runtime_image_id': IMAGE_ID,
                  'started_unix': started, 'scientific_verdict': None, 'reference_accessed': False}
    write(output / 'invocation.json', invocation)
    with (output / 'render.log').open('x') as log, (output / 'gpu.csv').open('x') as gpu:
        child = subprocess.Popen(command, cwd='/source', stdout=log, stderr=subprocess.STDOUT)
        while child.poll() is None:
            subprocess.run(['nvidia-smi', '--query-gpu=timestamp,uuid,memory.used,utilization.gpu',
                            '--format=csv,noheader,nounits'], stdout=gpu, stderr=subprocess.DEVNULL)
            gpu.flush()
            time.sleep(5)
    receipt = {**invocation, 'exit_code': child.returncode, 'status': 'FAIL',
               'wall_seconds': time.time()-started, 'surfaces': {}, 'renders': []}
    try:
        if child.returncode:
            raise RuntimeError('Native render.py exited with ' + str(child.returncode))
        receipt['realized_extraction'] = parse_extraction_log(output / 'render.log', 512, 50)
        for kind, filename in (('raw', 'fuse.ply'), ('post', 'fuse_post.ply')):
            path = output / 'model/train/ours_30000' / filename
            mesh = o3d.io.read_triangle_mesh(str(path))
            if (not len(mesh.vertices) or not len(mesh.triangles)
                    or not np.isfinite(np.asarray(mesh.vertices)).all() or mesh.get_surface_area() <= 0):
                raise ValueError('Invalid nonempty triangle surface: ' + kind)
            receipt['surfaces'][kind] = identity(path, str(path.relative_to(output)))
        split = read('/input/scene/split_manifest_da3_v2.json')
        views = sorted(split['evaluation'], key=lambda view: view['name'])
        folder = output / 'model/test/ours_30000'
        if len(list((folder / 'renders').glob('*.png'))) != len(views):
            raise ValueError('Native evaluation RGB count differs from frozen split')
        for index, view in enumerate(views):
            render = folder / 'renders' / f'{index:05d}.png'
            actual = folder / 'gt' / f'{index:05d}.png'
            depth = folder / 'vis' / f'depth_{index:05d}.tiff'
            photo = Path('/input/scene/images') / view['name']
            # Verify real saved GT order, not filename enumeration alone.
            with Image.open(actual) as a, Image.open(photo) as b:
                if not np.array_equal(np.asarray(a.convert('RGB')), np.asarray(b.convert('RGB'))):
                    raise ValueError('Native render image/pose ordering differs: ' + view['name'])
            receipt['renders'].append({key: view[key] for key in ('name', 'image_id', 'camera_id')} | {
                'evaluation_index': index, 'render_path': str(render.relative_to(output)),
                'render_sha256': sha(render), 'depth_path': str(depth.relative_to(output)),
                'depth_sha256': sha(depth)})
        receipt['status'] = 'PASS'
    except Exception as exc:
        receipt['error'] = repr(exc)
    receipt['log_sha256'] = sha(output / 'render.log')
    write(output / 'receipt.json', receipt)
    print(job['id'] + ' extraction ' + receipt['status'], flush=True)
    if receipt['status'] != 'PASS':
        raise SystemExit(1)


def load_legacy():
    sys.path.insert(0, '/legacy/evaluation')
    sys.path.insert(1, '/legacy')
    import geometry
    import run_evaluation
    import render_quality
    return geometry, run_evaluation, render_quality


def paired_arrays(old, new, thresholds):
    import numpy as np
    if (not np.array_equal(old['reference_original_indices'], new['reference_original_indices'])
            or not np.array_equal(old['reference_points'], new['reference_points'])):
        raise ValueError('Reference identity mismatch; paired spatial comparison is prohibited')
    a, b = old['reference_to_triangle_distance'], new['reference_to_triangle_distance']
    rows = []
    for threshold in thresholds:
        previous, current = a < threshold, b < threshold
        rows.append({'threshold_m': threshold, 'reference_points': len(a),
                     'recovered': int((~previous & current).sum()),
                     'damaged': int((previous & ~current).sum()),
                     'retained': int((previous & current).sum()),
                     'unresolved': int((~previous & ~current).sum()),
                     'net_recovered_minus_damaged': int(current.sum()-previous.sum())})
    return rows


def matched_figure(path, rows, pair=None):
    """Tile already generated, identically framed legacy diagnostic figures."""
    from PIL import Image, ImageDraw
    images = []
    for label, image_path in rows:
        with Image.open(image_path) as source:
            picture = source.convert('RGB')
            picture.thumbnail((1200, 800))
            canvas = Image.new('RGB', (1200, picture.height+35), 'white')
            canvas.paste(picture, (0, 35))
            ImageDraw.Draw(canvas).text((10, 10), label, fill='black')
            images.append(canvas)
    total = Image.new('RGB', (1200, sum(image.height for image in images)), 'white')
    offset = 0
    for image in images:
        total.paste(image, (0, offset))
        offset += image.height
    total.save(path)


def rgb_depth_figure(output, region, prior, candidates, split, bounds, rq):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    from PIL import Image
    views = sorted(split['evaluation'], key=lambda row: row['name'])
    eligible = []
    for index, view in enumerate(views):
        box = rq.projected_prism_bbox(bounds, view['R'], view['t'], view['K'], view['width'], view['height'])
        if box:
            eligible.append(((box[2]-box[0])*(box[3]-box[1]), -index, index, box))
    if not eligible:
        raise ValueError('No frozen evaluation view sees the fixed regional prism')
    _, _, selected, box = max(eligible)
    x0, y0, x1, y1 = box
    view = views[selected]
    with Image.open(Path('/base/inputs') / region / 'scene/images' / view['name']) as photo:
        rgb = np.asarray(photo.convert('RGB'))[y0:y1, x0:x1]
    figure, axes = plt.subplots(2, 4, figsize=(16, 8), constrained_layout=True)
    axes[0, 0].imshow(rgb)
    axes[0, 0].set_title('Actual RGB; fixed prism bbox')
    axes[1, 0].axis('off')
    depth_images = []
    for column, candidate in enumerate(candidates, 1):
        record = candidate['render_records'][selected]
        with Image.open(record['render_path']) as render:
            axes[0, column].imshow(np.asarray(render.convert('RGB'))[y0:y1, x0:x1])
        depth_path = Path(record.get('depth_path', Path(record['render_path']).parent.parent / 'vis' / f'depth_{selected:05d}.tiff'))
        if depth_path.is_file():
            with Image.open(depth_path) as depth:
                depth_images.append((column, np.asarray(depth, dtype=float)[y0:y1, x0:x1]))
        else:
            axes[1, column].text(.5, .5, 'DEPTH NOT AVAILABLE', ha='center')
        axes[0, column].set_title(candidate['mode'])
    positive = [data[np.isfinite(data) & (data > 0)] for _, data in depth_images]
    positive = [data for data in positive if len(data)]
    low = min(float(data.min()) for data in positive) if positive else 0
    high = max(float(data.max()) for data in positive) if positive else 1
    for column, data in depth_images:
        shown = axes[1, column].imshow(np.ma.masked_where(~np.isfinite(data) | (data <= 0), data),
                                       cmap='viridis', vmin=low, vmax=max(high, low+1e-6))
        axes[1, column].set_title('Camera-Z depth (m), shared display range')
    for axis in axes.flat:
        axis.axis('off')
    if depth_images:
        figure.colorbar(shown, ax=list(axes[1, 1:]), shrink=.5)
    figure.suptitle(f'{region} prior={prior:g}; {view["name"]}; camera selected by largest input-only projected ROI')
    figure.savefig(output, dpi=130)
    plt.close(figure)
    return {'view': view['name'], 'evaluation_index': selected, 'bbox': box,
            'selection': 'largest fixed-prism projected area; input cameras only; ties by earliest frozen view',
            'depth_display_range_m': [low, high], 'depth_images_available': len(depth_images)}


def evaluate(args):
    import numpy as np
    import open3d as o3d
    g, legacy, rq = load_legacy()
    output, base = Path('/evaluation'), Path('/base')
    plan_doc = read(output / 'plan.json')
    for relative, expected in plan_doc['legacy_code_sha256'].items():
        if sha(Path('/legacy') / relative) != expected:
            raise ValueError('Legacy evaluation implementation changed')
    region = args.region
    region_output = output / 'regions' / region
    region_output.mkdir(parents=True, exist_ok=False)
    reference_path = Path('/reference') / region / 'reference.npz'
    if sha(reference_path) != REFERENCE_SHAS[region]:
        raise ValueError('Exact UAS reference changed')
    reference = np.load(reference_path, allow_pickle=False)['uas_xyz']
    ev, bounds = plan_doc['evaluation'], plan_doc['regions'][region]['domain']
    split = read(base / 'inputs' / region / 'scene/split_manifest_da3_v2.json')
    candidates = []
    for control in [row for row in plan_doc['controls'] if row['region'] == region]:
        surfaces = {row['mesh_kind']: verify(base, row['surface']) for row in control['surfaces']}
        records = [dict(row, render_path=str(path_below(base, row['render_path']))) for row in control['render_records']]
        candidates.append({**control, 'surface_paths': surfaces, 'render_records': records})
    # Fail closed unless *all* new extractions are complete before reference scoring.
    for job in plan_doc['runs']:
        extraction = output / 'extractions' / job['id']
        receipt = read(extraction / 'receipt.json')
        if receipt['status'] != 'PASS' or receipt['job'] != job:
            raise ValueError('Incomplete or mismatched new surface extraction')
        if job['region'] != region:
            continue
        surfaces = {kind: verify(extraction, record) for kind, record in receipt['surfaces'].items()}
        control = next(row for row in plan_doc['controls'] if row['region'] == region and row['prior'] == job['prior'])
        expected = control['surfaces'][0]['realized_extraction']
        for key in ('mesh_res', 'num_cluster', 'voxel_size_m', 'sdf_trunc_m', 'depth_trunc_m'):
            if receipt['realized_extraction'][key] != expected[key]:
                raise ValueError('Realized extraction differs from historical matched control: ' + key)
        records = [dict(row, render_path=str(extraction / row['render_path']),
                        depth_path=str(extraction / row['depth_path'])) for row in receipt['renders']]
        candidates.append({**job, 'surface_paths': surfaces, 'render_records': records})
    if len(candidates) != 6:
        raise ValueError('Each region must contain exactly six comparable final states')
    metrics_rows, jobs = [], []
    for candidate in candidates:
        for kind in ('raw', 'post'):
            folder = region_output / 'geometry' / candidate['id'] / kind
            folder.mkdir(parents=True, exist_ok=False)
            source = candidate['surface_paths'][kind]
            mesh = o3d.io.read_triangle_mesh(str(source))
            metrics, arrays = g.evaluate_geometry(np.asarray(mesh.vertices), np.asarray(mesh.triangles),
                reference, bounds, ev['surface_sample_spacing_m'], ev['reference_voxel_m'], 0,
                ev['thresholds_m'], xy_cell_size=ev['xy_cell_m'])
            metrics.update(region=region, candidate=candidate['id'], mode=candidate['mode'],
                           prior=candidate['prior'], mesh_kind=kind, mesh_res=512,
                           source=identity(source), reference_sha256=REFERENCE_SHAS[region],
                           plan_sha256=sha(output / 'plan.json'), crs=plan_doc['crs'], scientific_verdict=None)
            g.save_distance_arrays(folder / 'distances.npz', arrays)
            write(folder / 'metrics.json', metrics)
            legacy.section_figure(folder / 'sections.png', arrays, arrays['reference_points'], bounds, region, candidate['id']+'.'+kind)
            legacy.distance_figure(folder / 'distance.png', arrays, bounds, candidate['id']+'.'+kind)
            for threshold in metrics['thresholds']:
                metrics_rows.append({'region': region, 'candidate': candidate['id'], 'mode': candidate['mode'],
                    'prior': candidate['prior'], 'mesh_kind': kind, 'status': metrics['status'], **threshold,
                    'p2ref_mean_m': metrics['prediction_to_reference_point']['mean'],
                    'p2ref_p95_m': metrics['prediction_to_reference_point']['p95'],
                    'ref2surface_mean_m': metrics['reference_to_prediction_triangle']['mean'],
                    'ref2surface_p95_m': metrics['reference_to_prediction_triangle']['p95'],
                    'surface_area_m2': metrics['surface_area_m2'],
                    'reference_points': metrics['reference_points_after_voxel']})
            jobs.append({'candidate': candidate['id'], 'kind': kind, 'status': metrics['status'],
                         'metrics': str((folder / 'metrics.json').relative_to(output))})
            del mesh, arrays
    csv_write(region_output / 'geometry_metrics.csv', metrics_rows)
    pairs = []
    comparison_dir = region_output / 'comparisons'
    comparison_dir.mkdir()
    for prior in sorted(CONDITIONS):
        ids = {mode: candidate_id(region, mode, prior) for mode in ('da3', 'mvs', 'mvs_pgsr')}
        for previous, current in (('da3', 'mvs'), ('mvs', 'mvs_pgsr'), ('da3', 'mvs_pgsr')):
            for kind in ('raw', 'post'):
                old = np.load(region_output / 'geometry' / ids[previous] / kind / 'distances.npz', allow_pickle=False)
                new = np.load(region_output / 'geometry' / ids[current] / kind / 'distances.npz', allow_pickle=False)
                tag = f'{CONDITIONS[prior]}.{previous}_to_{current}.{kind}'
                pair_rows = paired_arrays(old, new, ev['thresholds_m'])
                for row in pair_rows:
                    pairs.append({'region': region, 'prior': prior, 'previous': previous, 'current': current,
                                  'mesh_kind': kind, **row})
                xyz, original_ids = old['reference_points'], old['reference_original_indices']
                a, b = old['reference_to_triangle_distance'], new['reference_to_triangle_distance']
                with (comparison_dir / (tag+'.points.csv')).open('x', newline='') as stream:
                    writer = csv.writer(stream)
                    writer.writerow(['reference_original_id', 'x', 'y', 'z', 'previous_distance_m', 'current_distance_m', 'reduction_m'])
                    for index, point, before, after in zip(original_ids, xyz, a, b):
                        writer.writerow([int(index), *map(float, point), float(before), float(after), float(before-after)])
                old.close()
                new.close()
        for view in ('sections', 'distance'):
            matched_figure(comparison_dir / f'{CONDITIONS[prior]}.raw.{view}.png',
                [(mode, region_output / 'geometry' / ids[mode] / 'raw' / (view+'.png')) for mode in ids])
        ordered = [next(row for row in candidates if row['mode'] == mode and row['prior'] == prior) for mode in ids]
        visual = rgb_depth_figure(comparison_dir / f'{CONDITIONS[prior]}.rgb_depth.png', region, prior, ordered, split, bounds, rq)
        write(comparison_dir / f'{CONDITIONS[prior]}.rgb_depth.json', visual)
    csv_write(region_output / 'paired_transitions.csv', pairs)
    # Exact prior evaluation functions and offline weights, CPU only. These RGB
    # metrics are development diagnostics because MVS neighbor leakage is unknown.
    scorer = rq.NativeMetrics('/source', '/weights', device='cpu')
    renders = []
    for candidate in candidates:
        records = candidate['render_records']
        render_seal = region_output / 'render_manifests' / (candidate['id']+'.json')
        write(render_seal, {'records': records, 'scientific_verdict': None})
        receipt = rq.evaluate_render_set(split, records, bounds, base / 'inputs' / region / 'scene/images',
            scorer, region_output / 'renders' / candidate['id'], region, candidate['id'], 'final30000', 0, sha(render_seal))
        renders.append({'candidate': candidate['id'], 'status': receipt['status']})
    status = 'PASS' if (all(row['status'] == 'ASSESSED_DEVELOPMENT_ONLY' for row in jobs)
                         and all(row['status'] == 'PASS_RENDER_QUALITY_EVALUATION' for row in renders)) else 'PARTIAL'
    write(region_output / 'receipt.json', {'region': region, 'status': status, 'geometry': jobs,
          'renders': renders, 'plan_sha256': sha(output / 'plan.json'), 'scientific_verdict': None,
          'same_reference_ids_verified': True, 'reference_sha256': REFERENCE_SHAS[region]})
    print(region + ' quantitative and qualitative evaluation ' + status, flush=True)


def report(args):
    root = Path('/evaluation')
    doc = read(root / 'plan.json')
    regions = [read(root / 'regions' / region / 'receipt.json') for region in ('P1', 'P2', 'P3')]
    statuses = [row['status'] for row in regions]
    status = 'PASS' if all(value == 'PASS' for value in statuses) else 'PARTIAL'
    rows, transitions = [], []
    for region in ('P1', 'P2', 'P3'):
        with (root / 'regions' / region / 'geometry_metrics.csv').open() as stream:
            rows.extend(csv.DictReader(stream))
        with (root / 'regions' / region / 'paired_transitions.csv').open() as stream:
            transitions.extend(csv.DictReader(stream))
    csv_write(root / 'geometry_metrics_all.csv', rows)
    csv_write(root / 'paired_transitions_all.csv', transitions)
    def fmt(value):
        return 'NA' if value in (None, '') else f'{float(value):.4f}'
    lines = [f'# GeoGS MVS depth + PGSR 기하 loss 기술 실험: {status}', '',
        'P1/P2/P3 × prior 0.005/0.0005 × MVS/MVS+PGSR의 새 12개 학습 결과와 기존 DA3 6개를 비교했다. '
        '모든 새 조건은 해당 영역의 complete Anchor8k에서 native protection을 유지하고 30,000 step까지 실행했다. '
        '원본 학습 checkpoint와 기존 결과는 보존하고 추출 복사본을 따로 만들었다.', '',
        '**기술 완료 상태와 과학적 판정은 별개다. `scientific_verdict: null`.**', '',
        '원인 검증은 DA3→MVS와 MVS→MVS+PGSR 비교를 구분한다. PGSR 조건은 기존 normal loss를 '
        'single-view normal consistency로 교체하며 multi-view geometry/NCC를 추가한다. '
        'MVS와 prior를 공동 사용한 GS 최적화이며 원본 MVS/prior 좌표 자체를 둘 다 갱신한 실험은 아니다.', '',
        '## 고정 평가와 실제 산출물', '',
        '기존 구현의 raw bounded TSDF512를 주 평가, postprocessed TSDF512를 보조 평가로 유지했다. '
        '표면 면적 샘플 간격 0.1 m, UAS 원점 고정 voxel 0.1 m, 기존 threshold '
        '0.1/0.2/0.25/0.5/1/2 m를 그대로 사용했다. 개선·훼손 전이는 동일 UAS 원본 point ID에서 계산했다. '
        '새 추출의 실제 voxel/sdf/depth truncation을 같은 영역 기존 조건과 정확하게 비교했다.', '',
        '[전체 기하 raw table](geometry_metrics_all.csv) · [전체 회복/훼손 전이](paired_transitions_all.csv) · '
        '[봉인 계획/입력 증거](plan.json)', '',
        '아래는 기존에 고정된 0.5 m threshold의 raw 결과이다. 다른 threshold 및 post 결과는 전체 표에 보존했다.', '',
        '| 영역 | 감독/손실 | prior | 예측→UAS 평균 m | UAS→표면 평균 m | Precision | Recall | F1 |',
        '|---|---|---:|---:|---:|---:|---:|---:|']
    for row in rows:
        if row['mesh_kind'] == 'raw' and float(row['threshold_m']) == .5:
            lines.append('| '+ ' | '.join([row['region'], row['mode'], row['prior'], fmt(row['p2ref_mean_m']),
                fmt(row['ref2surface_mean_m']), fmt(row['precision']), fmt(row['recall']), fmt(row['f1'])])+' |')
    lines += ['', '## 같은 관측점에서의 회복과 훼손', '',
        '거리 threshold 밖→안은 회복, 안→밖은 훼손으로 기록한다. 이는 관측 UAS에 대한 기하 전이이며 '
        '그 자체가 시간적 변화·지붕 의미·자동 LoD2 성공 판정은 아니다.', '',
        '| 영역 | prior | 비교 | threshold m | 회복 | 훼손 | 유지 | 미해결 |',
        '|---|---:|---|---:|---:|---:|---:|---:|']
    for row in transitions:
        if row['mesh_kind'] == 'raw' and float(row['threshold_m']) in (.25, .5):
            lines.append('| '+' | '.join([row['region'], row['prior'], row['previous']+'→'+row['current'],
                row['threshold_m'], row['recovered'], row['damaged'], row['retained'], row['unresolved']])+' |')
    for region in ('P1', 'P2', 'P3'):
        lines += ['', f'## {region} 동일 시점·단면 비교', '']
        for prior in (.005, .0005):
            prefix = f'regions/{region}/comparisons/{CONDITIONS[prior]}'
            lines += [f'prior={prior:g}: [거리 지도]({prefix}.raw.distance.png) · [실제 RGB와 depth]({prefix}.rgb_depth.png)',
                      '', f'![{region} prior {prior:g} 동일 단면]({prefix}.raw.sections.png)', '']
        lines += [f'[기하/전이 raw tables](regions/{region}/geometry_metrics.csv), '
                  f'[동일 UAS ID별 CSV](regions/{region}/comparisons), '
                  f'[전체 고정 평가 영상의 PSNR/SSIM/LPIPS 및 montage](regions/{region}/renders).', '']
    lines += ['## 해결 여부와 남은 한계', '',
        '- P1의 기존 지붕 잔존과 현재 바닥 회복, P2의 큰 지붕 변화와 골, P3의 보존은 위 같은 단면과 '
        '회복/훼손을 함께 검토해야 한다. 평균 수치 하나로 성공 판정을 내리지 않았다.',
        '- UAS 관측이 없는 곳의 예측→관측점 거리는 곧바로 오류가 아니다. 기존 수직 datum 한계와 CRS '
        'provenance를 그대로 유지했으며 새 정합·reference 기반 보정은 수행하지 않았다.',
        '- 기존 COLMAP MVS의 effective neighbor membership은 복구되지 않았다. RGB 평가 영상이 '
        'MVS 생성에 간접적으로 쓰였을 수 있어 held-out/generalization 성능으로 주장할 수 없다.',
        '- Native prior protection, 초기화, Anchor8k 효과가 남아 있다. PGSR loss 이식은 기존 '
        'GeoGS expected-depth local plane에 적용되며 공식 PGSR depth renderer 전체 재현이 아니다.',
        '- 이 후처리는 새 seed 반복, mesh resolution/표면 sample 민감도 sweep, Roofer/CityGML 공식 판정, '
        'temporal currentness 자동 판정 또는 population inference를 수행하지 않는다.',
        '- Raw/post mesh, native render/depth, 실제 loss weight/mask count와 GPU 자원 로그, 동일-ID 거리 배열, '
        '학습 및 추출 영수증을 모두 남겼다. 개별 실패는 아래 영수증에 노출된다.', '',
        '[완료 영수증](final_receipt.json) · [실패/예외 목록](issues.json) · [원본 보존 검증](preservation.json)', '']
    issues = [row for row in regions if row['status'] != 'PASS']
    write(root / 'issues.json', {'status': status, 'issues': issues, 'scientific_verdict': None})
    preservation = []
    for job in doc['runs']:
        for record in job['files']:
            verify('/task', record)
            preservation.append(record)
    for control in doc['controls']:
        for surface in control['surfaces']:
            verify('/base', surface['surface'])
    write(root / 'preservation.json', {'status': 'PASS', 'new_training_files': preservation,
          'historical_surfaces_verified': 12, 'write_policy': 'training and historical payloads mounted read-only',
          'scientific_verdict': None})
    with (root / 'REPORT.md').open('x') as stream:
        stream.write('\n'.join(lines))
    write(root / 'final_receipt.json', {'task_id': doc['task_id'], 'status': status,
          'new_training_runs': 12, 'historical_controls': 6, 'raw_and_post_surfaces_scored': 36,
          'regions': regions, 'plan_sha256': sha(root / 'plan.json'), 'report_sha256': sha(root / 'REPORT.md'),
          'same_reference_ids_verified': True, 'scientific_verdict': None, 'completed_unix': time.time()})
    if status == 'PASS':
        host_attempt = os.environ['JBGS_FINAL_HOST_ATTEMPT']
        write('/resolver/finalization_receipt_v1.json', {'task_id': doc['task_id'], 'status': 'PASS',
              'run_index_sha256': doc['run_index_sha256'], 'report_path': str(Path(host_attempt) / 'REPORT.md'),
              'attempt_directory': host_attempt, 'new_training_runs': 12, 'historical_controls': 6,
              'raw_and_post_surfaces_scored': 36, 'same_reference_ids_verified': True,
              'final_receipt_sha256': sha(root / 'final_receipt.json'), 'scientific_verdict': None,
              'completed_unix': time.time()})
    print('Final report ' + status + ': /evaluation/REPORT.md', flush=True)
    if status != 'PASS':
        raise SystemExit(2)


def failure(args):
    output = Path('/evaluation')
    receipt = {'status': 'FAIL', 'stage': args.failure_stage, 'exit_code': args.exit_code,
               'scientific_verdict': None, 'failed_unix': time.time(),
               'preservation': 'fresh evaluation attempt; all originals were mounted read-only'}
    write(output / f'failure_{int(time.time())}.json', receipt)
    if not (output / 'REPORT.md').exists():
        with (output / 'REPORT.md').open('x') as stream:
            stream.write(f'# MVS/PGSR 후처리: FAIL\n\n문제: {args.failure_stage} 단계가 exit={args.exit_code}로 종료되었다. '
                         '원인은 해당 단계 로그와 실패 영수증을 확인해야 한다. 완료된 출력과 원본은 보존했다. '
                         '전체 실험 완료·성능 개선을 주장하지 않는다. `scientific_verdict: null`.\n')


def self_test(args):
    import numpy as np
    from PIL import Image
    import tempfile
    g, legacy, rq = load_legacy()
    base = {'reference_original_indices': np.array([2, 5, 9]), 'reference_points': np.zeros((3, 3)),
            'reference_to_triangle_distance': np.array([.1, .8, .1])}
    changed = dict(base, reference_to_triangle_distance=np.array([.8, .1, .1]))
    result = paired_arrays(base, changed, [.5])[0]
    assert result['recovered'] == result['damaged'] == result['retained'] == 1
    assert result['unresolved'] == result['net_recovered_minus_damaged'] == 0
    try:
        paired_arrays(base, dict(changed, reference_original_indices=np.array([9, 5, 2])), [.5])
        raise AssertionError('Mismatched IDs accepted')
    except ValueError:
        pass
    vertices = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], dtype=float)
    triangles = np.array([[0, 1, 2], [0, 2, 3]])
    reference = np.array([[.2, .2, 0], [.8, .2, 0], [.5, .8, 0]])
    metrics, arrays = g.evaluate_geometry(vertices, triangles, reference,
        {'x': [-.1, 1.1], 'y': [-.1, 1.1], 'z': [-.1, .1]}, thresholds=[.5])
    assert metrics['status'] == 'ASSESSED_DEVELOPMENT_ONLY'
    assert metrics['thresholds'][0]['recall'] == 1
    with tempfile.TemporaryDirectory() as folder:
        folder = Path(folder)
        image_path = folder / 'figure.png'
        Image.new('RGB', (100, 80), 'red').save(image_path)
        matched_figure(folder / 'combined.png', [('A', image_path), ('B', image_path)])
        assert (folder / 'combined.png').stat().st_size > 0
    print('PASS finalizer analytic same-ID transitions, mismatch rejection, legacy surface scorer, montage')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage', required=True, choices=('static', 'plan', 'extract', 'evaluate', 'report', 'failure', 'self-test'))
    parser.add_argument('--run-index', type=Path)
    parser.add_argument('--host-task')
    parser.add_argument('--region', choices=('P1', 'P2', 'P3'))
    parser.add_argument('--failure-stage', default='unknown')
    parser.add_argument('--exit-code', type=int, default=1)
    args = parser.parse_args()
    if not Path('/.dockerenv').exists():
        raise RuntimeError('Project tools run inside Docker only')
    {'static': static_preflight, 'plan': plan, 'extract': extract, 'evaluate': evaluate, 'report': report,
     'failure': failure, 'self-test': self_test}[args.stage](args)


if __name__ == '__main__':
    main()
