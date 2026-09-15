"""Create all-view region rasters and input-depth annotation figures on CPU."""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import sys
import time

import matplotlib
matplotlib.use('Agg')
from matplotlib import font_manager
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Patch
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mvs_depth import checked_bytes, read_colmap_depth, load_view_depth
from manual_region_masks_v1 import (unproject, polygon_mask, boundary_band,
                                    resample_nearest, make_regions)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)


def color_table(cfg):
    lut = np.zeros((7, 3), np.uint8)
    for key, value in cfg['colors'].items():
        lut[int(key)] = [int(value[i:i+2], 16) for i in (1, 3, 5)]
    return lut


def blend(base, labels, valid, lut):
    opacity = np.full(labels.shape, .36)
    opacity[labels == 6] = .48
    opacity[labels == 5] = .28
    opacity[~valid] = .72
    output = base*(1-opacity[..., None]) + lut[labels]*opacity[..., None]
    edges = boundary_band(labels, 0)
    # Colored outlines preserve the original depth shading inside each region.
    output[edges & valid] = lut[labels[edges & valid]]
    yy, xx = np.indices(labels.shape)
    hatch = (labels == 5) & valid & ((xx+yy) % 13 < 2)
    output[hatch] = output[hatch] * .55
    output[~valid] = [219, 219, 223]
    return output.clip(0, 255).astype(np.uint8)


