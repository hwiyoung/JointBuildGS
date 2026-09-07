"""Publish a byte-bound scientific RGB preview without any new quality scoring."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFont


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(8 << 20), b''):
            h.update(block)
    return h.hexdigest()


def checked(path, expected=None):
    path = Path(path)
    digest = sha(path)
    if expected is not None and digest != expected:
        raise ValueError('Input SHA differs: ' + str(path))
    return dict(path=str(path), sha256=digest, bytes=path.stat().st_size)


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    with Path(path).open('x') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')


def contained(root, relative):
    p = Path(relative)
    if p.is_absolute() or '..' in p.parts:
        raise ValueError('Non-contained path')
    return root / p


def rgb(path):
    with Image.open(path) as im:
        im.load()
        if im.mode != 'RGB':
            raise ValueError('Expected RGB source')
        return np.asarray(im).copy()


def main():
    if not Path('/.dockerenv').exists():
        raise RuntimeError('Docker required')
    started = time.time()
    task, writable = Path('/task'), Path('/preview')
    cfg = read('/gallery_config.json')
    if cfg['schema'] != 'GEOGS_SFM_PREVIEW22000_GALLERY_v1' or cfg['scientific_verdict'] is not None:
        raise ValueError('Wrong gallery contract')
    checked(task/'contracts/sfm_prefix22000_rgb_preview_v1.json', cfg['policy_sha256'])
    preview = contained(task, cfg['preview_relative'])
    proof = read(preview/'receipt.json')
    if not (proof['status'] == 'PASS' and proof['region'] == 'P2' and proof['iteration'] == 22000
            and proof['native_exit_code'] == proof['validated_exit_code'] == 0
            and proof['scientific_verdict'] is None and proof['main_completion_inferred'] is False
            and proof['geometry_assessed'] is False):
        raise ValueError('Actual official RGB preview has not passed')
    inputs = [checked(preview/'receipt.json'), checked('/gallery_config.json'),
              checked(task/cfg['baseline_seal_relative'], cfg['baseline_seal_sha256']),
              checked(task/cfg['roi_receipt_relative'], cfg['roi_receipt_sha256'])]
    outputs = {r['path']: r for r in proof['outputs']}
    seal = read(task/cfg['baseline_seal_relative'])
    baselines = {}
    for condition in cfg['baseline_conditions']:
        candidates = [c for c in seal['candidates'] if c['region'] == 'P2' and c['condition'] == condition
                      and c['variant'] == 'final' and c['render_records']]
        if len(candidates) != 1:
            raise ValueError('Expected one exact baseline render mapping')
        rows = candidates[0]['render_records']
        if len(rows) != 9 or {r['evaluation_index'] for r in rows} != set(range(9)):
            raise ValueError('Baseline image membership differs')
        baselines[condition] = {r['evaluation_index']: r for r in rows}
    rois = [r for r in read(task/cfg['roi_receipt_relative'])['rows']
            if r['domain'] == 'fixed_prism_projected_bbox' and r['status'] == 'ASSESSED']
    if len(rois) != 9 or {r['evaluation_index'] for r in rois} != set(range(9)):
        raise ValueError('Expected all nine fixed ROIs')
    out = writable / cfg['output_name']
    out.mkdir(exist_ok=False)
    (out/'assets').mkdir()
    label = ['실제 사진', 'GeoGS 원설정 · 전체 30k', '깊이 가중치 0.0005 · 전체 30k', 'SfM · Anchor 생략 · 22k']
    identifiers = ['photo', 'native', 'depth_relaxed', 'sfm22k']
    items, first_crops, checks = [], None, []
    for index in range(9):
        roi = next(r for r in rois if r['evaluation_index'] == index)
        records = [baselines[c][index] for c in cfg['baseline_conditions']]
        identity = ['name', 'evaluation_index', 'image_id', 'camera_id']
        if any(any(r[k] != roi[k] for k in identity) for r in records):
            raise ValueError('Image/pose identity differs')
        photo_rel = f'model/test/ours_22000/gt/{index:05d}.png'
        new_rel = f'model/test/ours_22000/renders/{index:05d}.png'
        for rel in [photo_rel, new_rel]:
            inputs.append(checked(preview/rel, outputs[rel]['sha256']))
        paths = [preview/photo_rel] + [contained(task, r['render_path']) for r in records] + [preview/new_rel]
        for r, path in zip(records, paths[1:3]):
            inputs.append(checked(path, r['render_sha256']))
            old_gt = path.parent.parent/'gt'/path.name
            inputs.append(checked(old_gt, r['exported_gt_sha256']))
            if not np.array_equal(rgb(old_gt), rgb(paths[0])):
                raise ValueError('New and baseline actual photo pixels differ')
        arrays = [rgb(path) for path in paths]
        if len({a.shape for a in arrays}) != 1:
            raise ValueError('Image dimensions differ')
        h, w, _ = arrays[0].shape
        box = [roi['roi_x0'], roi['roi_y0'], roi['roi_x1'], roi['roi_y1']]
        x0, y0, x1, y1 = box
        if not (0 <= x0 < x1 <= w and 0 <= y0 < y1 <= h and roi['pixel_count'] == (x1-x0)*(y1-y0)):
            raise ValueError('Invalid frozen half-open ROI')
        full, cropped, crops = [], [], []
        for ident, title, path, pixels in zip(identifiers, label, paths, arrays):
            full.append(dict(id=ident, label=title, url='/task/'+str(path.relative_to(task)),
                             sha256=sha(path), width=w, height=h))
            crop = pixels[y0:y1, x0:x1].copy()
            target = out/'assets'/f'{index:05d}.{ident}.png'
            Image.fromarray(crop).save(target)
            if not np.array_equal(rgb(target), crop):
                raise ValueError('Scientific crop pixel mismatch')
            cropped.append(dict(id=ident, label=title, url='/task/'+cfg['preview_relative']+'/'+cfg['output_name']+
                                '/assets/'+target.name, sha256=sha(target), width=x1-x0, height=y1-y0))
            crops.append(crop)
        items.append(dict(index=index, name=roi['name'], image_id=roi['image_id'], camera_id=roi['camera_id'],
                          roi=box, full=full, roi_images=cropped))
        checks.append(dict(index=index, photo_and_pose_identity=True, same_photo_pixels=True,
                           matching_dimensions=True, exact_crop_pixels=True))
        if index == cfg['first_index']:
            first_crops = crops
    manifest = dict(schema=cfg['schema'], scientific_verdict=None, status='OFFICIAL_RGB_PREVIEW', region='P2',
                    iteration=22000, main_completion_inferred=False, geometry_assessed=False,
                    parent_status_at_observation=proof['parent_status_at_observation'], first_index=cfg['first_index'],
                    total_images=9, baseline_total_iterations=30000, items=items,
                    preview_receipt_url='/task/'+cfg['preview_relative']+'/receipt.json',
                    prefix8000_viewer='/app/index.html?manifest=/task/evaluation/no_anchor_sfm_prefix8000_v1/profiles/viewer_v1/manifest.json&color=height')
    write(out/'manifest.json', manifest)
    shutil.copyfile('/code/gallery.html', out/'index.html')
    # Standalone scientific figure: original crop pixels, unchanged resolution.
    ch, cw, _ = first_crops[0].shape
    gutter, top, footer = 20, 104, 50
    fig = Image.new('RGB', (4*cw+5*gutter, top+ch+footer), '#fafafa')
    draw = ImageDraw.Draw(fig)
    font_path = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
    font = ImageFont.truetype(font_path, 20)
    title_font = ImageFont.truetype(font_path, 26)
    draw.text((gutter, 14), 'P2: fixed-photo comparison of official RGB renders', fill='#17202a', font=title_font)
    english = ['Actual photo', 'Native GeoGS | total 30k', 'Depth .0005 | total 30k', 'SfM, no Anchor | 22k preview']
    panels = []
    for i, (crop, title) in enumerate(zip(first_crops, english)):
        x = gutter+i*(cw+gutter)
        draw.text((x, 68), title, fill='#17202a', font=font)
        fig.paste(Image.fromarray(crop), (x, top))
        panels.append(dict(x=x, y=top, width=cw, height=ch,
                           pixels_sha256=hashlib.sha256(crop.tobytes()).hexdigest()))
    draw.text((gutter, top+ch+15), 'Fixed index 0; no resampling. Unequal total budgets; geometry is not assessed in this preview.',
              fill='#333333', font=font)
    fig_path = out/'P2_fixed_photo00000_preview22000.png'
    fig.save(fig_path)
    saved = rgb(fig_path)
    for p, crop in zip(panels, first_crops):
        if not np.array_equal(saved[p['y']:p['y']+ch, p['x']:p['x']+cw], crop):
            raise ValueError('Figure panel pixel mismatch')
    write(out/'receipt.json', dict(status='PASS_RGB_PREVIEW_GALLERY_BUILD', scientific_verdict=None,
            main_completion_inferred=False, geometry_assessed=False, quality_metrics_computed=False,
            started_unix=started, finished_unix=time.time(), inputs=inputs, checks=checks,
            manifest_sha256=sha(out/'manifest.json'), html_sha256=sha(out/'index.html'),
            figure=dict(path=fig_path.name, sha256=sha(fig_path), panels=panels),
            script_sha256=sha(__file__), preview_receipt_sha256=sha(preview/'receipt.json'),
            pixel_processing='Exact existing ROI crop and copy only; no resampling or color/exposure adjustment'))
    print(json.dumps(dict(status='PASS_RGB_PREVIEW_GALLERY_BUILD', images=9, figure=str(fig_path))))


if __name__ == '__main__':
    main()
