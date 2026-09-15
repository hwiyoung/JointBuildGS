"""Visualize sealed RGB, MVS and ALS-prior inputs in an isolated CPU container.

Run with only /mvs_input, /prior_input, /selection.json and /output mounts.
The figures retain original depth values, holes and legacy ray conventions.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import sys
import time

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.colors import ListedColormap
from matplotlib.patches import Rectangle
import numpy as np
from PIL import Image

sys.path.insert(0, '/repo')
from src.phd.geogs_mvs_pgsr_v1.mvs_depth import (
    checked_bytes, load_view_depth, read_colmap_depth,
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, data):
    with Path(path).open('x') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)


def summary(values):
    values = np.asarray(values)
    values = values[np.isfinite(values)]
    if not values.size:
        return {'count': 0}
    return {'count': int(values.size), 'min': float(values.min()),
            'median': float(np.median(values)), 'max': float(values.max()),
            'p02': float(np.percentile(values, 2)), 'p98': float(np.percentile(values, 98))}


def local_height(depth, K, R, t, pixel_offset=0, return_xyz=False):
    yy, xx = np.indices(depth.shape, dtype=np.float64)
    pixels = np.stack((xx + pixel_offset, yy + pixel_offset, np.ones_like(xx)), -1)
    rays = pixels @ np.linalg.inv(np.asarray(K, dtype=np.float64)).T
    valid = np.isfinite(depth) & (depth > 0)
    xyz = (rays * np.where(valid, depth, 0)[..., None] - np.asarray(t)) @ np.asarray(R)
    return np.where(valid[..., None], xyz, np.nan) if return_xyz else np.where(valid, xyz[..., 2], np.nan)


def sample_native_values(values, K_native, K_rgb, width, height):
    yy, xx = np.indices((height, width), dtype=np.float64)
    rays = np.stack((xx, yy, np.ones_like(xx)), -1)
    uv = rays @ (np.asarray(K_native) @ np.linalg.inv(np.asarray(K_rgb))).T
    ix = np.floor(uv[..., 0] / uv[..., 2] + .5).astype(int)
    iy = np.floor(uv[..., 1] / uv[..., 2] + .5).astype(int)
    valid = (ix >= 0) & (iy >= 0) & (ix < values.shape[1]) & (iy < values.shape[0])
    out = values[np.clip(iy, 0, values.shape[0]-1), np.clip(ix, 0, values.shape[1]-1)]
    return np.where(valid[..., None] if out.ndim == 3 else valid, out, np.nan)


def spatial_summary(xyz, cfg):
    valid = np.isfinite(xyz).all(axis=-1)
    result = {'valid_rgb_samples_of_native_rays': int(valid.sum())}
    if not valid.any():
        return result
    result['local_xyz_min'] = np.min(xyz[valid], axis=0).tolist()
    result['local_xyz_max'] = np.max(xyz[valid], axis=0).tolist()
    for name in ('evaluation_roi', 'training_context'):
        inside = valid.copy()
        for i, dim in enumerate(('x', 'y', 'z')):
            inside &= (xyz[..., i] >= cfg[name][dim][0]) & (xyz[..., i] <= cfg[name][dim][1])
        result[name + '_fraction_of_valid'] = float(inside.sum() / valid.sum())
    return result


def image_panel(ax, values, title, *, limits=None, cmap=None, unit=None):
    if limits is None:
        im = ax.imshow(values, interpolation='nearest')
    else:
        palette = matplotlib.colormaps[cmap].copy()
        palette.set_bad('#dedede')
        im = ax.imshow(np.ma.masked_invalid(values), interpolation='nearest',
                       cmap=palette, vmin=limits[0], vmax=limits[1])
        bar = ax.figure.colorbar(im, ax=ax, fraction=.043, pad=.025, extend='both')
        bar.set_label(unit, fontsize=10)
    ax.set_title(title, loc='left', fontsize=12, pad=9)
    ax.set_xticks([])
    ax.set_yticks([])
    return im


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--config', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--commit', required=True)
    p.add_argument('--runtime-image-id', required=True)
    args = p.parse_args()
    if not Path('/.dockerenv').exists() or Path('/artifacts/JointBuildGS').exists() or Path('/reference').exists():
        raise RuntimeError('Use an isolated Docker CPU run without broad artifact or reference mounts')
    start = time.monotonic()
    cfg = json.loads(args.config.read_text())
    out = args.output
    out.mkdir(parents=True, exist_ok=False)
    (out / 'config.json').write_bytes(args.config.read_bytes())
    try:
        binding_path = Path('/mvs_input/bindings.json')
        binding = json.loads(checked_bytes(binding_path, cfg['binding_sha256']))
        selection_path = Path('/selection.json')
        selection = json.loads(checked_bytes(selection_path, cfg['selection_sha256']))
        manifest_path = Path('/prior_input/input_manifest.json')
        manifest = json.loads(checked_bytes(manifest_path, binding['parent_input_manifest_sha256']))
        files = {row['path']: row for row in manifest['files']}
        prior_receipt_path = Path('/prior_input/prior/receipt.json')
        prior_receipt_hash = files['prior/receipt.json']['sha256']
        checked_bytes(prior_receipt_path, prior_receipt_hash)
        font_manager.fontManager.addfont(cfg['font_path'])
        plt.rcParams.update({'font.family': font_manager.FontProperties(fname=cfg['font_path']).get_name(),
                             'axes.unicode_minus': False, 'figure.facecolor': 'white', 'font.size': 11})
        views = {v['name']: v for v in binding['train']}
        cases = {c['id']: c for c in selection['cases']}
        rows = []
        for case_id in cfg['selection_cases']:
            case = cases[case_id]
            if case['region'] != 'P1' or case['split'] != 'train':
                raise ValueError('Expected existing P1 train selection')
            view = views[case['view']['name']]
            for key in ('K', 'R', 't', 'name', 'sha256'):
                if view[key] != case['view'][key]:
                    raise ValueError('Selected camera differs from bound training camera: ' + key)
            name, stem = view['name'], Path(view['name']).stem
            rgb_path = Path('/prior_input/scene/images') / name
            native_path = Path('/mvs_input') / view['local_depth']
            prior_relative = 'prior/raw_depth/' + stem + '.npy'
            prior_path = Path('/prior_input') / prior_relative
            checked_bytes(prior_path, files[prior_relative]['sha256'])
            depth, valid, loader_receipt = load_view_depth(view, depth_path=native_path, rgb_path=rgb_path)
            native = read_colmap_depth(native_path, view['maps']['depth'])
            prior = np.load(prior_path, allow_pickle=False)
            rgb = np.asarray(Image.open(rgb_path).convert('RGB'))
            if prior.shape != depth.shape or rgb.shape[:2] != depth.shape:
                raise ValueError('Raster shapes differ')
            # Exact adapter sampling identity, including holes, using the actual native input.
            sampled = sample_native_values(native, view['maps']['depth']['K'], view['K'], view['width'], view['height'])
            sampled_valid = np.isfinite(sampled) & (sampled > 0)
            if not np.array_equal(sampled_valid, valid) or not np.array_equal(sampled[valid], depth[valid]):
                raise ValueError('Visualization sampling differs from actual MVS adapter')
            bbox = case['bbox']
            x0, y0, x1, y1 = map(int, bbox)
            if not (0 <= x0 < x1 <= view['width'] and 0 <= y0 < y1 <= view['height']):
                raise ValueError('Invalid existing crop')
            crop = np.s_[y0:y1, x0:x1]
            m = np.where(valid, depth, np.nan)[crop]
            pvalid = np.isfinite(prior) & (prior > 0)
            old = np.where(pvalid, prior, np.nan)[crop]
            photo = rgb[crop]
            common = np.isfinite(m) & np.isfinite(old)
            delta = np.full(m.shape, np.nan, dtype=np.float32)
            delta[common] = m[common] - old[common]
            valid_m, valid_p = np.isfinite(m), np.isfinite(old)
            limits = np.percentile(np.concatenate((m[valid_m], old[valid_p])), cfg['depth_display_percentiles']).tolist()
            state = valid_m.astype(np.uint8) + 2 * valid_p.astype(np.uint8)
            native_xyz = local_height(native, view['maps']['depth']['K'], view['R'], view['t'], return_xyz=True)
            mvs_xyz = sample_native_values(native_xyz, view['maps']['depth']['K'], view['K'], view['width'], view['height'])[crop]
            mvs_z = mvs_xyz[..., 2]
            prior_z = local_height(prior, view['K'], view['R'], view['t'], .5)[crop]
            case_out = out / case_id
            case_out.mkdir()
            Image.fromarray(photo).save(case_out / 'rgb_crop.png')
            np.savez_compressed(case_out / 'input_arrays.npz',
                                rgb=photo, mvs_camera_z=m, prior_camera_z=old,
                                mvs_minus_prior=delta, source_availability=state,
                                mvs_local_z=mvs_z, prior_local_z=prior_z,
                                mvs_local_xyz=mvs_xyz,
                                crop_xyxy=np.asarray(bbox), K=np.asarray(view['K']),
                                R=np.asarray(view['R']), t=np.asarray(view['t']))
            fig, axes = plt.subplots(2, 3, figsize=(16, 11))
            fig.suptitle('P1 · 실제 학습 입력 깊이 비교\n' + name, fontsize=17, x=.05, ha='left', y=.98)
            image_panel(axes[0, 0], photo, '① 현재 RGB · 같은 crop')
            image_panel(axes[0, 1], m, '② 현재 MVS depth', limits=limits, cmap='viridis', unit='카메라 Z 깊이 (m)')
            image_panel(axes[0, 2], old, '③ 과거 ALS prior depth', limits=limits, cmap='viridis', unit='카메라 Z 깊이 (m)')
            image_panel(axes[1, 0], delta, '④ MVS − prior · 차이 진단',
                        limits=[-cfg['difference_display_limit_m'], cfg['difference_display_limit_m']],
                        cmap='PuOr_r', unit='깊이 차이 (m) · 양수 = MVS가 더 멂')
            palette = ListedColormap(['#dedede', '#2075b5', '#dca839', '#464652'])
            im = axes[1, 1].imshow(state, vmin=-.5, vmax=3.5, cmap=palette, interpolation='nearest')
            axes[1, 1].set_title('⑤ 입력 존재 여부 · confidence 아님', loc='left', fontsize=12, pad=9)
            bar = fig.colorbar(im, ax=axes[1, 1], fraction=.043, pad=.025, ticks=[0, 1, 2, 3])
            bar.ax.set_yticklabels(['둘 다 결측', 'MVS만', 'prior만', '둘 다 존재'])
            axes[1, 1].set_xticks([]); axes[1, 1].set_yticks([])
            image_panel(axes[1, 2], rgb, '⑥ 원사진 내 표시 범위')
            axes[1, 2].add_patch(Rectangle((x0, y0), x1-x0, y1-y0, fill=False, ec='#e49b22', lw=2))
            fig.text(.05, .038, '회색 = 결측. 두 depth는 같은 색 범위이며 crop 내 합동 2–98 백분위 밖은 색만 포화 표시. 원값은 보존.', fontsize=10)
            fig.text(.05, .016, '차이는 정확도·변화 정답이 아님. MVS nearest 조회·prior 반 픽셀 ray 유지. 입력 가시화이며 학습·confidence 추정 없음.', fontsize=10)
            fig.subplots_adjust(left=.035, right=.965, bottom=.075, top=.89, hspace=.18, wspace=.30)
            fig.savefig(case_out / 'depth_comparison.png', dpi=140)
            plt.close(fig)
            fig, axes = plt.subplots(1, 3, figsize=(16, 6))
            fig.suptitle('P1 · 입력 depth에서 역투영한 높이 · ' + name, fontsize=15, y=.99)
            image_panel(axes[0], photo, '현재 RGB')
            image_panel(axes[1], mvs_z, '현재 MVS의 로컬 높이', limits=cfg['height_display_limits_local_z_m'], cmap='viridis', unit='로컬 Z (m)')
            image_panel(axes[2], prior_z, '과거 prior의 로컬 높이', limits=cfg['height_display_limits_local_z_m'], cmap='viridis', unit='로컬 Z (m)')
            fig.text(.035, .025, '각 입력의 원래 ray로 역투영. 같은 높이 색 범위. 높이는 입력 파생값이며 독립 관측·confidence가 아님.', fontsize=10)
            fig.subplots_adjust(left=.035, right=.96, bottom=.10, top=.89, wspace=.25)
            fig.savefig(case_out / 'height_comparison.png', dpi=140)
            plt.close(fig)
            candidate_rows = []
            candidates = cfg.get('candidate_rectangles', {}).get(case_id, [])
            if candidates:
                fig, axes = plt.subplots(1, 3, figsize=(16, 6))
                fig.suptitle('P1 · 첫 수동 가중치 실험의 영역 후보 · 아직 학습에 적용하지 않음', fontsize=15, y=.98)
                image_panel(axes[0], photo, '현재 RGB · 입력을 보고 정한 사각형 후보')
                image_panel(axes[1], m, '현재 MVS depth', limits=limits, cmap='viridis', unit='카메라 Z (m)')
                image_panel(axes[2], delta, 'MVS − prior · 차이 진단',
                            limits=[-cfg['difference_display_limit_m'], cfg['difference_display_limit_m']],
                            cmap='PuOr_r', unit='깊이 차이 (m)')
                for candidate in candidates:
                    a, b, c, d = map(int, candidate['bbox'])
                    if not (0 <= a < c <= m.shape[1] and 0 <= b < d <= m.shape[0]):
                        raise ValueError('Candidate rectangle outside crop')
                    s = np.s_[b:d, a:c]
                    for ax in axes:
                        ax.add_patch(Rectangle((a, b), c-a, d-b, fill=False, ec='white', lw=3))
                        ax.add_patch(Rectangle((a, b), c-a, d-b, fill=False, ec='#161622', lw=1.2))
                        ax.text(a+2, b+2, candidate['id'], ha='left', va='top', fontsize=13,
                                color='white', bbox={'facecolor':'#161622', 'edgecolor':'none', 'pad':2})
                    candidate_rows.append({**candidate, 'bbox_coordinates': 'crop-relative RGB pixel indices, half-open',
                                           'pixels': int(m[s].size), 'mvs_valid_fraction': float(valid_m[s].mean()),
                                           'prior_valid_fraction': float(valid_p[s].mean()),
                                           'mvs_camera_z_m': summary(m[s]), 'prior_camera_z_m': summary(old[s]),
                                           'difference_common_pixels_m': summary(delta[s]),
                                           'mvs_local_z_m': summary(mvs_z[s]), 'prior_local_z_m': summary(prior_z[s]),
                                           'mvs_native_ray_spatial_support': spatial_summary(mvs_xyz[s], cfg)})
                fig.text(.035, .035, 'A 지면 보정 후보   ·   B 인접 지면 대조   ·   C 주변 지붕 (기존 P1 평가 밖)   ·   D 수목 제외 검토', fontsize=11)
                fig.text(.035, .009, '표시용 후보이며 GT 라벨·자동 분할·다시점 마스크 아님. 원본 입력은 그대로 유지.', fontsize=9)
                fig.subplots_adjust(left=.035, right=.96, bottom=.115, top=.87, wspace=.25)
                fig.savefig(case_out / 'region_candidates.png', dpi=140)
                plt.close(fig)
            rows.append({'id': case_id, 'camera_name': name, 'crop_xyxy': bbox,
                         'candidate_regions': candidate_rows,
                         'crop_pixels': int(m.size), 'mvs_valid_pixels': int(valid_m.sum()),
                         'prior_valid_pixels': int(valid_p.sum()), 'common_valid_pixels': int(common.sum()),
                         'mvs_valid_fraction_is_not_confidence': float(valid_m.mean()),
                         'mvs_camera_z_m': summary(m), 'prior_camera_z_m': summary(old),
                         'mvs_minus_prior_camera_z_m': summary(delta),
                         'mvs_local_z_m': summary(mvs_z), 'prior_local_z_m': summary(prior_z),
                         'display_depth_limits_m': limits,
                         'display_clipped_mvs_pixels': int(((m < limits[0]) | (m > limits[1])).sum()),
                         'display_clipped_prior_pixels': int(((old < limits[0]) | (old > limits[1])).sum()),
                         'pgsr_selected_neighbor_count': len(binding['neighbor_graph']['graph'][name]['selected']),
                         'loader': loader_receipt, 'prior_sha256': sha(prior_path),
                         'actual_adapter_sample_identity': 'PASS', 'raw_sources_unchanged': True})
            # Recheck exact used source bytes; input mounts are also read-only.
            checked_bytes(prior_path, files[prior_relative]['sha256'])
            checked_bytes(rgb_path, view['sha256'])
            checked_bytes(native_path, view['maps']['depth']['sha256'])
            print(json.dumps({'case': case_id, 'camera': name, 'crop_valid_mvs': float(valid_m.mean())}), flush=True)
        write(out / 'receipt.json', {'task_id': cfg['task_id'], 'status': 'PASS_INPUT_VISUALIZATION_ONLY',
              'scientific_verdict': None, 'created_utc': datetime.now(timezone.utc).isoformat(),
              'seconds': time.monotonic()-start, 'commit': args.commit,
              'runtime_image_id': args.runtime_image_id, 'python': platform.python_version(),
              'numpy': np.__version__, 'matplotlib': matplotlib.__version__,
              'config_sha256': sha(args.config), 'script_sha256': sha(__file__),
              'loader_sha256': sha('/repo/src/phd/geogs_mvs_pgsr_v1/mvs_depth.py'),
              'binding_sha256': sha(binding_path), 'selection_sha256': sha(selection_path),
              'parent_input_manifest_sha256': sha(manifest_path),
              'prior_receipt_sha256': prior_receipt_hash, 'crs': manifest['crs'],
              'depth_frame': 'CAMERA_Z_METERS', 'mvs_sampling': 'Exact existing nearest native sampler',
              'prior_ray': 'Original Open3D u+0.5,v+0.5 retained',
              'difference_meaning': 'Same stored RGB index; MVS nearest-native sampling and prior half-pixel convention use nonidentical rays; not accuracy or change labels',
              'reference_accessed': False, 'training_executed': False, 'gpu_exposed': False,
              'confidence_inferred': False, 'supervision_masks_created': False,
              'selection_policy': cfg['selection_policy'], 'cases': rows,
              'outputs': [{'path': str(p.relative_to(out)), 'sha256': sha(p), 'bytes': p.stat().st_size}
                          for p in sorted(out.rglob('*')) if p.is_file()]})
    except Exception as exc:
        write(out / 'failure.json', {'status': 'FAILED', 'error': repr(exc), 'scientific_verdict': None})
        raise


if __name__ == '__main__':
    main()