def draw_figure(rgb, depth, labels, valid, view, index, cfg, lut, path, pdf):
    values = depth[valid]
    limits = np.percentile(values, cfg['depth_display_percentiles']) if values.size else [0, 1]
    if limits[1] <= limits[0]:
        limits[1] = limits[0] + 1
    norm = matplotlib.colors.Normalize(*limits, clip=True)
    depth_rgb = (matplotlib.colormaps['viridis'](norm(depth))[..., :3]*255).astype(np.uint8)
    depth_rgb[~valid] = [219, 219, 223]
    rgb_overlay = blend(rgb, labels, valid, lut)
    depth_overlay = blend(depth_rgb, labels, valid, lut)
    fig, ax = plt.subplots(2, 2, figsize=(14, 10.8))
    fig.suptitle(f'{cfg.get("region", "P1")} · 전체 영상의 수동 영역 / 다중 시점 전파 초안\n{index+1:02d}/{cfg["train_view_count"]} · {view["name"]}', x=.045, ha='left', fontsize=15, y=.975)
    panels = [(rgb, '현재 RGB · 전체 프레임'), (rgb_overlay, 'RGB 위 영역 표시'),
              (depth_rgb, '현재 MVS depth · 원래 결측 유지'), (depth_overlay, 'MVS depth 위 영역 표시')]
    for axis, (array, title) in zip(ax.flat, panels):
        axis.imshow(array, interpolation='nearest')
        axis.set_title(title, loc='left', fontsize=12)
        axis.axis('off')
    sm = matplotlib.cm.ScalarMappable(norm=norm, cmap='viridis')
    cax = fig.add_axes([.93, .20, .012, .255])
    cb = fig.colorbar(sm, cax=cax, extend='both')
    cb.set_label('카메라 Z 깊이 (m)', fontsize=10)
    handles = [Patch(facecolor=cfg['colors'][str(i)], edgecolor='#444444',
                     hatch='///' if i == 5 else None,
                     label=f'R{i} {cfg["region_labels"][str(i)]} · ' + ('α' if i == 1 else '1' if i in (2,3) else '0')) for i in range(1,7)]
    fig.legend(handles=handles, loc='lower center', bbox_to_anchor=(.48,.055), ncol=3, fontsize=11, frameon=False)
    fig.text(.045, .035, '표시 배율 예: α=4. 빗금=판단 유보, 연회색 결측=depth 감독 0. 숫자는 신뢰도 확률이 아닙니다.', fontsize=10)
    fig.text(.045, .015, '현재 MVS로 대응을 검사한 표시 초안 · 원본 입력/학습 변경 없음 · 깊이 색 범위는 시점별 2–98 백분위.', fontsize=9)
    fig.subplots_adjust(left=.04, right=.915, bottom=.14, top=.895, hspace=.18, wspace=.065)
    fig.savefig(path, dpi=115)
    pdf.savefig(fig, dpi=95)
    plt.close(fig)
    return rgb_overlay, depth_overlay, limits.tolist()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--runtime-image-id', required=True)
    args = parser.parse_args()
    if not Path('/.dockerenv').exists() or Path('/artifacts/JointBuildGS').exists() or Path('/reference').exists():
        raise RuntimeError('Use isolated CPU Docker with narrow input mounts')
    cfg = json.loads(args.config.read_text())
    start = time.monotonic()
    out = args.output
    out.mkdir(parents=True, exist_ok=False)
    for folder in ('views', 'manual_sources', 'contact_sheets'):
        (out / folder).mkdir()
    font_manager.fontManager.addfont(cfg['font_path'])
    plt.rcParams.update({'font.family': font_manager.FontProperties(fname=cfg['font_path']).get_name(), 'axes.unicode_minus':False, 'figure.facecolor':'white'})
    font = ImageFont.truetype(cfg['font_path'], 16)
    lut = color_table(cfg)
    try:
        binding = json.loads(checked_bytes('/mvs_input/bindings.json', cfg['binding_sha256']))
        manifest_path = Path('/prior_input/input_manifest.json')
        manifest = json.loads(checked_bytes(manifest_path, binding['parent_input_manifest_sha256']))
        views = binding['train']
        names = [v['name'] for v in views]
        if len(names) != cfg['train_view_count'] or len(set(names)) != len(names):
            raise ValueError('Unexpected train membership')
        if set(names) & set(binding.get('evaluation_names', [])):
            raise ValueError('Train/evaluation overlap')
        sources = []
        inputs = {'/mvs_input/bindings.json':cfg['binding_sha256'], str(manifest_path):binding['parent_input_manifest_sha256']}
        file_hashes = {row['path']:row['sha256'] for row in manifest['files']}
        for item in cfg['manual_sources']:
            view = views[item['train_index']]
            if view['name'] != item['name']:
                raise ValueError('Manual source differs from frozen camera index')
            rgb_path = Path('/prior_input/scene/images') / view['name']
            checked_bytes(rgb_path, view['sha256'])
            inputs[str(rgb_path)] = view['sha256']
            native_path = Path('/mvs_input') / view['local_depth']
            depth = read_colmap_depth(native_path, view['maps']['depth'])
            inputs[str(native_path)] = view['maps']['depth']['sha256']
            labels_rgb = polygon_mask(view['width'], view['height'], item['polygons'], item['default_region'])
            Kn = np.asarray(view['maps']['depth']['K'])
            labels_native = resample_nearest(labels_rgb, view['K'], Kn, depth.shape[1], depth.shape[0], 5).astype(np.uint8)
            edge = boundary_band(labels_native, cfg['source_boundary_native_px'])
            labels_native[edge & (labels_native != 4)] = 5
            source = {'view':view, 'depth':depth, 'labels':labels_native,
                      'xyz':unproject(depth, Kn, view['R'], view['t'])}
            if item.get('intervention_polygon'):
                candidate_rgb = polygon_mask(view['width'], view['height'], [item['intervention_polygon']], 0) == 1
                candidate = resample_nearest(candidate_rgb, view['K'], Kn, depth.shape[1], depth.shape[0], 0).astype(bool)
                candidate &= ~boundary_band(candidate, cfg['source_boundary_native_px'])
                source['candidate'] = candidate & np.isin(labels_native, cfg.get('intervention_base_regions', [3]))
                # Freeze the prior input consulted for this manual polygon; prior
                # is never used to render visibility or to derive target depth.
                prior_rel = 'prior/raw_depth/' + Path(view['name']).stem + '.npy'
                prior_path = Path('/prior_input') / prior_rel
                checked_bytes(prior_path, file_hashes[prior_rel])
                inputs[str(prior_path)] = file_hashes[prior_rel]
            Image.fromarray(labels_rgb).save(out / 'manual_sources' / (Path(view['name']).stem + '_manual_region_id.png'))
            Image.fromarray(lut[labels_rgb]).save(out / 'manual_sources' / (Path(view['name']).stem + '_manual_regions_color.png'))
            write_json(out / 'manual_sources' / (Path(view['name']).stem + '_polygons.json'), item)
            sources.append(source)
        rows, thumbs, highlights = [], [], []
        region = cfg.get('region', 'P1')
        with PdfPages(out / f'{region}_all_{len(views)}_views.pdf') as pdf:
            for index, view in enumerate(views):
                stem = Path(view['name']).stem
                folder = out / 'views' / f'{index:03d}_{stem}'
                folder.mkdir()
                rgb_path = Path('/prior_input/scene/images') / view['name']
                native_path = Path('/mvs_input') / view['local_depth']
                sampled, rgb_valid, _ = load_view_depth(view, depth_path=native_path, rgb_path=rgb_path)
                depth = read_colmap_depth(native_path, view['maps']['depth'])
                rgb = np.asarray(Image.open(rgb_path).convert('RGB'))
                inputs[str(rgb_path)] = view['sha256']
                inputs[str(native_path)] = view['maps']['depth']['sha256']
                result = make_regions(depth, view, sources, cfg)
                Kn = view['maps']['depth']['K']
                mapped = {key: resample_nearest(array, Kn, view['K'], view['width'], view['height'], 5 if key == 'region_id' else 0)
                          for key, array in result.items()}
                if not np.array_equal(mapped['valid'], rgb_valid):
                    raise ValueError('Region and existing depth loader use different valid pixels')
                exact_depth = resample_nearest(depth, Kn, view['K'], view['width'], view['height'])
                if not np.array_equal(sampled[rgb_valid], exact_depth[rgb_valid]):
                    raise ValueError('Depth raster differs from existing loader')
                labels = mapped['region_id'].astype(np.uint8)
                if not np.isin(labels, [1,2,3,4,5,6]).all() or np.any(mapped['weight'][~rgb_valid] != 0):
                    raise ValueError('Incomplete partition or nonzero invalid weight')
                np.savez_compressed(folder / 'native_masks.npz', **result)
                np.savez_compressed(folder / 'rgb_masks.npz', **mapped)
                Image.fromarray(labels).save(folder / 'region_id.png')
                Image.fromarray(lut[labels]).save(folder / 'regions_color.png')
                rgb_overlay, depth_overlay, depth_limits = draw_figure(rgb, sampled, labels, rgb_valid, view, index, cfg, lut, folder / 'full_frame.png', pdf)
                Image.fromarray(rgb_overlay).save(folder / 'rgb_overlay.jpg', quality=92)
                Image.fromarray(depth_overlay).save(folder / 'depth_overlay.png')
                weights = mapped['weight']
                weight_rgb = np.full(rgb.shape, [53,58,64], np.uint8)
                weight_rgb[weights == 1] = [203,219,229]
                weight_rgb[weights == cfg['display_alpha']] = [230,159,0]
                Image.fromarray(weight_rgb).save(folder / 'weight_alpha4.png')
                native_counts = {str(i):int((result['region_id'] == i).sum()) for i in range(1,7)}
                counts = {str(i):int((labels == i).sum()) for i in range(1,7)}
                inside = mapped['inside_context']
                support = int(inside.sum())
                classified = int((inside & np.isin(labels, [1,2,3,4])).sum())
                row = {'train_index':index, 'name':view['name'], 'native_shape':list(depth.shape), 'rgb_shape':list(rgb.shape[:2]),
                       'native_counts':native_counts, 'rgb_counts':counts,
                       'rgb_valid':int(rgb_valid.sum()), 'rgb_invalid':int((~rgb_valid).sum()),
                       'valid_context_rgb_samples':support, 'assigned_context_rgb_samples':classified,
                       'assigned_fraction_of_valid_context':classified / support if support else None,
                       'cross_view_conflict_rgb_samples':int(mapped['cross_view_conflict'].sum()),
                       'candidate_rgb_samples':counts['1'], 'manual_source':index in [s['train_index'] for s in cfg['manual_sources']],
                       'depth_color_limits_camera_z_m':depth_limits, 'folder':str(folder.relative_to(out))}
                write_json(folder / 'view.json', row)
                rows.append(row)
                thumb = Image.fromarray(depth_overlay).resize((350,253))
                thumbs.append((index, view['name'], counts['1'], thumb))
                if index in [s['train_index'] for s in cfg['manual_sources'][:2]]:
                    highlights.append((index, view['name'], rgb_overlay, depth_overlay))
                if index % 10 == 0 or index == len(views)-1:
                    print(json.dumps({'completed':index+1, 'total':len(views), 'candidate_pixels':counts['1'], 'assigned_context':row['assigned_fraction_of_valid_context']}, ensure_ascii=False), flush=True)
        for page, offset in enumerate(range(0, len(thumbs), 12), 1):
            canvas = Image.new('RGB', (1424, 954), '#ffffff')
            draw = ImageDraw.Draw(canvas)
            draw.text((12,8), f'{region} / MVS depth 영역 초안 / {offset+1}–{min(offset+12,len(thumbs))} of {len(views)}', fill='#222222', font=font)
            for j, (index, name, count, thumb) in enumerate(thumbs[offset:offset+12]):
                x, y = 6+(j%4)*356, 44+(j//4)*295
                canvas.paste(thumb, (x,y))
                draw.text((x,y+255), f'{index:02d} | {name[12:-4]} | R1 {count:,} px', fill='#222222', font=font)
            canvas.save(out / 'contact_sheets' / f'page_{page:02d}.jpg', quality=95)
        fig, axes = plt.subplots(2, 2, figsize=(15,11))
        for col, (index, name, rgb_overlay, depth_overlay) in enumerate(highlights):
            axes[0,col].imshow(rgb_overlay); axes[1,col].imshow(depth_overlay)
            axes[0,col].set_title(f'학습 시점 {index:02d} · RGB 영역 표시', loc='left', fontsize=13)
            axes[1,col].set_title(f'학습 시점 {index:02d} · MVS depth 영역 표시', loc='left', fontsize=13)
        for axis in axes.flat:
            axis.axis('off')
        handles = [Patch(facecolor=cfg['colors'][str(i)], label=f'{i} {cfg["region_labels"][str(i)]}') for i in range(1,7)]
        fig.legend(handles=handles, loc='lower center', bbox_to_anchor=(.5,.04), ncol=3, frameon=False, fontsize=12)
        fig.suptitle(f'{region} · 보정 시험 영역을 서로 다른 시점에 표시', fontsize=18, y=.975)
        fig.text(.045,.018,'주황=보정 시험 대상(α), 파랑/올리브=기본 1, 나머지=0. 빗금=판단 유보. 깊이 색 범위는 시점별로 다릅니다.',fontsize=11)
        fig.subplots_adjust(left=.035,right=.98,top=.91,bottom=.13,hspace=.15,wspace=.055)
        fig.savefig(out / f'{region}_two_views.png',dpi=130)
        plt.close(fig)
        csv_fields = ['train_index','name','rgb_valid','rgb_invalid','valid_context_rgb_samples','assigned_context_rgb_samples','assigned_fraction_of_valid_context','candidate_rgb_samples','cross_view_conflict_rgb_samples','manual_source','folder']
        with (out / 'coverage.csv').open('x',newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=csv_fields, extrasaction='ignore')
            writer.writeheader(); writer.writerows(rows)
        # Original inputs are checked again after generation, not merely trusted
        # because they were mounted read-only in this container.
        for path, expected in inputs.items():
            checked_bytes(path, expected)
        payloads = [{'path':str(p.relative_to(out)), 'bytes':p.stat().st_size, 'sha256':sha(p)} for p in sorted(out.rglob('*')) if p.is_file()]
        write_json(out / 'receipt.json', {'task_id':cfg['task_id'], 'status':'PASS_ALL_TRAIN_VIEW_ANNOTATION_DRAFT',
                   'scientific_verdict':None, 'training_executed':False, 'human_reviewed_all_pixels':False,
                   'created_at_utc':datetime.now(timezone.utc).isoformat(), 'runtime_seconds':time.monotonic()-start,
                   'commit':args.commit, 'runtime_image_id':args.runtime_image_id,
                   'versions':{'python':platform.python_version(),'numpy':np.__version__,'matplotlib':matplotlib.__version__},
                   'config':cfg, 'config_sha256':sha(args.config), 'input_hashes':inputs,
                   'source_snapshot_sha256':{p.name:sha(p) for p in sorted(Path(__file__).parent.iterdir()) if p.is_file()},
                   'views':rows, 'outputs':payloads, 'total_views':len(rows),
                   'views_with_candidate':sum(r['candidate_rgb_samples'] > 0 for r in rows),
                   'checks':{'exact_train_membership':True,'full_partition':True,'native_rgb_depth_loader_identity':True,'invalid_weights_zero':True,'inputs_rehashed_after':True},
                   'limitations':['Manual semantic annotations are a reviewable draft, not semantic ground truth.',
                                  'Transfer thresholds are not calibrated MVS confidence; apparent consistency can share reconstruction error.',
                                  f'All {len(views)} rasters are generated; per-pixel semantic accuracy is not certified.',
                                  'Current per-view transients not seen in the two manual sources may remain undiscovered.',
                                  'No reference data or evaluation cameras were used; no training integration or optimization ran.']})
        print(json.dumps({'status':'PASS_ALL_TRAIN_VIEW_ANNOTATION_DRAFT','views':len(rows),'output':str(out)},ensure_ascii=False),flush=True)
    except Exception as exc:
        write_json(out / 'failure.json', {'status':'FAILED','scientific_verdict':None,'exception':type(exc).__name__,'message':str(exc)})
        raise


if __name__ == '__main__':
    main()
