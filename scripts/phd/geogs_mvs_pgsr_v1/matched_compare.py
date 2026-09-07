"""Bounded matched comparison. Container stages separate inputs from UAS scoring."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
from datetime import datetime, timezone

sys.path.insert(0, '/snapshot')
import finalize as f

OUT = Path('/output')
BASE = Path('/base')
LABELS = {'da3': 'Vanilla GeoGS · DA3', 'mvs': 'MVS-only', 'mvs_pgsr': 'MVS+PGSR'}


def atomic(path, value):
    path = Path(path)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def plan(args):
    if Path('/reference').exists():
        raise RuntimeError('Reference access is prohibited during plan and staging')
    cfg = f.read('/snapshot/config.json')
    ex = f.read('/experiment.json')
    source_sha, config_sha = f.sha('/source/mvs_pgsr_source_provenance.json'), f.sha('/experiment.json')
    seal = f.read(BASE / 'contracts/candidates_sealed_v1.json')
    old = f.read(BASE / 'contracts/execution_v1.json')
    assert seal['config_sha256'] == f.sha(BASE / 'contracts/execution_v1.json')
    sys.path.insert(0, '/snapshot/legacy/evaluation')
    import render_quality as rq
    doc = {'config': cfg, 'config_sha256': f.sha('/snapshot/config.json'),
           'scientific_verdict': None, 'crs': old['crs'], 'evaluation': old['evaluation'],
           'regions': old['regions'], 'reference_sha256': f.REFERENCE_SHAS,
           'legacy_seal_sha256': f.sha(BASE / 'contracts/candidates_sealed_v1.json'),
           'code_sha256': {str(p.relative_to('/snapshot')): f.sha(p)
                          for p in sorted(Path('/snapshot').rglob('*.py'))},
           'controls': [], 'runs': [], 'views': {}}
    for region in cfg['regions']:
        selected = [r for r in seal['candidates'] if r['region'] == region
                    and r['condition'] == 'D005_Pnative' and r['iteration'] == 30000
                    and r['mesh_res'] == 512 and r['mesh_kind'] == 'raw' and not r.get('supplemental_only')]
        assert len(selected) == 1
        control = selected[0]
        f.verify(BASE, control['surface'])
        f.verify(BASE, control['final_complete_state']['point_cloud'])
        rgb = [r for r in seal['candidates'] if r['region'] == region
               and r['condition'] == 'D005_Pnative' and r['iteration'] == 30000
               and r['mesh_kind'] == 'raw' and r.get('render_records') and not r.get('supplemental_only')]
        assert len(rgb) == 1
        assert rgb[0]['render_input_point_cloud']['sha256'] == control['render_input_point_cloud']['sha256']
        render_records = []
        for record in rgb[0]['render_records']:
            assert f.sha(BASE / record['render_path']) == record['render_sha256']
            depth = Path(record['render_path']).parent.parent / 'vis' / f'depth_{record["evaluation_index"]:05d}.tiff'
            render_records.append({**record, 'depth_path': str(depth), 'depth_sha256': f.sha(BASE / depth)})
        doc['controls'].append({'region': region, 'mode': 'da3', 'surface': control['surface'],
            'ply': control['final_complete_state']['point_cloud'], 'renders': render_records,
            'realized_extraction': control['realized_extraction']})
        split = f.read(BASE / 'inputs' / region / 'scene/split_manifest_da3_v2.json')
        views = sorted(split['evaluation'], key=lambda r: r['name'])
        eligible = []
        for index, view in enumerate(views):
            box = rq.projected_prism_bbox(old['regions'][region]['domain'], view['R'], view['t'],
                                          view['K'], view['width'], view['height'])
            if box:
                eligible.append(((box[2]-box[0])*(box[3]-box[1]), -index, index, box))
        assert len(eligible) >= cfg['view_count']
        doc['views'][region] = [{'index': index, 'name': views[index]['name'], 'bbox': box,
                                'camera': views[index]} for _, _, index, box in
                               sorted(eligible, reverse=True)[:cfg['view_count']]]
        for mode in ('mvs', 'mvs_pgsr'):
            candidates = []
            expected = {'status': 'PASS', 'completed': True, 'phase': 'train', 'final_iteration': 30000,
                        'region': region, 'mode': mode, 'prior': .005, 'config_sha256': config_sha,
                        'source_provenance_sha256': source_sha, 'scientific_verdict': None,
                        'runtime_image_id': f.IMAGE_ID}
            for path in sorted((Path('/task/train') / region / (mode + '_0.005')).glob('attempt.*/receipt.json')):
                receipt = f.read(path)
                if all(receipt.get(k) == v for k, v in expected.items()):
                    candidates.append((path.parent, receipt))
            assert len(candidates) == 1, (region, mode, 'completed run ambiguity')
            run, receipt = candidates[0]
            relative = str(run.relative_to('/task'))
            complete = f.read(run / 'model/jbgs_complete/iteration_30000/receipt.json')
            ply = run / 'model/point_cloud/iteration_30000/point_cloud.ply'
            record = f.identity(ply, str(ply.relative_to('/task')))
            assert record['sha256'] == complete['ply_sha256'] == receipt['complete_state_receipt']['ply_sha256']
            identifier = f.candidate_id(region, mode, .005)
            destination = OUT / 'extractions' / identifier
            (destination / 'model/point_cloud/iteration_30000').mkdir(parents=True, exist_ok=False)
            shutil.copyfile(ply, destination / 'model/point_cloud/iteration_30000/point_cloud.ply')
            shutil.copyfile(run / 'model/cfg_args', destination / 'model/cfg_args')
            cfg_record = f.identity(run / 'model/cfg_args', str((run / 'model/cfg_args').relative_to('/task')))
            (destination / 'staged_cfg.sha256').write_text(cfg_record['sha256'] + '  model/cfg_args\n')
            job = {'id': identifier, 'region': region, 'mode': mode, 'prior': .005,
                   'training_relative': relative, 'files': [record, cfg_record],
                   'host_output_directory': str(Path(args.host_task) / relative),
                   'training_receipt_sha256': f.sha(run / 'receipt.json'),
                   'source_provenance_sha256': source_sha, 'config_sha256': config_sha,
                   'input_manifest_sha256': f.sha(BASE / 'inputs' / region / 'input_manifest.json'),
                   'scientific_verdict': None}
            f.write(destination / 'job.json', job)
            doc['runs'].append(job)
    f.write(OUT / 'plan.json', doc)
    (OUT / 'extractions.tsv').write_text(''.join(r['region']+'\t'+r['id']+'\n' for r in doc['runs']))
    print('PASS: four sealed finals, two controls, four input-selected views; no UAS access', flush=True)


def candidates(doc, region):
    control = next(r for r in doc['controls'] if r['region'] == region)
    result = [{'mode': 'da3', 'surface': f.verify(BASE, control['surface']),
               'renders': [{**r, 'render_path': str(BASE / r['render_path']),
                            'depth_path': str(BASE / r['depth_path'])} for r in control['renders']]}]
    for job in [r for r in doc['runs'] if r['region'] == region]:
        folder = OUT / 'extractions' / job['id']
        receipt = f.read(folder / 'receipt.json')
        assert receipt['status'] == 'PASS' and receipt['job'] == job
        for key in ('mesh_res', 'num_cluster', 'voxel_size_m', 'sdf_trunc_m', 'depth_trunc_m'):
            assert receipt['realized_extraction'][key] == control['realized_extraction'][key], key
        result.append({'mode': job['mode'], 'surface': f.verify(folder, receipt['surfaces']['raw']),
            'renders': [{**r, 'render_path': str(folder / r['render_path']),
                         'depth_path': str(folder / r['depth_path'])} for r in receipt['renders']]})
    return result


def evaluate(args):
    import numpy as np
    import open3d as o3d
    from PIL import Image
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    g, legacy, rq = f.load_legacy()
    doc = f.read(OUT / 'plan.json')
    for name, expected in doc['code_sha256'].items():
        assert f.sha(Path('/snapshot') / name) == expected
    region = args.region
    rows = candidates(doc, region)  # all region surfaces verified before reference is read
    refpath = Path('/reference') / region / 'reference.npz'
    assert f.sha(refpath) == doc['reference_sha256'][region]
    reference = np.load(refpath, allow_pickle=False)['uas_xyz']
    ev, bounds = doc['evaluation'], doc['regions'][region]['domain']
    folder = OUT / 'regions' / region
    folder.mkdir(parents=True, exist_ok=False)
    metrics, arrays_all, output_rows = {}, {}, []
    for row in rows:
        mode = row['mode']
        destination = folder / mode
        destination.mkdir()
        mesh = o3d.io.read_triangle_mesh(str(row['surface']))
        measured, arrays = g.evaluate_geometry(np.asarray(mesh.vertices), np.asarray(mesh.triangles),
            reference, bounds, ev['surface_sample_spacing_m'], ev['reference_voxel_m'], 0,
            ev['thresholds_m'], xy_cell_size=ev['xy_cell_m'])
        measured.update(region=region, mode=mode, surface_sha256=f.sha(row['surface']),
                        reference_sha256=doc['reference_sha256'][region], plan_sha256=f.sha(OUT / 'plan.json'))
        f.write(destination / 'metrics.json', measured)
        g.save_distance_arrays(destination / 'distances.npz', arrays)
        legacy.section_figure(destination / 'sections.png', arrays, arrays['reference_points'], bounds, region, mode)
        metrics[mode], arrays_all[mode] = measured, arrays
        for threshold in measured['thresholds']:
            output_rows.append({'region': region, 'mode': mode, **threshold,
                'p2ref_mean_m': measured['prediction_to_reference_point']['mean'],
                'ref2surface_mean_m': measured['reference_to_prediction_triangle']['mean'],
                'surface_area_m2': measured['surface_area_m2']})
        del mesh
    paired = []
    for previous, current in [('da3', 'mvs'), ('mvs', 'mvs_pgsr')]:
        paired.extend({'previous': previous, 'current': current, **r} for r in
                      f.paired_arrays(arrays_all[previous], arrays_all[current], ev['thresholds_m']))
    f.csv_write(folder / 'metrics.csv', output_rows)
    f.csv_write(folder / 'paired.csv', paired)
    f.matched_figure(folder / 'sections.png', [(r['mode'], folder / r['mode'] / 'sections.png') for r in rows])
    views = []
    for chosen in doc['views'][region]:
        index, name = chosen['index'], chosen['name']
        box = tuple(chosen['bbox'])
        target = folder / ('view_' + str(index))
        target.mkdir()
        photo = BASE / 'inputs' / region / 'scene/images' / name
        with Image.open(photo) as image:
            original = np.asarray(image.convert('RGB').crop(box))
        Image.fromarray(original).save(target / 'original.png')
        depth_arrays, renders = {}, {}
        errors = {}
        for row in rows:
            record = row['renders'][index]
            assert record['name'] == name
            assert f.sha(record['render_path']) == record['render_sha256']
            with Image.open(record['render_path']) as image:
                rgb = np.asarray(image.convert('RGB').crop(box))
            assert rgb.shape == original.shape
            renders[row['mode']] = rgb
            mse = float(np.mean((rgb.astype(float)/255-original.astype(float)/255)**2))
            errors[row['mode']] = {'roi_rgb_mse': mse, 'roi_psnr_db': float(-10*np.log10(max(mse, 1e-12)))}
            Image.fromarray(rgb).save(target / (row['mode'] + '_rgb.png'))
            depth = Path(record.get('depth_path', Path(record['render_path']).parent.parent / 'vis' / f'depth_{index:05d}.tiff'))
            if record.get('depth_sha256'):
                assert f.sha(depth) == record['depth_sha256']
            with Image.open(depth) as image:
                depth_arrays[row['mode']] = np.asarray(image, dtype=float)[box[1]:box[3], box[0]:box[2]]
        positives = [d[np.isfinite(d) & (d > 0)] for d in depth_arrays.values()]
        low, high = min(float(d.min()) for d in positives if len(d)), max(float(d.max()) for d in positives if len(d))
        cmap = plt.get_cmap('viridis')
        for mode, depth in depth_arrays.items():
            rgba = cmap(np.clip((depth-low)/max(high-low, 1e-6), 0, 1), bytes=True)
            rgba[~np.isfinite(depth) | (depth <= 0), :3] = 20
            Image.fromarray(rgba[:, :, :3]).save(target / (mode + '_depth.png'))
        fig, axes = plt.subplots(2, 4, figsize=(16, 8), constrained_layout=True)
        axes[0, 0].imshow(original); axes[0, 0].set_title('Original RGB')
        for col, row in enumerate(rows, 1):
            mode = row['mode']
            axes[0, col].imshow(renders[mode]); axes[0, col].set_title(LABELS[mode])
            axes[1, col].imshow(np.ma.masked_where(~np.isfinite(depth_arrays[mode]) | (depth_arrays[mode] <= 0), depth_arrays[mode]), vmin=low, vmax=high, cmap='viridis')
            axes[1, col].set_title('Camera-Z, same color range')
        for axis in axes.flat: axis.axis('off')
        fig.suptitle(region + ' / ' + name + ' / prior .005, same pose and crop')
        fig.savefig(target / 'comparison.png', dpi=130); plt.close(fig)
        views.append({**chosen, 'depth_range_m': [low, high], 'rgb_diagnostic': errors})
    f.write(folder / 'receipt.json', {'status': 'PASS', 'scientific_verdict': None, 'region': region,
            'same_reference_ids_verified': True, 'matched_extraction_parameters_verified': True,
            'metrics': metrics, 'paired': paired, 'views': views})
    print(region + ' PASS matched surface/reference and real RGB/depth', flush=True)


def qualify(value, prefix):
    if isinstance(value, dict):
        return {k: prefix+v if k == 'url' else qualify(v, prefix) for k, v in value.items()}
    if isinstance(value, list): return [qualify(v, prefix) for v in value]
    return value


def publish(args):
    from export_geometry import export_native_mesh
    publish_root = Path('/publish')
    publish_root.mkdir(parents=True, exist_ok=True)
    doc = f.read(OUT / 'plan.json')
    tag = f.sha(OUT / 'plan.json')[:20]
    target = publish_root / tag
    target.mkdir(exist_ok=False)
    regions, summary = [], []
    for region in doc['config']['regions']:
        result = f.read(OUT / 'regions' / region / 'receipt.json')
        assert result['status'] == 'PASS'
        domain = doc['regions'][region]['domain']
        bounds = {'min': [domain[a][0] for a in 'xyz'], 'max': [domain[a][1] for a in 'xyz']}
        conditions = []
        for row in candidates(doc, region):
            mode = row['mode']
            destination = target / region / mode
            destination.parent.mkdir(parents=True, exist_ok=True)
            data = export_native_mesh(row['surface'], destination, bounds, expected_sha=f.sha(row['surface']),
                                      point_cap=doc['config']['point_cap'])
            data = qualify(data, '/data/matched/' + tag + '/' + region + '/' + mode + '/')
            conditions.append({'id': mode, 'label': LABELS[mode], 'status': 'available',
                               'mesh': data['mesh'], 'color': data['color'], 'source': data['source']})
        image_target = target / region / 'images'
        image_target.mkdir()
        views = []
        for view in result['views']:
            index = view['index']
            prefix = 'view_' + str(index)
            src = OUT / 'regions' / region / prefix
            shutil.copytree(src, image_target / prefix)
            url = '/data/matched/' + tag + '/' + region + '/images/' + prefix + '/'
            def image_record(filename):
                path = image_target / prefix / filename
                return {'url': url + filename, 'bytes': path.stat().st_size, 'sha256': f.sha(path)}
            views.append({'id': str(index), 'image_name': view['name'], 'label': view['name'],
                'split': 'development evaluation; MVS independence unverified',
                'original': image_record('original.png'), 'depth_range_m': view['depth_range_m'],
                'roi_bbox': view['bbox'],
                'conditions': {mode: {'status': 'available', 'rgb': image_record(mode+'_rgb.png'),
                              'depth': image_record(mode+'_depth.png')} for mode in LABELS}})
        shutil.copyfile(OUT / 'regions' / region / 'sections.png', target / region / 'sections.png')
        regions.append({'id': region, 'bounds': bounds, 'conditions': conditions, 'views': views})
        summary.append(result)
    manifest = {'schema': 'geogs_matched_comparison_v1', 'scientific_verdict': None,
                'generated_at': datetime.now(timezone.utc).isoformat(),
                'surface_contract': {'label': 'prior 0.005 · 보호 유지 · 30,000 step · raw RGB TSDF512',
                                     'mesh_resolution': 512, 'surface': 'raw'}, 'regions': regions}
    f.write(target / 'manifest.json', manifest)
    f.write(target / 'measurements.json', summary)
    shutil.copyfile(OUT / 'plan.json', target / 'plan.json')
    atomic(publish_root / 'manifest.json', manifest)
    f.write(OUT / 'receipt.json', {'status': 'PASS_MATCHED_COMPARISON', 'scientific_verdict': None,
             'manifest_sha256': f.sha(target / 'manifest.json'), 'regions': ['P1', 'P2'],
             'url': 'http://127.0.0.1:8910/app/matched.html', 'published_relative': tag})
    print('PASS matched comparison published: ' + tag, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage', choices=['plan', 'evaluate', 'publish'], required=True)
    parser.add_argument('--region', choices=['P1', 'P2'])
    parser.add_argument('--host-task')
    args = parser.parse_args()
    {'plan': plan, 'evaluate': evaluate, 'publish': publish}[args.stage](args)
