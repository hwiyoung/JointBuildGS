"""Read-only independent native-pixel, selected PSNR and section-count QA."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import resource
import sys
import time
from datetime import datetime, timezone

import numpy as np
from PIL import Image, __version__ as pillow_version


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(path.read_text())


def rgb(path):
    return np.asarray(Image.open(path).convert('RGB'))


def psnr(a, b):
    mse = float(np.mean((a.astype(np.float64) - b.astype(np.float64)) ** 2))
    if mse == 0:
        raise ValueError('Exact-image/infinite PSNR needs an explicit review adapter')
    return float(10 * np.log10(255 ** 2 / mse))


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evaluation', type=Path, required=True)
    parser.add_argument('--figures', type=Path, required=True)
    parser.add_argument('--task', type=Path, required=True)
    parser.add_argument('--parent', type=Path, required=True)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--allow-partial', action='store_true')
    args = parser.parse_args()
    require(Path('/.dockerenv').exists(), 'Docker required')
    out = args.output / ('attempt_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ'))
    out.mkdir(parents=True, exist_ok=False)
    started = time.time()
    bound = {}
    checks = []
    code_sha = sha(Path(__file__))

    def bind(path, expected=None):
        actual = sha(path)
        require(expected is None or actual == expected, 'Input digest differs: ' + str(path))
        bound[str(path)] = dict(path=str(path), sha256=actual, bytes=path.stat().st_size)
        return path

    from run_selection_v2 import run_from_evaluation
    resolver_path=Path(__file__).with_name('run_selection_v2.py')
    bind(resolver_path)
    (out/'run_selection_v2.py').write_bytes(resolver_path.read_bytes())
    try:
        cfg = read(bind(args.config))
        er = read(bind(args.evaluation / 'receipt.json'))
        fr = read(bind(args.figures / 'receipt.json'))
        full = er['status'] == 'COMPLETE_DEVELOPMENT_EVALUATION'
        require(full or (args.allow_partial and er['status'] == 'PARTIAL_DEVELOPMENT_EVALUATION'),
                'Full evaluation required unless explicit --allow-partial')
        require(er['scientific_verdict'] is None and fr['scientific_verdict'] is None, 'Scientific verdict forbidden')
        require(er['reference_used_for_training_or_parameter_selection'] is False, 'Reference use boundary differs')
        require(fr['raw_photo_ox_or_temporal_truth_inferred'] is False, 'Figure interpretation boundary differs')
        require(cfg['runtime']['image_id'] == os.environ['JBGS_RUNTIME_IMAGE_ID'], 'Pinned image differs')
        require({r['sha256'] for r in er['inputs'] if r['path'].endswith('/experiment_v2.json')} == {sha(args.config)}, 'Config binding differs')
        eo = {r['path']: r['sha256'] for r in er['outputs']}
        fi = {r['path']: r['sha256'] for r in fr['inputs']}
        require(fi.get(str(args.evaluation / 'receipt.json')) == sha(args.evaluation / 'receipt.json'), 'Figure/evaluation identity differs')
        expected = {(Path(k).parts[0], Path(k).parts[1]) for k in eo if len(Path(k).parts) == 3 and k.endswith('/raw_metrics.json')}
        observed = {(r['region'], r['condition']) for r in fr['records']}
        require(expected == observed and len(fr['records']) == len(expected) == er['run_count'], 'Figure condition membership differs')
        if full:
            require(len(expected) == len(cfg['regions']) * len(cfg['conditions']) == 18, 'Full18 membership differs')
        for record in fr['outputs']:
            path = bind(args.figures / record['path'], record['sha256'])
            require(path.stat().st_size == record['bytes'], 'PNG byte count differs')
        appearance_path = bind(args.evaluation / 'appearance_per_image.csv', eo['appearance_per_image.csv'])
        with appearance_path.open(newline='') as stream:
            appearance = list(csv.DictReader(stream))
        seal_path = args.parent / 'contracts/candidates_sealed_v1.json'
        seal = read(bind(seal_path, fi[str(seal_path)]))
        for record in fr['records']:
            region, condition, name = (record[k] for k in ('region', 'condition', 'photograph'))
            case = args.figures / record['figure_directory']
            full_png, crop = rgb(case / 'matched_camera_full.png'), rgb(case / 'matched_camera_roi.png')
            x0, y0, x1, y1 = record['crop']['bbox']
            w, h = x1 - x0, y1 - y0
            _, _, fw, fh = record['full']['bbox']
            require(full_png.shape == (fh + 56, fw * 4, 3) and crop.shape == (h + 56, w * 4, 3), 'Native panel dimensions differ')
            for i in range(4):
                require(np.array_equal(crop[56:, i*w:(i+1)*w], full_png[56+y0:56+y1, i*fw+x0:i*fw+x1]), 'ROI is not the corresponding native-pixel crop')
            photo_path = args.parent / 'inputs' / region / 'scene/images' / name
            photo = rgb(bind(photo_path, fi[str(photo_path)]))
            gcases = [r for r in seal['candidates'] if (r['region'], r['condition'], r['variant'], r['mesh_kind']) ==
                      (region, condition.removeprefix('LC_'), 'final', 'raw')]
            require(len(gcases) == 1, 'Matched G identity is not unique')
            gcase = gcases[0]
            anchors = [r for r in seal['candidates'] if (r['region'], r['condition'], r['variant'], r['mesh_kind']) ==
                       (region, 'D005_Pnative', 'anchor_512', 'raw')]
            require(len(anchors) == 1, 'Anchor render candidate is not unique')
            ar = [r for r in anchors[0]['render_records'] if r['name'] == name]
            require(len(ar) == 1, 'Selected Anchor camera is not unique')
            ar = ar[0]
            anchor = rgb(bind(args.parent / ar['render_path'], ar['render_sha256']))
            expected_names = {r['name'] for r in gcase['render_records']}
            gr = [r for r in gcase['render_records'] if r['name'] == name]
            require(len(gr) == 1, 'Selected G camera is not unique')
            gr = gr[0]
            g = rgb(bind(args.parent / gr['render_path'], gr['render_sha256']))
            identity_path = args.evaluation / region / condition / 'render_identity.json'
            identity = read(bind(identity_path, eo[str(identity_path.relative_to(args.evaluation))]))
            lr = [r for r in identity['records'] if r['name'] == name]
            require(len(lr) == 1 and {r['name'] for r in identity['records']} == expected_names, 'Local camera membership differs')
            lr = lr[0]
            for key in ('camera_id', 'image_id', 'evaluation_index'):
                require(record[key] == ar[key] == gr[key] == lr[key], 'Selected camera identity differs: ' + key)
            run=run_from_evaluation(args.task,region,condition,er,bind)
            lc = rgb(bind(run / lr['render_path'], lr['render_sha256']))
            for i, actual in ((0, photo), (1, anchor), (2, g), (3, lc)):
                require(np.array_equal(full_png[56:, i*fw:(i+1)*fw], actual), 'Panel differs from original input image')
            result = dict(region=region, condition=condition, photo=name, image_id=record['image_id'],
                          camera_id=record['camera_id'], evaluation_index=record['evaluation_index'],
                          crop_bbox=record['crop']['bbox'], crop_pixels=w*h, exact_native_panels_and_crops=True,
                          independently_checked_panel_sources=['current_photo', 'Anchor8k', 'matched_G', 'LC'],
                          domains=[], section_count_checks=[])
            for domain in ('full_frame', 'fixed_prism_projected_bbox'):
                candidates = [r for r in appearance if r['region'] == region and r['candidate'] == condition and r['domain'] == domain]
                require(len(candidates) == len(expected_names) and {r['name'] for r in candidates} == expected_names, 'Appearance camera set differs')
                row = next(r for r in candidates if r['name'] == name)
                a, b, c, d = [int(row[k]) for k in ('roi_x0', 'roi_y0', 'roi_x1', 'roi_y1')]
                require(int(row['pixel_count']) == (c-a)*(d-b), 'Pixel denominator differs')
                require([a,b,c,d] == record['full' if domain == 'full_frame' else 'crop']['bbox'], 'Selected bbox differs')
                pg, pl = psnr(photo[b:d,a:c], g[b:d,a:c]), psnr(photo[b:d,a:c], lc[b:d,a:c])
                require(abs(pg-float(row['parent_psnr_native_db'])) < 1e-3 and abs(pl-float(row['psnr_cpu_float64_db'])) < 1e-9, 'Independent PSNR differs')
                key = 'psnr_native_db' if domain == 'full_frame' else 'psnr_cpu_float64_db'
                deltas = [float(r[key])-float(r['parent_psnr_native_db']) for r in candidates]
                result['domains'].append(dict(domain=domain, selected_g_psnr_db=pg, selected_lc_psnr_db=pl,
                    selected_delta_db=pl-pg, camera_count=len(candidates), positive_cameras=sum(v>0 for v in deltas),
                    negative_cameras=sum(v<0 for v in deltas), mean_delta_db=float(np.mean(deltas)),
                    mean_definition='camera-unweighted dB mean; not pooled pixel MSE'))
            metrics_path = args.evaluation / region / condition / 'raw_metrics.json'
            metrics = read(bind(metrics_path, eo[str(metrics_path.relative_to(args.evaluation))]))
            bounds = np.asarray(metrics['bounds_half_open'])
            for label, candidate in (('Anchor8k', 'D005_Pnative.anchor_512.raw'),
                                     ('Matched Global G', condition.removeprefix('LC_')+'.mesh_512.raw'), ('Local LC', None)):
                path = (args.parent / 'evaluation/geometry' / region / candidate / 'sample0.1_reference0.1.npz' if candidate
                        else args.evaluation / region / condition / 'raw_distances.npz')
                bind(path, fi[str(path)] if candidate else eo[str(path.relative_to(args.evaluation))])
                with np.load(path, allow_pickle=False) as arrays:
                    points, reference = arrays['prediction_surface_samples'], arrays['reference_points']
                    for section in (s for s in record['sections'] if s['candidate'] == label):
                        axis = 'XY'.index(section['axis'])
                        require(section['width_m'] == .5 and section['center_m'] == bounds[axis].mean(), 'Fixed section band differs')
                        require(section['horizontal_bounds_m'] == bounds[1-axis].tolist() and section['z_bounds_m'] == bounds[2].tolist(), 'Section axes differ')
                        pn = int(np.sum(np.abs(points[:,axis]-section['center_m']) < .25))
                        rn = int(np.sum(np.abs(reference[:,axis]-section['center_m']) < .25))
                        require((pn, rn) == (section['prediction_samples'], section['reference_samples']), 'Section counts differ')
                        result['section_count_checks'].append(dict(candidate=label, axis=section['axis'], prediction_samples=pn, reference_samples=rn))
            require(len(result['section_count_checks']) == 6, 'Missing section comparisons')
            checks.append(result)
        require(sha(Path(__file__)) == code_sha, 'Review source changed during execution')
        (out/'review_figures_v2.py').write_bytes(Path(__file__).read_bytes())
        (out/'config_snapshot.json').write_bytes(args.config.read_bytes())
        result = dict(schema='jbgs.actual_figure_integrity_review.v2', status='PASS_NATIVE_PIXEL_PSNR_AND_BAND_QA',
            review_revision='v2.2_explicit_evaluated_run_source',
            matrix_status='FULL18' if full else 'PARTIAL', scientific_verdict=None, run_count=len(checks),
            manual_visual_review_status='SEPARATE_REQUIRED', checks=checks, inputs=list(bound.values()), source_sha256=code_sha,
            command=sys.argv, wall_seconds=time.time()-started, peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
            runtime=dict(image_id=os.environ['JBGS_RUNTIME_IMAGE_ID'], python=sys.version, numpy=np.__version__, pillow=pillow_version,
                         cpu_max=Path('/sys/fs/cgroup/cpu.max').read_text().strip(), memory_max=Path('/sys/fs/cgroup/memory.max').read_text().strip()),
            raw_photo_ox_or_temporal_truth_inferred=False, source_causality_or_spatial_unique_effect_inferred=False)
        with (out/'receipt.json').open('x') as stream:
            json.dump(result, stream, indent=2, allow_nan=False); stream.write('\n')
        print(json.dumps(dict(status=result['status'], output=str(out), run_count=len(checks), scientific_verdict=None)), flush=True)
    except Exception as error:
        with (out/'failure.json').open('x') as stream:
            json.dump(dict(status='FAIL_FIGURE_QA', scientific_verdict=None, error=str(error), exception_type=type(error).__name__,
                           inputs=list(bound.values()), completed_checks=checks, source_sha256=code_sha), stream, indent=2, allow_nan=False)
        raise


if __name__ == '__main__':
    main()
