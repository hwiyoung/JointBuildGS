"""Measure the three P1 interventions after all final training states are sealed.

Native extraction runs in separate reference-free GPU containers. Measurements
use fixed input masks and the existing independent UAS scorer in a CPU container.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time

ALPHAS = (0, 1, 4)
TRAIN_NAME = 'DJI_20241217084553_0100_D.JPG'
EVAL_NAME = 'DJI_20241217084551_0099_D.JPG'
ANCHOR_SHA = 'c08a39aa2deb81b26dd4dd75d0be9e6bb5e150db503f9d422a05423388679274'
OUT = Path('/output')


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            h.update(block)
    return h.hexdigest()


def write(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def frozen_finalizer():
    sys.path.insert(0, '/driver')
    import finalize
    return finalize


def verify(path, expected):
    if sha(path) != expected:
        raise ValueError('Payload identity changed: ' + str(path))


def plan():
    import numpy as np
    if Path('/reference').exists():
        raise RuntimeError('No evaluation reference may be exposed during staging')
    f = frozen_finalizer()
    config = read('/experiment/config.json')
    if (config.get('scientific_verdict') is not None or config.get('alphas') != list(ALPHAS)
            or config.get('visual_weight') != .05 or config.get('dynamic_visual_weight') is not False
            or config.get('prior_weight') != .005 or config.get('protection') != 'native'):
        raise ValueError('The three fixed-weight native-protection conditions must be frozen')
    verify('/experiment/mask/r1_mask.npz', config['mask_sha256'])
    with np.load('/experiment/mask/r1_mask.npz', allow_pickle=False) as masks:
        for key in ('r1_mask', 'use_mask'):
            if masks[key].dtype != np.bool_ or masks[key].shape != (1013, 1400) or not masks[key].any():
                raise ValueError('The annotated-support experiment requires two frozen boolean RGB masks')
    verify('/experiment/source/render.py', sha('/source/render.py'))
    jobs = []
    for alpha in ALPHAS:
        run = Path('/experiment/train') / f'alpha_{alpha}'
        receipt = read(run / 'receipt.json')
        if (receipt.get('status') != 'PASS' or receipt.get('scientific_verdict') is not None
                or receipt.get('completed') is not True or receipt.get('alpha') != alpha
                or receipt.get('phase') != 'train' or receipt.get('final_iteration') != 30000
                or receipt.get('config_sha256') != sha('/experiment/config.json')
                or receipt.get('mask_sha256') != config['mask_sha256']
                or receipt.get('fixed_visual_weight') != .05):
            raise ValueError('All three training receipts must pass before extraction')
        restore = read(run / 'model/jbgs_restore.json')
        if (restore.get('checkpoint_sha256') != ANCHOR_SHA or restore.get('iteration') != 8000
                or restore.get('release') is not False or restore.get('lambda_lod_anchor') != .005):
            raise ValueError('Training did not use the same native protected P1 anchor')
        equivalence = restore.get('restore_equivalence', {})
        if (equivalence.get('status') != 'PASS'
                or equivalence.get('scope') != 'immediate_complete_anchor_restore'
                or equivalence.get('protection') != 'native_exact'
                or not all(equivalence.get(k) is True for k in (
                    'model_optimizer_exact', 'controller_exact', 'camera_order_and_stack_exact', 'rng_exact'))):
            raise ValueError('Complete anchor equivalence was not verified')
        complete_dir = run / 'model/jbgs_complete/iteration_30000'
        complete = read(complete_dir / 'receipt.json')
        if (complete.get('iteration') != 30000 or complete.get('scientific_verdict') is not None
                or complete.get('after_protection_registration') is not True):
            raise ValueError('Missing complete final iteration 30000 receipt')
        ply = run / 'model/point_cloud/iteration_30000/point_cloud.ply'
        verify(ply, complete['ply_sha256'])
        verify(complete_dir / 'point_cloud.ply', complete['ply_sha256'])
        verify(complete_dir / 'checkpoint.pth', complete['checkpoint_sha256'])
        dest = OUT / 'extractions' / f'alpha_{alpha}'
        (dest / 'model/point_cloud/iteration_30000').mkdir(parents=True)
        shutil.copyfile(ply, dest / 'model/point_cloud/iteration_30000/point_cloud.ply')
        shutil.copyfile(run / 'model/cfg_args', dest / 'model/cfg_args')
        job = {'id': f'P1.alpha_{alpha}', 'alpha': alpha, 'region': 'P1', 'mode': 'mvs',
               'prior': .005, 'scientific_verdict': None,
               'files': [{'path': str(ply), 'sha256': complete['ply_sha256']}],
               'source_provenance_sha256': sha('/source/mvs_pgsr_source_provenance.json'),
               'input_manifest_sha256': sha('/input/input_manifest.json'),
               'training_receipt_sha256': sha(run / 'receipt.json'),
               'final_complete_receipt_sha256': sha(complete_dir / 'receipt.json'),
               'final_gaussians': complete['gaussians'],
               'staged_cfg_sha256': sha(dest / 'model/cfg_args')}
        write(dest / 'job.json', job)
        jobs.append(job)
    write(OUT / 'plan.json', {'schema': 'P1_SINGLE_VIEW_WEIGHT_POSTPROCESS_v2', 'jobs': jobs,
          'scientific_verdict': None, 'config_sha256': sha('/experiment/config.json'),
          'mask_sha256': sha('/experiment/mask/r1_mask.npz'),
          'mask_keys': ['r1_mask', 'use_mask'], 'baseline': config['baseline'],
          'driver_sha256': sha(__file__), 'native_finalizer_sha256': sha('/driver/finalize.py'),
          'native_renderer_sha256': sha('/source/render.py'), 'reference_accessed': False,
          'created_unix': time.time()})


def stats(values):
    import numpy as np
    values = np.asarray(values)
    if not values.size:
        return {'n': 0, 'mae_m': None, 'median_abs_m': None, 'p95_abs_m': None,
                'rmse_m': None, 'signed_mean_m': None}
    absolute = np.abs(values)
    return {'n': int(values.size), 'mae_m': float(absolute.mean()),
            'median_abs_m': float(np.median(absolute)), 'p95_abs_m': float(np.quantile(absolute, .95)),
            'rmse_m': float(np.sqrt(np.mean(values ** 2))), 'signed_mean_m': float(values.mean())}


def render_record(folder, split, role, name):
    import numpy as np
    from PIL import Image
    rows = sorted(split[role], key=lambda row: row['name'])
    indices = [i for i, row in enumerate(rows) if row['name'] == name]
    if len(indices) != 1:
        raise ValueError('Requested camera is not unique in its frozen split: ' + name)
    index = indices[0]
    subdir = 'train' if role == 'train' else 'test'
    result = folder / 'model' / subdir / 'ours_30000'
    rgb_path = result / 'renders' / f'{index:05d}.png'
    gt_path = result / 'gt' / f'{index:05d}.png'
    depth_path = result / 'vis' / f'depth_{index:05d}.tiff'
    source_path = Path('/input/scene/images') / name
    with Image.open(gt_path) as a, Image.open(source_path) as b:
        actual = np.asarray(a.convert('RGB'))
        if not np.array_equal(actual, np.asarray(b.convert('RGB'))):
            raise ValueError('Rendered GT pixels do not match the claimed image: ' + name)
    with Image.open(rgb_path) as image:
        rgb = np.asarray(image.convert('RGB'))
    with Image.open(depth_path) as image:
        depth = np.asarray(image, dtype=np.float32)
    if depth.shape != actual.shape[:2] or rgb.shape != actual.shape:
        raise ValueError('Native render dimensions differ')
    record = {'name': name, 'role': role, 'index': index, 'gt_pixels_verified': True,
              'rgb_path': str(rgb_path.relative_to(OUT)), 'rgb_sha256': sha(rgb_path),
              'depth_path': str(depth_path.relative_to(OUT)), 'depth_sha256': sha(depth_path)}
    return rgb, depth, actual, record


def measurement_regions(mask, use_mask, valid):
    """Partition original valid pixels without treating excluded depth as supervision."""
    import numpy as np
    if (mask.dtype.kind != 'b' or use_mask.dtype.kind != 'b' or valid.dtype.kind != 'b'
            or mask.shape != valid.shape or use_mask.shape != valid.shape):
        raise ValueError('R1, use_mask and native validity must be boolean arrays on the same RGB raster')
    if np.any(use_mask & ~valid) or np.any(mask & valid & ~use_mask):
        raise ValueError('Frozen support must exclude invalid depth and contain every valid R1 pixel')
    regions = {'R1': mask & valid, 'other_used': use_mask & ~mask,
               'excluded_valid': ~use_mask & valid}
    membership = sum(region.astype(np.uint8) for region in regions.values())
    if not np.array_equal(membership, valid.astype(np.uint8)):
        raise ValueError('Response measurement regions must partition original valid depth exactly')
    return regions


def figures(frames, target, valid, mask, use_mask):
    import numpy as np
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap
    scale_rows = {}
    for role, name in (('train', TRAIN_NAME), ('evaluation', EVAL_NAME)):
        rows = 3 if role == 'train' else 2
        fig, axes = plt.subplots(rows, 4, figsize=(20, 4.5 * rows), constrained_layout=True)
        actual = frames[0][role][2]
        axes[0, 0].imshow(actual)
        axes[0, 0].set_title('Current image: ' + name)
        pool = target[valid] if role == 'train' else np.concatenate([
            frames[a][role][1][np.isfinite(frames[a][role][1]) & (frames[a][role][1] > 0)] for a in ALPHAS])
        if not pool.size:
            raise ValueError('No finite positive depth for the comparison figure')
        lower, upper = map(float, np.quantile(pool, [.01, .99]))
        if upper <= lower:
            upper = lower + 1.
        scale_rows[role] = {'depth_min_m': lower, 'depth_max_m': upper,
                            'display_only_percentiles': [1, 99], 'same_scale_across_alphas': True}
        if role == 'train':
            axes[1, 0].imshow(np.ma.masked_where(~valid, target), vmin=lower, vmax=upper, cmap='viridis')
            axes[1, 0].set_title('Frozen MVS camera-Z (m)')
            support_classes = np.where(mask, 2, np.where(use_mask, 1, 0))
            axes[2, 0].imshow(np.ma.masked_where(~valid, support_classes),
                              cmap=ListedColormap(['#777777', '#8fdf43', '#00d7e8']), vmin=0, vmax=2)
            axes[2, 0].set_title('R1=cyan / other used=lime / excluded=gray')
            errors = np.concatenate([np.abs(frames[a][role][1][valid & np.isfinite(frames[a][role][1])
                                        & (frames[a][role][1] > 0)] - target[valid & np.isfinite(frames[a][role][1])
                                        & (frames[a][role][1] > 0)]) for a in ALPHAS])
            error_max = max(float(np.quantile(errors, .95)), 1e-6) if errors.size else 1.
            scale_rows[role]['absolute_residual_max_m'] = error_max
        else:
            axes[1, 0].text(.5, .5, '0099_D: fixed evaluation camera\nShared depth scale across three outputs',
                            ha='center', va='center', transform=axes[1, 0].transAxes)
        depth_artist = residual_artist = None
        for col, alpha in enumerate(ALPHAS, 1):
            rgb, depth, _, _ = frames[alpha][role]
            axes[0, col].imshow(rgb)
            axes[0, col].set_title(f'alpha={alpha}: native RGB')
            ok = np.isfinite(depth) & (depth > 0)
            depth_artist = axes[1, col].imshow(np.ma.masked_where(~ok, depth), vmin=lower, vmax=upper, cmap='viridis')
            axes[1, col].set_title(f'alpha={alpha}: rendered camera-Z (m)')
            if role == 'train':
                residual_artist = axes[2, col].imshow(np.ma.masked_where(~(valid & ok), np.abs(depth-target)),
                                                     vmin=0, vmax=error_max, cmap='magma')
                axes[2, col].set_title(f'alpha={alpha}: |render - MVS| (m)')
                for row in (0, 1, 2):
                    axes[row, col].contour(mask.astype(float), levels=[.5], colors=['cyan'], linewidths=.6)
                    axes[row, col].contour(use_mask.astype(float), levels=[.5], colors=['lime'],
                                           linewidths=.7, linestyles='dashed')
        for axis in axes.flat:
            axis.set_axis_off()
        fig.colorbar(depth_artist, ax=axes[1, 1:].tolist(), shrink=.7, label='Camera-Z (m)')
        if residual_artist is not None:
            fig.colorbar(residual_artist, ax=axes[2, 1:].tolist(), shrink=.7, label='Input fit error (m)')
        fig.suptitle('P1 single-view weight response; cyan: R1, dashed lime: used depth support; input fit is not accuracy')
        stem = 'train_0100_comparison' if role == 'train' else 'evaluation_0099_comparison'
        fig.savefig(OUT / (stem+'.png'), dpi=130)
        fig.savefig(OUT / (stem+'.pdf'))
        plt.close(fig)
    return scale_rows


def uas_measurements(plan_doc, extractions):
    import numpy as np
    import open3d as o3d
    f = frozen_finalizer()
    g, _, _ = f.load_legacy()
    reference_path = Path('/reference/P1/reference.npz')
    verify(reference_path, f.REFERENCE_SHAS['P1'])
    reference = np.load(reference_path, allow_pickle=False)['uas_xyz']
    cfg = read('/evaluation_config.json')
    ev, domain = cfg['evaluation'], cfg['regions']['P1']['domain']
    all_arrays, metric_rows = {}, []
    for alpha in ALPHAS:
        for kind in ('raw', 'post'):
            folder = OUT / 'uas' / f'alpha_{alpha}' / kind
            folder.mkdir(parents=True)
            source = OUT / 'extractions' / f'alpha_{alpha}' / extractions[alpha]['surfaces'][kind]['path']
            mesh = o3d.io.read_triangle_mesh(str(source))
            metrics, arrays = g.evaluate_geometry(np.asarray(mesh.vertices), np.asarray(mesh.triangles),
                reference, domain, ev['surface_sample_spacing_m'], ev['reference_voxel_m'], 0,
                ev['thresholds_m'], xy_cell_size=ev['xy_cell_m'])
            metrics.update(alpha=alpha, mesh_kind=kind, region='P1', crs=cfg['crs'],
                           source_sha256=sha(source), reference_sha256=sha(reference_path),
                           scientific_verdict=None, interpretation='Independent UAS proximity; development only')
            write(folder / 'metrics.json', metrics)
            g.save_distance_arrays(folder / 'distances.npz', arrays)
            all_arrays[alpha, kind] = arrays
            metric_rows.append({'alpha': alpha, 'mesh_kind': kind, 'status': metrics['status'],
                'ref2surface_mean_m': metrics['reference_to_prediction_triangle']['mean'],
                'surface2ref_mean_m': metrics['prediction_to_reference_point']['mean'],
                'thresholds': metrics['thresholds']})
            del mesh
    pairs = []
    for alpha in (0, 4):
        for kind in ('raw', 'post'):
            for row in f.paired_arrays(all_arrays[1, kind], all_arrays[alpha, kind], ev['thresholds_m']):
                pairs.append({'baseline_alpha': 1, 'alpha': alpha, 'mesh_kind': kind, **row})
    write(OUT / 'uas_summary.json', {'scientific_verdict': None, 'metrics': metric_rows,
          'paired_same_reference_ids': pairs, 'reference_sha256': sha(reference_path),
          'evaluation_config_sha256': sha('/evaluation_config.json'), 'same_reference_ids_verified': True,
          'scope': 'Fixed P1 prism; no automatic projection of the 2D R1 mask into UAS labels'})
    return metric_rows


def measure():
    import numpy as np
    f = frozen_finalizer()
    plan_doc = read(OUT / 'plan.json')
    for path, key in (('/experiment/config.json', 'config_sha256'),
                      ('/experiment/mask/r1_mask.npz', 'mask_sha256'),
                      (__file__, 'driver_sha256'), ('/driver/finalize.py', 'native_finalizer_sha256')):
        verify(path, plan_doc[key])
    split = read('/input/scene/split_manifest_da3_v2.json')
    binding = read('/mvs/bindings.json')
    view = next(row for row in binding['train'] if row['name'] == TRAIN_NAME)
    sys.path.insert(0, '/source')
    from jbgs_mvs_pgsr_depth import load_view_depth
    target, valid, target_receipt = load_view_depth(view, depth_path=Path('/mvs') / view['local_depth'],
                                            rgb_path=Path('/input/scene/images') / TRAIN_NAME)
    with np.load('/experiment/mask/r1_mask.npz', allow_pickle=False) as data:
        mask = data['r1_mask'].copy()
        use_mask = data['use_mask'].copy()
    if mask.dtype.kind != 'b' or mask.shape != target.shape or not mask.any() or mask.all():
        raise ValueError('R1 must be a nontrivial boolean mask on the exact 0100_D RGB raster')
    regions = measurement_regions(mask, use_mask, valid)
    frames, extractions = {}, {}
    expected_parameters = None
    for job in plan_doc['jobs']:
        alpha = job['alpha']
        folder = OUT / 'extractions' / f'alpha_{alpha}'
        verify(folder / 'model/cfg_args', job['staged_cfg_sha256'])
        receipt = read(folder / 'receipt.json')
        if receipt['status'] != 'PASS' or receipt['job'] != job:
            raise ValueError('Extraction did not pass with the staged final identity')
        for surface in receipt['surfaces'].values():
            verify(folder / surface['path'], surface['sha256'])
        parameters = {key: receipt['realized_extraction'][key] for key in (
            'mesh_res', 'num_cluster', 'voxel_size_m', 'sdf_trunc_m', 'depth_trunc_m')}
        if expected_parameters is not None and parameters != expected_parameters:
            raise ValueError('Actual extraction settings differ between intervention arms')
        expected_parameters = parameters
        extractions[alpha] = receipt
        frames[alpha] = {role: render_record(folder, split, role, name)
                        for role, name in (('train', TRAIN_NAME), ('evaluation', EVAL_NAME))}
    common = valid.copy()
    for alpha in ALPHAS:
        depth = frames[alpha]['train'][1]
        common &= np.isfinite(depth) & (depth > 0)
    results = []
    for alpha in ALPHAS:
        depth = frames[alpha]['train'][1]
        predicted_valid = np.isfinite(depth) & (depth > 0)
        for label, domain in regions.items():
            available = domain & predicted_valid
            common_domain = common & domain
            results.append({'alpha': alpha, 'region': label, 'fixed_mvs_valid_pixels': int(domain.sum()),
                'render_valid_pixels': int(available.sum()),
                'render_valid_fraction': float(available.sum()/domain.sum()) if domain.any() else None,
                'available_render_fit': stats(depth[available]-target[available]),
                'same_pixels_all_alphas_fit': stats(depth[common_domain]-target[common_domain]),
                'target_camera_supervision_multiplier': alpha if label == 'R1' else (1 if label == 'other_used' else 0),
                'interpretation': ('Excluded-depth discrepancy diagnostic; not a training loss or independent accuracy'
                    if label == 'excluded_valid' else 'Training-input fit; not independent geometry accuracy'),
                'scientific_verdict': None})
    write(OUT / 'input_fit.json', {'scientific_verdict': None, 'source': target_receipt,
          'mask_sha256': plan_doc['mask_sha256'], 'results': results,
          'mask_keys': ['r1_mask', 'use_mask'],
          'region_valid_pixel_counts': {name: int(region.sum()) for name, region in regions.items()},
          'excluded_depth_policy': 'Excluded from 0100_D MVS loss; geometry can still respond to RGB, prior and other views',
          'validity': 'finite positive rendered camera-Z; no opacity support assertion',
          'render_records': {str(a): {role: data[3] for role, data in frames[a].items()} for a in ALPHAS}})
    with (OUT / 'input_fit.csv').open('x', newline='') as stream:
        fields = ['alpha', 'region', 'fixed_mvs_valid_pixels', 'render_valid_pixels',
                  'target_camera_supervision_multiplier', 'common_pixels', 'common_mae_m', 'common_p95_m']
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in results:
            measured = row['same_pixels_all_alphas_fit']
            writer.writerow({**{k: row[k] for k in fields[:5]}, 'common_pixels': measured['n'],
                             'common_mae_m': measured['mae_m'], 'common_p95_m': measured['p95_abs_m']})
    scales = figures(frames, target, valid, mask, use_mask)
    write(OUT / 'figure_scales.json', scales)
    uas_rows = uas_measurements(plan_doc, extractions)
    lines = ['# P1 · 0100_D R1 가중치 실험 결과', '',
        '상태: 세 조건 학습 완료 및 native TSDF512 추출·입력 반응·독립 UAS 개발 평가 완료.',
        '`scientific_verdict: null`', '',
        '## 비교 조건', '',
        '동일 complete Anchor8k에서 30000까지 학습한 alpha=0/1/4를 비교한다. '
        'prior=0.005와 native 보호를 유지한다. 실제 학습 가중치·조건은 각 training receipt와 trace가 소유한다.', '',
        'alpha=1은 0100_D의 사용자가 지정한 R1/R2/R3 감독 영역과 고정 MVS 계수 0.05를 사용하는 새 기준선이다. '
        '0100_D의 R4·미분류·범위 밖은 depth 감독에서 제외하고 나머지 97개 영상의 depth는 유지한다. '
        '과거 전체 유효 픽셀 또는 dynamic MVS 계수 실험과 동일 조건이라고 간주하지 않는다.', '',
        '## 0100_D 입력 반응', '',
        '아래 수치는 원 MVS 유효 픽셀을 R1, other_used(사용 영역 중 R1 밖), excluded_valid(사용 영역 밖)로 나누어 '
        'rendered depth와 MVS depth의 차이를 계산한 것이다. '
        '세 조건 모두 rendered depth가 유효한 동일 픽셀을 비교하며, 이것은 입력 적합도이고 독립 정확도가 아니다.', '',
        '**excluded_valid는 0100_D depth 감독에서 제외된 영역의 진단이다.** '
        '해당 영역의 형상은 RGB·prior·다른 97개 영상의 감독에 의해 계속 바뀔 수 있다. '
        'R1도 alpha=0 조건에서는 이 영상의 depth 감독을 받지 않는다.', '',
        '| alpha | 영역 | 동일 픽셀 수 | MAE (m) | P95 (m) |', '|---:|---|---:|---:|---:|']
    for row in results:
        s = row['same_pixels_all_alphas_fit']
        fmt = lambda value: 'NA' if value is None else f'{value:.4f}'
        lines.append(f"| {row['alpha']} | {row['region']} | {s['n']} | {fmt(s['mae_m'])} | {fmt(s['p95_abs_m'])} |")
    lines += ['', '[입력 반응 JSON](postprocess/input_fit.json) · [CSV](postprocess/input_fit.csv)', '',
        '![0100_D RGB/depth 비교](postprocess/train_0100_comparison.png)', '',
        '[0100_D PDF](postprocess/train_0100_comparison.pdf)', '',
        '![0099_D RGB/depth 비교](postprocess/evaluation_0099_comparison.png)', '',
        '[0099_D PDF](postprocess/evaluation_0099_comparison.pdf)', '',
        '## 표면과 독립 UAS 개발 평가', '',
        '세 조건의 실제 voxel·SDF truncation·depth truncation이 동일함을 검사했다. '
        'raw 표면을 주 비교로, postprocessed 표면을 보조로 보존한다. '
        '기존 P1 고정 공간과 동일 UAS 참조점 ID를 사용하며 2D R1을 UAS 평가 라벨로 전용하지 않는다.', '',
        '[독립 UAS 요약 및 동일 참조점 보정/손상 집계](postprocess/uas_summary.json)', '',
        '| alpha | 최종 Gaussian 수 | raw TSDF512 | post TSDF512 |', '|---:|---:|---|---|']
    for job in plan_doc['jobs']:
        alpha = job['alpha']
        root = f'postprocess/extractions/alpha_{alpha}/model/train/ours_30000'
        lines.append(f"| {alpha} | {job['final_gaussians']} | [raw]({root}/fuse.ply) | [post]({root}/fuse_post.ply) |")
    lines += ['', '## 해석 한계', '',
        '깊이 오차 감소만으로 특정 Gaussian의 이동·제거 또는 새 표면 생성이 입증되지는 않는다. '
        '출력 TIFF는 expected camera-Z이며 opacity나 실제 단일 표면 지지를 직접 검증하지 않는다. '
        '0099_D는 학습에서 제외된 고정 카메라이지만 역사 MVS 생성 이웃이 완전히 복구되지 않아 '
        '엄격히 독립적인 영상 검증이라고 주장하지 않는다. UAS 결과도 개발 비교이며 과학적 판정은 하지 않는다.', '']
    (OUT / 'REPORT.md').write_text('\n'.join(lines))
    write(OUT / 'receipt.json', {'status': 'PASS', 'completed': True, 'scientific_verdict': None,
          'alphas': list(ALPHAS), 'native_extraction_parameters': expected_parameters,
          'final_gaussian_counts': {str(j['alpha']): j['final_gaussians'] for j in plan_doc['jobs']},
          'same_reference_ids_verified': True, 'uas_surface_count': len(uas_rows),
          'report_sha256': sha(OUT / 'REPORT.md'), 'completed_unix': time.time()})
    print('PASS: three native extractions, named-camera figures, fixed-mask input fit and same-ID UAS development evaluation')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage', choices=('plan', 'measure'), required=True)
    args = parser.parse_args()
    if not Path('/.dockerenv').exists():
        raise RuntimeError('Docker execution required')
    {'plan': plan, 'measure': measure}[args.stage]()


if __name__ == '__main__':
    main()
